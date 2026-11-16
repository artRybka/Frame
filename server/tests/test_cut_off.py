"""Pictures their museums keep cut off, the rest the decoder's grey."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFile

from frame_server.imaging.cut_off import cut_off


def _jpeg(img: Image.Image, quality: int = 85) -> Image.Image:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality)
    return Image.open(io.BytesIO(out.getvalue())).convert("RGB")


def _painting(w: int, h: int, seed: int = 1) -> Image.Image:
    rng = np.random.default_rng(seed)
    a = rng.integers(20, 235, (h // 8 + 1, w // 8 + 1, 3), dtype=np.uint8)
    return Image.fromarray(a).resize((w, h), Image.Resampling.BICUBIC)


def _cut(img: Image.Image, keep: float) -> Image.Image:
    """``img`` with all but its top ``keep`` the decoder's grey."""
    out = img.copy()
    top = int(img.height * keep)
    out.paste((128, 128, 128), (0, top, img.width, img.height))
    return out


def test_a_truncated_jpeg_is_cut_off() -> None:
    """MNW's Podoliński (mnw:861190): the file ends early, the decoder
    fills the rest with grey."""
    whole = io.BytesIO()
    _painting(390, 640).save(whole, "JPEG", quality=90)
    data = whole.getvalue()[: len(whole.getvalue()) // 10]
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = False
    assert cut_off(img)


def test_the_museums_thumbnail_of_a_cut_off_file_is_cut_off() -> None:
    assert cut_off(_jpeg(_cut(_painting(624, 1024), 0.07)))
    assert cut_off(_jpeg(_cut(_painting(390, 640), 0.07).resize((97, 160))))
    # Large originals, too, and when most of the picture came through.
    assert cut_off(_jpeg(_cut(_painting(2400, 4000), 0.7), 92))


def test_a_picture_all_grey_is_cut_off() -> None:
    assert cut_off(_jpeg(Image.new("RGB", (300, 400), (128, 128, 128))))


def test_whole_pictures_are_not_cut_off() -> None:
    assert not cut_off(_jpeg(_painting(390, 640)))
    # A grey sheet around the picture: on both sides, a museum's padding.
    padded = Image.new("RGB", (400, 640), (128, 128, 128))
    padded.paste(_painting(400, 400), (0, 120))
    assert not cut_off(_jpeg(padded))
    # A grey floor with the grain of a photograph, or a grey not the fill's.
    floor = np.asarray(_painting(400, 600)).copy()
    rng = np.random.default_rng(3)
    floor[400:] = np.clip(128 + rng.normal(0, 6, floor[400:].shape), 0, 255).astype(np.uint8)
    assert not cut_off(_jpeg(Image.fromarray(floor)))
    darker = _painting(400, 600)
    darker.paste((110, 110, 110), (0, 300, 400, 600))
    assert not cut_off(_jpeg(darker))
    # A thin grey band at the bottom is not most of a picture lost.
    assert not cut_off(_jpeg(_cut(_painting(400, 600), 0.95)))
