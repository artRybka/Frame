"""The pen sketches of pages drawn by an earlier pen, drawn again.

The sheet an analysis of composition is drawn on has a few strokes of a
pen over its stains (``ai.pen``). When the pen learns to draw better
(:data:`pen.ROUND`), the pages that have their analysis keep it and get the
sketch alone anew: one question to Sonnet a page, nobody waiting, so asked
at night through the Batch API for half the price (about a cent a page;
Mateusz 2026-11-12 08:15, of work nobody waits for: "A możemy je dać w
pakiecie? Tzn wolniej ale taniej?"). A page whose whole analysis is about
to be made again (``ComposeJob``) gets the new pen with it and is not asked
about here.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from . import pen
from .check import CHECK_SIDE, page_views
from .client import SONNET
from .composition import PAGES, PAGES_SECONDS, VERSIONS, ComposeJob, cropped
from .daily import KIND as DAILY
from .daily import Box, Stroke, View, _view, picture
from .jobs import NoteJob, Usage, text_hash

if TYPE_CHECKING:
    from ..library import Item, Note

log = logging.getLogger(__name__)

KIND = "pen"


def wants(note: Note | None) -> bool:
    """A page with an analysis whose sketch an earlier pen drew (or none)."""
    if note is None or note.data.get(pen.PEN_KEY, 1) >= pen.ROUND:
        return False
    return bool(page_views(note.data))


def _drawn(composition: Any, field: Box | None, sketch: list[dict[str, Any]]) -> Any:
    """A composition with the sketch put in its takes of this field."""
    if not isinstance(composition, dict) or not isinstance(composition.get("views"), list):
        return composition

    def same(raw: Any) -> bool:
        view = _view(raw) if isinstance(raw, dict) else None
        return view is not None and view.field == field

    views = [{**v, "sketch": sketch} if same(v) else v for v in composition["views"]]
    return {**composition, "views": views}


def redrawn(data: dict[str, Any], strokes: list[Stroke] | None) -> dict[str, Any]:
    """A page with the sketch of its shown take drawn anew, also in the
    versions it keeps of the same field (the sketch is of the picture, not
    of the analysis); marked done even when nothing usable came (the sketch
    it had stays)."""
    out = {**data, pen.PEN_KEY: pen.ROUND}
    shown = page_views(data)
    if strokes is None or not shown:
        return out
    field = shown[0].field
    sketch = [s.model_dump() for s in strokes]
    out["composition"] = _drawn(data.get("composition"), field, sketch)
    kept = data.get(VERSIONS)
    if isinstance(kept, list):
        out[VERSIONS] = [
            {**v, "composition": _drawn(v.get("composition"), field, sketch)}
            if isinstance(v, dict)
            else v
            for v in kept
        ]
    return out


class PenJob(NoteJob):
    """The sketch of a page that has its analysis, by this pen."""

    kind = KIND
    model = SONNET
    prompt_version = f"pen-{pen.ROUND}"
    #: The picture and the instruction in, some twenty strokes and a little
    #: thought out (about 0.035 USD at once, half of it at night).
    typical = Usage(input_tokens=2400, cache_read_input_tokens=0, output_tokens=3000)
    night = True

    def __init__(self, compose: ComposeJob) -> None:
        super().__init__(compose.library, compose.images, compose.config)
        self.compose = compose
        self._pages: tuple[float, set[str]] = (0.0, set())

    def enabled(self) -> bool:
        """With the pages themselves ("Studium dnia" on)."""
        return self.config.enabled(DAILY)

    def waiting(self) -> set[str]:
        when, ids = self._pages
        if time.monotonic() - when > PAGES_SECONDS:
            ids = {
                item_id
                for kind in PAGES
                for item_id, note in self.library.notes(kind).items()
                if wants(note)
            } - self.compose.waiting()
            self._pages = (time.monotonic(), ids)
        return ids

    def wanted(self, item: Item) -> bool:
        return item.id in self.waiting()

    def in_library(self, item: Item) -> bool:
        """Never asked at once (a card opened, "describe the library"):
        nobody waits for it."""
        return False

    def _view(self, item_id: str) -> View | None:
        for kind in PAGES:
            page = self.library.note(item_id, kind)
            shown = page_views(page.data) if page is not None else []
            if shown:
                return shown[0]
        return None

    def _picture(self, item: Item, view: View) -> Any:
        img = picture(self.images, item, CHECK_SIDE)
        return cropped(img, view.field) if view.field is not None else img

    def source_hash(self, item: Item) -> str:
        view = self._view(item.id)
        field = view.field.model_dump_json() if view is not None and view.field else ""
        return text_hash(item.thumb_url, field)

    def params(self, item: Item) -> dict[str, Any]:
        view = self._view(item.id)
        if view is None:
            raise LookupError(f"no page of {item.id} has an analysis")
        return pen.question(self._picture(item, view))

    def apply(self, item: Item, note: Note) -> None:
        view = self._view(item.id)
        strokes = None
        if view is not None and "szkic" in note.data:
            try:
                strokes = pen.strokes(note.data, self._picture(item, view).size)
            except Exception as err:  # the picture cannot be had now: the old sketch stays
                log.warning("pen sketch of %s not put in: %s", item.id, err)
        for kind in PAGES:
            page = self.library.note(item.id, kind)
            if page is not None and wants(page):
                data = redrawn(page.data, strokes)
                self.library.save_note(page.model_copy(update={"data": data}))
        self._pages = (0.0, set())
        log.info("pen sketch of %s: %s strokes", item.id, len(strokes) if strokes else "no")
