"""What the tidying of copies changed, for the owner to look over (Mateusz
2026-11-11: "potrzebne są jakieś podsumowania wykonanych prac, szczególnie
przy usuniętych duplikatach, przynajmniej tych, gdzie były wątpliwości").

Each change the pictures (``twins``) or the judge (``ai.twins_judge``) wrote:
a picture made a copy of another work's picture (``copy``), a detail of it
(``detail``) or a photograph of it on a wall (``scene``), how it was settled
(``by``: ``pictures``, ``hash`` or ``judge``, the last the doubtful ones the
pictures could not settle) and, for the judge, what it and its critic said.
Nothing is deleted by these changes: a copy stays in the library and the
best copy of the work is shown. The owner can take a change back ("To nie to
samo", :meth:`Twins.separate`): the pair is then kept apart for good.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .repo import Library

KEY = "tidy_log"
#: Changes kept, the newest.
KEEP = 2000
#: How a change was settled; the judge's were doubtful.
BY = ("pictures", "hash", "judge")
RELATIONS = ("copy", "detail", "scene")


class TidyLog:
    def __init__(self, library: Library) -> None:
        self.library = library
        self._lock = threading.Lock()

    def add(self, changes: list[dict[str, Any]]) -> None:
        """``changes``: each ``{"a", "b", "relation", "by"}`` and maybe
        ``"why"``, ``"critic"``: ``a`` is the copy, the detail or the
        photograph, ``b`` the work it belongs to."""
        if not changes:
            return
        at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            kept = self.entries(newest_first=False)
            for change in changes:
                kept.append({"at": at, **change})
            self.library.set_state(KEY, kept[-KEEP:])

    def entries(self, newest_first: bool = True) -> list[dict[str, Any]]:
        stored = self.library.get_state(KEY, []) or []
        kept = [e for e in stored if isinstance(e, dict)]
        return kept[::-1] if newest_first else kept

    def drop(self, a: str, b: str) -> None:
        """The changes between ``a`` and ``b`` off the list."""
        pair = {a, b}
        with self._lock:
            kept = [e for e in self.entries(newest_first=False) if {e.get("a"), e.get("b")} != pair]
            self.library.set_state(KEY, kept)

    def since(self, at: str) -> dict[str, int]:
        """How many changes of each kind since ``at`` (ISO): ``copy``,
        ``detail``, ``scene`` and ``judge`` (the judge's, of any kind)."""
        counts = dict.fromkeys((*RELATIONS, "judge"), 0)
        for entry in self.entries(newest_first=False):
            if str(entry.get("at") or "") < at:
                continue
            relation = str(entry.get("relation") or "")
            if relation in counts:
                counts[relation] += 1
            if entry.get("by") == "judge":
                counts["judge"] += 1
        return counts
