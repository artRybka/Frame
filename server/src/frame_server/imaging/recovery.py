"""The colours a work has lost, given back by calculation alone: first a
preview on its card, since 2026-11-15 18:39 UTC the work's picture itself
when the owner asks ("Wybranie w menu podmienia na wersje z odżółconym
papierem / ściągniętym werniksem", ``Item.cleaned``,
:mod:`frame_server.cleaning`): with no slider any more ("Z ściągania
werniksu usuwamy suwak. Zostawiamy tylko poziom propozycji"), at the
proposed strength (:func:`kept_strength`).

Mateusz 2026-11-15, of works „zgaszone, ściemniałe, zbrązowiałe czy
stonowane pod werniksem”: a simulation of their colours recovered, as a
preview on the card; then: no image model („algorytm … bez angażowania
modelu graficznego”), „Koncepcja suwaka - super”, works on paper
„mogłaby odżółcać papier”, the proposed strength as near as it can be
(„fajnie jeżeli „propozycja” będzie możliwie trafna… Czy na pewno do
każdej analizy potrzebujemy modelu?”), and of the trials on thirty real
conservations: „Zbudować bez modelu”.

Two calculations, both in linear light and with every pixel the work's own:

Varnish (oil, tempera). An aged resin varnish is a yellow filter: it takes
most of the blue, some green and little red. One number says how thick it
is; the picture without it is each channel times ``exp(d * ALPHA)``, then
brought back into range (:func:`gains`). In the preview (apps of
1.145.155–161) the phone did that sum itself while the owner moved the
slider, the server reading the picture once: which strength to propose
(:func:`propose`) and how light the result gets at every strength
(``Varnish.tops``). The work shown cleaned is made here
(:func:`unvarnished`), with three things the preview's sum had not: the
darks keep their own colour (:data:`DARK`, by the picture's own middle:
:func:`_dark`) and lose the varnish's haze (:data:`DEPTH`), and a picture
dark all over comes out lighter (:data:`LIFT`).

Paper (drawings, prints, watercolours, pastels). The sheet's tone is read
as a smooth field (darker edges, old mount lines), every pixel is divided
by it and given a well-kept sheet's tone: ink, wash and print are
transparent layers on the paper, so what the paper lost they lost with
it (:func:`deyellow`). What lies on the sheet opaquely (white chalk, body
colour, thick black) is left alone. Paper toned by intent (blue, grey,
prepared) is not offered (:func:`sheet_state`).

What thirty before-and-after pairs of real conservations said (the measure:
OKLab colour distance to the photograph after the real cleaning):
- the varnish's colour (``ALPHA``) holds: other ratios gain 3 % at most;
- where the varnish was the trouble (14 pairs) the best strength brings the
  distance from 3.2 to 2.1, and the strength proposed here to 2.3;
- one photograph cannot tell a yellowed picture from one darkened by grime
  or one that was always warm (16 pairs): there the sum is too strong.
  Hence a preview asked for, a slider, and words that say what it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from .color import (
    FloatArray,
    linear_to_oklab,
    linear_to_u8,
    luminance,
    oklab_to_linear,
    u8_to_linear,
)

#: Part of what the app keeps a reading and a de-yellowed sheet by: raise it
#: when either calculation changes.
VERSION = 1

#: Aged natural-resin varnish: how much of red, green and blue it takes,
#: relative to blue.
ALPHA = (0.15, 0.36, 1.0)
#: The thickest varnish the slider goes to (blue let through: exp(-1.6) = 0.2).
D_MAX = 1.6
#: The strengths ``Varnish.tops`` is read at.
STEPS = tuple(round(0.1 * i, 1) for i in range(17))
#: Where the lightest of the result is put when it would leave the range.
TOP = 0.97
#: The long side a picture is read at: its colours, not its detail.
READ = 320

#: The strength real conservations took off, in the pairs where varnish was
#: the trouble, and how the picture's own white moves it.
TYPICAL = 0.69
WHITE_MEAN = 0.78
WHITE_WEIGHT = 0.24
#: A white the varnish's colour does not explain (a warm lamp, a coloured
#: ground, no white at all) says nothing.
WHITE_FIT = 0.06
#: A white that is white already: little to take off. The proposal comes
#: down with it, never below ``LEAST`` (the slider is there to try).
WHITE_CLEAN = 0.3
LEAST = 0.2
#: Which sum a work shown cleaned was made with (``Cleaned.reading``): raise
#: it when :func:`unvarnished` or :func:`kept_strength` changes, and the
#: works kept cleaned are made again (``Cleaning.catch_up``).
#: 2 (2026-11-15 21:44): the whole proposal, darks by the picture's middle,
#: the lights of a dark picture raised.
READING = 2
#: Under this luminance (linear light) the varnish's colour is taken off
#: less and less, and not at all at black: there only the lightness
#: follows. Mateusz 2026-11-15 19:00–19:05, of works shown cleaned:
#: "kalkulacja lekko zaniebieszcza czarne / bardzo ciemne fragmenty
#: dzieła", "I ciemne zielenie - podobnie jak inne partie ciemne dzieła".
#: What a photograph shows in a picture's darks is mostly the light its
#: surface throws back, not paint seen through the varnish, so the blue
#: given back there was never taken. The thirty pairs say the same: the
#: share of the varnish's colour nearest the real cleaning is none under
#: 0.01, an eighth to 0.04, three eighths to 0.08, three quarters to 0.15
#: and all of it above. The darkest tenth of a really cleaned picture
#: stays warm (OKLab b +1.4, 3 pairs on the blue side); the plain sum left
#: it at +0.3 with 11 on the blue side, this at +1.1 with 6, as many as
#: the photographs left alone.
DARK = 0.15
#: What is dark is dark for the picture: in one that is dark all over the
#: paint itself lies under :data:`DARK`, and a cleaning that left its colour
#: alone was no cleaning to the eye. Mateusz 2026-11-15 21:44–21:46, of
#: Gainsborough's "Cottage Children" (the Met; half of it under 0.017, 98 %
#: under 0.15): "Korekta werniksu - czasem ledwo widoczna". So the colour
#: fades out under this many times the picture's median luminance, between
#: :data:`DARK_LEAST` and :data:`DARK`. On the thirty pairs it is as near
#: the real cleaning as the one threshold (6.81 both, the whole proposal),
#: the darkest tenth as warm (+1.1, 6 on the blue side); dark greens move
#: under half as far to blue as under the plain sum (a quarter with the
#: one threshold). In the pairs where varnish was the trouble the real cleaning
#: took its whole colour off everything lighter than 0.01.
DARK_BY_MIDDLE = 2.0
DARK_LEAST = 0.03
#: A cleaned picture is lighter: where the sum leaves room over the lights
#: (a picture dark all over), they are raised by this share of the room,
#: in stops. Mateusz 2026-11-15 22:08, of the Gainsborough with its colour
#: back but as dark as before: "Jeszcze mocniej". More strength is not the
#: way (on the thirty pairs half as much again on dark pictures is farther
#: from the real cleaning: 6.82 for 6.81); lighter lights are: the dark
#: pictures of the pairs come out of a real cleaning twice as light in the
#: median (two photographs, though), and with this the sum is nearer it
#: (6.79; dark pictures 0.31 nearer than the photograph left alone, for
#: 0.27), the darkest tenth as warm. The Gainsborough comes out 1.6 times
#: as light. A picture whose lights are darker than :data:`LIGHTS_LEAST`
#: is a night: raised no more than one with its lights there (1.56 times).
LIFT = 0.5
LIGHTS_LEAST = 0.4
#: Contrast (Mateusz 19:02: "Nie wiem czy nie powinien być minimalnie
#: większy"): an aged varnish also lays a haze over the darks. The
#: picture's own black (this centile of its luminance) comes down by
#: ``DEPTH`` of itself for a varnish of 1. On the pairs the spread of
#: lightness is 7 % wider in the mean after a real cleaning (in under
#: half of them, though: two photographs, two lightings); the plain sum
#: gave 2.5 %, this gives 5.6 % and is no farther from the real cleaning
#: (6.81 for 6.87, lightness counted; the photograph left alone 7.07).
BLACK_AT = 0.02
DEPTH = 0.75
#: A haze is thin: a picture with no black in it (its darkest a mid-tone)
#: is not darkened as if that were haze. (The pairs' blacks: 0.001–0.02.)
BLACK_MOST = 0.02
_LUMA = (0.2126, 0.7152, 0.0722)


@dataclass(frozen=True)
class Varnish:
    """A picture read for the varnish simulation."""

    #: The strength to open the slider at.
    strength: float
    #: The thickness the picture's white speaks of; None without a white to go by.
    white: float | None
    #: The lightest of the result (99.7th centile of the largest channel)
    #: at every strength of :data:`STEPS`, before it is brought into range.
    tops: tuple[float, ...]


def _small(img: Image.Image, long: int = READ) -> FloatArray:
    rgb = img.convert("RGB")
    scale = long / max(rgb.size)
    if scale < 1:
        size = (max(round(rgb.width * scale), 8), max(round(rgb.height * scale), 8))
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
    return u8_to_linear(np.asarray(rgb))


def _inner(lin: FloatArray, rim: float) -> FloatArray:
    """Without the edge: a frame's gold, a mount, the table."""
    height, width = lin.shape[:2]
    a, b = round(height * rim), round(width * rim)
    return lin[a : height - a, b : width - b]


def white_of(lin: FloatArray, top: float = 0.05, pick: float = 0.3) -> FloatArray:
    """The paint's white as it shows now: of the lightest pixels, the least
    yellow (under a yellow filter, white is the least yellow light thing)."""
    px = lin.reshape(-1, 3)
    y = luminance(px)
    cut = np.quantile(y, 1 - top)
    light = px[(y >= cut) & (px.max(1) < 0.985)]  # blown highlights say nothing
    if len(light) < 50:
        light = px[y >= cut]
    lab = linear_to_oklab(light)
    yellow = lab[:, 2] + 0.5 * np.abs(lab[:, 1])
    count = max(int(len(light) * pick), 20)
    chosen: FloatArray = light[np.argsort(yellow)[:count]].mean(0)
    return chosen


def thickness(white: FloatArray) -> tuple[float, float]:
    """The varnish that would give a neutral white this colour, and how far
    the colour is from what any varnish would give (log units)."""
    logs = np.log(np.maximum(np.asarray(white, dtype=np.float64), 1e-4))
    # log w = log k - d * alpha, least squares over (log k, d)
    design = np.stack([np.ones(3), -np.asarray(ALPHA, dtype=np.float64)], 1)
    found, *_ = np.linalg.lstsq(design, logs, rcond=None)
    left = float(np.sqrt(np.mean((logs - design @ found) ** 2)))
    return float(found[1]), left


def propose(white: float | None) -> float:
    """The strength to propose: what real conservations took off, moved by
    the picture's own white (learnt on the varnished pairs, each left out
    in turn: within 0.2 of the best strength on 8 of 14)."""
    if white is None:
        return TYPICAL
    strength = TYPICAL + WHITE_WEIGHT * (white - WHITE_MEAN)
    if white < WHITE_CLEAN:
        strength = max(strength * white / WHITE_CLEAN, LEAST)
    return round(float(np.clip(strength, 0.0, D_MAX)), 2)


def gains(strength: float, top: float) -> tuple[float, float, float]:
    """What red, green and blue (linear light) are multiplied by at
    ``strength``; ``top``: the lightest of the result there
    (``Varnish.tops``): the preview's sum, which the apps of
    1.145.155–161 do in their shader."""
    scale = TOP / top if top > TOP else 1.0
    r, g, b = (float(np.exp(strength * a)) * scale for a in ALPHA)
    return r, g, b


def _black(lin: FloatArray) -> float:
    """The picture's own black: the darkest it has, a few specks aside."""
    return min(float(np.quantile(luminance(lin.reshape(-1, 3)), BLACK_AT)), BLACK_MOST)


def _dark(lin: FloatArray) -> float:
    """The luminance under which the picture's colour is its darks' own
    (:data:`DARK_BY_MIDDLE`): :data:`DARK`, less in a picture dark all over."""
    middle = float(np.median(luminance(lin.reshape(-1, 3))))
    return float(np.clip(DARK_BY_MIDDLE * middle, DARK_LEAST, DARK))


def _without(lin: FloatArray, strength: float, black: float, dark: float) -> FloatArray:
    """``lin`` without a varnish of ``strength``, not yet brought into
    range: the haze off its darks (``black``: :func:`_black` of the whole
    picture), then the varnish's colour off, all of it in the lights and
    less and less under ``dark`` (:func:`_dark` of the whole picture),
    where only the lightness follows."""
    haze = black * min(DEPTH * strength, 1.0)
    clear = np.clip((lin - haze) / (1.0 - haze), 0.0, 1.0)
    colour = np.exp(strength * np.asarray(ALPHA, dtype=np.float32))
    even = float(colour @ np.asarray(_LUMA, dtype=np.float32))
    share = np.clip(luminance(clear) / dark, 0.0, 1.0)
    share = share * share * (3.0 - 2.0 * share)
    out: FloatArray = (clear * (even + (colour - even) * share[..., None])).astype(np.float32)
    return out


def _into_range(out: FloatArray) -> float:
    """What the sum ``out`` is multiplied by: its lightest brought down to
    :data:`TOP` when it left the range, and raised towards it when the
    picture is dark all over (:data:`LIFT`)."""
    top = float(np.quantile(out.max(-1), 0.997))
    if top > TOP:
        return TOP / top
    return float((TOP / max(top, LIGHTS_LEAST)) ** LIFT)


def unvarnish(lin: FloatArray, strength: float) -> FloatArray:
    """The picture without a varnish of ``strength``."""
    out = _without(lin, strength, _black(lin), _dark(lin))
    return np.clip(out * _into_range(out), 0, 1).astype(np.float32)


def kept_strength(img: Image.Image) -> float:
    """The strength a work is shown without its varnish at
    (``Item.cleaned``): the proposal ("Zostawiamy tylko poziom
    propozycji"). Three quarters of it, kept at first (1.145.164: nearer
    the real cleaning on the thirty pairs under the plain sum, 2.44 for
    2.57), gained nothing once the darks kept their colour (6.81 and 6.79,
    lightness counted) and was hard to see: on the pairs a real cleaning
    moves a picture by 10.7 (OKLab × 100, mean; two photographs, though),
    three quarters of the proposal by 2.0, the whole by 2.7."""
    return read_varnish(img).strength


@dataclass(frozen=True)
class VarnishSum:
    """What the sum of :func:`unvarnished` goes by for one picture, read
    small from it: all the phone needs to take the varnish off what it
    shows (the full-screen viewer, ``ios/…/VarnishSum.swift``; Mateusz
    2026-11-20: "korekta może dotyczyć tylko tego co widać"). Per pixel,
    in linear light: ``clear = clip((lin - haze) / (1 - haze))``,
    ``share = smoothstep(clip(luminance(clear) / dark))``,
    ``out = clip(clear * (even + (colour - even) * share) * scale)``."""

    haze: float
    colour: tuple[float, float, float]
    even: float
    dark: float
    scale: float
    luma: tuple[float, float, float] = _LUMA


def varnish_sum(img: Image.Image, strength: float) -> VarnishSum:
    """The numbers of the sum taking a varnish of ``strength`` off ``img``."""
    small = _small(img.convert("RGB"), 640)
    black, dark = _black(small), _dark(small)
    scale = _into_range(_without(small, strength, black, dark))
    colour = np.exp(strength * np.asarray(ALPHA, dtype=np.float32))
    r, g, b = (float(c) for c in colour)
    return VarnishSum(
        haze=float(black * min(DEPTH * strength, 1.0)),
        colour=(r, g, b),
        even=float(colour @ np.asarray(_LUMA, dtype=np.float32)),
        dark=dark,
        scale=scale,
    )


def unvarnished(img: Image.Image, strength: float) -> Image.Image:
    """``img`` without a varnish of ``strength``, whole and at its own size:
    its black, its middle and how light it gets are read small, the sum
    goes a band of rows at a time (an original of 4000 px never holds more
    than a few bands of floats)."""
    rgb = img.convert("RGB")
    small = _small(rgb, 640)
    black, dark = _black(small), _dark(small)
    scale = _into_range(_without(small, strength, black, dark))
    source = np.asarray(rgb)
    out = np.empty_like(source)
    rows = 256
    for start in range(0, source.shape[0], rows):
        lin = u8_to_linear(source[start : start + rows])
        out[start : start + rows] = linear_to_u8(
            np.clip(_without(lin, strength, black, dark) * scale, 0, 1)
        )
    return Image.fromarray(out)


def read_varnish(img: Image.Image) -> Varnish:
    lin = _small(img)
    found, left = thickness(white_of(_inner(lin, 0.05)))
    white = float(np.clip(found, 0.0, D_MAX)) if left <= WHITE_FIT else None
    largest = lin.reshape(-1, 3)
    tops = tuple(
        round(
            float(
                np.quantile((largest * np.exp(d * np.asarray(ALPHA, np.float32))).max(-1), 0.997)
            ),
            4,
        )
        for d in STEPS
    )
    return Varnish(strength=propose(white), white=white, tops=tops)


# ---------- paper ----------

#: The warmth (OKLab chroma) of well-kept sheets in the owner's library:
#: paper was cream, never blue-white.
FRESH = 0.014
#: The side the sheet's tone is read at, and how far it is smoothed (of it).
FIELD = 192
SMOOTH = 0.07
#: The long side a de-yellowed sheet is sent at (the card shows 1800).
SENT = 2000

SheetState = Literal["hidden", "toned", "white", "yellowed"]


@dataclass(frozen=True)
class Sheet:
    """The sheet of a work on paper, as the calculation finds it."""

    #: Its colour, linear RGB.
    colour: tuple[float, float, float]
    #: How much of the picture is bare sheet.
    share: float
    chroma: float
    hue: float  # degrees: 90 is yellow
    lightness: float


def _seed(lin: FloatArray) -> FloatArray:
    """The sheet's colour: the commonest light colour of the picture."""
    height, width = lin.shape[:2]
    long = max(height, width)
    size = (max(width * 160 // long, 8), max(height * 160 // long, 8))
    small = cv2.resize(lin, size, interpolation=cv2.INTER_AREA).reshape(-1, 3)
    lab = linear_to_oklab(small)
    light = lab[:, 0] >= np.quantile(lab[:, 0], 0.45)
    cells = np.round(lab[light] / np.array([0.04, 0.012, 0.012])).astype(int)
    keys, inverse, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    # The commonest, with a lean to the lighter: the sheet is rarely the
    # darkest common thing.
    score = counts * (1 + 2 * (keys[:, 0] * 0.04 - 0.5))
    seed: FloatArray = np.median(small[light][inverse.ravel() == int(np.argmax(score))], 0)
    return seed.astype(np.float32)


def _mask(lin: FloatArray, seed: FloatArray) -> np.ndarray:
    lab = linear_to_oklab(lin)
    at = linear_to_oklab(seed[None])[0]
    near = np.linalg.norm(lab[..., 1:] - at[1:], axis=-1) < 0.035
    return near & (lab[..., 0] > at[0] - 0.20) & (lab[..., 0] < at[0] + 0.06)


def _field(lin: FloatArray, mask: np.ndarray, seed: FloatArray) -> tuple[FloatArray, float]:
    """The sheet's tone everywhere, smooth and small (:data:`FIELD`): a blur
    of the bare sheet's own pixels, carried across the drawing. Two more
    rounds keep only what is as light as the sheet around it, so pencil and
    pale wash do not darken the field."""
    height, width = lin.shape[:2]
    scale = FIELD / max(height, width)
    size = (max(round(width * scale), 8), max(round(height * scale), 8))
    small = cv2.resize(lin, size, interpolation=cv2.INTER_AREA)
    bare = cv2.resize(mask.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    bare = np.where(bare > 0.85, bare, 0.0).astype(np.float32)  # tiles nearly all sheet
    sigma = SMOOTH * FIELD
    light = luminance(small)

    def blur(weight: FloatArray) -> FloatArray:
        summed = cv2.GaussianBlur(small * weight[..., None], (0, 0), sigma)
        weights = cv2.GaussianBlur(weight, (0, 0), sigma)[..., None]
        sure = np.clip(weights / 0.04, 0, 1)
        mean = np.where(weights > 1e-4, summed / np.maximum(weights, 1e-4), seed)
        return (mean * sure + seed * (1 - sure)).astype(np.float32)

    field = blur(bare.astype(np.float32))
    for _ in range(2):
        field = blur((bare * (light >= luminance(field) * 0.985)).astype(np.float32))
    return field, float(bare.mean())


def _fresh(field: FloatArray, seed: FloatArray) -> FloatArray:
    """A well-kept sheet's tone. Yellowing takes blue and some green and
    leaves red nearly alone, so the red the sheet still has (at its least
    stained) is the fresh sheet's lightness; its warmth comes down to a
    well-kept sheet's, a very warm sheet keeping some of its own."""
    red = float(np.quantile(field[..., 0], 0.97))
    lab = linear_to_oklab(seed[None])[0].copy()
    chroma = float(np.hypot(lab[1], lab[2]))
    warmth = max(FRESH, 0.3 * chroma)
    if chroma > warmth:
        lab[1:] *= warmth / chroma
    tone = np.clip(oklab_to_linear(lab[None])[0], 1e-4, 1)
    return (tone * (max(red, float(seed[0])) / tone[0])).clip(0, 1).astype(np.float32)


def read_sheet(img: Image.Image) -> Sheet:
    lin = _small(img, 640)
    seed = _seed(lin)
    _, share = _field(lin, _mask(lin, seed), seed)
    lab = linear_to_oklab(seed[None])[0]
    r, g, b = (float(c) for c in seed)
    return Sheet(
        colour=(r, g, b),
        share=share,
        chroma=float(np.hypot(lab[1], lab[2])),
        hue=float(np.degrees(np.arctan2(lab[2], lab[1]))),
        lightness=float(lab[0]),
    )


#: A support that has its colour by intent, in the museums' words.
_TONE = (
    r"blue|gr[ae]y|brown|buff|tan\b|green|pink|colou?red|tinted|toned|prepared|gilded|gold"
    r"|niebiesk|szar|brąz|barwion|kolorow|złot|bruin|blauw|grijs|grijze|teint|bleu|gris|brun"
)
_AFTER_ON = re.compile(r"(?:\bon\b|\bop\b|\bna\b|\bsur\b|\bauf\b)(.*)$")
_TONED_TAIL = re.compile(rf"({_TONE}|silk|jedwab|vellum|parchment|pergamin|kalka)")
_TONED_PAPER = re.compile(rf"({_TONE})\w*\s+(laid |wove )?(paper|papier|karton)")
_PAPER_TONED = re.compile(rf"(papier|karton)\w*\s+({_TONE})")


def toned_by_words(medium: str) -> bool:
    """Whether the museum says the support is coloured: the word must speak
    of the support, not of the medium ("brown ink on paper" is not)."""
    text = medium.lower()
    after = _AFTER_ON.search(text)
    tail = after.group(1) if after else ""
    return bool(_TONED_TAIL.search(tail) or _TONED_PAPER.search(text) or _PAPER_TONED.search(text))


def sheet_state(sheet: Sheet, medium: str = "") -> SheetState:
    """Whether the sheet has yellowed: from its colour and the museum's
    words (agrees with a model's eye on 79 % of 300 works on paper; no
    model is asked). "hidden": too little bare sheet to read."""
    if sheet.share < 0.10:
        return "hidden"
    if toned_by_words(medium):
        return "toned"
    if sheet.chroma < FRESH:
        return "white"
    if 50 <= sheet.hue <= 105 and sheet.chroma <= 0.075 and sheet.lightness >= 0.62:
        return "yellowed"
    return "toned"


def _smoothstep(x: FloatArray) -> FloatArray:
    return (x * x * (3 - 2 * x)).astype(np.float32)


def deyellow(img: Image.Image, *, opaque: bool = False, long: int = SENT) -> Image.Image:
    """The work with its sheet as a well-kept one. ``opaque``: pastel and
    gouache cover the sheet, only where it shows through is changed."""
    rgb = img.convert("RGB")
    if max(rgb.size) > long:
        rgb.thumbnail((long, long), Image.Resampling.LANCZOS)
    read = _small(rgb, 640)
    seed = _seed(read)
    field, _ = _field(read, _mask(read, seed), seed)
    fresh = (_fresh(field, seed) / np.maximum(field, 1e-3)).astype(np.float32)
    # The field is smooth: found small, carried to the picture's size; the
    # sum itself goes a band of rows at a time, so a 2000 px sheet never
    # holds more than a few bands of floats beside these.
    source = np.asarray(rgb)
    height, width = source.shape[:2]

    def up(small: FloatArray) -> FloatArray:
        big = cv2.resize(small, (width, height), interpolation=cv2.INTER_CUBIC)
        return np.asarray(big, dtype=np.float32)

    field_y = up(luminance(field))
    field_ab = up(np.ascontiguousarray(linear_to_oklab(field)[..., 1:]))
    gain = up(fresh)
    out = np.empty_like(source)
    rows = 256
    for top in range(0, height, rows):
        end = min(top + rows, height)
        lin = u8_to_linear(source[top:end])
        sheet_y, sheet_ab, band_gain = field_y[top:end], field_ab[top:end], gain[top:end]
        y = luminance(lin)
        lab = linear_to_oklab(lin)
        # Lighter than the sheet and less yellow: white chalk, body colour.
        # They lie on it opaquely; the sheet's loss is not theirs.
        lighter = np.clip((y - sheet_y) / np.maximum(0.12 * sheet_y, 1e-3), 0, 1)
        whiter = np.clip((sheet_ab[..., 1] - lab[..., 2]) / 0.012, 0, 1)
        weight = 1 - lighter * whiter
        # Nearly black: thick ink, a border, the table under the sheet.
        weight = weight * _smoothstep(
            np.clip((y / np.maximum(sheet_y, 1e-3) - 0.06) / 0.24, 0, 1).astype(np.float32)
        )
        if opaque:
            away = np.linalg.norm(lab[..., 1:] - sheet_ab, axis=-1)
            weight = weight * np.exp(-0.5 * (away / 0.03) ** 2)
        out[top:end] = linear_to_u8(lin * (1 + weight[..., None] * (band_gain - 1)))
    return Image.fromarray(out)
