"""Reflections taken out of a photograph of a work by two more taken
from the sides (the scan of three, Mateusz 2026-11-16: "pierwsze zdjęcie
na wprost, a kolejne pod większym kątem", "żeby efekt był rewelacyjny").

What his own photographs of a print behind glass showed: in a bright room
every view has a veil over the whole glass, the one from the front most
of all (the room behind the photographer), and each has sharp reflections
of its own (a window, a doorway, his own figure). Replacing bright patches
(:mod:`.glare`) only made smears there.

The work is flat, so within its corners the side photographs are laid
over the first with one homography each (and since 2026-11-17 16:04 UTC
by what is left after it, :func:`_settled`). In linear light a reflection
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
  tell one work, and nothing is touched (:data:`NOT_ONE`). Unless it is
  asked for all the same (``anyway``): he has the two to choose between
  then, with the one photograph proposed (2026-11-17 22:43 UTC, "wybór
  pomiędzy obrazem składanym (inteligentnym) a z pojedynczego zdjęcia -
  zawsze go dawaj, a w sytuacji gdzie podejrzewasz płaskorzeźbę albo
  dzieło które wymaga pojedynczego zdjęcia ustawiaj je jako domyślne").

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
  side views' too (:data:`MEND_ALL`).

And shown the plate of that (2026-11-17 08:08 UTC, the lamp's place
ringed: "Czy „odzyskiwany” z bocznego zdjęcia fragment nie mógłby być
korygowany kolorystycznie do otoczenia? Teraz jeszcze się odcina"; 08:20
UTC: "Tło papieru także się nieznacznie różni odcieniem"). About a lamp
the phone presses the first view flat, so its lines are pale there, and
the lines put in from the side views were black among them: they are
made as strong as the lines about the patch (:func:`_toned`). The paper
in the patch is brought to the paper about it once all is taken off
(:func:`_level`), and the lamp's pale rim is the side views' as well
where every one of them tells less light (:func:`_rim`).

And shown that (08:33 UTC: "A nie możemy delikatnie „wtopić”, rozmyć
krawędzi wklejanej łatki? Oczywiście na zewnątrz, tak żeby nie pokazać
chowanej lampy czy odbicia"). The patch ended on the lamp's soft edge,
and what was left of that edge drew the lamp on the paper. It goes a
little way outward now and ends by degrees (:data:`GLARE_OUT`), and its
tone goes over into the first view's further still
(:data:`GLARE_FEATHER`). Neither over an edge of the work
(:func:`_outward`): on the cows a lamp lay on a print near its edge, and
from the side a print ends a little elsewhere under its mount.

His small oil on canvas (16:04 UTC, the work's card: "Trochę rzeczy się
nie zgadza… Tutaj obraz jakby się rozjeżdżał"). The side views lay 4 to
7 pixels off the first, 22 at the edges: thick paint on a canvas taken
steeply from the side is no plane. What lay elsewhere was read as a
reflection, lines came out double and the light paint grey. After the
homography each side view is now settled on the first place by place
(:func:`_settled`).

When what :func:`merge` makes of the same photographs changes, raise
:data:`..own_works.MERGING`: his works scanned before are then made once
more of their scans' photographs after the update."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import cv2
import numba
import numpy as np
from numpy.typing import NDArray

from . import bands

#: The long side the photographs are laid over each other at.
MATCH_SIDE = 2400
#: Matches a side photograph needs to be laid over the first.
MIN_MATCHES = 40
#: A side view is settled on the first by what its squares of so many
#: pixels are off the first's, one round each (powers of two: the phase
#: correlation is half a pixel out on other sizes).
SETTLE_TILES = (128, 128, 64)
#: What counts as the work's fine there: between so many pixels and so
#: much of the width.
SETTLE_FINE = (1.0, 0.005)
#: A square says how far it is off when the two views' fine agrees in it
#: so well, when that is no more than so much of the square, and no more
#: than so many pixels and so much of their own length from what the
#: squares about it say.
SETTLE_SURE = 0.1
SETTLE_FAR = 0.4
SETTLE_ODD = (1.5, 0.5)
#: The squares are told from each other over so many of them, and where
#: none about a place is sure, over so many.
SETTLE_ABOUT = (0.8, 3.0)
#: The most a place is moved (of the width).
SETTLE_MOST = 0.04
#: The width the reflection layers are worked out at: reflections are
#: soft, and the work's own grain must not show in them.
LAYER_WIDTH = 256
#: The width the views' exposures are compared at.
EVEN_WIDTH = 192
#: The steps a view's exposure is told by: the strongest so many of its
#: own, where they are among the other view's strongest too. And with
#: fewer such than this, the first view's strongest alone.
EVEN_STRONG = 0.2
EVEN_FEW = 50
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
#: What the side views tell under a glare is put in the tones the first
#: view has about it: its light by what the two differ by there, and its
#: lines (what is finer than this, of the work's width) by how strong
#: they are in each; told from so near, and from further where less than
#: :data:`MEND_SURE` about is free; no weaker or stronger than this.
GLARE_LINES = 0.006
GLARE_ABOUT = (0.03, 0.1, 0.4)
GLARE_STRENGTH = (0.4, 1.5)
#: A glare's rim is not burnt out, and is as pale: within so far of the
#: glare (of the work's width) the work is the side views' as well where
#: the first view still has this much more light than they tell (of what
#: they tell; from, and wholly at), over places this wide.
GLARE_RIM = 0.012
GLARE_RIM_MORE = (0.04, 0.1)
GLARE_RIM_OVER = 0.003
#: And so far outward the patch goes in any case, ending over as much
#: again: a lamp's edge is soft, and the patch ended on it.
GLARE_OUT = 0.006
#: And the patch's tone goes over into the first view's by degrees, so
#: far outward (of the work's width).
GLARE_FEATHER = 0.03
#: Neither goes over an edge of the work, nor nearer to one than
#: :data:`GLARE_OUT`: where its light steps by this much of what it is
#: there, or its colour by this much (the share one colour has of the
#: three). A print ends under its mount there, and each view sees that
#: end elsewhere; the lines of a drawing are no such step (graphite on
#: paper is a step of half that colour, and a print pale as its mount
#: one of little light).
GLARE_STEP = (0.4, 0.045)
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
#: And along an edge of what is taken off: where within this far each
#: way (of the work's width) that differs by this much of the work's
#: light (from, and wholly at). What the first view has finer than
#: :data:`MEND_FINE` there is that edge itself.
MEND_SHARP_ABOUT = 0.004
MEND_SHARP = (0.06, 0.15)
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
#: Where the soft layer was this much of the light the work is left with
#: (from, and wholly at; the colour it has the most of), the work was
#: seen through a veil, and its tone and colour are the side views':
#: so far about such a place (of the work's width) and over so much more
#: by degrees. Not where less than this share of the work is free of it.
VEILED = (0.1, 0.3)
VEILED_GROW = 0.01
VEILED_SOFT = 0.02
VEILED_FREE = 0.15
#: And no more comes off a place so than this much of what it has.
VEILED_MOST = 0.75
#: Under a veil of this much of the work's light (from, and wholly at)
#: the first view shows its picture pressed flat, and all of it wider
#: than :data:`MEND_FINE` is the side views': so far about, and over as
#: much again by degrees.
VEILED_HEAVY = (0.5, 1.0)
VEILED_HEAVY_GROW = 0.004
#: The layer is a sheen on the paint's grain and no veil in glass where
#: this much of what a place has over the darkest about it is such a
#: sheen (from, and wholly at; over this far about, of the width), if
#: the layer is not this much light in itself there.
VEILED_SHEEN = (0.25, 0.5)
VEILED_SHEEN_ABOUT = 0.02
VEILED_STRONG = (0.07, 0.12)
#: And the whole work is paint under varnish where its veiled places are
#: such a sheen by this much in the middle (from, and wholly at): his
#: works behind glass had 0.10 to 0.19 there, his oil portrait 0.34 to
#: 0.47.
VEILED_PAINT = (0.22, 0.32)
#: The work's corners are found by eye (Opus, or he moves them after):
#: this much more of the photograph around them is cleaned too (of the
#: work's size, each way), so a cut a little wider has no seam.
AROUND = 0.015
#: The side views told in the first's light differ by this much of what
#: they tell at the middle place of the work, and each of the two has by
#: :data:`NOT_ONE_EACH` of their light more than the other, the work
#: over: they do not show one flat work, and nothing is touched: the
#: merge is in doubt. His collage of a mirror, foil and a circuit board
#: 0.11 and 0.12; glass and oil to 0.06 and to 0.02 on his twenty-two
#: scans, but his Nikifor behind glass with the bright room all over one
#: side view 0.13 and 0.003. (By the first alone, 0.12, while the side
#: views' exposures were told by the first's strongest steps: the collage
#: 0.17 then, and the Nikifor "no flat work".)
NOT_ONE = 0.085
NOT_ONE_EACH = 0.045
#: Less light than this taken off (of the first photograph's) is nothing.
LEAST = 0.01
#: More than this is no reflection: the photographs do not show one work
#: in one light, and nothing is touched: in doubt as well.
MOST = 0.7
#: Rows worked on at once at full size.
ROWS = 512
#: And so many such bands at a time, where the machine has this much
#: memory to spare (GB): a band holds a quarter of a gigabyte the while.
AT_A_TIME = 2
SPARE = 3.0

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
    #: The photographs do not show one flat work in one light (a relief, a
    #: mirror in it: :data:`NOT_ONE`, :data:`MOST`): the first photograph
    #: alone is likely the better picture of it.
    doubt: bool = False
    #: How long each part of it took, in seconds (the side photographs
    #: ``laid`` over the first, what is the first's ``own``, the ``layer``
    #: they share, what was ``mended``, the photograph ``whole``): what a
    #: scan's time goes on is told from his own scans.
    took: dict[str, float] = field(default_factory=dict)


@dataclass
class _View:
    #: The work as this photograph shows it, laid over the first's, linear.
    light: Floats
    #: -1 taken from the left, 1 from the right, 0 the first.
    side: int
    #: The band along that edge where the frame's side hides the work
    #: from this photograph (of the work's width).
    hidden: float = HIDDEN
    #: And how far in its lines are not yet the other views' (no further
    #: than ``hidden``): from there on its tone and colour are the
    #: work's, if not yet what it has finer.
    shows: float = HIDDEN
    #: A side view's photograph as it was given, and where each place of
    #: the view lies in it (across and down): what it shows finer than
    #: the views' size is put in with the work under a glare.
    photo: Image | None = None
    seen: Floats | None = None
    #: What its light was divided by to be even with the first's.
    gains: tuple[float, float, float] = (1.0, 1.0, 1.0)


def merge(first: Image, sides: list[Image], corners: Quad, anyway: bool = False) -> Merged:
    """``first`` (RGB, H × W × 3) without the reflections ``sides`` do not
    share, within ``corners`` (the work: top left, top right, bottom
    right, bottom left, 0–1 across and down). Where the photographs do
    not show one flat work in one light it is ``first`` untouched, in
    doubt; made of them all the same when asked for ``anyway``, and in
    doubt still."""
    took: dict[str, float] = {}
    last = [time.perf_counter()]

    def mark(part: str) -> None:
        now = time.perf_counter()
        took[part] = round(took.get(part, 0.0) + now - last[0], 2)
        last[0] = now

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
    # The side photographs' points are found here, one photograph after
    # another: finding them holds a gigabyte the while (OpenCV is on every
    # core for it by itself), and found by one thread it is the same
    # gigabyte each time (two at a time, the scan took half as much
    # memory again: 2.5 GB against 1.7, measured 2026-11-19 on his
    # scans). The rest of laying each is by itself, so side by side, and
    # kept in their order.
    points = [_marks(_resize(photo, _matched(photo))) for photo in sides]
    each = zip(sides, points, strict=True)
    for laid in bands.pool.map(lambda of: _lay(front, marks, *of), each):
        if laid is not None:
            views.append(laid)
    mark("laid")
    if len(views) < 2:
        return Merged(first, 0, 0.0, took=took)

    _even(views)
    _hide(views)
    whole = float(views[0].light.mean())
    # What the first view alone shows goes first, and the rest is worked
    # out of a first view without it.
    front = views[0].light
    alone, swap, differ, told = _alone(views)
    doubt = differ > NOT_ONE
    if doubt and not anyway:
        mark("own")
        return Merged(first, len(views) - 1, 0.0, True, took)
    less = front - alone
    # A lamp's light is taken off as well, though the work under it is
    # put in from the side views: a lamp alone on an even veil was
    # "nothing taken off", and stayed.
    own = float(alone.mean())
    finer = None
    if swap is not None:
        work = _toned(swap[0], less, swap[1])
        beside = _outward(work, swap[1], wd * GLARE_FEATHER)
        patch = _rim(views, told, less, swap[1], beside)
        swap = (work, patch)
        finer = _finer(views, told, work)
        less = less + (work - less) * patch
        alone = alone * (1 - patch)
        front = front + (work - front) * patch
    mark("own")
    views[0] = _View(less, 0)
    layer, held = _reflection(views)
    # What most of the work has is not taken off.
    layer = (layer - _kept(layer, held)).astype(np.float32)
    soft = np.clip(cv2.resize(layer, (wd, ht), interpolation=cv2.INTER_CUBIC), 0, None)
    removed = (own + float(soft.mean())) / max(whole, 1e-6)
    doubt = doubt or removed > MOST
    if removed < LEAST or (removed > MOST and not anyway):
        mark("layer")
        return Merged(first, len(views) - 1, 0.0, doubt, took)
    # The layer's pixels → the photograph's (a pixel's place is its middle).
    to_photo = (
        _larger(1 / scale, 1 / scale)
        @ np.linalg.inv(to_work)
        @ _larger(wd / soft.shape[1], ht / soft.shape[0])
    )
    lamp = None if swap is None else swap[1]
    veil, low, share = _grain(less, alone, soft, views[1:], lamp)
    mark("layer")
    # The first view as it comes out of that, and what is still to mend.
    now = front - veil - np.clip(front - low, 0, None) * share
    mend, theirs = _mend(now, front, alone, soft, views, told)
    veiled, pressed = _veiled(now - mend, soft, views, share)
    mend = mend + veiled
    theirs = np.maximum(theirs, pressed)
    if finer is None and theirs.any():
        finer = _finer(views, told, _from_sides(views, told, 0.0)[0])
    if swap is not None:
        mend = mend + _level(now - mend, swap[0], swap[1], beside)
    mark("mended")
    clean = _subtract(first, (veil, low, share), mend, swap, to_photo, quad, finer, theirs)
    mark("whole")
    return Merged(clean, len(views) - 1, round(removed, 4), doubt, took)


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
    """``light`` as a photograph's levels; the light is spent on it."""
    light *= 65535
    light += 0.5
    np.clip(light, 0, 65535, out=light)
    return _FROM_LINEAR[light.astype(np.uint16)]


def _marks(img: Image) -> tuple[Any, Any]:
    """What a photograph is known by in another: its points and what is
    about each."""
    sift = cv2.SIFT_create(8000, contrastThreshold=0.02)  # type: ignore[attr-defined]
    found: tuple[Any, Any] = sift.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), None)
    return found


def _matched(photo: Image) -> float:
    """How much smaller a side photograph is matched than it was given:
    its longer side :data:`MATCH_SIDE` at most."""
    return min(1.0, MATCH_SIDE / max(photo.shape[:2]))


def _lay(
    front: Image, marks: tuple[Any, Any], photo: Image, theirs: tuple[Any, Any] | None = None
) -> _View | None:
    """A side photograph laid over the work as the first shows it (with
    its ``marks``), or None when too little of them matches (another
    work, a blur). ``theirs``: the photograph's own marks at the size it
    is matched at (:func:`_matched`), where they were found already."""
    scale = _matched(photo)
    side = _resize(photo, scale)
    k1, d1 = marks
    k2, d2 = theirs or _marks(side)
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
    over, seen = _settled(front, side, found)
    # A pixel's place is its middle, in the photograph as it was given.
    seen = ((seen + 0.5) / scale - 0.5).astype(np.float32)
    return _View(
        _linear(over), -1 if lean > 0.03 else 1 if lean < -0.03 else 0, photo=photo, seen=seen
    )


def _settled(front: Image, side: Image, found: NDArray[Any]) -> tuple[Image, Floats]:
    """The ``side`` photograph laid over ``front`` by the homography
    ``found`` and then, place by place, by what its fine is still off
    the first's; and where each place of ``front`` lies in ``side``
    (across and down).

    His small oil on canvas in a floating frame (2026-11-17 16:04 UTC:
    "Trochę rzeczy się nie zgadza… czy najpierw nie trzeba dokładnie
    nanieść poszczególnych zdjęć na siebie a dopiero potem robić dalsze
    edycje? Tutaj obraz jakby się rozjeżdżał"). One homography laid the
    side views 4 to 7 pixels off the first, 22 at the edges, of a work
    1200 wide: a canvas with thick paint, taken steeply from the side, is
    no plane, nor is the lens without its bend. Every stroke that lay
    elsewhere was read as a reflection: lines came out double and the
    light paint grey. His earlier oils were up to 13 pixels off at their
    corners. What is left is smooth over the work, so it is measured
    square by square (:func:`_off`), made one field (:func:`_field`) and
    the photograph is laid again by it, a few rounds: a tenth of a pixel
    is left."""
    ht, wd = front.shape[:2]
    back = np.linalg.inv(found)
    grid = np.mgrid[0:ht, 0:wd].astype(np.float32)
    moved = np.zeros((2, ht, wd), np.float32)
    most = wd * SETTLE_MOST

    def laid() -> tuple[Image, Floats]:
        at = np.stack([grid[1] + moved[0], grid[0] + moved[1]], -1).reshape(-1, 1, 2)
        seen = cv2.perspectiveTransform(at.astype(np.float64), back).astype(np.float32)
        seen = seen.reshape(ht, wd, 2)
        return cv2.remap(side, seen[..., 0], seen[..., 1], cv2.INTER_LINEAR), seen

    over, seen = laid()
    first = _fine(_linear(front))
    for size in SETTLE_TILES:
        tile = size
        while tile > 32 and tile > min(wd, ht) // 4:
            tile //= 2
        if tile > min(wd, ht) // 2:
            break
        field = _field(_off(first, _fine(_linear(over)), tile), tile, (ht, wd))
        if field is None:
            break
        moved = np.clip(moved + field, -most, most)
        over, seen = laid()
    return over, seen


def _fine(light: Floats) -> Floats:
    """What a view is known by from place to place: the fine of its
    light, whatever the exposure and the veil over it."""
    tone = np.log(light.mean(-1) + 0.02)
    wide = max(2 * SETTLE_FINE[0], light.shape[1] * SETTLE_FINE[1])
    fine = cv2.GaussianBlur(tone, (0, 0), SETTLE_FINE[0]) - cv2.GaussianBlur(tone, (0, 0), wide)
    return np.asarray(fine, np.float32)


def _off(first: Floats, other: Floats, tile: int) -> Floats:
    """How far ``other`` lies off ``first`` in each square of ``tile``
    pixels, half a square apart: across, down and how sure (0–1)."""
    ht, wd = first.shape
    step = tile // 2
    window = cv2.createHanningWindow((tile, tile), cv2.CV_32F)
    rows = range(0, ht - tile + 1, step)
    cols = range(0, wd - tile + 1, step)
    off = np.zeros((len(rows), len(cols), 3), np.float32)
    for i, y in enumerate(rows):
        for j, x in enumerate(cols):
            # Copies: the correlation writes into what it is given.
            one = first[y : y + tile, x : x + tile].copy()
            two = other[y : y + tile, x : x + tile].copy()
            (across, down), sure = cv2.phaseCorrelate(one, two, window)
            off[i, j] = (across, down, sure)
    return off


def _field(off: Floats, tile: int, shape: tuple[int, int]) -> Floats | None:
    """What the squares say (:func:`_off`) as one smooth field over the
    work (across and down, 2 × H × W), or None when none of them is sure.
    A square that says another thing than those about it has a reflection
    in it, or nothing: it is told by them."""
    if off.shape[0] < 2 or off.shape[1] < 2:
        return None
    far = np.hypot(off[..., 0], off[..., 1])
    sure = np.where((off[..., 2] >= SETTLE_SURE) & (far <= SETTLE_FAR * tile), off[..., 2], 0)
    sure = np.clip(sure, 0, 1).astype(np.float32)
    for _ in range(2):
        about = _about(np.where(sure[..., None] > 0, off[..., :2], np.nan))
        odd = np.hypot(off[..., 0] - about[..., 0], off[..., 1] - about[..., 1])
        allowed = np.maximum(SETTLE_ODD[0], SETTLE_ODD[1] * np.hypot(about[..., 0], about[..., 1]))
        sure = np.where(odd > allowed, 0, sure).astype(np.float32)  # NaN: nothing about, stays
    if not sure.any():
        return None

    def told(sigma: float) -> tuple[Floats, Floats]:
        edge = cv2.BORDER_REPLICATE
        weight = cv2.GaussianBlur(sure, (0, 0), sigma, borderType=edge)
        each = [
            cv2.GaussianBlur(off[..., k] * sure, (0, 0), sigma, borderType=edge) for k in (0, 1)
        ]
        return np.stack(each, -1) / np.maximum(weight, 1e-6)[..., None], weight

    near, weight = told(SETTLE_ABOUT[0])
    wide, _ = told(SETTLE_ABOUT[1])
    mesh = np.where(weight[..., None] > 0.2, near, wide).astype(np.float32)
    # One more square about, going on as the last two did.
    mesh = np.concatenate([2 * mesh[:1] - mesh[1:2], mesh, 2 * mesh[-1:] - mesh[-2:-1]], 0)
    mesh = np.concatenate(
        [2 * mesh[:, :1] - mesh[:, 1:2], mesh, 2 * mesh[:, -1:] - mesh[:, -2:-1]], 1
    )
    # A square's middle is where it says it for; the first, one step out.
    step = tile // 2
    start = (tile - 1) / 2 - step
    to_mesh = np.array([[1 / step, 0, -start / step], [0, 1 / step, -start / step]], np.float64)
    field = cv2.warpAffine(
        mesh,
        to_mesh,
        (shape[1], shape[0]),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return np.ascontiguousarray(field.transpose(2, 0, 1))


def _about(said: Floats) -> Floats:
    """The middle one of what each square and the eight about it say
    (NaN: says nothing; NaN where none of the nine does)."""
    rows, cols = said.shape[:2]
    wide = np.pad(said, ((1, 1), (1, 1), (0, 0)), constant_values=np.nan)
    nine = np.stack([wide[i : i + rows, j : j + cols] for i in range(3) for j in range(3)])
    none = np.isnan(nine).all(0)
    middle = np.nanmedian(np.where(none, 0, nine), 0)
    return np.where(none, np.nan, middle).astype(np.float32)


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


def _counts(views: list[_View], h: int, w: int, tone: bool = False) -> Floats:
    """How much each view counts (0–1) at this size: a side one not in
    the band along the edge it was taken from, and by degrees beyond it
    (counting at once, what was taken off the work changed in a line
    down it). For the work's ``tone`` and colour alone it counts from
    where its lines are the other views' (:attr:`_View.shows`), and
    sooner."""
    counts = np.ones((len(views), h, w), np.float32)
    for n, view in enumerate(views):
        if view.side == 0:
            continue
        band = max(1, round(w * (view.shows if tone else view.hidden)))
        ease = max(1, round(w * (HIDDEN_SHOWN if tone else HIDDEN_EASE)))
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
        unlike = 0
        for k in range(1, max(2, round(HIDDEN / 0.01))):
            a = own[:, k * strip : (k + 1) * strip]
            like = max(
                float((a * b).sum() / (math.sqrt(float((a * a).sum() * (b * b).sum())) + 1e-9))
                for b in (other[:, k * strip : (k + 1) * strip] for other in others)
            )
            if like < HIDDEN_LIKE:
                unlike = k
        shown = unlike == 0
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
        view.shows = min(view.hidden, max(HIDDEN_SHOWN, (unlike + 1.5) * 0.01, last / wd))


def _even(views: list[_View]) -> None:
    """The side views brought to the first's exposure and white balance.
    The work's own edges are in every view, so per channel the gain is
    what the side view's steps across them are of the first's (a
    reflection only adds light, and no place need be clean of it in
    both): of the steps that are strong in both.

    His drawing behind glass scanned in one arc (2026-11-18 16:11 UTC:
    "w Test i Test 4 które są za szybą mogłoby być lepiej"): pencil on
    paper, a lamp burnt into the first photograph and his own figure dark
    in the glass. The first view's strongest steps were the lamp's rim
    and the figure's outline, which no side view has: the gains came out
    a half and a sixth of what they were, the side views twice and four
    times too light and blue, and the lamp stayed as a pale patch with
    green lines in it. (The side photographs are the room tracking's
    since 1.145.240, in another white balance than the first, which the
    gains are there to even out.)"""
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
            strong = (
                (np.abs(a) >= np.quantile(np.abs(a), 1 - EVEN_STRONG))
                & (np.abs(b) >= np.quantile(np.abs(b), 1 - EVEN_STRONG))
                & (a * b > 0)
            )
            if int(strong.sum()) < EVEN_FEW:
                strong = np.abs(a) >= np.quantile(np.abs(a), 0.9)
            gains.append(float(np.clip(np.median(b[strong] / a[strong]), 0.5, 2.0)))
        # The exposure is one for the three channels; the white balance
        # moves between two photographs of one wall only so far. More is
        # the work's own shine (gold letters, which are yellow from the
        # front and white from the side), not the camera's.
        middle = sorted(gains)[1]
        gains = [float(np.clip(g, middle * (1 - BALANCE), middle * (1 + BALANCE))) for g in gains]
        for c in range(3):
            view.light[..., c] /= gains[c]
        view.gains = (gains[0], gains[1], gains[2])


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
    they tell there; nothing where one of the two is the lighter all
    over); and what the first view differs from each side view by
    (:func:`_told`).

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
    told = []
    says = []
    lights = []
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
        owns.append(over)
        plains.append(plain)
        told.append(tells)
        says.append(np.clip(side + tells, 0, None) * counts[n][..., None])
        lights.append(side)

    def said(parts: list[Floats], count: Floats, light: Floats) -> Floats:
        # Only what every side view says: where one does not show the
        # work (the frame's side) nothing is the first view's alone. But
        # about where the first view (its ``light``) is burnt out: it
        # shows nothing of the work there, and those that do show the
        # place say it. (A lamp that reached the frame, 2026-11-18 17:39
        # UTC: "znowu pokazują się ostre krawędzie w miejscach podmian".
        # The end of it stayed in the band along the frame, cut off
        # where the side view from there begins to count.)
        near = max(3, round(light.shape[1] * GLARE_NEAR)) | 1
        wide = max(3, round(light.shape[1] * ALONE_SHADE)) | 1
        blown = cv2.morphologyEx(
            (light.max(-1) >= BLOWN).astype(np.float32),
            cv2.MORPH_OPEN,
            np.ones((near, near), np.uint8),
        )
        blown = cv2.dilate(blown, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (wide, wide)))
        blown = cv2.GaussianBlur(blown, (0, 0), wide / 4)
        most = np.maximum.reduce(parts)
        least: Floats | None = None
        for n, part in enumerate(parts, 1):
            mute = ((1 - count[n]) * blown)[..., None]
            part = part + (most - part) * mute
            least = part if least is None else np.minimum(least, part)
        assert least is not None
        return np.asarray(least, np.float32)

    alone = said(owns, counts_fine, fine)
    glare = said(plains, counts, first)
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
            # Burnt out as widely: specks of a sheen are no lamp, and
            # under them a side view put the mount in for a print's edge.
            blown = cv2.morphologyEx(
                (light.max(-1) >= BLOWN).astype(np.float32), cv2.MORPH_OPEN, about
            )
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
        if both.any():
            whole = float(np.median(differ[both]))
            # A reflection only adds light: with the room in the glass
            # all over one side view, that one is the lighter of the two
            # everywhere and the work is what the other shows. Of a work
            # that is no flat one each is the lighter somewhere. (His
            # Nikifor behind glass, 2026-11-18 16:11 UTC, "w Test i Test
            # 4 które są za szybą mogłoby być lepiej": it was "no flat
            # work", and the one photograph was proposed.)
            by = (lights[1] - lights[0]).sum(-1)
            by = (by / ((lights[0] + lights[1]).sum(-1) / 2 + GLARE_DARK))[both]
            each = min(float(np.clip(by, 0, None).mean()), float(np.clip(-by, 0, None).mean()))
            if each <= NOT_ONE_EACH:
                whole = 0.0
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


def _toned(work: Floats, to: Floats, patch: Floats) -> Floats:
    """``work`` (what the side views tell) in the tones of ``to`` (the
    first view) as the places about ``patch`` have them.

    His drawing behind glass (2026-11-17 08:08 UTC, the place of the lamp
    ringed on the plate: "Czy „odzyskiwany” z bocznego zdjęcia fragment
    nie mógłby być korygowany kolorystycznie do otoczenia? Teraz jeszcze
    się odcina"). About a lamp the phone presses the first view flat and
    the lamp's glow lies over it: its pencil lines are pale there. The
    side views have neither, and the lines put in from them were black
    beside the pale ones, on paper a shade lighter."""
    ht, wd = work.shape[:2]
    weights = np.array([0.2126, 0.7152, 0.0722], np.float32)
    fine = max(1.0, GLARE_LINES * wd)
    # Not the patch, nor right beside it.
    by = max(3, round(wd * GLARE_NEAR)) | 1
    free = 1 - cv2.dilate(patch[..., 0], np.ones((by, by), np.uint8))
    free = (free * free).astype(np.float32)

    def lines(of: Floats) -> Floats:
        # Less the grain, which the first view has more of.
        grey = of @ weights
        return np.asarray(
            cv2.GaussianBlur(grey, (0, 0), 1.0) - cv2.GaussianBlur(grey, (0, 0), fine), np.float32
        )

    w = max(64, wd // 4)
    h = max(64, round(ht * w / wd))

    def small(of: Floats) -> Floats:
        return cv2.resize(of, (w, h), interpolation=cv2.INTER_AREA).reshape(h, w, -1)

    counts = small(free)
    apart = small((to - work) * free[..., None])
    theirs, mine = small(lines(work) ** 2 * free), small(lines(to) ** 2 * free)
    light = np.zeros_like(apart)
    strong = np.zeros_like(counts)
    left = np.ones_like(counts)
    for last, wide in enumerate(GLARE_ABOUT):

        def about(of: Floats, sigma: float = wide * w) -> Floats:
            return cv2.GaussianBlur(of, (0, 0), sigma).reshape(h, w, -1)

        some = about(counts)
        sure = left if last == len(GLARE_ABOUT) - 1 else left * np.clip(some / MEND_SURE, 0, 1)
        light += about(apart) / np.maximum(some, 1e-6) * sure
        strong += np.sqrt(about(mine) / np.maximum(about(theirs), 1e-12)) * sure
        left = left - sure
    light = cv2.resize(light, (wd, ht), interpolation=cv2.INTER_LINEAR)
    strong = cv2.resize(np.clip(strong, *GLARE_STRENGTH), (wd, ht), interpolation=cv2.INTER_LINEAR)
    plain = cv2.GaussianBlur(work, (0, 0), fine)
    return np.asarray(plain + light + (work - plain) * strong[..., None], np.float32)


def _level(now: Floats, work: Floats, patch: Floats, beside: Floats) -> Floats:
    """What is to come off ``now`` (the first view cleaned) in ``patch``,
    where it is ``work`` (the side views' telling) put in, for it to lie
    as far from that telling as the places about the patch do; and off
    the places next to the patch (so far from it, ``beside``), less and
    less outward.

    The same plate, a quarter of an hour on (2026-11-17 08:20 UTC: "Tło
    papieru także się nieznacznie różni odcieniem"): what is taken off
    after the work is put in under a lamp (the veil, the sheen, the
    mending about it) is not the same in the patch and beside it, and
    the paper under the lamp came out a few levels lighter and cooler.

    And shown that (08:33 UTC: "A nie możemy delikatnie „wtopić”, rozmyć
    krawędzi wklejanej łatki? Oczywiście na zewnątrz, tak żeby nie
    pokazać chowanej lampy czy odbicia"): the patch ended at the lamp's
    edge, and what little of the lamp's glow was left beside it drew
    that edge. Only the tone goes over; the lines beside the patch stay
    the first view's (the side views have them a pixel or three off)."""
    ht, wd = now.shape[:2]
    reach = max(2.0, wd * GLARE_FEATHER)
    outward = np.clip(1 - beside / reach, 0, 1)
    outward = outward * outward * (3 - 2 * outward)
    over = np.maximum(patch[..., 0], outward).astype(np.float32)
    away = cv2.distanceTransform((patch[..., 0] <= 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    free = ((away > reach) * (1 - patch[..., 0])).astype(np.float32)
    w = max(64, wd // 4)
    h = max(64, round(ht * w / wd))

    def small(of: Floats) -> Floats:
        return cv2.resize(of, (w, h), interpolation=cv2.INTER_AREA).reshape(h, w, -1)

    apart = now - work
    counts = small(free)
    beside = small(apart * free[..., None])
    about = np.zeros_like(beside)
    left = np.ones_like(counts)
    for last, wide in enumerate(GLARE_ABOUT):
        some = cv2.GaussianBlur(counts, (0, 0), wide * w).reshape(h, w, 1)
        sure = left if last == len(GLARE_ABOUT) - 1 else left * np.clip(some / MEND_SURE, 0, 1)
        about += cv2.GaussianBlur(beside, (0, 0), wide * w) / np.maximum(some, 1e-6) * sure
        left = left - sure
    about = cv2.resize(about, (wd, ht), interpolation=cv2.INTER_LINEAR)
    # Told of the patch and of what is beside it alone: beyond an edge of
    # the work the two are another thing apart.
    fine = max(1.0, GLARE_LINES * wd)
    of = (over > 0).astype(np.float32)
    here = cv2.GaussianBlur(apart * of[..., None], (0, 0), fine)
    here = here / np.maximum(cv2.GaussianBlur(of, (0, 0), fine), 1e-3)[..., None]
    return np.asarray((here - about) * over[..., None], np.float32)


def _rim(
    views: list[_View], told: list[Floats], less: Floats, patch: Floats, beside: Floats
) -> Floats:
    """``patch`` (how much of a place is a glare's, 0–1) with the glare's
    rim: where about it the first view (``less``, without what was told
    to be its own) still has more light than every side view tells. The
    rim of his lamp stayed on the drawing, a pale crescent at its end and
    a pale line along it. Every one of them: the shade of a mount on the
    edge of a print is in one, and came into the cows as a dark notch.

    And a little way outward in any case (so far from it, ``beside``),
    ending by degrees."""
    wd = less.shape[1]
    by = max(1, round(wd * GLARE_RIM))
    about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * by + 1, 2 * by + 1))
    zone = cv2.dilate((patch[..., 0] > 0.5).astype(np.float32), about)
    over = max(1.0, wd * GLARE_RIM_OVER)
    more: Floats | None = None
    tellings = _tellings(views, told, GLARE_BLACK)
    for tells, light in tellings:
        lit = cv2.GaussianBlur(tells.mean(-1), (0, 0), over)
        has = cv2.GaussianBlur((less - tells).mean(-1), (0, 0), over) / (lit + GLARE_DARK)
        has = np.where(np.isfinite(light), has, 0).astype(np.float32)
        more = has if more is None else np.minimum(more, has)
    assert more is not None
    more = np.clip((more - GLARE_RIM_MORE[0]) / (GLARE_RIM_MORE[1] - GLARE_RIM_MORE[0]), 0, 1)
    rim = cv2.GaussianBlur((more * zone).astype(np.float32), (0, 0), over / 2)
    # Outward by degrees (2026-11-17 08:33 UTC: "A nie możemy delikatnie
    # „wtopić”, rozmyć krawędzi wklejanej łatki? Oczywiście na zewnątrz").
    out = max(1.0, wd * GLARE_OUT)
    outward = np.clip(2 - beside / out, 0, 1)
    outward = outward * outward * (3 - 2 * outward)
    shown = np.isfinite(np.minimum.reduce([light for _, light in tellings]))
    wider = np.maximum(rim, outward * shown)
    return np.asarray(np.maximum(patch, wider[..., None]), np.float32)


def _outward(work: Floats, patch: Floats, far: float) -> Floats:
    """How far each place is from ``patch`` (pixels; infinite beyond
    ``far``), going about the edges of ``work``: there is no way over a
    step of its light (:data:`GLARE_STEP`), nor nearer to one than
    :data:`GLARE_OUT`.

    The cows, each print behind its window in a mount: a lamp lay on a
    print near its edge, and what was put in from the side went outward
    over that edge. From the side the print ends a little elsewhere under
    its mount: a pale bite came into the print's edge, and a grey bar
    onto the mount above it."""
    wd = patch.shape[1]
    by = max(1.0, wd * GLARE_OUT / 2)
    soft = cv2.GaussianBlur(work, (0, 0), by)

    def step(of: Floats) -> Floats:
        # A step so high, blurred so far, is as steep as this at its middle.
        steep = np.hypot(cv2.Sobel(of, cv2.CV_32F, 1, 0), cv2.Sobel(of, cv2.CV_32F, 0, 1)) / 8
        return np.asarray(steep * by * np.sqrt(2 * np.pi), np.float32)

    light = soft.mean(-1)
    shares = soft / (soft.sum(-1, keepdims=True) + 3 * GLARE_DARK)
    edge = step(light) > GLARE_STEP[0] * (light + GLARE_DARK)
    for colour in range(3):
        edge |= step(np.ascontiguousarray(shares[..., colour])) > GLARE_STEP[1]
    near = 2 * max(1, round(wd * GLARE_OUT)) + 1
    about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (near, near))
    way = 1 - cv2.dilate(edge.astype(np.uint8), about)
    # Nor from what of the patch lies at an edge: that stays as it is.
    reached = np.minimum((patch[..., 0] > 0.5).astype(np.uint8), way)
    away = np.where(reached > 0, 0, np.inf).astype(np.float32)
    if not reached.any():
        return away
    # Only about the patch: nothing further is reached.
    rows, cols = np.nonzero(reached)
    span = int(np.ceil(far)) + 1
    top, left = max(0, rows.min() - span), max(0, cols.min() - span)
    box = (slice(top, rows.max() + span + 1), slice(left, cols.max() + span + 1))
    reached, way, within = reached[box], way[box], away[box]
    steps = (
        cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3)),
        np.ones((3, 3), np.uint8),
    )
    for n in range(1, span):
        grown = np.maximum(reached, np.minimum(cv2.dilate(reached, steps[n % 2]), way))
        within[grown > reached] = n
        reached = grown
    return away


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


def _tellings(views: list[_View], told: list[Floats], black: float) -> list[tuple[Floats, Floats]]:
    """What each side view tells of the work in the first's light (with
    what the first differs from it by, ``told``; no less than ``black``
    of its own light), and how light that is about each place (the three
    colours together; infinite where the view does not show the work)."""
    ht, wd = views[0].light.shape[:2]
    near = max(3, round(wd * GLARE_NEAR)) | 1
    hidden = _counts(views, ht, wd)
    tellings = []
    for n, (view, differs) in enumerate(zip(views[1:], told, strict=True), 1):
        tells = view.light + cv2.resize(differs, (wd, ht), interpolation=cv2.INTER_LINEAR)
        tells = np.maximum(tells, view.light * np.float32(black))
        light = cv2.GaussianBlur(tells.sum(-1), (0, 0), near / 2)
        tellings.append((tells, np.where(hidden[n] > 0, light, np.inf)))
    return tellings


def _from_sides(views: list[_View], told: list[Floats], black: float) -> tuple[Floats, Floats]:
    """The work as the side views tell it in the first's light (each with
    what the first differs from it by, ``told``), and where any of them
    shows it (0 or 1): mostly the one that is the darker about a place,
    for the other may have a reflection of its own there.

    A black of the work is not made blacker than black by the veil the
    side view has over it (a channel at nothing, a blue blot): no less
    than ``black`` of the side view's own light."""
    ht, wd = views[0].light.shape[:2]
    tellings = _tellings(views, told, black)
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


def _finer(
    views: list[_View], told: list[Floats], work: Floats
) -> Callable[[NDArray[np.float64], Floats], Floats]:
    """What the side photographs show of the work finer than the views'
    size, as strong as ``work`` (what the views tell under a glare,
    toned) has their lines: for a part of the first photograph, given
    where the views' pixels lie in it and how much of each of its places
    is a glare.

    His drawing with the lamp taken out (Mateusz 2026-11-18 17:41 UTC:
    "wklejki są niższej jakości…"). The views are a third of the first
    photograph's size, which is enough to tell a reflection by; what
    comes off the first leaves it as sharp as it was. But under a lamp
    the first has nothing, and the work put in there was the views':
    soft lines among sharp ones. The side photographs are larger than
    the views, and what they have over them is put in as well."""
    ht, wd = work.shape[:2]
    weights = np.array([0.2126, 0.7152, 0.0722], np.float32)
    tellings = _tellings(views, told, GLARE_BLACK)
    least = np.minimum.reduce([light for _, light in tellings])
    wide = max(2.0, GLARE_ABOUT[0] * wd)
    near = max(3, round(wd * GLARE_NEAR)) | 1

    def lines(of: Floats) -> Floats:
        grey = of @ weights
        fine = (grey - cv2.GaussianBlur(grey, (0, 0), 2.0)) ** 2
        return np.asarray(cv2.GaussianBlur(fine, (0, 0), wide), np.float32)

    mine = lines(work)
    parts: list[tuple[Image, Floats, Floats, Floats, Floats]] = []
    whole = np.zeros((ht, wd), np.float32)
    for view, (_, light) in zip(views[1:], tellings, strict=True):
        # As much of each as it tells of the work there (:func:`_from_sides`).
        with np.errstate(invalid="ignore"):
            share = np.exp(-(light - least) / (0.1 * (np.abs(least) + 0.05)))
        share = np.where(np.isfinite(light), share, 0).astype(np.float32)
        whole += share
        if view.photo is None or view.seen is None:
            continue
        strong = np.sqrt(mine / np.maximum(lines(view.light), 1e-12))
        share = share * np.clip(strong, 0, GLARE_STRENGTH[1])
        # With the room in the glass over it a view's finest is mostly its
        # grain (his Nikifor: speckles where the lamp's end had been): the
        # less of it, the less of its light there is the work's.
        own = cv2.GaussianBlur(view.light.sum(-1), (0, 0), near / 2)
        with np.errstate(invalid="ignore"):
            clear = np.clip(light / np.maximum(own, 1e-6), 0, 1)
        share = share * np.where(np.isfinite(light), clear * clear, 0).astype(np.float32)
        parts.append((view.photo, view.seen, view.light, share, np.array(view.gains, np.float32)))
    whole = np.maximum(whole, 1e-6)
    # Each one's share of them all, once and not at every asking.
    parts = [(*part[:3], part[3] / whole, part[4]) for part in parts]

    def fine(to_part: NDArray[np.float64], glare: Floats) -> Floats:
        # Asked for band by band of the first photograph, two bands at a
        # time: what it holds the while is kept small (each step in the
        # place of the last, and the same numbers as before).
        out = np.zeros((*glare.shape[:2], 3), np.float32)
        some = glare > 0
        down, across = np.flatnonzero(some.any(1)), np.flatnonzero(some.any(0))
        if not len(down) or not parts:
            return out
        r0, r1, c0, c1 = down[0], down[-1] + 1, across[0], across[-1] + 1
        at = np.empty((r1 - r0, c1 - c0, 2), np.float64)
        at[..., 0] = np.arange(c0, c1)
        at[..., 1] = np.arange(r0, r1)[:, None]
        at = cv2.perspectiveTransform(at.reshape(-1, 1, 2), np.linalg.inv(to_part))
        at = at.reshape(r1 - r0, c1 - c0, 2)
        u, v = at[..., 0].astype(np.float32), at[..., 1].astype(np.float32)
        del at

        def here(of: Floats, how: int = cv2.INTER_LINEAR) -> Floats:
            return cv2.remap(of, u, v, how, borderMode=cv2.BORDER_REPLICATE)

        for photo, seen, light, share, gains in parts:
            sharp = cv2.remap(
                photo,
                here(seen[..., 0]),
                here(seen[..., 1]),
                cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            more = _linear(sharp)
            more /= gains
            more -= here(light, cv2.INTER_CUBIC)
            more *= here(share)[..., None]
            out[r0:r1, c0:c1] += more
        return out

    return fine


def _mend(
    now: Floats,
    front: Floats,
    alone: Floats,
    soft: Floats,
    views: list[_View],
    told: list[Floats],
) -> tuple[Floats, Floats]:
    """What is still to come off ``now`` (the first view, ``front``, with
    its reflections taken off) where the first view had light of its own,
    ``alone``, and along the edges of the ``soft`` layer: there the
    work's picture is the side views', and only the fine of it the first
    view's. Signed, the views' size; and how much of each place has the
    side views' fine as well (0–1).

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
    none = np.zeros_like(now), np.zeros((ht, wd), np.float32)
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
    reach = _reach

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

    work = _line(work, now, (free * shown).astype(np.float32))

    # Nor is what is wider than they can tell it theirs: what the first
    # differs from a side view by is told from so far about
    # (:data:`ALONE_ABOUT`), and a wide soft light in the first view is
    # in that telling too.
    apart = cv2.GaussianBlur(now - work, (0, 0), fine)
    coarse = cv2.GaussianBlur(small(apart), (0, 0), MEND_COARSE * w)
    apart = apart - cv2.resize(coarse, (wd, ht), interpolation=cv2.INTER_LINEAR)
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
    pressed = reach(pressed.astype(np.float32), MEND_GROW, MEND_SOFT)
    # And along a sharp edge of what is taken off: his own figure dark in
    # the glass with the lit room about it, in focus (2026-11-18 17:39
    # UTC, shown his drawing scanned in one arc: "znowu pokazują się ostre
    # krawędzie w miejscach podmian"). What is taken off is softer than
    # such an edge, and the rest of it, a pixel or two wide, stayed as
    # the first view's fine: his outline pressed into the paper.
    taken = cv2.GaussianBlur((alone + soft).max(-1), (0, 0), 1.0)
    by = max(2, round(MEND_SHARP_ABOUT * wd))
    about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * by + 1, 2 * by + 1))
    sharp = (cv2.dilate(taken, about) - cv2.erode(taken, about)) / (base + MEND_DARK)
    sharp = np.clip((sharp - MEND_SHARP[0]) / (MEND_SHARP[1] - MEND_SHARP[0]), 0, 1) * shown
    sharp = cv2.GaussianBlur(cv2.dilate(sharp.astype(np.float32), about), (0, 0), by / 2)
    pressed = np.maximum(pressed, sharp)[..., None]
    stays = (detail @ weights)[..., None] * (1 - pressed)
    stays = stays + (work - cv2.GaussianBlur(work, (0, 0), fine)) * pressed
    mend = np.asarray((apart + detail - stays) * mask[..., None], np.float32)
    return mend, np.asarray(pressed[..., 0] * mask, np.float32)


def _reach(of: Floats, grow: float, soft: float) -> Floats:
    """``of`` (0–1) so far about (of the width) and over so much more by
    degrees: worked out the smaller the further it goes."""
    ht, wd = of.shape[:2]
    less = max(1, round(grow * wd) // 8)
    tiny = cv2.dilate(of, np.ones((less, less), np.uint8))
    tiny = cv2.resize(tiny, (wd // less, ht // less), interpolation=cv2.INTER_AREA)
    by = max(1, round(grow * wd / less))
    about = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * by + 1, 2 * by + 1))
    over = cv2.GaussianBlur(cv2.dilate(tiny, about), (0, 0), soft * wd / less)
    over = cv2.resize(over, (wd, ht), interpolation=cv2.INTER_LINEAR)
    return np.asarray(over * over * (3 - 2 * over), np.float32)


def _line(theirs: Floats, mine: Floats, free: Floats) -> Floats:
    """``theirs`` in the tones of ``mine``: by the line the two pictures
    keep to about each place, where it is ``free`` (0–1) to say
    (:data:`MEND_REACH`). Worked out small, it is even over a place and
    far about."""
    ht, wd = mine.shape[:2]
    w = max(64, wd // 4)
    h = max(64, round(ht * w / wd))

    def small(of: Floats) -> Floats:
        return cv2.resize(of, (w, h), interpolation=cv2.INTER_AREA)

    counts = small(free)[..., None]
    side, first = small(theirs), small(mine)
    squares, both = small(theirs * theirs), small(theirs * mine)
    slope = np.zeros_like(side)
    rest = np.zeros_like(side)
    left = np.ones((h, w, 1), np.float32)
    for last, wide in enumerate(MEND_REACH):
        sigma = wide * w

        def about_of(of: Floats, sigma: float = sigma) -> Floats:
            return cv2.GaussianBlur(of, (0, 0), sigma).reshape(h, w, -1)

        some = about_of(counts)
        by = np.maximum(some, 1e-6)
        middle, to = about_of(side * counts) / by, about_of(first * counts) / by
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
    return np.asarray(slope * theirs + rest, np.float32)


def _carried(of: Floats, sure: Floats) -> Floats:
    """``of`` where it is ``sure`` (0–1), and elsewhere what the sure
    places about have of it, the nearest first (:data:`MEND_REACH`)."""
    ht, wd = of.shape[:2]
    w = max(64, wd // 4)
    h = max(64, round(ht * w / wd))
    counts = cv2.resize(sure, (w, h), interpolation=cv2.INTER_AREA)[..., None]
    have = cv2.resize(of * sure[..., None], (w, h), interpolation=cv2.INTER_AREA)
    have = have.reshape(h, w, -1)
    far = np.zeros_like(have)
    left = np.ones((h, w, 1), np.float32)
    for last, wide in enumerate(MEND_REACH):
        some = cv2.GaussianBlur(counts, (0, 0), wide * w).reshape(h, w, 1)
        about = cv2.GaussianBlur(have, (0, 0), wide * w).reshape(h, w, -1)
        by = left if last == len(MEND_REACH) - 1 else left * np.clip(some / MEND_SURE, 0, 1)
        far = far + about / np.maximum(some, 1e-6) * by
        left = left - by
    far = cv2.resize(far, (wd, ht), interpolation=cv2.INTER_LINEAR).reshape(ht, wd, -1)
    sure = sure[..., None]
    return np.asarray(of * sure + far * (1 - sure), np.float32)


def _shown(views: list[_View]) -> tuple[Floats, Floats]:
    """The work as the side views show it, in their own light, and how
    sure that is (0–1): about each place mostly the darker of them (a
    reflection only adds light), and sure where each of them shows the
    work's tone (:func:`_counts`). Along the frame's side one was taken
    from only the other does, and that one may have the room in the
    glass there."""
    ht, wd = views[0].light.shape[:2]
    counts = _counts(views, ht, wd, tone=True)[1:]
    near = max(3, round(wd * GLARE_NEAR)) | 1
    lights = np.stack([cv2.GaussianBlur(v.light.sum(-1), (0, 0), near / 2) for v in views[1:]])
    least = np.where(counts > 0, lights, np.inf).min(0)
    least = np.where(np.isfinite(least), least, 0).astype(np.float32)
    weigh = np.exp(-(lights - least) / (0.1 * (np.abs(least) + 0.05))) * counts
    weigh = weigh.astype(np.float32)
    darker = np.zeros_like(views[0].light)
    for n, view in enumerate(views[1:]):
        darker += view.light * weigh[n][..., None]
    darker /= np.maximum(weigh.sum(0), 1e-6)[..., None]
    return darker, np.asarray(counts.min(0), np.float32)


def _veiled(now: Floats, soft: Floats, views: list[_View], sheen: Floats) -> tuple[Floats, Floats]:
    """What is still to come off ``now`` (the first view with its
    reflections taken off and mended) where the ``soft`` layer was a
    large share of the light the work is left with: its tone and colour
    there are the side views'. ``sheen`` is how much of what a place has
    over the darkest about it is a sheen on the work's grain
    (:func:`_grain`). Signed, the views' size; and how much of each
    place has the side views' fine as well (0–1).

    His Nikifor behind glass (2026-11-18 18:13 UTC, shown the scan with
    the side views' light put right: "Wtapianie na pokazanych przykładach
    - myślę że może być jeszcze lepiej. Teraz nadal widać odcięcie"; and
    18:19: "Problemem jest chyba tonacja i kolorystyka na łączeniu.
    Istotne jest wyrównanie nie tylko fragmentami, ale względem
    nakładanych, półprzejrzystych obszarów"). A lit doorway lay in the
    glass over the left of the sky, as much light again as the paint has
    there. Taken off, the sky under it was a pale pink beside the orange
    next to it, cut off where the doorway ended: the phone presses what
    it sees through such a veil flat, the even part of the layer stays
    on (:func:`_kept`), and in the band by the frame only the side view
    with the room all over it says anything. The view from the left has
    that sky as it is.

    So under such a veil, and a little way about it by degrees, what is
    wider than :data:`MEND_TINT` is the side views' picture
    (:func:`_shown`) in the first view's tones, as the places with no
    veil have the two (:func:`_line`); what is finer stays the first
    view's. Where the side views are not sure of the work (the strip
    along the frame), as much comes off as off the sure places next to
    it: the veil does not end there.

    Under a veil as light as the work itself (:data:`VEILED_HEAVY`) the
    first view has little of the picture left: the doorway's edge ran
    down through a tree, and the half of the tree under it stayed a
    ghost of the other half. There all that is wider than
    :data:`MEND_FINE` is the side views', and what they show finer than
    the views' size goes in with it (:func:`_finer`).

    This is for what glass mirrors. The sheen of an oil's varnish is a
    large share of its dark paint's light nearly everywhere, and held a
    veil it made his portraits the side views' pictures, a hand gone
    from pink to ochre (the same day, 16:11 UTC: "Na olejach nie jest
    źle"). A sheen lies on the paint's grain (:func:`_grain`), what
    glass mirrors does not: where the layer is mostly such a sheen it is
    no veil here, unless it is strong in itself (:data:`VEILED_STRONG`:
    his doorway on gouache, which has a grain too); and a work whose
    veiled places are such a sheen for the most part is paint under
    varnish, with no veil at all (:data:`VEILED_PAINT`)."""
    ht, wd = now.shape[:2]
    none = np.zeros_like(now), np.zeros((ht, wd), np.float32)
    if len(views) < 3:
        return none
    sides, sure = _shown(views)
    left = cv2.GaussianBlur(np.clip(now, 0, None).mean(-1), (0, 0), 2.0)
    share = cv2.GaussianBlur(soft.max(-1), (0, 0), 2.0) / (left + MEND_DARK)
    veiled = np.clip((share - VEILED[0]) / (VEILED[1] - VEILED[0]), 0, 1)
    if not veiled.any():
        return none
    paint = float(sheen.max(-1)[veiled > 0].mean())
    if paint >= VEILED_PAINT[1]:
        return none
    veiled *= 1 - max(0.0, (paint - VEILED_PAINT[0]) / (VEILED_PAINT[1] - VEILED_PAINT[0]))
    grain = cv2.GaussianBlur(sheen.max(-1), (0, 0), VEILED_SHEEN_ABOUT * wd)
    glass = 1 - np.clip((grain - VEILED_SHEEN[0]) / (VEILED_SHEEN[1] - VEILED_SHEEN[0]), 0, 1)
    strong = cv2.GaussianBlur(soft.max(-1), (0, 0), 2.0)
    strong = np.clip((strong - VEILED_STRONG[0]) / (VEILED_STRONG[1] - VEILED_STRONG[0]), 0, 1)
    veiled = (veiled * np.maximum(glass, strong)).astype(np.float32)
    if not veiled.any():
        return none
    over = _reach(veiled, VEILED_GROW, VEILED_SOFT)
    free = ((1 - over) ** 2 * sure).astype(np.float32)
    if float(free.mean()) < VEILED_FREE:
        # A veil over all of it: nothing says how the two pictures go together.
        return none
    theirs = _line(sides, now, free)
    tint = max(1.0, MEND_TINT * wd)
    have = cv2.GaussianBlur(sure, (0, 0), tint)
    apart = cv2.GaussianBlur((now - theirs) * sure[..., None], (0, 0), tint)
    # The darker side view is the picture as soon as it counts at all.
    known = np.clip(have * 4, 0, 1)
    apart = _carried(apart / np.maximum(have, 1e-3)[..., None], known)
    heavy = np.clip((share - VEILED_HEAVY[0]) / (VEILED_HEAVY[1] - VEILED_HEAVY[0]), 0, 1)
    heavy = np.minimum(heavy, veiled).astype(np.float32)
    if heavy.any():
        heavy = _reach(heavy, VEILED_HEAVY_GROW, VEILED_HEAVY_GROW) * known
        closer = cv2.GaussianBlur(now - theirs, (0, 0), max(1.0, MEND_FINE * wd))
        apart = apart + (closer - apart) * heavy[..., None]
    off = apart * over[..., None]
    # No more than most of what a place has, and of its three colours
    # alike: the frame's dark beside the work has no veil on it.
    most = np.clip(now, 0, None) * VEILED_MOST
    by = np.where(off > most, most / np.maximum(off, 1e-6), 1.0).min(-1, keepdims=True)
    return np.asarray(off * by, np.float32), np.asarray(heavy * over, np.float32)


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
    finer: Callable[[NDArray[np.float64], Floats], Floats] | None = None,
    theirs: Floats | None = None,
) -> Image:
    """``first`` less its reflection ``layer`` (:func:`_grain`, laid on it
    by ``to_photo``) and what is to ``mend`` after (:func:`_mend`, laid
    on it likewise) within ``quad``, at full size, a band of rows at a
    time; and where ``swap`` says so (the work under a glare and how much
    of a place is one, laid on it likewise) that work in the first's
    stead, with what the side photographs show ``finer`` than it
    (:func:`_finer`); that also where what was mended has their fine
    (``theirs``, laid on it likewise)."""
    veil, low, share = layer
    h, w = first.shape[:2]
    x0 = max(0, math.floor(quad[:, 0].min()) - 8)
    x1 = min(w, math.ceil(quad[:, 0].max()) + 8)
    y0 = max(0, math.floor(quad[:, 1].min()) - 8)
    y1 = min(h, math.ceil(quad[:, 1].max()) + 8)
    out = first.copy()
    mended = bool(mend.any())
    feather = max(1.5, 0.002 * max(x1 - x0, y1 - y0))

    def band(top: int) -> None:
        rows = min(ROWS, y1 - top)
        shift = np.array([[1, 0, -x0], [0, 1, -top], [0, 0, 1]], np.float64)

        def laid(what: Floats, how: int) -> Floats:
            return cv2.warpPerspective(
                what, shift @ to_photo, (x1 - x0, rows), flags=how, borderMode=cv2.BORDER_REPLICATE
            )

        inside = np.zeros((rows, x1 - x0), np.uint8)
        cv2.fillConvexPoly(inside, np.round(quad - [x0, top]).astype(np.int32), 255)
        soft = cv2.GaussianBlur(inside.astype(np.float32) / 255, (0, 0), feather)[..., None]
        light = _linear(first[top : top + rows, x0:x1])
        put_in: Floats | None = None
        if swap is not None:
            glare = laid(swap[1], cv2.INTER_LINEAR)
            if glare.any():
                put = laid(swap[0], cv2.INTER_CUBIC)
                if finer is not None:
                    put += finer(shift @ to_photo, glare)
                put -= light
                put *= glare[..., None]
                put *= soft
                light += put
                del put
                put_in = glare
        # Each of these in the place of the last: several bands are held
        # at a time, and a band's picture is 25 MB.
        sheen = laid(low, cv2.INTER_LINEAR)
        np.subtract(light, sheen, out=sheen)
        np.clip(sheen, 0, None, out=sheen)
        part = laid(share, cv2.INTER_LINEAR)
        np.clip(part, 0, 1, out=part)
        sheen *= part
        part = laid(veil, cv2.INTER_CUBIC)
        np.clip(part, 0, None, out=part)
        part += sheen
        part *= soft
        light -= part
        del sheen
        if mended:
            part = laid(mend, cv2.INTER_CUBIC)
            part *= soft
            light -= part
        del part
        if finer is not None and theirs is not None:
            also = laid(theirs, cv2.INTER_LINEAR)
            if put_in is not None:
                also = also * (1 - put_in)
            if also.any():
                more = finer(shift @ to_photo, also)
                more *= also[..., None]
                more *= soft
                light += more
                del more
        out[top : top + rows, x0:x1] = _srgb(light)

    # Each band is worked out by itself, so two at a time make the same
    # picture: this step was a quarter of the scan's time (Mateusz
    # 2026-11-18 23:34 UTC: "przyspieszyć składanie obrazów - teraz trwa
    # to zdecydowanie za długo […] Nie może odbyć się kosztem jakości").
    # Two and no more, and one after another on a machine with little
    # memory to spare: a band holds a quarter of a gigabyte the while.
    tops = range(y0, y1, ROWS)
    lanes = AT_A_TIME if spare() >= SPARE else 1

    def every(nth: int) -> None:
        for top in tops[nth::lanes]:
            band(top)

    for _ in bands.pool.map(every, range(lanes)):
        pass
    return out


def spare() -> float:
    """The memory this machine has to spare, in GB (much, where it does
    not say)."""
    try:
        with open("/proc/meminfo") as told:
            for line in told:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1e6
    except (OSError, ValueError, IndexError):
        pass
    return math.inf


__all__ = ["Merged", "grown", "merge", "spare"]
