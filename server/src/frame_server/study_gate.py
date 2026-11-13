"""Which works may have a study ("Studium dzieła", Mateusz 2026-11-13): the
card of a work that may not shows no button for it, and the server takes
no order for it.

Three sieves, the free ones first:

1. the rules (``library.verdict``, ``Place.STUDIED``): copies, "Sztuki
   inne", a sketchbook's page or sheet of studies, a design or plan, the
   owner's photographs;
2. the sheet's pixels (``library.paper``): one small sketch on an empty
   page, notes scattered thinly;
3. for a pale sheet left between them, or a drawing its museum calls a
   study or sketch: Haiku with the picture (``ai.study_fit``), once a work.

What the curator of the study of the day set aside as no work for a page
(``daily_unfit``) counts too, and what is set aside here is never the
study of the day. A small picture is no reason: the creative restorer
draws it larger first (``study.Study``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .ai import study_fit
from .library import ItemKind
from .library.good import sketch_title
from .library.images import load_image
from .library.paper import Sheet
from .library.paper import read as read_sheet
from .library.verdict import NAMES, Place, against

if TYPE_CHECKING:
    from .ai.client import Claude
    from .library import ImageCache, Item, Library

log = logging.getLogger(__name__)

#: The works judged here: {id: {"fit": bool, "why": Polish, "by": "sheet" |
#: "model"}}.
STATE_KEY = "study_fit"
KEPT = 20_000
#: What the card says of a sheet the pixels set aside.
EMPTY = "prawie pusta kartka"
SCATTERED = "rozproszone szkice i notatki"


class StudyGate:
    def __init__(
        self,
        library: Library,
        images: ImageCache,
        claude: Claude | None = None,
        enabled: Callable[[], bool] = lambda: False,
        curated_unfit: Callable[[], dict[str, str]] = dict,
    ) -> None:
        self.library = library
        self.images = images
        self.claude = claude
        #: Whether Claude may be asked (the study's switch and key).
        self.enabled = enabled
        #: The works the study of the day's curator set aside.
        self.curated_unfit = curated_unfit
        self._lock = threading.Lock()
        self._asking: set[str] = set()

    def judged(self) -> dict[str, dict[str, Any]]:
        return dict(self.library.get_state(STATE_KEY, {}))

    def unfit(self) -> set[str]:
        """The works judged here to be worth no study."""
        return {i for i, v in self.judged().items() if not v.get("fit", True)}

    def why_not(self, item: Item, ask: bool = False) -> str | None:
        """Why ``item`` may have no study (in Polish), None when it may.
        ``ask``: Haiku may be asked now about a sheet the free sieves leave
        open (a second or two, once a work); else such a work may."""
        if reasons := against(item, Place.STUDIED):
            return NAMES[reasons[0]]
        if item.kind != ItemKind.ARTWORK:
            return None  # the owner's own works keep theirs
        if (seen := self.curated_unfit().get(item.id)) is not None:
            return seen or "odłożone przez kuratora"
        known = self.judged().get(item.id)
        if known is not None:
            return None if known.get("fit", True) else str(known.get("why") or "nie na studium")
        sheet = self._sheet(item, fetch=ask)
        if sheet is not None and (sheet.empty or sheet.scattered):
            why = EMPTY if sheet.empty else SCATTERED
            self._keep(item.id, False, why, "sheet")
            return why
        if not ask or not self._doubtful(item, sheet):
            return None
        return self._ask(item, sheet)

    def _doubtful(self, item: Item, sheet: Sheet | None) -> bool:
        """A pale sheet, or a drawing its museum calls a study or sketch."""
        return (sheet is not None and sheet.pale and sheet.plate is None) or sketch_title(item)

    def _sheet(self, item: Item, fetch: bool) -> Sheet | None:
        try:
            path = self.images.ensure_thumb(item) if fetch else self.images.thumb_path(item)
            if not path.is_file():
                return None
            return read_sheet(load_image(path.read_bytes()))
        except Exception as err:  # no picture: judged by its words alone
            log.info("study gate: no picture of %s (%s)", item.id, err)
            return None

    def _ask(self, item: Item, sheet: Sheet | None) -> str | None:
        if self.claude is None or not self.enabled():
            return None
        with self._lock:
            if item.id in self._asking:
                return None
            self._asking.add(item.id)
        try:
            answer = study_fit.ask(self.claude, self.images, item, sheet)
        except Exception as err:  # not now: the work may, and is asked again later
            log.info("study gate: Haiku did not judge %s (%s)", item.id, err)
            return None
        finally:
            with self._lock:
                self._asking.discard(item.id)
        log.info(
            "study gate: %s %s (%s, %.4f USD)",
            item.id,
            "fit" if answer.fit else "unfit",
            answer.why,
            answer.usd,
        )
        self._keep(item.id, answer.fit, answer.why, "model")
        return None if answer.fit else (answer.why or "nie na studium")

    def _keep(self, item_id: str, fit: bool, why: str, by: str) -> None:
        with self._lock:
            judged = self.judged()
            judged.pop(item_id, None)
            judged[item_id] = {"fit": fit, "why": why, "by": by}
            self.library.set_state(STATE_KEY, dict(list(judged.items())[-KEPT:]))

    def forget(self, item_id: str) -> None:
        """Judged again next time (its picture changed)."""
        with self._lock:
            judged = self.judged()
            if judged.pop(item_id, None) is not None:
                self.library.set_state(STATE_KEY, judged)
