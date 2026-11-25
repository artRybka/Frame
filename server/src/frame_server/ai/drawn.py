"""The study sheet of an analysis of composition: its study drawn by an
image model (Google's, through the Interactions API), its marks drawn here
in chalk (``imaging.chalk``). What is asked of the model and in what order;
the pictures' own sums are in ``imaging.drawn``.

Mateusz 2026-11-12, after four rounds of trial sheets (19:44: "całość
łącznie z akwarela robi model graficzny"; 22:14: "Jest świetnie.
Wdrażamy."). Two questions a sheet, each answered with a picture, about
0.08 USD together:

1. The work redrawn as a painter's study in watercolour and pen
   (:data:`UNDERLAY`): what the analysis says matters is drawn exactly and
   in fuller colour, the rest set down in broad pale washes; what is dark
   is one schematic wash, the wash carries no detail, a face is a few
   lines and hair a mass (his remarks of 20:54, 21:26 and 21:59).
2. One wash and one pen line let out of the study to the side edges of
   the page (:data:`SPILL`; 21:59: "wyjścia szkicem i akwarelą w
   pojedynczych miejscach do krawędzi ekranu. subtelnie - jedną plamą,
   pojedynczą kreską"). Asked as a change to the finished study: asked for
   together with the study, the model painted a photograph of a sheet
   with a smaller study on it.

The analysis's marks were drawn over the study by the model too, from
words, a coloured pencil each, and taken apart again (``drawn.split``).
Since 2026-11-22 they are drawn here, in chalk, each straight into a layer
of its own (Mateusz 22:10, after five rounds of trial sheets: "Jest super.
Działamy."): every mark where it lies, nothing written, the study under
them untouched, and nothing paid.

Each answer differs, so a sheet is made once and kept (``drawn``).

Cheaper since the trial of 2026-11-13 (Mateusz 07:11: "zastanów się jak
obniżyć koszt"): the study is asked of a model that does not think first
(:data:`THINK`; the same look, and a third faster), the spill of Google's
cheapest model (``gemini.LITE``), which lets a wash run out as well as the
dearer one.
"""

from __future__ import annotations

import base64
import io
import logging
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from ..imaging import chalk, drawn
from .client import HAIKU, AiUnavailable, request
from .daily import Mark, View
from .gemini import NotDrawn, blocked
from .sketch import _loop_box

log = logging.getLogger(__name__)

#: What the sheets are counted as in the month's spending.
KIND = "sheet"
#: A sheet is about this much (two answers: its study and what runs out of
#: it; its marks are drawn here), for what is told before.
TYPICAL_USD = 0.08
#: How much the model thinks before it draws the study.
THINK = "minimal"
#: A study Google will not take at all (a nude, now and then) is asked for
#: up to this many times: a refusal costs nothing (Mateusz 2026-11-13 08:26:
#: "Akty - ograniczmy się do powielania prób (do 8 razy)"; black bars over
#: the nude let one more work through in the trial, he chose not to).
BLOCKED_TRIES = 8
#: The works whose analysis the owner had made anew ("Wykonaj ponowną
#: analizę"): the new take's sheet is drawn at once (state).
AT_ONCE = "drawn_at_once"
#: The study. Mateusz 2026-11-13: its MANNER (08:27: "u Matissa przeszkadza
#: bardzo dokładny szkic modelki. Kompletnie gubi charakter obrazu"), its
#: COLOUR (:data:`COLOUR`) and darks as deep as painted (08:30: "podkłady są
#: chwilami zbyt mdłe, szczególnie przy dziełach ciemnych i wymagających
#: pokazania czerni czy ciemnej plamy"). And LESS than the painting, never
#: more (2026-11-14 20:33, on Matisse's „Radość życia”: "rysuje zbyt
#: dokładnie (zmyśla) ważne żeby rysował raczej mniej niż na dziele a nie
#: więcej. Lepiej. Ogólniej i schematyczniej niż za dużo"): the studies
#: drawn before are looked at by :data:`JUDGE` and the busy ones drawn anew
#: (``drawn.DrawnSheets``, :data:`PLAIN`).
UNDERLAY = """\
Redraw this painting as a painter's composition study in watercolour and pen on cream paper \
(#F5F1EA). A study is a summary: it says less than the painting, never more. It dwells on what \
the painting is about and only sets down the rest.

GEOMETRY (most important). Keep exactly the framing of the source image. Every figure, object \
and edge stays at exactly the same position and the same size as in the source, from edge to \
edge. Do not crop, zoom, shift, rotate or mirror. Do not add a margin, border, frame, mat or the \
edge of a sheet. The study fills the same rectangle as the painting.

LESS THAN THE PAINTING (the rule over all the others). The study always holds fewer lines, \
fewer details and fewer things than the painting, everywhere, the focus included. When in doubt, \
leave it out: a shape the painter only suggested stays a suggestion or a patch of wash; a detail \
too small or too vague to be sure of is not drawn. Never add anything the painting does not \
plainly show: no features, fingers, folds, leaves, waves, ornaments, animals, props or figures \
that are not clearly painted there, and never more of them than are painted. Never sharpen, \
complete or explain what the painter left open. Use about half the lines a careful copy would \
need. A schematic, general study is right; a busy, over-exact one is wrong.

WHAT MATTERS. An analysis of this painting names what matters in it (in Polish): {FOCUS}. These \
places are the focus of the study. Everything else is the setting.

THE FOCUS is the most finished part, and still a summary. The pen draws its main contours, the \
big shapes and the one or two details that tell (the tilt of a head, the line of an arm, the \
thing held), as simply as the painter drew them or more simply. A face is its outline and, only \
where the painter clearly painted them, the eyes, nose and mouth as a few short marks, with at \
most one light shadow wash: no wrinkles, no lashes, no lips drawn in full, no hatching on cheeks \
or brow, no modelling. Hair is one mass: its outline and one wash, never curls or strands. Hands \
are mittens of a few lines; no fingernails or knuckles. Its washes are fuller and truer to the \
painting's colour, flat, with at most one darker second wash for its main shadow.

THE SETTING is never left empty and never detailed. Each big area of it (a sky, a sea, a wall, a \
floor, a background, a wide dress, a stand of trees) gets one broad wash of its own colour and \
its own value, so that the painting's big pattern of light and dark reads from across a room: \
what is dark in the painting is a clearly darker wash, what is light is a pale wash or bare \
paper. Soft irregular edges; thin gaps of bare paper between some washes; the wash stops raggedly \
short of the sheet's edge here and there. Here the pen only indicates: a few long loose lines for \
the main edges and directions, nothing small, no texture. Figures and things in the setting are \
flat silhouettes: a patch of wash with at most a broken outline of a few strokes; no faces, no \
hands, no inner lines, no anatomy.

PEN LINE. A fine ink line, dark grey-brown, clearly readable but delicate: a little stronger \
than a pencil line, never heavy (unless the painter's own contour is, see MANNER), never a \
comic-book outline. Few lines: each one is needed. Its pressure varies: firmer and darker on the \
focus and where a form turns, hair-thin in the setting. No hatching anywhere: shadow is wash.

DEPTH. The study is airy, yet it has depth and the painting's own range of value, from bare \
paper to the painting's darkest dark. What is dark in the painting (a dark background, a black \
coat or dress, a storm cloud, a night sky, a shadowed wall or floor) is one broad, schematic \
wash as deep as it is in the painting: a dark painting gets a dark study, and what is black in \
the painting is a strong, deep, ink-dark wash, warm or cool as painted. It is brushed loosely, \
ragged at its edge, the paper breaking through it here and there. Middle areas are a middle or \
pale wash. Lights are bare paper. The focus stands out from the setting by richer colour and by \
the pen, and the dark wash behind or beside it sets it off.

THE WASH CARRIES NO DETAIL. Watercolour here is only flat tone and colour. Inside any big shape \
(the front of a bed, a coat, a hull, a dress, a body, a mass of foliage) the wash is one flat \
tone, at most two. No wood grain, no pattern, no texture, no leaves, no small folds, no modelling \
of small forms, no cast shadows of small things, no streaks that imitate the painting's \
brushwork. Whatever detail is kept is drawn by the pen, and only in the focus.

MANNER. This is a study of this particular painting, so it keeps the painter's own way of \
drawing and painting, simplified further, never refined. Where the painter simplified, flattened \
or distorted forms (bold dark outlines, flat areas of colour, a mask-like face, heavy or \
elongated limbs, tilted perspective), the study keeps exactly that: the same contours, the same \
simplified features, the same proportions, even where they are not anatomically or optically \
correct. Never correct the anatomy, never make a face, a body or a space more realistic, more \
academic, more detailed or prettier than the painter did. Where the painter outlined figures \
with a heavy dark contour (as Matisse or Gauguin did), the pen follows it with the same bold \
contour and nothing inside it; a painting modelled in light and shade has no such outline, and \
its study keeps the fine pen line. A figure the painter flattened into a simple shape stays a \
simple shape: its outline in a few long lines, no anatomy, no modelling of the body, the face \
blank or as summary as the painter's (a few strokes, not a portrait). A loose painting gets an \
even looser study; a precise one a clear but still simplified study.
{COLOUR}
BARE PAPER. Only the lightest lights and the gaps: a tenth to a fifth of the sheet.

FIDELITY. What is drawn stays true: poses, directions of gaze and proportions as painted, a \
face the same age and kind of person, hair its own colour. Every figure keeps its place, at \
least as a patch of wash or a few strokes, however small; nothing is invented, moved, \
beautified or modernised.

DO NOT ADD any text, signature, numbers, labels, arrows, construction lines, geometric diagrams, \
cast shadows, pencils or other props. The image is only the flat sheet, seen straight on.
"""

#: The study of a work of one colour, a print or a drawing (Mateusz
#: 2026-11-22 14:22: "dla grafik i rysunków monochromatycznych nie dajemy
#: akwareli"; 14:26, of three ways: "Kreska w kolorze odbitki"): drawn in
#: line alone, in the work's own ink on its own paper, its tones by
#: hatching as a print makes them; no wash, no colour. Which works:
#: :func:`lined`.
UNDERLAY_LINE = """\
Redraw this work (a print or a drawing in one colour) as an artist's composition study in line \
alone: pen or pencil in the work's own ink, on paper of the work's own tone. A study is a \
summary: it says less than the work, never more. It dwells on what the work is about and only \
sets down the rest.

GEOMETRY (most important). Keep exactly the framing of the source image. Every figure, object \
and edge stays at exactly the same position and the same size as in the source, from edge to \
edge. Do not crop, zoom, shift, rotate or mirror. Do not add a margin, border, frame, mat or the \
edge of a sheet. The study fills the same rectangle as the work.

LINE ALONE, ONE COLOUR. The whole study is drawn with one point in one colour: the colour of the \
work's own ink or chalk (black, grey, brown, sepia, red chalk, blue, as it is). The paper is the \
work's own paper tone, plain and even, with no stains. No watercolour, no wash, no tint, no \
second colour, no smudged or rubbed tone: every tone is made of lines.

LESS THAN THE WORK (the rule over all the others). The study always holds fewer lines, fewer \
details and fewer things than the work, everywhere, the focus included. When in doubt, leave it \
out. Never add anything the work does not plainly show: no features, folds, leaves, ornaments, \
animals, props or figures that are not clearly there, and never more of them than there are. \
Never sharpen, complete or explain what the artist left open. A schematic, general study is \
right; a busy, over-exact one is wrong.

WHAT MATTERS. An analysis of this work names what matters in it (in Polish): {FOCUS}. These \
places are the focus of the study. Everything else is the setting.

THE FOCUS is the most finished part, and still a summary: its main contours, the big shapes and \
the one or two details that tell, as simply as the artist drew them or more simply. A face is \
its outline and, only where the artist clearly drew them, the eyes, nose and mouth as a few \
short marks. Hair is one mass: its outline and a few strokes of its direction. Hands are a few \
lines.

TONE BY HATCHING. The work's big pattern of light and dark stays and reads from across a room, \
made the way a print or a drawing makes it: parallel hatching for a middle tone, crossed \
hatching for a dark, dense crossed hatching for the darkest, so dense in the deepest darks of \
a dark work that it nearly closes. The hatching is simpler, looser and more open than the \
work's own: long even strokes laid in one or two directions over a whole area, following the \
direction of its form, never the work's every engraved line. Lights are bare paper. What is \
dark in the work is just as dark in the study: keep the work's own balance of light and dark. A \
dark work (a night, a mezzotint, a charcoal drawing of deep shadow) gets a dark study, most of \
it dense crossed hatching closing almost to solid, with the paper showing only in its lights.

THE SETTING is never left empty and never detailed: each big area of it (a sky, a ground, a \
wall, a background) gets its tone as one broad field of even hatching, with at most a few long \
loose lines for its main edges and directions. Figures and things in the setting are \
silhouettes: an outline of a few strokes filled with the hatching of their tone; no faces, no \
hands, no inner lines.

MANNER. This is a study of this particular work, so it keeps the artist's own way of drawing, \
simplified further, never refined: the same contours, proportions and distortions, the same \
character of line (an etcher's free line, an engraver's swelling line, a chalk's soft grain, a \
pen's sharp line). Never make a face, a body or a space more realistic or prettier than the \
artist did.

BARE PAPER. Only the lights and the gaps between hatched fields.

FIDELITY. What is drawn stays true: poses, directions of gaze and proportions as they are; \
every figure keeps its place, at least as a silhouette, however small; nothing is invented, \
moved, beautified or modernised.

DO NOT ADD any text, signature, numbers, labels, plate marks, arrows, construction lines, \
geometric diagrams, pencils or other props. The image is only the flat sheet, seen straight on.
"""

#: What runs out of a line study: two lines, never a wash.
SPILL_LINE = """\
This image is a finished composition study of a print or drawing (line alone, in one colour) \
on a sheet of paper. The study lies in the middle; round it there is a margin of the same bare \
paper. Do one thing only: let the study leave its rectangle in two places, the way an artist's \
pen sometimes runs off a study. Return the same sheet with that added.

THE STUDY STAYS AS IT IS. Same framing and size: the study stays where it is and as large as \
it is, the margin stays as wide as it is. Do not redraw, darken, sharpen or clean any of it: \
every line stays exactly where and how it is. Nothing is added inside the study.

THE SPILL, into the LEFT and RIGHT margins only, one on each side. On each side choose one line \
of the study that already runs to its edge (a horizon, a contour, an arm, the edge of a hatched \
field) and carry it on in a single stroke of the same pen and colour across the margin to the \
edge of the image, getting thinner. Or, on one side instead, let a few strokes of a hatched \
field run a little way out, loose and thinning. No wash, no colour, no tint. Subtle. The rest of \
the margins stays bare, clean paper. Nothing is depicted in the margin.
"""

#: Which line study the kept ones of the works of one colour were drawn
#: with: one drawn before (in watercolour) is drawn anew, its lines kept
#: (``drawn.DrawnSheets``). 1: line alone, 2026-11-22.
LINE = 1


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

#: Which prompt of the study the kept ones were drawn with: a study kept
#: from before this one is looked at by the judge once and, when it says
#: more than its painting, drawn anew with its lines kept
#: (``drawn.DrawnSheets``). 1: "less than the painting" of 2026-11-14.
PLAIN = 1
#: Who judges a kept study against its painting, and how large both are
#: sent (a face's features must be told apart).
JUDGE_MODEL = HAIKU
JUDGE_SIDE = 1024
JUDGE = """\
You compare a painting (first image) with a watercolour-and-pen composition study of it \
(second image). A good study is a summary: it says LESS than the painting, never more. It is \
schematic and general: broad flat washes, few pen lines, the main contours of what matters, \
small figures as silhouettes.

The study says MORE than the painting (redraw: true) when, anywhere on it, it:
- draws things the painting does not plainly show: invented facial features, fingers, folds, \
leaves, waves, ornaments, animals, objects or figures;
- is more detailed, more finished or more realistic than the painting: full faces with lashes, \
lips and modelling where the painter painted a summary face or a mask; hair curl by curl; \
anatomy, muscles or modelling on a figure the painter flattened; textured foliage, wood grain, \
patterns or many small strokes the painting does not have;
- covers the background with busy pen work instead of a few loose lines.

It is fine (redraw: false) when it is as simple as the painting or simpler, even if crude, \
incomplete or loose; a missing detail is never a fault. Small differences of colour or \
placement do not matter. Judge only by how much is drawn.

List in "more" (English, a few words each, at most four) what the study draws beyond the \
painting; empty when nothing."""
JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["more", "redraw"],
    "properties": {
        "more": {"type": "array", "items": {"type": "string"}},
        "redraw": {"type": "boolean"},
    },
}


def _picture(img: Image.Image) -> dict[str, Any]:
    small = img.convert("RGB")
    small.thumbnail((JUDGE_SIDE, JUDGE_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    small.save(out, "JPEG", quality=85)
    data = base64.standard_b64encode(out.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def judge_request(work: Image.Image, study: Image.Image) -> dict[str, Any]:
    """The question whether a kept ``study`` says more than its ``work``
    (Messages API parameters, :data:`JUDGE_SCHEMA` the answer's shape)."""
    content = [
        {"type": "text", "text": "The painting:"},
        _picture(work),
        {"type": "text", "text": "The study:"},
        _picture(study),
    ]
    return request(
        model=JUDGE_MODEL, system=JUDGE, content=content, schema=JUDGE_SCHEMA, max_tokens=1500
    )


#: What the analysis says of the painting's colour, given to the study
#: (Mateusz 2026-11-13 08:29: "w miejscach akcentu czy tam gdzie kolor jest
#: wymieniany do analizy podkreślić go na szkicu").
COLOUR = """
COLOUR. What the analysis says about the painting's colour (in Polish): {SAID}. Where it \
names an accent of colour, or a colour that returns in several places, that colour is a little \
stronger on the study than the washes round it: a clear, true wash of that hue, in exactly \
those places, so that the accent and its returns are seen at once. Only there; everything else \
keeps the washes described above.
"""
#: A sentence of the analysis that speaks of colour (Polish stems).
_COLOURED = re.compile(
    r"akcent|kolor|barw|czerw|żół|żółt|błęk|niebiesk|ziele|ochr|biel|róż|pomarańcz|fiolet|"
    r"złot|ugr|rdzaw|brąz|granat|purpur|karmin|cynob|szmaragd|turkus|seledyn",
    re.IGNORECASE,
)
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


def colour(view: View) -> str:
    """What the analysis says of colour: its sentences that name one, and
    the marks that follow a colour returning ("echo")."""
    sentences = [t for t in re.split(r"(?<=[.!?])\s+", view.text) if _COLOURED.search(t)]
    echoes = [
        f"{m.title}: {m.text}" if m.text else m.title
        for m in view.marks
        if m.shape == "echo" and m.title and _COLOURED.search(f"{m.title} {m.text}")
    ]
    return " ".join(f"„{t.strip()}”" for t in dict.fromkeys(sentences + echoes))


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
class Under:
    """What lies under a work's lines, as the model answered: its study,
    and the study with what runs out of it (None: it goes without). Kept
    for the work, so that another take of it (an analysis made anew) has
    only its lines drawn over the same study."""

    study: Image.Image
    spilt: Image.Image | None = None


@dataclass
class Sheet:
    """A drawn sheet as it is kept: the page (the field with its side
    margins) as a JPEG, a layer per titled mark of the take (PNG; None
    where the model left the mark out), each mark's colour and where its
    number stands (fractions of the field), the field's size in pixels,
    what the answers cost and what it was drawn over."""

    page: bytes
    layers: list[bytes | None]
    colours: list[str]
    numbers: list[list[tuple[float, float]]]
    size: tuple[int, int]
    cost: dict[str, float] = field(default_factory=dict)
    under: Under | None = None


def titled(view: View) -> list[Mark]:
    """The take's marks the model draws: those with a name, as many as
    there are pencils."""
    return [m for m in view.marks if m.title][: len(drawn.PENCILS)]


def lined(tags: Sequence[str]) -> bool:
    """Whether a work with these colour tags (``Item.color_tags``) gets a
    study in line alone (:data:`UNDERLAY_LINE`): a print or a drawing of
    one colour."""
    return "monochrome" in tags


def study_prompt(view: View, line: bool = False) -> str:
    if line:
        return UNDERLAY_LINE.replace("{FOCUS}", focus(view) or "—")
    said = colour(view)
    return UNDERLAY.replace("{FOCUS}", focus(view) or "—").replace(
        "{COLOUR}", COLOUR.replace("{SAID}", said) if said else ""
    )


def spill_prompt(line: bool = False) -> str:
    """What is asked for what runs out of a study (of a line study: lines)."""
    return SPILL_LINE if line else SPILL


def _asked(paint: Paint, prompt: str, picture: Image.Image) -> tuple[Image.Image, float]:
    """The study (or its lines) as asked, asked again while Google will not
    take the question (:data:`BLOCKED_TRIES` at most; refused, it costs
    nothing)."""
    for attempt in range(BLOCKED_TRIES):
        try:
            return paint(prompt, [picture])
        except NotDrawn as err:
            if not blocked(err.code) or attempt == BLOCKED_TRIES - 1:
                raise
    raise AssertionError("unreachable")


def _study(
    picture: Image.Image, view: View, paint: Paint, costs: dict[str, float], line: bool = False
) -> tuple[Image.Image, Any]:
    """The work as a study, and where it lies on the work. An answer that
    is not the work's (another framing altogether) is asked for once more."""
    prompt = study_prompt(view, line)
    off = math.inf
    for _ in range(2):
        study, usd = _asked(paint, prompt, picture)
        costs["underlay"] = costs.get("underlay", 0.0) + usd
        frac, off = drawn.measure(picture, study)
        if off <= drawn.FAR_OFF:
            return study, frac
    raise NotDrawn(f"the study lies {off:.1f}% off the work")


def _field(work: Image.Image, study: Image.Image) -> tuple[tuple[int, int], Any, Any]:
    """The field's size, where the study lies on the work and the study laid
    on the page as the field. Raises :class:`NotDrawn` when the study is
    not the work's."""
    size = drawn.field_size(work)
    frac, off = drawn.measure(work, study)
    if off > drawn.FAR_OFF:
        raise NotDrawn(f"the study lies {off:.1f}% off the work")
    return size, frac, drawn.on_page(np.asarray(drawn.laid(study, frac, size), np.float32) / 255)


def _page(
    study: Image.Image,
    spilt: Image.Image | None,
    frac: Any,
    size: tuple[int, int],
    field_: Any,
    seed: int,
) -> bytes:
    spill = None
    if spilt is not None:
        try:
            spill = drawn.spilt(study, spilt, frac, size)
        except Exception as err:  # the sheet is paid for: it goes without its spill
            log.warning("the sheet's spill left out: %s", err)
    return drawn.jpeg(drawn.page(field_, spill, seed))


def repaged(
    work: Image.Image, study: Image.Image, spilt: Image.Image | None, seed: int = 1
) -> bytes:
    """A kept sheet's page over another study of the same ``work`` (its
    lines stay as they are: they lie on the work, not on the study).
    Raises :class:`NotDrawn` when the study is not the work's."""
    size, frac, field_ = _field(work, study)
    return _page(study, spilt, frac, size, field_, seed)


def strokes(view: View) -> list[chalk.Stroke]:
    """The take's titled marks as the chalk draws them."""
    return [chalk.Stroke(m.shape, [(p.x, p.y) for p in m.points], m.text) for m in titled(view)]


def lines(
    field_: Any, view: View, seed: int
) -> tuple[list[Any], list[str], list[list[tuple[float, float]]]]:
    """The take's marks in chalk over ``field_`` (the field as the page
    shows it, RGB 0…1): a layer for each (the field large), its pencil's
    colour (the one that stands out most from what it lies on,
    ``imaging.drawn.pencils``) and where its numbers stand, on its own line
    (fractions of the field; a ring of an echo each, a rhythm's first and
    last element)."""
    marks = titled(view)
    if not marks:
        return [], [], []
    h, w = field_.shape[:2]
    rgb = (np.clip(field_, 0, 1) * 255 + 0.5).astype(np.uint8)
    pencils = drawn.pencils([_course(m) for m in marks], Image.fromarray(rgb))
    layers = chalk.draw(rgb, strokes(view), seed)
    placed = [
        drawn.Placed(
            m.shape,
            [(p.x * w, p.y * h) for p in m.points],
            _loop_box(m, (w, h)) if m.shape == "loop" else None,
        )
        for m in marks
    ]
    numbers = [[(x / w, y / h) for x, y in found] for found in drawn.spots(placed, layers, field_)]
    return layers, [colour.lower() for _, colour in pencils], numbers


def _there(layer: Any) -> bool:
    return float((layer > 0.3).mean()) >= drawn.NO_MARK


def put_together(
    work: Image.Image,
    view: View,
    study: Image.Image,
    spilt: Image.Image | None,
    costs: dict[str, float],
    seed: int = 1,
) -> Sheet:
    """The sheet out of the model's answers and the chalk: ``work`` as it
    was sent (:func:`imaging.drawn.sent`), its ``study`` and the study with
    what runs out of it (``spilt``; None: the sheet goes without); the
    take's marks are drawn over the study as the page shows it. Raises
    :class:`NotDrawn` when the study is not the work's."""
    size, frac, field_ = _field(work, study)
    layers, colours, numbers = lines(field_, view, seed)
    return Sheet(
        page=_page(study, spilt, frac, size, field_, seed),
        layers=[drawn.png(layer) if _there(layer) else None for layer in layers],
        colours=colours,
        numbers=numbers,
        size=size,
        cost={k: round(v, 4) for k, v in costs.items()},
    )


def underlay(
    picture: Image.Image,
    view: View,
    paint: Paint,
    spill: Paint | None = None,
    costs: dict[str, float] | None = None,
    line: bool = False,
) -> Under:
    """What a work's takes are drawn over, asked for now: its study, and
    the study with what runs out of it (``spill`` paints it, ``paint``
    itself when None; one that cannot be had is left out); ``line``: a
    study in line alone (:func:`lined`). Raises :class:`NotDrawn` when the
    study is not the work's."""
    costs = costs if costs is not None else {}
    study, _ = _study(drawn.sent(picture), view, paint, costs, line)
    spilt = None
    try:
        spilt, costs["spill"] = (spill or paint)(spill_prompt(line), [drawn.padded(study)[0]])
    except AiUnavailable:
        raise
    except Exception as err:  # the sheet is paid for: it goes without its spill
        log.warning("the sheet's spill left out: %s", err)
    return Under(study, spilt)


def draw(
    picture: Image.Image,
    view: View,
    paint: Paint,
    seed: int = 1,
    under: Under | None = None,
    spill: Paint | None = None,
    costs: dict[str, float] | None = None,
    line: bool = False,
) -> Sheet:
    """The sheet of a take, asked for now: ``picture`` is the work (its
    field alone, when the take has one) and ``view`` the take as its field
    sees it (``View.inside``); ``spill`` paints what runs out of the study
    (``paint`` itself when None). Over ``under`` (the work's study, had
    before) nothing is asked: the take's marks are drawn in chalk over it
    (Mateusz 2026-11-12 23:20: "gdy zamawiam ponowną analizę, a podkład od
    Gemini już jest, to rób nim tylko kolorowe kreski"). ``costs``: what was paid for this sheet
    before (its study, asked apart), added to. Raises :class:`NotDrawn`
    when the study is not the work's; a spill that cannot be had is left
    out."""
    work = drawn.sent(picture)
    costs = dict(costs or {})
    if under is None:
        under = underlay(work, view, paint, spill, costs, line)
    sheet = put_together(work, view, under.study, under.spilt, costs, seed)
    sheet.under = under
    return sheet
