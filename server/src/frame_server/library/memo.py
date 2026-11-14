"""What is worked out of a work once and kept for as long as that very
record lives.

The catalogue is looked through whole for a search, a count, a card of
Odkrywaj: for each of its 117 000 works the same was worked out again each
time, the reasons it is no picture (``verdict.whys``) and its texts without
accents (``search_index.folded_text``); half of a search's time and more
(the audit of 2026-11-14). A work's record is never changed where it
stands: the library puts a new one in its place (``model_copy``), and that
one is asked anew. So an answer is kept by the record itself, not by its
id, and goes when the record does.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import Any

#: Every memo there is: a record changed in place is forgotten by them all.
_ALL: list[PerItem[Any]] = []


class _Kept[T](weakref.ref[Any]):
    """A record held weakly, with what was worked out of it (one object a
    record and memo: there are hundreds of thousands)."""

    __slots__ = ("answer", "key")

    answer: T
    key: int

    def __new__(cls, item: Any, gone: Callable[[_Kept[T]], None], answer: T) -> _Kept[T]:
        return super().__new__(cls, item, gone)

    def __init__(self, item: Any, gone: Callable[[_Kept[T]], None], answer: T) -> None:
        super().__init__(item, gone)  # type: ignore[call-arg]  # typeshed: __new__ only
        self.key = id(item)
        self.answer = answer


class PerItem[T]:
    """``work(item)``, worked out once for each record.

    The record is held weakly: a memo keeps no work in memory that the
    library has let go (a museum's answer shown once, a record replaced)."""

    def __init__(self, work: Callable[[Any], T]) -> None:
        self._work = work
        self._kept: dict[int, _Kept[T]] = {}
        self._gone = self._forget  # one bound method for every record
        _ALL.append(self)

    def __call__(self, item: Any) -> T:
        kept = self._kept.get(id(item))
        if kept is not None and kept() is item:
            return kept.answer
        answer = self._work(item)
        self._kept[id(item)] = _Kept(item, self._gone, answer)
        return answer

    def _forget(self, kept: _Kept[T]) -> None:
        # Only its own: the number may already be another record's.
        if self._kept.get(kept.key) is kept:
            self._kept.pop(kept.key, None)

    def forget(self, item: Any) -> None:
        kept = self._kept.get(id(item))
        if kept is not None and kept() is item:
            self._kept.pop(id(item), None)

    def __len__(self) -> int:
        return len(self._kept)


def changed(item: Any) -> None:
    """``item`` was changed where it stands: what was kept of it is stale."""
    for memo in _ALL:
        memo.forget(item)
