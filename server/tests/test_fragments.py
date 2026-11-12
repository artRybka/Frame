"""Elongated works kept larger (images.kept_size) and works' fragments
(library/fragments.py)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from frame_server.library.fragments import Fragments, Part, part_id, place, split_part
from frame_server.library.images import (
    IMAGE_AREA,
    IMAGE_MAX,
    ImageCache,
    kept_long,
    kept_size,
    own_copy,
    usual_copy,
)
from frame_server.library.models import Item
from frame_server.sharper import Quality


def test_ordinary_pictures_keep_the_long_side() -> None:
    assert kept_size(6000, 4500) == (4000, 3000)
    assert kept_size(4500, 6000) == (3000, 4000)
    assert kept_size(10000, 5000) == (4000, 2000)  # 2:1, the edge
    assert kept_size(1000, 800) == (1000, 800)  # never enlarged


def test_elongated_pictures_keep_more() -> None:
    # Fukutomi's full scan, 1:30: 16 384 × 550 instead of 4000 × 134 (the
    # long side's limit comes first; 13 968 × 469 while the limit was 2560).
    width, height = kept_size(76716, 2577)
    assert width * height <= IMAGE_AREA * 1.001
    assert (width, height) == (16384, 550)
    # 3:1: the short side stays half the limit.
    assert kept_size(9000, 3000) == (6000, 2000)
    # Tall ones too.
    assert kept_size(1000, 30000) == (546, 16384)
    # The source's own file is never enlarged.
    assert kept_size(3400, 114) == (3400, 114)
    # The long side has a limit.
    assert max(kept_size(400_000, 4000)) <= 16384
    assert kept_long(76716, 76716 / 2577) == 16384
    assert kept_long(4000) == IMAGE_MAX


def test_quality_compares_elongated_copies_by_what_is_kept() -> None:
    own = Quality.sized(2560, 86)
    copy = Quality.sized(16555, 720)
    assert copy.better(own)  # was capped at 2560 each: never better
    assert not Quality.sized(2600, 88).better(own)


def _item(source: str, url: str, width: int, height: int) -> Item:
    return Item(
        id=f"{source}:1",
        source=source,
        source_id="1",
        image_url=url,
        thumb_url=url,
        width=width,
        height=height,
    )


def test_elongated_works_are_asked_larger() -> None:
    iiif = "https://example.org/iiif/x/full/!2560,2560/0/default.jpg"
    wide = _item("nga", iiif, 16555, 720)
    assert own_copy(wide) == "https://example.org/iiif/x/full/!16384,16384/0/default.jpg"
    assert usual_copy(wide) == iiif
    si = "https://ids.si.edu/ids/deliveryService?id=X&max=2560"
    assert own_copy(_item("si", si, 9000, 1000)).endswith("&max=9000")


def test_works_are_asked_in_the_size_they_are_kept_in() -> None:
    """Originals are kept up to 4000 px (Mateusz 2026-11-11); the works'
    addresses, kept with them, asked for 2560."""
    iiif = "https://example.org/iiif/x/full/!2560,2560/0/default.jpg"

    def asked(source: str, width: int, height: int) -> str:
        return own_copy(_item(source, iiif, width, height)).split("/full/")[1].split("/")[0]

    assert asked("nga", 7594, 5084) == "!4000,4000"
    # Never more than the file has: Yale's server enlarged a 1306 px scan
    # to the 2560 asked, the Courtauld's refuses.
    assert asked("smk", 1306, 1236) == "!1306,1306"
    assert asked("courtauld", 2973, 897) == "!2973,2973"
    # Yale's server takes 9 to 44 s over a size and half a second over the
    # whole file (2026-11-12): whole, and cut down here, ...
    assert asked("yale", 1306, 1236) == "full"
    assert asked("yale", 4212, 6066) == "full"
    assert asked("yale", 16555, 720) == "full"
    # ... but for a file past 50 Mpx (as much as is opened whole here).
    assert asked("yale", 8084, 6741) == "!4000,4000"
    # Sizes not the file's (a thumbnail's): the limit, ...
    assert asked("getty", 527, 640) == "!4000,4000"
    assert asked("vam", 409, 600) == "!4000,4000"
    # ... or the whole file where the server would enlarge it.
    assert asked("wellcome", 493, 600) == "max"
    # A size that is the museum's own limit stays.
    aic = "https://www.artic.edu/iiif/2/x/full/!3000,3000/0/default.jpg"
    assert own_copy(_item("aic", aic, 3000, 1267)) == aic
    assert own_copy(_item("met", "https://images.metmuseum.org/x.jpg", 600, 435)).endswith("x.jpg")


def test_a_larger_size_refused_falls_back(tmp_path: Path) -> None:
    iiif = "https://example.org/iiif/x/full/!2560,2560/0/default.jpg"
    cache = ImageCache(tmp_path, lambda: httpx.Client())
    urls = cache._addresses(_item("nga", iiif, 9000, 1000), thumb=False)
    assert urls == ["https://example.org/iiif/x/full/!9000,9000/0/default.jpg", iiif]


def test_a_scan_smaller_than_asked_is_had_whole(tmp_path: Path) -> None:
    """The Getty's server (IIIF 3) answers 400 to a size larger than the
    scan: a work with a scan smaller than the 2560 asked had no original at
    all (2026-11-11). The whole file is asked then, and only then."""
    iiif = "https://example.org/iiif/x/full/!2560,2560/0/default.jpg"
    asked: list[str] = []
    answers = {"!4000,4000": 400, "max": 200}

    def answer(request: httpx.Request) -> httpx.Response:
        size = request.url.path.split("/full/")[1].split("/")[0]
        asked.append(size)
        status = answers.get(size, 400)
        return httpx.Response(status, content=_jpeg(1888, 2290) if status == 200 else b"")

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(answer)))
    cache.sleep = lambda _s: None
    small = _item("getty", iiif, 527, 640)
    with Image.open(cache.ensure_image(small)) as kept:
        assert kept.size == (1888, 2290)
    assert asked == ["!4000,4000", "max"]
    # A server that is down is not asked for the whole file (the Getty's
    # largest scans are 12 000 px): the size asked before, then nothing.
    asked.clear()
    answers["!4000,4000"] = 404
    other = _item("getty", iiif, 527, 640).model_copy(update={"id": "getty:2"})
    with pytest.raises(OSError):
        cache.ensure_image(other)
    assert asked == ["!4000,4000", "!2560,2560"]


def test_originals_are_kept_in_the_new_size(tmp_path: Path) -> None:
    cache = ImageCache(tmp_path, lambda: httpx.Client())
    item = _item("upload", "", 6000, 300)
    cache.store(item, _jpeg(6000, 300))
    with Image.open(cache.image_path(item)) as kept:
        assert kept.size == (6000, 300)  # 1.8 Mpx, 20:1: kept whole


def _jpeg(width: int, height: int) -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 180, 150)).save(buf, "JPEG")
    return buf.getvalue()


CMA = {
    "data": {
        "id": 130638,
        "alternate_images": [
            {  # the whole scroll again
                "web": {"url": "https://cdn/alt0_web.jpg", "width": "900", "height": "30"},
                "print": {"url": "https://cdn/alt0_print.jpg", "width": "3400", "height": "114"},
            },
            {
                "web": {"url": "https://cdn/alt1_web.jpg", "width": "1263", "height": "509"},
                "print": {"url": "https://cdn/alt1_print.jpg", "width": "3400", "height": "1376"},
            },
            {
                "web": {"url": "https://cdn/alt2_web.jpg", "width": "1263", "height": "511"},
                "print": {"url": "https://cdn/alt2_print.jpg", "width": "3400", "height": "1375"},
            },
        ],
    }
}


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_cleveland_scroll_sections(tmp_path: Path) -> None:
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, json=CMA)

    fragments = Fragments(tmp_path / "fragments.json", lambda: _client(httpx.MockTransport(answer)))
    scroll = Item(
        id="cma:130638",
        source="cma",
        source_id="130638",
        title="The Story of Fukutomi",
        artist="Japan",
        image_url="https://cdn/print.jpg",
        width=900,
        height=30,
    )
    parts = fragments.items(scroll)
    assert [p.id for p in parts] == ["cma:130638~p1", "cma:130638~p2"]
    assert parts[0].image_url == "https://cdn/alt1_print.jpg"
    assert parts[0].thumb_url == "https://cdn/alt1_web.jpg"
    assert (parts[0].part_of, parts[0].part, parts[0].parts) == ("cma:130638", 1, 2)
    assert parts[1].title == "The Story of Fukutomi (fragment 2/2)"
    assert fragments.part(scroll, 2) == parts[1]
    assert fragments.part(scroll, 3) is None
    assert len(asked) == 1  # kept
    again = Fragments(tmp_path / "fragments.json", lambda: _client(httpx.MockTransport(answer)))
    assert [p.id for p in again.items(scroll)] == [p.id for p in parts]
    assert len(asked) == 1  # kept on disk too
    # Ordinary works are not asked about.
    painting = scroll.model_copy(
        update={"id": "cma:1", "source_id": "1", "width": 900, "height": 700}
    )
    assert fragments.items(painting) == []
    assert len(asked) == 1


def test_commons_tile_sets(tmp_path: Path) -> None:
    grid = (
        "{|\n|[[File:Bosch - Garden-x0-y0.jpg|117px]]\n||[[File:Bosch - Garden-x1-y0.jpg|117px]]\n"
        "|-\n|[[File:Bosch - Garden-x0-y1.jpg|117px]]\n||[[File:Bosch - Garden-x1-y1.jpg|117px]]\n"
        "|}\n[[File:Bosch Garden.jpg|117px]]"
    )
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "embeddedin":
            return httpx.Response(200, json={"query": {"embeddedin": [{"pageid": 22605738}]}})
        if params.get("prop") == "revisions" and params.get("pageids"):
            text = "{{Tile set available}}\n{{Tile set/Garden/grid}}\n{{Artwork}}"
            return httpx.Response(
                200,
                json={"query": {"pages": {"1": {"revisions": [{"slots": {"main": {"*": text}}}]}}}},
            )
        if params.get("prop") == "revisions":
            assert params.get("titles") == "Template:Tile set/Garden/grid"
            return httpx.Response(
                200,
                json={"query": {"pages": {"2": {"revisions": [{"slots": {"main": {"*": grid}}}]}}}},
            )
        titles = params.get("titles", "").split("|")
        asked.extend(titles)
        assert titles == [
            "File:Bosch - Garden-x0-y0.jpg",
            "File:Bosch - Garden-x1-y0.jpg",
            "File:Bosch - Garden-x0-y1.jpg",
            "File:Bosch - Garden-x1-y1.jpg",
        ]
        # The last column and row narrower, as a grid's ends are.
        sizes = [(29952, 29952), (9984, 29952), (29952, 5000), (9984, 5000)]
        pages = {
            str(n): {
                "title": t,
                "imageinfo": [
                    {
                        "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{n}.jpg",
                        "thumburl": f"https://upload.wikimedia.org/thumb/{n}.jpg",
                        "width": sizes[n][0],
                        "height": sizes[n][1],
                    }
                ],
            }
            for n, t in enumerate(titles)
        }
        return httpx.Response(200, json={"query": {"pages": pages}})

    fragments = Fragments(tmp_path / "f.json", lambda: _client(httpx.MockTransport(answer)))
    garden = Item(
        id="wmc:22605738",
        source="wmc",
        source_id="22605738",
        title="The Garden of Earthly Delights",
        width=30000,
        height=17078,
    )
    parts = fragments.items(garden)
    assert [p.width for p in parts] == [29952, 9984, 29952, 9984]
    assert parts[0].image_url.endswith("/0.jpg")
    # Each tile's place on the whole, from the grid.
    places = [(p.x, p.y, p.w, p.h) for p in fragments.parts(garden)]
    assert places[0] == (0, 0, 0.75, 29952 / 34952)
    assert places[1] == (0.75, 0, 0.25, 29952 / 34952)
    assert places[3] == (0.75, 29952 / 34952, 0.25, 5000 / 34952)
    # Shown in Commons' widest rendition, not 150 MB.
    assert "/thumb/" in own_copy(parts[0]) and "3840px" in own_copy(parts[0])
    # A file without tiles: no question about its page.
    other = garden.model_copy(update={"id": "wmc:5", "source_id": "5"})
    assert fragments.items(other) == []
    # Kept before tiles had places: asked again once.
    assert len(asked) == 4
    kept = json.loads((tmp_path / "f.json").read_text())
    for part in kept["wmc:22605738"]["parts"]:
        for key in ("x", "y", "w", "h"):
            part.pop(key)
    (tmp_path / "f.json").write_text(json.dumps(kept))
    again = Fragments(tmp_path / "f.json", lambda: _client(httpx.MockTransport(answer)))
    assert again.parts(garden)[1].x == 0.75
    assert len(asked) == 8


def test_tiles_off_a_grid_are_not_placed() -> None:
    def tile(width: int, height: int) -> Part:
        return Part(url="u", thumb="t", width=width, height=height)

    # Column 0's tiles of two widths: no grid.
    parts = place([tile(100, 50), tile(90, 50)], [(0, 0), (1, 0)])
    assert not any(p.placed for p in parts)
    # A column missing.
    parts = place([tile(100, 50), tile(100, 50)], [(0, 0), (0, 2)])
    assert not any(p.placed for p in parts)
    parts = place([tile(100, 50), tile(40, 50)], [(0, 0), (0, 1)])
    assert [(p.x, p.w) for p in parts] == [(0, 100 / 140), (100 / 140, 40 / 140)]


def test_fragment_ids() -> None:
    assert part_id("cma:130638", 3) == "cma:130638~p3"
    assert split_part("cma:130638~p3") == ("cma:130638", 3)
    assert split_part("cma:130638") is None
    assert split_part("aic:1~larger") is None
    assert split_part("smk:KKS1984-23/366~p12") == ("smk:KKS1984-23/366", 12)


def test_a_fragment_id_is_made_from_its_work(tmp_path: Path) -> None:
    from frame_server.library.importer import Importer
    from frame_server.library.repo import Library

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=CMA)

    cache = ImageCache(tmp_path / "cache", lambda: httpx.Client())
    importer = Importer(Library(tmp_path / "lib.db"), cache, None)  # type: ignore[arg-type]
    importer.fragments = Fragments(
        tmp_path / "f.json", lambda: _client(httpx.MockTransport(answer))
    )
    scroll = Item(
        id="cma:130638",
        source="cma",
        source_id="130638",
        title="The Story of Fukutomi",
        image_url="https://cdn/print.jpg",
        width=900,
        height=30,
    )
    importer.remember([scroll])  # as a search shows it
    assert [f.id for f in importer.fragments_of(scroll)] == ["cma:130638~p1", "cma:130638~p2"]
    found = importer.resolve("cma:130638~p2")
    assert found is not None and found.image_url == "https://cdn/alt2_print.jpg"
    assert importer.resolve("cma:130638~p9") is None
    # Cleveland's sections have no known place on the scroll (yet).
    found, places = importer.placed_fragments(scroll)
    assert len(found) == 2 and places == []


def test_fragments_keep_their_margins(tmp_path: Path) -> None:
    from frame_server.library.images import _trimmed

    assert _trimmed("wmc:22605738")
    assert not _trimmed("wmc:22605738~p18")  # a tile keeps its edges
    assert not _trimmed("upload:1")
    cache = ImageCache(tmp_path, lambda: httpx.Client())
    # A dark band at a tile's edge is part of the work, not a margin.
    banded = Image.new("RGB", (400, 300), (0, 0, 0))
    banded.paste((200, 180, 150), (0, 0, 300, 300))
    for item_id in ("wmc:5~p2", "wmc:5"):
        banded.save(tmp_path / "images" / f"{Item.stem_of(item_id)}.jpg", quality=95)
    cache.trim_kept()
    with Image.open(tmp_path / "images" / "wmc_5~p2.jpg") as tile:
        assert tile.size == (400, 300)
    # Those kept trimmed before are let go once, had again when asked for.
    assert cache.drop_fragments() == 1
    assert not (tmp_path / "images" / "wmc_5~p2.jpg").exists()
    assert (tmp_path / "images" / "wmc_5.jpg").exists()


def test_tile_sets_are_listed_once(tmp_path: Path) -> None:
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, json={"query": {"embeddedin": [{"pageid": 13276351}]}})

    fragments = Fragments(tmp_path / "f.json", lambda: _client(httpx.MockTransport(answer)))
    assert fragments.tiled("wmc:13276351")
    assert not fragments.tiled("wmc:1")
    assert not fragments.tiled("wmc:13276351~p2")
    assert not fragments.tiled("rijks:SK-C-5")
    assert len(asked) == 1


def test_tile_sets_are_known_by_their_work(tmp_path: Path) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("list") == "embeddedin":
            return httpx.Response(
                200, json={"query": {"embeddedin": [{"pageid": 1}, {"pageid": 2}]}}
            )
        assert params.get("pageids") == "1|2"
        pages = [
            {
                "title": "File:Nachtwacht - Google Art Project.jpg",
                "revisions": [
                    {"slots": {"main": {"content": "{{Artwork\n |wikidata = Q219831\n}}"}}}
                ],
            },
            {"title": "File:No work.jpg", "revisions": [{"slots": {"main": {"content": "x"}}}]},
        ]
        return httpx.Response(200, json={"query": {"pages": pages}})

    fragments = Fragments(tmp_path / "f.json", lambda: _client(httpx.MockTransport(answer)))
    assert fragments.tiled_files("Q219831") == ["File:Nachtwacht - Google Art Project.jpg"]
    assert fragments.tiled_files("Q1") == []
    assert fragments.tiled_files("") == []


def test_a_works_commons_copy_brings_its_tiles(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A work shown in Commons' file in a tile set (``Sharper``) has that
    file's tiles."""
    from frame_server.library.fragments import Fragments
    from frame_server.library.models import SharperCopy

    work = Item(id="rijks:1", source="rijks", source_id="1", title="De Nachtwacht")
    fragments = Fragments(tmp_path / "f.json", lambda: httpx.Client())
    assert not fragments.may_have(work)
    shown = work.model_copy(
        update={
            "sharper": SharperCopy(
                url="https://upload.wikimedia.org/x.jpg",
                item_id="wmc:123",
                source="wmc",
                width=3840,
                height=3200,
            )
        }
    )
    assert fragments.may_have(shown)
    assert Fragments._key(shown) == "rijks:1@wmc:123"


def test_tiles_are_kept_as_large_as_commons_gives_them(tmp_path: Path) -> None:
    from frame_server.library.images import TILE_MAX, kept_side

    assert TILE_MAX == 3840
    assert kept_side(_item("wmc", "", 29952, 29952)) == IMAGE_MAX
    tile = _item("wmc", "https://upload.wikimedia.org/x.jpg", 29952, 29952)
    tile = tile.model_copy(update={"id": "wmc:1~p3"})
    assert kept_side(tile) == TILE_MAX
    cache = ImageCache(tmp_path, lambda: httpx.Client())
    cache._original = lambda item, urgent: Image.new("RGB", (3840, 3840))  # type: ignore[method-assign]
    with Image.open(cache.picture(tile, True)[0]) as kept:
        assert kept.size == (3840, 3840)
    # Kept at 2560 before: let go once (the thumbnails stay).
    (tmp_path / "thumbs" / "wmc_1~p3.jpg").write_bytes(b"x")
    assert cache.drop_fragments(thumbs=False) == 1
    assert (tmp_path / "thumbs" / "wmc_1~p3.jpg").exists()
