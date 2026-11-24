"""A print cut to its sheet, unless the paper round the impression is wide
(``crop_model.plate``; Mateusz 2026-11-24 09:36 UTC: „kadrujmy do kartki,
chyba że margines od odbitki jest wtedy bardzo duży. W takiej sytuacji
trzeba ograniczyć margines do rozsądnej proporcji, równo od każdej strony
od odbitki”; 10:38 „ale próg nie 25% tylko 15%”)."""

from __future__ import annotations

import numpy as np

from frame_server.imaging import crop_model as cm

W, H = 900, 700
SHEET = (100, 80, 800, 620)


def print_photo(impression: tuple[int, int, int, int], caption: bool = False) -> np.ndarray:
    """A sheet of paper on a dark board, an etching's lines on it."""
    rng = np.random.default_rng(3)
    a = np.full((H, W, 3), 55, np.uint8)
    x0, y0, x1, y1 = SHEET
    a[y0:y1, x0:x1] = (236, 230, 216)
    x0, y0, x1, y1 = impression
    y, x = np.mgrid[y0:y1, x0:x1]
    ink = ((x * 3 + y * 7) % 19 < 8) | ((x - y) % 23 < 3)
    a[y0:y1, x0:x1][ink] = (70, 60, 50)
    if caption:
        a[y1 + 14 : y1 + 20, x0 + 40 : x0 + 160] = (90, 80, 70)
    return (a.astype(np.int16) + rng.integers(-1, 2, a.shape)).clip(0, 255).astype(np.uint8)


def corners(box: tuple[float, float, float, float]) -> list[list[float]]:
    x0, y0, x1, y1 = box
    return [[x0 / W, y0 / H], [x1 / W, y0 / H], [x1 / W, y1 / H], [x0 / W, y1 / H]]


def apart(a: cm.Quad | list[list[float]], b: list[list[float]]) -> float:
    """How far apart two quads' corners are, in px."""
    return float(np.abs((np.array(a) - np.array(b)) * [W, H]).max())


def test_a_small_impression_on_a_wide_sheet_is_cut_with_an_even_margin() -> None:
    impression = (250, 200, 650, 500)
    made = cm.plate(print_photo(impression), corners(SHEET))
    assert made is not None
    cut, alone = made
    assert alone is not None and apart(alone, corners(impression)) < 3.5
    # 8% of the impression's shorter side (300 px), the same on every side.
    pad = cm.PLATE_MARGIN * 300
    x0, y0, x1, y1 = impression
    assert apart(cut, corners((x0 - pad, y0 - pad, x1 + pad, y1 + pad))) < 3.5


def test_the_margin_is_as_much_as_the_narrowest_side_has() -> None:
    # 20 px of paper above, 220 below: the even margin is the narrowest's.
    impression = (250, 100, 650, 400)
    made = cm.plate(print_photo(impression), corners(SHEET))
    assert made is not None
    x0, y0, x1, y1 = impression
    assert apart(made[0], corners((x0 - 20, y0 - 20, x1 + 20, y1 + 20))) < 3.5


def test_a_sheet_with_a_narrow_margin_stays() -> None:
    # 40 px round 620 × 460: at most 9% of the shorter side, under 15%.
    photo = print_photo((140, 120, 760, 580))
    assert cm.impression(photo, corners(SHEET)) is not None
    assert cm.plate(photo, corners(SHEET)) is None
    # Over a lower bar it would be cut.
    assert cm.plate(photo, corners(SHEET), over=0.05) is not None


def test_a_caption_under_the_impression_is_left_out_of_it() -> None:
    impression = (250, 200, 650, 480)
    made = cm.plate(print_photo(impression, caption=True), corners(SHEET))
    assert made is not None and made[1] is not None
    assert apart(made[1], corners(impression)) < 3.5


def test_printed_to_the_edge_or_on_no_paper_the_sheet_stays() -> None:
    # The ink right to the sheet's edge: no plain paper round anything.
    assert cm.plate(print_photo(SHEET), corners(SHEET)) is None
    # A dark sheet (a painting's board): no paper.
    dark = np.full((H, W, 3), 40, np.uint8)
    dark[250:450, 300:600] = 200
    assert cm.plate(dark, corners(SHEET)) is None


def test_overlap() -> None:
    a = corners((100, 100, 500, 500))
    assert cm.overlap(a, a, (W, H)) == 1.0
    assert abs(cm.overlap(a, corners((300, 100, 700, 500)), (W, H)) - 1 / 3) < 0.02
