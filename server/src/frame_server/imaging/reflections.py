"""Reflections taken out of a photograph of a work by two more taken
from the sides (the scan of three, Mateusz 2026-11-16: "pierwsze zdjęcie
na wprost, a kolejne pod większym kątem", "żeby efekt był rewelacyjny").

What his own photographs of a print behind glass showed: in a bright room
every view has a veil over the whole glass, the one from the front most
of all (the room behind the photographer), and each has sharp reflections
of its own (a window, a doorway, his own figure). Replacing bright patches
(:mod:`.glare`) only made smears there.

The work is flat, so within its corners the side photographs are laid
over the first with one homography each. In linear light a reflection
only adds: each view is the work plus its own reflection layer, and the
views' differences are differences of those layers alone, whatever the
work shows. Per pixel the least view, ``low``, is the work plus the veil
all the views share there, ``common``: the one unknown. It is found as
the least field that leaves every view's reflection layer
(``common + view - low``) piecewise smooth (total variation): an edge the
work has is in all the views and costs nothing, a reflection's edge is in
one and is paid for unless ``common`` takes it over. What the first
photograph's layer comes to is subtracted from the first photograph at
its full size, so every detail stays the first photograph's own; the side
ones only say what is reflection.

The frame's side hides the work's near edge from the side, so a side
photograph does not count in a band along the edge it was taken from.

What his first scans on the phone showed (2026-11-16, a dark folder with
gold letters on a desk, a painting on a screen; "efekt wychodzi nazbyt
kontrastowy i zbyt nasycony"): a work shines of itself, differently from
each side, and that is no reflection to take off. So a side view's
difference from the first is the middle one of each cell's
(:func:`_apart`), which gilding and varnish are not; the views' white
balances are held near each other (:data:`BALANCE`); and of the least
view only a part may be shared veil (:data:`VEIL_MOST`): that veil is
the one thing here that is supposed, not seen, and all of it made a dark
work black.

What his paintings showed (2026-11-16 16:44 UTC, four oils and a print
behind glass; "Skany wychodzą chyba odrobinę zbyt kontrastowe i ciemne?
Porównaj proszę zdjęcia na wprost z efektami po połączeniu"): the scans
were 7 to 11 levels (of 255) darker than the photographs from the front
and their shadows closed (the 2nd percentile from 12 to 2, from 15 to 6).
Much of what went was even over the whole work: the sheen of the paint
and the veil over the glass, which is how the work looks in its room. So
the light that most of the work has in its layer stays
(:data:`KEPT`), and only what stands out of it, a reflection with a
shape, is taken off: 2 to 6 levels darker, the shadows as they were.

What his sixteen cows behind glass and an oil portrait showed
(2026-11-16 18:16 and 19:01 UTC; "Spójrz na efekt skanowania dzieła za
szybą", "chyba działa zbyt punktowo i z ostrym odcięciem"):

- From the front the glass mirrored him, dark, and from the sides the
  bright room: the first view was the least one, and nothing said its
  lit hand and the lamp were reflections. What the first view has over
  what both side views tell of a place, each told in the first's light
  (:func:`_told`), is its own (:func:`_alone`); where that is a lamp's
  glare, with nothing of the work left under it, the work is taken from
  the side views.
- On an oil the window's sheen lies on the ridges of the paint and not
  in the furrows; the layer is soft, and taken off every place alike it
  left the furrows black. Where the first view is rougher than the side
  views the layer goes from each place by what it has over the darkest
  about (:func:`_grain`); elsewhere no more goes than that darkest has.
- A side view came to count at once beyond its band, and what was taken
  off changed in a line down the work: it counts by degrees
  (:data:`HIDDEN_EASE`). The band is as wide as the frame's side shows
  dark in the side view (:func:`_hide`).
- A collage of a mirror, foil and a circuit board: the side views do not
  tell one work, and nothing is touched (:data:`NOT_ONE`).

What the cows showed scanned again (2026-11-16 22:30 UTC, three places
ringed on a screenshot; "Odbicia w szybie - jest lepiej, ale przejście
powinno być jeszcze łagodniejsze"): his hand went from the sky about a
cow and stayed on her in hard-edged patches, a finger stayed over the
dark of a print, and the lamp that was taken out left a dark ring. What
is the first view's own is now told by the plain places about each place
and drawn sharp (:func:`_own`), it goes off as drawn and is not held to
the darkest about, and about a lamp nothing is taken for a sheen on the
grain (:func:`_grain`). On paint, where the first view is the rougher
one, it goes as before, with the layer.

And the third time (2026-11-17 00:06 UTC, shown the scan of 1.145.203:
"To dalej nie wygląda idealnie. Czy nie możemy zrobić miękkich, daleko
sięgających przejść?"): a finger's edge in the glass is sharper than the
views can tell it, and taken off it left a light line with a dark one
beside it, and dark wedges between the fingers. About a place where the
first view had light of its own the picture is now mended from the side
views, which have no such hand: widely and by degrees over the plain of
a print, closely about its letters and lines (:func:`_mend`).

A drawing behind glass (2026-11-17 06:57 UTC, three places ringed on a
screenshot of the work's card: "Jest coraz lepiej. Ale myślę że można
jeszcze poprawić efekt. Zobacz sobie mój ostatni skan"). A lamp burnt
into the first view, his own figure dark in the glass with the room's
veil about it, a lit kitchen over a ladder; one side view clean, the
other with a window where the first had the lamp.

- What is the first view's own was the least over both side views: where
  one had its window, only the lamp's red went and a green patch stayed.
  The side view that is the darker there says it (:func:`_one`), unless
  the first shows what the lighter one shows: a print behind its mount
  has the mount's shade along its edge from one side.
- The even part of the veil stays (:data:`KEPT`), and it stayed about
  his figure and not in it, his head and shoulders a shade darker on the
  paper. About such an edge what stays comes back by degrees
  (:func:`_kept`), and the pale line along it is mended from the side
  views as a finger's is.
- A work in a wide mount is hidden by no frame: a side view that shows
  the work's lines up to its edge counts nearly up to it (:func:`_hide`).
  The band left the other one alone there, with its window.
- Under the kitchen's light the phone pressed the ladder's lines pale:
  where the first view's own light is much and bright, the fine is the
  side views' too (:data:`MEND_ALL`)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numba
import numpy as np
from numpy.typing import NDArray

#: The long side the photographs are laid over each other at.
MATCH_SIDE = 2400
#: Matches a side photograph needs to be laid over the first.
MIN_MATCHES = 40
#: The width the reflection layers are worked out at: reflections are
#: soft, and the work's own grain must not show in them.
LAYER_WIDTH = 256
#: The width the views' exposures are compared at.
EVEN_WIDTH = 192
#: The pyramid: how much smaller, and how many steps there.
LEVELS = ((8, 1500), (4, 1000), (2, 600), (1, 300))
#: What a unit of shared veil costs beside the layers' smoothness: next
#: to nothing, only to choose the least of the equally smooth.
VEIL_COST = 0.002
#: How far a channel's gain may be from the three's middle one.
BALANCE = 0.12
#: A cell of the layers is the middle of so many differences each way.
CELL = 4
#: The most of the least view that may be veil all the views share.
VEIL_MOST = 0.3
#: The reflection layer's percentile (per channel) that is the work's own
#: even sheen or veil and stays on it. Not the middle one: a reflection
#: over more than half of the work would stay whole. 40 until 2026-11-16
#: 22:19 UTC (Mateusz, an oil portrait scanned in the evening, shown the
#: scan as it was, B, and with nothing kept, C: "Najbliżej jest jednak B.
#: Może odrobinę w kierunku C. Ale samo C jest zdecydowanie za ciemne i
#: zbyt dużo kontrastu").
KEPT = 30
#: Where the layer has less than that (his own figure, dark in the glass)
#: what stays comes back to it over so much of the work's width: at once,
#: the figure stayed drawn on the work.
KEPT_EASE = 0.12
#: Not about a place that has less only because it could have no more: a
#: dark of the work, where the shared veil is this near the most it may
#: be (:data:`VEIL_MOST`; from, and wholly at).
KEPT_HELD = (0.5, 0.9)
#: And only about an edge: where what stays differs within two cells of
#: the layer each way by this much of the even light (from, and wholly
#: at). A sheen that thins out by degrees is as the work is.
KEPT_EDGE = (0.4, 0.8)
#: Nor about the layer's own rim, so much of its width: there it thins out
#: to what lies about the work, and the work darkened toward its edges.
KEPT_RIM = 0.04
#: And only about a place this much of the width across at the least: a
#: figure. On an oil the sheen lies on one half, the other half has less
#: in specks and streaks, and all of that half came out a tone darker.
KEPT_FIGURE = 0.05
#: The width what the first view alone shows is worked out at: a finger
#: in the glass is a hundredth of the work across.
ALONE_WIDTH = 512
#: And the width it is drawn at: the edge of a reflection is as sharp as
#: the glass shows it.
ALONE_FINE = 1024
#: A place of a side view is plain when the lightest about it (two
#: pixels each way) is over the darkest by less than this, and this much
#: of its own light; a rough one (a line of the work) says little.
ALONE_PLAIN = 0.02
ALONE_PLAIN_OF = 0.15
#: The plain places about a rough one tell it: from so near (of the
#: work's width), and from further where the near ones are fewer than
#: this share.
ALONE_REACH = (0.0015, 0.005, 0.015)
ALONE_SURE = 0.3
#: A thing narrower than this (of the work's width) is grain.
ALONE_GRAIN = 0.005
#: A side view tells what the first should show from what is about a
#: place, this far each way (of the work's width): wider than a hand.
ALONE_ABOUT = 0.15
#: And only from places as light in the side view: the steps of light
#: (a factor of two each, about) a place is between two of.
ALONE_STEPS = 8
#: Times round, and what a place is off by that halves its weight (and
#: this much of the first view).
ALONE_ROUNDS = 4
# This share of the places about being as light is few.
ALONE_FEW = 0.03
ALONE_OFF = 0.003
ALONE_OFF_OF = 0.03
#: What the first view has over what a side view tells counts from this
#: and this much of the first view on: less is grain and the laying over.
ALONE_FROM = 0.0015
ALONE_FROM_OF = 0.015
#: The most of the first view that may be such a thing.
ALONE_MOST = 0.9
#: A side view that tells a place lighter than the other does by this
#: much of what the darker tells (from, and wholly at) has a reflection
#: of its own there, and only the darker says what is the first's.
ALONE_ONE = (0.15, 0.4)
#: And only where the first view is as far from the lighter of them: by
#: this much of what the two are apart (from, and wholly at). Where the
#: first shows what the lighter one shows, it is the darker that is off
#: (the shade of a mount on the edge of a print, seen from that side).
ALONE_THREE = (0.4, 0.7)
#: Nor what is narrower than this (of the work's width): that shade is a
#: strip along the print's edge, and a window in the glass is wide. But
#: for where the first view is burnt out (:data:`BLOWN`): it shows
#: nothing there, and the window over his lamp was a strip as narrow.
ALONE_SHADE = 0.03
#: Where the first view's own reflection is so much light (linear) it is
#: a lamp's glare: the photograph is burnt out there, or so near it that
#: what is left of the work under it is pale and all grain. And so far
#: about such a place (of the work's width).
GLARE = 0.2
GLARE_NEAR = 0.006
#: Its least colour is at least so much of its most.
GLARE_COLOUR = 0.4
#: The side views tell one work under it when they differ by no more
#: than this of what they tell (and of this much light at the least, the
#: three colours together).
GLARE_DIFFER = 0.25
GLARE_DARK = 0.1
#: The least of a side view's own light that is the work's there.
GLARE_BLACK = 0.3
#: A pixel of a view over this says nothing of what the views differ by.
BLOWN = 0.85
#: The band at the edge a side photograph was taken from, where the
#: frame's side hides the work (of the work's width).
HIDDEN = 0.06
#: The band is as wide as the side view is this dark beside the first
#: (its columns' middle light), and a little more, up to so much.
HIDDEN_DARK = 0.15
HIDDEN_BESIDE = 0.01
HIDDEN_MOST = 0.15
#: Beyond the band a side view comes to count over so much more.
HIDDEN_EASE = 0.04
#: A work in a wide mount is hidden by nothing: where the side view shows
#: the lines the other views show there (strips of a hundredth of the
#: width, each as like theirs as this at the least; not the outermost,
#: which is the mount's edge in all of them) the band is only this wide.
HIDDEN_LIKE = 0.4
HIDDEN_SHOWN = 0.02
#: A reflection in glass is light over all there is: no more of it lies
#: on a place than the darkest about has (this far each way, of the
#: work's width: a cell of the layer and a half). What the layer has over
#: that is a sheen on the work's own grain, and goes from each place by
#: what the place has over that darkest.
GRAIN_ABOUT = 0.006
#: A sheen on the grain shows in the first view being rougher than the
#: side views there (the lightest about a place over the darkest): by
#: this share of its own roughness it may be the photographs, from this
#: on wholly the sheen.
GRAIN_FROM = 0.15
GRAIN_SURE = 0.4
#: Where the first view has light of its own that is this much of what
#: the work has there (from, and wholly at), the work's picture is mended
#: from the side views: so far about such a place (of the work's width),
#: and over so much more by degrees.
MEND_FROM = 0.08
MEND_TO = 0.25
MEND_DARK = 0.03
MEND_GROW = 0.008
MEND_SOFT = 0.012
#: And so far where the work is plain: where what the side views show
#: finer than twice :data:`MEND_FINE` is under the first of these (of
#: how light the place is; by degrees to the second), this far about
#: (of the work's width; a print behind its mount is so far off in them).
MEND_FAR = 0.045
MEND_FAR_SOFT = 0.02
MEND_PLAIN = (0.05, 0.15)
MEND_OFF = 0.004
#: And where the soft layer has an edge on a plain of the work: where
#: within this far each way (of the work's width) it differs by this much
#: of the work's light (from, and wholly at). The layer is soft and the
#: edge of his figure in the glass is not: a pale line stayed along it.
MEND_EDGE_ABOUT = 0.008
MEND_EDGE = (0.06, 0.15)
#: What is finer than this (of the work's width) stays the first view's.
MEND_FINE = 0.0018
#: Unless its own light there is this much of the work's (from, and
#: wholly at) and the first view is this light with it (linear, its
#: lightest colour): the phone presses such light flat, and the work's
#: lines under it are pale. There the fine is the side views' as well.
MEND_ALL = (0.2, 0.5)
MEND_ALL_LIGHT = (0.55, 0.8)
#: But about letters and lines no colour finer than this is theirs.
MEND_TINT = 0.006
#: And what is coarser than this stays the first view's as well.
MEND_COARSE = 0.025
#: The side views' picture is put in the first's tones by the line the
#: two keep to about each place, from so near (of the work's width), and
#: from further where less than this share about is free of such light.
MEND_REACH = (0.008, 0.025, 0.08, 0.3)
MEND_SURE = 0.5
#: Light that differs by less than this says nothing of that line.
MEND_NOISE = 0.02
#: The work's corners are found by eye (Opus, or he moves them after):
#: this much more of the photograph around them is cleaned too (of the
#: work's size, each way), so a cut a little wider has no seam.
AROUND = 0.015
#: The side views told in the first's light differ by this much of what
#: they tell at the middle place of the work: they do not show one flat
#: work (his collage of a mirror, foil and a circuit board, 0.30; glass
#: and oil 0.04 to 0.10), and nothing is touched.
NOT_ONE = 0.2
#: Less light than this taken off (of the first photograph's) is nothing.
LEAST = 0.01
#: More than this is no reflection: the photographs do not show one work
#: in one light, and nothing is touched.
MOST = 0.7
#: Rows worked on at once at full size.
ROWS = 512

Image = NDArray[Any]
Floats = NDArray[Any]
Quad = list[tuple[float, float]]


@dataclass
class Merged:
    image: Image
    #: Side photographs that could be laid over the first.
    used: int
    #: The share of the first photograph's light within the work that was
    #: reflection and is taken off (0–1).
    removed: float


@dataclass
class _View:
    #: The work as this photograph shows it, laid over the first's, linear.
    light: Floats
    #: -1 taken from the left, 1 from the right, 0 the first.
    side: int
    #: The band along that edge where the frame's side hides the work
    #: from this photograph (of the work's width).
    hidden: float = HIDDEN


def merge(first: Image, sides: list[Image], corners: Quad) -> Merged:
    """``first`` (RGB, H × W × 3) without the reflections ``sides`` do not
    share, within ``corners`` (the work: top left, top right, bottom
    right, bottom left, 0–1 across and down)."""
    h, w = first.shape[:2]
    quad = grown(corners) * [w, h]
    scale = min(1.0, MATCH_SIDE / max(h, w))
    small = _resize(first, scale)
    # The work upright, at the size the small copy has it.
    across = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2 * scale
    down = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2 * scale
    if across < 200 or down < 200:
        return Merged(first, 0, 0.0)
    wd, ht = round(across), round(down)
    rect = np.array([[0, 0], [wd, 0], [wd, ht], [0, ht]], np.float32)
    to_work = cv2.getPerspectiveTransform(((quad + 0.5) * scale - 0.5).astype(np.float32), rect)
    front = cv2.warpPerspective(small, to_work, (wd, ht), flags=cv2.INTER_LINEAR)

    views = [_View(_linear(front), 0)]
    marks = _marks(front)
    for photo in sides:
        laid = _lay(front, marks, photo)
        if laid is not None:
            views.append(laid)
    if len(views) < 2:
        return Merged(first, 0, 0.0)

    _even(views)
    _hide(views)
    whole = float(views[0].light.mean())
    # What the first view alone shows goes first, and the rest is worked
    # out of a first view without it.
    front = views[0].light
    alone, swap, differ, told = _alone(views)
    if differ > NOT_ONE:
        return Merged(first, len(views) - 1, 0.0)
    less = front - alone
    if swap is not None:
        work, patch = swap
        less = less + (work - less) * patch
        alone = alone * (1 - patch)
        front = front + (work - front) * patch
    views[0] = _View(less, 0)
    layer, held = _reflection(views)
    # What most of the work has is not taken off.
    layer = (layer - _kept(layer, held)).astype(np.float32)
    soft = np.clip(cv2.resize(layer, (wd, ht), interpolation=cv2.INTER_CUBIC), 0, None)
    removed = float((alone + soft).mean()) / max(whole, 1e-6)
    if not LEAST <= removed <= MOST:
        return Merged(first, len(views) - 1, 0.0)
    # The layer's pixels → the photograph's (a pixel's place is its middle).
    to_photo = (
        _larger(1 / scale, 1 / scale)
        @ np.linalg.inv(to_work)
        @ _larger(wd / soft.shape[1], ht / soft.shape[0])
    )
    lamp = None if swap is None else swap[1]
    veil, low, share = _grain(less, alone, soft, views[1:], lamp)
    # The first view as it comes out of that, and what is still to mend.
    now = front - veil - np.clip(front - low, 0, None) * share
    mend = _mend(now, front, alone, soft, views, told)
    clean = _subtract(first, (veil, low, share), mend, swap, to_photo, quad)
    return Merged(clean, len(views) - 1, round(removed, 4))


def _kept(layer: Floats, held: Floats) -> Floats:
    """What of the reflection ``layer`` stays on the work: the even light
    most of it has (:data:`KEPT`), and less where the layer has less, and
    about such a place by degrees, unless it has less for being ``held``
    (0–1) to what a dark of the work lets it be.

    His drawing behind glass (2026-11-17 06:57 UTC, "myślę że można
    jeszcze poprawić efekt"): he stood before it, dark in the glass, and
    the room's veil lay about his figure and not in it. All but the even
    part of the veil went, and none of what little the figure had: its
    outline stayed on the paper, a step of that even part. So what stays
    rises from such a place no steeper than the whole of it over
    :data:`KEPT_EASE` of the width: from a place as wide as a figure
    (:data:`KEPT_FIGURE`) with a sharp edge (:data:`KEPT_EDGE`), not from
    the layer's rim (:data:`KEPT_RIM`)."""
    even = np.percentile(layer.reshape(-1, layer.shape[-1]), KEPT, axis=0).astype(np.float32)
    least = np.minimum(layer, even)
    # How much of the even light a place has: of the colour it has the
    # most of (less of one colour alone is the layer's own unevenness).
    level = (least / np.maximum(even, 1e-6)).max(-1)
    rim = max(1, round(layer.shape[1] * KEPT_RIM))
    inner = cv2.copyMakeBorder(level[rim:-rim, rim:-rim], rim, rim, rim, rim, cv2.BORDER_REPLICATE)
    wide = max(3, round(layer.shape[1] * KEPT_FIGURE)) | 1
    figure = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (wide, wide))
    less = (1 - inner) * (1 - held.max(-1))
    full = 1 - cv2.morphologyEx(less.astype(np.float32), cv2.MORPH_OPEN, figure)
    reach = max(1, round(layer.shape[1] * KEPT_EASE))
    square = np.ones((3, 3), np.uint8)
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    eased = full
    for step in range(reach):
        # Square and cross by turns: about as far each way.
        eased = np.minimum(eased, cv2.erode(eased, cross if step % 2 else square) + 1 / reach)
    eased = np.minimum(eased, level)
    five = np.ones((5, 5), np.uint8)
    edge = cv2.dilate(full, five) - cv2.erode(full, five)
    edge = np.clip((edge - KEPT_EDGE[0]) / (KEPT_EDGE[1] - KEPT_EDGE[0]), 0, 1)
    about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * reach + 1, 2 * reach + 1))
    near = cv2.GaussianBlur(cv2.dilate(edge.astype(np.float32), about), (0, 0), reach / 2)
    level = level - (level - eased) * np.clip(near, 0, 1)
    return np.asarray(np.minimum(least, even * level[..., None]), np.float32)


def grown(corners: Quad) -> NDArray[np.float64]:
    """The corners with :data:`AROUND` more about their middle: what
    :func:`merge` cleans."""
    quad = np.array(corners, np.float64)
    middle = quad.mean(0)
    return middle + (quad - middle) * (1 + 2 * AROUND)


def _larger(across: float, down: float) -> NDArray[np.float64]:
    """A picture's pixels → those of one so many times larger, middle
    of a pixel to the middle of what it covers."""
    return np.array(
        [[across, 0, (across - 1) / 2], [0, down, (down - 1) / 2], [0, 0, 1]], np.float64
    )


def _resize(img: Image, scale: float) -> Image:
    if scale >= 1:
        return img
    h, w = img.shape[:2]
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


_TO_LINEAR = np.where(
    np.arange(256) / 255 <= 0.04045,
    np.arange(256) / 255 / 12.92,
    ((np.arange(256) / 255 + 0.055) / 1.055) ** 2.4,
).astype(np.float32)


def _linear(img: Image) -> Floats:
    return _TO_LINEAR[img]


#: Linear light (in 65 536 steps) → sRGB bytes.
_FROM_LINEAR = (
    np.where(
        np.arange(65536) / 65535 <= 0.0031308,
        np.arange(65536) / 65535 * 12.92,
        1.055 * np.power(np.arange(65536) / 65535, 1 / 2.4) - 0.055,
    )
    * 255
    + 0.5
).astype(np.uint8)


def _srgb(light: Floats) -> Image:
    steps = np.clip(light * 65535 + 0.5, 0, 65535).astype(np.uint16)
    return _FROM_LINEAR[steps]


def _marks(img: Image) -> tuple[Any, Any]:
    """What a photograph is known by in another: its points and what is
    about each."""
    sift = cv2.SIFT_create(8000, contrastThreshold=0.02)  # type: ignore[attr-defined]
    found: tuple[Any, Any] = sift.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), None)
    return found


def _lay(front: Image, marks: tuple[Any, Any], photo: Image) -> _View | None:
    """A side photograph laid over the work as the first shows it (with
    its ``marks``), or None when too little of them matches (another
    work, a blur)."""
    side = _resize(photo, min(1.0, MATCH_SIDE / max(photo.shape[:2])))
    k1, d1 = marks
    k2, d2 = _marks(side)
    if d1 is None or d2 is None or len(k1) < MIN_MATCHES or len(k2) < MIN_MATCHES:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d2, d1, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.8 * p[1].distance]
    if len(good) < MIN_MATCHES:
        return None
    src = np.array([k2[m.queryIdx].pt for m in good], np.float32)
    dst = np.array([k1[m.trainIdx].pt for m in good], np.float32)
    found, inliers = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, 2.0)
    if found is None or inliers is None or int(inliers.sum()) < MIN_MATCHES:
        return None
    ht, wd = front.shape[:2]
    # The work's corners in the side photograph: all of it must be there,
    # and its taller side is the one the photograph was taken from.
    back = np.linalg.inv(found)
    ends = cv2.perspectiveTransform(
        np.array([[[0, 0], [wd, 0], [wd, ht], [0, ht]]], np.float64), back
    )[0]
    sh, sw = side.shape[:2]
    if (ends < -0.02 * max(sh, sw)).any() or (ends > np.array([sw, sh]) * 1.02).any():
        return None
    left = float(np.linalg.norm(ends[3] - ends[0]))
    right = float(np.linalg.norm(ends[2] - ends[1]))
    if min(left, right) <= 0:
        return None
    lean = math.log(left / right)
    over = cv2.warpPerspective(side, found, (wd, ht), flags=cv2.INTER_LINEAR)
    return _View(_linear(over), -1 if lean > 0.03 else 1 if lean < -0.03 else 0)


def _coarse(light: Floats, shape: tuple[int, ...]) -> Floats:
    return cv2.resize(light, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)


def _apart(apart: Floats, shape: tuple[int, ...]) -> Floats:
    """What a side view differs from the first by, at the layers' size:
    the middle one of each cell's differences, and of the cells about it.
    A reflection is soft and fills a cell; what is the work's own (the
    shine of gilding or of varnish on a stroke of paint, which moves with
    the view) and what the laying over missed by a pixel are a few of a
    cell's and do not count. As a mean they spread: his dark folder with
    gold letters (2026-11-16) came out with a black halo about each."""
    h, w = shape[:2]
    fine = cv2.resize(apart, (w * CELL, h * CELL), interpolation=cv2.INTER_AREA)
    cells = fine.reshape(h, CELL, w, CELL, 3).transpose(0, 2, 1, 3, 4).reshape(h, w, CELL * CELL, 3)
    middle = np.ascontiguousarray(np.median(cells, axis=2).astype(np.float32))
    return cv2.medianBlur(middle, 5)


def _counts(views: list[_View], h: int, w: int) -> Floats:
    """How much each view counts (0–1) at this size: a side one not in
    the band along the edge it was taken from, and by degrees beyond it
    (counting at once, what was taken off the work changed in a line
    down it)."""
    counts = np.ones((len(views), h, w), np.float32)
    for n, view in enumerate(views):
        if view.side == 0:
            continue
        band = max(1, round(w * view.hidden))
        ease = max(1, round(w * HIDDEN_EASE))
        along = np.clip((np.arange(w, dtype=np.float32) - (band - 1)) / ease, 0, 1)
        counts[n] = along if view.side < 0 else along[::-1]
    return counts


def _hide(views: list[_View]) -> None:
    """How far in from its edge each side view does not show the work:
    :data:`HIDDEN` at the least, and as far as it shows the dark of the
    frame's side instead (a deep frame about his print behind glass: a
    strip of the print beyond the band came out black and speckled).
    Less where it plainly does show it: his drawing in a wide mount
    (2026-11-17 06:57 UTC) kept a pale strip of the kitchen in the glass
    along the edge, where only the other side view counted, and that one
    had a window there."""
    first = views[0].light.mean(-1)
    wd = first.shape[1]
    reach = round(wd * HIDDEN_MOST)

    def lines(view: _View) -> Floats:
        grey = cv2.GaussianBlur(np.sqrt(np.clip(view.light.mean(-1), 0, None)), (0, 0), 1.5)
        return np.asarray(grey - cv2.GaussianBlur(grey, (0, 0), 0.006 * wd), np.float32)

    drawn = [lines(view) for view in views]
    strip = max(4, round(wd * 0.01))
    for n, view in enumerate(views[1:], 1):
        if view.side == 0:
            continue
        # Its lines along its edge beside the other views' there.
        others = [drawn[m] for m in range(len(views)) if m != n]
        own = drawn[n]
        if view.side > 0:
            own, others = own[:, ::-1], [other[:, ::-1] for other in others]
        shown = True
        for k in range(1, max(2, round(HIDDEN / 0.01))):
            a = own[:, k * strip : (k + 1) * strip]
            like = max(
                float((a * b).sum() / (math.sqrt(float((a * a).sum() * (b * b).sum())) + 1e-9))
                for b in (other[:, k * strip : (k + 1) * strip] for other in others)
            )
            shown = shown and like >= HIDDEN_LIKE
        least = HIDDEN_SHOWN if shown else HIDDEN
        mine = view.light.mean(-1)
        if view.side > 0:
            first_, mine = first[:, ::-1], mine[:, ::-1]
        else:
            first_ = first
        # Column by column from the edge: the side view's middle light
        # beside the first's.
        dark = np.median(mine[:, :reach], axis=0) < HIDDEN_DARK * np.median(
            first_[:, :reach], axis=0
        )
        # Only the dark that begins in the band there always is: further
        # in it is the work's own (an oil's sheen in the first view).
        last = round(wd * HIDDEN)
        if not dark[: last + 1].any():
            last = 0
        while 0 < last < reach and dark[last]:
            last += 1
        view.hidden = max(least, min(HIDDEN_MOST, last / wd + HIDDEN_BESIDE))


def _even(views: list[_View]) -> None:
    """The side views brought to the first's exposure and white balance.
    The work's own edges are in every view and far stronger than a
    reflection's, so per channel the gain is what the side view's steps
    across them are of the first's (a reflection only adds light, and no
    place need be clean of it in both)."""
    shape = (
        max(8, round(views[0].light.shape[0] * EVEN_WIDTH / views[0].light.shape[1])),
        EVEN_WIDTH,
    )

    def steps(light: Floats) -> tuple[Floats, Floats]:
        soft = cv2.GaussianBlur(_coarse(light, shape), (0, 0), 1.5)
        return soft[:, 1:] - soft[:, :-1], soft[1:] - soft[:-1]

    fx, fy = steps(views[0].light)
    for view in views[1:]:
        sx, sy = steps(view.light)
        gains = []
        for c in range(3):
            a = np.concatenate([fx[..., c].ravel(), fy[..., c].ravel()])
            b = np.concatenate([sx[..., c].ravel(), sy[..., c].ravel()])
            strong = np.abs(a) >= np.quantile(np.abs(a), 0.9)
            gains.append(float(np.clip(np.median(b[strong] / a[strong]), 0.5, 2.0)))
        # The exposure is one for the three channels; the white balance
        # moves between two photographs of one wall only so far. More is
        # the work's own shine (gold letters, which are yellow from the
        # front and white from the side), not the camera's.
        middle = sorted(gains)[1]
        for c in range(3):
            gain = float(np.clip(gains[c], middle * (1 - BALANCE), middle * (1 + BALANCE)))
            view.light[..., c] /= gain


def _reflection(views: list[_View]) -> tuple[Floats, Floats]:
    """The first view's reflection layer (linear light, :data:`LAYER_WIDTH`
    wide), the views' exposures being even; and how near the veil the
    views share is to the most it may be there (0–1)."""
    ht, wd = views[0].light.shape[:2]
    common: Floats | None = None
    low = lights = None
    for shrink, steps in LEVELS:
        w = max(16, LAYER_WIDTH // shrink)
        h = max(16, round(ht * w / wd))
        first = cv2.GaussianBlur(_coarse(views[0].light, (h, w)), (0, 0), 1.0)
        some = _counts(views, h, w)
        # A view that counts for less differs from the first by less.
        lights = np.stack(
            [first]
            + [
                first + _apart(v.light - views[0].light, (h, w)) * some[n][..., None]
                for n, v in enumerate(views[1:], 1)
            ]
        ).astype(np.float32)
        counts = (some > 0).astype(np.float32)
        counted = np.where(counts[..., None] > 0, lights, np.inf)
        low = counted.min(0).astype(np.float32)
        over = np.where(counts[..., None] > 0, lights - low, 0).astype(np.float32)
        # A difference counts only where both its pixels do.
        across = counts.copy()
        across[:, :, :-1] *= counts[:, :, 1:]
        down = counts.copy()
        down[:, :-1] *= counts[:, 1:]
        start = (
            np.zeros_like(low)
            if common is None
            else cv2.resize(common, (w, h), interpolation=cv2.INTER_LINEAR)
        )
        most = low * np.float32(VEIL_MOST)
        common = _shared(over, across, down, most, np.minimum(start, most), steps)
    assert common is not None and low is not None and lights is not None
    near = common / np.maximum(low * np.float32(VEIL_MOST), 1e-6)
    held = np.clip((near - KEPT_HELD[0]) / (KEPT_HELD[1] - KEPT_HELD[0]), 0, 1)
    layer = np.clip(lights[0] - (low - common), 0, None).astype(np.float32)
    return layer, held.astype(np.float32)


def _alone(
    views: list[_View],
) -> tuple[Floats, tuple[Floats, Floats] | None, float, list[Floats]]:
    """What the first view shows and no side view does where the side
    views are the lighter ones (linear light, the views' size); and where
    that is a lamp's glare, the work as the side views tell it with how
    much of a place is such (0–1), or None without one; and how far the
    side views are from telling one work (the middle place's, of what
    they tell there); and what the first view differs from each side
    view by (:func:`_told`).

    His sixteen cows behind glass (2026-11-16 18:16 UTC, "Spójrz na
    efekt skanowania dzieła za szybą"): from the front the glass mirrored
    him, dark, and his lit hand and fingers; from the sides the bright
    room, a veil twice the light of the dark prints. The first view was
    the least one there, hand and all, and nothing said the hand was a
    reflection; and where the lamp had burnt the first photograph white
    there was no work left under it to keep, only a patch of colour.

    A side view shows the work in another light: the first view should be
    that with a gain and a veil of its own that are even over a hand's
    width (:func:`_told`). What it has over that, and over what every
    side view tells, is its own reflection, narrow or wide. Where the
    first view has a lamp's glare (:data:`GLARE`) the work is what the
    side views tell there."""
    ht, wd = views[0].light.shape[:2]
    w = min(ALONE_WIDTH, wd)
    h = max(16, round(ht * w / wd))
    first = _coarse(views[0].light, (h, w))
    counts = _counts(views, h, w)
    alone: Floats | None = None
    glare: Floats | None = None
    told = []
    says = []
    # What is the first view's own is drawn finer than it is told.
    wf = min(ALONE_FINE, wd)
    hf = max(16, round(ht * wf / wd))
    fine = _coarse(views[0].light, (hf, wf))
    counts_fine = _counts(views, hf, wf)
    counts_full = _counts(views, ht, wd)
    most: Floats | None = None
    owns = []
    plains = []
    for n, view in enumerate(views[1:], 1):
        # The middle of five each way: the shine of a gold letter and what
        # the laying over missed are narrower than any reflection.
        side = cv2.medianBlur(_coarse(view.light, (h, w)), 5)
        apart = cv2.medianBlur(np.ascontiguousarray(first - side), 5)
        tells = _told(side, apart, counts[n], first)
        plain = (apart - tells) * counts[n][..., None]
        seen = view.light + cv2.resize(tells, (wd, ht), interpolation=cv2.INTER_LINEAR)
        seen = np.where(counts_full[n][..., None] > 0, views[0].light - seen, -np.inf)
        most = seen if most is None else np.maximum(most, seen)
        over = _own(
            fine,
            _coarse(view.light, (hf, wf)),
            cv2.resize(tells, (wf, hf), interpolation=cv2.INTER_LINEAR),
            counts_fine[n],
        )
        # Only what every side view says: where one does not show the
        # work (the frame's side) nothing is the first view's alone.
        alone = over if alone is None else np.minimum(alone, over)
        glare = plain if glare is None else np.minimum(glare, plain)
        owns.append(over)
        plains.append(plain)
        told.append(tells)
        says.append(np.clip(side + tells, 0, None) * counts[n][..., None])
    assert alone is not None and glare is not None
    if len(says) == 2:
        # Unless one of the two has a reflection of its own there.
        only, second = _one(says, plains, np.minimum(counts[1], counts[2]))

        def more(
            of: list[Floats], least: Floats, only: Floats, second: Floats, light: Floats
        ) -> Floats:
            # What the darker one says over what both say, less what is
            # narrow where the first view (its ``light``) shows anything.
            over = np.clip(of[0] + (of[1] - of[0]) * second[..., None] - least, 0, None)
            wide = max(3, round(least.shape[1] * ALONE_SHADE)) | 1
            about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (wide, wide))
            near = max(3, round(least.shape[1] * GLARE_NEAR)) | 1
            blown = (light.max(-1) >= BLOWN).astype(np.float32)
            burnt = cv2.GaussianBlur(
                cv2.dilate(blown, np.ones((near, near), np.uint8)), (0, 0), near / 2
            )
            broad = cv2.morphologyEx(over, cv2.MORPH_OPEN, about)
            left = broad + (over - broad) * burnt[..., None]
            return np.asarray(left * only[..., None], np.float32)

        glare = glare + more(plains, glare, only, second, first)
        only = cv2.resize(only, (wf, hf), interpolation=cv2.INTER_LINEAR)
        second = cv2.resize(second, (wf, hf), interpolation=cv2.INTER_LINEAR)
        alone = alone + more(owns, alone, only, second, fine)
    if len(views) < 3:
        # One side view has reflections of its own, and nothing to say
        # which of the two a difference is.
        alone[:] = 0
        glare[:] = 0
    # How far the side views are from telling one work (of what they
    # tell): of a mirror, of foil, each tells what it saw there itself.
    differ = np.zeros(first.shape[:2], np.float32)
    whole = 0.0
    if len(says) > 1:
        differ = np.abs(says[0] - says[1]).sum(-1) / ((says[0] + says[1]).sum(-1) / 2 + GLARE_DARK)
        both = (counts[1] == 1) & (counts[2] == 1)
        whole = float(np.median(differ[both])) if both.any() else 0.0
    alone = np.clip(alone - (ALONE_FROM + ALONE_FROM_OF * fine), 0, fine * ALONE_MOST)
    # A pixel or two by itself is grain.
    few = max(3, round(wf * ALONE_GRAIN)) | 1
    alone = cv2.morphologyEx(
        alone.astype(np.float32), cv2.MORPH_OPEN, np.ones((few, few), np.uint8)
    )
    alone = cv2.GaussianBlur(alone, (0, 0), 0.7)
    out = np.clip(cv2.resize(alone, (wd, ht), interpolation=cv2.INTER_CUBIC), 0, None)
    # Drawn from the plain places about, it is no more on a place than
    # the place itself has over what some side view tells there: a furrow
    # of the paint between two shining ridges has none of their sheen.
    assert most is not None
    most = cv2.GaussianBlur(np.where(np.isfinite(most), most, 0).astype(np.float32), (0, 0), 1.0)
    out = np.clip(np.minimum(out, most), 0, views[0].light).astype(np.float32)

    # A lamp is light of every colour, and no narrow thing. (Under it the
    # work's own lines are gone from the first view, so here it is not
    # held against the lightest the side views have about.)
    lamp = (glare.max(-1) >= GLARE) & (glare.min(-1) >= GLARE * GLARE_COLOUR)
    near = max(3, round(w * GLARE_NEAR)) | 1
    burnt: Floats = cv2.morphologyEx(
        lamp.astype(np.float32), cv2.MORPH_OPEN, np.ones((near, near), np.uint8)
    )
    # And only where the side views tell one work under it (his collage:
    # a black blot in the mirror, the gold edge twice).
    some, which = cv2.connectedComponents((burnt > 0).astype(np.uint8))
    for one in range(1, some):
        if float(np.median(differ[which == one])) > GLARE_DIFFER:
            burnt[which == one] = 0
    if not burnt.any():
        return out, None, whole, told
    patch = cv2.dilate(burnt, np.ones((near, near), np.uint8))
    patch = cv2.GaussianBlur(patch, (0, 0), near / 3)
    patch = np.clip(cv2.resize(patch, (wd, ht), interpolation=cv2.INTER_LINEAR), 0, 1)[..., None]
    # The work as the side views tell it there. Where no side view shows
    # the place (the frame's side) nothing is put in.
    work, shown = _from_sides(views, told, GLARE_BLACK)
    patch = patch * shown[..., None]
    return out, (work, patch.astype(np.float32)), whole, told


def _one(says: list[Floats], plains: list[Floats], counts: Floats) -> tuple[Floats, Floats]:
    """Where only the darker of two side views says what is the first
    view's own (0–1), and whether that is the second (0 or 1); what each
    ``says`` the first should show and what the first has over that,
    ``plains``.

    His drawing behind glass (2026-11-17 06:57 UTC): the lamp in the
    first view lay where a window was in a side view. What both said was
    the lamp's was its red alone, and a green patch stayed. A reflection
    only adds light, so of two side views that differ the darker is the
    nearer to the work. Unless the first view shows what the lighter one
    does: then two of the three agree, and the third is in a shade (his
    cows, each print behind its window in the mount: a dark smear down
    the edge of a print)."""
    near = max(1.0, says[0].shape[1] * GLARE_NEAR / 2)
    lights = [cv2.GaussianBlur(say.sum(-1), (0, 0), near) for say in says]
    gap = np.abs(lights[0] - lights[1])
    one = gap / (np.minimum(lights[0], lights[1]) + GLARE_DARK)
    one = np.clip((one - ALONE_ONE[0]) / (ALONE_ONE[1] - ALONE_ONE[0]), 0, 1)
    second = (lights[1] < lights[0]).astype(np.float32)
    lighter = plains[0] + (plains[1] - plains[0]) * (1 - second[..., None])
    off = np.abs(cv2.GaussianBlur(lighter, (0, 0), near)).sum(-1)
    off = cv2.GaussianBlur(off, (0, 0), near) / (gap + 1e-3)
    three = np.clip((off - ALONE_THREE[0]) / (ALONE_THREE[1] - ALONE_THREE[0]), 0, 1)
    return (one * three * counts).astype(np.float32), second


def _from_sides(views: list[_View], told: list[Floats], black: float) -> tuple[Floats, Floats]:
    """The work as the side views tell it in the first's light (each with
    what the first differs from it by, ``told``), and where any of them
    shows it (0 or 1): mostly the one that is the darker about a place,
    for the other may have a reflection of its own there.

    A black of the work is not made blacker than black by the veil the
    side view has over it (a channel at nothing, a blue blot): no less
    than ``black`` of the side view's own light."""
    ht, wd = views[0].light.shape[:2]
    near = max(3, round(wd * GLARE_NEAR)) | 1
    hidden = _counts(views, ht, wd)
    tellings = []
    for n, (view, differs) in enumerate(zip(views[1:], told, strict=True), 1):
        tells = view.light + cv2.resize(differs, (wd, ht), interpolation=cv2.INTER_LINEAR)
        tells = np.maximum(tells, view.light * np.float32(black))
        light = cv2.GaussianBlur(tells.sum(-1), (0, 0), near / 2)
        tellings.append((tells, np.where(hidden[n] > 0, light, np.inf)))
    least = np.minimum.reduce([light for _, light in tellings])
    work = np.zeros_like(views[0].light)
    share = np.zeros((ht, wd, 1), np.float32)
    for tells, light in tellings:
        with np.errstate(invalid="ignore"):
            counts_for = np.exp(-(light - least) / (0.1 * (np.abs(least) + 0.05)))
        counts_for = np.where(np.isfinite(light), counts_for, 0)[..., None].astype(np.float32)
        work += tells * counts_for
        share += counts_for
    work = (work / np.maximum(share, 1e-6)).astype(np.float32)
    return work, (share[..., 0] > 0).astype(np.float32)


def _mend(
    now: Floats,
    front: Floats,
    alone: Floats,
    soft: Floats,
    views: list[_View],
    told: list[Floats],
) -> Floats:
    """What is still to come off ``now`` (the first view, ``front``, with
    its reflections taken off) where the first view had light of its own,
    ``alone``, and along the edges of the ``soft`` layer: there the
    work's picture is the side views', and only the fine of it the first
    view's. Signed, the views' size.

    His cows the third time (2026-11-17 00:06 UTC, shown the scan of
    1.145.203: "To dalej nie wygląda idealnie. Czy nie możemy zrobić
    miękkich, daleko sięgających przejść?"). A finger in the glass has an
    edge sharper than anything the views can tell of it (they are laid
    over each other to a pixel or three): taken off, it left a light line
    with a dark one beside it, and between the fingers dark wedges. The
    side views have no such hand at all. So about such a place the
    picture is theirs: put in the first view's tones by the line the two
    keep to around (their own veil is warm and made the blacks of a cow
    brown), with the first view's fine detail over it, in grey (the rest
    of an edge is a thin line of the hand's colour), and under it the
    first view's own wide lights and darks (a lamp's soft light is in
    what the side views are told by). Far about and by degrees where the
    work is plain; closely where it has letters or lines, which the side
    views show a few pixels off. On paint the same takes the dark rings
    and the pale blots a glare left."""
    ht, wd = now.shape[:2]
    none = np.zeros_like(now)
    if len(views) < 3:
        return none
    work, shown = _from_sides(views, told, 0.0)
    base = cv2.GaussianBlur(np.clip(work, 0, None).mean(-1), (0, 0), 2.0)
    much = cv2.GaussianBlur(alone.max(-1), (0, 0), 2.0) / (base + MEND_DARK)
    hard = (np.clip((much - MEND_FROM) / (MEND_TO - MEND_FROM), 0, 1) * shown).astype(np.float32)
    # The soft layer's edges (his own figure, dark in the glass, with the
    # room's veil about it).
    by = max(1, round(MEND_EDGE_ABOUT * wd))
    about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * by + 1, 2 * by + 1))
    most = cv2.GaussianBlur(soft.max(-1), (0, 0), 1.0)
    steps = (cv2.dilate(most, about) - cv2.erode(most, about)) / (base + MEND_DARK)
    edge = np.clip((steps - MEND_EDGE[0]) / (MEND_EDGE[1] - MEND_EDGE[0]), 0, 1) * shown
    edge = edge.astype(np.float32)
    if not hard.any() and not edge.any():
        return none
    fine = max(1.0, MEND_FINE * wd)

    def reach(of: Floats, grow: float, soft: float) -> Floats:
        # Worked out the smaller the further it goes.
        less = max(1, round(grow * wd) // 8)
        tiny = cv2.dilate(of, np.ones((less, less), np.uint8))
        tiny = cv2.resize(tiny, (wd // less, ht // less), interpolation=cv2.INTER_AREA)
        by = max(1, round(grow * wd / less))
        about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * by + 1, 2 * by + 1))
        over = cv2.GaussianBlur(cv2.dilate(tiny, about), (0, 0), soft * wd / less)
        over = cv2.resize(over, (wd, ht), interpolation=cv2.INTER_LINEAR)
        return np.asarray(over * over * (3 - 2 * over), np.float32)

    # Far about only where the work is plain: a print lies deeper than
    # its mount, and seen from the side its letters are a few pixels off
    # where the mount's corners put them (and from both sides, twice).
    rough = np.abs(work - cv2.GaussianBlur(work, (0, 0), 2 * fine)).max(-1)
    off = max(1, round(MEND_OFF * wd))
    rough = cv2.dilate(rough, np.ones((2 * off + 1, 2 * off + 1), np.uint8)) / (base + MEND_DARK)
    rough = np.clip((rough - MEND_PLAIN[0]) / (MEND_PLAIN[1] - MEND_PLAIN[0]), 0, 1)
    plain = cv2.GaussianBlur((1 - rough).astype(np.float32), (0, 0), off)
    far = np.maximum(reach(hard, MEND_FAR, MEND_FAR_SOFT), reach(edge, MEND_GROW, MEND_SOFT))
    mask = np.maximum(reach(hard, MEND_GROW, MEND_SOFT), far * plain) * shown

    # The line the two pictures keep to, where nothing is mended (the
    # dark between two fingers is none of the work's, and letters seen
    # twice have no line): worked out small, it is even over a place and
    # far about.
    free = (1 - mask) ** 2
    w = max(64, wd // 4)
    h = max(64, round(ht * w / wd))

    def small(of: Floats) -> Floats:
        return cv2.resize(of, (w, h), interpolation=cv2.INTER_AREA)

    counts = small((free * shown).astype(np.float32))[..., None]
    theirs, mine = small(work), small(now)
    squares, both = small(work * work), small(work * now)
    slope = np.zeros_like(theirs)
    rest = np.zeros_like(theirs)
    left = np.ones((h, w, 1), np.float32)
    for last, wide in enumerate(MEND_REACH):
        sigma = wide * w

        def about_of(of: Floats, sigma: float = sigma) -> Floats:
            return cv2.GaussianBlur(of, (0, 0), sigma).reshape(h, w, -1)

        some = about_of(counts)
        by = np.maximum(some, 1e-6)
        middle, to = about_of(theirs * counts) / by, about_of(mine * counts) / by
        spread = about_of(squares * counts) / by - middle * middle
        along = about_of(both * counts) / by - middle * to
        steep = np.clip(along / (spread + MEND_NOISE**2), 0.3, 2.0)
        sure = left if last == len(MEND_REACH) - 1 else left * np.clip(some / MEND_SURE, 0, 1)
        slope += steep * sure
        rest += (to - steep * middle) * sure
        left = left - sure
    even = MEND_REACH[0] * w / 2
    slope = cv2.resize(
        cv2.GaussianBlur(slope, (0, 0), even), (wd, ht), interpolation=cv2.INTER_LINEAR
    )
    rest = cv2.resize(
        cv2.GaussianBlur(rest, (0, 0), even), (wd, ht), interpolation=cv2.INTER_LINEAR
    )
    work = slope * work + rest

    # Nor is what is wider than they can tell it theirs: what the first
    # differs from a side view by is told from so far about
    # (:data:`ALONE_ABOUT`), and a wide soft light in the first view is
    # in that telling too.
    apart = cv2.GaussianBlur(now - work, (0, 0), fine)
    coarse = cv2.GaussianBlur(small(apart), (0, 0), MEND_COARSE * w)
    apart -= cv2.resize(coarse, (wd, ht), interpolation=cv2.INTER_LINEAR)
    # About letters and lines the colour of a place is theirs only as it
    # is over the letters and the dark between them together: the veil a
    # side view has over the dark between two letters is warm.
    weights = np.array([0.2126, 0.7152, 0.0722], np.float32)
    tint = apart - (apart @ weights)[..., None]
    wider = cv2.GaussianBlur(tint, (0, 0), MEND_TINT * wd)
    apart = apart - (tint - wider) * (1 - plain[..., None])
    detail = now - cv2.GaussianBlur(now, (0, 0), fine)
    # Under a bright reflection the first view's lines are pale (his
    # drawing behind glass, a lit kitchen over a ladder): the side views'.
    light = cv2.GaussianBlur(front.max(-1), (0, 0), 2.0)
    light = np.clip((light - MEND_ALL_LIGHT[0]) / (MEND_ALL_LIGHT[1] - MEND_ALL_LIGHT[0]), 0, 1)
    pressed = np.clip((much - MEND_ALL[0]) / (MEND_ALL[1] - MEND_ALL[0]), 0, 1) * light * shown
    pressed = reach(pressed.astype(np.float32), MEND_GROW, MEND_SOFT)[..., None]
    stays = (detail @ weights)[..., None] * (1 - pressed)
    stays = stays + (work - cv2.GaussianBlur(work, (0, 0), fine)) * pressed
    return np.asarray((apart + detail - stays) * mask[..., None], np.float32)


def _own(first: Floats, side: Floats, tells: Floats, counts: Floats) -> Floats:
    """What the first view has over what a side view tells, place by
    place, as the plain places say it.

    The side views are laid over the first to within a pixel or three,
    and are the softer ones: at every line of the work the two differ by
    the line itself, as much as by any reflection. Held against the
    lightest the side view has about (as this was done first), nothing
    was the first view's own on a drawn cow, and his hand in the glass
    went from the sky about her and stayed on her, in patches with hard
    edges (2026-11-16 22:30 UTC, "przejście powinno być jeszcze
    łagodniejsze"). A reflection does not know the work's lines: what it
    is on a line is what it is beside it. So a place says the less the
    rougher the side view is about it, and a rough place is told by the
    plain ones about, nearer ones first."""
    apart = cv2.medianBlur(np.ascontiguousarray(first - side - tells), 5)
    grey = cv2.GaussianBlur(side.mean(-1), (0, 0), 1.0)
    about = np.ones((5, 5), np.uint8)
    rough = (cv2.dilate(grey, about) - cv2.erode(grey, about)) / (
        ALONE_PLAIN + ALONE_PLAIN_OF * grey
    )
    weigh = (counts / (1 + rough * rough) ** 2).astype(np.float32)
    out = np.zeros_like(apart)
    left = np.ones(weigh.shape, np.float32)
    for last, wide in enumerate(ALONE_REACH):
        sigma = wide * first.shape[1]
        some = cv2.GaussianBlur(weigh, (0, 0), sigma)
        told = cv2.GaussianBlur(apart * weigh[..., None], (0, 0), sigma)
        told /= np.maximum(some, 1e-6)[..., None]
        sure = left if last == len(ALONE_REACH) - 1 else left * np.clip(some / ALONE_SURE, 0, 1)
        out += told * sure[..., None]
        left = left - sure
    return np.asarray(out * counts[..., None], np.float32)


def _told(side: Floats, apart: Floats, counts: Floats, first: Floats) -> Floats:
    """What the first view differs from a side view by, as the places
    about tell it (:data:`ALONE_ABOUT` each way) where the side view is
    as light as here: the phone's own tone mapping lifts each
    photograph's shadows by another amount, so the two differ by one
    thing in the dark of a print and by another in its sky. A place where
    they differ by more than those about it counts for less each time
    round, so a hand or a lamp in one of them does not pull its
    surroundings."""
    size = round(side.shape[1] * ALONE_ABOUT) | 1

    def about(a: Floats) -> Floats:
        return cv2.boxFilter(a, -1, (size, size), borderType=cv2.BORDER_REFLECT)

    # How light, colour by colour: in steps of a factor, each place
    # between two of them. (By its three colours together the orange of a
    # signature was told by the pink sky about it, as light but all blue.)
    step = (np.log(side + 0.01) - math.log(0.01)) / (math.log(1.01) - math.log(0.01))
    step = step * (ALONE_STEPS - 1)
    part = [np.clip(1 - np.abs(step - k), 0, 1).astype(np.float32) for k in range(ALONE_STEPS)]
    # A pixel burnt out in either (in any colour) says nothing of what
    # they differ by.
    seen = counts * ((first.max(-1) < BLOWN) & (side.max(-1) < BLOWN))
    seen = seen.astype(np.float32)[..., None]
    weigh = seen
    tells = np.zeros_like(apart)
    for round_ in range(ALONE_ROUNDS):
        # Strict by degrees: the first telling is pulled by all there is.
        wide = 2.0 ** (ALONE_ROUNDS - 1 - round_)
        totals = [about(of * weigh * apart) for of in part]
        somes = [about(of * weigh) for of in part]
        tells = np.zeros_like(apart)
        for of, total, some, near, near_some in zip(
            part, totals, somes, _beside(totals), _beside(somes), strict=True
        ):
            # With few places as light about, those a little lighter and
            # a little darker say it too (the black patches of a cow
            # under the lamp, the only black about, came out red).
            tells += (
                of * (total + ALONE_FEW * near) / np.maximum(some + ALONE_FEW * near_some, 1e-6)
            )
        # A place is off by its colour that is off the most.
        off = np.abs(apart - tells) / ((ALONE_OFF + ALONE_OFF_OF * first) * wide)
        off = off.max(-1, keepdims=True)
        weigh = (seen / (1 + off * off) ** 2).astype(np.float32)
    return tells


def _beside(steps: list[Floats]) -> list[Floats]:
    """Each step with those beside it, half as much for each step away."""
    up = list(steps)
    for k in range(1, len(steps)):
        up[k] = steps[k] + up[k - 1] / 2
    down = list(steps)
    for k in range(len(steps) - 2, -1, -1):
        down[k] = steps[k] + down[k + 1] / 2
    return [a + b - c for a, b, c in zip(up, down, steps, strict=True)]


def _shared(
    over: Floats, across: Floats, down: Floats, most: Floats, start: Floats, steps: int
) -> Floats:
    """The veil the views share: the least ``m`` (0 … ``most``) with every
    ``m + over[i]`` piecewise smooth. Chambolle and Pock's primal-dual
    steps for Σ‖∇m + ∇over[i]‖₁ + cost·m."""
    step = 0.99 / math.sqrt(8.0 * over.shape[0])
    found: Floats = _steps(
        np.ascontiguousarray(over, np.float32),
        np.ascontiguousarray(across, np.float32),
        np.ascontiguousarray(down, np.float32),
        np.ascontiguousarray(most, np.float32),
        np.ascontiguousarray(start, np.float32),
        steps,
        np.float32(step),
        np.float32(VEIL_COST * step),
    )
    return found


@numba.njit(cache=True)
def _steps(
    over: Floats,
    across: Floats,
    down: Floats,
    most: Floats,
    start: Floats,
    steps: int,
    step: np.float32,
    cost: np.float32,
) -> Floats:
    """:func:`_shared`'s steps, a pixel at a time: as whole arrays they
    were the better part of the half minute his phone waited for a scan
    (2026-11-16, "etap „łączę trzy zdjęcia, usuwam odblaski” trwa bardzo
    długo")."""
    n, h, w, channels = over.shape
    px = np.zeros_like(over)
    py = np.zeros_like(over)
    m = start.copy()
    ahead = m.copy()
    sx = np.zeros_like(m)
    sy = np.zeros_like(m)
    one = np.float32(1)
    for _ in range(steps):
        sx[:] = 0
        sy[:] = 0
        for i in range(n):
            for y in range(h):
                for x in range(w):
                    wx = across[i, y, x]
                    wy = down[i, y, x]
                    size = np.float32(0)
                    for c in range(channels):
                        gx = np.float32(0)
                        gy = np.float32(0)
                        if x < w - 1:
                            gx = (ahead[y, x + 1, c] - ahead[y, x, c]) + (
                                over[i, y, x + 1, c] - over[i, y, x, c]
                            )
                        if y < h - 1:
                            gy = (ahead[y + 1, x, c] - ahead[y, x, c]) + (
                                over[i, y + 1, x, c] - over[i, y, x, c]
                            )
                        a = (px[i, y, x, c] + step * gx) * wx
                        b = (py[i, y, x, c] + step * gy) * wy
                        px[i, y, x, c] = a
                        py[i, y, x, c] = b
                        size += a * a + b * b
                    # Onto the unit ball over both directions and the three
                    # channels at once: a step is one step whatever its
                    # colour, so the veil does not come out in coloured
                    # patches.
                    size = np.float32(math.sqrt(size))
                    for c in range(channels):
                        if size > one:
                            px[i, y, x, c] /= size
                            py[i, y, x, c] /= size
                        sx[y, x, c] += px[i, y, x, c]
                        sy[y, x, c] += py[i, y, x, c]
        for y in range(h):
            for x in range(w):
                for c in range(channels):
                    # The divergence of (sx, sy): what the steps above are
                    # the adjoint of.
                    div = np.float32(0)
                    if x < w - 1:
                        div += sx[y, x, c]
                    if x > 0:
                        div -= sx[y, x - 1, c]
                    if y < h - 1:
                        div += sy[y, x, c]
                    if y > 0:
                        div -= sy[y - 1, x, c]
                    new = m[y, x, c] + step * div - cost
                    if new > most[y, x, c]:
                        new = most[y, x, c]
                    if new < 0:
                        new = np.float32(0)
                    ahead[y, x, c] = 2 * new - m[y, x, c]
                    m[y, x, c] = new
    return m


def _grain(
    less: Floats, alone: Floats, soft: Floats, sides: list[_View], lamp: Floats | None
) -> tuple[Floats, Floats, Floats]:
    """The reflection on the first view (``alone``, its own and drawn
    sharp, and the ``soft`` layer over the rest, ``less``) as it lies on
    the work's own grain: the veil that is on every place, the darkest
    about each place, and the share of what a place has over that darkest
    that is reflection too. ``lamp`` is how much of a place is a glare
    taken out (0–1), or None.

    His oil portrait (2026-11-16 19:01 UTC, "chyba działa zbyt punktowo i
    z ostrym odcięciem"): the window's sheen lay on the ridges of the
    paint and not in the furrows between, the layer is soft and said the
    middle of the two, and that taken off every place left the furrows
    black and the ridges shining. Glass has no such thing: what it
    mirrors lies on the black of a line as on the paper beside it, and
    the first view is no rougher for it than the side views are.

    His cows behind glass again (22:30 UTC, "przejście powinno być
    jeszcze łagodniejsze"): a finger in the glass over the dark of a
    print stayed, for the dark beside it has no such light. So what is
    the first view's own goes as it is drawn, and only the soft layer is
    held to the darkest about, of the view without it. And where a lamp
    was taken out the edge of the patch is a step and no grain: about it
    nothing is a sheen (the lamp left a dark ring)."""
    ht, wd = less.shape[:2]
    near = max(3, round(wd * GRAIN_ABOUT)) | 1
    about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * near + 1, 2 * near + 1))

    def rough(of: Floats) -> tuple[Floats, Floats]:
        # Not a pixel of grain: of what is a pixel and a half wide.
        calm = cv2.GaussianBlur(of, (0, 0), 1.0)
        darkest = cv2.erode(calm, about)
        return darkest, cv2.GaussianBlur(cv2.dilate(calm, about) - darkest, (0, 0), near)

    mine = rough(less + alone)[1]
    counts = _counts([_View(less, 0), *sides], ht, wd)
    theirs = np.full_like(less, np.inf)
    for n, view in enumerate(sides, 1):
        counted = np.where(counts[n][..., None] > 0, rough(view.light)[1], np.inf)
        theirs = np.minimum(theirs, counted)
    with np.errstate(invalid="ignore"):
        rougher = np.clip(1 - theirs / np.maximum(mine, 1e-4), 0, 1)
    sure = np.clip((rougher - GRAIN_FROM) / (GRAIN_SURE - GRAIN_FROM), 0, 1)
    rougher = rougher * sure * sure * (3 - 2 * sure)
    if lamp is not None:
        # A lamp is one piece and wider than the grain; the glints on the
        # ridges of paint are taken out the same way and are the grain.
        by = cv2.morphologyEx((lamp > 0.5).astype(np.float32), cv2.MORPH_OPEN, about)
        by = cv2.dilate(by, about, iterations=3)
        rougher *= 1 - np.clip(cv2.GaussianBlur(by, (0, 0), near), 0, 1)[..., None]

    # Where the first view is the rougher one, what is its own is a sheen
    # on the grain as well and goes as the layer does: taken off place by
    # place it left the paint peppered black (the side views are not laid
    # to the pixel, and their furrows are not the first's).
    grain = rougher.max(-1, keepdims=True)
    soft = soft + alone * grain
    less = less + alone * grain
    alone = alone * (1 - grain)
    low = rough(less)[0]
    low = np.minimum(low, cv2.GaussianBlur(low, (0, 0), near / 2))
    over = cv2.GaussianBlur(np.clip(less - low, 0, None), (0, 0), near)
    sheen = np.minimum(soft, rougher * over)
    # The rest is a veil, and no more of one than the darkest about has:
    # more is the layer's mistake (laid on the lighter places about by
    # their light, a white of his cows came out blue-green).
    veil = alone + np.minimum(soft - sheen, np.clip(low, 0, None))
    share = np.clip(sheen / np.maximum(over, 1e-4), 0, 1)
    low = low + alone
    return veil.astype(np.float32), low.astype(np.float32), share.astype(np.float32)


def _subtract(
    first: Image,
    layer: tuple[Floats, Floats, Floats],
    mend: Floats,
    swap: tuple[Floats, Floats] | None,
    to_photo: NDArray[np.float64],
    quad: Floats,
) -> Image:
    """``first`` less its reflection ``layer`` (:func:`_grain`, laid on it
    by ``to_photo``) and what is to ``mend`` after (:func:`_mend`, laid
    on it likewise) within ``quad``, at full size, a band of rows at a
    time; and where ``swap`` says so (the work under a glare and how much
    of a place is one, laid on it likewise) that work in the first's
    stead."""
    veil, low, share = layer
    h, w = first.shape[:2]
    x0 = max(0, math.floor(quad[:, 0].min()) - 8)
    x1 = min(w, math.ceil(quad[:, 0].max()) + 8)
    y0 = max(0, math.floor(quad[:, 1].min()) - 8)
    y1 = min(h, math.ceil(quad[:, 1].max()) + 8)
    out = first.copy()
    mended = bool(mend.any())
    feather = max(1.5, 0.002 * max(x1 - x0, y1 - y0))
    for top in range(y0, y1, ROWS):
        rows = min(ROWS, y1 - top)
        shift = np.array([[1, 0, -x0], [0, 1, -top], [0, 0, 1]], np.float64)

        def laid(
            what: Floats, how: int, shift: NDArray[np.float64] = shift, rows: int = rows
        ) -> Floats:
            return cv2.warpPerspective(
                what, shift @ to_photo, (x1 - x0, rows), flags=how, borderMode=cv2.BORDER_REPLICATE
            )

        inside = np.zeros((rows, x1 - x0), np.uint8)
        cv2.fillConvexPoly(inside, np.round(quad - [x0, top]).astype(np.int32), 255)
        soft = cv2.GaussianBlur(inside.astype(np.float32) / 255, (0, 0), feather)[..., None]
        light = _linear(first[top : top + rows, x0:x1])
        if swap is not None:
            glare = laid(swap[1], cv2.INTER_LINEAR)
            if glare.any():
                glare = glare[..., None] * soft
                light = light + (laid(swap[0], cv2.INTER_CUBIC) - light) * glare
        sheen = np.clip(light - laid(low, cv2.INTER_LINEAR), 0, None)
        sheen *= np.clip(laid(share, cv2.INTER_LINEAR), 0, 1)
        light = light - (np.clip(laid(veil, cv2.INTER_CUBIC), 0, None) + sheen) * soft
        if mended:
            light = light - laid(mend, cv2.INTER_CUBIC) * soft
        out[top : top + rows, x0:x1] = _srgb(light)
    return out


__all__ = ["Merged", "grown", "merge"]
