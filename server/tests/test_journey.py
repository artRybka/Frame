"""Droga dzieła: a museum's provenance retold as stops on a road, with only
what the record says (Mateusz 2026-11-10, "S1")."""

from __future__ import annotations

from typing import Any

import httpx
from test_ai import FakeAnthropic, fake  # noqa: F401  (fixture)

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU
from frame_server.ai.journey import Journeys, Record, from_wikidata, read
from frame_server.library.models import Item, ItemKind
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
