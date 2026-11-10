"""Droga dzieła: a museum's provenance retold as stops on a road, with only
what the record says (Mateusz 2026-11-10, "S1")."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_ai import FakeAnthropic, fake  # noqa: F401  (fixture)

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU
from frame_server.ai.journey import (
    NONE_VERSION,
    VERSION,
    Journeys,
    Record,
    _told,
    _year,
    bridges,
    from_wikidata,
    read,
)
from frame_server.library import nga
from frame_server.library.models import Item, ItemKind, Note, SharperCopy
from frame_server.service import FrameService

AIC = {
    "data": {
        "provenance_text": (
            "By descent to Mme. Seurat, the artist’s mother (died 1899), Paris, 1891; by descent "
            "to Emile Seurat, the artist’s brother; sold for 800 francs to Casimir Brû, Paris, "
            "1900; sold for $20,000 to Frederic Clay and Helen Birch Bartlett, Chicago, 1924; "
            "given to the Art Institute, 1926."
        ),
        "exhibition_history": (
            "Paris, Maison Dorée, VIIIème Exposition de peinture, May 15–June 15, 1886, cat. 175."
            "\n\nBrussels, IVe exposition annuelle de XX, February, 1887, cat. 1."
        ),
    }
}

TEXT = AIC["data"]["provenance_text"] + "\n\n" + AIC["data"]["exhibition_history"]

ANSWER = {
    "headline": "Z pracowni w Paryżu do Chicago",
    "lead": "Czterdzieści lat drogi i jedna podróż przez ocean.",
    "from_where": "z Paryża",
    "stops": [
        {
            "year": "1886",
            "place": "Paryż",
            "lat": 48.86,
            "lon": 2.35,
            "kind": "shown",
            "owner": False,
            "detour": False,
            "text": "Pierwszy raz pokazany, **nr 175** w katalogu.",
        },
        {
            "year": "1887",
            "place": "Bruksela",
            "lat": 50.85,
            "lon": 4.35,
            "kind": "shown",
            "owner": False,
            "detour": True,
            "text": "Wystawa grupy **Les XX**.",
        },
        {
            "year": "1900",
            "place": "Paryż",
            "lat": 48.86,
            "lon": 2.35,
            "kind": "sold",
            "owner": True,
            "detour": False,
            "text": "Émile sprzedaje go Casimirowi Brû za **800 franków**.",
        },
        {
            "year": "1910",  # not in the record
            "place": "Londyn",
            "lat": 51.5,
            "lon": -0.12,
            "kind": "shown",
            "owner": False,
            "detour": True,
            "text": "Wystawa w Londynie.",
        },
        {
            "year": "1924",
            "place": "Chicago",
            "lat": 41.88,
            "lon": -87.62,
            "kind": "sold",
            "owner": True,
            "detour": False,
            "text": "Sprzedany za **20 000 dolarów** Bartlettom.",
        },
        {
            "year": "1926",
            "place": "Chicago",
            "lat": 41.88,
            "lon": -87.62,
            "kind": "gift",
            "owner": True,
            "detour": False,
            "text": "Dar dla **Art Institute**.",
        },
    ],
}


def _seurat() -> Item:
    return Item(
        id="aic:27992",
        source="aic",
        source_id="27992",
        kind=ItemKind.ARTWORK,
        title="A Sunday on La Grande Jatte — 1884",
        artist="Georges Seurat",
        date_text="1884–86",
    )


def _http(answers: dict[str, Any]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        for part, body in answers.items():
            if part in str(request.url):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={})

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_only_what_the_record_says_is_kept() -> None:
    record = Record(text=TEXT, exhibitions=2)
    journey = read(ANSWER, record, _seurat())
    assert journey is not None
    assert [s.year for s in journey.stops] == ["1886", "1887", "1900", "1924", "1926"]
    assert journey.years == 40 and journey.hands == 3 and journey.exhibitions == 2
    assert journey.km is not None and 6500 < journey.km < 6800  # Paryż → Chicago
    # A sum the record does not give is no stop either.
    wrong = {
        **ANSWER,
        "stops": [{**s, "text": s["text"].replace("800", "900")} for s in ANSWER["stops"]],
    }
    assert [s.year for s in read(wrong, record, _seurat()).stops] == [  # type: ignore[union-attr]
        "1886",
        "1887",
        "1924",
        "1926",
    ]
    assert read({"stops": ANSWER["stops"][:1]}, record, _seurat()) is None  # one stop: no road


def test_a_museums_record_ends_in_the_museum() -> None:
    record = Record(
        text=TEXT,
        source="Art Institute of Chicago",
    )
    journey = read(ANSWER, record, _seurat())
    assert journey is not None and journey.stops[-1].kind == "museum"


def test_the_journey_is_looked_up_once_and_kept(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    fake.answer = ANSWER
    journeys = Journeys(
        service.library,
        service.claude,
        service.ai_config,
        http=_http({"api.artic.edu": AIC}),
    )
    item = service.library.upsert(_seurat())
    found = journeys.look(item)
    assert found is not None and found.source == "Art Institute of Chicago"
    assert found.exhibitions == 2
    (asked,) = fake.asked
    assert asked["model"] == HAIKU and "800 francs" in str(asked["messages"])
    assert journeys.journey(item) == found and journeys.asked(item)
    assert not journeys.look_soon(item)  # kept: never asked again
    assert service.claude.spending.by_kind()["journey"] > 0


def test_no_record_is_kept_as_none_and_the_switch_asks_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    journeys = Journeys(
        service.library,
        service.claude,
        service.ai_config,
        http=_http({"api.artic.edu": {"data": {}}}),
    )
    item = service.library.upsert(_seurat())
    assert journeys.look(item) is None and journeys.asked(item)
    assert fake.asked == []
    other = service.library.upsert(_seurat().model_copy(update={"id": "aic:1", "source_id": "1"}))
    service.ai_config.update(AiConfigUpdate(journey=False))
    assert not journeys.look_soon(other)


def test_owners_and_exhibitions_from_wikidata() -> None:
    def claim(target: str, **when: str) -> dict[str, Any]:
        quals = {
            p: [{"datavalue": {"value": {"time": f"+{y}-00-00T00:00:00Z"}}}]
            for p, y in when.items()
        }
        return {
            "rank": "normal",
            "mainsnak": {"datavalue": {"value": {"id": target}}},
            "qualifiers": quals,
        }

    work = {
        "entities": {
            "Q1": {
                "claims": {
                    "P127": [claim("Q20", P580="1797"), claim("Q10", P580="1600", P582="1700")],
                    "P608": [claim("Q30", P585="1900")],
                }
            }
        }
    }
    labels = {
        "entities": {
            "Q10": {"labels": {"en": {"value": "King Charles"}}},
            "Q20": {"labels": {"en": {"value": "Louvre"}}},
            "Q30": {"labels": {"en": {"value": "Exposition Universelle"}}},
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=work if "claims" in str(request.url) else labels)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        record = from_wikidata(http, "Q1")
    assert record is not None and record.source == "Wikidata" and record.exhibitions == 1
    assert record.text.index("1600–1700: King Charles") < record.text.index("from 1797: Louvre")
    assert "1900: Exposition Universelle" in record.text


# -- more museums, and works from elsewhere that hang in them ----------------------------------

RIJKS = {
    "referred_to_by": [
        {
            "content": "Aankoop met steun van de Vereniging Rembrandt",
            "classified_as": [{"id": "http://vocab.getty.edu/aat/300026687"}],
        },
        {
            "content": (
                "<div><p>…; his sale, Amsterdam, 16 May 1696, no. 2, fl. 175, to Isaac Rooleeuw;"
                "{Hoet 1752, vol. 1, p. 34.} from whom, fl. 550,000, to the museum, 1908</p></div>"
            ),
            "classified_as": [{"id": "http://vocab.getty.edu/aat/300444174"}],
            "language": [{"id": "http://vocab.getty.edu/aat/300388277"}],
        },
    ]
}

LOUVRE = {
    "objectHistory": "Donné par l'artiste au baron Rivet, 1849 ;\r\n\r\nlégué au musée, 1925.",
    "previousOwner": [{"value": "Rivet, Charles", "note": "", "role": ""}],
    "acquisitionDetails": [
        {"mode": "legs", "dates": [{"type": "date du legs", "value": "1925", "startYear": 1925}]}
    ],
    "exhibition": [{"value": "Delacroix, New York (Etats-Unis), 17/09/2018 - 06/01/2019 "}],
}


def _journeys(service: FrameService, answers: dict[str, Any], **more: Any) -> Journeys:
    return Journeys(service.library, service.claude, service.ai_config, http=_http(answers), **more)


def _work(source: str, source_id: str, **more: Any) -> Item:
    return Item(
        id=f"{source}:{source_id}",
        source=source,
        source_id=source_id,
        kind=ItemKind.ARTWORK,
        title="A work",
        **more,
    )


def _nga_index(folder: Path, rows: list[tuple[int, str]]) -> None:
    path = folder / "nga" / "collection.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(nga.SCHEMA)
        db.execute(f"PRAGMA user_version = {nga.INDEX_VERSION}")
        db.executemany("INSERT INTO works (id, provenance) VALUES (?, ?)", rows)


def test_the_rijksmuseum_and_the_louvre_tell_the_way(service: FrameService) -> None:
    journeys = _journeys(service, {"id.rijksmuseum.nl/200108369": RIJKS, "cl010059724": LOUVRE})
    rijks = journeys.record(_work("rijks", "200108369"))
    assert rijks is not None and rijks.source == "Rijksmuseum"
    # Its English provenance, without the markup and the sources in braces.
    assert rijks.text == (
        "Provenance: …; his sale, Amsterdam, 16 May 1696, no. 2, fl. 175, to Isaac Rooleeuw; "
        "from whom, fl. 550,000, to the museum, 1908"
    )
    louvre = journeys.record(_work("louvre", "010059724"))
    assert louvre is not None and louvre.source == "Musée du Louvre" and louvre.exhibitions == 1
    assert "baron Rivet, 1849 ; légué au musée, 1925." in louvre.text
    assert "Former owners: Rivet, Charles" in louvre.text
    assert "Came to the Louvre: legs (date du legs: 1925)" in louvre.text
    assert "Delacroix, New York (Etats-Unis), 17/09/2018 - 06/01/2019" in louvre.text
    # A museum's record ends in the museum, whichever museum it is.
    assert (
        read(ANSWER, Record(text=TEXT, source="Musée du Louvre"), _seurat())
        .stops[  # type: ignore[union-attr]
            -1
        ]
        .kind
        == "museum"
    )


def test_the_national_gallery_tells_it_from_its_data_at_home(
    service: FrameService,
    tmp_path: Path,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journeys = _journeys(service, {}, data_dir=tmp_path)
    monkeypatch.setattr(nga.INDEX, "_start", lambda path: None)
    item = service.library.upsert(_work("nga", "46626"))
    # No index yet: nothing is kept, and the work is left alone for a while.
    assert journeys.look(item) is None and not journeys.asked(item)
    assert not journeys.look_soon(item)
    _nga_index(
        tmp_path,
        [
            (
                46626,
                "Sold 1909 to Carl Sternheim, Munich;[1] bequest 1963 to NGA.\n\n\n[1] For 3000.",
            ),
            (7, ""),
        ],
    )
    found = journeys.record(item)
    assert found is not None and found.source == "National Gallery of Art"
    assert found.text == (
        "Provenance: Sold 1909 to Carl Sternheim, Munich;[1] bequest 1963 to NGA."
        "\n\nNotes:\n[1] For 3000."
    )
    assert journeys.record(_work("nga", "7")) is None  # the gallery gives none


def test_a_work_from_elsewhere_gets_its_museums_record(service: FrameService) -> None:
    """Commons' Mona Lisa: the Louvre's record, by the ARK id on its
    Wikidata item; a work shown in the museum's own copy: that museum's."""
    claims = {
        "P9394": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "010059724"}}}],
        "P4610": [{"rank": "deprecated", "mainsnak": {"datavalue": {"value": "1"}}}],
        "P127": [],
    }
    assert bridges(claims) == [("louvre", "010059724")]
    answers = {
        "wbgetentities": {"entities": {"Q1": {"claims": claims}}},
        "cl010059724": LOUVRE,
        "api.artic.edu/api/v1/artworks/27992": AIC,
    }
    journeys = _journeys(service, answers, work_qid=lambda item: "Q1")
    found = journeys.record(_work("wmc", "123"))
    assert found is not None and found.source == "Musée du Louvre"
    # The Art Institute's own picture stands in for an archive's photograph.
    copy = SharperCopy(url="https://x/y.jpg", item_id="aic:27992", source="aic", width=9, height=9)
    found = journeys.record(_work("europeana", "/1/a", sharper=copy))
    assert found is not None and found.source == "Art Institute of Chicago"
    # No museum that tells: Wikidata's own owners, here too few.
    journeys = _journeys(service, answers, work_qid=lambda item: "")
    assert journeys.record(_work("wmc", "124")) is None


def test_a_none_from_before_is_looked_for_once_more(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    fake.answer = ANSWER
    journeys = _journeys(service, {"api.artic.edu": AIC})
    item = service.library.upsert(_seurat())
    service.library.save_note(
        Note(item_id=item.id, kind="journey", model="", prompt_version=VERSION, data={})
    )
    assert not journeys.asked(item)  # kept when fewer records were read
    assert journeys.look(item) is not None and journeys.asked(item)
    other = service.library.upsert(_work("met", "437658"))
    assert journeys.look(other) is None and journeys.asked(other)
    note = service.library.note(other.id, "journey")
    assert note is not None and note.prompt_version == NONE_VERSION and note.data == {}


def test_what_the_record_does_not_give_is_left_out_without_a_word() -> None:
    """Mateusz 2026-11-10 22:20, three stops "bez daty", each ending in
    "; zapis nie podaje daty.": „Powtórzenia w opisach braku daty są
    irytujące.”"""
    assert [_year(y) for y in ("bez daty", "Bez Daty", "b.d.", "undated", "?", "—", "")] == [""] * 7
    assert _year("ok. 1700") == "ok. 1700" and _year("przed 1891") == "przed 1891"
    assert (
        _told("Obraz należał do **Richarda, 4. markiza Hertford**; zapis nie podaje daty.")
        == "Obraz należał do **Richarda, 4. markiza Hertford**."
    )
    assert (
        _told("Obraz **Fragonarda** powstał w 1767 roku; zapis nie podaje miejsca jego powstania.")
        == "Obraz **Fragonarda** powstał w 1767 roku."
    )
    assert _told("Kupuje go **Brû** (źródło nie wymienia ceny).") == "Kupuje go **Brû**."
    assert _told("Kupuje go **Brû**, choć zapis nie podaje ceny; płaci gotówką.") == (
        "Kupuje go **Brû**; płaci gotówką."
    )
    plain = "Émile sprzedaje go Casimirowi Brû za **800 franków**."
    assert _told(plain) == plain
    answer = {
        **ANSWER,
        "stops": [
            {
                **ANSWER["stops"][0],
                "year": "bez daty",
                "text": "Pokazany w Paryżu; zapis nie podaje daty.",
            },
            *ANSWER["stops"][1:],
        ],
    }
    journey = read(answer, Record(text=TEXT), _seurat())
    assert journey is not None
    assert journey.stops[0].year == "" and journey.stops[0].text == "Pokazany w Paryżu."
