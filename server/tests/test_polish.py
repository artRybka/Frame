from __future__ import annotations

import httpx

from frame_server.library import Item
from frame_server.library.nationality import artist_note, fix_note, noun
from frame_server.library.polish import (
    MAX_BODY,
    NOTE_MODEL,
    TRANSLATE_MODEL,
    Context,
    PolishText,
    clean,
    model_for,
    request_text,
    schema,
    written_for,
)
from frame_server.library.wikidata import Facts, Wikidata, record_id

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
    assert model_for(described) == TRANSLATE_MODEL
    assert written_for(bare) == "note"
    assert model_for(bare) == NOTE_MODEL
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
    text = clean(answer, item, Context())
    assert text is not None
    assert text.title == "Burza śnieżna"
    assert len(text.frame) <= MAX_BODY and text.frame.endswith("obrazie.")
    assert text.full == "Akapit pierwszy dalej.\n\nAkapit drugi"
    assert text.artist_note == "Brytyjczyk, 1775–1851"
    assert text.sources == []  # a translation names no sources
    assert PolishText.from_json(text.to_json()) == text

    wikidata = Context(facts=Facts(qid="Q1", title_pl="Śnieżyca", creator_gender="female"))
    text = clean(answer, item, wikidata)
    assert text is not None
    assert text.title == "Śnieżyca"
    assert text.artist_note == "Brytyjka, 1775–1851"

    assert clean({**answer, "frame": ""}, item, Context()) is None


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
    text = clean(answer, item, Context())
    assert text is not None
    assert text.written == "note"
    assert text.sources == ["obraz"]
    assert text.full == "Malarz patrzy na widza."
    assert text.artist_note == "Włoch, 1615–1673"
    assert text.date == ""  # the museum gives no date: none is made up
