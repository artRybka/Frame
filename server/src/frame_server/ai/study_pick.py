"""The curator of the study of the day: which of the day's best works is
worth a whole page (Mateusz 2026-11-11: "Studium bazgrołów ze szkicowania
to nie jest najlepszy pomysł").

The rules of :mod:`frame_server.daily` rank the catalogue's works for the
day by season, anniversaries and taste, without a look at the picture: a
pale page of Frederic Church's sketchbook, notes of passers-by scattered
over a sheet, became a study. Neither its words nor its pixels give such a
page away (a finished portrait drawing by Ingres is as pale), so the
rules' shortlist goes to Sonnet, pictures and all: it sets aside what is no
finished work worth a page (sketches, notes, near-empty sheets, fragments,
documents) or what only a poor photograph shows, and chooses the one with
most to see and tell, the sharper photograph ahead among works as rich. One question a
day, about 0.02 USD; the work it sets aside is never shortlisted again.
Without a key, with the study of the day's switch off or when the answer
fails, the rules' first work stands, pale sheets and sketches put last.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .client import SONNET, image_block, request
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import ImageCache, Item
    from .client import Claude

log = logging.getLogger(__name__)

KIND = "study_pick"
MODEL = SONNET

SYSTEM = """\
You choose the work for "Studium dnia" (the study of the day) of a Polish home \
art frame. Each day one work of its catalogue gets a long illustrated page: \
its story, its composition drawn over the picture, its details cut out and \
enlarged, its colours. Rules have made today's shortlist, in order of \
preference (season, anniversaries, the owner's taste). You get each work's \
picture and what its museum says.

First judge every work. "fit" is true only for a finished work worth a quarter \
of an hour of looking, whole and readable in the picture: a painting, a \
finished drawing, watercolour or print, an illuminated page, an object made \
as art. "fit" is false for:
- a working sketch, a page of a sketchbook, studies or notes scattered over a \
sheet, colour notes written on a drawing;
- a pale or nearly empty sheet on which little can be seen;
- a fragment or damaged remains whose subject cannot be read;
- a document, a page of text, a letter, a map, a pattern or ornament design, a \
technical or scientific drawing, a minor everyday object;
- a poor photograph of the work: blurred, faded or with a strong colour cast, \
black and white although the work is in colour, or showing much besides the \
work (a wall, a stand, a colour chart or scale bar, glare, the work cut off).
A preparatory drawing or oil sketch may fit when it stands as a complete, \
striking image by itself (a finished portrait drawing by Ingres, a vivid oil \
sketch of a sunset); scattered notes never do. Museums' titles and types can \
mislead: judge by the picture. "what": what the picture shows, at most 15 \
words; "why": at most 15 words; "photo": true when the work itself would fit \
and only its photograph does not (another photograph may come later).

Then choose one fit work for today: the one with most to see and to tell \
(composition, story, detail, colour, technique), preferring an earlier one \
when they are about equal. The page shows the picture across a 2560-pixel \
screen and cuts details out of it, so the photograph counts too: among works \
about as rich, prefer the sharper, truer photograph; one shorter than 2000 \
pixels shows its details blurred. "choice" is its number; "reason" one Polish \
sentence why it. When none fits, "choice" is 0 and "reason" says why."""

SCHEMA = _object(
    works={
        "type": "array",
        "items": _object(
            n={"type": "integer"},
            what=_str(),
            fit={"type": "boolean"},
            photo={"type": "boolean"},
            why=_str(),
        ),
    },
    choice={"type": "integer"},
    reason=_str(),
)


@dataclass
class Choice:
    """The curator's answer: the work chosen (None: no work fits), why,
    and the works it set aside with what it saw in each."""

    item: Item | None
    reason: str
    unfit: dict[str, str] = field(default_factory=dict)
    #: Works set aside only for their photograph: the copy shown (its id),
    #: by work; another copy found later brings the work back.
    poor_copy: dict[str, str] = field(default_factory=dict)
    usd: float = 0.0


def _label(n: int, item: Item, ink: float | None) -> str:
    lines = [f"{n}. {item.title or 'Untitled'}"]
    who = ", ".join(p for p in (item.artist, item.date_text or str(item.year or "")) if p)
    if who:
        lines.append(who)
    kind = "; ".join(p for p in (item.classification, item.medium) if p)
    if kind:
        lines.append(kind[:200])
    if item.museum:
        lines.append(item.museum)
    size = _photograph(item)
    if size:
        lines.append(size)
    if ink is not None and ink < 1.0:
        lines.append(f"(a light sheet: about {ink:.0%} of it is marked)")
    if item.description:
        lines.append(item.description[:300])
    return "\n".join(lines)


def _photograph(item: Item) -> str:
    """The size of the photograph the page is made from, when known."""
    copy = item.sharper
    if copy is not None:
        where = f" (a sharper copy from {copy.museum or copy.source})"
        return f"Photograph: {copy.width} × {copy.height} px{where}"
    if item.width and item.height:
        return f"Photograph: {item.width} × {item.height} px"
    return ""


def params(images: ImageCache, shortlist: list[tuple[Item, float | None]]) -> dict[str, Any]:
    """The question about ``shortlist`` (works with their ``ink_share``,
    None when unknown); a work whose picture cannot be had is left out."""
    content: list[dict[str, Any]] = []
    for n, (item, ink) in enumerate(shortlist, 1):
        content.append({"type": "text", "text": _label(n, item, ink)})
        content.append(image_block(images, item))
    return request(model=MODEL, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=6000)


def copy_key(item: Item) -> str:
    """Which copy of the work is shown: a sharper copy's id, "" for its own."""
    return item.sharper.item_id if item.sharper is not None else ""


def read(data: dict[str, Any] | None, shortlist: list[Item]) -> Choice:
    """The work chosen, the reason and the works set aside (by id); the
    chosen work is never one set aside."""
    if not data:
        raise ValueError("no answer")
    unfit: dict[str, str] = {}
    poor: dict[str, str] = {}
    for work in data.get("works") or []:
        n = work.get("n")
        if isinstance(n, int) and 1 <= n <= len(shortlist) and work.get("fit") is False:
            item = shortlist[n - 1]
            if work.get("photo") is True:
                poor[item.id] = copy_key(item)
                continue
            seen = " · ".join(str(p).strip() for p in (work.get("what"), work.get("why")) if p)
            unfit[item.id] = seen[:300]
    choice = data.get("choice")
    reason = str(data.get("reason") or "").strip()
    if not isinstance(choice, int) or not 0 <= choice <= len(shortlist):
        raise ValueError(f"choice {choice!r} not on the list")
    chosen = shortlist[choice - 1] if choice else None
    if chosen is not None and (chosen.id in unfit or chosen.id in poor):
        raise ValueError(f"choice {choice} set aside")
    return Choice(chosen, reason, unfit, poor)


def choose(
    claude: Claude, images: ImageCache, shortlist: list[tuple[Item, float | None]]
) -> Choice:
    """Asks the curator about ``shortlist``; raises when it cannot answer."""
    seen: list[tuple[Item, float | None]] = []
    for item, ink in shortlist:
        try:
            images.ensure_thumb(item)
        except Exception as err:  # no picture: nothing to judge by
            log.info("study of the day: %s left off the shortlist (%s)", item.id, err)
            continue
        seen.append((item, ink))
    if not seen:
        raise ValueError("no pictures")
    answer = claude.ask(KIND, params(images, seen))
    choice = read(answer.data, [item for item, _ in seen])
    choice.usd = answer.cost_usd
    return choice
