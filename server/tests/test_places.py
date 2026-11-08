"""Szukaj's "Muzeum": the places works are in, rather than the sources their
pictures come from (Mateusz 2026-11-08)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from frame_server.library import Item, ItemKind, PlaylistRules
from frame_server.library.museums import (
    PLACES_EUROPEANA,
    PLACES_WD,
    Access,
    Europeana,
    available,
    museum,
    reachable,
)
from frame_server.library.places import Places, known_places, learn_places, migrate_sources
from frame_server.library.search import MuseumSearch
from frame_server.library.wikidata_places import WikidataPlaces
from frame_server.museum_places import (
    ORIGINAL_NOTE,
    MuseumPlaces,
    commons_picture,
    reproduction,
)
from frame_server.schedule import FrameSettings

PRADO = "Q160112"
GHENT = "Q1810524"  # St Bavo's Cathedral
RIJKS = "Q190804"


def _item(source: str, n: int | str = 1, **kw: Any) -> Item:
    kw.setdefault("title", "The Milkmaid")
    kw.setdefault("artist", "Johannes Vermeer")
    return Item(id=f"{source}:{n}", source=source, source_id=str(n), **kw)


# -- places and their keys ----------------------------------------------------------


def test_a_museum_source_is_its_place() -> None:
    assert _item("rijks").held_at == RIJKS
    assert _item("rijks").held_by == "Rijksmuseum"
    # Yale's own works say which of its two museums.
    yale = _item("yale", museum="Yale Center for British Art")
    assert yale.held_at == "Q6352575"


def test_a_place_found_wins_over_the_source() -> None:
    known_places().learn(PRADO, "Muzeum Prado", "Madryt")
    copy = _item("wmc", place=PRADO)
    assert copy.held_at == PRADO
    assert copy.held_by == "Muzeum Prado"


def test_names_not_known_yet_are_keys_of_their_own() -> None:
    places = known_places()
    key = places.key_of("Musée Rodin")
    assert key.startswith("name:")
    # Once Wikidata names it, the old key means the item.
    places.learn("Q1340069", "Muzeum Rodina", "Paryż", aliases=["Musée Rodin"])
    assert places.canon(key) == "Q1340069"
    assert places.key_of("musee rodin") == "Q1340069"


def test_places_learnt_are_kept() -> None:
    places = Places()
    places.learn(PRADO, "Muzeum Prado", "Madryt", aliases=["Museo del Prado"])
    places.provides(PRADO, "Museo Nacional del Prado")
    places.pictured(PRADO, "Las Meninas.jpg")
    again = Places.from_state(json.loads(json.dumps(places.state())))
    assert again.name(PRADO) == "Muzeum Prado"
    assert again.place(PRADO).city == "Madryt"
    assert again.key_of("Museo del Prado") == PRADO
    assert again.provider(PRADO) == "Museo Nacional del Prado"
    assert again.picture(PRADO) == "Las Meninas.jpg"
    assert again.picture(GHENT) is None


def test_old_museum_choices_become_places() -> None:
    places, kept = migrate_sources(["rijks", "wmc", "yale", "paris", "photos"])
    assert places == [RIJKS, "Q6352575", "Q1568434"]
    assert kept == ["wmc", "paris", "photos"]
    rules = PlaylistRules(sources=["rijks", "europeana"], exclude_sources=["aic"])
    assert rules.places == [RIJKS]
    assert rules.sources == ["europeana"]
    assert rules.exclude_places == ["Q239303"]
    assert rules.exclude_sources == []


# -- what a search of places asks ------------------------------------------------------


def test_a_place_with_a_source_asks_it_and_others_wikidata() -> None:
    known_places().learn(PRADO, "Muzeum Prado", "Madryt")
    search = MuseumSearch.of(PlaylistRules(), places=[RIJKS, PRADO, GHENT])
    offered = ["rijks", "aic", "europeana"]
    # Commons turned off: still reachable for chosen places.
    keys = search.asked(offered, [*offered, "wmc"])
    assert keys == ["rijks", f"{PLACES_WD}{PRADO}|{GHENT}"]
    # Europeana is asked for those its data providers are known for.
    known_places().provides(PRADO, "Museo Nacional del Prado")
    keys = search.asked(offered, [*offered, "wmc"])
    assert keys[-1] == f"{PLACES_EUROPEANA}{PRADO}"


def test_works_of_places_left_out_dont_come() -> None:
    search = MuseumSearch.of(PlaylistRules(query="Vermeer"), skip_places=[RIJKS])
    assert not search.in_place(_item("rijks"))
    assert search.in_place(_item("aic"))
    # Every place of a source left out: the source is not asked.
    assert search.asked(["rijks", "aic"]) == ["aic"]


def test_sources_turned_off_are_not_offered() -> None:
    access = Access(private_use=True, sources_off=frozenset({"wmc", "openverse"}))
    assert "wmc" not in available(access)
    assert "openverse" not in available(access)
    assert "wmc" in reachable(access)
    # The works of a chosen museum still come through Wikidata and Commons.
    with httpx.Client() as http:
        assert isinstance(museum(f"{PLACES_WD}{PRADO}", http, access), WikidataPlaces)
        assert museum("wmc", http, access).key == "wmc"


def test_europeana_asks_its_data_providers() -> None:
    known_places().provides(PRADO, "Museo Nacional del Prado")
    with httpx.Client() as http:
        found = museum(f"{PLACES_EUROPEANA}{PRADO}", http, Access())
    assert isinstance(found, Europeana)
    assert found.providers == ("Museo Nacional del Prado",)


def test_settings_keep_the_sources_turned_off() -> None:
    settings = FrameSettings(sources_off=["wmc", "wikiart"])
    assert FrameSettings.model_validate(settings.model_dump()).sources_off == ["wmc", "wikiart"]


# -- Wikidata ------------------------------------------------------------------------


def _claims(**props: list[str]) -> dict[str, Any]:
    def value(v: str) -> Any:
        return {"id": v} if v[:1] == "Q" and v[1:].isdigit() else v

    return {
        "claims": {
            p: [{"mainsnak": {"datavalue": {"value": value(v)}}} for v in values]
            for p, values in props.items()
        }
    }


def _wikidata(handler_extra=None) -> httpx.MockTransport:
    """Wikidata knowing Las Meninas in the Prado, and Commons its file."""

    def handle(request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        if handler_extra and (answer := handler_extra(q)) is not None:
            return answer
        if request.url.host == "www.wikidata.org" and q.get("list") == "search":
            assert f"P195={PRADO}" in q["srsearch"] or "P170=" in q["srsearch"]
            return httpx.Response(
                200, json={"query": {"searchinfo": {"totalhits": 1}, "search": [{"title": "Q1"}]}}
            )
        if q.get("action") == "wbgetentities" and q.get("ids") == "Q1":
            entity = _claims(
                P18=["Las Meninas, by Diego Velázquez.jpg"], P195=[PRADO], P31=["Q3305213"]
            )
            return httpx.Response(200, json={"entities": {"Q1": entity}})
        if q.get("action") == "wbgetentities" and q.get("ids") == PRADO:
            labels = {"labels": {"pl": {"value": "Muzeum Prado"}}}
            return httpx.Response(200, json={"entities": {PRADO: labels}})
        if request.url.host == "commons.wikimedia.org":
            page = {
                "pageid": 77,
                "ns": 6,
                "title": "File:Las Meninas, by Diego Velázquez.jpg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/meninas.jpg",
                        "thumburl": "https://upload.wikimedia.org/meninas-640.jpg",
                        "width": 2000,
                        "height": 2300,
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Las_Meninas.jpg",
                        "extmetadata": {
                            "LicenseShortName": {"value": "Public domain"},
                            "Artist": {"value": "Diego Velázquez"},
                            "ObjectName": {"value": "Las Meninas"},
                            "DateTimeOriginal": {"value": "1656"},
                        },
                    }
                ],
            }
            return httpx.Response(200, json={"query": {"pages": {"77": page}}})
        return httpx.Response(404)

    return httpx.MockTransport(handle)


def test_wikidata_finds_the_works_of_a_place() -> None:
    known_places().learn(PRADO, "Muzeum Prado", "Madryt")
    with httpx.Client(transport=_wikidata()) as http:
        total, items = WikidataPlaces(http, places=(PRADO,)).search_kind("", "painting")
    assert total == 1
    [meninas] = items
    assert meninas.source == "wmc"
    assert meninas.place == PRADO
    assert meninas.held_by == "Muzeum Prado"


def test_a_place_picture_is_looked_for_once(service) -> None:
    asked: list[str] = []

    def count(q: dict[str, str]) -> None:
        asked.append(q.get("action", ""))
        return None

    places = MuseumPlaces(service.library, lambda: httpx.Client(transport=_wikidata(count)))
    assert places.picture(PRADO) == "Las Meninas, by Diego Velázquez.jpg"
    n = len(asked)
    assert places.picture(PRADO) == "Las Meninas, by Diego Velázquez.jpg"
    assert len(asked) == n
    assert commons_picture("Las Meninas.jpg", 720) == (
        "https://commons.wikimedia.org/wiki/Special:FilePath/Las_Meninas.jpg?width=720"
    )


# -- reproductions -------------------------------------------------------------------


def _lamb(**kw: Any) -> Item:
    kw.setdefault("artist", "Jan van Eyck")
    kw.setdefault("artist_bio", "ok. 1390–1441")
    kw.setdefault("medium", "Chromolithograph")
    return Item(
        id="wellcome:1",
        source="wellcome",
        source_id="1",
        kind=ItemKind.ARTWORK,
        title="The adoration of the mystic lamb",
        **kw,
    )


def test_a_chromolithograph_of_van_eyck_is_a_copy() -> None:
    assert reproduction(_lamb()) == "Chromolitografia"
    # A chromolithograph of an artist alive then is the work itself.
    assert reproduction(_lamb(artist="Jules Chéret", artist_bio="1836–1932")) == ""
    # A painting is never a copy.
    assert reproduction(_lamb(medium="Oil on panel")) == ""


def test_a_copy_is_put_where_the_original_is(service) -> None:
    library = service.library
    library.upsert(_lamb())

    def wikidata(q: dict[str, str]) -> httpx.Response | None:
        if q.get("action") == "wbsearchentities":
            hit = {"id": "Q5432", "description": "Flemish painter (c.1390-1441)"}
            return httpx.Response(200, json={"search": [hit]})
        if q.get("list") == "search":
            assert "P170=Q5432" in q["srsearch"] and "adoration" in q["srsearch"]
            return httpx.Response(200, json={"query": {"search": [{"title": "Q2"}]}})
        if q.get("ids") == "Q2":
            return httpx.Response(200, json={"entities": {"Q2": _claims(P195=[GHENT])}})
        if q.get("ids") == GHENT:
            labels = {"labels": {"pl": {"value": "Katedra św. Bawona"}}}
            return httpx.Response(200, json={"entities": {GHENT: labels}})
        return None

    places = MuseumPlaces(library, lambda: httpx.Client(transport=_wikidata(wikidata)))
    assert places.originals() == 1
    lamb = library.get("wellcome:1")
    assert lamb.place == GHENT
    assert lamb.reproduction == "Chromolitografia"
    assert lamb.held_at == GHENT
    assert lamb.held_by == "Katedra św. Bawona"
    assert library.notes(ORIGINAL_NOTE)["wellcome:1"].data == {"place": GHENT}
    # Asked once: not again the next night.
    assert places.originals() == 0


# -- the app's list ------------------------------------------------------------------


def test_the_list_has_the_catalogues_places_and_our_museums(service, monkeypatch) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    with TestClient(app) as client:
        library = app.state.service.library
        library.upsert(_item("rijks", 1))
        library.upsert(_item("rijks", 2, title="The Night Watch", artist="Rembrandt"))
        library.upsert(_item("aic", 3, title="Nighthawks", artist="Edward Hopper"))
        known_places().pictured(PRADO, "Las Meninas.jpg")
        known_places().learn(PRADO, "Muzeum Prado", "Madryt")
        monkeypatch.setattr(
            app.state.service.museum_places,
            "hits",
            lambda text, limit=7: [],
        )
        rows = client.get("/api/places").json()
        assert [r["key"] for r in rows[:2]] == [RIJKS, "Q239303"]
        assert rows[0]["item_id"] in ("rijks:1", "rijks:2")
        assert all(r["key"] for r in rows)
        found = client.get("/api/places", params={"q": "amster"}).json()
        assert [r["name"] for r in found] == ["Rijksmuseum"]
        # A museum with no work here yet shows Wikidata's picture.
        monkeypatch.setattr(
            app.state.service.museum_places, "picture", lambda key: "Las Meninas.jpg"
        )
        answer = client.get(f"/api/places/{PRADO}/picture").json()
        assert answer["picture"].endswith("Las_Meninas.jpg?width=720")


def test_learnt_places_survive_a_restart(service) -> None:
    known_places().learn(PRADO, "Muzeum Prado", "Madryt")
    service.library.save_places()
    learn_places(Places())
    from frame_server.library import Library

    Library(service.settings.data_dir / "library.db")
    assert known_places().name(PRADO) == "Muzeum Prado"
