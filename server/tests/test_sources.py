"""Europeana with the EU public-domain rule, Openverse, and WikiArt for tests."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from frame_server.library import Item
from frame_server.library.lifespan import LifeDates, free_in_eu
from frame_server.library.museums import (
    Access,
    Discovery,
    Europeana,
    Openverse,
    WikiArt,
    available,
    museum,
)

MATISSE = "http://data.europeana.eu/agent/60593"
WARHOL = "http://data.europeana.eu/agent/1"
MONDRIAN = "http://www.wikidata.org/entity/Q151803"


def _client(handler, sent: list[httpx.Request] | None = None) -> httpx.Client:
    def record(request: httpx.Request) -> httpx.Response:
        if sent is not None:
            sent.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(record))


def _life_answers(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "/entity/agent/60593" in url:
        return httpx.Response(200, json={"dateOfDeath": "1954-11-03"})
    if "/entity/agent/1." in url:
        return httpx.Response(200, json={"dateOfDeath": ["1987-02-22"]})
    if "/entity/search" in url:
        agents = [
            {"prefLabel": {"en": "Henri Matisse Jr."}, "dateOfDeath": ["2001-01-01"]},
            {"prefLabel": {"pl": "Henri Matisse"}, "dateOfDeath": ["1954-11-03"]},
        ]
        return httpx.Response(200, json={"items": agents})
    if "wikidata.org" in url:
        death = {"mainsnak": {"datavalue": {"value": {"time": "+1944-02-01T00:00:00Z"}}}}
        return httpx.Response(200, json={"entities": {"Q151803": {"claims": {"P570": [death]}}}})
    return httpx.Response(404, json={})


def test_eu_rule_counts_seventy_full_years() -> None:
    assert free_in_eu(1955, date(2026, 1, 1))
    assert not free_in_eu(1956, date(2026, 12, 31))
    assert free_in_eu(1956, date(2027, 1, 1))


def test_death_years_by_uri_and_exact_name_and_cached() -> None:
    sent: list[httpx.Request] = []
    life = LifeDates("key")
    with _client(_life_answers, sent) as http:
        assert life.death_year(http, MATISSE) == 1954
        assert life.death_year(http, MONDRIAN) == 1944
        assert life.death_year(http, "Matisse, Henri") == 1954  # not "Jr."
        assert life.death_year(http, "http://vocab.getty.edu/ulan/500017300") is None
        asked = len(sent)
        assert life.death_year(http, MATISSE) == 1954
    assert len(sent) == asked == 3


def _europeana_record(rights: str, creators: list[str], **extra) -> dict:
    return {
        "id": "/2048047/Clasate_e91c",
        "title": ["La blouse roumaine"],
        "dcCreator": creators,
        "rights": [rights],
        "edmIsShownBy": ["https://images.example/blouse.jpg"],
        "edmPreview": ["https://api.europeana.eu/thumbnail/v2/url.json?uri=x&type=IMAGE"],
        "year": ["1939"],
        "dataProvider": ["National Museum of Art of Romania"],
        "guid": ["https://www.europeana.eu/item/2048047/Clasate_e91c"],
        **extra,
    }


def _europeana(records: list[dict], sent: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if "record/v2/search.json" in str(request.url):
            return httpx.Response(200, json={"totalResults": len(records), "items": records})
        return _life_answers(request)

    return _client(handler, sent)


def test_europeana_takes_works_free_in_the_eu() -> None:
    in_copyright = "http://rightsstatements.org/vocab/InC/1.0/"
    records = [
        _europeana_record(in_copyright, [MATISSE, "Matisse, Henri"]),
        _europeana_record(in_copyright, [WARHOL, "Warhol, Andy"], id="/1/warhol"),
        _europeana_record("http://creativecommons.org/publicdomain/mark/1.0/", [], id="/1/pd"),
        _europeana_record("http://creativecommons.org/licenses/by-sa/4.0/", [], id="/1/bysa"),
    ]
    sent: list[httpx.Request] = []
    access = Access(life=LifeDates("key"), europeana_key="key")
    with _europeana(records, sent) as http:
        total, items = Europeana(http, access=access).search("Matisse")
    assert total == 4
    assert [i.id for i in items] == ["europeana:2048047~Clasate_e91c", "europeana:1~pd"]
    matisse = items[0]
    assert matisse.artist == "Henri Matisse" and matisse.year == 1939
    assert matisse.license == "Domena publiczna w UE (twórca zm. 1954)"
    assert matisse.thumb_url.endswith("&size=w400")
    assert items[1].license == "Public Domain Mark 1.0"
    params = sent[0].url.params
    assert params["wskey"] == "key" and params.get_list("qf") == [
        "TYPE:IMAGE",
        "contentTier:(2 OR 3 OR 4)",
    ]

    # Free licences only for private use; without death years only marked works.
    with _europeana(records, []) as http:
        licensed = Europeana(http, access=Access(private_use=True)).search("x")[1]
    assert [i.license for i in licensed] == ["Public Domain Mark 1.0", "CC BY-SA 4.0"]


def test_europeana_discovery_and_fetch() -> None:
    sent: list[httpx.Request] = []
    record = _europeana_record("http://creativecommons.org/publicdomain/zero/1.0/", [])
    with _europeana([record], sent) as http:
        source = Europeana(http)
        source.discover(Discovery(year_to=1955, kind="painting", style="cubism"))
        item = source.fetch("2048047~Clasate_e91c")
    assert item is not None and item.license == "CC0 1.0"
    discover, fetch = sent[0].url.params, sent[1].url.params
    assert discover["query"] == "cubism"
    assert discover.get_list("qf")[2:] == ["what:painting", "YEAR:[* TO 1955]"]
    assert fetch["query"] == 'europeana_id:"/2048047/Clasate_e91c"'


def _openverse_result(n: int, licence: str) -> dict:
    return {
        "id": f"uuid-{n}",
        "title": f"Composition {n}",
        "creator": "Ana Artist",
        "license": licence,
        "license_version": "4.0" if licence.startswith("by") else "1.0",
        "url": f"https://live.staticflickr.com/{n}.jpg",
        "thumbnail": f"https://api.openverse.org/v1/images/uuid-{n}/thumb/",
        "foreign_landing_url": f"https://www.flickr.com/photos/{n}",
        "attribution": f'"Composition {n}" by Ana Artist is licensed under CC. To view...',
        "category": "digitized_artwork",
        "tags": [{"name": "abstract", "accuracy": None}, {"name": "blue", "accuracy": 0.9}],
        "width": 3000,
        "height": 2000,
    }


def test_openverse_licences_follow_private_use() -> None:
    sent: list[httpx.Request] = []
    results = [_openverse_result(1, "cc0"), _openverse_result(2, "by-sa")]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result_count": 2, "results": results})

    with _client(handler, sent) as http:
        public = Openverse(http).search("abstract", limit=24)[1]
        licensed = Openverse(http, private_use=True).search("abstract")[1]
        assert Openverse(http).discover(Discovery(year_from=1960)) == (0, [])
    assert [i.license for i in public] == ["CC0 1.0"]
    assert [i.license for i in licensed] == ["CC0 1.0", "CC BY-SA 4.0"]
    item = licensed[1]
    assert item.credit == '"Composition 2" by Ana Artist is licensed under CC'
    assert item.subjects == ["abstract"] and item.id == "openverse:uuid-2"
    assert sent[0].url.params["license"] == "cc0,pdm"
    assert sent[0].url.params["page_size"] == "20"  # the anonymous maximum
    assert sent[0].url.params["category"] == "digitized_artwork,illustration"  # no photos
    assert "by-sa" in sent[1].url.params["license"]
    assert len(sent) == 2  # dates can't be filtered: not even asked


def test_wikiart_only_while_switched_on_and_pages_by_token() -> None:
    assert "wikiart" not in available(Access())
    assert "wikiart" in available(Access(wikiart=True))
    with pytest.raises(KeyError):
        museum("wikiart", httpx.Client())

    def painting(n: int) -> dict:
        return {
            "id": f"wa{n}",
            "title": f"No. {n}",
            "artistName": "Mark Rothko",
            "artistUrl": "mark-rothko",
            "url": f"no-{n}",
            "completitionYear": 1950 + n % 10,
            "image": f"https://uploads.wikiart.org/images/mark-rothko/no-{n}.jpg!Large.jpg",
        }

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("paginationToken")
        start = 60 if token == "second" else 0
        rows = [painting(n) for n in range(start, start + 60)]
        more = token is None
        return httpx.Response(
            200, json={"data": rows, "hasMore": more, "paginationToken": "second" if more else None}
        )

    WikiArt._tokens.clear()
    with _client(handler) as http:
        source = museum("wikiart", http, Access(wikiart=True))
        total, items = source.search("rothko", limit=24, page=3)  # works 48-71
    assert [i.source_id for i in items] == [f"wa{n}" for n in range(48, 72)]
    assert total == 120
    first = items[0]
    assert first.image_url == "https://uploads.wikiart.org/images/mark-rothko/no-48.jpg"
    assert first.license == "Tylko do testów ramki (WikiArt)"
    assert first.url == "https://www.wikiart.org/en/mark-rothko/no-48"


def test_wikiart_switch_lists_it_and_switching_off_removes_its_works(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        keys = [m["key"] for m in client.get("/api/museums").json()]
        assert "europeana" in keys and "openverse" in keys and "wikiart" not in keys

        settings = client.get("/api/settings").json()
        assert settings["wikiart"] is False
        settings["wikiart"] = True
        client.put("/api/settings", json=settings)
        assert "wikiart" in [m["key"] for m in client.get("/api/museums").json()]

        svc.library.upsert(Item(id="wikiart:wa1", source="wikiart", source_id="wa1"))
        svc.library.upsert(Item(id="aic:1", source="aic", source_id="1"))
        settings["wikiart"] = False
        client.put("/api/settings", json=settings)
        assert not svc.library.has("wikiart:wa1") and svc.library.has("aic:1")
        assert client.get("/api/museums/wikiart/search", params={"q": "x"}).status_code == 404
