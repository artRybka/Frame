"""Whether a pale sheet is worth a study ("Studium dzieła"), asked of
Haiku with the picture (Mateusz 2026-11-13).

The words of its museum and the way its marks lie (``library.paper``) tell
the clear cases: a sketchbook's page, a sheet with one small sketch in a
corner, notes scattered thinly. Between them a pale drawing may be a
finished portrait by Ingres or a sheet of working studies; the curator of
the study of the day (``ai.study_pick``) judges such works by their
picture, and so does this question, one work at a time, for a work's
card: under a tenth of a cent. A poor photograph is no reason here: a
small picture is drawn again by the creative restorer before its study.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .client import HAIKU, image_block, request
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import ImageCache, Item
    from ..library.paper import Sheet
    from .client import Claude

KIND = "study_fit"
MODEL = HAIKU

SYSTEM = """\
A Polish home art frame writes a long illustrated page about a work on the \
owner's request ("Studium dzieła"): its story, its composition drawn over \
the picture, its details cut out and enlarged. You decide whether the work \
shown is worth such a page.

"fit" is true for a finished work worth a quarter of an hour of looking, \
whole and readable: a painting, a finished drawing (a portrait drawing by \
Ingres, a landscape drawing worked over the whole sheet), a watercolour, a \
print, an oil sketch or study that stands as a complete, striking image by \
itself.
"fit" is false for:
- a page of a sketchbook, a working sheet of separate studies or quick \
sketches, notes or colour notes written over a drawing;
- a pale or nearly empty sheet on which little can be seen: one small \
sketch on a large empty page;
- a design, pattern, plan, map, diagram or technical drawing;
- a document, a page of text, a letter;
- a fragment whose subject cannot be read.
Judge by the picture: museums' titles and types can mislead. The photograph's \
own quality (small, soft) is no reason either way. "what": what the picture \
shows, at most 12 words; "why": one short Polish phrase saying why it is or is \
not worth a page (e.g. "kartka roboczych szkiców z notatkami")."""

SCHEMA = _object(what=_str(), fit={"type": "boolean"}, why=_str())


@dataclass(frozen=True)
class Fit:
    """The answer: worth a study or not, and why (in Polish)."""

    fit: bool
    why: str
    usd: float = 0.0


def _label(item: Item, sheet: Sheet | None) -> str:
    lines = [item.title or "Untitled"]
    who = ", ".join(p for p in (item.artist, item.date_text or str(item.year or "")) if p)
    if who:
        lines.append(who)
    kind = "; ".join(p for p in (item.classification, item.medium) if p)
    if kind:
        lines.append(kind[:200])
    if sheet is not None:
        lines.append(f"(a light sheet: about {sheet.ink:.1%} of it is marked)")
    if item.description:
        lines.append(item.description[:300])
    return "\n".join(lines)


def params(images: ImageCache, item: Item, sheet: Sheet | None) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": _label(item, sheet)},
        image_block(images, item),
    ]
    return request(model=MODEL, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=1500)


def read(data: dict[str, Any] | None) -> Fit:
    if not data or not isinstance(data.get("fit"), bool):
        raise ValueError("no answer")
    why = str(data.get("why") or "").strip()[:200]
    return Fit(bool(data["fit"]), why)


def ask(claude: Claude, images: ImageCache, item: Item, sheet: Sheet | None) -> Fit:
    """Asks Haiku about ``item``; raises when it cannot answer."""
    answer = claude.ask(KIND, params(images, item, sheet))
    fit = read(answer.data)
    return Fit(fit.fit, fit.why, answer.cost_usd)
