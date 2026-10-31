"""The "Rytm" take asked alone of pages written before it was part of the
question (the work of the day's pages and the studies, ``ai.daily``).

Those pages are kept for good (``DailyJob.fresh``), so a new prompt never
reaches them. This job asks Opus only for the rhythms of the work's picture,
a short question next to writing the page again, and puts the take in place
of a third take of another kind ("Światło", which the old prompt allowed).
A page without rhythms keeps its two takes; either way it is asked once.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..library.markup import strip_markup
from ..library.models import Note
from .client import OPUS, request
from .daily import (
    _POINT,
    GRIDS,
    MAX_MARKS,
    RHYTHM,
    RHYTHM_ASKED,
    View,
    _composition,
    _dicts,
    _list,
    _object,
    _str,
    _view,
    has_rhythm,
    picture_block,
    takes,
)
from .daily import (
    KIND as DAILY,
)
from .jobs import NoteJob, Usage, text_hash
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import Item

KIND = "rhythm"
PROMPT_VERSION = "rhythm-1"
#: The pages a rhythm is asked for.
PAGES = (DAILY, STUDY)
#: How long the list of pages wanting a rhythm is kept between looks.
PAGES_SECONDS = 30.0
TYPICAL = Usage(input_tokens=2500, cache_read_input_tokens=800, output_tokens=1500)

SYSTEM = (
    """Rysujesz ołówkiem na obrazie jedno ujęcie analizy kompozycji do strony o dziele \
w aplikacji domowej ramki: „Rytm”. Naturalna, poprawna polszczyzna, jak w dobrym polskim \
muzeum, bez superlatywów i bez zwrotów do czytelnika. Ujęcia „Spojrzenie” i „Geometria” są \
już narysowane; nie powtarzaj ich.

"""
    + RHYTHM
    + """ Bez rytmów "views" to pusta lista. Pokazuj tylko to, co naprawdę widać, niczego nie \
naginaj.

Ujęcie (najwyżej jedno): "title" „Rytm”, "grid" "none", "text" (dwa-trzy zdania, co \
się powtarza i jak to prowadzi oko) i "marks": 1–5 śladów "rhythm", każdy z "points" \
(2–12 punktów, po jednym na każdym powtórzeniu, po kolei; x i y to ułamki szerokości i \
wysokości obrazu od lewego górnego rogu, 0–1, dokładnie na powtarzanej rzeczy), "title" \
(1–3 słowa, podpis przy śladzie) i "text" (najwyżej 45 znaków, dopisek pod podpisem)."""
)

SCHEMA = _object(
    views=_list(
        _object(
            title=_str(),
            grid={"type": "string", "enum": list(GRIDS)},
            text=_str(),
            marks=_list(
                _object(
                    shape={"type": "string", "enum": ["rhythm"]},
                    points=_list(_POINT),
                    title=_str(),
                    text=_str(),
                )
            ),
        )
    )
)


def wants_rhythm(note: Note | None) -> bool:
    """A written page whose question did not ask for "Rytm" and that has no
    rhythm in it."""
    if note is None or "teaser" not in note.data or note.data.get(RHYTHM_ASKED):
        return False
    views = _dicts((note.data.get("composition") or {}).get("views"))
    found = [v for v in map(_view, views) if v is not None]
    return bool(found) and not any(has_rhythm(v) for v in found)


def rhythm(data: dict[str, Any]) -> View | None:
    """The answer's take, with its rhythms only, as "Rytm"."""
    for view in (v for v in map(_view, _dicts(data.get("views"))) if v is not None):
        marks = [m for m in view.marks if m.shape == "rhythm"][:MAX_MARKS]
        if marks:
            return view.model_copy(update={"title": "Rytm", "grid": "none", "marks": marks})
    return None


def request_text(item: Item, page: dict[str, Any]) -> str:
    lines = [
        "DZIEŁO",
        f"Tytuł: {page.get('title') or strip_markup(item.title)}",
        f"Autor: {item.artist}",
        f"Data: {item.date_text}",
    ]
    views = _dicts((page.get("composition") or {}).get("views"))
    for view in [v for v in map(_view, views) if v is not None][:2]:
        lines += ["", f"UJĘCIE „{view.title}” (już narysowane)", view.text]
    return "\n".join(lines)


class RhythmJob(NoteJob):
    kind = KIND
    model = OPUS
    prompt_version = PROMPT_VERSION
    typical = TYPICAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pages: tuple[float, set[str]] = (0.0, set())

    def waiting(self) -> set[str]:
        """The works with a page wanting a rhythm (looked up again every
        :data:`PAGES_SECONDS`: the background asks about every item)."""
        when, ids = self._pages
        if time.monotonic() - when > PAGES_SECONDS:
            ids = {
                item_id
                for kind in PAGES
                for item_id, note in self.library.notes(kind).items()
                if wants_rhythm(note)
            }
            self._pages = (time.monotonic(), ids)
        return ids

    def wanted(self, item: Item) -> bool:
        return item.id in self.waiting()

    def source_hash(self, item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def _page(self, item: Item) -> dict[str, Any]:
        for kind in PAGES:
            note = self.library.note(item.id, kind)
            if wants_rhythm(note):
                assert note is not None
                return note.data
        return {}

    def params(self, item: Item) -> dict[str, Any]:
        text = {"type": "text", "text": request_text(item, self._page(item))}
        return request(
            model=OPUS,
            system=SYSTEM,
            content=[picture_block(self.images, item), text],
            schema=SCHEMA,
            max_tokens=8000,
            effort="medium",
        )

    def apply(self, item: Item, note: Note) -> None:
        """Puts the take in each of the work's pages wanting it, in place of
        a third take of another kind; the pages stay as fresh as they were."""
        take = rhythm(note.data)
        for kind in PAGES:
            page = self.library.note(item.id, kind)
            if not wants_rhythm(page):
                continue
            assert page is not None
            views = _dicts((page.data.get("composition") or {}).get("views"))
            kept = takes([v for v in map(_view, views) if v is not None])
            if take is not None:
                kept = [*kept[:2], take]
            data = {**page.data, "composition": _composition(kept).model_dump(), RHYTHM_ASKED: True}
            self.library.save_note(page.model_copy(update={"data": data}))
        self._pages = (0.0, set())
