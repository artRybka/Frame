"""Elongated works kept larger (images.kept_size) and works' fragments
(library/fragments.py)."""

from __future__ import annotations

from pathlib import Path

import httpx
from PIL import Image

from frame_server.library.fragments import Fragments, part_id, split_part
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
    assert kept_size(4000, 3000) == (2560, 1920)
    assert kept_size(3000, 4000) == (1920, 2560)
    assert kept_size(5120, 2560) == (2560, 1280)  # 2:1, the edge
    assert kept_size(1000, 800) == (1000, 800)  # never enlarged


def test_elongated_pictures_keep_more() -> None:
    # Fukutomi's full scan, 1:30: 13 968 × 469 instead of 2560 × 86.
    width, height = kept_size(76716, 2577)
    assert width * height <= IMAGE_AREA * 1.001
    assert (width, height) == (13968, 469)
    # 3:1: the short side stays half the frame's.
    assert kept_size(9000, 3000) == (3840, 1280)
    # Tall ones too.
    assert kept_size(1000, 30000) == (467, 14022)
    # The source's own file is never enlarged.
    assert kept_size(3400, 114) == (3400, 114)
    # The long side has a limit.
    assert max(kept_size(400_000, 4000)) <= 16384
    assert kept_long(76716, 76716 / 2577) == 13968
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
    wide = _item("yale", iiif, 16555, 720)
    assert own_copy(wide) == "https://example.org/iiif/x/full/!12275,12275/0/default.jpg"
    assert usual_copy(wide) == iiif
    assert own_copy(_item("yale", iiif, 4000, 3000)) == iiif  # ordinary
    assert own_copy(_item("vam", iiif, 16555, 720)) == iiif  # sizes not the file's
    si = "https://ids.si.edu/ids/deliveryService?id=X&max=2560"
    assert own_copy(_item("si", si, 9000, 1000)).endswith("&max=7680")


def test_a_larger_size_refused_falls_back(tmp_path: Path) -> None:
    iiif = "https://example.org/iiif/x/full/!2560,2560/0/default.jpg"
    cache = ImageCache(tmp_path, lambda: httpx.Client())
    urls = cache._addresses(_item("nga", iiif, 9000, 1000), thumb=False)
    assert urls == ["https://example.org/iiif/x/full/!7680,7680/0/default.jpg", iiif]


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
        "|-\n|[[File:Bosch - Garden-x0-y1.jpg|117px]]\n|}\n[[File:Bosch Garden.jpg|117px]]"
    )

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
        assert titles == [
            "File:Bosch - Garden-x0-y0.jpg",
            "File:Bosch - Garden-x1-y0.jpg",
            "File:Bosch - Garden-x0-y1.jpg",
        ]
        pages = {
            str(n): {
                "title": t,
                "imageinfo": [
                    {
                        "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{n}.jpg",
                        "thumburl": f"https://upload.wikimedia.org/thumb/{n}.jpg",
                        "width": 29952,
                        "height": 29952,
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
    assert [p.width for p in parts] == [29952] * 3
    assert parts[0].image_url.endswith("/0.jpg")
    # Shown in Commons' widest rendition, not 150 MB.
    assert "/thumb/" in own_copy(parts[0]) and "3840px" in own_copy(parts[0])
    # A file without tiles: no question about its page.
    other = garden.model_copy(update={"id": "wmc:5", "source_id": "5"})
    assert fragments.items(other) == []


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
