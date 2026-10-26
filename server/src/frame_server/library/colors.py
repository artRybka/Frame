"""Colour analysis of library pictures: palette, colour tags, panel suitability."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ..imaging.color import linear_to_oklab, linear_to_u8, oklab_to_linear, u8_to_linear
from ..imaging.gamut import gamut_coverage
from ..imaging.palette import EM32DX, Palette
from .models import ColorSwatch

# Colour families used for tags and smart playlists. The app shows them
# with Polish names; keep the keys stable.
COLOR_FAMILIES = (
    "red",
    "orange",
    "yellow",
    "green",
    "teal",
    "blue",
    "purple",
    "pink",
    "brown",
    "black",
    "gray",
    "white",
)
MOODS = ("warm", "cool", "vivid", "muted", "monochrome", "dark", "light")
#: OKLab chroma of the strongest tint that still reads as aged paper or a
#: sepia print rather than as colour.
PAPER_TINT = 0.07
#: Tint spread (see ``tint_spread``) from no colour of its own to plainly
#: several colours, for the suitability score.
COLOUR_SPREAD = (0.01, 0.035)
#: OKLab chroma of a picture's most colourful tenth that counts as fully colourful.
COLOUR_CHROMA = 0.08
#: Version of the suitability score; items scored by an older one are scored
#: again (``Player.rescore``).
SCORE_VERSION = 2


def _sample(img: Image.Image, size: int = 64) -> np.ndarray:
    small = img.convert("RGB").copy()
    small.thumbnail((size, size), Image.Resampling.BILINEAR)
    return u8_to_linear(np.asarray(small)).reshape(-1, 3)


def kmeans(points: np.ndarray, k: int, iterations: int = 15) -> tuple[np.ndarray, np.ndarray]:
    """Small deterministic k-means; returns (centres, weights)."""
    order = np.argsort(points[:, 0])
    centres = points[order[np.linspace(0, len(points) - 1, k).astype(int)]].copy()
    labels = np.zeros(len(points), dtype=int)
    for _ in range(iterations):
        dist = ((points[:, None, :] - centres[None, :, :]) ** 2).sum(-1)
        labels = dist.argmin(1)
        for c in range(k):
            members = points[labels == c]
            if len(members):
                centres[c] = members.mean(0)
    weights = np.bincount(labels, minlength=k) / len(points)
    return centres, weights


def family(lab: np.ndarray) -> str:
    light, a, b = (float(v) for v in lab)
    chroma = float(np.hypot(a, b))
    hue = float(np.degrees(np.arctan2(b, a)) % 360)
    if 15 <= hue < 110 and 0.03 <= chroma < 0.13 and light < 0.6:
        return "brown"
    if chroma < 0.025 + 0.035 * light:
        # Aged paper and greyish tints count as neutrals, not as colours;
        # dark colours carry less chroma, so the bar is lower for them.
        if light > 0.82:
            return "white"
        if light < 0.3:
            return "black"
        return "gray"
    if hue >= 330 or hue < 15:
        return "pink" if light > 0.65 else "red"
    if hue < 45:
        return "red"
    if hue < 80:
        return "orange"
    if hue < 120:
        return "yellow"
    if hue < 175:
        return "green"
    if hue < 230:
        return "teal"
    if hue < 290:
        return "blue"
    return "purple"


def colourfulness(lab: np.ndarray, spread: float) -> float:
    """0..1: how much colour of its own a picture has. Both its tint spread
    (more than one hue, not sepia on old paper) and its chroma count: a
    yellowed etching and a grey photo score 0, Van Gogh 1."""
    low, high = COLOUR_SPREAD
    hues = min(1.0, max(0.0, (spread - low) / (high - low)))
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    strength = min(1.0, float(np.percentile(chroma, 90)) / COLOUR_CHROMA)
    return float(np.sqrt(hues * strength))


def suitability(
    linear: np.ndarray, lab: np.ndarray, spread: float, palette: Palette = EM32DX
) -> float:
    """0..1: how good a picture looks on the panel. Its six inks make colour
    shine: colourful works lead, drawings, etchings and B&W photos stay at
    0.5 at most (they look fine, only plainer). Contrast and a mid-light
    picture help, dark ones turn muddy; gamut coverage counts a little, as
    gamut mapping handles colours beyond the inks well."""
    light = lab[:, 0]
    coverage = gamut_coverage(linear.reshape(1, -1, 3), palette)
    contrast = min(1.0, float(light.std()) / 0.2)
    brightness = 1.0 - min(1.0, abs(float(light.mean()) - 0.65) / 0.45)
    colour = colourfulness(lab, spread)
    return round(0.5 * colour + 0.2 * contrast + 0.2 * brightness + 0.1 * coverage, 3)


def score(img: Image.Image, palette: Palette = EM32DX, spread: float | None = None) -> float:
    """The suitability score alone, for pictures already analysed."""
    linear = _sample(img)
    if spread is None:
        spread = tint_spread(img)
    return suitability(linear, linear_to_oklab(linear), spread, palette)


def analyse(
    img: Image.Image, palette: Palette = EM32DX, spread: float | None = None
) -> tuple[list[ColorSwatch], list[str], float]:
    """Dominant colours, colour/mood tags and a 0..1 e-paper suitability
    score; ``spread`` is the picture's ``tint_spread`` if already known."""
    linear = _sample(img)
    lab = linear_to_oklab(linear)
    centres, weights = kmeans(lab, k=6)
    order = np.argsort(-weights)
    swatches = []
    for idx in order:
        if weights[idx] < 0.02:
            continue
        rgb = linear_to_u8(np.clip(oklab_to_linear(centres[idx]), 0, 1))
        swatches.append(
            ColorSwatch(
                hex="#{:02x}{:02x}{:02x}".format(*rgb), weight=round(float(weights[idx]), 3)
            )
        )

    families: dict[str, float] = {}
    accents: set[str] = set()
    for centre, weight in zip(centres, weights, strict=True):
        name = family(centre)
        families[name] = families.get(name, 0.0) + float(weight)
        # A small but strongly coloured area (the blue in a Hokusai wave)
        # is what people remember a picture by.
        if weight >= 0.05 and float(np.hypot(centre[1], centre[2])) >= 0.06:
            accents.add(name)
    tags = [n for n in COLOR_FAMILIES if families.get(n, 0.0) >= 0.12 or n in accents]

    light = lab[:, 0]
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360
    coloured = chroma > 0.04
    warm = float(chroma[coloured & ((hue < 110) | (hue > 330))].sum())
    cool = float(chroma[coloured & (hue >= 150) & (hue <= 300)].sum())
    mean_chroma = float(chroma.mean())
    if mean_chroma < 0.03:
        tags.append("monochrome")
    elif mean_chroma > 0.1:
        tags.append("vivid")
    elif mean_chroma < 0.05:
        tags.append("muted")
    if warm > 1.5 * cool and mean_chroma >= 0.03:
        tags.append("warm")
    elif cool > 1.5 * warm and mean_chroma >= 0.03:
        tags.append("cool")
    mean_light = float(light.mean())
    if mean_light < 0.45:
        tags.append("dark")
    elif mean_light > 0.8:
        tags.append("light")

    if spread is None:
        spread = tint_spread(img)
    return swatches, tags, suitability(linear, lab, spread, palette)


def tint_spread(img: Image.Image) -> float:
    """How far the colours stray from a faint single tint (OKLab chroma, 95th
    percentile): ~0 for drawings, etchings, black-and-white and sepia photos,
    however yellowed the paper; above ~0.014 once there is any real colour.

    Toned monochrome lies on one line through the grey axis in the a/b
    plane. Distance from that line, colour on the far side of grey (blue
    sky against orange sand) and a tint stronger than old paper's (a
    cyanotype, red chalk) all count."""
    ab = linear_to_oklab(_sample(img, 128))[:, 1:]
    _, vectors = np.linalg.eigh(ab.T @ ab)
    axis = vectors[:, -1]
    along = ab @ axis
    if along.mean() < 0:
        along = -along
    across = np.abs(ab @ np.array([-axis[1], axis[0]]))
    beyond = np.maximum(np.maximum(-along, along - PAPER_TINT), 0.0)
    return round(float(np.percentile(np.maximum(across, beyond), 95)), 4)
