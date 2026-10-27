"""Colour analysis of library pictures: palette, colour tags, panel suitability."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ..imaging.color import linear_to_oklab, linear_to_u8, oklab_to_linear, u8_to_linear
from ..imaging.gamut import gamut_coverage
from ..imaging.layout import load_image
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
#: Version of the colour analysis and suitability score; items analysed by
#: an older one are analysed again (``Player.rescore``). 3: accents, ICC.
SCORE_VERSION = 3

#: Dominant colours closer than this (``_distance``) read as one.
MERGE = 0.06
#: Dominant colours shown, at most, and the least share of the picture.
MAX_DOMINANT = 4
MIN_DOMINANT = 0.04
#: A pixel is coloured enough to be part of an accent from this OKLab
#: chroma, chroma / lightness (dark reds) or a/b distance from the
#: picture's own cast (a greyish blue in a brown picture) on.
ACCENT_CHROMA = 0.035
ACCENT_SATURATION = 0.12
ACCENT_OFF_CAST = 0.05
#: Least share of the picture an accent covers.
ACCENT_AREA = 0.004
#: An accent's colour comes from its most colourful pixels: at most this
#: share of the picture.
ACCENT_VIVID = 0.04
#: An accent must be this many times as colourful as a dominant colour of
#: about its hue and lightness, or this much more chroma.
ACCENT_STRONGER = 1.6
ACCENT_BRIGHTER = 0.045
#: Accents closer than this (``_distance``, lightness halved) are one.
ACCENT_TWIN = 0.07
MAX_ACCENTS = 4
#: Hue sectors (OKLab hue, degrees) accents are looked for in.
ACCENT_SECTORS = (
    ("red", -30, 45),
    ("orange", 45, 75),
    ("yellow", 75, 120),
    ("green", 120, 175),
    ("teal", 175, 230),
    ("blue", 230, 290),
    ("purple", 290, 330),
)


def _sample(img: Image.Image, size: int = 64) -> np.ndarray:
    # load_image honours a colour profile: an Adobe RGB scan read as sRGB
    # looks muted (Matejko's Stańczyk loses his red).
    small = load_image(img).copy()
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
    """Dominant colours then accents, colour/mood tags and a 0..1 e-paper
    suitability score; ``spread`` is the picture's ``tint_spread`` if
    already known."""
    linear = _sample(img)
    lab = linear_to_oklab(linear)
    centres, weights = kmeans(lab, k=6)
    dominant = dominant_colours(centres, weights)
    accents = accent_colours(linear_to_oklab(_sample(img, 128)), dominant)
    swatches = [_swatch(c, w) for c, w in dominant]
    swatches += [_swatch(c, w, accent=True) for c, w, _ in accents]

    families: dict[str, float] = {}
    accents_named: set[str] = set()
    for centre, weight in zip(centres, weights, strict=True):
        name = family(centre)
        families[name] = families.get(name, 0.0) + float(weight)
        # A small but strongly coloured area (the blue in a Hokusai wave)
        # is what people remember a picture by.
        if weight >= 0.05 and float(np.hypot(centre[1], centre[2])) >= 0.06:
            accents_named.add(name)
    accents_named |= {name for _, _, name in accents}
    tags = [n for n in COLOR_FAMILIES if families.get(n, 0.0) >= 0.12 or n in accents_named]

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


def _swatch(lab: np.ndarray, weight: float, accent: bool = False) -> ColorSwatch:
    rgb = linear_to_u8(np.clip(oklab_to_linear(lab), 0, 1))
    return ColorSwatch(
        hex="#{:02x}{:02x}{:02x}".format(*rgb), weight=round(float(weight), 3), accent=accent
    )


def _distance(p: np.ndarray, q: np.ndarray, light: float = 1.0) -> float:
    """OKLab distance with colour (a, b) counted twice: two dark tones of
    different hue (a red skirt, a brown jug) differ more to the eye than to
    plain ΔE. ``light`` < 1 weighs lightness less."""
    d = p - q
    return float(np.sqrt((light * d[0]) ** 2 + 4 * (d[1] ** 2 + d[2] ** 2)))


def _hue(lab: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360


def dominant_colours(centres: np.ndarray, weights: np.ndarray) -> list[tuple[np.ndarray, float]]:
    """The k-means colours, largest first, with near-identical ones (three
    beiges of an old wall) merged, at most ``MAX_DOMINANT``."""
    merged: list[tuple[np.ndarray, float]] = []
    for idx in np.argsort(-weights):
        centre, weight = centres[idx], float(weights[idx])
        for j, (other, share) in enumerate(merged):
            if _distance(centre, other) < MERGE:
                merged[j] = ((other * share + centre * weight) / (share + weight), share + weight)
                break
        else:
            merged.append((centre.copy(), weight))
    merged.sort(key=lambda m: -m[1])
    return [m for m in merged if m[1] >= MIN_DOMINANT][:MAX_DOMINANT]


def accent_colours(
    lab: np.ndarray, dominant: list[tuple[np.ndarray, float]]
) -> list[tuple[np.ndarray, float, str]]:
    """Small, vivid colours the dominant ones do not show: the blue apron,
    yellow bodice and red skirt of Vermeer's Milkmaid, though each covers a
    few percent. One per hue sector at most, in the colour of its most
    vivid pixels rather than an average with its shadows; (colour, share of
    the picture that looks like it, colour family), largest first."""
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = _hue(lab)
    # Coloured beyond the picture's own: in a vivid Van Gogh only the
    # strongest colours count, in a varnished Vermeer much less does.
    saturation = chroma / np.maximum(lab[:, 0], 0.25)
    cast = np.median(lab[:, 1:], 0)
    off_cast = np.hypot(lab[:, 1] - cast[0], lab[:, 2] - cast[1])
    coloured = (
        (chroma >= max(ACCENT_CHROMA, 1.3 * float(np.median(chroma))))
        | (saturation >= max(ACCENT_SATURATION, 1.3 * float(np.median(saturation))))
    ) & (chroma >= 0.03)
    coloured |= (off_cast >= max(ACCENT_OFF_CAST, 2.5 * float(np.median(off_cast)))) & (
        chroma >= 0.025
    )
    shown_chroma = np.array([float(np.hypot(c[1], c[2])) for c, _ in dominant])
    shown_hue = np.array([float(_hue(c)) for c, _ in dominant])
    shown_light = np.array([float(c[0]) for c, _ in dominant])
    n = len(lab)
    found: list[tuple[np.ndarray, float, str, float]] = []
    for name, start, end in ACCENT_SECTORS:
        member = coloured & ((hue - start) % 360 < end - start)
        count = int(member.sum())
        if count < ACCENT_AREA * n:
            continue
        # Its most colourful pixels: Stańczyk's red costume, not his
        # red-brown room.
        top = max(1, min(int(0.3 * count), int(ACCENT_VIVID * n)))
        centre = lab[member][np.argsort(-chroma[member])[:top]].mean(0)
        vivid = float(np.hypot(centre[1], centre[2]))
        if vivid < 0.05 and float(np.hypot(*(centre[1:] - cast))) < ACCENT_OFF_CAST:
            continue
        # A dominant colour of about its hue and lightness may show it
        # already, unless the accent is much more vivid (a gold sleeve is
        # no mid brown).
        gap = np.abs((shown_hue - float(_hue(centre)) + 180) % 360 - 180)
        near = (gap < 20) & (np.abs(shown_light - centre[0]) < 0.15) & (shown_chroma >= 0.03)
        shown = float(shown_chroma[near].max()) if near.any() else 0.0
        if vivid < ACCENT_STRONGER * shown and vivid - shown < ACCENT_BRIGHTER:
            continue
        # Its share: the coloured pixels that look like it.
        diff = lab - centre
        alike = np.sqrt(0.25 * diff[:, 0] ** 2 + 4 * (diff[:, 1] ** 2 + diff[:, 2] ** 2))
        share = float((coloured & (alike < ACCENT_TWIN)).mean())
        if share < ACCENT_AREA:
            continue
        if name == "orange" and centre[0] < 0.6:
            name = "brown"
        elif name == "red" and centre[0] > 0.65:
            name = "pink"
        found.append((centre, share, name, np.sqrt(share) * vivid))
    found.sort(key=lambda f: -f[3])
    accents: list[tuple[np.ndarray, float, str]] = []
    for centre, share, name, _ in found:
        # Neighbouring sectors of one look (a face's red and orange).
        twin = next(
            (i for i, a in enumerate(accents) if _distance(centre, a[0], 0.5) < ACCENT_TWIN), None
        )
        if twin is not None:
            accents[twin] = (accents[twin][0], accents[twin][1] + share, accents[twin][2])
        elif len(accents) < MAX_ACCENTS:
            accents.append((centre, share, name))
    return sorted(accents, key=lambda a: -a[1])


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
