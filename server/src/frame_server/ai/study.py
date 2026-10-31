"""A study of any work, written by Claude when the owner asks for it on the
work's card ("Przygotuj studium dzieła"): the page the work of the day
gets (``ai.daily``), without "why today".

Asked only for the works the owner picked, and kept: opening it again costs
nothing, and a new prompt does not throw a written study away.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .daily import PROMPT_VERSION, SYSTEM, DailyJob
from .jobs import text_hash

if TYPE_CHECKING:
    from ..library import Item
    from ..library.models import Note

KIND = "study"

SYSTEM_STUDY = (
    SYSTEM
    + """

Tym razem to nie „Dzieło dnia”, tylko studium jednego dzieła, o które poprosił właściciel \
ramki. "why_today" zostaw pusty i nie wiąż tekstu z dzisiejszą datą. "teaser" to jedno \
zdanie zapowiedzi studium."""
)


class StudyJob(DailyJob):
    kind = KIND
    prompt_version = f"study-1/{PROMPT_VERSION}"
    system = SYSTEM_STUDY

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        #: Whether the owner asked for a study of the work; set by ``frame_server.study``.
        self.requested: Callable[[str], bool] = lambda item_id: False
        #: How far the question being asked now is ("sources", "writing"), by item.
        self.stages: dict[str, str] = {}

    def in_library(self, item: Item) -> bool:
        return self.requested(item.id)

    def source_hash(self, item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def fresh(self, item: Item, note: Note | None) -> bool:
        """A written study stays until the work's text changes; a failed one
        until the prompt does as well."""
        return (
            note is not None
            and note.source_hash == self.source_hash(item)
            and ("teaser" in note.data or note.prompt_version == self.prompt_version)
        )

    def params(self, item: Item) -> dict[str, Any]:
        self.stages[item.id] = "sources"  # the museum, Wikidata and Wikipedia first
        params = super().params(item)
        self.stages[item.id] = "writing"
        return params
