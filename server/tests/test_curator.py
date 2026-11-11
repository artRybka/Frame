"""Discover's periods from antiquity on, and the curator's cards in "Dziś
dla Ciebie" (Mateusz 2026-11-06)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic, _message, fake  # noqa: F401  (fixture)

from frame_server.ai import AiConfigUpdate
from frame_server.ai.curator import Curator, prompt
from frame_server.library import Item, ItemKind
from frame_server.library.museums import MetropolitanMuseum
from frame_server.library.repo import matches
from frame_server.library.themes import (
    ANTIQUITY,
    BY_KEY,
    CURATED_KEY,
    LATER,
    PERIODS,
    THEMES,
    WEEKLY_MIXES,
    curated,
    curated_due,
    for_you,
    occasion,
    search_page,
    theme,
)
from frame_server.library.verdict import Place, against

DAY = date(2026, 11, 9)


def _work(item_id: str, **fields: Any) -> Item:
    fields.setdefault("kind", ItemKind.ARTWORK)
    source, _, source_id = item_id.partition(":")
    return Item(id=item_id, source=source, source_id=source_id, **fields)


def test_periods_run_from_egypt_to_the_interwar_years() -> None:
    periods = [t for t in THEMES if t.group == PERIODS]
    assert [t.key for t in periods] == [
        "ancient-egypt",
        "fayum",
        "roman-frescoes",
        "byzantine-icons",
        "gold-ground",
        "15c",
        "16c",
        "17c",
        "18c",
        "early-19c",
        "late-19c",
        "belle-epoque",
        "interwar",
    ]
    assert {t.section for t in periods[:4]} == {ANTIQUITY}
    assert {t.section for t in periods[4:]} == {LATER}
    # Antiquity comes from the museums, kept only when it fits; pictures only.
    for found in periods[:4]:
        assert found.searches() and found.strict
        assert "technique:painting" in found.terms
    assert BY_KEY["antiquity-painted"].group == "Tematy"
    assert occasion(date(2027, 1, 7)).theme == "byzantine-icons"
    assert occasion(date(2027, 4, 21)).theme == "roman-frescoes"
    assert occasion(date(2026, 11, 4)).theme == "ancient-egypt"


def test_antiquity_cards_keep_paintings_and_leave_objects_out() -> None:
    tomb = _work(
        "met:548437",
        title="Menna and Family Hunting in the Marshes, Tomb of Menna",
        artist="Nina de Garis Davies",
        year=-1400,
        medium="Tempera on paper",
        classification="Facsimile, Menna (TT 69), marsh hunting",
        culture="Egyptian",
    )
    fresco = _work(
        "met:247009",
        title="Wall painting from Room H of the Villa of P. Fannius Synistor at Boscoreale",
        year=-50,
        medium="Fresco",
        classification="Miscellaneous-Stone",
        culture="Roman",
    )
    fayum = _work(
        "met:547860",
        title="Portrait of a young woman in red",
        year=90,
        medium="Encaustic on limewood with gold leaf",
        classification="Panel painting, young woman in red",
        culture="Egyptian",
    )
    mummy = _work(
        "met:547697",
        title="Mummy with an Inserted Panel Portrait of a Youth",
        year=80,
        medium="Mummified human body with linen; panel portrait: encaustic on limewood",
        classification="Mummy, youth, panel portrait, human remains",
        culture="Egyptian",
    )
    enamel = _work(
        "met:464548",
        title="Medallion with the Virgin from an Icon Frame",
        year=1100,
        medium="Gold, silver, and enamel worked in cloisonné",
        classification="Enamels-Cloisonné",
        culture="Byzantine",
    )
    icon = _work(
        "cma:1445",
        title="Icon of the New Testament Trinity",
        year=1445,
        medium="Tempera and gold on wood panel",
        classification="Painting",
        culture="Byzantium, Constantinople",
    )
    assert matches(tomb, BY_KEY["ancient-egypt"].rules())
    assert not against(fresco, Place.SOUGHT) and matches(fresco, BY_KEY["roman-frescoes"].rules())
    assert matches(fayum, BY_KEY["fayum"].rules())
    assert against(mummy, Place.SOUGHT)  # a whole mummy is no picture
    assert against(enamel, Place.SOUGHT) and not matches(enamel, BY_KEY["byzantine-icons"].rules())
    assert matches(icon, BY_KEY["byzantine-icons"].rules())

    class Importer:
        def search(self, source: str, query: str, limit: int, page: int) -> tuple[int, list[Item]]:
            return 3, [tomb, fresco, enamel]

    kept, total = search_page(Importer(), BY_KEY["ancient-egypt"], 1)  # type: ignore[arg-type]
    assert kept == [tomb] and total == 3


def test_the_met_names_the_culture_of_its_egyptian_works() -> None:
    record = {
        "objectID": 548437,
        "isPublicDomain": True,
        "primaryImageSmall": "https://images.metmuseum.org/x.jpg",
        "title": "Menna and Family Hunting in the Marshes",
        "objectBeginDate": -1400,
        "department": "Egyptian Art",
        "culture": "",
        "medium": "Tempera on paper",
    }
    with httpx.Client() as http:
        item = MetropolitanMuseum(http)._map(record)
    assert item is not None and item.culture == "Egyptian"


def _catalogue(service) -> None:
    library = service.library
    with library.batch():
        for n in range(14):
            library.upsert(
                _work(
                    f"cma:{n}",
                    title=f"Portrait of a lady {n}",
                    artist="Rembrandt" if n % 2 else "John Singer Sargent",
                    medium="Oil on canvas",
                    classification="Painting",
                    year=1650,
                    pooled=True,
                )
            )
        for n in range(14, 28):
            library.upsert(
                _work(
                    f"cma:{n}",
                    title=f"River at dawn {n}",
                    artist="Theodore Robinson",
                    styles=["Impressionism"],
                    medium="Oil on canvas",
                    classification="Painting",
                    year=1890,
                    pooled=True,
                )
            )


CARDS = {
    "cards": [
        {
            "name": "Twarze przez dwa tysiące lat",
            "description": "Rembrandt obok Sargenta.",
            "terms": ["subject:portrait"],
            "artists": ["Rembrandt", "Sargent"],
        },
        {
            "name": "Rzeźby Rodina",
            "description": "Brąz i marmur.",
            "terms": ["technique:sculpture", "subject:portrait"],
            "artists": [],
        },
        {
            "name": "Morze nocą",
            "description": "Za mało dzieł w katalogu.",
            "terms": ["subject:sea", "subject:night"],
            "artists": ["Whistler"],
        },
        {
            "name": "Malarze światła",
            "description": "Robinson, Rembrandt i Sargent.",
            "terms": [],
            "artists": ["Theodore Robinson", "Rembrandt", "Sargent"],
        },
        {
            "name": "Trzecia karta",
            "description": "Nie ma już na nią miejsca.",
            "terms": ["subject:portrait", "period:17c"],
            "artists": [],
        },
    ]
}


def _answer(fake_client: FakeAnthropic, data: dict[str, Any]) -> None:
    def results(batch_id: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(type="succeeded", message=_message(data)),
            )
            for r in fake_client.batches[batch_id]
        ]

    fake_client.messages.batches.results = results


def test_the_curator_orders_at_night_and_its_cards_pass_the_checks(
    service,
    fake,  # noqa: F811
    monkeypatch,
) -> None:
    _catalogue(service)
    library = service.library
    curator: Curator = service.curator
    assert curated_due(library, DAY) == 2

    assert curator.order(DAY)
    assert not curator.order(DAY)  # one order at a time
    sent = next(iter(fake.batches.values()))[0]["params"]
    text = sent["messages"][0]["content"][0]["text"]
    assert "subject:portrait" in text and "Rembrandt | 7" in text
    assert "technique:sculpture" not in text  # never the objects of their own group
    assert sent["model"].startswith("claude-opus")

    assert curator.collect() is False  # still running
    _answer(fake, CARDS)
    fake.ended = True
    assert curator.collect() is True
    shown = curated(library)
    assert [t.name for t in shown] == ["Twarze przez dwa tysiące lat", "Malarze światła"]
    faces = shown[0]
    assert faces.key == "curator-twarze-przez-dwa-tysiace-lat"
    assert set(faces.artists) == {"Rembrandt", "John Singer Sargent"}  # as the catalogue spells
    assert library.query(faces.rules())[0] == 14
    assert curated_due(library, DAY) == 0
    assert "order" not in library.get_state(CURATED_KEY)

    # In "Dziś dla Ciebie" in place of two of the week's pairs.
    weekly = for_you(library, DAY)
    assert [t.key for t in weekly].count(faces.key) == 1
    mixes = [t for t in weekly if t.key.startswith("week-mix-")]
    assert len(mixes) <= WEEKLY_MIXES - 2
    # Mateusz's order (2026-11-07): a curator's card, the artist of the
    # week, the other curator's card, then the pairs.
    kinds = [
        t.key.split("-")[0] + ("-" + t.key.split("-")[1] if t.key.startswith("week") else "")
        for t in weekly
    ]
    artist = kinds.count("week-artist")
    assert kinds[: 2 + artist] == ["curator", *["week-artist"] * artist, "curator"]
    assert theme(faces.key, library) == faces

    # Opened in the app: made again the next night; the other stays.
    from frame_server.web import create_app, discover_api

    discover_api._cards = (0.0, {})  # not another test's
    monkeypatch.setattr(discover_api, "CARD_MIN", 0)  # the epochs' cards, however empty
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        cards = {c["key"]: c for c in client.get("/api/themes").json()}
        assert cards[faces.key]["group"] == "Dziś dla Ciebie"
        epochs = [c for c in cards.values() if c["group"] == PERIODS]
        assert epochs[0]["section"] == ANTIQUITY and epochs[0]["section_years"]
        assert client.get(f"/api/themes/{faces.key}?page=1").status_code == 200
    assert curated_due(library, DAY) == 1
    assert curated_due(library, DAY + timedelta(days=7)) == 2  # a week on: both

    _answer(
        fake,
        {
            "cards": [
                CARDS["cards"][0],  # made before: not again
                {
                    "name": "Rembrandt i Sargent",
                    "description": "Dwa wieki portretu.",
                    "terms": ["subject:portrait"],
                    "artists": ["Rembrandt", "Sargent"],
                },
            ]
        },
    )
    fake.ended = False
    assert curator.order(DAY + timedelta(days=1))
    fake.ended = True
    assert curator.collect() is True
    assert [t.name for t in curated(library)] == ["Malarze światła", "Rembrandt i Sargent"]


def test_the_curator_asks_nothing_when_switched_off(service, fake) -> None:  # noqa: F811
    _catalogue(service)
    service.ai_config.update(AiConfigUpdate(curator=False))
    assert not service.curator.order(DAY)
    assert fake.batches == {}
    # Without the curator, "Dziś dla Ciebie" is as before.
    assert not [t for t in for_you(service.library, DAY) if t.key.startswith("curator-")]
    assert "Make 6 cards" in prompt(service.library, DAY, ["Rembrandt"], 2)


def test_antiquity_is_looked_for_first_while_its_cards_have_no_cover(service) -> None:
    from frame_server.library.themes import COVER_MIN, thin_searches

    searches = thin_searches(service.library)
    assert ("met", "Facsimile tomb") in searches and ("getty", "mummy portrait") in searches
    with service.library.batch():
        for n in range(COVER_MIN):
            service.library.upsert(
                _work(
                    f"met:{n}",
                    title=f"Facsimile painting {n}",
                    year=-1400,
                    medium="Tempera on paper",
                    classification="Facsimile",
                    culture="Egyptian",
                    pooled=True,
                )
            )
    assert ("met", "Facsimile tomb") not in thin_searches(service.library)


@pytest.mark.parametrize("key", ["ancient-egypt", "books-of-hours"])
def test_kept_close_sets_open_with_the_catalogue_and_keep_what_the_museums_found(
    service, monkeypatch, key
) -> None:
    import json

    from frame_server.library.themes import kept_close
    from frame_server.web import create_app, discover_api

    assert kept_close(BY_KEY.get(key) or theme(key, service.library))
    egypt = key == "ancient-egypt"
    with service.library.batch():
        for n in range(3):
            service.library.upsert(
                _work(
                    f"met:{n}",
                    title=f"Facsimile painting {n}" if egypt else f"Leaf from a Book of Hours {n}",
                    year=-1400 if egypt else 1450,
                    medium="Tempera on paper" if egypt else "Tempera and gold on parchment",
                    classification="Facsimile" if egypt else "Manuscripts and Illuminations",
                    culture="Egyptian" if egypt else "French",
                    pooled=True,
                )
            )
    found = _work(
        "met:900",
        title="Nakht and his wife, Tomb of Nakht",
        year=-1410,
        medium="Tempera on paper",
        classification="Facsimile",
        culture="Egyptian",
        thumb_url="https://images.metmuseum.org/900.jpg",
    )
    monkeypatch.setattr(service.importer, "search", lambda *a, **k: (1, [found]))
    monkeypatch.setattr(service.importer, "measure", lambda *a, **k: None)
    kept: list[Item] = []
    monkeypatch.setattr(service.player, "keep_searched", lambda items: kept.extend(items))
    discover_api._cards = (0.0, {})
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        reply = client.get(f"/api/themes/{key}/stream?page=1")
    lines = [json.loads(line) for line in reply.text.splitlines() if line]
    first = {i["item"]["id"] for i in lines[0]["items"]}
    assert first == {"met:0", "met:1", "met:2"}  # at once, from the catalogue
    assert lines[-1]["end"]
    if egypt:
        later = {i["item"]["id"] for line in lines[1:] for i in line.get("items") or []}
        assert "met:900" in later
        assert found in kept  # into the catalogue, for the cover and next time


def test_a_museum_page_asked_again_comes_from_memory(service, monkeypatch) -> None:
    from frame_server.library import importer as importer_module

    asked: list[str] = []
    work = _work("met:7", title="Fresco", medium="Fresco", year=-50)

    class Met:
        def search(self, query: str, limit: int = 24, page: int = 1) -> tuple[int, list[Item]]:
            asked.append(query)
            return 1, [work]

    monkeypatch.setattr(importer_module, "museum", lambda *a: Met())
    importer = service.importer
    assert importer.search("met", "Boscoreale wall painting") == (1, [work])
    assert importer.search("met", "Boscoreale wall painting") == (1, [work])
    assert asked == ["Boscoreale wall painting"]
    importer.search("met", "Boscoreale wall painting", page=2)
    assert len(asked) == 2


def test_antiquity_from_getty_yale_and_the_v_and_a_fits_its_cards() -> None:
    """Works dated in words, before Christ at Yale, and the V&A's types."""
    from frame_server.library.importer import dated

    getty = dated(
        _work(
            "getty:1",
            title="Fresco Fragment",
            date_text="1st century A.D.",
            classification="Painting",
            culture="Roman",
        )
    )
    assert getty.year == 1 and matches(getty, BY_KEY["roman-frescoes"].rules())
    dura = _work(
        "yale:2",
        title="Baptistery wall painting: Christ Walking on Water",
        year=232,
        medium="Paint on plaster",
        classification="Paintings",
        culture="Syrian, Dura-Europos",
    )
    assert matches(dura, BY_KEY["roman-frescoes"].rules())
    fayum = dated(
        _work(
            "vam:3",
            title="Fayum Mummy Portrait",
            date_text="4th century",
            classification="Mummy Portrait",
            culture="Egypt",
        )
    )
    assert not against(fayum, Place.SOUGHT) and matches(fayum, BY_KEY["fayum"].rules())
    icon = dated(
        _work(
            "vam:4",
            title="Icon of 'Saint Paraskeve'",
            date_text="16th century with later renovation",
            classification="Icon",
            culture="Greece",
        )
    )
    assert matches(icon, BY_KEY["byzantine-icons"].rules())
    late = dated(
        _work("vam:5", title="St Gerasimos", date_text="19th century", classification="Icon")
    )
    assert not matches(late, BY_KEY["byzantine-icons"].rules())


def test_yale_dates_before_christ_are_before_christ() -> None:
    from frame_server.library.yale import YaleMuseums

    def entry(label: str, value: str) -> dict[str, Any]:
        return {"label": {"en": [label]}, "value": {"none": [value]}}

    manifest = {
        "label": {"none": ["Wall painting fragment showing three offering bearers"]},
        "metadata": [
            entry("Date", "1401–1391 B.C."),
            entry("Classification", "Paintings"),
            entry("Copyright Statement", "Public Domain"),
        ],
        "items": [
            {
                "width": 3000,
                "height": 2000,
                "items": [
                    {
                        "items": [
                            {
                                "body": {
                                    "service": [
                                        {"id": "https://images.collections.yale.edu/iiif/2/x"}
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
        ],
    }
    with httpx.Client() as http:
        item = YaleMuseums(http)._map("yuag:1", manifest)
    assert item is not None and item.year == -1401
