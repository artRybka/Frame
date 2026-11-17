"""Museum photographs cut down to the work in them (Mateusz 2026-11-14:
"automatyczne wykadrowanie z możliwością korekty lub przywrócenia").

The national museums of Warsaw and Kraków, and others now and then,
photograph works as they stand: in a gilt frame on an easel, on a grey
board, a print on its sheet pasted onto a card. Two questions, as the
night's other checks ask theirs (:class:`.critic_night.CriticNight`):

- the judge, Haiku, looks at the thumbnail and names what is around the
  work (``surround``): a hundredth of a cent a work, so the whole catalogue
  is looked at, Favourites, playlists and Discover first;
- where a frame, an easel, a board or a backdrop is, Opus names the layers
  from the outside in and their corners (a picture and a copy with a grid:
  the smaller models place them badly), about 2 cents a work, half that
  through the Batch API. Its corners are set on the picture's own edges
  (:func:`..imaging.cut.snap`) and the work is cut (``Item.cut``,
  ``ImageCache.recut``) only when Opus is sure of them.

Paper is never cut by itself (a poster's printed line, a page around an
illustration, a print's margin were the trial's only mistakes): a print or
drawing keeps its sheet; without it ("bez marginesu") only when the owner
asks, then Opus is asked at once. The same is done when a card opens on a
work not looked at yet (:meth:`Crops.soon`). The owner corrects the corners
or gives the cut up in the app; a work he has set is never cut again by
itself.

A work whose own outline is no rectangle (a cut-out, a shard, a round
miniature in its gilt frame, a plate, an oval) is never cut (Mateusz
2026-11-15: „Przy obiektach o kształcie innym niż prostokąt … nie kadruj.
Już wykadrowane – trzeba przywrócić”): Opus names the outline with the
corners (``shape``), and the cuts set before it was asked are looked at
once more (:meth:`Crops.reshaped`, :meth:`Crops.now`) and given back whole.
"""

from __future__ import annotations

import base64
import io
import logging
import math
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw

from ..imaging.cut import (
    Quad,
    area,
    backdrop_quad,
    framed_geometry,
    sheet_out_to_strips,
    snap,
    strip_depths,
    thin_backdrop,
    valid,
    worth_cutting,
)
from ..imaging.layout import Crop, load_image
from ..library.images import OWN_SOURCES
from ..library.models import NOT_RECTANGLE, SHAPES, Cut, Framing, ItemKind, quads_close
from .client import HAIKU, OPUS, image_block, request
from .critic_night import REST, CriticNight
from .gatekeeper import facts

if TYPE_CHECKING:
    from ..library import Importer, Item

log = logging.getLogger(__name__)

KIND = "crops"
SWITCH = "crops"

#: What can be around a work in its photograph (the judge's words).
SURROUND = ("backdrop", "easel", "frame", "mount", "paper_margin", "page_text", "colour_chart")
#: Around the work and never part of it: Opus is asked for the corners.
CUT_AROUND = frozenset({"backdrop", "easel", "frame", "mount", "colour_chart"})
#: A print's or a page's paper: kept unless the owner says otherwise.
PAPER = frozenset({"paper_margin", "page_text"})
#: Sources that photograph works as they stand, looked at first.
FIRST_SOURCES = ("mnw", "mnk")

#: Once the works cared about are looked at for a thin strip of backdrop
#: the judge missed (:meth:`Crops.swept`); a new number looks again.
BAND_SWEEP = 2
#: The thin strips' check a work was asked with (``asked[id]["band"]``):
#: 2 (2026-11-15) falls back on the pixels where Opus was unsure, so works
#: asked by 1 and left uncut are asked again.
BAND = 2
#: Opus's question a work was asked with (``asked[id]["q"]``): 2
#: (2026-11-16) is sure of a print's plate when only its sheet runs off
#: the photograph or under a colour chart (Erichsøe's „Selvportræt med
#: Violin”, SMK KKS10560, uncut and never asked again when its card
#: opened). A card opened on a work left uncut by an older question asks
#: it again; the night does not.
QUESTION = 2
#: Once the cuts kept with a plate that is the work itself are tidied
#: (:meth:`Crops.untwinned`).
TWIN_TIDY = 1
#: Once the cuts kept whose sheet lies on its plate on one side are
#: tidied (:meth:`Crops.sheets_out`).
SHEET_TIDY = 1

#: Once the cuts set from the pixels' strips alone (:meth:`Crops.strips`)
#: before they had to agree with Opus's answer are given back whole and
#: put before Opus again (:meth:`Crops.strips_rechecked`).
STRIP_TIDY = 1
#: The note such a cut was written with.
STRIPS_NOTE = "thin strips of backdrop, from the pixels"

#: Once the cuts set before the work's outline was asked
#: (:attr:`Cut.shape`) are put before Opus again (:meth:`Crops.reshaped`).
SHAPE_SWEEP = 1
#: Of those, asked in one night at most (a short question, a smaller
#: picture: about half a cent each through the Batch API).
RESHAPE_PER_NIGHT = 300
#: The picture for that question.
SHAPE_SIDE = 1000

#: Once the cuts set before the frame's or the passe-partout's outer edge
#: was kept (:attr:`Cut.surround`, the card's "W ramie", Mateusz
#: 2026-11-17) are put before Opus again for it (:meth:`Crops.surrounded`).
SURROUND_SWEEP = 1
#: Of those, asked in one night at most: the corners' whole question,
#: about a cent each through the Batch API.
SURROUND_PER_NIGHT = 150
#: The layers of Opus's answer kept as what surrounds the work, and their
#: name on the card.
SURROUND_KINDS = {"frame_outer": "frame", "mount": "mount"}
#: :func:`surround_in`: a surround this much larger than the work at least.
SURROUND_LARGER = 1.03
#: What the judge saw around a work that may have a frame or a mount.
FRAMED_AROUND = frozenset({"frame", "mount"})

#: How long a page about a work waits for its photograph to be looked at
#: and cut (seconds): the judge and Opus take 5 to 15 s, a minute when the
#: museum is slow to give the photograph.
PAGE_WAIT = 90.0

#: The judge's thumbnail, and Opus's picture (the trial's sizes).
JUDGE_SIDE = 640
PHOTO_SIDE = 1400

JUDGE = (
    "A museum photograph of one artwork. Which of these, if any, are visible around the "
    "artwork itself, taking at least a thin strip at an edge of the photograph: backdrop "
    "(wall, cloth, grey or white board behind), easel, picture frame, mount or passe-partout, "
    "blank paper margin around a print or drawing, printed page text around an illustration, "
    "colour chart. An empty list if the artwork runs to the photograph's edges."
)
JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["surround"],
    "properties": {
        "surround": {"type": "array", "items": {"type": "string", "enum": list(SURROUND)}}
    },
}

LAYERS = ("frame_outer", "frame_inner", "mount", "sheet", "plate", "canvas")
CORNERS = """This is a museum's photograph of one catalogued artwork. Around the work there \
may be things that are not the work: the backdrop or wall, an easel, a picture frame (gilded \
or plain), a cardboard mount or passe-partout, the sheet a print was pulled on, conservation \
strips, a colour chart, the block, covers and binding of a sketchbook or album and the edges \
of the pages under the one shown.

List the nested rectangles you can see, from the outside in, each as its four corners \
(top-left, top-right, bottom-right, bottom-left) in the coordinates of the grid drawn on the \
second copy (0-1000 across, 0-1000 down, over the whole photograph). Put each corner exactly \
on the visible edge; if the photograph is taken at an angle, the corners need not form a \
rectangle. Kinds: "frame_outer", "frame_inner" (the frame's opening, where the painted \
surface starts), "mount" (board/passe-partout), "sheet" (the paper of a print, drawing, \
poster or page; in a sketchbook or album only the one page shown is a sheet, the book's block \
and the pages under it are not listed), "plate" (a print's plate mark or the printed/drawn \
image area), "canvas" (an unframed painting's edge). The backdrop is never listed: it is \
the photograph.

Then choose:
- "work": the index of the rectangle that is the artwork itself as one would hang it without \
frame: for a painting the painted surface (inside the frame); for a print, drawing or poster \
the image area if the paper around it is blank margin; the whole sheet if the image runs to \
the paper's edge or the paper carries part of the work (a signature, a printed title or text, \
a deliberate margin belonging to the design).
- "with_paper": the index of the sheet if a viewer might want to keep the paper margin \
(prints with a plate mark), else null.
- "shape": the outline of the artwork itself as it is shown (not of its frame, mount or \
backdrop): "rectangle" (a canvas, panel, sheet, page or plate, also seen at an angle or with \
slightly rounded corners), "round" (a circle or an oval: a tondo, a portrait miniature or \
medallion, a plate or dish, a medal or coin, a work seen through a round or oval opening) or \
"irregular" (any other outline: a cut-out following the drawn shape, a silhouette, a fragment \
or shard with broken edges, an arched or shaped panel, a fan, an object). Only a rectangle is \
cut out of its photograph; for the others still list what you see.
- "confident": true only if the edges of the work you chose are clearly visible. A page's \
rounded corners or its bound edge are no reason for doubt: put the corners just inside the \
rounding, on the page. Nor is a sheet that runs off the photograph or lies under a colour \
chart, ruler or label when the work is the plate inside it: list the sheet as far as it shows.
Answer in JSON only."""
#: The owner's own photograph of a work of his ("Dodaj własne dzieło",
#: Mateusz 2026-11-15): taken with a phone at home, often at an angle, the
#: work hanging on a wall in its frame, sometimes behind glass.
HOME = CORNERS.replace(
    "This is a museum's photograph of one catalogued artwork.",
    "This is a photograph its owner took with a phone of one artwork at home, often at an "
    "angle and in its frame on a wall, sometimes behind glass with reflections. Find the "
    "work itself as a museum would catalogue it.",
)
CORNERS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["layers", "work", "with_paper", "shape", "confident", "note"],
    "properties": {
        "layers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "corners"],
                "properties": {
                    "kind": {"type": "string", "enum": list(LAYERS)},
                    "corners": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                    },
                },
            },
        },
        "work": {"type": ["integer", "null"]},
        "with_paper": {"type": ["integer", "null"]},
        "shape": {"type": "string", "enum": list(SHAPES)},
        "confident": {"type": "boolean"},
        "note": {"type": "string"},
    },
}


SHAPE = """This is a museum's photograph of one catalogued artwork. What is the outline of \
the artwork itself as it is shown, not of its frame, mount, the backdrop or the board it lies \
on?
- "rectangle": a canvas, a panel, a sheet, a page, a print's plate: four straight sides, also \
when photographed at an angle or with slightly rounded corners.
- "round": a circle or an oval: a tondo, a portrait miniature or medallion in its round frame, \
a plate or dish, a medal or coin, a work seen through a round or oval opening of its frame or \
mount.
- "irregular": any other outline: a cut-out following the drawn shape, a silhouette, a \
fragment or shard with broken edges, an arched or shaped panel, a fan, an object (a vase, a \
sculpture).
Answer in JSON only."""
SHAPE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["shape", "note"],
    "properties": {
        "shape": {"type": "string", "enum": list(SHAPES)},
        "note": {"type": "string"},
    },
}


def shape_of(data: dict[str, Any]) -> str:
    """The work's outline in Opus's answer (:data:`SHAPES`), "" when it
    does not say (an answer to the question before 1.145.153)."""
    shape = data.get("shape")
    return shape if isinstance(shape, str) and shape in SHAPES else ""


def _block(img: Image.Image) -> dict[str, Any]:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    data = base64.standard_b64encode(out.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def gridded(img: Image.Image) -> Image.Image:
    """``img`` with a 0–1000 grid drawn over it: the corners are read off it."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    for k in range(0, 1001, 50):
        x, y = k * (w - 1) / 1000, k * (h - 1) / 1000
        major = k % 100 == 0
        colour = (255, 0, 255) if major else (0, 200, 255)
        width = 2 if major else 1
        draw.line([(x, 0), (x, h)], fill=colour, width=width)
        draw.line([(0, y), (w, y)], fill=colour, width=width)
        if major:
            draw.text((x + 3, 3), str(k), fill=colour)
            draw.text((3, y + 3), str(k), fill=colour)
    return out


def _quad(layer: Any) -> Quad | None:
    try:
        corners = [(float(x) / 1000, float(y) / 1000) for x, y in layer["corners"]]
    except (KeyError, TypeError, ValueError):
        return None
    return valid(corners)


def read_layers(data: dict[str, Any]) -> tuple[Quad | None, Quad | None] | None:
    """Opus's answer as the corners shown (the work, a print with its
    sheet; None for the whole photograph) and a print's without the sheet
    (or None); None when there is nothing to cut to. A sheet is always what
    is shown: paper is cut away only by the owner, also when Opus names the
    plate and no sheet around it (a sheet filling the photograph, MNW)."""
    layers = data.get("layers")
    work = data.get("work")
    if not isinstance(layers, list) or not isinstance(work, int) or not 0 <= work < len(layers):
        return None
    quads = [_quad(layer) if isinstance(layer, dict) else None for layer in layers]
    kinds = [layer.get("kind") if isinstance(layer, dict) else None for layer in layers]
    work_quad = quads[work]
    if work_quad is None:
        return None
    if kinds[work] == "sheet":
        return work_quad, None  # the page itself: a sketchbook's block around it is no paper
    paper = data.get("with_paper")
    sheet = paper if isinstance(paper, int) and 0 <= paper < work else None
    if sheet is None:  # the sheet nearest around the work
        sheet = next((n for n in range(work - 1, -1, -1) if kinds[n] == "sheet"), None)
    if sheet is None or quads[sheet] is None:
        if kinds[work] == "plate":  # the sheet is the photograph: its paper stays
            return None, work_quad
        return work_quad, None
    return quads[sheet], work_quad


def _aside(claim: dict[str, Any]) -> bool:
    """A claim put before Opus beside the night's cutting (the outline
    asked again, the frame's edge): outside its limit and its counts."""
    return bool(claim.get("reshape") or claim.get("frame_edge"))


def _surround_fields(found: dict[str, Any]) -> dict[str, Any]:
    """:attr:`Cut.surround` and its kind from Opus's corners
    (:func:`corners_in`), asked with them; nothing for corners from
    elsewhere (the pixels' strips)."""
    if "surround" not in found:
        return {}
    return {
        "surround": found.get("surround"),
        "surround_kind": str(found.get("surround_kind") or ""),
        "surround_asked": True,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _box(quad: Quad | None) -> tuple[float, float, float, float]:
    """The box (left, top, right, bottom) around ``quad``, the whole
    photograph for None."""
    if quad is None:
        return 0.0, 0.0, 1.0, 1.0
    xs, ys = [x for x, _ in quad], [y for _, y in quad]
    return min(xs), min(ys), max(xs), max(ys)


def _crop_moved(crop: Crop | None, old: Quad | None, new: Quad | None) -> Crop | None:
    """``crop`` (a part of the photograph cut to ``old``, None: whole) as
    the same part of the photograph cut to ``new``: its centre moved, its
    zoom changed by as much as the picture is smaller or larger."""
    if crop is None:
        return None
    ox0, oy0, ox1, oy1 = _box(old)
    nx0, ny0, nx1, ny1 = _box(new)
    if min(ox1 - ox0, oy1 - oy0, nx1 - nx0, ny1 - ny0) <= 0:
        return crop
    x = ox0 + crop.x * (ox1 - ox0)
    y = oy0 + crop.y * (oy1 - oy0)
    share = ((nx1 - nx0) + (ny1 - ny0)) / ((ox1 - ox0) + (oy1 - oy0))
    return crop.model_copy(
        update={
            "x": min(1.0, max(0.0, (x - nx0) / (nx1 - nx0))),
            "y": min(1.0, max(0.0, (y - ny0) / (ny1 - ny0))),
            "zoom": min(8.0, max(1.0, crop.zoom * share)),
        }
    )


def framing_moved(
    framing: dict[str, Framing], old: Quad | None, new: Quad | None
) -> dict[str, Framing]:
    """The owner's framings, set on the photograph cut to ``old`` (None:
    whole), as the same parts of it cut to ``new``: a cut keeps what he
    chose to show, the model's (Wyspiański's „Macierzyństwo”, 2026-11-15:
    a close-up of the mother's face kept the thin wooden frame of the copy
    he picked from being cut away) and his own corrected corners alike
    (they wiped his framings until the audit of 2026-11-15)."""
    return {
        side: Framing(
            fill=_crop_moved(f.fill, old, new),
            detail=_crop_moved(f.detail, old, new),
            picture=_crop_moved(f.picture, old, new),
            fit=_crop_moved(f.fit, old, new),
        )
        for side, f in framing.items()
    }


def framing_within(framing: dict[str, Framing], quad: Quad) -> dict[str, Framing]:
    """The owner's framings, set on the whole photograph, as the same parts
    of the picture cut to ``quad`` (:func:`framing_moved`)."""
    return framing_moved(framing, None, quad)


#: :func:`strips_fit`: a strip may end this far inside the sheet Opus saw
#: (his corners are a hundredth or so off), and must end this far outside
#: the image area he saw within it (a print keeps its paper).
STRIP_AGREE = 0.012
PAPER_KEPT = 0.008


def strips_fit(depths: tuple[float, float, float, float], data: dict[str, Any]) -> bool:
    """Whether the thin strips found in the pixels (``depths``: top,
    bottom, left, right, :func:`..imaging.cut.strip_depths`) are backdrop
    by what Opus saw (``data``, his answer however sure): each ends on the
    sheet (or canvas) he named, not inside it, and outside every plate or
    image area. A print whose paper runs off the photograph has a margin as
    plain as any board: Jackson's chiaroscuro woodcut after Veronese
    (Europeana, Mateusz 2026-11-15) lost its margin on two sides and kept
    it on the other two, Géricault's lithographs (Cleveland, NGA) theirs
    and the lettering under them. With no sheet named, the strips must
    run round all four sides and clear of everything he named; with
    nothing named, nothing tells."""
    layers = data.get("layers")
    if not isinstance(layers, list):
        layers = []
    named: list[tuple[str, tuple[float, float, float, float]]] = []
    for layer in layers:
        quad = _quad(layer) if isinstance(layer, dict) else None
        if quad is not None:
            named.append((str(layer.get("kind") or ""), _box(quad)))
    if not named:
        return False  # nothing to tell a print's margin from board by
    top, bottom, left, right = depths
    # (side's index in a box, where the strip ends, whether it lies at the
    # box's low end: left or top)
    ends = [
        (i, end, low)
        for i, end, low, depth in (
            (1, top, True, top),
            (3, 1 - bottom, False, bottom),
            (0, left, True, left),
            (2, 1 - right, False, right),
        )
        if depth > 0
    ]
    if not ends:
        return False

    def outside(box: tuple[float, float, float, float], by: float) -> bool:
        """Every strip ends at least ``by`` outside ``box`` (less than
        ``-by`` inside it)."""
        return all((box[i] - end if low else end - box[i]) >= by for i, end, low in ends)

    if any(kind == "plate" for kind, _ in named) and not all(
        outside(box, PAPER_KEPT) for kind, box in named if kind == "plate"
    ):
        return False
    sheets = [box for kind, box in named if kind in ("sheet", "canvas")]
    if sheets:
        return outside(sheets[0], -STRIP_AGREE)
    return len(ends) == 4 and all(outside(box, PAPER_KEPT) for _, box in named)


#: :func:`tilted`: a side this far from upright or level (degrees) is no
#: perspective of a work standing or lying straight.
TILT = 25.0


def tilted(quad: Quad) -> bool:
    """Whether ``quad`` stands on a corner: a lozenge (Mondrian's Victory
    Boogie-Woogie, WikiArt, cut along its edges into an upright square,
    2026-11-15), not a rectangle at an angle."""
    for i in range(4):
        (x0, y0), (x1, y1) = quad[i], quad[(i + 1) % 4]
        angle = math.degrees(math.atan2(abs(y1 - y0), abs(x1 - x0)))
        if min(angle, 90.0 - angle) > TILT:
            return True
    return False


def _kind(data: dict[str, Any], quad: Quad | None) -> str:
    """The kind Opus named the layer ``quad`` was read from, "" if none."""
    for layer in data.get("layers") or []:
        if isinstance(layer, dict) and quad is not None and _quad(layer) == quad:
            return str(layer.get("kind") or "")
    return ""


#: :func:`plate_for_chart`: a side this near the photograph's edge runs off it.
OFF_EDGE = 0.02


#: :func:`on_photo_edge`: a side Opus put this near the photograph's edge
#: is on it.
ON_EDGE = 0.003


def on_photo_edge(said: Quad, snapped: Quad) -> Quad:
    """``snapped`` with the sides Opus put on the photograph's edge back
    there: a sheet that runs off the photograph has no edge of its own
    on that side, and the snap took the line of the print's border or of
    a ruler for it (a Hiroshige whose paper fills the photograph cut to
    its keyline, 2026-11-16)."""
    out = [list(c) for c in snapped]
    for idx, axis, edge in (((0, 1), 1, 0.0), ((1, 2), 0, 1.0), ((2, 3), 1, 1.0), ((0, 3), 0, 0.0)):
        if all(abs(said[i][axis] - edge) <= ON_EDGE for i in idx):
            for i in idx:
                out[i][axis] = edge
    return [(x, y) for x, y in out]


def plate_for_chart(found: dict[str, Any]) -> dict[str, Any]:
    """``found`` (:func:`corners_in`) with the plate shown instead of a
    sheet that runs off the photograph on two sides or more (or is the
    photograph, None) where a colour chart was seen: the chart, a ruler
    and the museum's label lie on that paper, so showing it shows them
    (Erichsøe, SMK KKS10560, Mateusz 2026-11-16). The plate is then the
    work, with no paper to choose."""
    work, plate = found.get("work"), found.get("plate")
    if plate is None:
        return found
    if work is not None:
        xs, ys = [x for x, _ in work], [y for _, y in work]
        off = sum(
            (
                max(xs[0], xs[3]) <= OFF_EDGE,
                min(xs[1], xs[2]) >= 1 - OFF_EDGE,
                max(ys[0], ys[1]) <= OFF_EDGE,
                min(ys[2], ys[3]) >= 1 - OFF_EDGE,
            )
        )
        if off < 2:
            return found
    return {**found, "work": plate, "plate": None}


def surround_in(
    img: Image.Image, data: dict[str, Any], work: Quad | None
) -> tuple[Quad, str] | None:
    """The outer edge of the frame or the passe-partout around ``work`` in
    Opus's answer (``data``), set on the photograph's edges, and what it is
    ("frame", "mount"): the outermost such layer around the work and
    clearly larger than it. None when there is none."""
    if work is None:
        return None
    x0, y0, x1, y1 = _box(work)
    for layer in data.get("layers") or []:  # from the outside in
        if not isinstance(layer, dict):
            continue
        kind = SURROUND_KINDS.get(str(layer.get("kind") or ""))
        quad = _quad(layer)
        if kind is None or quad is None:
            continue
        bx0, by0, bx1, by1 = _box(quad)
        if bx0 > x0 + 0.005 or by0 > y0 + 0.005 or bx1 < x1 - 0.005 or by1 < y1 - 0.005:
            continue  # not around the work
        if area(quad) < area(work) * SURROUND_LARGER:
            continue
        snapped = snap(img, quad, str(layer.get("kind")))
        return (snapped if valid(snapped) is not None else quad), kind
    return None


def _owners_frame(cut: Cut) -> dict[str, Any]:
    """The frame's edge the owner set on ``cut`` (:attr:`Cut.surround_by`),
    kept when the work is cut anew."""
    return {
        "surround": cut.surround,
        "surround_kind": cut.surround_kind,
        "surround_by": "owner",
        "surround_asked": True,
    }


def framed(cut: Cut) -> Cut:
    """``cut`` with the card's "W ramie" as it is now (:attr:`Cut.framed_kind`,
    :attr:`Cut.framed_aspect`, :attr:`Cut.framed_inner`)."""
    by, shown = cut.framed_by(), cut.shown()
    found = None
    if by is not None and shown is not None:
        found = framed_geometry(by[0], shown, cut.aspect)
    if by is None or found is None:
        none: dict[str, Any] = {"framed_kind": "", "framed_aspect": 0.0, "framed_inner": None}
        return cut.model_copy(update=none)
    return cut.model_copy(
        update={"framed_kind": by[1], "framed_aspect": found[0], "framed_inner": found[1]}
    )


def corners_in(img: Image.Image, data: dict[str, Any]) -> dict[str, Any] | None:
    """Opus's answer (:data:`CORNERS_SCHEMA`) as corners set on the edges
    of ``img``, the photograph it was asked about (:meth:`Crops.corners`)."""
    shape = shape_of(data)
    read = read_layers(data)
    if read is None:
        return None
    if read[0] is not None and tilted(read[0]):
        return None  # a lozenge hung on its point (Mondrian), no upright work
    shown = snap(img, read[0], _kind(data, read[0])) if read[0] is not None else None
    if shown is not None and read[0] is not None and _kind(data, read[0]) == "sheet":
        shown = on_photo_edge(read[0], shown)
    plate = snap(img, read[1], "plate") if read[1] is not None else None
    if shown is not None and plate is not None:
        shown = sheet_out_to_strips(img, shown, plate)  # Beksiński, MNK
    if shown is not None and _kind(data, read[0]) == "sheet":
        # A sheet taken in from its edge to a line printed on it (a
        # poster's border, MNK 321605): out to where the board's strip ends,
        # when the strips are board by Opus's answer (:func:`strips_fit`).
        depths = strip_depths(img)
        if strips_fit(depths, data):
            shown = sheet_out_to_strips(img, shown, None, depths)
    if shown is not None and not worth_cutting(shown):
        shown = None  # the sheet is the photograph: only the plate is cut
    if shown is None and plate is None:
        return None
    around = surround_in(img, data, shown)
    return {
        "work": shown,
        "plate": plate,
        "aspect": round(img.width / img.height, 5),
        "shape": shape,
        "note": str(data.get("note") or "")[:300],
        "surround": around[0] if around is not None else None,
        "surround_kind": around[1] if around is not None else "",
    }


class Crops(CriticNight):
    kind = KIND
    switch = SWITCH
    #: 2 (2026-11-14): a sketchbook's page is the work, not its block, and
    #: a page's rounded corners are no doubt. Works Opus would not cut are
    #: asked again; the judge's "nothing around it" stands.
    version = 2
    judge_model = HAIKU
    critic_model = OPUS
    #: The judge: about 0.01 cent a work through the Batch API, 600 a night
    #: some 2 USD a month while the catalogue's backlog lasts.
    per_night = 600
    #: Opus: about a cent a work through the Batch API.
    critic_per_night = 60

    importer: Importer | None = None
    _pool: ThreadPoolExecutor | None = None

    def _setup(self) -> None:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(2, thread_name_prefix="crops")
            self._running: dict[str, Future[bool]] = {}
            self._guard = threading.Lock()

    def asked(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in (self.state().get("asked") or {}).items()
            if isinstance(v, dict)
            and (v.get("v") == self.version or (v.get("v") == 1 and v.get("critic") is not False))
        }

    # -- which works --------------------------------------------------------------

    @staticmethod
    def wanted(item: Item) -> bool:
        """A museum work whose photograph may have something around it."""
        return (
            item.kind == ItemKind.ARTWORK
            and item.source not in OWN_SOURCES
            and not item.part_of
            and item.look is None
            and not item.excluded
            and not item.seen_as
            and not (item.sharper is not None and item.sharper.restored)
            and bool(item.thumb_url or item.image_url or item.sharper is not None)
        )

    @staticmethod
    def stale(item: Item) -> bool:
        """No cut for the picture shown: none, or the model's for another
        picture (a sharper copy took its place). The owner's stays his."""
        cut = item.cut
        if cut is None:
            return True
        return cut.by == "auto" and cut.picture != item.picture_key()

    @classmethod
    def open_to_cut(cls, item: Item) -> bool:
        """The model may cut it: no cut for the picture shown, or only its
        paper seen around it and nothing cut (a sheet on a thin strip of
        board the judge took for the paper's margin)."""
        cut = item.cut
        return cls.stale(item) or (
            cut is not None
            and cut.by == "auto"
            and cut.work is None
            and cut.plate is None
            and not cut.not_rectangle
        )

    @classmethod
    def unshaped(cls, item: Item) -> bool:
        """The model's cut of the picture shown, set before the work's
        outline was asked (:attr:`Cut.shape`): it is asked now, and a work
        that is no rectangle is given back whole."""
        cut = item.cut
        return (
            cut is not None
            and cut.by == "auto"
            and not cls.stale(item)
            and cut.shown() is not None
            and cut.shape == ""
        )

    @classmethod
    def unsurrounded(cls, item: Item) -> bool:
        """A cut of the picture shown set before the frame's or the
        passe-partout's outer edge was kept (:attr:`Cut.surround`), where
        one may be: a frame or a mount seen around the work, or a work of
        his own (photographed in its frame on a wall). Asked once."""
        cut = item.cut
        if cut is None or cut.surround_asked or cut.work is None or item.cut_shown() is None:
            return False
        if cut.by == "auto" and cls.stale(item):
            return False
        return item.source in OWN_SOURCES or bool(FRAMED_AROUND & set(cut.around))

    def banded(self, item: Item) -> bool:
        """A thin strip of backdrop along the thumbnail's sides
        (:func:`..imaging.cut.thin_backdrop`), which the judge misses."""
        path = self.images.kept_thumb(item.id)
        if path is None:
            return False
        try:
            with Image.open(path) as img:
                return thin_backdrop(img)
        except OSError:
            return False

    def candidates(self, asked: dict[str, Any]) -> list[Item]:
        # A work asked about is asked again when another copy took the
        # place of the photograph looked at (``Item.picture_key``): a
        # sharper copy picked at night was shown whole until its card was
        # opened (the audit of 2026-11-15).
        found = [
            i
            for i in self.library.all_items()
            if self.stale(i) and self.wanted(i) and not self._looked_at(asked.get(i.id), i)
        ]
        found.sort(key=lambda i: i.added_at or "", reverse=True)
        found.sort(key=lambda i: i.source not in FIRST_SOURCES)
        found.sort(key=lambda i: not (not i.pooled or i.favorite or i.show_count > 0))
        cared = self.cared()
        found.sort(key=lambda i: cared.get(i.id, REST))
        return found

    @staticmethod
    def _looked_at(entry: dict[str, Any] | None, item: Item) -> bool:
        """Whether ``entry`` (``asked[id]``) is a look at the picture the
        work is shown from now; a photograph that could not be had is not
        asked about again."""
        if entry is None:
            return False
        return bool(entry.get("broken")) or entry.get("p", "") == item.picture_key()

    def noted(self, item: Item) -> dict[str, Any]:
        return {"p": item.picture_key(), "q": QUESTION}

    def _round(self, state: dict[str, Any]) -> tuple[bool, list[tuple[Item, dict[str, Any]]]]:
        if not state.get("claims"):
            return super()._round(state)
        claims: dict[str, Any] = state["claims"]
        found: list[tuple[Item, dict[str, Any]]] = []
        rechecks: list[tuple[Item, dict[str, Any]]] = []
        surrounds = 0
        for item_id, claim in list(claims.items()):
            item = self.library.get(item_id)
            if item is None:
                claims.pop(item_id, None)
            elif claim.get("reshape"):
                if len(rechecks) < RESHAPE_PER_NIGHT:
                    rechecks.append((item, claim))
            elif claim.get("frame_edge"):
                if surrounds < SURROUND_PER_NIGHT:
                    rechecks.append((item, claim))
                    surrounds += 1
            elif len(found) < self.limit(True):
                found.append((item, claim))
        return True, found + rechecks

    def base_limit(self, critic: bool) -> int:
        return self.critic_per_night if critic else self.per_night

    def asked_in(self, round_: list[tuple[Item, dict[str, Any]]], critic: bool) -> int:
        # (the outlines asked again have a limit of their own)
        return sum(1 for _, claim in round_ if not _aside(claim))

    def waiting_claims(self) -> int:
        """Works the judge found something around, waiting for Opus."""
        claims = self.state().get("claims") or {}
        return sum(1 for c in claims.values() if not _aside(c or {}))

    def order(self) -> bool:
        self.reshaped()
        self.surrounded()
        self.strips_rechecked()
        self.swept()
        self.untwinned()
        self.sheets_out()
        return super().order()

    def reshaped(self) -> int:
        """Once (:data:`SHAPE_SWEEP`): the model's cuts set before the
        work's outline was asked are put before Opus with that question
        alone; a work that is no rectangle is given back whole when the
        answer comes (:meth:`write`). Not while a round is under way: its
        answers may bring more. How many."""
        state = self.state()
        if state.get("shape_sweep") == SHAPE_SWEEP or state.get("order"):
            return 0
        claims = state.get("claims") or {}
        cared = self.cared()
        found = [i for i in self.library.all_items() if self.unshaped(i) and i.id not in claims]
        found.sort(key=lambda i: cared.get(i.id, REST))
        for item in found:
            claims[item.id] = {"reshape": True}
        state["claims"], state["shape_sweep"] = claims, SHAPE_SWEEP
        self._save(state)
        log.info("crops: %d cuts set before the outline was asked, for Opus", len(found))
        return len(found)

    def surrounded(self) -> int:
        """Once (:data:`SURROUND_SWEEP`): the cuts set before the frame's or
        the passe-partout's outer edge was kept are put before Opus for it
        (:meth:`unsurrounded`), the works cared about first,
        :data:`SURROUND_PER_NIGHT` a night. Not while a round is under way.
        How many."""
        state = self.state()
        if state.get("surround_sweep") == SURROUND_SWEEP or state.get("order"):
            return 0
        claims = state.get("claims") or {}
        cared = self.cared()
        found = [i for i in self.library.all_items() if self.unsurrounded(i) and i.id not in claims]
        found.sort(key=lambda i: cared.get(i.id, REST))
        for item in found:
            around = list(item.cut.around) if item.cut else []
            claims[item.id] = {"frame_edge": True, "around": around}
        state["claims"], state["surround_sweep"] = claims, SURROUND_SWEEP
        self._save(state)
        log.info("crops: %d cuts without their frame's edge, for Opus", len(found))
        return len(found)

    def strips_rechecked(self) -> int:
        """Once (:data:`STRIP_TIDY`): the model's cuts made from the pixels'
        strips alone (1.145.140 to 1.145.170) are given back whole and put
        before Opus again, whose answer they must now agree with
        (:func:`strips_fit`): a print's own paper margin had been taken
        for a strip of board (Jackson after Veronese, Europeana; Géricault,
        Cleveland and NGA; Mateusz 2026-11-15). Not while a round is under
        way. How many."""
        state = self.state()
        if state.get("strip_tidy") == STRIP_TIDY or state.get("order"):
            return 0
        from_strips = {w.get("id"): w for w in self.written() if w.get("note") == STRIPS_NOTE}
        done = 0
        for item_id, entry in from_strips.items():
            item = self.library.get(str(item_id))
            cut = item.cut if item is not None else None
            if item is None or cut is None or cut.by != "auto" or self.stale(item):
                continue
            if cut.work is None or not quads_close(cut.work, entry.get("work") or []):
                continue
            whole = Cut(
                around=cut.around,
                aspect=cut.aspect,
                picture=item.picture_key(),
                shape=cut.shape,
                at=_now(),
            )
            self.apply(item, whole)
            state = self.state()
            claims = state.get("claims") or {}
            claims[item.id] = {"around": sorted({*cut.around, "backdrop"}), "band": True}
            state["claims"] = claims
            self._save(state)
            done += 1
        state = self.state()
        state["strip_tidy"] = STRIP_TIDY
        self._save(state)
        log.info("crops: %d cuts made from the pixels' strips alone, given back for Opus", done)
        return done

    def sheets_out(self) -> int:
        """Once (:data:`SHEET_TIDY`): the cuts kept whose sheet lies on
        its plate on a side where a strip of backdrop shows further out
        (:func:`..imaging.cut.sheet_out_to_strips`) get that side back. How
        many."""
        state = self.state()
        if state.get("sheet_tidy") == SHEET_TIDY:
            return 0
        done = 0
        for item in self.library.all_items():
            cut = item.cut
            if cut is None or cut.work is None or cut.plate is None:
                continue
            full = self.images.full_path(item)
            if not full.is_file():
                continue
            try:
                with Image.open(full) as img:
                    work = sheet_out_to_strips(img, cut.work, cut.plate)
            except OSError:
                continue
            if work != cut.work:
                self.apply(item, cut.model_copy(update={"work": work}))
                done += 1
        state = self.state()
        state["sheet_tidy"] = SHEET_TIDY
        self._save(state)
        log.info("crops: %d sheets got back a side taken for their plate's", done)
        return done

    def untwinned(self) -> int:
        """Once (:data:`TWIN_TIDY`): the cuts kept with a "plate" that is
        the work itself lose it (:meth:`Cut.without_twin`); the picture
        shown stays. How many."""
        state = self.state()
        if state.get("twin_tidy") == TWIN_TIDY:
            return 0
        done = 0
        for item in self.library.all_items():
            if item.cut is not None and item.cut.without_twin() is not item.cut:
                self.library.update(item.id, cut=item.cut.without_twin())
                done += 1
        state = self.state()
        state["twin_tidy"] = TWIN_TIDY
        self._save(state)
        log.info("crops: %d cuts lost a plate that was the work itself", done)
        return done

    def swept(self) -> int:
        """Once (:data:`BAND_SWEEP`): the works cared about that the judge
        passed by before thin strips of backdrop were looked for, put
        before Opus when their thumbnail shows one. The rest are looked at
        again when their card opens. How many."""
        state = self.state()
        if state.get("band_sweep") == BAND_SWEEP:
            return 0
        asked = self.asked()
        claims = state.get("claims") or {}
        cared = self.cared()
        found: dict[str, dict[str, Any]] = {}
        for item_id in sorted(cared, key=lambda i: cared[i]):
            entry = asked.get(item_id)
            if entry is None or entry.get("band") == BAND or item_id in claims:
                continue
            item = self.library.get(item_id)
            if item is None or not self.wanted(item):
                continue
            if self.open_to_cut(item) and self.banded(item):
                around = item.cut.around if item.cut is not None else []
                found[item_id] = {"around": sorted({*around, "backdrop"}), "band": True}
        state = self.state()
        claims = state.get("claims") or {}
        asked_all = state.get("asked") or {}
        for item_id, claim in found.items():
            claims.setdefault(item_id, claim)
            if isinstance(asked_all.get(item_id), dict):
                asked_all[item_id]["band"] = BAND
        state["claims"], state["asked"], state["band_sweep"] = claims, asked_all, BAND_SWEEP
        self._save(state)
        log.info("crops: %d works cared about show a thin backdrop, for Opus", len(found))
        return len(found)

    # -- the questions ------------------------------------------------------------

    def question(self, item: Item) -> dict[str, Any]:
        content = [
            image_block(self.images, item, max_side=JUDGE_SIDE),
            {"type": "text", "text": JUDGE},
        ]
        return request(
            model=self.judge_model,
            system="You look at museum photographs of artworks.",
            content=content,
            schema=JUDGE_SCHEMA,
        )

    def claim(self, item: Item, data: dict[str, Any]) -> dict[str, Any] | None:
        around = sorted({s for s in data.get("surround") or [] if s in SURROUND})
        if not CUT_AROUND & set(around) and self.banded(item):
            # Perugino, Cleveland, 2026-11-15: strips the judge missed.
            return {"around": sorted({*around, "backdrop"}), "band": True}
        if CUT_AROUND & set(around):
            return {"around": around}
        if PAPER & set(around) and self.stale(item):
            # Only paper: nothing cut, but the card offers "Pokaż bez marginesu".
            self.library.update(item.id, cut=Cut(around=around, picture=item.picture_key()))
        return None

    def photo(self, item: Item) -> Image.Image:
        """The museum's photograph of the work, whole (downloaded if need be)."""
        return load_image(self.images.museum_photo(item)).convert("RGB")

    def shape_question(self, item: Item) -> dict[str, Any]:
        """Opus asked only for the work's outline (:data:`SHAPE`)."""
        img = self.photo(item)
        img.thumbnail((SHAPE_SIDE, SHAPE_SIDE), Image.Resampling.LANCZOS)
        return request(
            model=self.critic_model,
            system="You find artworks in museum photographs.",
            content=[_block(img), {"type": "text", "text": f"{SHAPE}\n\n{facts(item)}"}],
            schema=SHAPE_SCHEMA,
            max_tokens=3000,
            effort="low",
        )

    def critic_question(self, item: Item, claim: dict[str, Any]) -> dict[str, Any]:
        if claim.get("reshape"):
            return self.shape_question(item)
        img = self.photo(item)
        img.thumbnail((PHOTO_SIDE, PHOTO_SIDE), Image.Resampling.LANCZOS)
        around = ", ".join(claim.get("around") or []) or "?"
        if item.source in OWN_SOURCES:  # his own photograph (the frame's edge asked)
            text = f"{HOME}\n\n{facts(item)}"
        else:
            text = f"{CORNERS}\n\n{facts(item)}\nSeen around it at a glance: {around}."
        if claim.get("hint"):
            # "Do sprawdzenia" → "Przytnij": what the night audit saw, in Polish.
            text += (
                f"\nA check of the catalogue noticed (in Polish): {claim['hint']} "
                "Whatever it names that is not the work (a ruler, a colour chart, a museum's "
                "label, the board or paper around it) stays outside the work's rectangle."
            )
        return request(
            model=self.critic_model,
            system="You find artworks in museum photographs.",
            content=[_block(img), _block(gridded(img)), {"type": "text", "text": text}],
            schema=CORNERS_SCHEMA,
            max_tokens=8000,
            effort="medium",
        )

    def corners(self, item: Item, data: dict[str, Any], sure: bool = True) -> dict[str, Any] | None:
        """Opus's answer as corners set on the photograph's edges: the
        work shown ("work", None for the whole photograph), a print's
        without its sheet ("plate") and the photograph's "aspect". None when
        there is nothing to cut to (or Opus is unsure, with ``sure``)."""
        if sure and data.get("confident") is not True:
            return None
        if sure and shape_of(data) in NOT_RECTANGLE:
            return None
        if read_layers(data) is None:
            return None
        return corners_in(self.photo(item), data)

    def home_corners(self, img: Image.Image) -> dict[str, Any] | None:
        """Opus asked for the work in the owner's own photograph of a work
        of his (:data:`HOME`; "Dodaj własne dzieło", Mateusz 2026-11-15):
        the corners as :meth:`corners` gives them, whatever its doubt; None
        when it found nothing to cut to. The night never asks."""
        small = img.convert("RGB")
        small.thumbnail((PHOTO_SIDE, PHOTO_SIDE), Image.Resampling.LANCZOS)
        answer = self.claude.ask(
            KIND,
            request(
                model=self.critic_model,
                system="You find artworks in photographs.",
                content=[_block(small), _block(gridded(small)), {"type": "text", "text": HOME}],
                schema=CORNERS_SCHEMA,
                max_tokens=8000,
                effort="medium",
            ),
        )
        if answer.refused or not answer.data:
            return None
        return corners_in(img, answer.data)

    def confirmed(self, item: Item, claim: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        shape = shape_of(data)
        if claim.get("reshape"):
            return {"reshape": True, "shape": shape} if shape else {}
        if claim.get("frame_edge"):
            return self.surround_found(item, data)
        if shape in NOT_RECTANGLE:
            # No strips from the pixels either: the outline is the work's.
            return {"around": list(claim.get("around") or []), "shape": shape, "whole": True}
        try:
            found = self.corners(item, data)
            if (not found or found["work"] is None) and claim.get("band"):
                found = self.strips(item, data)
                if found is not None:
                    found["shape"] = shape
        except OSError as err:
            log.info("crops: the photograph of %s: %s", item.id, err)
            return {}
        if found and "colour_chart" in (claim.get("around") or []):
            found = plate_for_chart(found)
        return {**claim, **found} if found and found["work"] is not None else {}

    def strips(self, item: Item, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """The photograph without the thin strips of backdrop along its
        sides, from the pixels (:func:`..imaging.cut.backdrop_quad`): when
        Opus was unsure of a sheet's edge that nearly meets the
        photograph's (Munch, Cleveland, 2026-11-15). Only where the strips
        agree with what Opus saw (``data``, :func:`strips_fit`): a print's
        own paper margin is as plain as a board."""
        img = self.photo(item)
        depths = strip_depths(img)
        quad = backdrop_quad(img)
        if quad is None or not worth_cutting(quad) or not strips_fit(depths, data or {}):
            return None
        return {
            "work": quad,
            "plate": None,
            "aspect": round(img.width / img.height, 5),
            "note": STRIPS_NOTE,
        }

    def write(self, item: Item, claim: dict[str, Any]) -> bool:
        """The cut Opus confirmed put on; whether the work was cut. A work
        that is no rectangle is kept whole, and so is one cut before its
        outline was asked (``reshape``): given back whole."""
        stored = self.library.get(item.id)
        if stored is None:
            return False
        if claim.get("reshape"):
            if self.unshaped(stored):
                self.reshape(stored, str(claim.get("shape") or ""))
            return False
        if claim.get("frame_edge"):
            self.surround_write(stored, claim)
            return False
        if not self.open_to_cut(stored):
            return False  # the owner's own cut: his
        if claim.get("whole"):
            self.reshape(stored, str(claim.get("shape") or ""))
            return False
        cut = Cut(
            work=claim.get("work"),
            plate=claim.get("plate"),
            around=list(claim.get("around") or []),
            aspect=float(claim.get("aspect") or 0.0),
            picture=stored.picture_key(),
            shape=str(claim.get("shape") or ""),
            at=_now(),
            **_surround_fields(claim),
        )
        self.apply(stored, cut)
        return True

    def reshape(self, item: Item, shape: str) -> Item:
        """The work's outline kept (:attr:`Cut.shape`): a rectangle's cut
        stays as it is; a work of any other outline is shown whole, the
        model's corners it had kept aside for its study's boxes. Never the
        owner's cut."""
        cut = item.cut
        if shape not in SHAPES or (cut is not None and cut.by == "owner"):
            return item
        if shape not in NOT_RECTANGLE:
            if cut is None or cut.shape == shape:
                return item
            return self.library.update(item.id, cut=cut.model_copy(update={"shape": shape})) or item
        current = cut is not None and not self.stale(item)
        undone = cut.shown() if cut is not None and current else None
        whole = Cut(
            aspect=cut.aspect if cut is not None else 0.0,
            picture=item.picture_key(),
            shape=shape,
            undone=undone,
            undone_at=cut.at if cut is not None and undone is not None else "",
            at=_now(),
        )
        log.info("crops: %s is %s, shown whole", item.id, shape)
        return self.apply(item, whole)

    def surround_found(self, item: Item, data: dict[str, Any]) -> dict[str, Any]:
        """The frame's or the passe-partout's outer edge around the work
        as it is cut now, from Opus's corners (``data``)."""
        cut = item.cut
        try:
            found = surround_in(self.photo(item), data, cut.work if cut is not None else None)
        except OSError as err:
            log.info("crops: the photograph of %s: %s", item.id, err)
            return {}
        return {
            "frame_edge": True,
            "quad": found[0] if found is not None else None,
            "kind": found[1] if found is not None else "",
        }

    def surround_write(self, item: Item, found: dict[str, Any]) -> Item:
        """The frame's edge found (:meth:`surround_found`) kept with the
        work's cut, asked for good; its pictures stay as they are."""
        cut = item.cut
        if cut is None or not self.unsurrounded(item):
            return item
        kind = str(found.get("kind") or "")
        quad = found.get("quad") if kind else None
        found_now = {
            "surround": quad,
            "surround_kind": kind if quad else "",
            "surround_asked": True,
        }
        updated = framed(cut.model_copy(update=found_now))
        log.info("crops: %s around the work: %s", item.id, kind or "nothing")
        return self.library.update(item.id, cut=updated) or item

    def surround_now(self, item: Item) -> bool:
        """A card opened on a work cut before its frame's edge was kept
        (:meth:`unsurrounded`): Opus asked for it now. Whether one was
        found."""
        claim = {"frame_edge": True, "around": list(item.cut.around) if item.cut else []}
        try:
            answer = self.claude.ask(KIND, self.critic_question(item, claim))
        except Exception as err:  # no key, the limit, a picture gone: the night's again
            log.info("crops: the frame of %s not asked now (%s)", item.id, err)
            return False
        if answer.refused or not answer.data:
            return False
        found = self.surround_found(item, answer.data)
        if not found:
            return False
        claims = self.state().get("claims") or {}
        if claims.get(item.id, {}).get("frame_edge"):
            state = self.state()
            (state.get("claims") or {}).pop(item.id, None)
            self._save(state)
        updated = self.surround_write(item, found)
        return bool(updated.cut is not None and updated.cut.framed_kind)

    # -- putting a cut on -----------------------------------------------------------

    def apply(self, item: Item, cut: Cut | None) -> Item:
        """``cut`` kept for the work and its pictures made again from it:
        the original, the thumbnail, the colours, the study's details."""
        if cut is not None and item.cut is not None and item.cut.surround_by == "owner":
            cut = cut.model_copy(update=_owners_frame(item.cut))
        cut = framed(cut.without_twin()) if cut is not None else None
        changes: dict[str, Any] = {"cut": cut}
        if item.framing:
            # His framings were set on the picture as it was shown: they
            # show the same parts of it cut anew (or whole again).
            before = item.cut_shown()
            after = cut.shown() if cut is not None and cut.picture == item.picture_key() else None
            if before != after:
                changes["framing"] = framing_moved(item.framing, before, after)
        updated = self.library.update(item.id, **changes) or item.model_copy(update=changes)
        self.images.recut(updated)
        if self.importer is not None:
            try:
                updated = self.importer.measure_again(updated)
            except OSError as err:
                log.info("colours of %s: %s", item.id, err)
        details = Path(self.images.thumbs.parent) / "details"
        for old in details.glob(f"{item.file_stem}-*.jpg"):
            old.unlink(missing_ok=True)
        log.info("cut of %s: %s", item.id, "whole" if cut is None or not cut.shown() else cut.by)
        return updated

    def set_by_owner(
        self,
        item: Item,
        corners: Quad | None = None,
        paper: bool | None = None,
        frame: Quad | None = None,
    ) -> Item:
        """The owner's corners (of the work as shown, with its paper or
        without), or his "Pokaż z marginesem / bez marginesu". Without the sheet when
        no plate is known yet: Opus is asked for it now. ``frame``: the
        outer edge of the frame or passe-partout as he set it (the card's
        "W ramie"); alone, the work's pictures stay as they are."""
        alone = frame is not None and corners is None and paper is None
        if alone and item.cut is not None and item.cut.shown() is not None and not self.stale(item):
            kind = item.cut.surround_kind or "frame"
            mine = {"surround": frame, "surround_kind": kind, "surround_by": "owner"}
            cut = framed(item.cut.model_copy(update={**mine, "surround_asked": True}))
            log.info("crops: %s frame's edge set by the owner", item.id)
            return self.library.update(item.id, cut=cut) or item
        old = item.cut if item.cut is not None and not self.stale(item) else None
        with Image.open(self.images.museum_photo(item, urgent=True)) as img:
            aspect = round(img.width / img.height, 5)
        cut = (old or Cut()).model_copy(
            update={"by": "owner", "aspect": aspect, "picture": item.picture_key(), "at": _now()}
        )
        if paper is not None:
            cut.paper = paper
            if not paper and cut.plate is None:
                found = self.ask_corners(item, sure=False)
                if found is not None:
                    cut.plate = found["plate"] or found["work"]
                    if cut.work is None and found["plate"] is not None:
                        cut.work = found["work"]
        if corners is not None:
            if not cut.paper and cut.plate is not None:
                cut.plate = corners
            else:
                cut.work = corners
        if frame is not None:
            kind = cut.surround_kind or "frame"
            cut = cut.model_copy(
                update={
                    "surround": frame,
                    "surround_kind": kind,
                    "surround_by": "owner",
                    "surround_asked": True,
                }
            )
        return self.apply(item, cut)

    def give_up(self, item: Item) -> Item:
        """ "Przywróć zdjęcie muzeum": the photograph whole, for good."""
        old = item.cut or Cut()
        cut = Cut(
            around=old.around,
            aspect=old.aspect,
            picture=item.picture_key(),
            by="owner",
            at=_now(),
        )
        self.forget_written(item.id)
        return self.apply(item, cut)

    def cut_now(self, item: Item, hint: str = "") -> Item | None:
        """ "Do sprawdzenia" → "Przytnij" (Mateusz 2026-11-15): Opus asked for
        the work's corners now, told what the night audit saw (``hint``: a
        ruler, a colour chart, a cut edge), and the cut kept as the owner's,
        never changed by itself again. None when nothing is found to cut."""
        answer = self.claude.ask(KIND, self.critic_question(item, {"around": [], "hint": hint}))
        if answer.refused or not answer.data:
            return None
        found = self.corners(item, answer.data, sure=False)
        if found is None or found["work"] is None:
            return None
        cut = Cut(
            work=found["work"],
            plate=found["plate"],
            around=list(item.cut.around) if item.cut is not None else [],
            aspect=float(found["aspect"]),
            picture=item.picture_key(),
            shape=str(found.get("shape") or ""),
            by="owner",
            at=_now(),
            **_surround_fields(found),
        )
        self.forget_written(item.id)
        return self.apply(item, cut)

    def ask_corners(self, item: Item, sure: bool = True) -> dict[str, Any] | None:
        """Opus asked now (the card, the owner's switch)."""
        answer = self.claude.ask(KIND, self.critic_question(item, {"around": []}))
        if answer.refused or not answer.data:
            return None
        return self.corners(item, answer.data, sure=sure)

    # -- when a card opens ----------------------------------------------------------

    def soon(self, item: Item) -> Future[bool]:
        """The work looked at in the background (:meth:`now`), once at a
        time: whether its cut changed."""
        self._setup()
        assert self._pool is not None
        with self._guard:
            running = self._running.get(item.id)
            if running is not None and not running.done():
                return running
            future = self._pool.submit(self.now, item)
            self._running[item.id] = future
            if len(self._running) > 200:
                self._running = {k: f for k, f in self._running.items() if not f.done()}
            return future

    def reshape_now(self, item: Item) -> bool:
        """A card opened on a work cut before its outline was asked: asked
        now (:meth:`shape_question`). Whether the cut changed (given back
        whole)."""
        try:
            answer = self.claude.ask(KIND, self.shape_question(item))
        except Exception as err:  # no key, the limit, a picture gone: the night's again
            log.info("crops: the outline of %s not asked now (%s)", item.id, err)
            return False
        shape = "" if answer.refused else shape_of(answer.data or {})
        if not shape:
            return False
        before = item.cut_shown()
        return self.reshape(item, shape).cut_shown() != before

    def before_page(self, item: Item) -> bool:
        """:meth:`now` before a page is written about the work (its study,
        the day's), waited for :data:`PAGE_WAIT` at most: a card that
        asked meanwhile shares the one look. Whether it was cut; a work
        not in the library is not looked at (its cut could not be kept)."""
        if self.library.get(item.id) is None:
            return False
        return self.soon(item).result(timeout=PAGE_WAIT)

    def now(self, item: Item) -> bool:
        """A card opened: a work not looked at yet (or whose picture changed
        since) is looked at now, the judge and then Opus, as at night.
        Whether it was cut."""
        stored = self.library.get(item.id) or item
        if not self.config.enabled(self.switch):
            return False
        if self.unsurrounded(stored):
            # "W ramie" on the card (the app reads the work again)
            self.surround_now(stored)
            stored = self.library.get(item.id) or stored
        if not self.wanted(stored):
            return False
        if self.unshaped(stored):
            return self.reshape_now(stored)
        if not self.open_to_cut(stored):
            return False
        asked = self.asked().get(stored.id)
        again = asked is not None and asked.get("p", "") == stored.picture_key()
        if again and asked is not None and asked.get("critic"):
            # Opus found the work's edges and nothing was cut: the owner's
            # framing stopped it before 2026-11-15 (Wyspiański's
            # „Macierzyństwo” in its thin wooden frame). Asked anew.
            asked, again = None, False
        if again and asked is not None and int(asked.get("q") or 1) < QUESTION:
            asked, again = None, False  # left uncut by an older question
        if asked is not None and again and (asked.get("band") == BAND or not self.banded(stored)):
            log.info("crops: %s looked at %s, nothing to cut", stored.id, asked.get("at"))
            return False  # looked at, and no thin backdrop the judge missed then
        try:
            if again:  # Opus straight away: the judge saw nothing (or only paper) before
                around = stored.cut.around if stored.cut is not None else []
                claim: dict[str, Any] | None = {
                    "around": sorted({*around, "backdrop"}),
                    "band": True,
                }
            else:
                judged = self.claude.ask(KIND, self.question(stored))
                claim = None if judged.refused else self.claim(stored, judged.data or {})
                log.info(
                    "crops: %s judged: %s",
                    stored.id,
                    "refused" if judged.refused else (judged.data or {}).get("surround"),
                )
            found = None
            if claim:
                answer = self.claude.ask(KIND, self.critic_question(stored, claim))
                if not answer.refused:
                    found = self.confirmed(stored, claim, answer.data or {}) or None
                data = answer.data or {}
                log.info(
                    "crops: %s by Opus: %s (sure %s, %s)",
                    stored.id,
                    "refused" if answer.refused else ("cut" if found else "nothing cut"),
                    data.get("confident"),
                    str(data.get("note") or "")[:120],
                )
        except Exception as err:  # no key, the limit, a picture gone: the night's again
            log.info("crops: %s not looked at now (%s)", stored.id, err)
            return False
        return self._settle_now(stored, found)

    def claims_waiting(self) -> list[str]:
        """The works the judge found something around that wait for Opus
        and are in no batch, the works cared about first (a run on demand,
        ``frame_server.on_demand``)."""
        state = self.state()
        ordered = set(((state.get("order") or {}).get("ids") or {}).values())
        claims = state.get("claims") or {}
        ids = [k for k, c in claims.items() if not _aside(c or {}) and k not in ordered]
        cared = self.cared()
        return sorted(ids, key=lambda i: cared.get(i, REST))

    def claim_now(self, item_id: str) -> bool | None:
        """A work the judge found something around, asked of Opus now
        rather than in the night's batch: whether it was cut; None when its
        claim is gone (asked meanwhile). What the ask raises (no key, the
        limit) is the caller's."""
        state = self.state()
        claim = (state.get("claims") or {}).get(item_id)
        ordered = set(((state.get("order") or {}).get("ids") or {}).values())
        stored = self.library.get(item_id)
        if not claim or _aside(claim) or item_id in ordered or stored is None:
            return None
        answer = self.claude.ask(KIND, self.critic_question(stored, claim))
        found = (
            None if answer.refused else (self.confirmed(stored, claim, answer.data or {}) or None)
        )
        log.info("crops: %s by Opus now: %s", stored.id, "cut" if found else "nothing cut")
        return self._settle_now(stored, found)

    def _settle_now(self, stored: Item, found: dict[str, Any] | None) -> bool:
        """What Opus found about a work asked now kept, as the night keeps
        its answers: whether it was cut."""
        state = self.state()
        asked_all = state.get("asked") or {}
        asked_all[stored.id] = {
            "v": self.version,
            "at": _now()[:10],
            "p": stored.picture_key(),
            "critic": bool(found and not found.get("whole")),
            "band": BAND,
            "q": QUESTION,
        }
        state["asked"] = asked_all
        (state.get("claims") or {}).pop(stored.id, None)
        self._save(state)
        if found and self.write(stored, found):
            state = self.state()
            state["written"] = [{"id": stored.id, "at": _now(), **found}, *self.written()]
            self._save(state)
            return True
        return False
