from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from frame_server.library import colors, tonal


def _picture() -> Image.Image:
    """A dark brown ground, an ochre middle, a cream-white robe, a small
    red cloak and a dark green shutter (Mateusz 2026-11-21: Czechowicz's
    white, Vermeer's shutters)."""
    img = Image.new("RGB", (256, 256), (58, 40, 24))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 150, 255, 255), fill=(150, 112, 60))
    d.rectangle((100, 40, 140, 140), fill=(238, 230, 205))
    d.rectangle((20, 160, 36, 190), fill=(190, 40, 30))
    d.rectangle((200, 30, 230, 80), fill=(34, 52, 30))
    return img


def test_a_painting_with_no_medium_is_told_by_its_type() -> None:
    assert colors.painting("", "Painting") and colors.painting("", "")
    assert not colors.painting("", "Drawing") and not colors.painting("", "Dessin, Arts graphiques")
    assert not colors.painting("", "Prints and Drawings") and not colors.painting("", "Poster")
    # The medium says first.
    assert colors.painting("oil on canvas", "Drawings")


def test_a_paintings_bar_is_its_masses_and_its_accents_in_their_places() -> None:
    img = _picture()
    grid = colors.linear_to_oklab(colors._grid(img, 128))
    bar = tonal.bar(grid)
    mains = [s for s in bar if not s.accent]
    accents = [s for s in bar if s.accent]
    # Masses from the darkest, each a band.
    lights = [float(colors._lab(s.hex)[0]) for s in mains]
    assert lights == sorted(lights) and all(s.weight >= tonal.BAND for s in mains)
    assert len(mains) <= tonal.MAX_MASSES and len(accents) <= tonal.MAX_ACCENTS
    # Each accent has its place and its amount, in order along the bar.
    places = [s.at for s in accents]
    assert all(p is not None and 0 <= p <= 1 for p in places)
    assert places == sorted(places)
    assert all(s.amount is not None and s.amount > 0 for s in accents)
    labs = [colors._lab(s.hex) for s in accents]
    hues = [float(np.degrees(np.arctan2(c[2], c[1])) % 360) for c in labs]
    chromas = [float(np.hypot(c[1], c[2])) for c in labs]
    # The red, the white and the green are there; the green lifted from its dark.
    assert any((h < 45 or h > 330) and ch > 0.1 for h, ch in zip(hues, chromas, strict=True))
    assert any(c[0] > 0.85 and ch < 0.05 for c, ch in zip(labs, chromas, strict=True))
    green = [c for c, h in zip(labs, hues, strict=True) if 100 <= h < 170]
    assert green and green[0][0] > float(colors._lab("#22341e")[0]) + 0.05


def test_analyse_paints_a_paintings_bar_only() -> None:
    img = _picture()
    painted = colors.analyse(img, medium="", classification="Painting")
    assert any(s.at is not None for s in painted.swatches)
    drawn = colors.analyse(img, medium="", classification="Drawing")
    assert all(s.at is None for s in drawn.swatches)
    # What the bar shows the picture is found by.
    assert colors.ACCENT_TAG + "red" in painted.tags or "red" in painted.tags


def test_one_colour_is_one_accent() -> None:
    a, b = np.array([0.6, 0.1, 0.12]), np.array([0.65, 0.105, 0.125])
    assert tonal._hue_apart(a, b) < tonal.ONE_HUE and abs(a[0] - b[0]) < tonal.ONE_LIGHT
