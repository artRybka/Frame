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

A print's sheet is cut down round its impression when the paper is wide
(``crop_model.plate``, Mateusz 2026-11-24): by the phone, by the server for
an app that does not say it did (:data:`..imaging.crop_model.PLATE`), and
once for every print cut before, his own cuts among them
(:meth:`PhoneCrops.plates_again`).
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from .ai.crops import Crops
from .imaging.crop_model import (
    KINDS,
    PHOTO_SIDE,
    PLATE,
    PLATE_SAME,
    holds,
    impression,
    kept,
    kind_of,
    model_of,
    overlap,
    plate,
    sheet_cut,
)
from .imaging.crop_night import Looker
from .imaging.cut import Quad, same_picture, valid, worth_cutting
from .imaging.layout import load_image
from .library.models import Cut

if TYPE_CHECKING:
    from .library import Item, Library

log = logging.getLogger(__name__)

#: The state's key in the library.
KEY = "phone_crops"
VERDICTS = ("cut", "whole", "unsure")
#: "Ucz kadrowania" (Mateusz 2026-11-21 00:47 UTC: „przygotuj mi ekran gdzie
#: dam mu dane startowe - ocenę czy trzeba kadrować i jeżeli tak, to czy jest
#: rama”): what he says of a catalogue photograph at a glance.
TOLD = ("whole", "cut", "framed")
#: The kinds he tells of, one at a time (Mateusz 2026-11-21 00:48 UTC:
#: „oddzielnie malarstwem, rysunkiem i grafiką. Będzie mi łatwiej”).
TAUGHT_KINDS = (0, 1, 2)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


#: A print is cut to its sheet and never framed by the model (Mateusz
#: 2026-11-20 22:13 UTC, „Rysunki jak dziś, grafiki do papieru”: of 70 prints
#: in his trial he corrected 23, the frame found round them right in 11 of 31).
# Drawings and prints are cut to the sheet, with no frame or passe-partout
# round them (Mateusz 2026-11-21 17:48 UTC: „Dla rysunku i grafiki
# zostawimy tylko jedno kadrowanie - »do kartki«”; prints since 2026-11-20).
SHEET_KINDS = (KINDS.index("drawing"), KINDS.index("print"))
#: A print: its sheet cut down round its impression when the paper is wide.
PRINT = KINDS.index("print")
#: The prints cut before are cut down round their impression once
#: (:meth:`PhoneCrops.plates_again`): 1 as ``crop_model.PLATE`` 1 had it;
#: 2 the model's from their sheet again, the margin round the impression
#: with its lettering (Mateusz 2026-11-25); 3 the model's again where the
#: cut left the drawing out, back to their sheet (``crop_model.PLATE_DRAWN``,
#: Mateusz 2026-11-27: „Nie możemy tak robić”). Prints left whole or to him
#: are looked at again instead (:meth:`wants`).
PLATES_AGAIN = 3
#: The whole photograph, as corners.
WHOLE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def _unframed_kind(item: Item) -> bool:
    return kind_of(item.classification, item.medium) in SHEET_KINDS


def _is_print(item: Item) -> bool:
    return kind_of(item.classification, item.medium) == PRINT


def _as_told(answer: str | None, kind: int | None) -> str | None:
    """His word as it is taught: "framed" of a drawing or print is a cut
    (17:48: „jeżeli gdzieś wybrałem »kadr z ramą« to potraktuj to jako
    »kadr«”)."""
    return "cut" if answer == "framed" and kind in SHEET_KINDS else answer


class PhoneCrops:
    """What the phone's model found about the museum works' photographs."""

    def __init__(self, library: Library, crops: Crops) -> None:
        self.library = library
        self.crops = crops
        self.looker = Looker()

    def _state(self) -> dict[str, Any]:
        state = dict(self.library.get_state(KEY, {}) or {})
        state.setdefault("looked", {})
        state.setdefault("fine", {})
        state.setdefault("told", {})
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.library.set_state(KEY, state)

    # -- which works -----------------------------------------------------------------

    def wants(self, item: Item, looked: dict[str, Any] | None = None) -> bool:
        """Whether the phone is to look at ``item``: a museum work with no
        cut of the photograph shown, not looked at by this model."""
        if not Crops.wanted(item) or not Crops.open_to_cut(item):
            return False
        seen = (looked if looked is not None else self._state()["looked"]).get(item.id)
        kind = kind_of(item.classification, item.medium)
        if not (seen and seen.get("p") == item.picture_key() and seen.get("m") == model_of(kind)):
            return True
        # A print left whole or to him before its paper was minded there
        # too (``crop_model.PLATE`` 2, ``sheet_cut``): looked at again.
        return (
            kind == PRINT
            and seen.get("v") in ("whole", "unsure")
            and int(seen.get("pl") or 0) < PLATE
        )

    def ask(self, item: Item) -> dict[str, Any]:
        """What the card's app needs to look at ``item``."""
        kind = kind_of(item.classification, item.medium)
        # A painting's own model since 2026-11-21: an app without it
        # (``MuseumCrop.model(of:)``) leaves paintings alone.
        return {
            "look": self.wants(item),
            "kind": kind,
            "model": model_of(kind),
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
        sheet: Quad | None = None,
        plate_alone: Quad | None = None,
        plates: int | None = None,
        night: bool = False,
    ) -> str:
        """What the phone's model found about ``item``'s photograph of
        ``size`` (as looked at), kept; a sure cut put on. The verdict kept
        ("cut" when the work was cut); "" when nothing was done: the
        photograph shown changed meanwhile, or the owner cut it himself.

        Of a print: ``work`` cut down round its impression (``plate_alone``)
        from the ``sheet`` the model found, by an app that did it as
        ``plates`` (:data:`..imaging.crop_model.PLATE`); here, of an app
        that did not. ``night``: looked at by the server at night
        (:meth:`at_night`), not by the phone."""
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
        if surround is not None and _unframed_kind(stored):
            surround = None
        alone: Quad | None = None
        if not _is_print(stored):
            sheet = None
        elif plates == PLATE:
            sheet = valid(sheet) if sheet is not None and work is not None else None
            if sheet is not None and plate_alone is not None:
                alone = kept(plate_alone)
        else:
            sheet = None
            made_of = sheet_cut(self._photo(stored), verdict, work)
            if made_of is not None:
                verdict, sheet, (work, alone) = made_of
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
        if _is_print(stored):
            state["looked"][stored.id].update(sheet=sheet, plate=alone, pl=PLATE)
        if night:
            state["looked"][stored.id]["night"] = True
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
                plate=alone if sheet is not None else None,
                paper=True,
            )
            self.crops.apply(stored, cut)
            return verdict
        if verdict == "whole" and stored.cut is None:
            # Looked at: nothing around it (as the night keeps it).
            self.library.update(stored.id, cut=Cut(aspect=aspect, picture=stored.picture_key()))
        return verdict

    def _photo(self, item: Item) -> np.ndarray:
        """``item``'s museum photograph as the phone looks at it: RGB, its
        long side at most :data:`..imaging.crop_model.PHOTO_SIDE`."""
        rgb = load_image(self.crops.images.museum_photo(item)).convert("RGB")
        rgb.thumbnail((PHOTO_SIDE, PHOTO_SIDE), Image.Resampling.LANCZOS)
        return np.asarray(rgb)

    # -- the same at night, on the server ----------------------------------------------

    def at_night(self, quiet: Callable[[], bool], most: int) -> dict[str, int]:
        """The works the phone is to look at (:meth:`waiting`, those cared
        about first) looked at here with the same models (``crop_night``),
        and what was found kept as the phone's is (Mateusz 2026-11-24
        10:53 UTC, „Na serwerze w nocy”): ``most`` of them at most, while
        ``quiet()`` says the night goes on. The phone passes over what was
        looked at here. How many of each verdict."""
        done = {"cut": 0, "whole": 0, "unsure": 0}
        works, _ = self.waiting(most)
        for item in works:
            if not quiet():
                break
            stored = self.library.get(item.id)
            if stored is None or not self.wants(stored):
                continue
            kind = kind_of(stored.classification, stored.medium)
            try:
                rgb = self._photo(stored)
                found = self.looker.look(rgb, kind)
                verdict = self.found(
                    stored,
                    verdict=found.verdict,
                    sure=found.sure,
                    work=found.work,
                    surround=found.surround,
                    size=(rgb.shape[1], rgb.shape[0]),
                    picture=stored.picture_key(),
                    model=model_of(kind),
                    sheet=found.sheet,
                    plate_alone=found.plate,
                    plates=PLATE,
                    night=True,
                )
            except (OSError, ValueError, LookupError) as err:
                log.warning("phone crops: %s not looked at tonight: %s", stored.id, err)
                continue
            if verdict in done:
                done[verdict] += 1
        log.info("phone crops at night: %s", done)
        return done

    # -- prints cut down round their impression, once ----------------------------------

    def plates_again(self) -> dict[str, int]:
        """Once after a start, for every print cut before prints were cut
        as now (:data:`..imaging.crop_model.PLATE`): its sheet cut down
        round its impression when the paper is wide. His own cuts too
        (Mateusz 2026-11-24 10:39–10:40 UTC: „ręczne kadry, jeżeli obejmują
        samą grafikę także obejmij tą zmianą”, „te Ręczne kadry z papierem
        wokół i te z całą kartką także obejmij zmianą”): his cut to the
        impression alone gets its margin within the model's sheet; within
        his cut of the sheet, or of the sheet and more, the impression is
        looked for as in the model's. His cuts set after it stay as he
        sets them. How many were cut anew: the model's, his, and of his
        those that were the impression alone."""
        state = self._state()
        if int(state.get("plates") or 0) >= PLATES_AGAIN:
            return {}
        done = {"auto": 0, "owner": 0, "owner_impression": 0, "looked": 0}
        for item in self.library.all_items():
            cut = item.cut
            if (
                cut is None
                or cut.work is None
                or not _is_print(item)
                or cut.picture != item.picture_key()
                or cut.not_rectangle
            ):
                continue
            try:
                made = self._plate_again(item, state, done)
            except (OSError, ValueError, LookupError) as err:
                log.warning("phone crops: %s not cut round its impression: %s", item.id, err)
                continue
            if made:
                done["owner" if cut.by == "owner" else "auto"] += 1
        state = self._state() | {"plates": PLATES_AGAIN, "plates_done": done}
        self._save(state)
        log.info(
            "phone crops: prints cut round their impression: %d of the model's, %d of his "
            "(%d to the impression alone), of %d looked at",
            done["auto"],
            done["owner"],
            done["owner_impression"],
            done["looked"],
        )
        return done

    def _plate_again(self, item: Item, state: dict[str, Any], done: dict[str, int]) -> bool:
        cut = item.cut
        assert cut is not None and cut.work is not None
        entry = state["looked"].get(item.id)
        if entry is not None and entry.get("p") != item.picture_key():
            entry = None
        rgb = self._photo(item)
        h, w = rgb.shape[:2]
        if cut.aspect and not same_picture(cut.aspect, (w, h)):
            return False
        done["looked"] += 1
        made: tuple[Quad, Quad | None] | None = None
        if cut.by == "owner":
            # The model's sheet where it looked, else his cut is the sheet.
            sheet = (entry or {}).get("sheet") or (entry or {}).get("work")
            found = impression(rgb, sheet) if sheet is not None else None
            if found is not None and sheet is not None:
                alone = found.on_photo(found.corners(), w, h)
                if overlap(cut.work, alone, (w, h)) >= PLATE_SAME:
                    made = plate(rgb, sheet, over=0.0)
                    if made is not None:
                        done["owner_impression"] += 1
            if made is None:
                made = plate(rgb, cut.work)
        else:
            # From the sheet the model found, not from the cut made of it.
            sheet = (entry or {}).get("sheet") or cut.work
            made = plate(rgb, sheet)
            if made is None and cut.plate is not None:
                # Cut round what it no longer takes for its impression
                # (one figure of a drawing): back to its sheet.
                made = ([(float(x), float(y)) for x, y in sheet], None)
            if made is not None and overlap(made[0], cut.work, (w, h)) >= 0.995:
                return False  # as cut now
        if made is None:
            return False
        work, alone_kept = made
        at = _now()
        if (
            cut.by == "auto"
            and entry is not None
            and entry.get("v") == "cut"
            and entry.get("at") == cut.at
        ):
            looked = self._state()
            looked["looked"][item.id] = entry | {
                "sheet": entry.get("sheet") or entry.get("work"),
                "work": work,
                "plate": alone_kept,
                "pl": PLATE,
                "at": at,
            }
            self._save(looked)
            state["looked"][item.id] = looked["looked"][item.id]
        again = {"work": work, "plate": alone_kept, "paper": True, "at": at}
        self.crops.apply(item, cut.model_copy(update=again))
        log.info("phone crops: %s (%s) cut round its impression", item.id, cut.by)
        return True

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
        not yet approved, the newest first: as the model left them, or cut
        by him since (among the cut ones)."""
        state = self._state()
        cut: list[Item] = []
        unsure: list[Item] = []
        for item_id, entry in sorted(
            state["looked"].items(), key=lambda kv: str(kv[1].get("at")), reverse=True
        ):
            if item_id in state["fine"] or entry.get("v") not in ("cut", "unsure"):
                continue
            item = self.library.get(item_id)
            if item is None or entry.get("p") != item.picture_key():
                continue
            if self._owners(item):
                # He set the cut himself from the list: it stays until he
                # approves it (Mateusz 2026-11-20: „Gdy klikam zapisz w
                # edycji kadru to nie zatwierdzaj automatycznie dzieła”).
                cut.append(item)
                continue
            if not self._models(item, entry):
                continue
            if entry["v"] == "cut":
                item = self._unframed(item)
            (cut if entry["v"] == "cut" else unsure).append(item)
        return cut, unsure

    @staticmethod
    def _owners(item: Item) -> bool:
        return item.cut is not None and item.cut.by == "owner"

    def _unframed(self, item: Item) -> Item:
        """``item`` without the frame the model found when it is not around
        all of the work (kept so by the app of 1.145.277), or round a print."""
        cut = item.cut
        if cut is None or cut.work is None or cut.surround is None or cut.surround_by == "owner":
            return item
        if holds(cut.surround, cut.work) and not _unframed_kind(item):
            return item
        log.info("phone crops: %s frame dropped", item.id)
        bare = cut.model_copy(update={"surround": None, "surround_kind": ""})
        return self.crops.apply(item, bare)

    def fine(self, item: Item) -> bool:
        """He looked at the model's cut and it is right, or at a work it
        left whole and that is right ("Bez kadru"): off the list, and a
        lesson as it is. Whether there was such a work of the model's."""
        state = self._state()
        entry = state["looked"].get(item.id)
        if entry is None or entry.get("v") not in ("cut", "unsure"):
            return False
        if entry.get("p") != item.picture_key():
            return False
        if not (self._owners(item) or self._models(item, entry)):
            return False
        state["fine"][item.id] = _now()
        self._save(state)
        return True

    def unfine(self, item_id: str) -> bool:
        """ "Cofnij" in "Sprawdź kadry": the approval taken back, the work on
        the list again. Whether it had been approved."""
        state = self._state()
        if state["fine"].pop(item_id, None) is None:
            return False
        self._save(state)
        return True

    def sure(self, ids: list[str]) -> dict[str, float]:
        """How sure the model was a cut is wanted, of each of ``ids``."""
        looked = self._state()["looked"]
        return {i: float(looked[i].get("s", 0.0)) for i in ids if i in looked}

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
            # The model is taught the sheet it found, not the impression's
            # cut made of it (``crop_model.plate``).
            models = entry.get("sheet") or entry.get("work")
            found.append(
                {
                    "id": item_id,
                    "kind": kind_of(item.classification, item.medium),
                    "model": entry,
                    "fine": fine and not owners,
                    "work": cut.work
                    if owners and cut is not None
                    else (None if entry.get("v") == "unsure" else models),
                    "surround": cut.surround
                    if cut is not None and (owners or cut.surround_by == "owner")
                    else (None if entry.get("v") == "unsure" else entry.get("surround")),
                    "at": state["fine"].get(item_id) or (cut.at if cut is not None else ""),
                }
            )
        return found

    # -- "Ucz kadrowania": his word on a photograph at a glance ------------------------

    def to_teach(self, limit: int, kind: int = 0) -> tuple[list[Item], int]:
        """Catalogue photographs of ``kind`` for him to say of whether they
        want a cut and a frame: museum works shown as the museum
        photographed them (no cut, so their small picture is the
        photograph), not looked at by the model nor told of yet, at random.
        And how many he has told of."""
        if kind not in TAUGHT_KINDS:
            raise ValueError(f"no such kind: {kind}")
        state = self._state()
        told, looked = state["told"], state["looked"]
        found = [
            item
            for item in self.library.all_items()
            if item.cut is None
            and item.id not in told
            and item.id not in looked
            and Crops.wanted(item)
            and kind_of(item.classification, item.medium) == kind
        ]
        return random.Random(len(told)).sample(found, min(limit, len(found))), len(told)

    def tell(self, item: Item, answer: str | None) -> int:
        """His word on ``item``'s photograph ("whole", "cut" or "framed"),
        kept; None takes it back ("Cofnij"). How many he has told of."""
        if answer is not None and answer not in TOLD:
            raise ValueError(f"no such answer: {answer}")
        state = self._state()
        if answer is None:
            state["told"].pop(item.id, None)
        else:
            kind = kind_of(item.classification, item.medium)
            state["told"][item.id] = {
                "p": item.picture_key(),
                "t": _as_told(answer, kind),
                "k": kind,
                "at": _now(),
            }
        self._save(state)
        return len(state["told"])

    def told(self) -> list[dict[str, Any]]:
        """What he said at a glance, for teaching the model on the Mac: the
        photograph whole, cut, or cut with a frame round the work (no
        corners); the photographs from ``/api/library/items/{id}/full?side=``."""
        found: list[dict[str, Any]] = []
        for item_id, entry in self._state()["told"].items():
            item = self.library.get(item_id)
            if item is None or entry.get("p") != item.picture_key():
                continue
            found.append(
                {
                    "id": item_id,
                    "kind": entry.get("k"),
                    "told": _as_told(entry.get("t"), entry.get("k")),
                    "at": entry.get("at"),
                }
            )
        return found
