"""The analysis's marks drawn in chalk (``imaging.chalk``): Mateusz
2026-11-22, five rounds of trial sheets, 22:10: "Jest super. Działamy."."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from frame_server.imaging import chalk
from frame_server.imaging.chalk import Stroke

W, H = 1200, 800


def _sheet() -> Any:
    """A pale study with a few things to ring: dark round spots, a tall figure."""
    img = Image.new("RGB", (W, H), (240, 234, 222))
    canvas = ImageDraw.Draw(img)
    for x, y in ((0.2, 0.3), (0.8, 0.3), (0.5, 0.75), (0.2, 0.75), (0.8, 0.75)):
        canvas.ellipse((x * W - 30, y * H - 30, x * W + 30, y * H + 30), fill=(170, 40, 30))
    canvas.rectangle((0.45 * W, 0.1 * H, 0.55 * W, 0.6 * H), fill=(60, 60, 80))
    return np.asarray(img)


def _at(layer: Any, x: float, y: float, r: int = 10) -> float:
    px, py = round(x * W), round(y * H)
    return float(layer[max(py - r, 0) : py + r + 1, max(px - r, 0) : px + r + 1].max())


def test_each_mark_has_its_layer_and_the_same_take_draws_the_same() -> None:
    marks = [
        Stroke("loop", [(0.5, 0.35), (0.56, 0.6)]),
        Stroke("triangle", [(0.2, 0.2), (0.4, 0.7), (0.1, 0.7)]),
        Stroke("rect", [(0.6, 0.1), (0.9, 0.4)]),
        Stroke("line", [(0.05, 0.9), (0.95, 0.88)], "Linia prowadzi wzrok w głąb"),
        Stroke("arrow", [(0.1, 0.5), (0.4, 0.45)]),
        Stroke("underline", [(0.6, 0.6), (0.9, 0.6)]),
        Stroke("rays", [(0.5, 0.5), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]),
        Stroke("spiral", [(0.9, 0.9), (0.7, 0.6), (0.75, 0.75)]),
        Stroke("motion", [(0.3, 0.8), (0.4, 0.7), (0.5, 0.68)]),
        Stroke("echo", [(0.2, 0.3), (0.8, 0.3)]),
        Stroke("rhythm", [(0.1, 0.1), (0.1, 0.4), (0.3, 0.1), (0.3, 0.4), (0.5, 0.1), (0.5, 0.4)]),
    ]
    layers = chalk.draw(_sheet(), marks, seed=7)
    assert len(layers) == len(marks)
    for layer, mark in zip(layers, marks, strict=True):
        assert layer.shape == (H, W) and layer.dtype == np.float32
        assert layer.min() >= 0.0 and layer.max() <= 1.0
        assert (layer > 0.3).mean() > 0.0006, mark.shape  # every mark drawn
        assert (layer > 0.47).mean() < 0.04, mark.shape  # a line, not a wash
    # Every choice of the hand comes from the seed.
    again = chalk.draw(_sheet(), marks, seed=7)
    assert all(np.array_equal(a, b) for a, b in zip(layers, again, strict=True))
    other = chalk.draw(_sheet(), marks, seed=8)
    assert not np.array_equal(layers[0], other[0])
    # The chalk shows the paper's tooth: grainy, not a solid line.
    on = layers[0][layers[0] > 0.05]
    assert np.std(on) > 0.1 and np.percentile(on, 10) < 0.6
    # A line that leads somewhere ends in a head; one that does not, none.
    plain = chalk.draw(_sheet(), [Stroke("line", [(0.05, 0.9), (0.95, 0.88)])], seed=7)[0]
    end = (slice(int(0.8 * H), H), slice(int(0.85 * W), W))
    assert (layers[3][end] > 0.3).sum() > (plain[end] > 0.3).sum() * 1.5


def test_the_rings_of_an_echo_are_round_and_joined_edge_to_edge() -> None:
    """21:17: "Zakreślenia powtórzeń - zawsze okrągłe"; 22:00: "połączyć
    linią (trochę cieńszą) koła powtórzeń … trzy - to robimy trójkąt"."""
    sheet = _sheet()
    # Two: one line between them.
    [two] = chalk.draw(sheet, [Stroke("echo", [(0.2, 0.3), (0.8, 0.3)])], seed=3)
    assert _at(two, 0.5, 0.3, 14) > 0.3  # the line
    assert _at(two, 0.2, 0.3, 4) < 0.2  # never through a ring's middle
    cx = round(0.2 * W)
    ys, xs = np.nonzero(two[:, : cx + 1] > 0.3)  # the left ring's left half (the line goes right)
    width, height = 2 * (cx - xs.min()), ys.max() - ys.min()
    assert 0.8 < width / height < 1.25  # round, not an ellipse
    # Three: a triangle.
    [three] = chalk.draw(sheet, [Stroke("echo", [(0.2, 0.3), (0.8, 0.3), (0.5, 0.75)])], seed=3)
    for x, y in ((0.5, 0.3), (0.35, 0.525), (0.65, 0.525)):
        assert _at(three, x, y, 16) > 0.3, (x, y)
    # Four: a quadrangle, its sides in turn round its middle, never across it.
    four_at = [(0.2, 0.3), (0.8, 0.3), (0.8, 0.75), (0.2, 0.75)]
    [four] = chalk.draw(sheet, [Stroke("echo", four_at)], seed=3)
    for x, y in ((0.5, 0.3), (0.8, 0.525), (0.5, 0.75), (0.2, 0.525)):
        assert _at(four, x, y, 16) > 0.3, (x, y)
    assert _at(four, 0.5, 0.525, 30) < 0.2  # no diagonal


def test_a_rhythm_is_drawn_along_its_elements_and_a_short_one_in_check_marks() -> None:
    """21:17: "Rytmy - zawsze trochę przeciągaj je dalej niż trzeba, a na
    końcu (nad/z prawej) dawaj znaczek ‚ptaszka’. Gdy rytm jest krótki -
    dawaj same ‚ptaszki’"."""
    sheet = _sheet()
    bands = [(0.2, 0.2), (0.6, 0.2), (0.2, 0.5), (0.6, 0.5), (0.2, 0.8), (0.6, 0.8)]
    [long] = chalk.draw(sheet, [Stroke("rhythm", bands)], seed=5)
    for y in (0.2, 0.5, 0.8):
        assert _at(long, 0.4, y, 8) > 0.3  # along each element
        assert _at(long, 0.625, y, 8) > 0.3  # drawn on past its end
        ys, xs = np.nonzero(long[int(y * H) - 60 : int(y * H) + 10, int(0.62 * W) :] > 0.3)
        assert xs.size and ys.min() < 50  # a check mark above its right end
    # Short: check marks alone, one on each element, nothing between them.
    ticks = [(0.2, 0.4), (0.2, 0.45), (0.4, 0.4), (0.4, 0.45), (0.6, 0.4), (0.6, 0.45)]
    assert np.median([0.05 * H]) < chalk.SHORT * W
    [short] = chalk.draw(sheet, [Stroke("rhythm", ticks)], seed=5)
    for x in (0.2, 0.4, 0.6):
        assert _at(short, x, 0.425, 30) > 0.3
    assert _at(short, 0.3, 0.425, 10) < 0.1 and _at(short, 0.5, 0.425, 10) < 0.1
    assert (short > 0.3).sum() < (long > 0.3).sum() / 2


def test_a_motion_is_one_smooth_arc_with_an_empty_head_and_two_echoes() -> None:
    """21:17: "Ruch - jak e … wzdłuż lini, po zewnętrznej łuku, w odsunięciu
    od grotu dwa, cieńsze echa … Strzałka ruchu zawsze musi być płynnym
    łukiem. Początek lini strzałki cieńszy, bliżej grotu grubszy"; 22:00:
    "Grot strzałki ruchu pusty w środku"."""
    [layer] = chalk.draw(_sheet(), [Stroke("motion", [(0.15, 0.5), (0.85, 0.5)])], seed=2)
    # A straight course is bent into an arc: its middle lies off the chord.
    column = layer[:, W // 2]
    ys = np.nonzero(column > 0.3)[0]
    assert ys.size and abs(ys.mean() / H - 0.5) > 0.05

    # Thin at its start, fuller near its head.
    def width_at(x: float) -> int:
        return int((layer[:, round(x * W)] > 0.3).sum())

    assert width_at(0.2) < width_at(0.7)
    # The head is drawn, its middle left bare.
    near = layer[:, round(0.8 * W) :]
    assert (near > 0.3).sum() > 100
    # Beside the arc, on its outer side, two thinner arcs: three strokes cross its middle.
    on = np.nonzero(column > 0.3)[0]
    assert (np.diff(on) > 8).sum() + 1 == 3


def test_an_echo_has_one_number_and_a_rhythm_two() -> None:
    """22:44: "skoro łączymy kółka powtórzeń, to nie dajemy na każdym
    numerka"; a rhythm keeps its number at its first and last element."""
    from frame_server.ai.daily import Mark, Spot, View
    from frame_server.ai.drawn import lines

    def at(*points: tuple[float, float]) -> list[Spot]:
        return [Spot(x=x, y=y) for x, y in points]

    view = View(
        title="t",
        text="",
        marks=[
            Mark(shape="echo", title="Czerwień", points=at((0.2, 0.3), (0.8, 0.3), (0.5, 0.75))),
            Mark(
                shape="rhythm",
                title="Pasy",
                points=at((0.1, 0.1), (0.1, 0.5), (0.3, 0.1), (0.3, 0.5), (0.9, 0.1), (0.9, 0.5)),
            ),
        ],
    )
    layers, colours, numbers = lines(_sheet().astype(np.float32) / 255, view, seed=4)
    assert len(layers) == 2 and len(set(colours)) == 2
    assert [len(spots) for spots in numbers] == [1, 2]
    for layer, spots in zip(layers, numbers, strict=True):  # each on its own line
        for x, y in spots:
            assert _at(layer, x, y, 8) > 0.3


def test_an_echo_rings_a_small_accent_snugly() -> None:
    """2026-11-23 00:13, Homer's „Jesień”: "Okręgi wokół rękawiczek są
    zdecydowanie zbyt duże": a ring as large as the patch of colour it rings."""
    img = Image.new("RGB", (W, H), (240, 234, 222))
    canvas = ImageDraw.Draw(img)
    canvas.rectangle((0.35 * W, 0.1 * H, 0.65 * W, 0.9 * H), fill=(40, 35, 35))  # a dark figure
    for x, y in ((0.45, 0.3), (0.55, 0.7)):  # two white gloves on it
        canvas.ellipse((x * W - 14, y * H - 20, x * W + 14, y * H + 20), fill=(250, 250, 250))
    [layer] = chalk.draw(np.asarray(img), [Stroke("echo", [(0.45, 0.3), (0.55, 0.7)])], seed=1)
    ys, xs = np.nonzero(layer[: H // 2] > 0.3)  # the upper ring, and the start of the line
    ring = (xs < 0.45 * W + 70) & (ys < 0.3 * H + 70)
    width = xs[ring].max() - xs[ring].min()
    assert 40 < width < chalk.RING[1] * W * 2 + 20  # round the glove, no farther
    assert _at(layer, 0.45, 0.3, 6) < 0.2  # the glove itself is left bare
