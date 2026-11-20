"""Museum photographs cut down to the work by the phone's own model, with
no Claude (Mateusz 2026-11-20: „Celem jest całkowite uniknięcie Opus”).

The app looks at a work's photograph (``/full?side=``
:data:`..imaging.crop_model.PHOTO_SIDE`) with its model and its core
(``imaging/crop_model.py`` is what they do) when its card opens, and in
batches from Konfiguracja → Diagnostyka ("Kadruj partię"), and says here
what it found (:meth:`PhoneCrops.found`). A sure cut of a work standing
almost upright is put on; an unsure one leaves the photograph whole for him
(„Gdy model brak pewności — po prostu zostawmy do ręcznego kadrowania”).

Both wait for him on the list "Kadrowane" in Biblioteka
(:meth:`PhoneCrops.review`): what the model cut, and what it left to him.
His corrections, and the cuts he said were fine, are what the model is
taught again from (:meth:`PhoneCrops.lessons`).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PIL import Image

from .ai.crops import Crops
from .imaging.crop_model import MODEL, holds, kind_of
from .imaging.cut import Quad, same_picture, valid, worth_cutting
from .library.models import Cut

if TYPE_CHECKING:
    from .library import Item, Library

log = logging.getLogger(__name__)

#: The state's key in the library.
KEY = "phone_crops"
VERDICTS = ("cut", "whole", "unsure")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PhoneCrops:
    """What the phone's model found about the museum works' photographs."""

    def __init__(self, library: Library, crops: Crops) -> None:
        self.library = library
        self.crops = crops

    def on(self) -> bool:
        return self.crops.on_phone()

    def _state(self) -> dict[str, Any]:
        state = dict(self.library.get_state(KEY, {}) or {})
        state.setdefault("looked", {})
        state.setdefault("fine", {})
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.library.set_state(KEY, state)

    # -- which works -----------------------------------------------------------------

    def wants(self, item: Item, looked: dict[str, Any] | None = None) -> bool:
        """Whether the phone is to look at ``item``: a museum work with no
        cut of the photograph shown, not looked at by this model."""
        if not self.on() or not Crops.wanted(item) or not Crops.open_to_cut(item):
            return False
        seen = (looked if looked is not None else self._state()["looked"]).get(item.id)
        return not (seen and seen.get("p") == item.picture_key() and seen.get("m") == MODEL)

    def ask(self, item: Item) -> dict[str, Any]:
        """What the card's app needs to look at ``item``."""
        return {
            "look": self.wants(item),
            "kind": kind_of(item.classification, item.medium),
            "model": MODEL,
            "picture": item.picture_key(),
        }

    def waiting(self, limit: int) -> tuple[list[Item], int]:
        """The works the phone is to look at, those cared about first; and
        how many there are in all."""
        looked = self._state()["looked"]
        found = [i for i in self.library.all_items() if self.wants(i, looked)]
        return self.crops.ranked(found)[:limit], len(found)

    # -- what the phone found ---------------------------------------------------------

    def found(
        self,
        item: Item,
        *,
        verdict: str,
        sure: float,
        work: Quad | None,
        surround: Quad | None,
        size: tuple[int, int],
        picture: str,
        model: str,
    ) -> str:
        """What the phone's model found about ``item``'s photograph of
        ``size`` (as looked at), kept; a sure cut put on. The verdict kept
        ("cut" when the work was cut); "" when nothing was done: the
        photograph shown changed meanwhile, or the owner cut it himself."""
        if verdict not in VERDICTS:
            raise ValueError(f"no such verdict: {verdict}")
        stored = self.library.get(item.id) or item
        if picture != stored.picture_key() or not Crops.open_to_cut(stored):
            return ""
        with Image.open(self.crops.images.museum_photo(stored)) as img:
            aspect = round(img.width / img.height, 5)
        if not same_picture(aspect, size):
            log.info("phone crops: %s was looked at in another photograph", stored.id)
            return ""
        work = valid(work) if work is not None else None
        surround = valid(surround) if surround is not None else None
        if surround is not None and (work is None or not holds(surround, work)):
            surround = None  # not around all of it: no frame (an older app's)
        if verdict == "cut" and (work is None or not worth_cutting(work)):
            verdict = "whole" if work is not None else "unsure"
        state = self._state()
        state["looked"][stored.id] = {
            "p": stored.picture_key(),
            "m": model,
            "v": verdict,
            "s": round(float(sure), 4),
            "work": work,
            "surround": surround,
            "aspect": aspect,
            "at": _now(),
        }
        state["fine"].pop(stored.id, None)
        self._save(state)
        log.info("phone crops: %s %s (sure %.2f, %s)", stored.id, verdict, sure, model)
        if verdict == "cut":
            cut = Cut(
                work=work,
                aspect=aspect,
                picture=stored.picture_key(),
                shape="rectangle",
                at=state["looked"][stored.id]["at"],
                surround=surround,
                surround_kind="frame" if surround is not None else "",
                surround_asked=True,
            )
            self.crops.apply(stored, cut)
            return verdict
        if verdict == "whole" and stored.cut is None:
            # Looked at: nothing around it (as the night keeps it).
            self.library.update(stored.id, cut=Cut(aspect=aspect, picture=stored.picture_key()))
        return verdict

    # -- "Kadrowane" -------------------------------------------------------------------

    def _models(self, item: Item, entry: dict[str, Any]) -> bool:
        """Whether ``item`` is shown as the model left it."""
        cut = item.cut
        if entry.get("p") != item.picture_key():
            return False
        if entry.get("v") == "cut":
            return cut is not None and cut.by == "auto" and cut.at == entry.get("at")
        return cut is None or cut.by == "auto"

    def review(self) -> tuple[list[Item], list[Item]]:
        """ "Kadrowane": the works the model cut, and those it left to him,
        still as it left them and not said to be fine, the newest first."""
        state = self._state()
        cut: list[Item] = []
        unsure: list[Item] = []
        for item_id, entry in sorted(
            state["looked"].items(), key=lambda kv: str(kv[1].get("at")), reverse=True
        ):
            if item_id in state["fine"] or entry.get("v") not in ("cut", "unsure"):
                continue
            item = self.library.get(item_id)
            if item is None or not self._models(item, entry):
                continue
            if entry["v"] == "cut":
                item = self._unframed(item)
            (cut if entry["v"] == "cut" else unsure).append(item)
        return cut, unsure

    def _unframed(self, item: Item) -> Item:
        """``item`` without the frame the model found when it is not around
        all of the work (kept so by the app of 1.145.277)."""
        cut = item.cut
        if cut is None or cut.work is None or cut.surround is None or cut.surround_by == "owner":
            return item
        if holds(cut.surround, cut.work):
            return item
        log.info("phone crops: %s frame not around the work, dropped", item.id)
        bare = cut.model_copy(update={"surround": None, "surround_kind": ""})
        return self.crops.apply(item, bare)

    def fine(self, item: Item) -> bool:
        """He looked at the model's cut and it is right: off the list, and
        a lesson as it is. Whether there was such a cut."""
        state = self._state()
        entry = state["looked"].get(item.id)
        if entry is None or entry.get("v") != "cut" or not self._models(item, entry):
            return False
        state["fine"][item.id] = _now()
        self._save(state)
        return True

    def lessons(self) -> list[dict[str, Any]]:
        """What the model is taught again from: each work it looked at that
        he corrected (his cut, or the photograph whole) or said was fine,
        with what the model proposed."""
        state = self._state()
        found: list[dict[str, Any]] = []
        for item_id, entry in state["looked"].items():
            item = self.library.get(item_id)
            if item is None or entry.get("p") != item.picture_key():
                continue
            fine = item_id in state["fine"]
            owners = item.cut is not None and item.cut.by == "owner"
            if not fine and not owners:
                continue
            cut = item.cut
            found.append(
                {
                    "id": item_id,
                    "kind": kind_of(item.classification, item.medium),
                    "model": entry,
                    "fine": fine and not owners,
                    "work": cut.work if owners and cut is not None else entry.get("work"),
                    "surround": cut.surround
                    if cut is not None and (owners or cut.surround_by == "owner")
                    else entry.get("surround"),
                    "at": state["fine"].get(item_id) or (cut.at if cut is not None else ""),
                }
            )
        return found
