"""The study sheet of an analysis of composition, drawn by an image model
(Google's, through the Interactions API): what is asked of it and in what
order. The pictures' own sums are in ``imaging.drawn``.

Mateusz 2026-11-12, after four rounds of trial sheets (19:44: "całość
łącznie z akwarela robi model graficzny"; 21:29: "wybieram opcję Model
rysuje sam, z opisu"; 22:14: "Jest świetnie. Wdrażamy."). Three questions
a sheet, each answered with a picture, about 0.15 USD together:

1. The work redrawn as a painter's study in watercolour and pen
   (:data:`UNDERLAY`): what the analysis says matters is drawn exactly and
   in fuller colour, the rest set down in broad pale washes; what is dark
   is one schematic wash, the wash carries no detail, a face is a few
   lines and hair a mass (his remarks of 20:54, 21:26 and 21:59).
2. The analysis's marks drawn over that study as a painting teacher
   would, from words alone (:data:`LINES`): every mark with a coloured
   pencil of its own, so that they can be taken apart again.
3. One wash and one pen line let out of the study to the side edges of
   the page (:data:`SPILL`; 21:59: "wyjścia szkicem i akwarelą w
   pojedynczych miejscach do krawędzi ekranu. subtelnie - jedną plamą,
   pojedynczą kreską"). Asked as a change to the finished study: asked for
   together with the study, the model painted a photograph of a sheet
   with a smaller study on it.

Each answer differs, so a sheet is made once and kept (``drawn``).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from ..imaging import drawn
from .client import AiUnavailable
from .daily import Mark, Spot, View
from .gemini import NotDrawn
from .sketch import _loop_box

log = logging.getLogger(__name__)

#: What the sheets are counted as in the month's spending.
KIND = "sheet"
#: A sheet is about this much (three answers), for what is told before.
TYPICAL_USD = 0.15
#: The works whose analysis the owner had made anew ("Wykonaj ponowną
#: analizę"): the new take's sheet is drawn at once (state).
AT_ONCE = "drawn_at_once"
UNDERLAY = """\
Redraw this painting as a painter's composition study in watercolour and pen on cream paper \
(#F5F1EA). A study has a hierarchy: it dwells on what the painting is about and only sets down \
the rest.

GEOMETRY (most important). Keep exactly the framing of the source image. Every figure, object \
and edge stays at exactly the same position and the same size as in the source, from edge to \
edge. Do not crop, zoom, shift, rotate or mirror. Do not add a margin, border, frame, mat or \
the edge of a sheet. The study fills the same rectangle as the painting.

WHAT MATTERS. An analysis of this painting names what matters in it (in Polish): {FOCUS}. \
These places are the focus of the study. Everything else is the setting.

THE FOCUS is finished. The pen draws its real contours precisely, with the few details that \
tell (a face's features and expression, hands, the things held, the structure of the main \
object). Economy even here. A face is its outline and the eyes, nose and mouth in a few sure \
lines, with one light shadow wash: no wrinkles, no hatching on cheeks or brow, no modelling \
line by line. Hair is a mass: its outline, a few long strokes for the way it falls, one wash \
and one darker; never curl by curl or strand by strand. Its washes are fuller and truer to the \
painting's colour, flat, with one darker second wash for its main shadow.

THE SETTING is never left empty and never detailed. Each big area of it (a sky, a sea, a wall, \
a floor, a background, a wide dress) gets one broad, diluted wash of its own colour and its \
own value, so that the painting's big pattern of light and dark reads from across a room: what \
is dark in the painting is a clearly darker wash, what is light is a pale wash or bare paper. \
Soft irregular edges; thin gaps of bare paper between some washes; the wash stops raggedly \
short of the sheet's edge here and there. Here the pen only indicates: a few long loose lines \
for the main edges and directions, nothing small, no texture.

PEN LINE. A fine ink line, dark grey-brown, clearly readable but delicate: a little stronger \
than a pencil line, never heavy, never a comic-book outline. Its pressure varies: firmer and \
darker on the focus and where a form turns, hair-thin in the setting. A little light diagonal \
hatching in the darkest shadow of the focus only.

DEPTH. The study is light and airy, yet it has depth: three clear steps of value. What is dark \
in the setting (a dark background, a storm cloud, a shadowed wall or floor) is one broad, \
schematic wash of a real middle-dark tone, brushed loosely, ragged at its edge, the paper \
breaking through it here and there. Middle areas are a pale wash. Lights are bare paper. Even \
the darkest wash stays transparent and is never black. The focus stands out from the setting \
by richer colour and by the pen, and the dark wash behind or beside it sets it off.

THE WASH CARRIES NO DETAIL. Watercolour here is only flat tone and colour. Inside any big \
shape (the front of a bed, a coat, a hull, a dress) the wash is one flat tone, at most two. No \
wood grain, no pattern, no texture, no small folds, no modelling of small forms, no cast \
shadows of small things, no streaks that imitate the painting's brushwork. Whatever detail is \
kept is drawn by the pen, and only in the focus. A face gets one light second wash for its \
shadow side, no more.

BARE PAPER. Only the lightest lights and the gaps: a tenth to a fifth of the sheet.

FIDELITY. Keep poses, expressions and proportions exactly. A face stays the same person: the \
same age, the same features, the same hair and its colour, the same direction of the gaze. Do \
not drop any figure or head, however small or half hidden; do not invent objects; do not \
beautify or modernise.

DO NOT ADD any text, signature, numbers, labels, arrows, construction lines, geometric \
diagrams, cast shadows, pencils or other props. The image is only the flat sheet, seen \
straight on.
"""

LINES = """\
This image is a finished composition study of a painting (watercolour and pen). A painting \
teacher now explains its composition by drawing over it with coloured pencils, one pencil for \
each finding. Draw the teacher's marks and return the study with them on it. The teacher only \
draws: nothing is written anywhere on the sheet.

THE STUDY STAYS AS IT IS. Same framing and size, edge to edge. Do not repaint, recolour, \
sharpen, clean or redraw any of it: every wash and every ink line stays exactly where and how \
it is. Bare paper stays bare. Only coloured pencil is added on top.

THE PENCILS. Waxy coloured pencils, a little grainy at the edge of the stroke, clearly thicker \
than the ink line, pressed firmly so that the colour stays pure and saturated over any wash, \
light or dark. Pressure varies within a stroke: heavier where it starts, lighter where it \
leaves the paper.

ONE PENCIL FOR ONE FINDING. Each finding below names its own pencil. Every stroke of that \
finding (its rings, arcs, arrowhead, echo strokes, ticks) is drawn with that pencil alone. No \
two findings share a colour. Colours are never mixed, shaded into one another or changed along \
a stroke; where two marks cross, each keeps its own colour. Use exactly the colours named.

WHAT THE TEACHER SHOWS. These are the findings of the analysis, one gesture for each, and \
nothing besides. Places are given in percent of the width from the left and of the height from \
the top, as a help to find the thing: draw each mark where the thing really is in the study. \
The names in quotation marks are for you alone, to know what each finding is about: they are \
never written on the sheet.
{MARKS}

THE ANALYSIS IN WORDS (to understand what the marks mean; in Polish): {TEXT}

HOW THE TEACHER DRAWS. This is not a diagram. It is live, loose, sketchy drawing done while \
talking, and every mark hugs the thing it is about.
- LOOP: to point at a thing the pencil runs round it, an envelope that follows its silhouette \
closely, open, the ends overlapping; never a neat ellipse or circle. It takes the outline of \
the thing itself: boxy with a curved top round the footboard of a bed, long and pointed round \
a boat, egg-shaped and leaning round a tilted head.
- TRIANGLE, BOX: a big shape is thrown in with long fast strokes that lie along the real edges \
it is made of (an arm, a mast, a hem, a bed rail), cross a little past the corners and fade \
out.
- LINE: one swift stroke along the form or edge it names; where it leads the eye somewhere it \
ends in an open arrowhead.
- MOTION: a sweeping curved arrow along the gesture of the body, the wave or the cloth, with \
an open arrowhead and two or three short strokes echoing it.
- ECHO: a small quick ring round each of the places that answer each other and a faint dotted \
arc from one ring to the next.
- RHYTHM: short repeated strokes, one on each repeated element.
- DIRECTION: one swift stroke from its start to its end, with an open arrowhead at the end.
- PERSPECTIVE: a few swift straight strokes along the real edges that run to the vanishing \
point, fanning out from it; they need not reach it.
- SPIRAL: one winding stroke that starts wide, turns through the things on its way and coils \
into its eye.
- UNDERLINE: one firm stroke under the thing, a little past both its ends.
Some strokes are gone over twice. Nothing is ruled, closed neatly or geometrically perfect. \
Keep it sparse and legible: only the gestures listed. Marks that concern neighbouring things \
run beside each other, never one on top of the other: leave a clear gap of paper between two \
different pencils wherever they do not have to cross.

NOTHING IS WRITTEN. No words, names, titles or captions beside the marks, no numbers, no \
letters, in any language. No legend, no colour key, no frame, no other additions. The sheet \
shows the study and the pencil strokes, nothing else.
"""

SPILL = """\
This image is a finished composition study of a painting (watercolour and pen) on a sheet of \
cream paper. The study lies in the middle; round it there is a margin of the same bare paper. \
Do one thing only: let the study leave its rectangle in two places, the way a painter's brush \
and pen sometimes run off a study. Return the same sheet with that added.

THE STUDY STAYS AS IT IS. Same framing and size: the study stays where it is and as large as \
it is, the margin stays as wide as it is. Do not repaint, recolour, sharpen, clean or redraw \
any of it: every wash and every ink line stays exactly where and how it is. Nothing is added \
inside the study.

THE SPILL, into the LEFT and RIGHT margins only.
- One wash. Choose one broad wash of the study that lies at its left or right edge (a \
background, a sky, a sea, a wall, a floor). Draw that one wash on outward with the same brush, \
in the same single colour and tone, across the margin to the very edge of the image: a loose \
tongue of paint, widest where it leaves the study, thinning and paling as it goes, ragged at \
its rim. It is ONE flat stain of ONE colour: nothing of the picture is repeated, mirrored or \
continued in it.
- One line. On the other side, choose one pen line that already runs to the study's edge (an \
arm, a mast, a horizon, a floorboard, a hem, the edge of a cloud). Carry it on in a single \
stroke of the same pen across the margin to the edge of the image, getting thinner.
That is all: one wash and one line. Subtle. The rest of the left and right margins, and all of \
the top and bottom margins, stay bare, clean paper. Nothing is depicted in the margin: no \
objects, no figures, no continuation of the scene.

The image is only the flat sheet, edge to edge, seen straight on: not a photograph of a sheet, \
no shadow, no table, no frame, no border line round the study. No text, no signature.
"""

#: The marks that say what the picture is about (the study's focus).
FOCUS_SHAPES = ("loop", "triangle", "rect", "motion")

#: What paints: the question's words and its pictures in, a picture and
#: what it cost out.
Paint = Callable[[str, Sequence[Image.Image]], tuple[Image.Image, float]]


# -- what is asked ----------------------------------------------------------------------


def focus(view: View) -> str:
    """What the analysis says matters, as the study's focus: the titles of
    the marks that point at a thing and of the places it rests on most."""
    marks = [m.title for m in view.marks if m.shape in FOCUS_SHAPES and m.title]
    main = [k.title for k in view.keys if k.main and k.title]
    return "; ".join(f"„{t}”" for t in dict.fromkeys(marks + main))


def _pc(spot: Spot) -> str:
    return f"({round(spot.x * 100)}, {round(spot.y * 100)})"


def said(mark: Mark) -> str:
    """A mark in words: what it is and about where it lies (per cent of the
    width and of the height), as a help to find the thing."""
    pts = mark.points
    if mark.shape == "loop":
        x0, y0, x1, y1 = _loop_box(mark, (100, 100))
        return (
            f"LOOP round what lies between {round(x0)} and {round(x1)} across, "
            f"{round(y0)} and {round(y1)} down"
        )
    if mark.shape == "triangle":
        return "TRIANGLE with its corners at " + ", ".join(_pc(p) for p in pts)
    if mark.shape == "rect":
        return f"BOX from {_pc(pts[0])} to {_pc(pts[-1])}"
    if mark.shape == "rhythm":
        across = ", ".join(f"{round(p.x * 100)} across" for p in pts[::2])
        return f"RHYTHM: a tick on each of the repeated elements standing at {across}"
    if mark.shape == "echo":
        return "ECHO between the places at " + ", ".join(_pc(p) for p in pts)
    if mark.shape == "motion" and len(pts) > 2:
        through = ", ".join(_pc(p) for p in pts[1:-1])
        return f"MOTION that starts at {_pc(pts[0])}, passes {through} and ends at {_pc(pts[-1])}"
    if mark.shape in ("motion", "arrow"):
        return f"DIRECTION from {_pc(pts[0])} to {_pc(pts[-1])}"
    if mark.shape == "rays":
        ends = ", ".join(_pc(p) for p in pts[1:])
        return f"PERSPECTIVE: edges running to the vanishing point at {_pc(pts[0])} from {ends}"
    if mark.shape == "spiral":
        return (
            f"SPIRAL that starts at {_pc(pts[0])}, turns through {_pc(pts[1])} "
            f"and winds into its eye at {_pc(pts[-1])}"
        )
    if mark.shape == "underline":
        return f"UNDERLINE from {_pc(pts[0])} to {_pc(pts[-1])}"
    return "LINE through " + ", ".join(_pc(p) for p in pts)


def lines_prompt(marks: Sequence[Mark], pencils: Sequence[tuple[str, str]], text: str) -> str:
    rows = [
        f"{n}. {word} pencil ({colour}). „{m.title}” ({m.text.rstrip('.')}): {said(m)}."
        for n, (m, (word, colour)) in enumerate(zip(marks, pencils, strict=False), start=1)
    ]
    return LINES.replace("{MARKS}", "\n".join(rows)).replace("{TEXT}", text)


def _course(mark: Mark) -> tuple[list[tuple[float, float]], bool]:
    """Where a mark runs (fractions of the field) and whether it closes."""
    pts = [(p.x, p.y) for p in mark.points]
    if mark.shape == "loop":
        x0, y0, x1, y1 = (v / 100 for v in _loop_box(mark, (100, 100)))
        turn = np.linspace(0, 2 * math.pi, 24)
        ring = [
            (
                (x0 + x1) / 2 + (x1 - x0) / 2 * math.cos(a),
                (y0 + y1) / 2 + (y1 - y0) / 2 * math.sin(a),
            )
            for a in turn
        ]
        return ring, False
    if mark.shape == "rect":
        (ax, ay), (bx, by) = pts[0], pts[-1]
        return [(ax, ay), (bx, ay), (bx, by), (ax, by)], True
    return pts, mark.shape == "triangle"


# -- a sheet ------------------------------------------------------------------------------


@dataclass
class Sheet:
    """A drawn sheet as it is kept: the page (the field with its side
    margins) as a JPEG, a layer per titled mark of the take (PNG; None
    where the model left the mark out), each mark's colour and where its
    number stands (fractions of the field), the field's size in pixels and
    what the answers cost."""

    page: bytes
    layers: list[bytes | None]
    colours: list[str]
    numbers: list[list[tuple[float, float]]]
    size: tuple[int, int]
    cost: dict[str, float] = field(default_factory=dict)


def titled(view: View) -> list[Mark]:
    """The take's marks the model draws: those with a name, as many as
    there are pencils."""
    return [m for m in view.marks if m.title][: len(drawn.PENCILS)]


def study_prompt(view: View) -> str:
    return UNDERLAY.replace("{FOCUS}", focus(view) or "—")


def lines_ask(study: Image.Image, view: View) -> tuple[str, list[str]] | None:
    """What is asked for the take's marks over its ``study``, and the
    pencils' colours in the marks' order; None when it has none to draw."""
    marks = titled(view)
    if not marks:
        return None
    pencils = drawn.pencils([_course(m) for m in marks], study)
    return lines_prompt(marks, pencils, view.text), [colour for _, colour in pencils]


def _there(layers: Sequence[Any]) -> int:
    return sum(float((layer > 0.3).mean()) >= drawn.NO_MARK for layer in layers)


def _study(
    picture: Image.Image, view: View, paint: Paint, costs: dict[str, float]
) -> tuple[Image.Image, Any]:
    """The work as a study, and where it lies on the work. An answer that
    is not the work's (another framing altogether) is asked for once more."""
    prompt = study_prompt(view)
    off = math.inf
    for _ in range(2):
        study, usd = paint(prompt, [picture])
        costs["underlay"] = costs.get("underlay", 0.0) + usd
        frac, off = drawn.measure(picture, study)
        if off <= drawn.FAR_OFF:
            return study, frac
    raise NotDrawn(f"the study lies {off:.1f}% off the work")


def _marks(
    study: Image.Image, view: View, paint: Paint, costs: dict[str, float]
) -> Image.Image | None:
    """The study with the take's marks as the model drew them over it.
    Asked once more when a mark is left out; the answer with more of the
    marks is kept."""
    ask = lines_ask(study, view)
    if ask is None:
        return None
    prompt, colours = ask
    best: tuple[int, Image.Image] | None = None
    for _ in range(2):
        marked, usd = paint(prompt, [study])
        costs["lines"] = costs.get("lines", 0.0) + usd
        layers, _ = drawn.split(study, marked, colours)
        if best is None or _there(layers) > best[0]:
            best = (_there(layers), marked)
        if best[0] == len(layers):
            break
    return best[1] if best is not None else None


def put_together(
    work: Image.Image,
    view: View,
    study: Image.Image,
    marked: Image.Image | None,
    spilt: Image.Image | None,
    costs: dict[str, float],
    seed: int = 1,
) -> Sheet:
    """The sheet out of the model's three answers: ``work`` as it was sent
    (:func:`imaging.drawn.sent`), its ``study``, the study with the take's
    marks (``marked``; None when the take has none) and with what runs out
    of it (``spilt``; None: the sheet goes without). Raises
    :class:`NotDrawn` when the study is not the work's."""
    size = drawn.field_size(work)
    frac, off = drawn.measure(work, study)
    if off > drawn.FAR_OFF:
        raise NotDrawn(f"the study lies {off:.1f}% off the work")
    field_ = drawn.on_page(np.asarray(drawn.laid(study, frac, size), np.float32) / 255)
    marks = titled(view)
    layers: list[Any] = []
    colours: list[str] = []
    numbers: list[list[tuple[float, float]]] = []
    ask = lines_ask(study, view) if marked is not None else None
    if ask is not None and marked is not None:
        raw, colours = drawn.split(study, marked, ask[1])
        for n, layer in enumerate(raw):
            as_image = Image.fromarray((np.clip(layer, 0, 1) * 255).astype(np.uint8))
            on = np.asarray(drawn.laid(as_image, frac, size), np.float32) / 255
            layers.append(drawn.softened(on, seed + n))
        placed = [
            drawn.Placed(
                m.shape,
                [(p.x * size[0], p.y * size[1]) for p in m.points],
                _loop_box(m, size) if m.shape == "loop" else None,
            )
            for m in marks
        ]
        numbers = [
            [(x / size[0], y / size[1]) for x, y in found]
            for found in drawn.spots(placed, layers, field_)
        ]
    spill = None
    if spilt is not None:
        try:
            spill = drawn.spilt(study, spilt, frac, size)
        except Exception as err:  # the sheet is paid for: it goes without its spill
            log.warning("the sheet's spill left out: %s", err)
    return Sheet(
        page=drawn.jpeg(drawn.page(field_, spill, seed)),
        layers=[drawn.png(layer) if _there([layer]) else None for layer in layers],
        colours=colours,
        numbers=numbers,
        size=size,
        cost={k: round(v, 4) for k, v in costs.items()},
    )


def draw(picture: Image.Image, view: View, paint: Paint, seed: int = 1) -> Sheet:
    """The sheet of a take, asked for now: ``picture`` is the work (its
    field alone, when the take has one) and ``view`` the take as its field
    sees it (``View.inside``). Raises :class:`NotDrawn` when the model's
    study is not the work's; a spill that cannot be had is left out."""
    work = drawn.sent(picture)
    costs: dict[str, float] = {}
    study, _ = _study(work, view, paint, costs)
    marked = _marks(study, view, paint, costs)
    spilt = None
    try:
        spilt, costs["spill"] = paint(SPILL, [drawn.padded(study)[0]])
    except AiUnavailable:
        raise
    except Exception as err:  # the sheet is paid for: it goes without its spill
        log.warning("the sheet's spill left out: %s", err)
    return put_together(work, view, study, marked, spilt, costs, seed)
