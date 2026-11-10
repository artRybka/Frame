"""Works to look at far closer, in tiles: "Pod lupą" (frame_server.library.zoom;
Mateusz 2026-11-09)."""

from __future__ import annotations

import time

from frame_server.library import Item, ItemSummary, zoom
from frame_server.library.models import SharperCopy
from frame_server.player import TILE_WORKS_KEY
from frame_server.service import FrameService
from frame_server.web.discover_api import ZOOM_ROW, _zoom_row
from frame_server.web.library_api import remote_items


def _item(item_id: str, **fields: object) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("title", item_id)
    return Item(id=item_id, source=source, source_id=source_id, pooled=True, **fields)  # type: ignore[arg-type]


def test_works_shown_in_a_tile_set_are_marked_and_make_a_row(service: FrameService) -> None:
    zoom.known({"100", "200", "300"})
    night_watch = SharperCopy(
        url="https://upload.wikimedia.org/nw.jpg",
        item_id="wmc:200",
        source="wmc",
        width=3840,
        height=3124,
    )
    rijks = service.library.upsert(
        _item(
            "rijks:1", title="De Nachtwacht", artist="Rembrandt", sharper=night_watch, favorite=True
        )
    )
    garden = service.library.upsert(_item("wmc:100", title="Garden of Earthly Delights"))
    plain = service.library.upsert(_item("met:5", title="Wheat Field"))
    assert ItemSummary.of(rijks).zoom and ItemSummary.of(garden).zoom
    assert not ItemSummary.of(plain).zoom
    assert [r.zoom for r in remote_items(service, [rijks, plain], copies=False)] == [True, False]

    # Commons' files with a tile set as read: the one the library shows
    # already in another work's place (not twice), one it doesn't have.
    files = [_item("wmc:200", title="The Night Watch"), _item("wmc:300", title="The Milkmaid")]
    service.library.set_state(
        TILE_WORKS_KEY, {"at": time.time(), "items": [i.model_dump(mode="json") for i in files]}
    )
    row = _zoom_row(service)
    assert row is not None and row.key == ZOOM_ROW and row.title == "Pod lupą"
    ids = [r.item.id for r in row.items]
    assert ids[0] == "rijks:1"  # the heart first
    assert sorted(ids) == ["rijks:1", "wmc:100", "wmc:300"]
    assert all(r.zoom for r in row.items)


def test_no_row_before_the_tile_sets_are_listed(service: FrameService) -> None:
    zoom.known(())
    service.library.set_state(TILE_WORKS_KEY, {"at": time.time(), "items": []})
    assert _zoom_row(service) is None


def test_one_work_in_several_tile_sets_is_shown_once(service: FrameService) -> None:
    """Whistler's "Princess" three times in a row (Mateusz 2026-11-10):
    Commons keeps it as several files with a tile set."""
    zoom.known({"400", "401", "402", "500", "501"})
    princess = [
        _item(
            f"wmc:{n}",
            title="The Princess from the Land of Porcelain",
            artist="James McNeill Whistler",
            width=w,
            height=h,
        )
        for n, w, h in ((400, 8000, 13000), (401, 12000, 19500), (402, 6000, 9700))
    ]
    # Another work by its Wikidata item: titles in two languages.
    watch = [
        _item("wmc:500", title="The Night Watch", artist="Rembrandt", width=9000, height=7000),
        _item("wmc:501", title="De Nachtwacht", artist="Rembrandt", width=28128, height=23334),
    ]
    files = [*princess, *watch]
    service.library.set_state(
        TILE_WORKS_KEY, {"at": time.time(), "items": [i.model_dump(mode="json") for i in files]}
    )
    fragments = service.importer.fragments
    assert fragments is not None
    fragments._page_works.update({"500": "Q219831", "501": "Q219831"})
    row = _zoom_row(service)
    assert row is not None
    assert sorted(r.item.id for r in row.items) == ["wmc:401", "wmc:501"]  # the largest
