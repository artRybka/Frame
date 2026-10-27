"""Copies of one work from several sources."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from frame_server.library import (
    Item,
    ItemKind,
    Job,
    Library,
    Playlist,
    PlaylistKind,
    PlaylistRules,
)
from frame_server.library.duplicates import (
    Shown,
    Works,
    dedupe,
    origin,
    same_work,
    title_key,
    work_key,
)
from frame_server.library.museums import MUSEUMS, Museum
from frame_server.web.library_api import remote_items


def _work(source: str, n: int | str, **kw) -> Item:
    kw.setdefault("title", "Wheat Field with Cypresses")
    kw.setdefault("artist", "Vincent van Gogh")
    return Item(id=f"{source}:{n}", source=source, source_id=str(n), **kw)


def test_title_key_drops_what_sources_add() -> None:
    assert title_key("The Water Lilies") == "water lilies"
    assert (
        title_key("Claude Monet - The Water Lilies (1906) - Google Art Project", "Claude Monet")
        == "water lilies"
    )
    assert title_key("Les Nymphéas, 1906", "Monet") == "nympheas"
    assert title_key("Vincent van Gogh") == "vincent gogh"  # nothing else to go by
    # Commons file names: the artist as Commons calls him, where the work
    # hangs, which scan.
    vermeer = "Johannes Vermeer"
    for name in (
        "Jan Vermeer van Delft - The Glass of Wine - Google Art Project",
        "Johannes Vermeer, The Glass of Wine, The Metropolitan Museum of Art",
        "Johannes Vermeer - The Glass of Wine - WGA24652",
        "Johannes Vermeer - The Glass of Wine - 406 - Mauritshuis",
    ):
        assert title_key(name, vermeer) == "glass wine", name
    # Commas within a title stay.
    assert title_key("Officer and Laughing Girl, after Vermeer", "Jacquemart") == (
        "officer laughing girl after vermeer"
    )


def test_same_work_across_sources() -> None:
    met = _work("met", 436535, year=1889, width=1000, height=794)
    commons = _work(
        "wmc",
        1,
        title="Vincent van Gogh - Wheat Field with Cypresses - Google Art Project",
        artist="Vincent van Gogh  (1853–1890)  Dutch painter",
        year=1889,
        width=4000,
        height=3200,
    )
    openverse = _work("openverse", "x", artist="Gogh, Vincent van")
    assert same_work(met, commons) and same_work(met, openverse) and same_work(commons, openverse)
    assert work_key(met) == work_key(commons) == work_key(openverse) == "gogh|wheat field cypresses"

    # One source's works are never copies of each other.
    assert not same_work(met, _work("met", 2, year=1889))
    # Another year, another painting of the same name.
    assert not same_work(met, _work("aic", 3, year=1885))
    # Another shape, another painting.
    assert not same_work(met, _work("aic", 4, year=1889, width=800, height=1000))
    # Another artist.
    assert not same_work(met, _work("aic", 5, artist="Paul Cézanne"))
    # Titles shared by many works match only with a year.
    portrait = _work("met", 6, title="Self-Portrait")
    assert not same_work(portrait, _work("wmc", 7, title="Self Portrait"))
    assert same_work(
        portrait.model_copy(update={"year": 1887}),
        _work("wmc", 7, title="Self Portrait", year=1887),
    )
    # The same page or picture, whatever the titles say.
    assert same_work(
        _work("met", 8, url="https://www.metmuseum.org/art/collection/search/8"),
        _work(
            "openverse", 9, title="Wheatfield", url="http://metmuseum.org/art/collection/search/8/"
        ),
    )
    # Own works and photos are what they are.
    upload = _work("upload", 10, kind=ItemKind.OWN)
    assert not same_work(upload, _work("met", 10)) and work_key(upload) == ""


def test_dedupe_keeps_the_museums_copy_where_the_first_copy_was() -> None:
    found = [
        _work("openverse", 1),
        _work("aic", 2, title="The Bedroom", year=1889),
        _work("met", 3),
        _work("wmc", 4, title="The Bedroom", year=1889),
        _work("europeana", 5, title="Starry Night"),
    ]
    assert [i.id for i in dedupe(found)] == ["met:3", "aic:2", "europeana:5"]


def test_works_keep_one_copy_per_source() -> None:
    """A copy without a year fits the first of two paintings with one name,
    not both."""
    works = Works(
        [
            _work("aic", 1, title="Water Lilies", artist="Claude Monet", year=1906),
            _work("aic", 2, title="Water Lilies", artist="Claude Monet", year=1916),
            _work("wmc", 3, title="Water Lilies", artist="Claude Monet"),
        ]
    )
    assert sorted(len(g) for g in works.groups) == [1, 2]


def test_library_hides_copies_the_server_added(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_work("openverse", 1, pooled=True))
    lib.upsert(_work("met", 2, pooled=True))
    lib.upsert(_work("wmc", 3, title="The Bedroom", pooled=True))
    lib.upsert(_work("europeana", 4, title="The Bedroom"))  # kept by the owner
    lib.upsert(_work("aic", 5, title="The Bedroom", pooled=True))
    assert lib.spare_copies() == {"openverse:1", "wmc:3", "aic:5"}
    assert {i.id for i in lib.query()[1]} == {"met:2", "europeana:4"}
    # Asked by source, a source's copies are there.
    assert [i.id for i in lib.query(PlaylistRules(sources=["openverse"]))[1]] == ["openverse:1"]

    assert lib.twin(_work("rijks", 6)) == lib.get("met:2")
    assert lib.twin(lib.get("met:2")) is None  # type: ignore[arg-type]
    assert lib.twin(_work("rijks", 7, title="Irises")) is None

    # The owner keeps the Openverse copy: now that one is the work's copy.
    lib.update("openverse:1", pooled=False)
    assert lib.spare_copies() == {"met:2", "wmc:3", "aic:5"}
    # Both copies kept by the owner: the catalogue lists the work once, in
    # the copy from the more reliable source.
    lib.update("met:2", pooled=False)
    assert {i.id for i in lib.query()[1]} == {"met:2", "europeana:4"}
    assert {i.id for i in lib.query(PlaylistRules(query="Wheat"))[1]} == {"met:2"}
    # Only the Openverse copy is a favourite: that one stands for the work there.
    lib.update("openverse:1", favorite=True)
    assert [i.id for i in lib.query(PlaylistRules(favorites_only=True))[1]] == ["openverse:1"]
    lib.update("met:2", pooled=True)

    manual = lib.save_playlist(
        Playlist(name="Mine", kind=PlaylistKind.MANUAL, item_ids=["openverse:1", "europeana:4"])
    )
    lib.update("met:2", pooled=False)
    manual = manual.model_copy(update={"item_ids": [*manual.item_ids, "met:2"]})
    assert [i.id for i in lib.playlist_items(manual)] == ["met:2", "europeana:4"]


def _fake(key: str, titles: list[str]) -> type[Museum]:
    class Fake(Museum):
        name = key

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            start = (page - 1) * limit
            items = [
                self._item(str(n), title=t, artist="Claude Monet", year=1900)
                for n, t in enumerate(titles)
            ]
            return len(items), items[start : start + limit]

        def fetch(self, source_id: str) -> Item | None:
            return None

    Fake.key = key
    return Fake


def _sources(monkeypatch) -> None:
    for key in list(MUSEUMS):
        monkeypatch.delitem(MUSEUMS, key)
    monkeypatch.setitem(MUSEUMS, "openverse", _fake("openverse", ["Haystacks", "Poplars"]))
    monkeypatch.setitem(MUSEUMS, "aic", _fake("aic", ["Haystacks", "Water Lilies"]))
    monkeypatch.setitem(MUSEUMS, "wmc", _fake("wmc", ["Haystacks", "Water Lilies", "Poplars"]))


def test_searching_every_source_finds_each_work_once(service, monkeypatch) -> None:
    _sources(monkeypatch)
    _, items, _ = service.importer.search_all("Monet", limit=8)
    # Where each work first came, its copy from the most reliable source.
    assert [i.id for i in items] == ["aic:0", "wmc:2", "aic:1"]

    lilies = _work("wmc", 1, title="Water Lilies", artist="Claude Monet", year=1900, pooled=True)
    service.library.upsert(lilies)
    shown = remote_items(service, items)
    # The museum's copy over the one the server put in the catalogue...
    assert [(r.item.id, r.in_library) for r in shown] == [
        ("aic:0", False),
        ("wmc:2", False),
        ("aic:1", False),
    ]
    assert shown[0].work == "monet|haystacks"
    # The catalogue shows its copy: the app leaves this one out there.
    assert [r.twin for r in shown] == [None, None, "wmc:1"]
    # ...but the owner's copy over any.
    service.library.update("wmc:1", pooled=False)
    shown = remote_items(service, items)
    assert [(r.item.id, r.in_library) for r in shown] == [
        ("aic:0", False),
        ("wmc:2", False),
        ("wmc:1", True),
    ]
    # One source asked for: its own works, as they are.
    assert [r.item.id for r in remote_items(service, items, copies=False)][2] == "aic:1"


def test_filling_takes_each_work_once_from_the_best_source(service, monkeypatch) -> None:
    _sources(monkeypatch)
    monkeypatch.setattr(service.importer, "_analysed", lambda item: item)
    job = Job(id="j", description="fill")
    service.importer.fill(PlaylistRules(artists=["Claude Monet"]), 10, job, pooled=True)
    visible = {"aic:0", "aic:1", "wmc:2"}
    assert {i.id for i in service.library.query()[1]} == visible
    assert job.done == 3 and set(job.item_ids) == visible
    # A copy taken before the better one came stays out of sight until the
    # catalogue is tidied.
    spare = service.library.spare_copies()
    assert spare <= {"openverse:0", "wmc:0", "wmc:1", "openverse:1"}
    assert service.player.drop_spare_copies() == len(spare)
    assert {i.id for i in service.library.query(include_excluded=True)[1]} == visible


def test_a_playlist_gets_a_work_once(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        for item in (_work("met", 1), _work("wmc", 2), _work("aic", 3, title="Irises")):
            svc.library.upsert(item)
        playlist = client.post(
            "/api/playlists", json={"name": "Wybór", "kind": "manual", "item_ids": ["met:1"]}
        ).json()["playlist"]["id"]
        detail = client.post(
            f"/api/playlists/{playlist}/items", json={"item_ids": ["wmc:2", "aic:3"]}
        ).json()
    assert detail["item_ids"] == ["met:1", "aic:3"]


def test_favorites_playlist_always_stays(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        playlists = client.get("/api/playlists").json()
        favorites = [p for p in playlists if p["rules"]["favorites_only"]]
        assert [p["name"] for p in favorites] == ["Ulubione"]
        assert favorites[0]["item_count"] == 0  # there even with no hearts
        fav_id = favorites[0]["id"]

        assert client.delete(f"/api/playlists/{fav_id}").status_code == 409
        # Renamed, it stays the hearts' smart playlist.
        renamed = client.put(
            f"/api/playlists/{fav_id}",
            json={"name": "Serduszka", "kind": "manual", "rules": {"favorites_only": False}},
        ).json()["playlist"]
        assert renamed["name"] == "Serduszka"
        assert renamed["kind"] == "smart" and renamed["rules"]["favorites_only"]

        other = client.post(
            "/api/playlists", json={"name": "Inna", "rules": {"colors": ["blue"]}}
        ).json()["playlist"]["id"]
        assert client.delete(f"/api/playlists/{other}").json() == {"deleted": True}

    # A library that lost it (deleted before) gets it back on start.
    svc.library.delete_playlist(fav_id)
    with TestClient(create_app(service.settings)) as client:
        names = [
            p["name"] for p in client.get("/api/playlists").json() if p["rules"]["favorites_only"]
        ]
    assert names == ["Ulubione"]


def test_aggregators_pass_on_several_collections() -> None:
    """Openverse has the Met's record and a Commons file of one painting;
    Europeana's Rijksmuseum records keep the museum's inventory number."""
    met = _work("openverse", "a", url="https://www.metmuseum.org/art/collection/search/437881")
    commons = _work(
        "openverse",
        "b",
        title="Vincent van Gogh - Wheat Field with Cypresses - Google Art Project",
        url="https://commons.wikimedia.org/w/index.php?curid=1",
    )
    assert origin(met) == "openverse:metmuseum.org" and same_work(met, commons)
    # Two of one museum's works still aren't copies...
    other = met.model_copy(
        update={"id": "openverse:c", "url": "https://www.metmuseum.org/art/collection/search/9"}
    )
    assert not same_work(met, other)
    # ...but two files on Commons may be, dated alike and of one shape.
    scan = _work("wmc", 1, title="Johannes Vermeer - Het melkmeisje - Google Art Project")
    scan = scan.model_copy(update={"artist": "Johannes Vermeer", "year": 1660})
    rescan = scan.model_copy(
        update={"id": "wmc:2", "title": "Johannes Vermeer - Het melkmeisje - rijksmuseum - 001"}
    )
    sized = {"width": 4000, "height": 4485}
    assert same_work(scan.model_copy(update=sized), rescan.model_copy(update=sized))
    assert not same_work(scan, rescan)  # shapes unknown
    assert not same_work(
        scan.model_copy(update=sized), rescan.model_copy(update={**sized, "year": None})
    )
    assert not same_work(
        scan.model_copy(update=sized), rescan.model_copy(update={"width": 4485, "height": 3000})
    )

    rijks = _work(
        "rijks",
        200108369,
        title="The Milkmaid",
        artist="Johannes Vermeer",
        url="https://www.rijksmuseum.nl/nl/collectie/object/SK-A-2344--42dd0e658c2979aec8e144d2357c55c0",
    )
    europeana = Item(
        id="europeana:90402~SK_A_2344",
        source="europeana",
        source_id="90402~SK_A_2344",
        title="Het melkmeisje",
        url="https://www.europeana.eu/item/90402/SK_A_2344",
    )
    other = europeana.model_copy(update={"id": "europeana:90402~SK_A_1595"})
    other = other.model_copy(update={"source_id": "90402~SK_A_1595"})
    assert same_work(rijks, europeana) and not same_work(rijks, other)


def test_shown_works_come_once_and_better_copies_replace_worse() -> None:
    shown = Shown()
    first = shown.take([_work("openverse", 1, year=1889), _work("openverse", 2, title="Irises")])
    assert [(t.item.id, t.work, t.replaces) for t in first] == [
        ("openverse:1", "gogh|wheat field cypresses", None),
        ("openverse:2", "gogh|irises", None),
    ]
    # Other museums answer later: their copies take the place of worse ones.
    later = shown.take(
        [_work("wmc", 3), _work("met", 4, year=1889), _work("wmc", 5, title="Irises")]
    )
    assert [(t.item.id, t.replaces) for t in later] == [
        ("wmc:3", "openverse:1"),
        ("met:4", "wmc:3"),
        ("wmc:5", "openverse:2"),
    ]
    # Copies no better than the one shown are left out.
    assert shown.take([_work("aic", 6, year=1889), _work("met", 4)]) == []


def test_streamed_search_shows_each_work_once(service, monkeypatch) -> None:
    """Each museum answers on its own: a work comes once, a better copy
    taking the place of a worse one, also on later pages."""
    from frame_server.web import create_app

    _sources(monkeypatch)
    app = create_app(service.settings)

    def shown(lines: list[dict], before: dict[str, dict] | None = None) -> dict[str, dict]:
        works = dict(before or {})
        for line in lines:
            for remote in line["items"]:
                assert remote["work"]
                works.pop(remote["replaces"] or "", None)
                assert remote["item"]["id"] not in works
                works[remote["item"]["id"]] = remote
        return works

    params = {"q": "Monet", "limit": 1}
    with TestClient(app) as client:
        with client.stream("GET", "/api/discover/search/stream", params=params) as resp:
            lines = [json.loads(line) for line in resp.iter_lines() if line]
        first = shown(lines)
        assert len({r["work"] for r in first.values()}) == len(first)
        assert list(first) == ["aic:0"]  # the museum's Haystacks
        works = first
        for page, sources in ((2, ["openverse", "aic", "wmc"]), (3, ["wmc"])):
            more = client.get(
                "/api/discover/search/stream", params={**params, "page": page, "source": sources}
            )
            works = shown([json.loads(line) for line in more.text.splitlines() if line], works)
        # Commons' Poplars in place of Openverse's, shown on the page before.
        assert sorted(works) == ["aic:0", "aic:1", "wmc:2"]
        assert works["wmc:2"]["replaces"] == "openverse:1"


def test_a_smart_playlist_needs_a_rule(service) -> None:
    from frame_server.library import Playlist
    from frame_server.web import create_app
    from frame_server.web.playlists_api import DETAIL_LIMIT

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        assert client.post("/api/playlists", json={"name": "Wszystko"}).status_code == 422
        # A manual one may start empty.
        manual = client.post("/api/playlists", json={"name": "Moja", "kind": "manual"})
        assert manual.status_code == 200

        # One saved before: its detail lists a part, and it can be deleted.
        for n in range(DETAIL_LIMIT + 5):
            svc.library.upsert(_work("met", n, title=f"Work {n}"))
        everything = svc.library.save_playlist(Playlist(name="Wszystko")).id
        detail = client.get(f"/api/playlists/{everything}").json()
        assert len(detail["items"]) == DETAIL_LIMIT
        assert detail["playlist"]["item_count"] == DETAIL_LIMIT + 5
        assert client.delete(f"/api/playlists/{everything}").json() == {"deleted": True}
