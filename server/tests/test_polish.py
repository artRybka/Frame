"""Polish titles and texts: nationalities, Wikidata, prompts, the job, the
frame and the app's card."""

from __future__ import annotations

import itertools
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic, _message

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU, SONNET, cost
from frame_server.ai.pl_text import (
    KIND,
    MAX_BODY,
    NOTE_USAGE,
    STYLES,
    TRANSLATION_USAGE,
    Context,
    PolishText,
    clean,
    description,
    model_for,
    own_title_first,
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


def test_a_one_line_caption_gets_a_note() -> None:
    """A caption that names the work, its author and its date and nothing more
    (a Commons file's, here for a work in the NGA) is too little to translate:
    the work gets a note, with the caption as one more fact."""
    caption = (
        "Boy in a Red Waistcoat, oil painting by Paul Cézanne, 1888–1890; high-resolution scan."
    )
    longer = (
        "Garçon au gilet rouge. Oil on canvas, 1888–1890, by Paul Cézanne (French, 1839–1906). "
        "National Gallery of Art, Washington, Collection of Mr. and Mrs. Paul Mellon."
    )
    for text in (caption, longer):
        item = _item(
            title="Garçon au gilet rouge",
            artist="Paul Cézanne",
            artist_bio="French, 1839–1906",
            date_text="c. 1888–1890",
            medium="oil on canvas",
            description=text,
        )
        assert description(item) == "", text
        assert written_for(item) == "note"
        asked = request_text(item, Context())
        assert "Opis muzeum" not in asked
        assert f"Krótka adnotacja muzeum (za mało na opis): {text}" in asked

    # One short sentence about what the picture shows is still a description.
    said = (
        "A boy leans on a table with his head in his hand, his red waistcoat the one warm "
        "note among the blues and greys of the room."
    )
    item = _item(title="Garçon au gilet rouge", artist="Paul Cézanne", description=said)
    assert description(item) == said
    assert "Krótka adnotacja" not in request_text(item, Context())


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


def test_a_copy_in_any_language_is_no_translation() -> None:
    dutch = (
        "Een dienstmaagd staat achter een tafel en schenkt melk uit een melkkan in een "
        "kookpot. Op de tafel staat een mand met brood en een stenen kruik."
    )
    german = (
        "Die Malerei zeigt eine junge Frau, die in einem Zimmer steht und einen Brief liest. "
        "Das Licht fällt durch das Fenster auf ihr Gesicht."
    )
    french = (
        "Une jeune femme est assise dans un intérieur et lit une lettre près de la fenêtre "
        "ouverte, avec la lumière du jour sur son visage."
    )
    polish = (
        "Służąca stoi za stołem i nalewa mleko z dzbanka do garnka. Na stole leży kosz z "
        "chlebem, a obok stoi kamionkowy dzban; w głębi widać okno Pietera de Hoocha."
    )
    for text in (dutch, german, french):
        assert untranslated(text), text
    assert not untranslated(polish)

    item = _item(title="Het melkmeisje", description=dutch)
    answer = {"title": "Mleczarka", "frame": polish, "full": dutch}
    text = clean(answer, item, None)
    assert text is not None and text.full == polish


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
    # The label on the frame goes without the date (Mateusz 2026-11-08).
    assert caption_for(item, polish, dated=False) == "J. M. W. Turner — Burza śnieżna"
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


def test_polish_titles_lose_the_artists_name(service: FrameService, fake: FakeAnthropic) -> None:
    # A model keeps the name a Commons file name put in front of the title.
    item = _item(
        title="Tadeusz Makowski Skapiec", artist="Tadeusz Makowski", description=DESCRIPTION
    )
    text = clean({**PL_ANSWER, "title": "Tadeusz Makowski Skąpiec"}, item, None)
    assert text is not None and text.title == "Skąpiec"

    # Texts written by older versions are shown without it too.
    fake.answer = {**PL_ANSWER, "title": "Tadeusz Makowski Skąpiec"}
    item = _add(service, "met:1", artist="Tadeusz Makowski", description=DESCRIPTION)
    service.ai.run_one(KIND, "met:1")
    note = service.library.note("met:1", KIND)
    assert note is not None
    data = {**note.data, "title": "Tadeusz Makowski Skąpiec"}
    service.library.save_note(note.model_copy(update={"data": data}))
    text = service.pl_text.text(item)
    assert text is not None and text.title == "Skąpiec"


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
            "title": None,
        }
        svc.ai_config.set_key(GOOD_KEY)
        clients.setdefault(GOOD_KEY, FakeAnthropic(GOOD_KEY)).answer = PL_ANSWER
        svc.ai.start()
        view = client.get("/api/library/items/met:1/polish?wait=10").json()
        assert view["status"] == "ready"
        assert view["text"]["title"] == "Burza śnieżna"
        assert client.get("/api/ai").json()["pl_text_progress"]["done"] == 1


def test_the_title_is_picked_out_of_the_answer_as_it_is_written(
    service: FrameService, fake: FakeAnthropic
) -> None:
    item = _add(service, "met:1", description=DESCRIPTION)
    job = service.pl_text
    job.params(item)
    for piece in ['{"tit', 'le": "Burza ', 'śnieżna \\"', 'nad morzem\\""']:
        assert job.early_title("met:1") is None
        job.partial(item, piece)
    assert job.early_title("met:1") == 'Burza śnieżna "nad morzem"'
    job.partial(item, ', "frame": "Parowiec')  # the rest changes nothing
    assert job.early_title("met:1") == 'Burza śnieżna "nad morzem"'


def test_the_card_gets_the_title_before_the_texts(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    clients: dict[str, FakeAnthropic] = {}
    svc.claude.factory = lambda key: clients.setdefault(key, FakeAnthropic(key))
    _offline(svc)
    svc.ai_config.set_key(GOOD_KEY)
    fake = clients.setdefault(GOOD_KEY, FakeAnthropic(GOOD_KEY))
    fake.answer = PL_ANSWER
    fake.held = threading.Event()
    fake.held_after = 5  # '{"title": "Burza śnieżna", ...' is whole by then
    url = "/api/library/items/met:1/polish"
    with TestClient(app) as client:
        _add(svc, "met:1", description=DESCRIPTION)
        svc.ai.start()
        try:
            started = time.monotonic()
            view = client.get(f"{url}?wait=10&early=true").json()
            assert time.monotonic() - started < 5
            assert view == {"status": "waiting", "text": None, "title": "Burza śnieżna"}
            # Without "early" the wait is for the texts, as before.
            fake.held.set()
            view = client.get(f"{url}?wait=10").json()
            assert view["status"] == "ready"
            assert view["text"]["title"] == "Burza śnieżna"
            assert view["title"] is None
        finally:
            fake.held.set()
            svc.ai.stop()


def _works(request: httpx.Request, seen: list[httpx.Request]) -> httpx.Response:
    """Wikidata with works Q1 ("met:1"), Q2 ("met:2") and none for "met:3"."""
    seen.append(request)
    params = request.url.params
    if params.get("list") == "search":
        value = params["srsearch"].rsplit("=", 1)[1]
        hits = {"1": "Q1", "2": "Q2"}
        found = [{"title": hits[value]}] if value in hits else []
        return httpx.Response(200, json={"query": {"search": found}})
    labels = {"Q1": "Słoneczniki", "Q2": "Gwiaździsta noc"}
    return httpx.Response(
        200,
        json={
            "entities": {
                i: {"labels": {"pl": {"value": labels[i]}}, "claims": {}}
                for i in params["ids"].split("|")
            }
        },
    )


def test_wikidata_reads_the_works_found_together() -> None:
    seen: list[httpx.Request] = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: _works(r, seen)))
    wd = Wikidata()
    items = [_item(source_id=n) for n in ("1", "2", "3")]
    facts = wd.facts_of(http, items)
    assert {k: f and f.title_pl for k, f in facts.items()} == {
        "met:1": "Słoneczniki",
        "met:2": "Gwiaździsta noc",
        "met:3": None,
    }
    reads = [r for r in seen if r.url.params.get("action") == "wbgetentities"]
    assert [r.url.params["ids"] for r in reads] == ["Q1|Q2"]
    count = len(seen)
    assert wd.facts_of(http, items) == facts  # all remembered, "met:3" too
    assert len(seen) == count
    assert wd.known(items[0]) == facts["met:1"]


def test_an_error_wikidata_gives_with_a_200_is_not_nothing() -> None:
    lagging = True

    def answer(request: httpx.Request) -> httpx.Response:
        if lagging:
            return httpx.Response(200, json={"error": {"code": "maxlag", "info": "lagged"}})
        return _wikidata(request)

    http = httpx.Client(transport=httpx.MockTransport(answer))
    wd = Wikidata()
    assert wd.facts(http, _item()) is None
    assert wd.cached(_item()) == (False, None)
    lagging = False
    assert wd.facts(http, _item()) is not None


def test_works_of_other_museums_are_found_by_their_numbers() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "search":
            assert params["srsearch"] == "haswbstatement:P217=KMS1"
            return httpx.Response(200, json={"query": {"search": [{"title": "Q7"}]}})
        number = {
            "mainsnak": {"datavalue": {"value": "KMS1"}},
            "qualifiers": {"P195": [{"datavalue": {"value": {"id": "Q671384"}}}]},
        }
        return httpx.Response(
            200,
            json={
                "entities": {
                    "Q7": {"labels": {"pl": {"value": "Kobieta"}}, "claims": {"P217": [number]}},
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(answer))
    wd = Wikidata()
    smk = wd.facts(http, _item(source="smk", source_id="KMS1"))
    assert smk is not None and smk.title_pl == "Kobieta"
    assert wd.facts(http, _item(source="wmc", source_id="123")) is None  # not asked
    # Another museum's number of the same kind: not this work.
    other = Wikidata()
    number_elsewhere = httpx.MockTransport(
        lambda r: (
            httpx.Response(200, json={"query": {"search": [{"title": "Q7"}]}})
            if r.url.params.get("list") == "search"
            else httpx.Response(200, json={"entities": {"Q7": {"labels": {"pl": {"value": "X"}}}}})
        )
    )
    smk = _item(source="smk", source_id="KMS1")
    assert other.facts(httpx.Client(transport=number_elsewhere), smk) is None


def test_the_texts_title_is_wikidatas_also_when_it_came_later(
    service: FrameService, fake: FakeAnthropic
) -> None:
    fake.answer = PL_ANSWER
    _add(service, "met:1", description=DESCRIPTION)
    service.ai.run_one(KIND, "met:1")
    item = service.library.get("met:1")
    assert item is not None
    assert service.pl_text.text(item).title == "Burza śnieżna"  # type: ignore[union-attr]
    service.pl_text.wikidata._keep(item, Facts(qid="Q1", title_pl="Śnieżyca"))
    assert service.pl_text.text(item).title == "Śnieżyca"  # type: ignore[union-attr]


def test_polish_museums_keep_their_own_titles() -> None:
    facts = Facts(qid="Q1", title_pl="Bitwa", creator_gender="male")
    mnw = _item(source="mnw", source_id="1", title="Bitwa pod Grunwaldem")
    assert own_title_first(mnw, facts) == Facts(qid="Q1", creator_gender="male")
    assert own_title_first(_item(), facts) is facts


def _answers(fake: FakeAnthropic, *answers: dict[str, Any]) -> None:
    """The fake answers these in turn (streamed or not), the last one after."""
    left = list(answers)

    def create(**params: Any) -> Any:
        fake.asked.append(params)
        return _message(left.pop(0) if len(left) > 1 else left[0])

    fake._create = create  # type: ignore[method-assign]
    fake.messages.create = create


NOTE_ANSWER = {**PL_ANSWER, "sources": ["obraz"]}


def _style(params: dict[str, Any]) -> str:
    return str(params["output_config"]["format"]["schema"]["properties"]["style"]["enum"][0])


def test_notes_take_the_five_styles_in_turn(service: FrameService, fake: FakeAnthropic) -> None:
    job = service.pl_text
    item = _add(service, "met:2", description="")
    dealt = [_style(job.params(item)) for _ in range(10)]
    assert set(dealt[:5]) == set(STYLES) and set(dealt[5:]) == set(STYLES)
    assert all(a != b for a, b in itertools.pairwise(dealt))  # never twice in a row
    params = job.params(item)
    question = params["messages"][0]["content"][1]["text"]
    name, _ = STYLES[_style(params)]
    assert f"STYL: {name}." in question
    assert "OSTATNIE POCZĄTKI" not in question  # no notes yet


def test_a_note_keeps_its_style_and_the_next_one_hears_how_it_opened(
    service: FrameService, fake: FakeAnthropic
) -> None:
    opening = "Ciężkie chmury nad portem zasłaniają niemal całe niebo nad statkiem."
    _answers(fake, {**NOTE_ANSWER, "full": opening, "style": "temat"})
    item = _add(service, "met:2", description="")
    service.ai.run_one(KIND, "met:2")
    text = service.pl_text.text(item)
    assert text is not None and text.written == "note" and text.style == "temat"

    service.pl_text._recent = (0.0, [])  # read again
    other = _add(service, "met:3", description="")
    question = service.pl_text.params(other)["messages"][0]["content"][1]["text"]
    assert "OSTATNIE POCZĄTKI" in question
    assert "„Ciężkie chmury nad portem zasłaniają niemal całe…”" in question


def test_a_museum_text_not_about_the_work_gets_a_note_at_once(
    service: FrameService, fake: FakeAnthropic
) -> None:
    """Haiku finds only the artist's life in the museum's text: Sonnet writes
    a note, told the text is not about the work."""
    _answers(fake, {**PL_ANSWER, "about_work": False}, {**NOTE_ANSWER, "style": "opis"})
    item = _add(service, "met:1", description=DESCRIPTION)
    service.ai.run_one(KIND, "met:1")

    assert [p["model"] for p in fake.asked] == [HAIKU, SONNET]
    assert "about_work" in fake.asked[0]["output_config"]["format"]["schema"]["required"]
    question = fake.asked[1]["messages"][0]["content"][1]["text"]
    assert "Tekst muzeum (ogólny, nie o tym dziele" in question
    assert "Opis muzeum:" not in question
    text = service.pl_text.text(item)
    assert text is not None and text.written == "note" and text.general
    # Kept: asked again, it stays a note (and is fresh).
    assert service.pl_text.written(item) == "note"
    assert service.ai.run_one(KIND, "met:1") is not None
    assert len(fake.asked) == 2


def test_a_nights_translation_not_about_the_work_asks_for_a_note_next(
    service: FrameService, fake: FakeAnthropic
) -> None:
    """A batch's answer is kept without a second question: the work waits for
    the next night's note, its texts not shown meanwhile."""
    from frame_server.library.models import Note

    item = _add(service, "met:1", description=DESCRIPTION)
    job = service.pl_text
    note = service.library.save_note(
        Note(
            item_id=item.id,
            kind=KIND,
            model=HAIKU,
            prompt_version=job.prompt_version,
            source_hash=job.source_hash(item),
            data={**PL_ANSWER, "about_work": False},
        )
    )
    job.apply(item, note)
    kept = service.library.note(item.id, KIND)
    assert kept is not None and kept.data == {"general": True}
    assert not job.fresh(item, kept)
    assert job.text(item) is None
    assert job.written(item) == "note"
    assert job.params(item)["model"] == SONNET
    # The museum's text changed: it is read as a description again.
    changed = service.library.upsert(
        item.model_copy(update={"description": DESCRIPTION + " More."})
    )
    assert job.written(changed) == "translation"


def test_a_translation_about_the_work_stays_one(service: FrameService, fake: FakeAnthropic) -> None:
    _answers(fake, {**PL_ANSWER, "about_work": True})
    item = _add(service, "met:1", description=DESCRIPTION)
    service.ai.run_one(KIND, "met:1")
    assert [p["model"] for p in fake.asked] == [HAIKU]
    text = service.pl_text.text(item)
    assert text is not None and text.written == "translation" and not text.general
