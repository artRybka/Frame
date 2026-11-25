"""Polish words typed in Szukaj, translated for the museums abroad."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic

from frame_server.ai import AiConfigUpdate
from frame_server.ai.search_words import KIND, SearchWords
from frame_server.library import Item, Note
from frame_server.library.importer import language_of
from frame_server.library.wording import Wording
from frame_server.service import FrameService
from frame_server.web import create_app

GUITAR = {"polish": True, "english": "guitar", "french": "guitare"}


@pytest.fixture
def fake(service: FrameService) -> FakeAnthropic:
    clients: dict[str, FakeAnthropic] = {}

    def factory(key: str) -> FakeAnthropic:
        return clients.setdefault(key, FakeAnthropic(key))

    service.claude.factory = factory
    service.ai_config.set_key(GOOD_KEY)
    client = factory(GOOD_KEY)
    client.answer = GUITAR
    return client


def test_each_language_gets_its_words() -> None:
    words = Wording("gitara", "guitar", "guitare")
    assert words.in_language("pl") == "gitara"
    assert words.in_language("en") == "guitar"
    assert words.in_language("fr") == "guitare"
    assert Wording("Monet").in_language("en") == "Monet"
    assert language_of("mnw") == language_of("mnk") == "pl"
    assert language_of("paris") == "fr"
    assert language_of("met") == language_of("europeana") == "en"


def test_the_model_translates_once(service: FrameService, fake: FakeAnthropic) -> None:
    words = service.search_words.wording("  Gitara ")
    assert (words.text, words.en, words.fr) == ("Gitara", "guitar", "guitare")
    assert len(fake.asked) == 1
    assert "gitara" in str(fake.asked[0]["messages"]).casefold()
    # Remembered, also after a restart.
    assert service.search_words.wording("gitara").en == "guitar"
    again = SearchWords(service.library, service.claude, service.ai_config)
    assert again.wording("GITARA").en == "guitar"
    assert len(fake.asked) == 1
    assert service.claude.spending.by_kind().get(KIND, 0) > 0


def test_names_and_english_stay_as_typed(service: FrameService, fake: FakeAnthropic) -> None:
    fake.answer = {"polish": False, "english": "Monet", "french": "Monet"}
    words = service.search_words.wording("Monet")
    assert not words.translated and words.in_language("en") == "Monet"
    # Nothing to translate is remembered too.
    service.search_words.wording("monet")
    assert len(fake.asked) == 1


def test_words_in_another_language_go_to_the_polish_museums_in_polish(
    service: FrameService, fake: FakeAnthropic
) -> None:
    # The app's hint gave "The Storks" (Bracquemond's print); Warsaw found
    # nothing for it, its catalogue has Chełmoński's "Bociany" (2026-11-18).
    fake.answer = {
        "polish": False,
        "english": "The Storks",
        "french": "The Storks",
        "polish_words": "Bociany",
    }
    words = service.search_words.wording("The Storks")
    assert words.in_language("pl") == "Bociany"
    assert words.in_language("en") == "The Storks"
    assert service.search_words.known("the storks") == ("Bociany",)
    again = SearchWords(service.library, service.claude, service.ai_config)
    assert again.wording("The Storks").in_language("pl") == "Bociany"
    assert len(fake.asked) == 1
    asked = service.importer.asked('"The Storks"', ["mnw", "met"])
    assert asked.texts == {"mnw": "Bociany", "met": '"The Storks"'}  # Met keeps to phrases
    assert asked.said == [["The Storks", "Bociany"]]  # either is a match


def test_words_remembered_before_their_polish_are_asked_again(
    service: FrameService, fake: FakeAnthropic
) -> None:
    service.search_words._remember("the storks", {})  # as 1.145.232 kept it
    fake.answer = {
        "polish": False,
        "english": "The Storks",
        "french": "The Storks",
        "polish_words": "Bociany",
    }
    assert service.search_words.wording("The Storks").pl == "Bociany"
    assert len(fake.asked) == 1
    # A name stays as typed, and is not asked again.
    fake.answer = {"polish": False, "english": "Monet", "french": "Monet", "polish_words": "Monet"}
    assert service.search_words.wording("Monet").in_language("pl") == "Monet"
    service.search_words.wording("Monet")
    assert len(fake.asked) == 2


def test_the_library_knows_some_words_without_the_model(service: FrameService) -> None:
    item = service.library.upsert(Item(id="aic:1", source="aic", source_id="1", title="Port"))
    service.library.save_note(
        Note(
            item_id=item.id,
            kind="keywords",
            model="m",
            prompt_version="1",
            data={"tags_en": ["sailing boat", "harbour"], "tags_pl": ["żaglowiec", "port"]},
        )
    )
    words = SearchWords(service.library, service.claude, service.ai_config)
    assert words.wording("Żaglowiec").en == "sailing boat"
    assert words.wording("żaglowiec muzyka").en == "sailing boat music"  # with the vocabulary
    assert not words.wording("gitara").translated  # no key: as typed


def test_the_catalogue_knows_the_library_words_from_the_start(service: FrameService) -> None:
    """Before any search was translated (the counts of Playlisty after a
    start): "słoneczniki" in a playlist's rules finds the works whose words
    are English, 19 works and not 9 (Mateusz 2026-11-13)."""
    item = service.library.upsert(
        Item(id="wmc:1", source="wmc", source_id="1", title="Twelve Sunflowers in a Vase")
    )
    service.library.save_note(
        Note(
            item_id=item.id,
            kind="keywords",
            model="m",
            prompt_version="1",
            data={"tags_en": ["sunflowers"], "tags_pl": ["słoneczniki"]},
        )
    )
    words = SearchWords(service.library, service.claude, service.ai_config)
    assert words.known("słoneczniki") == ("sunflowers",)


def test_the_owner_can_switch_it_off(service: FrameService, fake: FakeAnthropic) -> None:
    service.ai_config.update(AiConfigUpdate(search_words=False))
    assert not service.search_words.wording("gitara").translated
    assert fake.asked == []


def test_a_slow_answer_serves_the_next_search(service: FrameService, fake: FakeAnthropic) -> None:
    held = threading.Event()
    create = fake.messages.create

    def slow(**params: Any) -> Any:
        held.wait(10)
        return create(**params)

    fake.messages.create = slow
    assert not service.search_words.wording("gitara", wait=0.05).translated
    held.set()
    assert service.search_words.wording("gitara", wait=5).en == "guitar"
    assert len(fake.asked) == 1


def test_an_answer_landing_mid_search_is_not_asked_again(
    service: FrameService, fake: FakeAnthropic, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first answer lands after the next search looked for it in what
    # is known but before it asks: that search must not ask again.
    words = service.search_words
    held = threading.Event()
    create = fake.messages.create

    def slow(**params: Any) -> Any:
        held.wait(10)
        return create(**params)

    fake.messages.create = slow
    assert not words.wording("gitara", wait=0.05).translated
    first = words._asking["gitara"]
    from_library = words._from_library

    def late(key: str) -> str:
        held.set()
        first.result(timeout=5)
        return from_library(key)

    monkeypatch.setattr(words, "_from_library", late)
    assert words.wording("gitara", wait=5).en == "guitar"
    assert len(fake.asked) == 1


def test_museums_are_asked_in_their_languages(
    service: FrameService, fake: FakeAnthropic, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: dict[str, str] = {}

    def search(
        source: str, query: str, limit: int = 24, page: int = 1, wait: Any = None, kind: str = "any"
    ) -> Any:
        asked[source] = query
        return 0, []

    monkeypatch.setattr(service.importer, "search", search)
    monkeypatch.setattr(service.importer, "sources", lambda: ["met", "mnw", "paris", "aic"])
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        found = client.get(
            "/api/discover/search",
            params={"q": "gitara", "source": ["met", "mnw", "paris"], "term": ["style:cubism"]},
        )
        assert found.status_code == 200
        assert asked == {"met": "guitar cubism", "mnw": "gitara cubism", "paris": "guitare cubism"}

        # The hint while typing asks no museum: what is kept at home, each
        # in its museum's language.
        asked.clear()
        at_home: dict[str, str] = {}

        def home(texts, limit=8):  # type: ignore[no-untyped-def]
            at_home.update(texts)
            return 0, [], []

        monkeypatch.setattr(service.importer, "at_home", home)
        assert client.get("/api/terms/museums", params={"q": "gitara"}).status_code == 200
        assert asked == {}
        assert at_home == {"met": "guitar", "mnw": "gitara", "paris": "guitare", "aic": "guitar"}
    assert len(fake.asked) == 1


def test_the_phone_translates_and_haiku_is_not_asked(
    service: FrameService, fake: FakeAnthropic
) -> None:
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        answer = client.post(
            "/api/search/words",
            json={
                "words": [
                    {"text": "Gitara", "en": "guitar", "fr": "guitare"},
                    # Given back as typed (a name): left to Haiku.
                    {"text": "Rembrandt", "en": "Rembrandt", "fr": "Rembrandt"},
                ]
            },
        )
    assert answer.status_code == 200
    assert answer.json() == {"kept": 1}
    words = service.search_words.wording("gitara")
    assert (words.en, words.fr) == ("guitar", "guitare")
    assert service.search_words.known("gitara") == ("guitar", "guitare")
    assert fake.asked == []
    # Kept after a restart too.
    again = SearchWords(service.library, service.claude, service.ai_config)
    assert again.wording("GITARA").en == "guitar"
    assert fake.asked == []


def test_the_phone_never_replaces_an_answer(service: FrameService, fake: FakeAnthropic) -> None:
    assert service.search_words.wording("gitara").en == "guitar"
    assert not service.search_words.taught("gitara", "guitars")
    assert service.search_words.wording("gitara").en == "guitar"
    # Without French the museums in French get the words as typed.
    assert service.search_words.taught("stara kobieta", "old woman")
    words = service.search_words.wording("stara kobieta")
    assert (words.en, words.fr) == ("old woman", "")
    assert words.in_language("fr") == "stara kobieta"
    assert len(fake.asked) == 1


def test_the_suggestions_never_wait_for_a_translation(
    service: FrameService, fake: FakeAnthropic
) -> None:
    """Mateusz 2026-11-25: "najpierw pytamy to co mamy już na NAS (reakcja
    natychmiastowa)": what is known now, the model asked behind once."""
    import time

    held = threading.Event()
    create = fake.messages.create

    def slow(**params: Any) -> Any:
        held.wait(10)
        return create(**params)

    fake.messages.create = slow
    started = time.monotonic()
    assert not service.search_words.ahead("stara gitara").translated
    assert not service.search_words.ahead("stara gitara").translated
    assert time.monotonic() - started < 0.5
    held.set()
    assert service.search_words.wording("stara gitara", wait=5).en == "guitar"
    assert service.search_words.ahead("stara gitara").en == "guitar"
    assert len(fake.asked) == 1
