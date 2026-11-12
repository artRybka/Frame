"""Cover tiles show the work, not the paper or mount around it."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from frame_server.imaging.mount import inside_mount, work_box
from frame_server.library.images import ImageCache

CREAM = (236, 228, 212)


def _etching(size: tuple[int, int] = (480, 640)) -> Image.Image:
    """A dark plate in the middle of a wide cream sheet, with its caption
    below and the shadow of the sheet's edge on a white backdrop: Goya's
    "Si amanece; nos Vamos" as the Cleveland museum shows it."""
    w, h = size
    img = Image.new("RGB", size, (250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle((8, 8, w - 9, h - 9), fill=CREAM)
    rng = np.random.default_rng(1)
    plate = (rng.normal(70, 25, (300, 220, 3))).clip(0, 255).astype(np.uint8)
    img.paste(Image.fromarray(plate), (130, 150))
    draw.text((180, 470), "Si amanece; nos Vamos", fill=(60, 60, 60))
    return img


def test_a_plate_on_a_wide_sheet_is_cut_to_the_plate() -> None:
    box = work_box(_etching())
    assert box is not None
    left, top, right, bottom = box
    # The plate is x 130–350 of 480, y 150–450 of 640, its caption just
    # below it may stay; the wide sheet goes.
    assert 0.2 < left < 130 / 480 and 350 / 480 < right < 0.8
    assert 0.18 < top < 150 / 640 and 450 / 640 < bottom < 0.8
    cut = inside_mount(_etching())
    assert cut.size[0] < 0.6 * 480 and cut.size[1] < 0.6 * 640


def test_a_picture_running_to_its_edges_is_left_whole() -> None:
    rng = np.random.default_rng(2)
    painting = Image.fromarray(rng.normal(120, 50, (400, 520, 3)).clip(0, 255).astype(np.uint8))
    assert work_box(painting) is None
    assert inside_mount(painting) is painting
    # A dark ground at the edges is the picture, never a mount.
    dark = Image.new("RGB", (400, 500), (20, 18, 16))
    ImageDraw.Draw(dark).ellipse((120, 150, 280, 350), fill=(200, 160, 120))
    assert work_box(dark) is None
    # A sheet with a margin a few percent wide: the tile's zoom takes it.
    sheet = Image.new("RGB", (400, 500), CREAM)
    sheet.paste(
        Image.fromarray(rng.normal(90, 30, (480, 384, 3)).clip(0, 255).astype(np.uint8)), (8, 10)
    )
    assert work_box(sheet) is None


def test_the_tile_is_kept_beside_the_thumbnail(tmp_path: Path) -> None:
    cache = ImageCache(tmp_path, http=lambda: None)  # type: ignore[arg-type,return-value]
    thumb = cache.thumbs / "cma-133655.jpg"
    _etching().save(thumb, "JPEG", quality=90)
    tile = cache.tile(thumb)
    assert tile.parent == cache.tiles
    with Image.open(tile) as img:
        assert img.size[0] < 0.6 * 480
    assert cache.tile(thumb) == tile  # kept: not worked out again
    # A picture with nothing around it: the thumbnail's own bytes.
    plain = cache.thumbs / "cma-1.jpg"
    rng = np.random.default_rng(3)
    Image.fromarray(rng.normal(120, 50, (300, 300, 3)).clip(0, 255).astype(np.uint8)).save(plain)
    assert cache.tile(plain).read_bytes() == plain.read_bytes()
