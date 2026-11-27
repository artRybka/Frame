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


def drawing_photo(figure: tuple[int, int, int, int]) -> np.ndarray:
    """A lithograph with no plate: ``figure`` drawn dark, the rest of the
    scene in faint fine lines across the sheet."""
    photo = print_photo(figure)
    x0, y0, x1, y1 = SHEET
    for x in range(x0 + 60, x1 - 60, 17):
        if not figure[0] - 60 <= x <= figure[2] + 60:
            photo[y0 + 80 : y1 - 80, x : x + 2] = (222, 216, 202)
    for y in range(y0 + 90, y1 - 90, 41):
        photo[y : y + 2, figure[2] + 80 : x1 - 70] = (222, 216, 202)
    return photo


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


def test_a_print_photographed_as_its_sheet_alone_is_cut_round_its_impression() -> None:
    # Mateusz 2026-11-25: „Dlaczego takie dzieło się nie kadruje?” The
    # photograph is the sheet, nothing round it: the model wants it whole,
    # and the sheet is the photograph's own edges.
    x0, y0, x1, y1 = SHEET
    sheet_only = np.ascontiguousarray(print_photo((250, 200, 650, 500))[y0:y1, x0:x1])
    made = cm.sheet_cut(sheet_only, "whole", None)
    assert made is not None
    verdict, sheet, (_, alone) = made
    assert verdict == "cut" and sheet == cm.EDGES and alone is not None
    w, h = x1 - x0, y1 - y0
    want = [[(250 - x0) / w, (200 - y0) / h], [(650 - x0) / w, (200 - y0) / h]]
    assert np.abs(np.array(alone[:2]) - want).max() * w < 4
    # A sheet with a narrow margin, left whole, stays whole.
    narrow = np.ascontiguousarray(print_photo((140, 120, 760, 580))[y0:y1, x0:x1])
    assert cm.sheet_cut(narrow, "whole", None) is None
    # Unsure with no sheet found: the photograph is the sheet, as whole.
    assert cm.sheet_cut(sheet_only, "unsure", None) is not None


def test_an_unsure_print_is_cut_where_its_paper_bears_it_out() -> None:
    # Henequin's ornament (Met, 2026-11-25): a sheet with a narrow margin
    # on a light grey board, the model unsure of it (0.79 against 0.795).
    a = print_photo((140, 120, 760, 580)).copy()
    x0, y0, x1, y1 = SHEET
    board = np.ones(a.shape[:2], bool)
    board[y0:y1, x0:x1] = False
    a[board] = (168, 170, 172)
    sheet = corners(SHEET)
    made = cm.sheet_cut(a, "unsure", sheet)
    assert made is not None
    verdict, kept, (cut, alone) = made
    assert verdict == "cut" and alone is None and apart(cut, sheet) < 0.5 and kept == cut
    # A sheet not standing upright stays his.
    leaning = [
        [p[0] + (0.03 if i in (0, 3) else -0.03) * (1 if i < 2 else -1), p[1]]
        for i, p in enumerate(sheet)
    ]
    assert cm.upright_off(leaning, (W, H)) > cm.UPRIGHT
    assert cm.sheet_cut(a, "unsure", leaning) is None
    # Wide paper round the impression: cut round it, as a sure cut is.
    wide = print_photo((250, 200, 650, 500))
    made = cm.sheet_cut(wide, "unsure", sheet)
    assert made is not None and made[0] == "cut" and made[2][1] is not None


def test_the_margin_takes_in_the_lettering() -> None:
    # An ex-libris (CMA, 2026-11-25): a name printed under the picture is
    # not cut through („prawie wcina się w napis”).
    impression = (250, 200, 650, 460)
    photo = print_photo(impression).copy()
    photo[485:497, 300:600] = (70, 60, 50)  # a name, a little below
    made = cm.plate(photo, corners(SHEET))
    assert made is not None
    cut, alone = made
    assert max(p[1] for p in alone) < 470 / H  # the impression, without it
    assert max(p[1] for p in cut) > 500 / H  # the cut, round it


def test_one_dark_figure_of_a_drawing_is_no_impression() -> None:
    # A lithograph with no plate: one figure drawn dark, the rest of the
    # scene in faint fine lines across the sheet (Mateusz 2026-11-27, a
    # Toulouse-Lautrec cut to one of its two figures: „Nie możemy tak
    # robić”). The figure alone would be cut: the faint lines keep the sheet.
    figure = (250, 200, 480, 520)
    assert cm.plate(print_photo(figure), corners(SHEET)) is not None
    assert cm.plate(drawing_photo(figure), corners(SHEET)) is None


def test_lines_round_an_impression_within_its_margin_leave_it_cut() -> None:
    # A plate mark or a ruled border just round the impression is no drawing
    # left out.
    impression = (250, 200, 650, 500)
    photo = print_photo(impression)
    x0, y0, x1, y1 = impression
    photo[y0 - 10 : y0 - 8, x0 - 10 : x1 + 10] = (222, 216, 202)
    photo[y1 + 8 : y1 + 10, x0 - 10 : x1 + 10] = (222, 216, 202)
    assert cm.plate(photo, corners(SHEET)) is not None
