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


def test_museums_are_asked_in_their_languages(
    service: FrameService, fake: FakeAnthropic, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: dict[str, str] = {}

    def search(source: str, query: str, limit: int = 24, page: int = 1, wait: Any = None) -> Any:
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

        asked.clear()
        assert client.get("/api/terms/museums", params={"q": "gitara"}).status_code == 200
        assert asked == {"met": "guitar", "mnw": "gitara", "paris": "guitare", "aic": "guitar"}

        asked.clear()
        client.get("/api/museums/mnw/search", params={"q": "gitara"})
        assert asked == {"mnw": "gitara"}
    assert len(fake.asked) == 1
