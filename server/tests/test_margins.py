"""A museum's blank margins around a picture are cut off, nothing else."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from frame_server.imaging.margins import margins, trim_margins
from frame_server.library.images import ImageCache
from frame_server.library.models import Item

RNG = np.random.default_rng(7)


def _painting(w: int, h: int) -> np.ndarray:
    """A dark, textured picture: no line of it is flat, but smooth enough
    for a JPEG of it to keep a clean edge, as a painting's photograph does."""
    coarse = RNG.integers(30, 160, size=(h // 8 + 2, w // 8 + 2, 3), dtype=np.uint8)
    smooth = Image.fromarray(coarse).resize((w + 16, h + 16), Image.Resampling.BICUBIC)
    grain = RNG.integers(-6, 7, size=(h, w, 3))
    return np.clip(np.asarray(smooth)[8 : 8 + h, 8 : 8 + w] + grain, 0, 255).astype(np.uint8)


def _framed(
    w: int = 300,
    h: int = 200,
    sides: tuple[int, int, int, int] = (30, 20, 30, 20),
    fill: int = 255,
) -> Image.Image:
    """``_painting`` on a flat sheet, ``sides`` = left, top, right, bottom."""
    left, top, right, bottom = sides
    sheet = np.full((h + top + bottom, w + left + right, 3), fill, dtype=np.uint8)
    sheet[top : top + h, left : left + w] = _painting(w, h)
    return Image.fromarray(sheet)


def _jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def test_white_sheet_is_cut_off_with_its_halo() -> None:
    img = _framed()
    box = margins(img)
    assert box is not None
    left, top, right, bottom = box
    # The margin and a few pixels of the picture's edge, no more.
    assert 30 < left <= 33 and 20 < top <= 23
    assert 330 - 3 <= right < 330 and 220 - 3 <= bottom < 220
    assert trim_margins(img).size == (right - left, bottom - top)


def test_black_sheet_and_jpeg_noise() -> None:
    img = Image.open(io.BytesIO(_jpeg(_framed(fill=0))))
    box = margins(img)
    assert box is not None
    assert 30 < box[0] <= 34 and 20 < box[1] <= 24


def test_a_speck_in_the_margin_does_not_end_it() -> None:
    img = _framed(w=600, h=400, sides=(40, 40, 40, 40))
    img.putpixel((660, 470), (90, 90, 90))  # a museum's stamp, bottom right
    box = margins(img)
    assert box is not None and box[2] < 640 and box[3] < 440


def test_only_left_and_right_padding() -> None:
    box = margins(_framed(sides=(50, 0, 50, 0)))
    assert box is not None
    assert box[1] == 0 and box[3] == 200 and box[0] > 50 and box[2] < 350


def test_one_light_edge_is_the_picture() -> None:
    # A burnt-out sky at the top only: a photograph, not a margin.
    img = _framed(sides=(0, 30, 0, 0))
    assert margins(img) is None
    assert trim_margins(img) is img


def test_no_margins_at_all() -> None:
    assert margins(Image.fromarray(_painting(200, 150))) is None


def test_light_painting_edges_are_not_flat_enough() -> None:
    # A pale sky painted to the edge: light, but not a flat fill.
    sky = RNG.integers(215, 250, size=(150, 200, 3), dtype=np.uint8)
    assert margins(Image.fromarray(sky)) is None


def test_a_sketch_keeps_its_sheet() -> None:
    # A small drawing on a large white page: what would be left is too
    # little of the picture, so the page stays.
    img = _framed(w=60, h=40, sides=(120, 80, 120, 80))
    assert margins(img) is None


def _item(source: str, n: int = 1) -> Item:
    return Item(
        id=f"{source}:{n}",
        source=source,
        source_id=str(n),
        title="Pejzaż z postaciami",
        thumb_url=f"https://framemark.vam.ac.uk/{n}/thumb.jpg",
        image_url=f"https://framemark.vam.ac.uk/{n}/full.jpg",
    )


def test_downloads_lose_margins_own_pictures_do_not(tmp_path: Path) -> None:
    data = _jpeg(_framed())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=data)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    museum = _item("vam")
    with Image.open(cache.ensure_thumb(museum)) as thumb:
        assert thumb.width < 300 and thumb.height < 200
    with Image.open(cache.ensure_image(museum)) as original:
        assert original.width < 300
    photo = _item("icloud")
    with Image.open(cache.ensure_thumb(photo)) as thumb:
        assert thumb.size == (360, 240)


def test_kept_pictures_are_trimmed_in_place(tmp_path: Path) -> None:
    cache = ImageCache(tmp_path, lambda: httpx.Client())
    framed = _framed()
    museum, own = _item("vam"), _item("upload")
    for item in (museum, own):
        framed.save(cache.thumb_path(item))
        framed.save(cache.image_path(item))
    plain = _item("vam", 2)
    Image.fromarray(_painting(200, 150)).save(cache.thumb_path(plain))
    assert cache.trim_kept() == 2
    for path in (cache.thumb_path(museum), cache.image_path(museum)):
        with Image.open(path) as img:
            assert img.width < 300
    for path in (cache.thumb_path(own), cache.image_path(own)):
        with Image.open(path) as img:
            assert img.size == (360, 240)
    assert cache.trim_kept() == 0  # once trimmed, nothing more to cut
