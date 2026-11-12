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
    "cream",
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
#: 12: a white that stands out among the swatches (``lights``); 13: a
#: sizeable colour unlike the four dominant ones (``passed_over``); 14:
#: the tints of a pale sheet (``tints``); 15: one rule of names for the
#: shares, the swatches and the accents (``named``), beige a family of its
#: own, accents by the pixels that stand out, a tag for the white accent
#: and the tints, Tonacja against the picture's own white.
SCORE_VERSION = 15

#: A pixel counts towards a colour family from this OKLab chroma on, or
#: this chroma / lightness for light ones: a greyish-blue sky does, a beige
#: wall or the greys of a picture don't.
TINTED = 0.02
TINTED_LIGHT = 0.04
#: Beige (``"cream"``, "Beż"): a pale warm tint, lighter than
#: ``CREAM_LIGHT`` and of the hues ``CREAM_HUES`` (OKLab, degrees), up to
#: chroma ``CREAM_SURE`` always: the paper of a drawing, a print, an old
#: photograph, ivory, pale skin. Of 530 works of the owner's library 42
#: were "mostly orange" or "mostly yellow", 41 of them paper (the audit of
#: 2026-11-12; Mateusz 15:16: beige a family of its own in the Kolor
#: sheet). A stronger tint, up to ``CREAM_CHROMA``, is beige too unless it
#: is ``CREAM_OVER`` times as coloured as the picture's light parts are
#: (``paleness``): Vermeer's yellow bodice by a white wall is yellow, the
#: same tint all over a yellowed sheet is its paper. From ``CREAM_YELLOW``
#: degrees on only the faint ones: a pale lemon is a yellow.
CREAM_LIGHT = 0.62
CREAM_HUES = (35.0, 110.0)
CREAM_SURE = 0.07
CREAM_CHROMA = 0.10
CREAM_OVER = 1.5
CREAM_YELLOW = 100.0
#: The light parts say how coloured the picture's lights are when they are
#: this much of it.
CREAM_AREA = 0.005
#: A dark warm tone (lighter than ``BROWN_LIGHT`` it is none) is brown up
#: to chroma ``BROWN_CHROMA`` between orange and yellow-green; towards red
#: (``BROWN_RED`` degrees, up to orange at 45) only up to
#: ``BROWN_RED_CHROMA``, and nearer red than that never: the dark red of
#: Goya's and David's robes is a red.
BROWN_LIGHT = 0.6
BROWN_CHROMA = 0.13
BROWN_RED = 25.0
BROWN_RED_CHROMA = 0.09
#: A light red is pink near magenta and crimson (up to ``PINK_HUE``
#: degrees), and towards orange while it is paler than ``PINK_CHROMA``: a
#: vivid vermilion in the light stays red.
PINK_LIGHT = 0.65
PINK_HUE = 15.0
PINK_CHROMA = 0.16
#: Least share of the picture a colour family covers to be part of its
#: colouring (tag ``"blue"``: "W odcieniach błękitu"); less is an accent at most.
COLOURING = 0.15
#: Tags of colours that are only accents of a picture (``"accent:blue"``),
#: never with the colour's own tag.
ACCENT_TAG = "accent:"
NEUTRALS = ("black", "gray", "white")
#: What a picture's colours lie on: the neutrals and beige. Never an accent
#: (but the white that stands out: ``lights``), and aside when the colours
#: a picture is painted in are counted (``painted_in``, "most").
GROUNDS = (*NEUTRALS, "cream")
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
#: offers (``"blue@much"``): an accent (a small part that stands out: an
#: accent tag), clear, much, and most. Clear and much are "at least": the
#: colour covers ``LEVEL_CLEAR`` (``LEVEL_MUCH``) of the picture or more.
#: They were bands (8-33%, 28-62%), and a photograph a little lighter or
#: darker moved a work out of its band; "clear" did not find a picture
#: two fifths red (Mateusz 2026-11-12 15:16: "at least", clear from 6%).
#: "Most" is the share of the picture's colours (white, grey, black and
#: beige aside) and several colours asked at it share it: blue and teal
#: "most" are pictures painted mostly in the two.
LEVELS = ("accent", "clear", "much", "most")
LEVEL_MARK = "@"
LEVEL_CLEAR = 0.06
LEVEL_MUCH = 0.28
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
#: Temperatura and Nasycenie are measured as the eye sees the picture,
#: against its own white: the tint of its lightest ``TONE_WHITE_TOP``
#: (when that is a white: ``TONE_WHITE_LIGHT`` light, ``TONE_WHITE_CHROMA``
#: at most), taken away in proportion to lightness. Measured from grey, a
#: black etching on yellowed paper was warm and a pencil drawing vivid: of
#: 530 works of the owner's library 62% were warm and 3% cool, 40% vivid
#: (the audit of 2026-11-12; Mateusz 15:16). Against the white: 43% warm,
#: 51% neutral, 5% cool; 24% vivid, 31% moderate, 46% muted.
TONE_WHITE_TOP = 0.02
TONE_WHITE_LIGHT = 0.70
TONE_WHITE_CHROMA = 0.055
#: Temperatura: the picture's colour along the warm (orange, OKLab hue
#: ``TONE_WARM_HUE``) to cool axis, chroma-weighted mean; warm from
#: ``TONE_WARM``, cool below ``TONE_COOL`` (a little below zero: plain
#: grey is neutral), a monochrome work only below ``TONE_COOL_MONO``: the
#: grey ink of an engraving is cooler than its cream paper and no cool
#: picture, a cyanotype is.
TONE_WARM_HUE = 60.0
TONE_WARM = 0.016
TONE_COOL = -0.006
TONE_COOL_MONO = -0.02
#: Nasycenie: the chroma of the picture's most colourful tenth, a colour
#: in the dark counting for less (in full from ``TONE_FULL_LIGHT`` light
#: on, never less than ``TONE_DIM`` of it: the eye sees little colour in a
#: near-black brown); vivid from ``TONE_VIVID_CHROMA``, muted below
#: ``TONE_MUTED_CHROMA``.
TONE_VIVID_CHROMA = 0.068
TONE_MUTED_CHROMA = 0.035
TONE_FULL_LIGHT = 0.55
TONE_DIM = 0.35
#: Jasność: mean lightness; dark below ``TONE_DARK``, light from
#: ``TONE_LIGHT`` (28% / 30% / 42% of those 530 works).
TONE_DARK = 0.53
TONE_LIGHT = 0.69

#: Dominant colours closer than this (``_distance``) read as one.
MERGE = 0.06
#: Dominant colours shown, at most, and the least share of the picture.
MAX_DOMINANT = 4
MIN_DOMINANT = 0.04
#: A colour the four largest left no room for is shown after them when it
#: covers ``PASSED_SHARE`` of the picture and is ``PASSED_APART`` (see
#: ``_distance``) from every colour shown: the white robes of Delacroix's
#: Indian from Calcutta, an eighth of a picture whose four largest colours
#: are all dark (Mateusz 2026-11-12 12:28: „dlaczego np. tu nie ma bieli?
#: … Jest istotnym elementem dzieła.”), the black of a colour woodblock
#: print's key block.
PASSED_SHARE = 0.06
PASSED_APART = 0.2
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
#: A colour is an accent of a picture (its ``ACCENT_TAG``) also when the
#: bar does not show it: its pixels that stand out cover ``OUT_AREA`` of
#: the picture. A pixel stands out when it is ``OUT_TIMES`` as coloured as
#: the picture's middle (chroma ``OUT_CHROMA`` at least), or
#: ``OUT_CAST_TIMES`` as far from its cast as the middle pixel is
#: (``OUT_CAST`` at least): a blue in a brown room. Stricter than what
#: ``accent_colours`` takes for coloured: a tag is what a work is found
#: by, and a quarter of the works "with a red accent" had a dark brown
#: for it (the audit of 2026-11-12).
OUT_CHROMA = 0.08
OUT_TIMES = 2.0
OUT_CAST = 0.07
OUT_CAST_TIMES = 3.0
OUT_AREA = 0.01
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
#: The tints of a pale sheet (Mateusz 2026-11-12 13:46 and 14:28, of
#: Cézanne's lithograph in colours „Kąpiące się”, whose bar was a scale of
#: greys with one small green patch: „dlaczego … nie ma zieleni i
#: niebieskiego pod kreską rysunku?”, „zieleni i błękitu powinno być
#: chyba więcej na pasku a nie taki mały kwadracik?”). Its sky is a grey
#: by its numbers and blue to the eye, which takes the paper for white:
#: so a sheet's colours are measured from its paper, not from grey. The
#: sheet is light paper (the lightest fifth ``TINT_PAPER`` light and
#: white to cream, the middle tone ``TINT_LIGHT``, the darkest fiftieth
#: no more coloured than ``TINT_INK``: the dark blue of Hokusai's Great
#: Wave is no pencil) and pale (nine tenths of it within
#: ``TINT_PALE`` of the mixtures of its paper and its darkest mark, in
#: a/b); a pixel is tinted from ``TINT_OFF`` off those mixtures on, and
#: ``TINT_UNDER`` darker than the paper; a
#: tint is the tinted pixels of one side of the colour circle
#: (``TINT_SECTORS``), ``TINT_SHARE`` of the sheet at least, shown in the
#: colour of its most tinted ``TINT_TOP``. Only the cool sides: a warm
#: tint cannot be told from the paper's age, its foxing or its mount.
TINT_PAPER = 0.8
TINT_LIGHT = 0.72
TINT_PALE = 0.035
TINT_INK = 0.03
TINT_OFF = 0.01
TINT_UNDER = 0.03
TINT_SHARE = 0.05
TINT_TOP = 0.3
#: A large colour is of a tint's side from this far off the mixtures on,
#: and then shows the tint itself; an accent or a touch of its side is
#: the tint, and is given its share.
TINT_SHOWN = 0.03
TINT_SECTORS = (("green", 120, 195), ("blue", 195, 290))
#: Colours of a picture, at most: what the app's painted bar lays down.
MAX_SWATCHES = 8
#: Hue sectors (OKLab hue, degrees) accents are looked for in: one accent
#: a sector at most. What an accent found is called is ``named``'s to say.
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


def family(lab: np.ndarray, pale: float = 0.0) -> str:
    """The colour family of one colour, by the rule its pixels are named
    by (``named``); ``pale`` is its picture's ``paleness``."""
    return str(named(np.asarray(lab, dtype=float)[None, :], pale)[0])


def paleness(lab: np.ndarray) -> float:
    """How coloured a picture's light parts are (their median chroma; see
    ``CREAM_LIGHT``): what its beige is told from its yellow by. 0 for a
    picture with next to no light parts."""
    light = lab[:, 0] > CREAM_LIGHT
    if float(light.mean()) < CREAM_AREA:
        return 0.0
    return float(np.median(np.hypot(lab[light, 1], lab[light, 2])))


def named(lab: np.ndarray, pale: float) -> np.ndarray:
    """The colour family of each colour of ``lab``: the one rule of names,
    for a picture's pixels (``pixel_families``) and for the colours its bar
    shows (``family``), so what a tag says is what a share counts. ``pale``
    is the picture's ``paleness``."""
    light = lab[:, 0]
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = _hue(lab)
    names = np.where(light > 0.82, "white", np.where(light < 0.3, "black", "gray")).astype("<U6")
    tinted = chroma >= np.maximum(TINTED, TINTED_LIGHT * light)
    bar = np.where(
        hue < CREAM_YELLOW, min(CREAM_CHROMA, max(CREAM_SURE, CREAM_OVER * pale)), CREAM_SURE
    )
    cream = (
        tinted
        & (light > CREAM_LIGHT)
        & (hue >= CREAM_HUES[0])
        & (hue < CREAM_HUES[1])
        & (chroma < bar)
    )
    red = (hue >= 330) | (hue < 45)
    dark = light < BROWN_LIGHT
    sectors = (
        ("red", red),
        (
            "pink",
            red & (light > PINK_LIGHT) & ((hue >= 330) | (hue < PINK_HUE) | (chroma < PINK_CHROMA)),
        ),
        ("orange", (hue >= 45) & (hue < 80)),
        ("yellow", (hue >= 80) & (hue < 120)),
        ("green", (hue >= 120) & (hue < 175)),
        ("teal", (hue >= 175) & (hue < 210)),
        # A sky is blue: light sky blue is at 226 degrees.
        ("blue", (hue >= 210) & (hue < 290)),
        ("purple", (hue >= 290) & (hue < 330)),
        (
            "brown",
            dark
            & (
                ((hue >= 45) & (hue < 110) & (chroma < BROWN_CHROMA))
                | ((hue >= BROWN_RED) & (hue < 45) & (chroma < BROWN_RED_CHROMA))
            ),
        ),
        ("cream", cream),
    )
    for name, sector in sectors:
        names[tinted & sector] = name
    return names


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
    merged = merged_colours(centres, weights)
    dominant = dominant_colours(centres, weights)
    accents = accent_colours(fine, dominant)
    small = touches(linear_to_oklab(_sample(img, TOUCH_SAMPLE)), dominant, accents)
    monochrome = one_tone(fine, spread, accents)
    # One tint and a collector's stamp is one tint still: no touches there,
    # and its paper is no accent.
    if monochrome:
        small = []
    shown = [c for c, _ in dominant] + [c for c, _, _ in accents] + [c for c, _, _ in small]
    more = passed_over(merged[len(dominant) :], shown)
    shown += [c for c, _ in more]
    white = [] if monochrome else lights(fine, shown)
    # What the bar shows the picture is found by (Mateusz 2026-11-12
    # 15:16): the white it shows for standing out (here, or as the colour
    # passed over: the robes of Delacroix's Indian) is an accent by name.
    # In a picture of one tint the white passed over is its paper.
    pale_parts = paleness(fine)
    passed = not monochrome and any(family(c, pale_parts) == "white" for c, _ in more)
    also = ["white"] if white or passed else []
    # A pale sheet's tints: an accent of a tint's side is as large as the
    # tint; a tint no colour shows is shown as one more accent.
    sheet = None if monochrome else pale(fine)
    tinted: list[tuple[np.ndarray, float]] = []
    if sheet is not None:
        for colour, share, side in tints(fine, sheet):
            # A large colour of its side shows it, and holds its pixels.
            if any(sheet.side(c, TINT_SHOWN) == side for c, _ in dominant + more):
                continue
            for found in (accents, small):
                sides = [sheet.side(c, TINT_OFF) for c, _, _ in found]
                if side in sides:
                    twin = sides.index(side)
                    found[twin] = (found[twin][0], max(found[twin][1], share), found[twin][2])
                    break
            else:
                tinted.append((colour, share))
    swatches = [_swatch(c, w) for c, w in dominant + more]
    # A touch is what the eye goes to: it is shown before the least accent.
    room = MAX_SWATCHES - len(swatches) - len(small) - len(white) - len(tinted)
    swatches += [_swatch(c, w, accent=True) for c, w, _ in accents[: max(room, 0)]]
    swatches += [_swatch(c, w, accent=True) for c, w in tinted]
    swatches += [_swatch(c, w, accent=True) for c, w, _ in small]
    swatches += [_swatch(c, w, accent=True) for c, w in white]
    tags = colour_tags(fine, spread, shown, monochrome, also)
    return Analysis(swatches, tags, colour_shares(fine, spread))


def colour_shares(lab: np.ndarray, spread: float) -> dict[str, float]:
    """Each colour family's share of the picture (``pixel_families``), the
    ones it has, to three places."""
    names = pixel_families(lab, spread)
    shares = {n: round(float((names == n).mean()), 3) for n in COLOR_FAMILIES}
    return {n: v for n, v in shares.items() if v > 0}


def pixel_families(lab: np.ndarray, spread: float) -> np.ndarray:
    """Each pixel's colour family (``named``: a pale blue sky is blue, not
    grey); a picture with no colour of its own (``spread``: ink on yellowed
    paper) is all neutrals."""
    if spread < COLOUR_SPREAD[0]:
        light = lab[:, 0]
        return np.where(light > 0.82, "white", np.where(light < 0.3, "black", "gray")).astype("<U6")
    return named(lab, paleness(lab))


def standing_out(lab: np.ndarray) -> np.ndarray:
    """The pixels that catch the eye: far more coloured than the picture
    is, or well off its cast (see ``OUT_CHROMA``)."""
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    cast = np.median(lab[:, 1:], 0)
    off_cast = np.hypot(lab[:, 1] - cast[0], lab[:, 2] - cast[1])
    strong = chroma >= max(OUT_CHROMA, OUT_TIMES * float(np.median(chroma)))
    apart = (off_cast >= max(OUT_CAST, OUT_CAST_TIMES * float(np.median(off_cast)))) & (
        chroma >= 0.03
    )
    return np.asarray(strong | apart)


def one_tone(
    lab: np.ndarray, spread: float, accents: Sequence[tuple[np.ndarray, float, str]] = ()
) -> bool:
    """Whether a picture is monochrome (its ``"monochrome"`` tag): not in
    colours (``colourful``) and of one tint (``single_tone``)."""
    # Several hues, however muted (El Greco), are never monochrome.
    return not colourful(lab, spread) and single_tone(lab, spread, accents)


def colour_tags(
    lab: np.ndarray,
    spread: float,
    shown: Sequence[np.ndarray] = (),
    monochrome: bool | None = None,
    also: Sequence[str] = (),
) -> list[str]:
    """Colour and mood tags. A colour family is a tag when it covers
    ``COLOURING`` of the picture: a Madonna's blue robe in a gold altarpiece
    is not "in shades of blue". Smaller colours are ``ACCENT_TAG`` tags
    (``accented``): those the bar shows (``shown``; ``also``: the white
    that stands out, ``lights``), and those whose pixels stand out. Warm
    and cool go by area too, so one vivid red robe does not make a grey sky
    warm. ``monochrome``: whether the picture is (``one_tone``), if already
    known."""
    names = pixel_families(lab, spread)
    share = {n: float((names == n).mean()) for n in COLOR_FAMILIES}
    tags = [n for n in COLOR_FAMILIES if share[n] >= COLOURING]
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    mean_chroma = float(chroma.mean())
    in_colours = colourful(lab, spread)
    if monochrome is None:
        monochrome = one_tone(lab, spread)
    accents = accented(lab, spread, names, shown, monochrome) | set(also)
    tags += [ACCENT_TAG + n for n in COLOR_FAMILIES if n in accents and n not in tags]
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
    return tags + [TONE_TAG + side for side in tone_sides(lab, monochrome)]


def accented(
    lab: np.ndarray,
    spread: float,
    names: np.ndarray,
    shown: Sequence[np.ndarray],
    monochrome: bool,
) -> set[str]:
    """The colour families a picture has an accent of, the ones large
    enough for a tag of their own among them: the colours its bar shows
    (``shown``: the Little Street is found by its red shutter, Mateusz
    2026-11-11 21:50), each named as its pixels are (``named``: the dark
    brown of a varnished ground is no red accent), and the families whose
    pixels stand out on ``OUT_AREA`` of it though the bar has no room for
    them. A picture with no colour of its own (``spread``) has none; one
    of a single tint none by its pixels: a stamp on an etching is not what
    it is looked for by. Never a ground (``GROUNDS``): a white dominant
    colour is a sheet's paper as often as a white dress, and the white
    that stands out is ``lights``' to find."""
    if spread < COLOUR_SPREAD[0]:
        return set()
    pale = paleness(lab)
    found = {family(colour, pale) for colour in shown}
    if not monochrome:
        out = standing_out(lab)
        found |= {n for n in COLOR_FAMILIES if float((out & (names == n)).mean()) >= OUT_AREA}
    return {n for n in found if n not in GROUNDS}


def tone_sides(lab: np.ndarray, monochrome: bool) -> list[str]:
    """The picture's side of each Tonacja group (``TONE_GROUPS``), one
    each; its colour seen against its own white (``TONE_WHITE_TOP``)."""
    light = lab[:, 0]
    ab = lab[:, 1:]
    top = light >= np.percentile(light, 100 * (1 - TONE_WHITE_TOP))
    top_light = float(light[top].mean())
    white = np.median(ab[top], axis=0)
    if top_light < TONE_WHITE_LIGHT or float(np.hypot(white[0], white[1])) > TONE_WHITE_CHROMA:
        # Its lightest tone is a colour or a dark: nothing to see it against.
        white = np.zeros(2)
    seen = ab - np.outer(np.clip(light / max(top_light, 1e-6), 0, 1), white)
    chroma = np.hypot(seen[:, 0], seen[:, 1])
    hue = np.arctan2(seen[:, 1], seen[:, 0])
    warmth = float((chroma * np.cos(hue - np.radians(TONE_WARM_HUE))).mean())
    vivid = float(np.percentile(chroma * np.clip(light / TONE_FULL_LIGHT, TONE_DIM, 1.0), 90))
    mean_light = float(light.mean())
    cool = TONE_COOL_MONO if monochrome else TONE_COOL
    return [
        "warm" if warmth >= TONE_WARM else "cool" if warmth < cool else "neutral",
        "vivid"
        if vivid >= TONE_VIVID_CHROMA
        else "muted"
        if vivid < TONE_MUTED_CHROMA
        else "moderate",
        "monochrome" if monochrome else "colorful",
        "dark" if mean_light < TONE_DARK else "light" if mean_light >= TONE_LIGHT else "medium",
    ]


def painted_in(share: dict[str, float]) -> list[str]:
    """The colour families a picture is painted in, from each one's share
    of it: the fewest, largest first, that make ``ONLY_SHARE`` of its
    coloured pixels (``GROUNDS`` aside: a blue wash is blue alone on white
    paper and on cream). A blue Whistler nocturne is blue alone, Monet's
    sea at Pourville blue and turquoise; a picture without colour, none."""
    colours = sorted(((v, n) for n, v in share.items() if n not in GROUNDS and v > 0), reverse=True)
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
            if ACCENT_TAG + family not in have:
                return False
        elif at in ("clear", "much"):
            if share < (LEVEL_CLEAR if at == "clear" else LEVEL_MUCH):
                return False
        else:
            return False
    return not most or _mostly(shares, most)


def _mostly(shares: dict[str, float], families: list[str]) -> bool:
    """Whether ``families`` together make most of a picture: of its colours
    (``GROUNDS`` aside: white, grey, black and beige), or of all of it when
    one of them is asked."""
    picked = [shares.get(f, 0.0) for f in families]
    if any(f in GROUNDS for f in families):
        whole = sum(shares.values()) or 1.0
    else:
        whole = sum(v for f, v in shares.items() if f not in GROUNDS)
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
    return [m for m in merged_colours(centres, weights) if m[1] >= MIN_DOMINANT][:MAX_DOMINANT]


def passed_over(
    rest: Sequence[tuple[np.ndarray, float]], shown: Sequence[np.ndarray]
) -> list[tuple[np.ndarray, float]]:
    """The largest of the colours the dominant ones left no room for
    (``rest``) that is sizeable and unlike every colour ``shown`` (see
    ``PASSED_SHARE``); (colour, weight), or nothing."""
    for centre, weight in rest:
        if weight >= PASSED_SHARE and all(_distance(centre, c) >= PASSED_APART for c in shown):
            return [(centre, weight)]
    return []


def merged_colours(centres: np.ndarray, weights: np.ndarray) -> list[tuple[np.ndarray, float]]:
    """The k-means colours, largest first, with near-identical ones merged."""
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
    return merged


def accent_colours(
    lab: np.ndarray, dominant: list[tuple[np.ndarray, float]]
) -> list[tuple[np.ndarray, float, str]]:
    """Small, vivid colours the dominant ones do not show: the blue apron,
    yellow bodice and red skirt of Vermeer's Milkmaid, though each covers a
    few percent. One per hue sector at most, in the colour of its most
    vivid pixels rather than an average with its shadows; (colour, share of
    the picture that looks like it, the hue sector it was found in),
    largest first. Its tag goes by its colour (``accented``)."""
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
    hue sector), the most striking first."""
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
    weight), or nothing (see ``LIGHT_TOP``). Its tag is ``"accent:white"``."""
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


class Sheet(NamedTuple):
    """A pale sheet's paper and darkest mark (OKLab)."""

    paper: np.ndarray
    ink: np.ndarray

    def off(self, lab: np.ndarray) -> np.ndarray:
        """How far colours lie, in a/b, from the mixture of paper and ink
        that is as light as they are."""
        span = max(float(self.paper[0] - self.ink[0]), 1e-6)
        part = np.clip((self.paper[0] - lab[..., 0]) / span, 0.0, 1.0)
        mixed = self.paper[1:] + part[..., None] * (self.ink[1:] - self.paper[1:])
        return np.asarray(lab[..., 1:] - mixed)

    def side(self, colour: np.ndarray, least: float) -> str | None:
        """The tint (``TINT_SECTORS``) a colour is, ``least`` off the
        mixtures at least; else None."""
        off = self.off(colour)
        if float(np.hypot(off[0], off[1])) < least:
            return None
        hue = float(np.degrees(np.arctan2(off[1], off[0]))) % 360
        return next((name for name, start, end in TINT_SECTORS if start <= hue < end), None)


def pale(lab: np.ndarray) -> Sheet | None:
    """The paper and the darkest mark of a light, pale sheet (see
    ``TINT_PAPER``); None for any other picture."""
    light = lab[:, 0]
    if float(np.median(light)) < TINT_LIGHT:
        return None
    paper = np.median(lab[light >= np.quantile(light, 0.8)], axis=0)
    # Paper is white to cream: a pale blue picture is a mist, not a sheet.
    if paper[0] < TINT_PAPER or paper[2] < 0:
        return None
    sheet = Sheet(paper, np.median(lab[light <= np.quantile(light, 0.02)], axis=0))
    # Its darkest mark is a grey or a brown: drawn on, not printed in colours.
    if float(np.hypot(sheet.ink[1], sheet.ink[2])) > TINT_INK:
        return None
    off = sheet.off(lab)
    if float(np.quantile(np.hypot(off[:, 0], off[:, 1]), 0.9)) > TINT_PALE:
        return None
    return sheet


def tints(lab: np.ndarray, sheet: Sheet) -> list[tuple[np.ndarray, float, str]]:
    """The cool tints of a pale sheet: (colour, share of the sheet, side),
    largest first (see ``TINT_PAPER``). No tag goes by them: of 19 sheets
    of the owner's library with one, 9 had no such colour to the eye, 6 of
    them a tint from the grey board the museum photographed them on (the
    audit of 2026-11-12)."""
    off = sheet.off(lab)
    far = np.hypot(off[:, 0], off[:, 1])
    hue = np.degrees(np.arctan2(off[:, 1], off[:, 0])) % 360
    # A wash darkens its paper: a white mount round a cream sheet is no tint.
    under = lab[:, 0] <= sheet.paper[0] - TINT_UNDER
    found: list[tuple[np.ndarray, float, str]] = []
    for name, start, end in TINT_SECTORS:
        member = (far >= TINT_OFF) & (hue >= start) & (hue < end) & under
        share = float(member.mean())
        if share < TINT_SHARE:
            continue
        top = max(1, int(TINT_TOP * int(member.sum())))
        found.append((lab[member][np.argsort(-far[member])[:top]].mean(0), share, name))
    return sorted(found, key=lambda f: -f[1])


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
