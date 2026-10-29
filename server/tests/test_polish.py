"""Polish titles and texts: nationalities, Wikidata, prompts, the job, the
frame and the app's card."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU, SONNET, cost
from frame_server.ai.pl_text import (
    KIND,
    MAX_BODY,
    NOTE_USAGE,
    TRANSLATION_USAGE,
    Context,
    PolishText,
    clean,
    model_for,
    request_text,
    schema,
    untranslated,
    written_for,
)
from frame_server.config import Settings
from frame_server.imaging.layout import Fit
from frame_server.library import Item, ItemKind
from frame_server.library.nationality import (
    artist_note,
    fix_note,
    life_years,
    note_years,
    noun,
)
from frame_server.library.wikidata import Facts, Wikidata, record_id
from frame_server.player import caption_for, text_block_for
from frame_server.service import FrameService
from frame_server.web import create_app

DESCRIPTION = (
    "In this late painting Turner shows a steamboat caught in a snowstorm, "
    "the sea and the sky dissolved into one swirl of light and spray."
)


def _item(**kw) -> Item:
    kw.setdefault("source", "met")
    kw.setdefault("source_id", "436535")
    return Item(id=f"{kw['source']}:{kw['source_id']}", **kw)


def test_nationality_is_a_person_in_the_authors_gender() -> None:
    assert noun("Dutch") == "Holender"
    assert noun("dutch", "female") == "Holenderka"
    assert noun("Martian") is None
    assert artist_note("Dutch, Zundert 1853–1890 Auvers-sur-Oise") == "Holender, 1853–1890"
    assert artist_note("British, 1775–1851") == "Brytyjczyk, 1775–1851"
    assert artist_note("American, 1844–1926", "female") == "Amerykanka, 1844–1926"
    assert artist_note("Italian, Arenella (Naples) 1615–1673 Rome") == "Włoch, 1615–1673"
    assert artist_note("American (born Germany), 1830–1902") == "Amerykanin, 1830–1902"
    assert artist_note("Netherlandish, ca. 1525–1569") == "Niderlandczyk, ok. 1525–1569"
    assert artist_note("French, born 1950") == "Francuz, ur. 1950"
    assert artist_note("Dutch, active 1650–1680", "female") == "Holenderka, czynna 1650–1680"
    assert artist_note("Japanese") == "Japończyk"
    assert artist_note("born Russia, 1866–1944") is None
    assert life_years("Dutch, Zundert 1853–1890 Auvers-sur-Oise") == "1853–1890"
    assert note_years("Holenderka, czynna 1650–1680") == "czynna 1650–1680"
    assert note_years("ok. 1525–1569") == "ok. 1525–1569"
    assert note_years("Japończyk") == ""


def test_a_models_adjective_becomes_a_noun() -> None:
    assert fix_note("holenderski, 1853–1890") == "Holender, 1853–1890"
    assert fix_note("japońska, 1760–1849", "female") == "Japonka, 1760–1849"
    assert fix_note("Brytyjczyk, 1775–1851") == "Brytyjczyk, 1775–1851"
    assert fix_note("") == ""


def test_record_ids_by_source() -> None:
    assert record_id(_item()) == ("P3634", "436535")
    cma = _item(source="cma", source_id="122351", url="https://clevelandart.org/art/1942.647")
    assert record_id(cma) == ("P11110", "1942.647")
    wikiart = _item(
        source="wikiart",
        source_id="5772",
        url="https://www.wikiart.org/en/vincent-van-gogh/the-starry-night-1889",
    )
    assert record_id(wikiart) == ("P6002", "vincent-van-gogh/the-starry-night-1889")
    assert record_id(_item(source="wmc", source_id="1")) is None


def _wikidata(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    if params.get("list") == "search":
        assert params["srsearch"] == "haswbstatement:P3634=436535"
        return httpx.Response(200, json={"query": {"search": [{"title": "Q1"}]}})
    ids = params["ids"].split("|")
    entities = {
        "Q1": {
            "labels": {"pl": {"value": "Pola pszenicy z cyprysami"}},
            "claims": {
                "P180": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q10"}}}},
                    {"mainsnak": {"datavalue": {"value": {"id": "Q11"}}}},
                ],
                "P170": [{"mainsnak": {"datavalue": {"value": {"id": "Q5582"}}}}],
            },
            "sitelinks": {"enwiki": {"title": "Wheat Field with Cypresses"}},
        },
        "Q10": {"labels": {"pl": {"value": "cyprys"}}},
        "Q11": {"labels": {"en": {"value": "wheat field"}}},
        "Q5582": {"claims": {"P21": [{"mainsnak": {"datavalue": {"value": {"id": "Q6581097"}}}}]}},
    }
    return httpx.Response(200, json={"entities": {i: entities[i] for i in ids}})


def test_wikidata_facts_and_cache() -> None:
    calls: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _wikidata(request)

    http = httpx.Client(transport=httpx.MockTransport(record))
    wd = Wikidata()
    facts = wd.facts(http, _item())
    assert facts == Facts(
        qid="Q1",
        title_pl="Pola pszenicy z cyprysami",
        depicts_pl=("cyprys",),
        depicts_en=("wheat field",),
        creator_gender="male",
        wiki_en="Wheat Field with Cypresses",
    )
    count = len(calls)
    assert wd.facts(http, _item()) == facts
    assert len(calls) == count


def test_wikidata_errors_are_not_remembered() -> None:
    fail = True

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429) if fail else _wikidata(request)

    http = httpx.Client(transport=httpx.MockTransport(answer))
    wd = Wikidata()
    assert wd.facts(http, _item()) is None
    fail = False
    assert wd.facts(http, _item()) is not None


def test_translation_or_note_by_description() -> None:
    described = _item(description=f"<p>{DESCRIPTION}</p>")
    bare = _item(description="Gift of a friend, 1929")
    assert written_for(described) == "translation"
    assert model_for(described) == HAIKU
    assert written_for(bare) == "note"
    assert model_for(bare) == SONNET
    assert "sources" in schema("note")["required"]
    assert "sources" not in schema("translation")["properties"]
    text = request_text(described, Context(facts=Facts(qid="Q1", depicts_pl=("statek",))))
    assert "Opis muzeum:\n" + DESCRIPTION in text
    assert "co przedstawia: statek" in text
    assert "Opis muzeum" not in request_text(bare, Context())


def test_clean_fixes_and_trims_answers() -> None:
    item = _item(
        title="Snow Storm",
        artist="Joseph Mallord William Turner",
        artist_bio="British, 1775–1851",
        date_text="1842",
        medium="Oil on canvas",
        description=DESCRIPTION,
    )
    long = " ".join(f"Zdanie numer {n} mówi coś o obrazie." for n in range(60))
    answer = {
        "title": "<i>Burza śnieżna</i>",
        "frame": long,
        "full": "Akapit pierwszy [...] dalej.\n\nAkapit drugi…",
        "medium": "olej na płótnie",
        "date": "1842",
        "artist_note": "brytyjski, 1775–1851",
        "sources": ["obraz"],
    }
    text = clean(answer, item, None)
    assert text is not None
    assert text.title == "Burza śnieżna"
    assert len(text.frame) <= MAX_BODY and text.frame.endswith("obrazie.")
    assert text.full == "Akapit pierwszy dalej.\n\nAkapit drugi"
    assert text.artist_note == "Brytyjczyk, 1775–1851"
    assert text.sources == []  # a translation names no sources
    assert PolishText.model_validate(text.model_dump()) == text

    wikidata = Facts(qid="Q1", title_pl="Śnieżyca", creator_gender="female")
    text = clean(answer, item, wikidata)
    assert text is not None
    assert text.title == "Śnieżyca"
    assert text.artist_note == "Brytyjka, 1775–1851"

    assert clean({**answer, "frame": ""}, item, None) is None


def test_an_english_copy_is_no_translation() -> None:
    english = (
        "This is the most famous cityscape of the Dutch Golden Age. The interplay of light "
        "and shade and the subtle reflections in the water make this painting a masterpiece."
    )
    polish = (
        "To najsłynniejszy pejzaż miejski holenderskiego złotego wieku. Gra światła i cienia "
        "oraz subtelne odbicia w wodzie czynią z tego obrazu arcydzieło, by tak rzec."
    )
    assert untranslated(english)
    assert not untranslated(polish)
    assert not untranslated("The Hague")  # a name is too short to tell

    item = _item(title="View of Delft", description=english)
    answer = {"title": "Widok Delftu", "frame": polish, "full": english}
    text = clean(answer, item, None)
    assert text is not None and text.full == polish  # the frame's Polish text instead
    assert clean({**answer, "frame": english}, item, None) is None


def test_note_keeps_only_known_sources_and_models_note() -> None:
    item = _item(title="Rosa", artist="Salvator Rosa", medium="Oil on canvas")
    answer = {
        "title": "Autoportret",
        "frame": "Malarz patrzy na widza.",
        "full": "",
        "medium": "olej na płótnie",
        "date": "1647",
        "artist_note": "włoski, 1615–1673",
        "sources": ["obraz", "plotki"],
    }
    text = clean(answer, item, None)
    assert text is not None
    assert text.written == "note"
    assert text.sources == ["obraz"]
    assert text.full == "Malarz patrzy na widza."
    assert text.artist_note == "Włoch, 1615–1673"
    assert text.date == ""  # the museum gives no date: none is made up


@pytest.fixture
def fake(service: FrameService) -> FakeAnthropic:
    """The service talks to a fake Anthropic, with a key and no Wikidata."""
    clients: dict[str, FakeAnthropic] = {}
    service.claude.factory = lambda key: clients.setdefault(key, FakeAnthropic(key))
    service.ai_config.set_key(GOOD_KEY)
    _offline(service)
    return clients.setdefault(GOOD_KEY, FakeAnthropic(GOOD_KEY))


PL_ANSWER = {
    "title": "Burza śnieżna",
    "frame": "Parowiec ginie w zamieci. Morze i niebo zlewają się w jeden wir.",
    "full": "Pełne tłumaczenie opisu.",
    "medium": "olej na płótnie",
    "date": "1842",
    "artist_note": "brytyjski, 1775–1851",
}


def _no_wikidata(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404)


def _add(service: FrameService, item_id: str, **kw: Any) -> Item:
    kw.setdefault("kind", ItemKind.ARTWORK)
    kw.setdefault("title", "Snow Storm")
    kw.setdefault("artist", "J. M. W. Turner")
    kw.setdefault("artist_bio", "British, 1775–1851")
    kw.setdefault("date_text", "1842")
    kw.setdefault("medium", "Oil on canvas")
    item = service.library.upsert(
        Item(id=item_id, source=item_id.split(":")[0], source_id=item_id.split(":")[1], **kw)
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg_bytes((90, 120, 200), (640, 480)))
    return item


def _offline(service: FrameService) -> None:
    service.pl_text._http = httpx.Client(transport=httpx.MockTransport(_no_wikidata))


def test_a_description_is_translated_by_haiku_without_the_picture(
    service: FrameService, fake: FakeAnthropic
) -> None:
    fake.answer = PL_ANSWER
    item = _add(service, "met:1", description=DESCRIPTION)
    note = service.ai.run_one(KIND, "met:1")

    assert note is not None and note.model == HAIKU
    params = fake.asked[0]
    assert params["model"] == HAIKU
    assert [c["type"] for c in params["messages"][0]["content"]] == ["text"]
    assert "Opis muzeum:" in params["messages"][0]["content"][0]["text"]
    text = service.pl_text.text(item)
    assert text is not None
    assert text.title == "Burza śnieżna"
    assert text.artist_note == "Brytyjczyk, 1775–1851"  # from the bio, not the model

    # Asked once: a fresh note is not asked again.
    assert service.ai.run_one(KIND, "met:1") is not None
    assert len(fake.asked) == 1
    # Switched off: nothing in Polish.
    service.ai_config.update(AiConfigUpdate(pl_text=False))
    assert service.pl_text.text(item) is None


def test_without_a_description_sonnet_writes_a_note_from_the_picture(
    service: FrameService, fake: FakeAnthropic
) -> None:
    fake.answer = {**PL_ANSWER, "sources": ["obraz", "dane muzeum"]}
    item = _add(service, "met:2", description="")
    service.ai.run_one(KIND, "met:2")

    params = fake.asked[0]
    assert params["model"] == SONNET
    content = params["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "text"]
    assert "sources" in params["output_config"]["format"]["schema"]["required"]
    text = service.pl_text.text(item)
    assert text is not None and text.written == "note"
    assert text.sources == ["obraz", "dane muzeum"]


def test_photos_get_no_polish_texts(service: FrameService, fake: FakeAnthropic) -> None:
    photo = _add(service, "icloud:1", kind=ItemKind.PHOTO)
    assert not service.pl_text.wanted(photo)
    assert service.ai.need_now("icloud:1", KIND).result(timeout=1) is None


def test_the_estimate_counts_translations_and_notes(
    service: FrameService, fake: FakeAnthropic
) -> None:
    _add(service, "met:1", description=DESCRIPTION)
    _add(service, "met:2")
    items, usd = service.ai.estimate(KIND)
    assert items == 2
    expected = cost(HAIKU, TRANSLATION_USAGE, True) + cost(SONNET, NOTE_USAGE, True)
    assert abs(usd - expected) < 1e-9


def test_the_frame_prints_the_polish_texts() -> None:
    item = Item(
        id="met:1",
        source="met",
        source_id="1",
        title="Snow Storm",
        artist="J. M. W. Turner",
        date_text="1842",
        medium="Oil on canvas",
        description=DESCRIPTION,
    )
    polish = PolishText(
        title="Burza śnieżna",
        frame="Parowiec ginie w zamieci.",
        full="",
        medium="olej na płótnie",
        date="1842",
        artist_note="Brytyjczyk, 1775–1851",
    )
    block = text_block_for(item, polish)
    assert block.title == "Burza śnieżna"
    assert block.meta == ["J. M. W. Turner", "1842 · olej na płótnie"]
    assert block.body == "Parowiec ginie w zamieci."
    assert caption_for(item, polish) == "J. M. W. Turner — Burza śnieżna, 1842"
    assert text_block_for(item).title == "Snow Storm"


def test_the_frame_shows_life_years_only_without_a_date() -> None:
    item = Item(
        id="met:2",
        source="met",
        source_id="2",
        title="A Lady",
        artist="Judith Leyster",
        artist_bio="Dutch, Haarlem 1609–1660 Heemstede",
        medium="Oil on wood",
    )
    polish = PolishText(
        title="Dama",
        frame="Kobieta w czepku.",
        full="",
        medium="olej na desce",
        artist_note="Holenderka, 1609–1660",
    )
    assert text_block_for(item, polish).meta == ["Judith Leyster", "1609–1660 · olej na desce"]
    assert text_block_for(item).meta == ["Judith Leyster", "1609–1660 · Oil on wood"]
    # The museum's estimate wins over the life years.
    dated = item.model_copy(update={"date_text": "ca. 1635"})
    estimate = polish.model_copy(update={"date": "ok. 1635"})
    assert text_block_for(dated, estimate).meta == ["Judith Leyster", "ok. 1635 · olej na desce"]
    assert text_block_for(dated).meta == ["Judith Leyster", "ca. 1635 · Oil on wood"]
    # No years anywhere: the medium alone.
    bare = item.model_copy(update={"artist_bio": "Dutch"})
    plain = polish.model_copy(update={"artist_note": "Holenderka"})
    assert text_block_for(bare, plain).meta == ["Judith Leyster", "olej na desce"]


def test_the_player_uses_polish_texts_once_written(
    service: FrameService, fake: FakeAnthropic
) -> None:
    fake.answer = PL_ANSWER
    item = _add(service, "met:1", description=DESCRIPTION)
    settings = service.player.settings
    settings.art.fit = Fit.DESCRIPTION
    assert service.player.render_settings(item, settings).text.title == "Snow Storm"
    service.ai.run_one(KIND, "met:1")
    assert service.player.render_settings(item, settings).text.title == "Burza śnieżna"


def test_texts_kept_with_an_english_copy_are_asked_again(
    service: FrameService, fake: FakeAnthropic
) -> None:
    item = _add(service, "met:1", description=DESCRIPTION)
    fake.answer = {**PL_ANSWER, "full": DESCRIPTION}
    service.ai.run_one(KIND, "met:1")
    text = service.pl_text.text(item)
    assert text is not None and text.full == PL_ANSWER["frame"]

    # Kept before clean() caught it: not shown, and asked once more.
    note = service.library.note("met:1", KIND)
    assert note is not None
    service.library.save_note(note.model_copy(update={"data": {**note.data, "full": DESCRIPTION}}))
    assert service.pl_text.text(item) is None
    fake.answer = PL_ANSWER
    service.ai.run_one(KIND, "met:1")
    text = service.pl_text.text(item)
    assert text is not None and text.full == "Pełne tłumaczenie opisu."
    assert len(fake.asked) == 2


def test_teraz_gets_polish_titles_and_texts(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    clients: dict[str, FakeAnthropic] = {}
    svc.claude.factory = lambda key: clients.setdefault(key, FakeAnthropic(key))
    _offline(svc)
    svc.ai_config.set_key(GOOD_KEY)
    clients.setdefault(GOOD_KEY, FakeAnthropic(GOOD_KEY)).answer = PL_ANSWER
    with TestClient(app) as client:
        _add(svc, "met:1", description=DESCRIPTION)
        _add(svc, "met:2", description=DESCRIPTION)
        svc.player.queue_next("met:1")
        svc.player.queue_next("met:2")
        svc.ai.run_one(KIND, "met:1")
        upcoming = {i["id"]: i for i in client.get("/api/player").json()["upcoming"]}
        assert upcoming["met:1"]["title_pl"] == "Burza śnieżna"
        assert upcoming["met:2"]["title_pl"] is None


def test_the_card_asks_for_polish_texts(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    clients: dict[str, FakeAnthropic] = {}
    svc.claude.factory = lambda key: clients.setdefault(key, FakeAnthropic(key))
    _offline(svc)
    with TestClient(app) as client:
        _add(svc, "met:1", description=DESCRIPTION)
        assert client.get("/api/library/items/met:1/polish").json() == {
            "status": "off",
            "text": None,
        }
        svc.ai_config.set_key(GOOD_KEY)
        clients.setdefault(GOOD_KEY, FakeAnthropic(GOOD_KEY)).answer = PL_ANSWER
        svc.ai.start()
        view = client.get("/api/library/items/met:1/polish?wait=10").json()
        assert view["status"] == "ready"
        assert view["text"]["title"] == "Burza śnieżna"
        assert client.get("/api/ai").json()["pl_text_progress"]["done"] == 1
