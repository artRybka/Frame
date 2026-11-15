"""A work whose picture is small for the frame is marked after its title on
tiles and on its card (Mateusz 2026-11-12), by a size that is known only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from frame_server.library import ImageCache, Item, ItemKind, low_res
from frame_server.library.models import ItemSummary, SharperCopy


def _work(item_id: str, **fields: Any) -> Item:
    fields.setdefault("kind", ItemKind.ARTWORK)
    fields.setdefault("title", f"Work {item_id}")
    source, _, source_id = item_id.partition(":")
    return Item(id=item_id, source=source, source_id=source_id, **fields)


@pytest.fixture(autouse=True)
def _no_sizes() -> Iterator[None]:
    yield
    low_res.known_sizes(None)


def test_a_size_the_source_says() -> None:
    # De Chirico on WikiArt: under 1000 px.
    assert low_res.low_side(_work("wikiart:1", width=760, height=950)) == 950
    assert low_res.low_side(_work("wikiart:2", width=1599, height=1200)) == 1599
    assert low_res.low_side(_work("wikiart:3", width=1600, height=1200)) == 0
    assert low_res.low_side(_work("nga:1", width=3000, height=2400)) == 0


def test_a_thumbnails_size_is_none() -> None:
    # The Met says no size: what it has is its thumbnail's 600 px.
    met = _work("met:1", width=600, height=480)
    assert low_res.low_side(met) == 0
    low_res.known_sizes(lambda item: 1200 if item.id == "met:1" else None)
    assert low_res.low_side(met) == 1200
    low_res.known_sizes(lambda item: 3800)
    assert low_res.low_side(met) == 0


def test_the_original_read_by_the_caller() -> None:
    assert low_res.low_side(_work("met:2", width=600, height=480), (900, 1400)) == 1400
    assert low_res.low_side(_work("met:3", width=600, height=480), (0, 0)) == 0


def test_a_sharper_copy_is_what_counts() -> None:
    copy = SharperCopy(url="u", item_id="wmc:9", source="wmc", width=4000, height=3000)
    assert low_res.low_side(_work("wikiart:4", width=760, height=950, sharper=copy)) == 0
    small = SharperCopy(url="u", item_id="wmc:8", source="wmc", width=1400, height=1000)
    assert low_res.low_side(_work("met:4", sharper=small)) == 1400


def test_only_museum_works() -> None:
    assert low_res.low_side(_work("upload:1", kind=ItemKind.PHOTO, width=800, height=600)) == 0
    assert low_res.low_side(_work("icloud:1", width=800, height=600)) == 0
    tile = _work("wmc:5#2", width=800, height=600, part_of="wmc:5")
    assert low_res.low_side(tile) == 0


def test_tiles_carry_it() -> None:
    assert ItemSummary.of(_work("wikiart:6", width=760, height=950)).low_side == 950
    assert ItemSummary.of(_work("wikiart:7", width=2000, height=2500)).low_side == 0


def test_the_long_side_known_here(tmp_path: Path) -> None:
    images = ImageCache(tmp_path, lambda: httpx.Client())
    met = _work("met:9", width=600, height=480)
    assert images.long_side(met) is None  # a thumbnail's size is none
    assert images.long_side(_work("wikiart:9", width=760, height=950)) == 950
    images._remember_size(met, Image.new("RGB", (1300, 1000)))
    assert images.long_side(met) == 1300
    low_res.known_sizes(images.long_side)
    assert low_res.low_side(met) == 1300


def test_the_downloaded_original_beats_the_size_said(tmp_path: Path) -> None:
    # Wyspiański's „Macierzyństwo” on WikiArt (2026-11-15): WikiArt said
    # 433 × 600, its file was 1441 × 1999; the card marked it „600 px”.
    images = ImageCache(tmp_path, lambda: httpx.Client())
    work = _work("wikiart:10", width=433, height=600)
    low_res.known_sizes(images.long_side)
    assert low_res.low_side(work) == 600  # nothing downloaded yet: what it says
    images._remember_size(work, Image.new("RGB", (1441, 1999)))
    assert images.long_side(work) == 1999
    assert low_res.low_side(work) == 0
    assert low_res.low_side(work, (1441, 1999)) == 0
    # A small original stays marked though its source says more.
    big = _work("wikiart:11", width=3000, height=4000)
    images._remember_size(big, Image.new("RGB", (900, 1200)))
    assert low_res.low_side(big) == 1200
    # A copy picked counts, whatever the work's own was.
    copy = SharperCopy(url="u", item_id="wmc:93560153", source="wmc", width=1920, height=2548)
    assert low_res.low_side(big.model_copy(update={"sharper": copy})) == 0
