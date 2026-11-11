"""Copies of one work from several sources."""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from frame_server.imaging.layout import Crop
from frame_server.library import (
    Item,
    ItemKind,
    Job,
    Library,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    duplicates,
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
from frame_server.library.models import Framing, SharperCopy
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


def test_an_art_archives_slide_comes_after_every_other_copy() -> None:
    """Foto Marburg's faded colour slides on Europeana (Mateusz 2026-11-09):
    Commons' and WikiArt's copies come first; Europeana's museums' own
    scans keep their place before Commons."""
    marburg = "German Documentation Center for Art History - Marburg Picture Index"
    found = [
        _work("europeana", "199~a", title="Olive Grove", credit=marburg),
        _work("wikiart", 2, title="Olive Grove"),
        _work("wmc", 3, title="Olive Grove"),
    ]
    assert [i.id for i in dedupe(found)] == ["wmc:3"]
    assert [i.id for i in dedupe([found[0], found[1]])] == ["wikiart:2"]
    museum = _work("europeana", "2048~b", title="Olive Grove", credit="Nationalmuseum Sweden")
    assert [i.id for i in dedupe([found[2], museum])] == ["europeana:2048~b"]


def test_the_copy_with_the_better_picture_stands_for_the_work() -> None:
    """The picture first, then the source (Mateusz 2026-11-11): until
    1.145.29 Europeana's 400 px "Die Malkunst" stood before Commons' 7377."""
    vermeer = {"title": "Die Malkunst", "artist": "Johannes Vermeer"}
    khm = _work("europeana", "15502~GG_9128", width=400, height=479, **vermeer)
    commons = _work("wmc", 22003845, width=6209, height=7377, **vermeer)
    assert [i.id for i in dedupe([khm, commons])] == ["wmc:22003845"]
    # A museum says no size of its own picture, which is large: it stays
    # before Commons' copy, as the more reliable source.
    met = _work("met", 1, width=495, height=624)
    assert [i.id for i in dedupe([_work("wmc", 2, width=6600, height=8320), met])] == ["met:1"]
    # A copy known to be too small for the frame comes after one that is not.
    monet = {"title": "Impression, Sunrise", "artist": "Claude Monet", "year": 1872}
    weak = _work("wmc", 3, width=1600, height=1245, **monet)
    large = _work("wmc", 4, width=5773, height=4478, **monet)
    assert [i.id for i in dedupe([weak, large])] == ["wmc:4"]
    assert [i.id for i in dedupe([weak, _work("europeana", "9~x", **monet)])] == ["europeana:9~x"]
    # A sharper copy shown in its place makes the picture large enough.
    shown = SharperCopy(
        item_id="wmc:4", source="wmc", url="https://example.org/a.jpg", width=5773, height=4478
    )
    sharpened = _work("europeana", "9~y", sharper=shown, **monet)
    assert [i.id for i in dedupe([large, sharpened])] == ["europeana:9~y"]
    # Of two alike, the one the owner kept.
    kept = _work("wmc", 5, width=5000, height=3880, **monet)
    assert [i.id for i in dedupe([large.model_copy(update={"pooled": True}), kept])] == ["wmc:5"]


def test_a_painting_and_a_drawing_of_one_title_are_two_works() -> None:
    """Van Gogh's "Cypresses": the Met's painting and the Art Institute's
    drawing were one work, the drawing behind the painting (the catalogue
    of 2026-11-11)."""
    cypresses = {"title": "Cypresses", "year": 1889}
    met = _work("met", 437980, medium="Oil on canvas", classification="Paintings", **cypresses)
    drawing = "Pen and reed pen and brown ink over graphite on paper"
    aic = _work("aic", 87327, medium=drawing, **cypresses)
    assert not same_work(met, aic)
    assert len(dedupe([met, aic])) == 2
    # A copy that does not say what it is made with is either's.
    assert same_work(met, _work("wmc", 1, **cypresses))
    assert same_work(aic, _work("wmc", 1, **cypresses))
    # Paint on a drawing ("with watercolor") says no more.
    assert same_work(met, _work("cma", 2, medium="Pen and ink with watercolor", **cypresses))
    assert same_work(aic, _work("cma", 3, medium="Reed pen and ink", **cypresses))


def test_a_heart_follows_the_work_to_its_better_copy(tmp_path) -> None:
    """Ulubione shows a work in the copy that is liked: the heart moves to
    the better one (Mateusz 2026-11-11), the copy liked before stays."""
    lib = Library(tmp_path / "lib.db")
    monet = {"title": "Impression, Sunrise", "artist": "Claude Monet", "year": 1872}
    lib.upsert(_work("wmc", 3, width=1600, height=1245, **monet))
    lib.upsert(_work("wmc", 4, width=5773, height=4478, pooled=True, **monet))
    lib.upsert(_work("met", 1))
    lib.upsert(_work("openverse", 2))
    lib.upsert(_work("europeana", "9~x", title="Irises"))
    lib.upsert(_work("aic", 5, title="Irises", pooled=True))
    for item_id in ("wmc:3", "openverse:2", "met:1", "europeana:9~x"):
        lib.set_favorite("owner", item_id, True)
    lib.update("europeana:9~x", framing={"landscape": Framing(fill=Crop(x=0.4, zoom=1.5))})
    # The small Monet's heart goes to the large one; the Openverse copy's
    # stays, the Met's being liked too; the Europeana copy was framed.
    assert lib.hearts_to_best() == [("owner", "wmc:3", "wmc:4")]
    assert lib.favorites("owner") == {"wmc:4", "openverse:2", "met:1", "europeana:9~x"}
    assert lib.get("wmc:3") is not None and not lib.get("wmc:3").favorite  # type: ignore[union-attr]
    assert lib.get("wmc:4").favorite  # type: ignore[union-attr]
    assert lib.hearts_to_best() == []  # nothing left to move
    liked = lib.query(PlaylistRules(favorites_only=True), user="owner")[1]
    assert {i.id for i in liked} == {"wmc:4", "met:1", "europeana:9~x"}


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
    # The museum's copy stands for the work, the one the owner kept from
    # Europeana stays (in his lists): until 1.145.29 a kept copy came first.
    assert lib.spare_copies() == {"openverse:1", "wmc:3"}
    assert {i.id for i in lib.query()[1]} == {"met:2", "aic:5"}
    # Asked by source, a source's copies are there.
    assert [i.id for i in lib.query(PlaylistRules(sources=["openverse"]))[1]] == ["openverse:1"]

    assert lib.twin(_work("rijks", 6)) == lib.get("met:2")
    assert lib.twin(lib.get("met:2")) is None  # type: ignore[arg-type]
    assert lib.twin(_work("rijks", 7, title="Irises")) is None

    # The owner keeps the Openverse copy: it stays, behind the museum's.
    lib.update("openverse:1", pooled=False)
    assert lib.spare_copies() == {"wmc:3"}
    assert {i.id for i in lib.query()[1]} == {"met:2", "aic:5"}

    # Every source but the Art Institute: the next copy of its work takes
    # its place.
    rest = lib.query(PlaylistRules(exclude_sources=["aic"]))[1]
    assert {i.id for i in rest} == {"met:2", "europeana:4"}
    assert {i.id for i in lib.query(PlaylistRules(exclude_sources=["met"]))[1]} == {
        "openverse:1",
        "aic:5",
    }
    # Both copies kept by the owner: the catalogue lists the work once, in
    # the copy from the more reliable source.
    lib.update("met:2", pooled=False)
    assert {i.id for i in lib.query()[1]} == {"met:2", "aic:5"}
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


def test_grouping_is_kept_through_changes_that_do_not_touch_it(
    tmp_path, caplog, monkeypatch
) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_work("met", 1, pooled=True))
    lib.upsert(_work("openverse", 2, pooled=True))
    lib.upsert(_work("aic", 3, title="Irises", pooled=True))
    photo = Item(id="icloud:p", kind=ItemKind.PHOTO, source="icloud", source_id="p", url="a")
    lib.upsert(photo)
    works = lib.works()
    assert lib.spare_copies() == {"openverse:2"}

    # An album photo's fresh signed link, a work's keywords or shows, a
    # re-import as it was, a lone work deleted: the same grouping.
    lib.update("icloud:p", image_url="https://cvws.icloud-content.com/new")
    lib.update("met:1", keywords=["wheat"], show_count=3)
    lib.upsert(_work("met", 1, pooled=True))
    lib.delete("aic:3")
    lib.delete("icloud:p")
    assert lib.works() is works
    assert lib.get("met:1").keywords == ["wheat"]  # type: ignore[union-attr]
    assert works.best(_work("rijks", 9)) == lib.get("met:1")
    assert {i.id for i in lib.query()[1]} == {"met:1"}

    # The same values again: nothing is written.
    version = lib._version
    lib.update("met:1", show_count=3)
    assert lib._version == version

    # A title, or a copy of a work deleted: the works they have to do with
    # are grouped anew, in the same grouping (no one waits for the rest).
    lib.update("met:1", title="Wheat Field")
    assert lib.works() is works
    assert lib.spare_copies() == set()  # two works now
    lib.upsert(_work("rijks", 5, title="Wheat Field", pooled=True))
    assert lib.spare_copies() == {"rijks:5"}  # added to its group
    lib.delete("met:1")  # its copy is the work now
    assert lib.works() is works
    assert lib.spare_copies() == set()
    assert works.best(_work("aic", 9, title="Wheat Field")) == lib.get("rijks:5")
    assert lib.regrouped()[0] == 1 and lib.regrouped_in_part()[0] == 2

    # A change that has to do with too many works to look through while
    # the library waits: all are grouped again, and the log says why.
    monkeypatch.setattr(duplicates, "REGROUP_LOOKS", -1)
    grouping = [list(group) for group in works.groups]
    lib.update("rijks:5", title="Cypresses")
    assert [list(group) for group in works.groups] == grouping  # left as it was
    lib.update("rijks:5", year=1889)
    with caplog.at_level(logging.DEBUG, logger="frame_server.library.repo"):
        assert lib.works() is not works
    assert "after change of rijks:5 (title), in MainThread and 1 more change(s)" in caplog.text
    assert lib.works().best(_work("aic", 9, title="Cypresses")) == lib.get("rijks:5")


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
    # The heart on a search tile is the library's, over the museum's text.
    service.library.upsert(items[2].model_copy(update={"favorite": True}))
    held = remote_items(service, items, copies=False)[2]
    assert (held.in_library, held.item.favorite, items[2].favorite) == (True, True, False)


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


def test_filling_leaves_out_museums_asked_to(service, monkeypatch) -> None:
    _sources(monkeypatch)
    monkeypatch.setattr(service.importer, "_analysed", lambda item: item)
    job = Job(id="j", description="fill")
    rules = PlaylistRules(artists=["Claude Monet"], exclude_sources=["aic"])
    service.importer.fill(rules, 10, job, pooled=True)
    assert job.item_ids and not any(i.startswith("aic:") for i in job.item_ids)


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
        # It can be presented on the frame like any other.
        assert client.post(f"/api/playlists/{fav_id}/play").status_code == 202
        assert svc.player.settings.playlist_id == fav_id
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


def test_search_leaves_out_museums_asked_to(service, monkeypatch) -> None:
    """Every museum but those left out ("wszystkie poza Yale")."""
    from frame_server.web import create_app

    _sources(monkeypatch)
    app = create_app(service.settings)
    params = {"q": "Monet", "limit": 4, "skip": ["aic"]}
    with TestClient(app) as client:
        with client.stream("GET", "/api/discover/search/stream", params=params) as resp:
            lines = [json.loads(line) for line in resp.iter_lines() if line]
        assert sorted({line["source"] for line in lines}) == ["openverse", "wmc"]
        assert all(not r["item"]["id"].startswith("aic:") for li in lines for r in li["items"])
        found = client.get("/api/discover/search", params=params).json()
        assert found["items"] and all(r["item"]["source"] != "aic" for r in found["items"])
        # Every museum left out: nothing to ask.
        every = {**params, "skip": ["aic", "openverse", "wmc"]}
        assert client.get("/api/discover/search/stream", params=every).text == ""
        assert client.get("/api/discover/search", params=every).json()["total"] == 0
        # Left out alone asks nothing, as no museum chosen does.
        assert client.get("/api/discover/search", params={"skip": ["aic"]}).json()["total"] == 0

        # The catalogue leaves them out too.
        library = app.state.service.library
        library.upsert(_work("aic", 9, title="Haystacks", artist="Claude Monet"))
        library.upsert(_work("wmc", 8, title="Poplars", artist="Claude Monet"))
        listed = client.get("/api/library/items", params={"skip": ["aic"]}).json()
        assert [i["id"] for i in listed["items"]] == ["wmc:8"]


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


def test_a_hidden_work_is_gone_everywhere_but_ukryte(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        for item in (_work("met", 1), _work("aic", 3, title="Irises")):
            svc.library.upsert(item)
        svc.library.upsert(_work("wmc", 2, pooled=True))  # the server's copy of met:1
        playlist = client.post(
            "/api/playlists", json={"name": "Wybór", "kind": "manual", "item_ids": ["met:1"]}
        ).json()["playlist"]["id"]
        client.post(f"/api/playlists/{playlist}/items", json={"item_ids": ["aic:3"]})

        hidden = client.patch("/api/library/items/met:1", json={"excluded": True}).json()
        assert hidden["excluded"] and hidden["excluded_at"]
        page = client.get("/api/library/hidden").json()
        assert [i["id"] for i in page["items"]] == ["met:1"]
        # Not on the playlist, not in the library, its copies neither...
        listed = client.get(f"/api/playlists/{playlist}").json()["items"]
        assert [i["id"] for i in listed] == ["aic:3"]
        found = client.get("/api/library/items").json()["items"]
        assert [i["id"] for i in found] == ["aic:3"]
        # ...nor at a museum, the same work from another one included.
        at_museums = [_work("met", 1), _work("rijks", 9), _work("aic", 3, title="Irises")]
        assert [r.item.id for r in remote_items(svc, at_museums)] == ["aic:3"]

        back = client.patch("/api/library/items/met:1", json={"excluded": False}).json()
        assert not back["excluded"] and back["excluded_at"] is None
        assert client.get("/api/library/hidden").json()["items"] == []
        listed = client.get(f"/api/playlists/{playlist}").json()["items"]
        assert [i["id"] for i in listed] == ["met:1", "aic:3"]
        assert len(remote_items(svc, at_museums)) == 2  # met:1 and its copy are one work


# -- a change regroups the works it has to do with alone (docs/RULES.md, stage 2) ----


def _grouping(works: Works) -> set[tuple[str, ...]]:
    return {tuple(i.id for i in group) for group in works.groups if group}


def _filed_right(works: Works) -> None:
    """Every group is found by its items' titles and links, and nothing
    points at a group emptied."""
    for index, group in enumerate(works.groups):
        for item in group:
            assert works.group_index(item.id) == index
            assert all(index in held for held in works._held_under(item))
    for held in [*works._by_title.values(), *works._by_link.values()]:
        assert all(works.groups[index] for index in held)


def test_a_change_regroups_as_grouping_everything_anew_would() -> None:
    """Thousands of changes to small catalogues full of near copies: after
    each, the grouping is the one made from scratch, copy for copy and in
    the same order within each work."""
    import random

    titles = ["Irises", "Wheat Field", "Landscape", "Portrait of a Man", "Sunflowers"]
    artists = ["Vincent van Gogh", "van Gogh", "Claude Monet", "Monet", ""]
    sources = ["met", "aic", "wmc", "openverse", "europeana", "rijks", "wikiart", "cma"]
    for seed in range(60):
        rng = random.Random(seed)

        def some(n: int, rng: random.Random = rng) -> Item:
            source = rng.choice(sources)
            return Item(
                id=f"{source}:{n}",
                source=source,
                source_id=f"{rng.randint(1, 3)}~{n}" if source == "europeana" else str(n),
                title=rng.choice(titles),
                artist=rng.choice(artists),
                year=rng.choice([None, 1888, 1889, 1890, 1895]),
                width=rng.choice([0, 800, 1000]),
                height=rng.choice([0, 800]),
                url=rng.choice(["", "", f"https://example.org/{rng.randint(1, 6)}"]),
                image_url=f"https://example.org/img/{rng.randint(1, 40)}.jpg",
                pooled=rng.random() < 0.7,
            )

        items = {i.id: i for i in (some(n) for n in range(40))}
        works = Works(items.values())
        for _ in range(60):
            item_id = rng.choice(list(items))
            what = rng.random()
            if what < 0.15 and len(items) > 5:
                del items[item_id]
                assert works.remove(item_id) or works.regroup(item_id, None)
            else:
                old = items[item_id]
                other = rng.choice(list(items))
                new = old.model_copy(
                    update=rng.choice(
                        [
                            {"title": rng.choice(titles)},
                            {"artist": rng.choice(artists)},
                            {"year": rng.choice([None, 1888, 1889, 1890, 1895])},
                            {"copy_of": "" if other == item_id else other},
                            {"copy_of": ""},
                            {"pooled": not old.pooled},
                            {"url": f"https://example.org/{rng.randint(1, 6)}"},
                            {"width": rng.choice([0, 800, 1000])},
                            {"kind": rng.choice([ItemKind.ARTWORK, ItemKind.PHOTO])},
                        ]
                    )
                )
                items[item_id] = new
                assert works.regroup(item_id, new)
            assert _grouping(works) == _grouping(Works(items.values())), seed
            _filed_right(works)
        assert works.spare() == Works(items.values()).spare()


def test_a_copy_named_joins_its_work_and_the_rest_stays(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(1, 4):
        lib.upsert(_work("met", n, title=f"Work {n}", pooled=True))
    lib.upsert(_work("wmc", "a", title="Untitled", artist="", pooled=True))
    works = lib.works()
    untouched = [works.groups[works.group_index(f"met:{n}")] for n in (2, 3)]  # type: ignore[index]
    lib.update("wmc:a", copy_of="met:1")  # what the twins write
    assert lib.works() is works
    assert lib.spare_copies() == {"wmc:a"}
    assert all(
        works.groups[works.group_index(f"met:{n}")] is group  # type: ignore[index]
        for n, group in zip((2, 3), untouched, strict=True)
    )
    # ... and taken apart again ("To nie to samo").
    lib.update("wmc:a", copy_of="")
    assert lib.spare_copies() == set()
    assert lib.regrouped()[0] == 1 and lib.regrouped_in_part()[0] == 2


def test_a_copy_named_of_a_hidden_work_is_hidden_with_it(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_work("met", 1, title="The Little Street", artist="Johannes Vermeer"))
    lib.upsert(_work("wmc", 2, title="Het straatje", artist="", pooled=True))
    lib.update("met:1", excluded=True)
    assert {i.id for i in lib.query()[1]} == {"wmc:2"}
    # Their pictures show them to be one work (the twins): hidden as well,
    # and so is its copy a museum answers with.
    lib.update("wmc:2", copy_of="met:1")
    hidden = lib.hidden()
    assert lib.get("wmc:2") in hidden
    assert _work("rijks", 7, title="The Little Street", artist="Johannes Vermeer") in hidden
    assert lib.query()[1] == []
    # Taken apart again ("To nie to samo"): shown again.
    lib.update("wmc:2", copy_of="")
    assert lib.get("wmc:2") not in lib.hidden()
    assert {i.id for i in lib.query()[1]} == {"wmc:2"}
