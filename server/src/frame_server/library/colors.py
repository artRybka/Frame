"""Colour analysis of library pictures: palette, colour tags, colour shares."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np
from PIL import Image

from ..imaging.color import linear_to_oklab, linear_to_u8, oklab_to_linear, u8_to_linear
from ..imaging.layout import load_image
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
MOODS = ("warm", "cool", "vivid", "muted", "colorful", "monochrome", "dark", "light")
#: OKLab chroma of the strongest tint that still reads as aged paper or a
#: sepia print rather than as colour.
PAPER_TINT = 0.07
#: Tint spread (see ``tint_spread``) from no colour of its own to plainly
#: several colours.
COLOUR_SPREAD = (0.01, 0.035)
#: Version of the colour analysis; items analysed by
#: an older one are analysed again (``Player.rescore``). 3: accents, ICC;
#: 4: colour tags by area, accents tagged apart; 5: "colorful"; 6: "only:";
#: 7: each family's share (``Item.color_shares``), "monochrome" by hue;
#: 8: "monochrome" seen against its paper (``toned``); 9: Tonacja sides
#: (``"tone:neutral"``, ``tone_sides``); 10: without a museum's blank
#: margins (``imaging.margins``), which counted as white; 11: small
#: striking patches among the swatches and the accent tags (``touches``);
#: 12: a white that stands out among the swatches (``lights``).
SCORE_VERSION = 12

#: A pixel counts towards a colour family from this OKLab chroma on, or
#: this chroma / lightness for light ones: a greyish-blue sky does, a beige
#: wall or the greys of a picture don't.
TINTED = 0.02
TINTED_LIGHT = 0.04
#: Least share of the picture a colour family covers to be part of its
#: colouring (tag ``"blue"``: "W odcieniach błękitu"); less is an accent at most.
COLOURING = 0.15
#: Tags of colours that are only accents of a picture (``"accent:blue"``),
#: never with the colour's own tag.
ACCENT_TAG = "accent:"
NEUTRALS = ("black", "gray", "white")
#: Tags of the colours a picture is painted in (``"only:blue"``): the
#: fewest colour families, largest first, that make ``ONLY_SHARE`` of its
#: coloured pixels (neutrals aside). Never shown; a search for "Dominuje:
#: błękit i turkus" finds pictures whose such tags are all among those.
ONLY_TAG = "only:"
ONLY_SHARE = 0.8
WARM_FAMILIES = ("red", "orange", "yellow", "brown", "pink")
COOL_FAMILIES = ("green", "teal", "blue", "purple")
#: A warm (cool) picture: its warm (cool) tones cover this much of it, the
#: other side at most half as much, and of those tones at least ``TONE_VIVID``
#: of the picture is a real colour (chroma ``VIVID_CHROMA``), no warm grey.
TONE_AREA = 0.4
TONE_VIVID = 0.1
VIVID_CHROMA = 0.05

#: A colourful picture ("colorful": no black-and-white, monochrome or
#: two-tone work) shows colour, from ``HUE_CHROMA`` on, on at least
#: ``COLOURFUL_HUES`` of these wide hue sectors (OKLab hue, degrees), each on
#: ``HUE_AREA`` of it at least, an accent's size: a Madonna's red and blue in
#: a gold altarpiece will do, red chalk or a blue-and-brown print won't.
HUE_SECTORS = (
    ("red", -30, 45),
    ("yellow", 45, 110),
    ("green", 110, 175),
    ("blue", 175, 290),
    ("purple", 290, 330),
)
HUE_CHROMA = 0.03
HUE_AREA = 0.005
COLOURFUL_HUES = 3

#: A monochrome picture (black and white, sepia, a cyanotype, red chalk,
#: grisaille) has its tinted pixels (``MONO_CHROMA`` on) of one hue: their
#: spread around it, weighted by chroma squared, at most ``MONO_SPREAD``
#: degrees; nothing vivid (``MONO_VIVID`` of it at chroma ``MONO_VIVID_CHROMA``)
#: and no accent of another hue (``MONO_ACCENT_HUE`` degrees away). Tried
#: on 409 Cleveland works: almost all old photographs, etchings, chalk and
#: ink drawings, and two thirds of cyanotypes; brown old-master portraits
#: are close to it and a fifth of the paintings still count.
MONO_CHROMA = 0.025
MONO_SPREAD = 12.0
MONO_VIVID = 0.01
MONO_VIVID_CHROMA = 0.1
MONO_ACCENT_HUE = 40.0

#: A monochrome picture's colours seen as the eye sees them, against its
#: paper (the median tint of its lightest ``PAPER_LIGHTEST`` share, taken
#: away in proportion to lightness): a faded woodblock print's pinks and
#: blue-greys stand out from its yellowed paper, though all of them are
#: faint and warm. Of the pixels that then show a tint (``TONED_CHROMA``)
#: it is one of: a duotone, ``TONED_LINE`` of them on one line through the
#: paper within ``TONED_LINE_DEGREES``; one tone, ``TONED_HUE`` of them
#: within ``TONED_HUE_DEGREES``; or colour that goes with lightness alone,
#: as in an old photograph's warm lights and purple darks: at most
#: ``TONED_ASTRAY`` of the picture is ``TONED_CHROMA`` away from the median
#: colour of its lightness band (``TONED_BAND`` wide). Tried on 308 Cleveland
#: works the rule before took for monochrome: 34 of 43 coloured ones (Japanese
#: prints, portraits, watercolours) went, 1 stayed; of 265 monochrome ones
#: 204 stayed, those gone mostly old photographs toned unevenly on their mount.
PAPER_LIGHTEST = 0.4
TONED_CHROMA = 0.015
TONED_LINE = 0.9
TONED_LINE_DEGREES = 20.0
TONED_HUE = 0.95
TONED_HUE_DEGREES = 45.0
TONED_ASTRAY = 0.02
TONED_BAND = 0.08

#: How much of a picture a colour covers, in four levels the Kolor sheet
#: offers (``"blue@much"``): an accent (a small, vivid part: an accent
#: tag, at most ``LEVEL_ACCENT`` of the picture), clear, much, and most.
#: Clear and much are bands of the picture's area, overlapping a little as
#: the analysis only estimates; "most" is the share of the picture's
#: colours (white, grey and black aside) and several colours asked at it
#: share it: blue and teal "most" are pictures painted mostly in the two.
LEVELS = ("accent", "clear", "much", "most")
LEVEL_MARK = "@"
LEVEL_ACCENT = 0.1
LEVEL_CLEAR = (0.08, 0.33)
LEVEL_MUCH = (0.28, 0.62)
LEVEL_MOST = 0.6
#: Each colour asked at "most" covers this much of the picture's colours,
#: and together they this much of the picture (no grey drawing with a touch
#: of blue is "mostly blue").
LEVEL_MOST_EACH = 0.1
LEVEL_MOST_AREA = 0.12
#: Moods asked from the Tonacja card (``"tone:warm"``): every one must fit.
TONE_TAG = "tone:"
#: The Tonacja card's groups: each picture is on exactly one side of each
#: (Mateusz 2026-11-05: Kolorowe and Mono together are the whole library,
#: likewise the others, with a middle where the ends are not the whole of
#: it). Stored as ``"tone:<side>"`` tags; the plain moods above stay as
#: they were for playlists and colour cards, which want the plain cases.
TONE_GROUPS = (
    ("warm", "neutral", "cool"),
    ("vivid", "moderate", "muted"),
    ("colorful", "monochrome"),
    ("dark", "medium", "light"),
)
#: Temperatura: the picture's colour along the warm (orange, OKLab hue
#: ``TONE_WARM_HUE``) to cool axis, chroma-weighted mean; warm from
#: ``TONE_WARM``, cool below ``TONE_COOL`` (a little below zero: plain
#: grey is neutral). Old art is mostly warm: of 490 Cleveland works 51%
#: warm, 45% neutral, 4% cool.
TONE_WARM_HUE = 60.0
TONE_WARM = 0.025
TONE_COOL = -0.002
#: Nasycenie: the chroma of the picture's most colourful tenth; vivid from
#: ``TONE_VIVID_CHROMA``, muted below ``TONE_MUTED_CHROMA`` (16% / 52% /
#: 33% of the Cleveland works).
TONE_VIVID_CHROMA = 0.065
TONE_MUTED_CHROMA = 0.035
#: Jasność: mean lightness; dark below ``TONE_DARK``, light from
#: ``TONE_LIGHT`` (20% / 59% / 21%).
TONE_DARK = 0.53
TONE_LIGHT = 0.72

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
#: A touch: a patch too small for an accent whose colour stands out all the
#: same (the one red shutter of Vermeer's Little Street, the sun of Monet's
#: Impression). Looked for in a finer sample (``TOUCH_SAMPLE`` pixels a
#: side); its colour comes from the hue's most colourful pixels, this share
#: of the picture at most; it covers this share at least, and is this many
#: times as colourful as every colour of about its hue the palette shows
#: already, and this much more chroma. However much of the picture looks
#: like it, it is shown as a touch (``TOUCH_WEIGHT``).
TOUCH_SAMPLE = 192
TOUCH_VIVID = 0.001
TOUCH_AREA = 0.0004
TOUCH_STRONGER = 1.5
TOUCH_BRIGHTER = 0.05
TOUCH_WEIGHT = 0.02
MAX_TOUCHES = 2
#: A white that stands out (Mateusz 2026-11-12 11:38, of the foam of
#: Turner's dark sea, whose bar had browns and greys only: „biały jest
#: wyraźnie wybijającym się akcentem to trzeba go uwzględnić”). The other
#: accents are looked for by their colour, and white has none. It is the
#: picture's lightest ``LIGHT_TOP``: white (``LIGHT_WHITE`` light at least,
#: ``LIGHT_CHROMA`` at most), lighter than every colour shown by
#: ``LIGHT_ABOVE`` and than the picture's middle tone by ``LIGHT_OVER``
#: (the paper of a print, the mist of a pale landscape do not stand out),
#: and ``LIGHT_AREA`` of the picture is about as light. Shown as an
#: accent, ``LIGHT_WEIGHT`` at most.
LIGHT_TOP = 0.02
LIGHT_WHITE = 0.8
LIGHT_CHROMA = 0.05
LIGHT_ABOVE = 0.12
LIGHT_OVER = 0.3
LIGHT_NEAR = 0.08
LIGHT_AREA = 0.01
LIGHT_WEIGHT = 0.06
#: Colours of a picture, at most: what the app's painted bar lays down.
MAX_SWATCHES = 8
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


class Analysis(NamedTuple):
    """What ``analyse`` finds in a picture."""

    swatches: list[ColorSwatch]
    tags: list[str]
    #: Each colour family's share of the picture (``color_shares``).
    shares: dict[str, float]


def analyse(img: Image.Image, spread: float | None = None) -> Analysis:
    """Dominant colours, then accents, then the small striking patches
    (``touches``); colour/mood tags and the colour families' shares;
    ``spread`` is the picture's ``tint_spread`` if already known."""
    if spread is None:
        spread = tint_spread(img)
    linear = _sample(img)
    lab = linear_to_oklab(linear)
    fine = linear_to_oklab(_sample(img, 128))
    centres, weights = kmeans(lab, k=6)
    dominant = dominant_colours(centres, weights)
    accents = accent_colours(fine, dominant)
    small = touches(linear_to_oklab(_sample(img, TOUCH_SAMPLE)), dominant, accents)
    tags = colour_tags(fine, spread, dominant, accents, small)
    # One tint and a collector's stamp is one tint still: no touches there,
    # and its paper is no accent.
    if "monochrome" in tags:
        small = []
    shown = [c for c, _ in dominant] + [c for c, _, _ in accents] + [c for c, _, _ in small]
    white = [] if "monochrome" in tags else lights(fine, shown)
    swatches = [_swatch(c, w) for c, w in dominant]
    # A touch is what the eye goes to: it is shown before the least accent.
    room = MAX_SWATCHES - len(swatches) - len(small) - len(white)
    swatches += [_swatch(c, w, accent=True) for c, w, _ in accents[: max(room, 0)]]
    swatches += [_swatch(c, w, accent=True) for c, w, _ in small]
    swatches += [_swatch(c, w, accent=True) for c, w in white]
    return Analysis(swatches, tags, colour_shares(fine, spread))


def colour_shares(lab: np.ndarray, spread: float) -> dict[str, float]:
    """Each colour family's share of the picture (``pixel_families``), the
    ones it has, to three places."""
    names = pixel_families(lab, spread)
    shares = {n: round(float((names == n).mean()), 3) for n in COLOR_FAMILIES}
    return {n: v for n, v in shares.items() if v > 0}


def pixel_families(lab: np.ndarray, spread: float) -> np.ndarray:
    """Each pixel's colour family, as ``family`` names them but with a lower
    bar for colour (a pale blue sky is blue, not grey); a picture with no
    colour of its own (``spread``: ink on yellowed paper) is all neutrals."""
    light = lab[:, 0]
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = _hue(lab)
    names = np.where(light > 0.82, "white", np.where(light < 0.3, "black", "gray")).astype("<U6")
    if spread < COLOUR_SPREAD[0]:
        return names
    tinted = chroma >= np.maximum(TINTED, TINTED_LIGHT * light)
    sectors = (
        ("red", (hue >= 330) | (hue < 45)),
        ("pink", ((hue >= 330) | (hue < 15)) & (light > 0.65)),
        ("orange", (hue >= 45) & (hue < 80)),
        ("yellow", (hue >= 80) & (hue < 120)),
        ("green", (hue >= 120) & (hue < 175)),
        ("teal", (hue >= 175) & (hue < 230)),
        ("blue", (hue >= 230) & (hue < 290)),
        ("purple", (hue >= 290) & (hue < 330)),
        ("brown", (hue >= 15) & (hue < 110) & (chroma < 0.13) & (light < 0.6)),
    )
    for name, sector in sectors:
        names[tinted & sector] = name
    return names


def colour_tags(
    lab: np.ndarray,
    spread: float,
    dominant: list[tuple[np.ndarray, float]],
    accents: list[tuple[np.ndarray, float, str]],
    small: Sequence[tuple[np.ndarray, float, str]] = (),
) -> list[str]:
    """Colour and mood tags. A colour family is a tag when it covers
    ``COLOURING`` of the picture: a Madonna's blue robe in a gold altarpiece
    is not "in shades of blue". Smaller colours the palette shows (accents,
    small dominant ones, and the ``small`` striking patches, ``touches``:
    the Little Street is found by its red shutter, Mateusz 2026-11-11 21:50)
    are ``ACCENT_TAG`` tags; warm and cool go by area too, so one vivid red
    robe does not make a grey sky warm. A picture of one tint stays one
    (``single_tone`` does not look at ``small``) and has no touch for an
    accent: a stamp on an etching is not what it is looked for by."""
    names = pixel_families(lab, spread)
    share = {n: float((names == n).mean()) for n in COLOR_FAMILIES}
    tags = [n for n in COLOR_FAMILIES if share[n] >= COLOURING]
    shown = {name for _, _, name in accents} | {family(c) for c, _ in dominant}
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    mean_chroma = float(chroma.mean())
    # Several hues, however muted (El Greco), are never monochrome.
    in_colours = colourful(lab, spread)
    monochrome = not in_colours and single_tone(lab, spread, accents)
    if not monochrome:
        shown |= {name for _, _, name in small}
    tags += [
        ACCENT_TAG + n for n in COLOR_FAMILIES if n in shown and n not in tags and n not in NEUTRALS
    ]
    tags += [ONLY_TAG + n for n in painted_in(share)]

    if in_colours:
        tags.append("colorful")
    if monochrome:
        tags.append("monochrome")
    elif mean_chroma > 0.1:
        tags.append("vivid")
    elif mean_chroma < 0.05:
        tags.append("muted")
    warm, cool = (sum(share[n] for n in side) for side in (WARM_FAMILIES, COOL_FAMILIES))
    vivid = chroma >= VIVID_CHROMA
    for mood, side, other, families in (
        ("warm", warm, cool, WARM_FAMILIES),
        ("cool", cool, warm, COOL_FAMILIES),
    ):
        if (
            side >= TONE_AREA
            and other <= side / 2
            and float((vivid & np.isin(names, families)).mean()) >= TONE_VIVID
        ):
            tags.append(mood)
    mean_light = float(lab[:, 0].mean())
    if mean_light < 0.45:
        tags.append("dark")
    elif mean_light > 0.8:
        tags.append("light")
    return tags + [TONE_TAG + side for side in tone_sides(lab, "monochrome" in tags)]


def tone_sides(lab: np.ndarray, monochrome: bool) -> list[str]:
    """The picture's side of each Tonacja group (``TONE_GROUPS``), one each."""
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = np.arctan2(lab[:, 2], lab[:, 1])
    warmth = float((chroma * np.cos(hue - np.radians(TONE_WARM_HUE))).mean())
    vivid = float(np.percentile(chroma, 90))
    light = float(lab[:, 0].mean())
    return [
        "warm" if warmth >= TONE_WARM else "cool" if warmth < TONE_COOL else "neutral",
        "vivid"
        if vivid >= TONE_VIVID_CHROMA
        else "muted"
        if vivid < TONE_MUTED_CHROMA
        else "moderate",
        "monochrome" if monochrome else "colorful",
        "dark" if light < TONE_DARK else "light" if light >= TONE_LIGHT else "medium",
    ]


def painted_in(share: dict[str, float]) -> list[str]:
    """The colour families a picture is painted in, from each one's share
    of it: the fewest, largest first, that make ``ONLY_SHARE`` of its
    coloured pixels. A blue Whistler nocturne is blue alone, Monet's sea at
    Pourville blue and turquoise; a picture without colour, none."""
    colours = sorted(
        ((v, n) for n, v in share.items() if n not in NEUTRALS and v > 0), reverse=True
    )
    total = sum(v for v, _ in colours)
    found: list[str] = []
    held = 0.0
    for value, name in colours:
        if total <= 0 or held >= ONLY_SHARE * total:
            break
        found.append(name)
        held += value
    return found


def single_tone(
    lab: np.ndarray, spread: float, accents: Sequence[tuple[np.ndarray, float, str]] = ()
) -> bool:
    """Whether a picture is monochrome: greys alone, or one tint (sepia, a
    cyanotype, red chalk, grisaille), see ``MONO_SPREAD``. Old photographs
    tint their lights and darks a little apart, so the spread is weighted
    by chroma: their faint greys count for little. Faint colours on
    yellowed paper hide in that, so the colours are looked at against the
    paper too (``toned``)."""
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    if float((chroma >= MONO_VIVID_CHROMA).mean()) >= MONO_VIVID:
        return False
    tinted = chroma >= MONO_CHROMA
    if spread < COLOUR_SPREAD[0] or tinted.mean() < 0.01:
        return toned(lab)
    hue = np.radians(_hue(lab[tinted]))
    weight = chroma[tinted] ** 2
    centre = np.arctan2((weight * np.sin(hue)).sum(), (weight * np.cos(hue)).sum())
    off = np.degrees((hue - centre + np.pi) % (2 * np.pi) - np.pi)
    if float(np.sqrt((weight * off**2).sum() / weight.sum())) > MONO_SPREAD:
        return False
    centre_deg = float(np.degrees(centre)) % 360
    return toned(lab) and all(
        abs((float(_hue(c)) - centre_deg + 180) % 360 - 180) <= MONO_ACCENT_HUE
        for c, _, _ in accents
    )


def toned(lab: np.ndarray) -> bool:
    """Whether a picture's colours, seen against its paper, are one tone, a
    duotone or a tone that follows lightness (see ``PAPER_LIGHTEST``)."""
    light = lab[:, 0]
    ab = lab[:, 1:]
    lightest = light >= np.percentile(light, 100 * (1 - PAPER_LIGHTEST))
    paper = np.median(ab[lightest], axis=0)
    seen = ab - np.outer(np.clip(light / light[lightest].mean(), 0, 1), paper)
    tinted = np.hypot(seen[:, 0], seen[:, 1]) >= TONED_CHROMA
    if tinted.mean() < 0.01:
        return True
    hue = np.degrees(np.arctan2(seen[tinted, 1], seen[tinted, 0]))
    if (
        _arc(hue % 180, 180, TONED_LINE) <= TONED_LINE_DEGREES
        or _arc(hue % 360, 360, TONED_HUE) <= TONED_HUE_DEGREES
    ):
        return True
    band = np.minimum((light / TONED_BAND).astype(int), int(1 / TONED_BAND))
    astray = np.zeros(len(light), dtype=bool)
    for value in np.unique(band):
        inside = band == value
        off = ab[inside] - np.median(ab[inside], axis=0)
        astray[inside] = np.hypot(off[:, 0], off[:, 1]) >= TONED_CHROMA
    return float(astray.mean()) <= TONED_ASTRAY


def _arc(angles: np.ndarray, turn: float, share: float) -> float:
    """The narrowest arc of a circle ``turn`` degrees round that holds
    ``share`` of ``angles``."""
    ordered = np.sort(angles)
    count = len(ordered)
    span = max(int(np.ceil(share * count)), 1)
    wrapped = np.concatenate([ordered, ordered + turn])
    starts = np.arange(count)
    return float((wrapped[starts + span - 1] - wrapped[starts]).min())


def colourful(lab: np.ndarray, spread: float) -> bool:
    """Whether a picture is in colours: several hues far apart, each on an
    accent's share of it at least (``HUE_SECTORS``). Black-and-white,
    sepia, a single tint and two-tone works are not."""
    if spread < COLOUR_SPREAD[0]:
        return False
    coloured = np.hypot(lab[:, 1], lab[:, 2]) >= HUE_CHROMA
    hue = _hue(lab)
    hue = np.where(hue >= 330, hue - 360, hue)
    found = sum(
        float((coloured & (hue >= low) & (hue < high)).mean()) >= HUE_AREA
        for _, low, high in HUE_SECTORS
    )
    return found >= COLOURFUL_HUES


def has_colours(tags: list[str], wanted: list[str], shares: dict[str, float] | None = None) -> bool:
    """Whether a picture with ``tags`` and colour ``shares`` fits the
    ``wanted`` colours and moods. The Kolor sheet asks for colours at a
    level (``"blue@much"``, :func:`at_levels`) and moods from the Tonacja
    card (``"tone:warm"``): every one of them must fit. Older rules
    (playlists, colour cards) keep their meaning, below.

    Whether a picture with ``tags`` fits the ``wanted`` colours, moods
    and accents. Colours and moods are one group, accents another: any one
    of a group will do, but both groups must fit, so blue (or cool) with a
    red accent asks for blue pictures with something red. A colour and its
    accent exclude each other: "red accents" are pictures where red is
    only an accent. A third group, "only" (``"only:blue"``, ``"only:teal"``),
    asks for pictures painted in those colours alone: every colour it is
    painted in (:func:`painted_in`) is one of them, and one of them covers
    a good part of it (its colour tag), so a grey drawing with a touch of
    blue is not "only blue"."""
    have = set(tags)
    levels = [w for w in wanted if LEVEL_MARK in w]
    if not _tones_fit(have, {w.removeprefix(TONE_TAG) for w in wanted if w.startswith(TONE_TAG)}):
        return False
    if levels and not at_levels(have, shares or {}, levels):
        return False
    old = [w for w in wanted if LEVEL_MARK not in w and not w.startswith(TONE_TAG)]
    accents = {w for w in old if w.startswith(ACCENT_TAG)}
    only = {w for w in old if w.startswith(ONLY_TAG)}
    rest = set(old) - accents - only
    return (
        (not rest or bool(have & rest))
        and (not accents or bool(have & accents))
        and (not only or _only(have, only))
    )


def _tones_fit(have: set[str], sides: set[str]) -> bool:
    """Whether a picture is on the asked sides of the Tonacja groups: in
    each group asked, one of its sides (Ciemne or Średnie); every group
    asked must fit. Analysed before the sides, its plain moods stand in."""
    sided = any(t.startswith(TONE_TAG) for t in have)
    for group in TONE_GROUPS:
        asked = sides & set(group)
        if not asked:
            continue
        if sided:
            if not any(TONE_TAG + side in have for side in asked):
                return False
        elif not asked & have:
            return False
    # A side of no group (an older app's mood): it must fit too.
    rest = sides - {side for group in TONE_GROUPS for side in group}
    return all((TONE_TAG + side in have) or side in have for side in rest)


def level(family: str, at: str) -> str:
    """The token of ``family`` at a level: ``level("blue", "much")``."""
    return f"{family}{LEVEL_MARK}{at}"


def at_levels(have: set[str], shares: dict[str, float], wanted: list[str]) -> bool:
    """Whether a picture with tags ``have`` and ``shares`` has each colour
    at its asked level (``LEVELS``); colours asked at "most" together."""
    most: list[str] = []
    for token in wanted:
        family, _, at = token.partition(LEVEL_MARK)
        share = shares.get(family, 0.0)
        if at == "most":
            most.append(family)
        elif at == "accent":
            if ACCENT_TAG + family not in have or share > LEVEL_ACCENT:
                return False
        elif at in ("clear", "much"):
            low, high = LEVEL_CLEAR if at == "clear" else LEVEL_MUCH
            if not low <= share <= high:
                return False
        else:
            return False
    return not most or _mostly(shares, most)


def _mostly(shares: dict[str, float], families: list[str]) -> bool:
    """Whether ``families`` together make most of a picture: of its colours
    (white, grey and black aside), or of all of it when one is a neutral."""
    picked = [shares.get(f, 0.0) for f in families]
    if any(f in NEUTRALS for f in families):
        whole = sum(shares.values()) or 1.0
    else:
        whole = sum(v for f, v in shares.items() if f not in NEUTRALS)
    if whole <= 0 or sum(picked) < LEVEL_MOST_AREA:
        return False
    return sum(picked) >= LEVEL_MOST * whole and all(v >= LEVEL_MOST_EACH * whole for v in picked)


def _only(have: set[str], only: set[str]) -> bool:
    painted = {t for t in have if t.startswith(ONLY_TAG)}
    families = {t.removeprefix(ONLY_TAG) for t in only}
    return bool(painted) and painted <= only and bool(have & families)


def shown_tags(tags: list[str]) -> list[str]:
    """``tags`` as the app shows and counts them: without "only:" and the
    Tonacja sides ("tone:")."""
    return [t for t in tags if not t.startswith((ONLY_TAG, TONE_TAG))]


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


def touches(
    lab: np.ndarray,
    dominant: list[tuple[np.ndarray, float]],
    accents: Sequence[tuple[np.ndarray, float, str]],
) -> list[tuple[np.ndarray, float, str]]:
    """Small patches of a colour the palette does not show yet: the red
    shutter of Vermeer's Little Street, well under a hundredth of the
    picture and of the bricks' own hue, so ``accent_colours`` takes its
    sector for the wall. One per hue sector at most, (colour, weight,
    colour family), the most striking first."""
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = _hue(lab)
    shown = [c for c, _ in dominant] + [c for c, _, _ in accents]
    shown_chroma = np.array([float(np.hypot(c[1], c[2])) for c in shown])
    shown_hue = np.array([float(_hue(c)) for c in shown])
    shown_light = np.array([float(c[0]) for c in shown])
    n = len(lab)
    found: list[tuple[np.ndarray, float, str, float]] = []
    for name, start, end in ACCENT_SECTORS:
        member = (chroma >= 0.05) & ((hue - start) % 360 < end - start)
        count = int(member.sum())
        if count < TOUCH_AREA * n:
            continue
        top = max(1, min(count, int(TOUCH_VIVID * n)))
        centre = lab[member][np.argsort(-chroma[member])[:top]].mean(0)
        vivid = float(np.hypot(centre[1], centre[2]))
        # Of a hue the palette has: only if far more colourful than it. A
        # near-black ground with a blue cast does not show a blue turban.
        gap = np.abs((shown_hue - float(_hue(centre)) + 180) % 360 - 180)
        near = (gap < 40) & (shown_chroma >= 0.03) & (np.abs(shown_light - centre[0]) < 0.25)
        most = float(shown_chroma[near].max()) if near.any() else 0.0
        if vivid < TOUCH_STRONGER * most or vivid - most < TOUCH_BRIGHTER:
            continue
        if any(_distance(centre, c, 0.5) < ACCENT_TWIN for c in shown):
            continue
        diff = lab - centre
        alike = np.sqrt(0.25 * diff[:, 0] ** 2 + 4 * (diff[:, 1] ** 2 + diff[:, 2] ** 2))
        share = float((alike < ACCENT_TWIN).mean())
        if share < TOUCH_AREA:
            continue
        # Named as an accent of its sector is (``accent_colours``).
        if name == "orange" and centre[0] < 0.6:
            name = "brown"
        elif name == "red" and centre[0] > 0.65:
            name = "pink"
        found.append((centre, min(share, TOUCH_WEIGHT), name, vivid - most))
    found.sort(key=lambda f: -f[3])
    kept: list[tuple[np.ndarray, float, str]] = []
    for centre, weight, name, _ in found:
        if len(kept) < MAX_TOUCHES and all(
            _distance(centre, c, 0.5) >= ACCENT_TWIN for c, _, _ in kept
        ):
            kept.append((centre, weight, name))
    return kept


def lights(lab: np.ndarray, shown: Sequence[np.ndarray]) -> list[tuple[np.ndarray, float]]:
    """The white that stands out in a picture whose colours (``shown``) are
    all darker: the foam of Turner's sea, a white cap in a dark room; (colour,
    weight), or nothing (see ``LIGHT_TOP``). No tag goes by it."""
    light = lab[:, 0]
    top = max(1, int(LIGHT_TOP * len(lab)))
    centre = lab[np.argsort(-light)[:top]].mean(0)
    if centre[0] < LIGHT_WHITE or float(np.hypot(centre[1], centre[2])) > LIGHT_CHROMA:
        return []
    if shown and centre[0] - max(float(c[0]) for c in shown) < LIGHT_ABOVE:
        return []
    if centre[0] - float(np.median(light)) < LIGHT_OVER:
        return []
    share = float((light >= centre[0] - LIGHT_NEAR).mean())
    if share < LIGHT_AREA:
        return []
    return [(centre, min(share, LIGHT_WEIGHT))]


def tint_strength(img: Image.Image) -> float:
    """How strongly the whole picture is tinted (median OKLab chroma): ~0 for
    a neutral black-and-white photo or print, ~0.02 and up for sepia, old
    albumen prints, brown ink and cream or tinted paper."""
    lab = linear_to_oklab(_sample(img, 128))
    return round(float(np.median(np.hypot(lab[:, 1], lab[:, 2]))), 4)


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


#: OKLab distance from the paper's colour that counts as a mark on it.
INK_DISTANCE = 0.08
#: A sheet lighter than this (OKLab lightness of its median) is paper.
PAPER_LIGHT = 0.75
#: Of a sheet's pixels, fewer marked than this make it pale ("blada kartka").
PALE_INK = 0.03


def ink_share(img: Image.Image) -> float:
    """The share of a light sheet's pixels marked on it (``INK_DISTANCE``
    from the paper's colour, its median); 1.0 for a picture whose middle is
    no light paper. A pale sheet of a sketchbook has ~0.006, so has a
    finished Ingres portrait in graphite: the number alone cannot tell
    them apart (2026-11-11), only that little can be seen."""
    small = img.convert("RGB")
    small.thumbnail((256, 256))
    width, height = small.size
    margin = int(min(width, height) * 0.06)  # the mount and the museum's edge
    small = small.crop((margin, margin, width - margin, height - margin))
    lab = linear_to_oklab(u8_to_linear(np.asarray(small))).reshape(-1, 3)
    paper = np.median(lab, axis=0)
    if paper[0] < PAPER_LIGHT:
        return 1.0
    return round(float((np.linalg.norm(lab - paper, axis=1) > INK_DISTANCE).mean()), 4)


def pale_sheet(img: Image.Image) -> bool:
    """A light sheet with almost nothing on it."""
    return ink_share(img) < PALE_INK
