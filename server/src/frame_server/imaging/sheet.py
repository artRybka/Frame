"""The study sheet an analysis of a composition is drawn on: the picture as
a painter's synthesis, on the app's own page.

Mateusz 2026-11-11: the drawn analysis should look like "plastyczna praca
przygotowana na potrzeby takiej analizy", on "schematycznym szkicem obrazu
podkolorowanym akwarelą"; then, of the first sheets: the page must be the
app's background (light and dark), the pencil sketch had too many strokes
("jak kiepski komiks"), the watercolour was good, and "A co gdyby te
akwarele malować tak jak plamy na drodze dzieła, a rysunek jak rysunki
przy drodze dzieła?". Losing detail and shifting colours is fine with him:
"Taki szkic to ma być synteza, schemat dzieła na którym nanosi się zarys
analizy kompozycji".

So the sheet is:

- the page: ``Theme.paper`` of the app, flat (the app draws its own frame,
  grid, marks and notes around and over the picture this module makes);
- the picture's masses (about eight, by value first) as stains that spill
  like the ink stains of "Droga dzieła": a first pale wash where things
  happen, then each mass with a sharp wet edge where the pigment gathers
  and, in fragments, a paler second edge where the paper soaked; inside a
  stain the colour still moves a little, as the picture's does. Dark
  pictures are lifted into a watercolour's key, so that marks over them
  read. On the dark page the paint covers instead of staining and the
  picture stays dark;
- more general where less happens (Mateusz 2026-11-12: "Czy sama akwarela
  w tle mogłaby być ogólniejsza? Szczególnie tam gdzie mniej się dzieje?
  Może nawet nie zalewać plamą wszystkiego i fragmentami zostawiać tło
  podkładu"): there the small masses join the great ones, neighbours of
  nearly one colour are one stain, the stain is flat, and the page is left
  bare in fragments: most where the picture is nearest the page's own
  value (the lights on the light page, the darks on the dark one) and
  towards the field's edge, as a painter leaves a study unfinished;
- neighbours as he asked next (07:01): "Przerwy mogłyby pojawiać się czasem
  także pomiędzy plamami koloru. Teraz zawsze się nakładają jedna na drugą
  i powstaje ciemniejszy pas w każdym takim miejscu", and "jeżeli dwie
  plamy akwareli są do siebie bardzo podobne (np. niebieska ściana w
  pokoju van Gogha), to lepiej zlać je w jedną plamę". So neighbours very
  near in colour are one stain anywhere (:data:`SAME`); a stain's soaked
  edge lies on bare paper only, never over a neighbour; where two stains
  touch their wet fronts are faint; and here and there they keep apart and
  the page shows between them (:data:`GAP`);
- a few strokes of a nib (thick on the pull, thin where it lands and
  lifts), given by one who saw the picture (``ai.pen``); none when there
  are none.

After the first sheets on his phone (2026-11-12 09:47): "Z racji że linie
kredy rysujemy białe, to akwarelowe tło mogłoby być trochę ciemniejsze",
"Akwarelowy podkład może być jeszcze ogólniejszy", the pen "gdzieniegdzie
… 'szkicować'/kreskować ciemniejsze partie", and the sheet should "malować
/ rysować się na żywo". So (:data:`LOOK` 3):

- the masses are fewer and flatter (:data:`MASSES`, what happens inside a
  stain counts for less);
- the pen shades the darker parts with slanted lines, here and there
  (:func:`hatching`: measured, not asked of a model);
- the sheet is made as two layers (:func:`layers`): the stains, and what
  the pen drew with nothing around it, which the app lays down one after
  the other before the reader; :func:`render` is the two as one, for apps
  from before that.

That look also laid the light page's stains deeper and left less of it
bare. Seen on the page, he took the darker ground back (2026-11-12 10:54:
"akwarela jednak jaśniejsza - tak jak wcześniej"): :data:`LOOK` 4 lays the
stains as light as before it, and keeps the rest.

A sheet made by hand does not stop at its frame (2026-11-12 11:04: "plamy
akwareli mogą w jednym czy max 2 miejscach wylewać się i sięgać krawędzi
bocznej ekranu. podobnie kreska rysunku - pojedyncza może wystawać poza
kadr"). So (:data:`LOOK` 5) the layers are wider than the field by
:data:`BLEED` of it on each side, the page's margin beside the frame: in
one or two places a stain runs out over it (:func:`_spills`) and one
stroke that ends at a side goes on past it (:func:`_past`). What lies in
the field is as it was; :func:`field` is a layer cut back to it.

The margin first carried what lay by the frame as in a mirror, a second
chair beside the chair. Of that, 11:48: "wylewanie akwareli nie wygląda
dobrze - to musiałaby być jednolita plama, a nie odbicie lustrzane
skomplikowanego układu". So (:data:`LOOK` 6) what runs out is one stain
of one colour, the mass that lies at the frame there, and nothing of the
picture is carried beyond the frame.

And of the white linen of a portrait painted in the cream of the face
beside it (11:31: "(3) wskazuje i opisuje biel tkanin, a na szkicu jest
cielisty-kremowy"): what is white in the picture stays white on the
sheet (:func:`whites`), the paper itself on the light page, as one
paints in watercolour, and light paint on the dark one. An old varnish
yellows a picture's lights, so white is read without their cast.

Of a storm by Turner (2026-11-12 13:46): "na szkicu bardzo brakuje ciemnej
plamy nieba. to istotny element, a akwarela go pominęła. chyba
błękit/prześwit nieba też powinien się pokazać w akwareli", and of the
way the stains are painted altogether: "Szkic musi oddawać istotę i ideę
obrazu". The sheet had lost what that picture is made of in four places,
and :data:`LOOK` 7 mends each:

- stains of nearly one colour were joined one neighbour at a time, so a
  picture whose tones run into one another came out as a single stain
  from its darkest to its lightest. A stain is now one only while its two
  furthest parts are near (:data:`SAME`, :func:`_joined`);
- the picture was drawn out place by place before its masses were read,
  which made a great dark sky as light as the sea under it. Its key is
  one tone curve now (:func:`_keyed`); only what is white is still looked
  for in the picture drawn out;
- a quiet stain at the field's edge was left as paper however dark it
  was. What is far from the page's own value is always painted
  (:data:`BARE_FAR`);
- masses are sorted by value first, and under an old varnish every hue is
  a brown: the opening of blue was cloud. Hues are read against the
  picture's own (:func:`hues`), a place of another hue inside a mass is
  a stain of its own (:func:`_own`), and such a picture's paints are
  mixed further apart with its cast thinned (:func:`_mixed`).

No model is asked here; about four seconds a sheet (``sheets.Sheets``
makes them ahead).
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image

from . import trace

#: Pixels, as cv2 hands them about (its stubs know no dtypes).
Array = npt.NDArray[Any]
#: A stroke of the pen: its points (fractions of the picture), whether it
#: keeps its corners, whether it closes.
PenStroke = tuple[Sequence[tuple[float, float]], bool, bool]
#: A line the pen draws: its points (fractions of the field), whether it
#: keeps its corners, whether it closes, how heavy it is (0…1).
PenLine = tuple[Sequence[tuple[float, float]], bool, bool, float]

#: Raised when the look changes, so that sheets made before are made again.
LOOK = 8
#: The sheet's longer side.
LONG = 1500
#: The app's page and ink (``Theme.paper``, ``Theme.ink``): light, dark.
PAGE = {False: (0xF5, 0xF1, 0xEA), True: (0x12, 0x11, 0x10)}
INK = {False: (0x1D, 0x1B, 0x18), True: (0xF1, 0xEC, 0xE4)}
#: The darkest a wash gets (of the page's light), so that marks over it read.
LIFT = 0.15
#: The masses a picture is gathered into, and the least a mass is (of the
#: picture): a smaller one joins what surrounds it.
MASSES = 6
LEAST = 0.012
#: Where nothing happens a mass must be this much of the picture, and
#: neighbours there no further apart than this (CIE Lab) are one stain.
QUIET_LEAST = 0.06
ALIKE = 20.0
#: Neighbours this near in colour are one stain anywhere. A stain is one
#: only while all of it is this near: its two furthest parts, not each
#: part and the next (so a picture whose tones run into one another, a
#: storm in browns and greys, is not one stain from its darkest to its
#: lightest). What is left over between two stains, smaller than
#: :data:`PATCH` of the picture, still joins the one it is near as a
#: whole: a wall is not made of patches.
SAME = 16.0
PATCH = 0.04
#: Colours are told apart against the picture's own: where its hues lie
#: close together (their spread: how far from its middle hue nine tenths
#: of it lie, CIE a/b) they are read as if they spread this far, at most
#: :data:`HUE_GAIN` times further apart than they are. So the grey-blue
#: opening in a brown sky is another colour than the brown, as it is to
#: the eye. A picture of one colour (a drawing in sepia, spread under
#: :data:`HUE_ONE`) has no hues to tell apart, and what lies between is
#: read part way.
HUE_SPREAD = 22.0
HUE_GAIN = 2.5
HUE_ONE = (3.5, 7.0)
#: The paints of such a picture are mixed further apart in hue too (by
#: this much of how its colours are read), and its own cast (the middle
#: hue, when that is a varnish's yellow-brown, :data:`WHITE_WARM`) is
#: thinned to this much at the most: in its lights and middle tones,
#: where hue is seen. Its darks (under the first
#: of :data:`HUE_LIGHT`, CIE L; wholly from the second) keep their own
#: colour: what little hue a dark has is chance, and a brown shadow mixed
#: away from brown is violet.
HUE_PAINT = 0.6
HUE_CAST = 0.3
HUE_LIGHT = (30.0, 58.0)
#: A place inside a mass whose hue is this far from the mass's own (as the
#: picture's hues are read) is a stain of its own, however near in value:
#: the opening of blue in a sky of cloud (Mateusz 2026-11-12 13:46:
#: "chyba błękit/prześwit nieba też powinien się pokazać w akwareli").
#: Counted in its lights and middle tones only (:data:`HUE_LIGHT`), not
#: smaller than this much of the picture, and the greatest few only.
OWN_HUE = 14.0
OWN_LEAST = 0.008
OWN_MOST = 3
#: The first pale wash under the stains, where things happen.
FIRST = 0.3
#: What decides where the page is left bare in a quiet place: how near the
#: stain is to the page's own value, how near the field's edge, and chance;
#: bare where they come to more than :data:`BARE`.
BARE_NEAR = 0.7
BARE_RIM = 0.6
BARE_CHANCE = 0.45
BARE = 0.55
#: How far two neighbouring stains keep apart at most, where they do (of
#: the blurred edge between them: about three pixels each).
GAP = 0.38
#: How far under :data:`BARE` the wash begins to run thin, and the most of
#: the field that is left bare (a picture that is all sky is still painted).
BARE_THIN = 0.2
BARE_MOST = 0.3
#: A stain far from the page's own value is not left out, however quiet
#: the place and however near the edge: a great dark sky is what the
#: picture is made of (Mateusz 2026-11-12 13:46, of a storm by Turner whose
#: sky the sheet left as paper: "na szkicu bardzo brakuje ciemnej plamy
#: nieba. to istotny element, a akwarela go pominęła"). From the first of
#: these (how far the stain is from the page, CIE Lab, on the light page)
#: the edge and chance count for less, from the second for nothing.
BARE_FAR = (40.0, 54.0)
#: What is white in the picture stays white on the sheet: the paper itself
#: on the light page, light paint on the dark one. White is what is this
#: light (CIE L of the picture in the sheet's key) and this plain once the
#: cast of the picture's own lights is taken off (an old varnish yellows
#: its linen), unless those lights are more coloured than
#: :data:`WHITE_CAST` or not a varnish's yellow (:data:`WHITE_WARM`, the
#: hue's angle in Lab): a lamp, a sunset, a blue sky are a colour. A white
#: place smaller than :data:`WHITE_LEAST` of the picture is let go, and no
#: more than :data:`WHITE_MOST` of it is white (the lightest of it).
WHITE_LIGHT = 80.0
WHITE_PLAIN = 8.0
WHITE_CAST = 24.0
WHITE_WARM = (68.0, 102.0)
WHITE_LEAST = 0.002
WHITE_MOST = 0.25
#: How little of the picture's own tone the paper keeps where it is white
#: (its folds), and the light paint that stands for white on the dark page.
WHITE_TONE = 0.045
WHITE_PAINT = (0.91, 0.89, 0.85)
#: How much of the ink a stroke of the nib lays, and its width.
NIB_INK = 0.66
NIB = 3.3
#: The lightest line of the drawing is this much of the nib's width (a
#: detail; a form's heavy contour is the whole of it).
NIB_LIGHT = 0.45
#: The picture's own contours are drawn when it is at least this many
#: pixels on its shorter side, and the model's strokes are drawn with them
#: when they come to less line than this (in the picture's longer sides).
DRAWN_SIDE = 160
DRAWN_LEAST = 1.2
# How many of the pen's lines an app is given to draw its layer along.
PATHS = 64
#: The darker parts are hatched here and there: what counts as dark (the
#: darkest share of the picture, and at least this much under its middle
#: value, of 1), the least such a part is (of the picture), the lines'
#: slant (degrees from the horizontal, as a right hand hatches), how far
#: apart they lie, their least length (pixels), their width and ink.
HATCH_SHARE = 0.2
HATCH_UNDER = 0.14
HATCH_LEAST = 0.006
HATCH_SLANT = 56.0
HATCH_APART = 15.0
HATCH_SHORT = 26.0
HATCH_NIB = 1.5
HATCH_INK = 0.5
#: How much wider than the field the layers are on each side (of the
#: field's width): the page's margin there, into which a stain may run and
#: a stroke go on. A phone's margin is about 0.055 of the sheet, so what
#: reaches the layer's end is cut by the screen's edge there.
BLEED = 0.08
#: Where the stains run out: in one place, or as often as not in two; half
#: as high as this (of the field's shorter side); as far as this (of the
#: margin) where they run furthest; and they join the field from this many
#: pixels within it, where its ragged edge has stopped the paint.
SPILL_TWO = 0.5
SPILL_HALF = (0.1, 0.17)
SPILL_FAR = 1.25
SPILL_ROOT = 18
#: The stroke that goes on past the frame: one that ends this near a side
#: (of the width) and heads out of it at least this much (of its
#: direction); it ends this far into the margin.
PAST_NEAR = 0.035
PAST_HEADING = 0.35
PAST_FAR = (0.5, 0.85)


def _colour(rgb: tuple[int, int, int]) -> Array:
    return np.array(rgb, np.float32) / 255


def _noise(shape: tuple[int, int], sigma: float, rng: np.random.Generator) -> Array:
    """Smooth noise in -1…1 with features about ``sigma`` pixels."""
    h, w = shape
    if sigma > 6:  # made small and blown up: the same look, much faster
        k = sigma / 3
        raw = rng.standard_normal((max(int(h / k) + 2, 4), max(int(w / k) + 2, 4)))
        small = cv2.GaussianBlur(raw.astype(np.float32), (0, 0), 3)
        n = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    else:
        n = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), sigma)
    return n / (np.abs(n).max() + 1e-6)


def _keyed(rgb: Array, drawn: bool = False) -> Array:
    """The picture in a watercolour's key: its darks lifted, as one tone
    curve for the whole of it. ``drawn``: drawn out place by place first,
    so that a dark varnish hides less. The stains were once made of the
    picture so drawn, and a great dark sky came out as light as the sea
    under it; a picture's light and dark are what a study is of, so only
    what is white is still looked for that way (the foam of a wave on
    toned paper is its white, though the sheet's margin is lighter)."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    if drawn:
        lab[..., 0] = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(6, 6)).apply(lab[..., 0])
    light = lab[..., 0].astype(np.float32) / 255
    lo, hi = np.percentile(light, (1.5, 98.5))
    light = np.clip((light - lo) / max(hi - lo, 0.2), 0, 1) * 0.9
    middle = float(np.clip(np.median(light), 0.08, 0.92))
    if middle < 0.38:
        light = light ** float(np.clip(math.log(0.44) / math.log(middle), 0.55, 1.0))
    lab[..., 0] = np.clip(light * 255, 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def _flat(rgb: Array, side: int, spatial: int, colour: int) -> Array:
    """The picture without its small things, ``side`` pixels long (BGR)."""
    scale = side / max(rgb.shape[:2])
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    flat = cv2.pyrMeanShiftFiltering(
        cv2.cvtColor(small, cv2.COLOR_RGB2BGR), spatial, colour, maxLevel=2
    )
    return cv2.medianBlur(flat, 5)


def busy(rgb: Array, shape: tuple[int, int]) -> Array:
    """How much happens at each place of the picture, from 0 (a plain sky,
    a wall, a dark ground) to 1 (figures, foliage, a crowd), as a map of
    ``shape``: how many edges lie around the place, against the picture's
    own busiest parts but never against less than a plain picture has."""
    scale = 240 / max(rgb.shape[:2])
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(cv2.GaussianBlur(small, (0, 0), 1.2), cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100 / 255
    edges = np.zeros(lab.shape[:2], np.float32)
    for channel in range(3):
        gx = cv2.Sobel(lab[..., channel], cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(lab[..., channel], cv2.CV_32F, 0, 1, ksize=3)
        edges += gx * gx + gy * gy
    around = cv2.GaussianBlur(np.sqrt(edges), (0, 0), 9)
    most = max(float(np.percentile(around, 90)), 14.0)
    t = np.clip((around / most - 0.22) / 0.5, 0, 1)
    return cv2.resize(t * t * (3 - 2 * t), (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)


def hues(lab: Array) -> tuple[Array, float]:
    """The picture's middle hue (CIE a/b about 0) and how many times
    further apart than they are its hues are read (1 to :data:`HUE_GAIN`):
    more the closer together they lie, but not in a picture of one colour.
    ``lab``: CIE Lab as cv2 has it in bytes (a/b about 128)."""
    ab = lab[..., 1:].reshape(-1, 2).astype(np.float32) - 128
    middle = np.median(ab, axis=0)
    spread = float(np.percentile(np.linalg.norm(ab - middle, axis=1), 90))
    gain = float(np.clip(HUE_SPREAD / max(spread, 1e-3), 1, HUE_GAIN))
    some = float(np.clip((spread - HUE_ONE[0]) / (HUE_ONE[1] - HUE_ONE[0]), 0, 1))
    return middle, 1 + (gain - 1) * some


def _joined(piece: Array, count: int, lab: Array, quiet: Array) -> Array:
    """The masses with neighbours of nearly one colour made one (anywhere
    when very near, further apart where little happens): the nearest pair
    first, until none is near enough. Near is measured between the two
    furthest parts of what would be one stain; then a small leftover joins
    the neighbour whose colour as a whole it is near."""
    flat = piece.ravel()
    area = np.bincount(flat, minlength=count + 1).astype(np.float64)
    total = np.stack(
        [np.bincount(flat, lab[..., k].ravel(), minlength=count + 1) for k in range(3)], axis=1
    )
    still = np.bincount(flat, quiet.ravel(), minlength=count + 1)
    own = total / np.maximum(area, 1)[:, None]
    # how far apart the furthest parts of two stains are (each a part at first)
    far = np.linalg.norm(own[:, None] - own[None], axis=2)
    pairs: set[tuple[int, int]] = set()
    for one, other in ((piece[:, :-1], piece[:, 1:]), (piece[:-1], piece[1:])):
        differ = one != other
        lo = np.minimum(one[differ], other[differ])
        hi = np.maximum(one[differ], other[differ])
        pairs.update(zip(lo.tolist(), hi.tolist(), strict=True))
    to = np.arange(count + 1)
    small = PATCH * piece.size
    for whole in (True, False):  # the stains, then what is left over between them
        while pairs:
            best: tuple[int, int] | None = None
            nearest = 1.0
            for a, b in pairs:
                if whole:
                    apart = float(far[a, b])
                elif min(area[a], area[b]) < small:
                    apart = float(np.linalg.norm(total[a] / area[a] - total[b] / area[b]))
                else:
                    continue
                calm = float(min(still[a] / area[a], still[b] / area[b]))
                limit = max(SAME, ALIKE * calm if calm > 0.5 else 0.0)
                if apart < nearest * limit:
                    best, nearest = (a, b), apart / limit
            if best is None:
                break
            a, b = best
            area[a] += area[b]
            total[a] += total[b]
            still[a] += still[b]
            far[a] = far[:, a] = np.maximum(far[a], far[b])
            to[to == b] = a
            moved = ((int(to[p]), int(to[q])) for p, q in pairs)
            pairs = {(min(x, y), max(x, y)) for x, y in moved if x != y}
    return to[piece]


def _own(piece: Array, count: int, lab: Array) -> tuple[Array, int]:
    """The masses with the places of another hue inside them taken out
    (:data:`OWN_HUE`): masses are sorted by value first, so a patch of blue
    as light as the cloud beside it was cloud. Such a place is a mass of
    its own, unless it is the colour of a mass it touches (a strip of the
    neighbour, where the two were not parted cleanly): then it is that
    one's."""
    hue = lab[..., 1:]
    seen = np.clip((lab[..., 0] - HUE_LIGHT[0]) / (HUE_LIGHT[1] - HUE_LIGHT[0]), 0, 1)
    middle = {c: np.median(lab[piece == c], axis=0) for c in range(1, count + 1)}
    found: list[tuple[int, Array]] = []
    round_ = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    was = piece
    for c in range(1, count + 1):
        mass = was == c
        off = np.linalg.norm(hue - middle[c][1:], axis=2) * seen
        other = cv2.morphologyEx((mass & (off > OWN_HUE)).astype(np.uint8), cv2.MORPH_OPEN, round_)
        n, comp, stats, _ = cv2.connectedComponentsWithStats(other, connectivity=8)
        for k in range(1, n):
            if stats[k, cv2.CC_STAT_AREA] < OWN_LEAST * piece.size:
                continue
            whole = np.zeros(piece.shape, np.uint8)  # the place without its holes
            outline, _ = cv2.findContours(
                (comp == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
            )
            cv2.drawContours(whole, outline, -1, 1, cv2.FILLED)
            place = (whole > 0) & mass
            if np.median(off[place]) <= OWN_HUE:  # (a ring round the mass's own is not one)
                continue
            colour = np.median(lab[place], axis=0)
            beside = np.unique(was[(cv2.dilate(whole, np.ones((5, 5), np.uint8)) > 0) & ~mass])
            apart = {int(b): float(np.linalg.norm(colour - middle[int(b)])) for b in beside}
            nearest = min(apart, key=lambda b: apart[b], default=0)
            if nearest and apart[nearest] < SAME:
                piece = np.where(place, nearest, piece)
            else:
                found.append((int(place.sum()), place))
    for _, place in sorted(found, key=lambda entry: -entry[0])[:OWN_MOST]:
        count += 1
        piece = np.where(place, count, piece)
    return piece, count


def _plain(rgb: Array) -> Array:
    """The picture as its masses are read from it (BGR, 560 pixels long)."""
    return _flat(rgb, 560, 16, 40)


def whites(rgb: Array, flat: Array | None = None) -> Array:
    """Where the picture is white, as a small map (of :func:`masses`'s
    shape): light and plain, seen without the cast of its own lights."""
    flat = _plain(rgb) if flat is None else flat
    lab = cv2.cvtColor(flat, cv2.COLOR_BGR2LAB).astype(np.float32)
    light = lab[..., 0] * (100 / 255)
    ab = lab[..., 1:] - 128
    top = light >= np.percentile(light, 98)
    cast = np.median(ab[top], axis=0)
    hue = math.degrees(math.atan2(float(cast[1]), float(cast[0])))
    if float(np.hypot(*cast)) > WHITE_CAST or not WHITE_WARM[0] <= hue <= WHITE_WARM[1]:
        cast = np.zeros(2, np.float32)  # the lights are a colour, not a varnish
    level = max(float(light[top].mean()), 1.0)
    plain = np.linalg.norm(ab - cast * (light / level)[..., None], axis=2)
    found = (light >= WHITE_LIGHT) & (plain <= WHITE_PLAIN)
    if found.mean() > WHITE_MOST:  # the lightest of it
        found &= light >= np.quantile(light[found], 1 - WHITE_MOST / float(found.mean()))
    found = cv2.morphologyEx(found.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, comp, stats, _ = cv2.connectedComponentsWithStats(found, connectivity=8)
    kept = np.zeros(n, bool)
    kept[1:] = stats[1:, cv2.CC_STAT_AREA] >= WHITE_LEAST * found.size
    return kept[comp]


def masses(rgb: Array, seed: int = 1, flat: Array | None = None) -> tuple[Array, Array]:
    """The picture's masses: a small map of which mass each place belongs to
    (from 1) and each mass's colour. What is too small to be a mass joins
    the mass around it, and where little happens a mass must be greater and
    neighbours of nearly one colour are one."""
    flat = _plain(rgb) if flat is None else flat
    quiet = 1 - busy(rgb, flat.shape[:2])
    true = cv2.cvtColor(flat, cv2.COLOR_BGR2LAB).astype(np.float32)
    middle, gain = hues(true)
    true[..., 0] *= 100 / 255
    true[..., 1:] = (true[..., 1:] - 128 - middle) * gain  # as the picture's hues are read
    lab = true.copy()
    lab[..., 0] *= 255 / 100 * 1.3  # a painter sorts by value first
    cv2.setRNGSeed(seed)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, tags, _ = cv2.kmeans(  # type: ignore[call-overload]
        lab.reshape(-1, 3), MASSES, None, criteria, 4, cv2.KMEANS_PP_CENTERS
    )
    tags = tags.reshape(lab.shape[:2]).astype(np.int32)
    piece = np.zeros(tags.shape, np.int32)
    count = 0
    for tag in range(MASSES):  # connected pieces of each colour; the small ones are let go
        n, comp, stats, _ = cv2.connectedComponentsWithStats(
            (tags == tag).astype(np.uint8), connectivity=4
        )
        calm = np.bincount(comp.ravel(), quiet.ravel(), minlength=n)
        for c in range(1, n):
            area = stats[c, cv2.CC_STAT_AREA]
            least = LEAST + (QUIET_LEAST - LEAST) * calm[c] / area
            if area >= least * tags.size:
                count += 1
                piece[comp == c] = count
    if count == 0:  # one flat colour: one mass
        piece[:] = 1
        count = 1
    loose = (piece == 0).astype(np.uint8)
    if loose.any():
        _, near = cv2.distanceTransformWithLabels(
            loose, cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL
        )
        lut = np.zeros(int(near.max()) + 1, np.int32)
        lut[near[loose == 0]] = piece[loose == 0]
        piece = lut[near]
    joined = _joined(piece, count, true, quiet)
    kept = np.unique(joined)
    piece = np.searchsorted(kept, joined).astype(np.int32) + 1
    count = len(kept)
    piece, count = _own(piece, count, true)
    plain = cv2.cvtColor(flat, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    colours = np.zeros((count + 1, 3), np.float32)
    for c in range(1, count + 1):
        colours[c] = np.median(plain[piece == c], axis=0)
    return piece, colours


def _mixed(colours: Array, middle: Array, gain: float) -> Array:
    """The masses' colours mixed as the picture's hues are read
    (:func:`hues`): further apart about its middle hue, and that cast
    thinned, where they lie close together. Their values stay."""
    if gain <= 1:
        return colours
    apart = 1 + (gain - 1) * HUE_PAINT
    hue = math.degrees(math.atan2(float(middle[1]), float(middle[0])))
    cast = 1.0  # a picture all in green is green, not under a varnish
    if WHITE_WARM[0] <= hue <= WHITE_WARM[1]:
        cast = 1 - (1 - HUE_CAST) * (gain - 1) / (HUE_GAIN - 1)
    lab = cv2.cvtColor(colours.reshape(1, -1, 3).astype(np.float32), cv2.COLOR_RGB2LAB)
    seen = np.clip((lab[..., :1] - HUE_LIGHT[0]) / (HUE_LIGHT[1] - HUE_LIGHT[0]), 0, 1)
    read = middle * cast + (lab[..., 1:] - middle) * apart
    lab[..., 1:] += seen * (read - lab[..., 1:])
    return np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB).reshape(-1, 3), 0, 1)


def _pigment(colours: Array) -> Array:
    """The masses' colours as washes: a little purer, never as dark as oil."""
    hsv = cv2.cvtColor(colours.reshape(1, -1, 3), cv2.COLOR_RGB2HSV)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.2, 0, 1)
    hsv[..., 2] = LIFT + (1 - LIFT) * hsv[..., 2]
    return np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).reshape(-1, 3) ** 0.84, 0.02, 1)


def _steps(v: Array, n: int = 5, soft: float = 0.35) -> Array:
    """Values gathered softly into ``n`` steps (a painter's few tones)."""
    x = v * n
    f = np.floor(x)
    t = np.clip((x - f - 0.5) / soft + 0.5, 0, 1)
    return (f + t * t * (3 - 2 * t)) / n


def _moving(rgb: Array, rng: np.random.Generator) -> Array:
    """The picture's own gradations as soft washes at full size (how much
    light each lets through): what moves inside a stain."""
    h, w = rgb.shape[:2]
    flat = cv2.cvtColor(_flat(rgb, 520, 16, 42), cv2.COLOR_BGR2RGB)
    img = cv2.resize(flat, (w, h), interpolation=cv2.INTER_CUBIC)
    # paint does not keep to the drawing: pushed about a little
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    dx, dy = _noise((h, w), 30, rng) * 3.5, _noise((h, w), 30, rng) * 3.5
    img = cv2.remap(img, gx + dx, gy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    soft = cv2.edgePreservingFilter(
        cv2.cvtColor(img, cv2.COLOR_RGB2BGR), flags=cv2.RECURS_FILTER, sigma_s=48, sigma_r=0.34
    )
    hsv = cv2.cvtColor(
        cv2.cvtColor(soft, cv2.COLOR_BGR2RGB).astype(np.float32) / 255, cv2.COLOR_RGB2HSV
    )
    hsv[..., 2] = 0.24 + 0.76 * _steps(hsv[..., 2])
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.1, 0, 1)
    return np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.02, 1) ** 0.8


def _chaikin(points: Array, times: int = 3) -> Array:
    """A line through the points with its corners cut."""
    p = points
    for _ in range(times):
        if len(p) < 3:
            break
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        p = np.concatenate([p[:1], np.stack([q, r], axis=1).reshape(-1, 2), p[-1:]])
    return p


def _nib(layer: Array, points: Array, rng: np.random.Generator, width: float) -> None:
    """One stroke of a nib: thin where it lands and lifts, fuller between,
    fuller still on the pull than on the push."""
    seg = np.hypot(*np.diff(points, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < 4:
        return
    t = np.linspace(0, s[-1], max(int(s[-1] / 3), 2))
    p = np.stack([np.interp(t, s, points[:, 0]), np.interp(t, s, points[:, 1])], axis=1)
    n = len(p)
    d = np.gradient(p, axis=0)
    angle = np.arctan2(d[:, 1], d[:, 0])
    along = np.linspace(0, 1, n)
    body = np.sin(np.pi * along) ** 0.45
    pull = 0.72 + 0.4 * np.abs(np.sin(angle - 0.6))  # the nib is cut at an angle
    sway = np.interp(along, np.linspace(0, 1, 7), rng.uniform(0.85, 1.1, 7))
    w = np.maximum(width * (0.3 + 0.7 * body) * pull * sway, 1.0)
    q = np.round(p * 4).astype(np.int32)
    for i in range(n - 1):
        a, b = (int(q[i][0]), int(q[i][1])), (int(q[i + 1][0]), int(q[i + 1][1]))
        cv2.line(layer, a, b, 1.0, round(float(w[i]) * 2), cv2.LINE_AA, 2)


def hatching(rgb: Array, rng: np.random.Generator) -> list[Array]:
    """The lines that shade the picture's darker parts, here and there
    (Mateusz 2026-11-12, of the pen: "Gdzieniegdzie mogą też szkicować /
    kreskować ciemniejsze partie"): parallel, slanted as a right hand lays
    them, each as long as the dark part is wide there. Measured, not asked
    of a model: what is dark is plain to see."""
    h, w = rgb.shape[:2]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32) / 255
    light: Array = cv2.GaussianBlur(lab, (0, 0), 9)
    level = min(float(np.quantile(light, HATCH_SHARE)), float(np.median(light)) - HATCH_UNDER)
    dark = cv2.morphologyEx(
        (light < level).astype(np.uint8),
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)),
    )
    n, comp, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= HATCH_LEAST * h * w
    here = _noise((h, w), 0.09 * max(h, w), rng) > -0.05  # not all of a dark part
    mask = keep[comp] & here
    if not mask.any():
        return []
    slant = math.radians(HATCH_SLANT + float(rng.uniform(-5, 5)))
    along = np.array([math.cos(slant), -math.sin(slant)])  # up and to the right
    across = np.array([math.sin(slant), math.cos(slant)])
    corners = np.array([(0, 0), (w, 0), (0, h), (w, h)], np.float64)
    u0, u1 = (corners @ along).min(), (corners @ along).max()
    v0, v1 = (corners @ across).min(), (corners @ across).max()
    u = np.arange(u0, u1, 2.0)
    lines: list[Array] = []
    for v in np.arange(v0 + HATCH_APART / 2, v1, HATCH_APART):
        v = v + float(rng.uniform(-0.18, 0.18)) * HATCH_APART
        spots = u[:, None] * along + v * across
        x, y = np.round(spots[:, 0]).astype(int), np.round(spots[:, 1]).astype(int)
        on = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        on[on] = mask[y[on], x[on]]
        edges = np.flatnonzero(np.diff(np.concatenate([[0], on.astype(np.int8), [0]])))
        for start, end in zip(edges[::2], edges[1::2], strict=True):
            lift = rng.uniform(0, 5, 2)  # a hand does not stop on the edge
            a, b = u[start] + lift[0], u[end - 1] - lift[1]
            if b - a < HATCH_SHORT:
                continue
            bow = float(rng.uniform(-1.5, 1.5))
            lines.append(
                np.array(
                    [
                        a * along + v * across,
                        (a + b) / 2 * along + (v + bow) * across,
                        b * along + v * across,
                    ],
                    np.float32,
                )
            )
    return lines


def bleed(width: int) -> int:
    """How many pixels wider than a field this wide a layer is, each side."""
    return round(BLEED * width)


def field(layer: Image.Image) -> Image.Image:
    """A layer (:func:`layers`) cut back to the field: what an app from
    before the margin lays in the frame."""
    wide = layer.width
    guess = round(wide / (1 + 2 * BLEED))
    width = next((w for w in range(guess - 3, guess + 4) if w + 2 * bleed(w) == wide), guess)
    side = (wide - width) // 2
    return layer.crop((side, 0, side + width, layer.height))


def _sides(piece: Array, white: Array, height: int) -> tuple[Array, Array]:
    """Which mass lies at the field's left and right edge at each of
    ``height`` rows: the first that is not white from the edge inwards (a
    print's own margin is white), 0 where the picture is white well into
    it (paper does not run)."""
    label = np.where(white, 0, piece)
    rows = np.minimum(np.arange(height) * label.shape[0] // height, label.shape[0] - 1)
    deep = max(4, round(0.04 * label.shape[1]))
    found = []
    for strip in (label[:, :deep], label[:, ::-1][:, :deep]):
        first = (strip > 0).argmax(axis=1)
        found.append(strip[np.arange(len(strip)), first][rows])
    return found[0], found[1]


def _spills(
    painted: Array, margin: int, rng: np.random.Generator, sides: tuple[Array, Array]
) -> tuple[Array, Array]:
    """Where the stains run out of the field over the margin beside it: a
    tongue in one place or two, on a side where the field is painted up to
    its edge. As wide as the field with its two margins; 1 where a stain
    goes on, from a little within the field outwards, and with it which
    mass it is: what runs out is one stain of one colour (``sides``: the
    mass at each side's rows), where it can be from a place where that one
    mass alone lies along the edge (Mateusz 2026-11-12 11:48, of the
    margin that mirrored the picture: "to musiałaby być jednolita plama, a
    nie odbicie lustrzane skomplikowanego układu")."""
    h, w = painted.shape
    out = np.zeros((h, w + 2 * margin), np.float32)
    whose = np.zeros(out.shape, np.int32)
    if margin < 8:
        return out, whose
    half = rng.uniform(*SPILL_HALF, 2) * min(h, w)
    band = max(min(24, w // 8), 1)
    places: list[
        tuple[int, int, float]
    ] = []  # the side (0 left, 1 right), the row, half its height
    for k in range(2 if rng.random() < SPILL_TWO else 1):
        found: list[tuple[int, int]] = []
        wish = float(half[k])
        r = wish
        # one mass along the tongue's whole root, a narrower tongue sooner
        # than two masses; only then wherever the paint reaches the edge
        for r, one in ((wish, True), (0.75 * wish, True), (0.55 * wish, True), (wish, False)):
            for side in (0, 1):
                edge = painted[:, :band] if side == 0 else painted[:, w - band :]
                ids = sides[side]
                full = ((edge.mean(axis=1) > 0.9) & (ids > 0)).astype(np.uint8).reshape(-1, 1)
                reach = int(r) | 1
                fits = cv2.erode(full, np.ones((2 * reach + 1, 1), np.uint8)).ravel() > 0
                fits[: int(0.06 * h) + reach] = False
                fits[h - int(0.06 * h) - reach :] = False
                if one:
                    turns = np.concatenate([[0], np.cumsum(ids[1:] != ids[:-1])])
                    rows = np.arange(h)
                    lo, hi = np.clip(rows - reach, 0, h - 1), np.clip(rows + reach, 0, h - 1)
                    fits &= turns[lo] == turns[hi]
                for row in np.flatnonzero(fits).tolist():
                    if all(s != side or abs(row - at) > 2 * (r + other) for s, at, other in places):
                        found.append((side, row))
            if found:
                break
        if not found:
            break
        # the other side first, when one has run out already
        fresh = [f for f in found if all(f[0] != s for s, _, _ in places)] or found
        places.append((*fresh[int(rng.integers(len(fresh)))], r))
    if not places:
        return out, whose
    yy, xx = np.mgrid[0:h, 0 : w + 2 * margin].astype(np.float32)
    # no two run out alike: the front wanders, slowly and in small
    ragged = _noise(out.shape, 0.2 * margin, rng) * 0.3 * margin + _noise(out.shape, 5, rng) * 3
    for where, row, r in places:
        beyond = (margin - xx) if where == 0 else (xx - (margin + w - 1))  # out of the field
        # a round front, widest where it leaves the field
        shape = np.clip(1 - np.abs((yy - row) / r) ** 2.6, 0, 1)
        far = SPILL_FAR * margin * shape + ragged * np.clip(shape * 3, 0, 1)
        tongue = np.clip((far - beyond) / 1.5, 0, 1) * (shape > 0)
        tongue = np.where(beyond > -SPILL_ROOT, tongue, 0)
        out = np.maximum(out, tongue)
        root = sides[where][max(int(row - r), 0) : int(row + r) + 1]
        root = root[root > 0]
        if len(root):
            whose[(tongue > 0) & (beyond > 0)] = int(np.bincount(root).argmax())
    return out, whose


def _past(
    strokes: Sequence[PenStroke], size: tuple[int, int], margin: int, rng: np.random.Generator
) -> tuple[int, Array] | None:
    """The one stroke that goes on past the frame, and its points (pixels
    of the field) with that end carried out into the margin: one that
    ends at a side and heads out of it. None when no stroke does."""
    w, h = size
    found: list[tuple[int, Array]] = []
    for at, (points, _, closed) in enumerate(strokes):
        pts = np.asarray(points, np.float32).reshape(-1, 2) * (w, h)
        if closed or len(pts) < 2:
            continue
        for end, before in ((0, 1), (len(pts) - 1, len(pts) - 2)):
            way = pts[end] - pts[before]
            long = float(np.hypot(*way))
            if long < 1:
                continue
            way = way / long
            x = float(pts[end][0])
            left = x <= PAST_NEAR * w and way[0] < -PAST_HEADING
            right = x >= (1 - PAST_NEAR) * w and way[0] > PAST_HEADING
            if not (left or right):
                continue
            gap = x if left else (w - 1 - x)  # still within the field
            run = (gap + float(rng.uniform(*PAST_FAR)) * margin) / abs(float(way[0]))
            tip = (pts[end] + way * min(run, 2.2 * margin)).reshape(1, 2)
            found.append((at, np.concatenate([tip, pts] if end == 0 else [pts, tip])))
    if not found or margin < 8:
        return None
    return found[int(rng.integers(len(found)))]


def pen_lines(
    picture: Image.Image, strokes: Sequence[PenStroke] = (), aside: Sequence[bool] = ()
) -> list[PenLine]:
    """What the pen draws of this picture (its field alone): the picture's
    own contours (``trace.drawing``), exact where its subject is, which the
    strokes of the one who saw it say (``aside``: which of them are not of
    the subject). A picture that gives too little to draw (a fog) gets
    those strokes themselves as well; with no strokes and no contours the
    sheet is the stains alone."""
    guide = [
        (points, closed, not (at < len(aside) and aside[at]))
        for at, (points, _, closed) in enumerate(strokes)
    ]
    src = np.asarray(picture.convert("RGB"))
    try:
        drawn = trace.drawing(src, guide) if min(src.shape[:2]) >= DRAWN_SIDE else []
    except Exception:  # the measure fails: the strokes alone, as before it
        drawn = []
    lines: list[PenLine] = [(points, True, False, weight) for points, weight in drawn]
    if trace.run(drawn, (src.shape[1], src.shape[0])) < DRAWN_LEAST:
        lines = [(points, sharp, closed, 1.0) for points, sharp, closed in strokes] + lines
    return lines


def paths(lines: Sequence[PenLine], most: int = 10, count: int = PATHS) -> list[PenStroke]:
    """The pen's lines roughly, in a few points each: what an app draws
    the pen's layer along as the sheet draws itself. The first ``count``
    of them (the forms come first): the small lines beside them come with
    the shading, as whatever the strokes left does."""
    out: list[PenStroke] = []
    for points, sharp, closed, _ in lines[:count]:
        at: Array = np.asarray(points, np.float32).reshape(-1, 1, 2)
        fine = 0.004
        while len(at) > most:
            few = cv2.approxPolyDP(at, fine, closed)
            if len(few) <= most:
                at = few
                break
            fine *= 1.5
        out.append(([(float(x), float(y)) for x, y in at.reshape(-1, 2)], sharp, closed))
    return out


def layers(
    picture: Image.Image,
    strokes: Sequence[PenStroke] = (),
    *,
    dark: bool = False,
    seed: int = 1,
    aside: Sequence[bool] = (),
    lines: Sequence[PenLine] | None = None,
) -> tuple[Image.Image, Image.Image]:
    """The picture (its field alone) as the sheet's two layers,
    :data:`LONG` pixels long: the stains on the app's page, and over them
    what the pen drew (its strokes and the hatching of the darker parts), on
    nothing. The app lays one on the other, each as it is made.

    Both are wider than the field by :func:`bleed` on each side, the
    page's margin, where a stain or two run out and a stroke goes on;
    :func:`field` cuts a layer back."""
    rng = np.random.default_rng(seed)
    # What runs out of the field has its own chance: the field is the same
    # with it and without.
    loose = np.random.default_rng([seed, 5])
    src = np.asarray(picture.convert("RGB"))
    scale = LONG / max(src.shape[:2])
    size = (max(round(src.shape[1] * scale), 8), max(round(src.shape[0] * scale), 8))
    sized = cv2.resize(src, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    rgb = _keyed(sized)
    h, w = rgb.shape[:2]
    plain = _plain(rgb)
    piece, colours = masses(rgb, seed=seed % 2**31, flat=plain)
    paints = _pigment(_mixed(colours, *hues(cv2.cvtColor(plain, cv2.COLOR_BGR2LAB))))
    up = w / piece.shape[1]
    # What is white in the picture: the paper on the light page (with a
    # breath of the picture's tone, its folds), light paint on the dark one.
    white = whites(_keyed(sized, drawn=True))
    blank = cv2.GaussianBlur(
        cv2.resize(white.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR), (0, 0), 2.6
    )
    moving = _moving(rgb, rng)
    # The paint keeps inside the field, raggedly.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    inset = np.minimum.reduce([xx, yy, w - 1 - xx, h - 1 - yy])
    ragged = _noise((h, w), 20, rng) * 9 + _noise((h, w), 4, rng) * 2
    inside = np.clip((inset + ragged - 9) / 1.5, 0, 1)
    wander = _noise((h, w), 16, rng) * 0.1 + _noise((h, w), 3, rng) * 0.05  # no edge is ruled
    blotch = _noise((h, w), 46, rng) * 0.6 + _noise((h, w), 11, rng) * 0.4
    grain = _noise((h, w), 0.9, rng)
    patchy = _noise((h, w), 26, rng)  # where the paper soaks at a stain's edge
    lively = busy(rgb, (h, w))
    # Where little happens the page is left bare in fragments: sooner where
    # the stain would be near the page's own value, and towards the edge.
    page_lab = cv2.cvtColor(_colour(PAGE[dark]).reshape(1, 1, 3), cv2.COLOR_RGB2LAB)[0, 0]
    worn = paints**1.3 if dark else paints
    apart = np.linalg.norm(
        cv2.cvtColor(worn.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)[0] - page_lab, axis=1
    )
    near = np.clip(1.25 - apart / (52.0 if dark else 45.0), 0, 1)
    near[0] = 0
    near_map = cv2.GaussianBlur(
        cv2.resize(near[piece], (w, h), interpolation=cv2.INTER_LINEAR), (0, 0), 6
    )
    reach = apart * (45.0 / 52.0 if dark else 1.0)
    far = np.clip((reach - BARE_FAR[0]) / (BARE_FAR[1] - BARE_FAR[0]), 0, 1)
    far[0] = 0
    far_map = cv2.GaussianBlur(
        cv2.resize(far[piece], (w, h), interpolation=cv2.INTER_LINEAR), (0, 0), 6
    )
    rim = np.clip(1 - inset / (0.3 * min(h, w)), 0, 1)
    chance = _noise((h, w), 0.07 * max(h, w), rng) * 0.8 + _noise((h, w), 18, rng) * 0.2
    bare = (1 - lively) * (
        BARE_NEAR * near_map + (BARE_RIM * rim + BARE_CHANCE * chance) * (1 - far_map)
    )
    level = max(BARE, float(np.quantile(bare, 1 - BARE_MOST)))
    painted = bare < level
    if dark:
        painted |= blank > 0.5  # white is paint there: never left out
    # towards a bare place the wash runs thin before it stops
    thin = np.clip((level - bare) / BARE_THIN, 0, 1)
    least = 0.55 if dark else 0.35  # covering paint thinned much is a smudge
    thin = least + (1 - least) * thin * thin * (3 - 2 * thin)
    pad = 26
    # Where neighbours keep apart and the page shows between them.
    seam = np.clip(_noise((h, w), 60, rng) * 3 - 0.3, 0, 1)
    # The margin beside the field, where a stain may run out: one stain of
    # one colour, so nothing of the picture is carried there but the
    # paper's own chance (its grain, where it soaks); what the picture
    # gives the paint inside (its gradations, how much happens) ends at
    # the frame or dies away beyond it.
    side = bleed(w)
    wide = w + 2 * side

    def out(a: Array, how: str = "reflect") -> Array:
        pad = ((0, 0), (side, side)) + ((0, 0),) * (a.ndim - 2)
        if how == "fade":
            return np.pad(a, pad, mode="linear_ramp", end_values=0)
        return np.pad(a, pad, mode=how)  # type: ignore[call-overload]

    framed = np.pad(inside, ((0, 0), (side, side)))
    spilt, whose = _spills(painted, side, loose, _sides(piece, white, h))
    # (a stain that runs out ends as any stain does, with its wet front
    # and the paper soaked a little beyond it)
    inside = np.maximum(
        framed, np.clip(cv2.GaussianBlur(cv2.dilate(spilt, np.ones((33, 33))), (0, 0), 3), 0, 1)
    )
    wander, blotch, grain, patchy, seam = (out(a) for a in (wander, blotch, grain, patchy, seam))
    moving, lively, blank = out(moving, "edge"), out(lively, "fade"), out(blank, "constant")
    thin = np.pad(thin, ((0, 0), (side, side)), constant_values=1)
    painted = out(painted)
    painted[:, :side] = spilt[:, :side] > 0.5
    painted[:, side + w :] = spilt[:, side + w :] > 0.5
    under = FIRST * (0.85 + 0.15 * blotch) * framed * lively
    if not dark:
        under *= 1 - blank  # the paper stays clean where the picture is white
    canvas = np.zeros((h, wide, 3), np.float32) if dark else np.ones((h, wide, 3), np.float32)
    cover = np.zeros((h, wide), np.float32)
    if dark:
        canvas[:] = (moving**1.3) * under[..., None]
        cover[:] = under
    else:
        canvas *= moving ** under[..., None]
    # Each stain's body first, light ones first as one paints: a stain's
    # soaked edge is then not laid over its neighbours.
    stains: list[tuple[int, tuple[slice, slice], Array]] = []
    taken = np.zeros((h, wide), np.float32)
    # (what is white is a stain of its own, cut out of the masses it lay in)
    paints = np.concatenate([paints, _colour((255, 255, 255))[None]])
    if dark:
        paints[-1] = np.asarray(WHITE_PAINT, np.float32) ** (1 / 1.3)
    shapes = [(piece == c) & ~white for c in range(len(colours))] + [white]
    for c in sorted(range(1, len(shapes)), key=lambda c: -float(paints[c].sum())):
        if not shapes[c].any():
            continue
        ys, xs = np.nonzero(shapes[c])
        y0, y1 = max(int(ys.min() * up) - pad, 0), min(int((ys.max() + 1) * up) + pad, h)
        x0, x1 = max(int(xs.min() * up) - pad, 0), min(int((xs.max() + 1) * up) + pad, w)
        x0, x1 = x0 + side, x1 + side
        mask = cv2.resize(shapes[c].astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
        mask = out(mask, "constant")
        if c < len(colours) and (whose == c).any():  # the stain that runs out goes on there
            mask[whose == c] = 1
            ys, xs = np.nonzero(whose == c)
            y0, y1 = min(y0, max(int(ys.min()) - pad, 0)), max(y1, min(int(ys.max()) + pad, h))
            x0, x1 = min(x0, max(int(xs.min()) - pad, 0)), max(x1, min(int(xs.max()) + pad, wide))
        part = (slice(y0, y1), slice(x0, x1))
        mask = cv2.GaussianBlur(mask[part], (0, 0), 2.6)
        # neighbours meet, or here and there keep apart (wet paint beside
        # wet paint would run) and the page shows between them
        short = 0.5 + (GAP + 0.6 * np.abs(wander[part])) * seam[part]
        is_white = c == len(shapes) - 1
        body = ((mask > (0.5 if is_white else short)) & (painted[part] | is_white)).astype(np.uint8)
        if body.sum() < 40:
            continue
        stains.append((c, part, body))
        if dark or not is_white:  # the paper's white is no wet paint beside a neighbour
            taken[part] = np.maximum(taken[part], body)
    for c, part, body in stains:
        is_white = c == len(shapes) - 1
        d_in = cv2.distanceTransform(body, cv2.DIST_L2, 3)
        d_out = cv2.distanceTransform(1 - body, cv2.DIST_L2, 3)
        aa = np.clip(d_in, 0, 1)
        others = cv2.GaussianBlur(taken[part] - body, (0, 0), 2.5)
        touch = np.clip(others * 3, 0, 1)
        # the wet front: pigment carried to the edge and left there, most
        # where the edge is open; two fronts side by side would be a dark band
        load = (1 - FIRST) * (0.8 + 0.2 * blotch[part]) * thin[part] + 0.1 * grain[part]
        load += (0.42 * np.exp(-d_in / 1.3) + 0.1 * np.exp(-d_in / 9)) * (1 - 0.8 * touch)
        # the paper soaks at the edge: a paler second stain, in fragments,
        # on the bare paper only
        far = 5 + 7 * np.clip(patchy[part] + 0.2, 0, 1)
        halo = ((d_out > 0) & (d_out < far) & (patchy[part] > -0.1)).astype(np.float32)
        halo *= np.clip(1 - others * 4, 0, 1)
        if not dark:
            halo *= 1 - blank[part]  # and not on what is white
        halo_load = (0.16 + 0.14 * np.exp(-np.abs(far - d_out) / 1.1)) * halo
        flat = paints[c][None, None]
        # the stain is flat where nothing happens, and moves where much does
        own = ((0.06 + 0.22 * lively[part]) * framed[part])[..., None]
        tint = (1 - own) * flat + own * moving[part]
        if is_white and not dark:
            # the paper, with a breath of the picture's own tone in grey
            tone = moving[part].mean(axis=2, keepdims=True)
            tint = 1 - WHITE_TONE * (1 - np.repeat(tone, 3, axis=2)) / max(1 - FIRST, 0.1)
            load = np.ones_like(load)
        elif is_white:
            tint = np.broadcast_to(flat, tint.shape) * (
                0.9 + 0.1 * moving[part].mean(axis=2, keepdims=True)
            )
            load = np.maximum(load, 0.88)
        if dark:  # on a dark page paint covers instead of staining
            alpha = np.clip((aa * load * 0.9 + (1 - aa) * halo_load * 1.3) * inside[part], 0, 1)
            canvas[part] = canvas[part] * (1 - alpha[..., None]) + (tint**1.3) * alpha[..., None]
            cover[part] = 1 - (1 - cover[part]) * (1 - alpha)
        else:
            canvas[part] *= tint ** (aa * load * inside[part])[..., None]
            canvas[part] *= flat ** ((1 - aa) * halo_load * inside[part])[..., None]
    page, ink = _colour(PAGE[dark]), _colour(INK[dark])
    sheet = np.empty((h, wide, 3), np.float32)
    sheet[:] = page
    sheet = sheet * (1 - np.clip(cover, 0, 1)[..., None]) + canvas if dark else sheet * canvas
    wash = Image.fromarray((np.clip(sheet, 0, 1) * 255).astype(np.uint8))
    # The darker parts hatched, under the strokes. On the dark page the pen
    # is light: there the hatching is the page's own dark, so that it still
    # darkens what it shades.
    shift = np.array((side, 0), np.float32)
    shade = np.zeros((h, wide), np.float32)
    for line in hatching(rgb, rng):
        _nib(shade, line + shift, rng, HATCH_NIB)
    shaded = np.clip(shade, 0, 1) * framed * HATCH_INK
    # A few strokes of the nib, by one who saw the picture. One that ends
    # at a side goes on past the frame, as a hand does not stop on a line.
    line = np.zeros((h, wide), np.float32)
    free = np.zeros((h, wide), np.float32)
    if lines is None:
        lines = pen_lines(picture, strokes, aside)
    past = _past(
        [(points, sharp, closed) for points, sharp, closed, _ in lines], (w, h), side, loose
    )
    for at, (points, sharp, closed, weight) in enumerate(lines):
        pts = np.asarray(points, np.float32).reshape(-1, 2) * (w, h)
        if len(pts) < 2:
            continue
        if closed:
            pts = np.concatenate([pts, pts[:2]])  # closed a little past where it began
        goes = past is not None and past[0] == at
        if past is not None and goes:
            pts = past[1]
        pts = pts + shift
        nib = NIB * (NIB_LIGHT + (1 - NIB_LIGHT) * weight)
        _nib(free if goes else line, pts if sharp or len(pts) < 3 else _chaikin(pts), rng, nib)
    # (the stroke that goes on is not stopped by the field's edge at the sides)
    xs_wide = np.arange(wide, dtype=np.float32)[None, :]
    sides = ((xs_wide < side + SPILL_ROOT) | (xs_wide > side + w - 1 - SPILL_ROOT)).astype(
        np.float32
    )
    laid = np.clip(line, 0, 1) * framed + np.clip(free, 0, 1) * np.maximum(framed, sides)
    laid = np.clip(laid, 0, 1) * NIB_INK
    alpha = 1 - (1 - shaded) * (1 - laid)
    lead = page if dark else ink
    colour = lead * (shaded * (1 - laid))[..., None] + ink * laid[..., None]
    colour = colour / np.maximum(alpha, 1e-4)[..., None]
    drawn = np.dstack([np.where(alpha[..., None] > 0, colour, ink), alpha])
    pen = Image.fromarray((np.clip(drawn, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
    return wash, pen


def render(
    picture: Image.Image,
    strokes: Sequence[PenStroke] = (),
    *,
    dark: bool = False,
    seed: int = 1,
    aside: Sequence[bool] = (),
    lines: Sequence[PenLine] | None = None,
) -> Image.Image:
    """The sheet whole, the pen's layer laid on the stains, the field
    alone: for apps from before the two were sent apart."""
    wash, pen = layers(picture, strokes, dark=dark, seed=seed, aside=aside, lines=lines)
    whole = wash.convert("RGBA")
    whole.alpha_composite(pen)
    return field(whole.convert("RGB"))


def png(pen: Image.Image) -> bytes:
    """The pen's layer as the app gets it: on nothing."""
    out = io.BytesIO()
    pen.save(out, "PNG", optimize=True)
    return out.getvalue()


def jpeg(sheet: Image.Image) -> bytes:
    """The sheet as the app gets it: its flat page must stay the page's own
    colour, so the chroma is kept whole."""
    out = io.BytesIO()
    sheet.save(out, "JPEG", quality=88, subsampling=0, optimize=True)
    return out.getvalue()
