"""A work shown with the colours time took given back: its aged varnish
taken off, or its sheet de-yellowed, by calculation alone
(:mod:`frame_server.imaging.recovery`).

Mateusz 2026-11-15 18:39 UTC, after the preview on the card (1.145.155):
"To działa naprawdę fajnie. Z ściągania werniksu usuwamy suwak. Zostawiamy
tylko poziom propozycji. Wybranie w menu podmienia na wersje z odżółconym
papierem / ściągniętym werniksem. … Jeżeli wersja podmieniona na
skorygowaną to wyliczamy kolory i pasek z wersji po korekcie."

So it is kept for the work like its cut (``Item.cleaned``,
:class:`~frame_server.library.models.Cleaned`): the original and the
thumbnail are made again from the museum's photograph, which is kept beside
them (``ImageCache.recut``), and the colours, the colour bar and the search
are measured on the cleaned picture. The frame, the lists and the studies
show it. "Przywróć…" goes back to the picture as it came.

Since 2026-11-19 it is each person's own (Mateusz: "zdejmij werniks,
odżółć papier to indywidualne ustawienia każdego z użytkowników"): the
reading is the work's, who sees it so is ``Item.cleaned_by``. The kept
original, thumbnail and colours, and the frame's rotation, go by the
owner's choice; another person's other choice is a picture made apart
(``ImageCache.variant``), and the frame shows a work they send their way.

No model is asked and nothing is spent. A study written and a composition
sheet drawn before stay as they are (they cost; the owner asks again).

Another copy of the picture (a sharper one, one the owner picked) is
another photograph: "nie wiemy jaką ona ma kolorystykę i automatyczne
naniesienie zmian barwy mogłoby być błędem" (Mateusz 2026-11-15 18:54), so
it is shown as it comes; the cleaning stays with the picture it was read
on and shows again when that picture does. The restorer's drawing is the
same photograph drawn larger ("tak dla wersji restauratora"): it is drawn
from the picture as it came and cleaned the same.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from PIL import Image

from .imaging import recovery
from .library.models import Cleaned, Item, ItemKind
from .library.viewer import OWNER_ID
from .library.vocabulary import is_photograph

if TYPE_CHECKING:
    from .library.images import ImageCache
    from .library.importer import Importer
    from .library.repo import Library

log = logging.getLogger(__name__)

#: How the app says a work is made (its ``PaintStyle``): in oil or tempera,
#: on paper in a medium that lets the sheet through, or one that covers it.
Made = Literal["oil", "paper", "opaque"]
Kind = Literal["varnish", "paper", "none"]
#: Oils painted after this are not offered: their varnish, where they have
#: one, has not had the time to yellow.
VARNISH_UNTIL = 1950
#: The long side a picture is read at to say what it may be offered.
READ = 640
#: The share of the proposal the first sum (``Cleaned.reading`` 1) kept a
#: work at; the proposal is kept whole since.
FIRST_SHARE = 0.75


class NothingToClean(ValueError):
    """The work has neither an aged varnish nor a yellowed sheet to offer."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def by_its_data(item: Item, made: str) -> bool:
    """Whether the work's data leave anything to offer at all, before its
    picture is looked at: no photograph, no oil too young to have yellowed,
    nothing that is not a work."""
    if item.kind != ItemKind.ARTWORK or is_photograph(item):
        return False
    return not (made == "oil" and item.year is not None and item.year > VARNISH_UNTIL)


def offered(item: Item, made: str, picture: Image.Image) -> Kind:
    """What ``picture`` (the work as it came, not cleaned) may be offered."""
    if not by_its_data(item, made):
        return "none"
    if made == "oil":
        return "varnish"
    state = recovery.sheet_state(recovery.read_sheet(picture), item.medium)
    return "paper" if state == "yellowed" else "none"


class Cleaning:
    """Sets, gives up and renews a work's cleaning."""

    def __init__(self, library: Library, images: ImageCache) -> None:
        self.library = library
        self.images = images
        self.importer: Importer | None = None

    # -- the owner's asks -------------------------------------------------------------

    def clean(self, item: Item, made: str, user: str = OWNER_ID) -> Item:
        """ "Zdejmij werniks" / "Odżółć papier": ``user`` sees the work
        cleaned from now on. Raises :class:`NothingToClean` when it has
        nothing to offer; errors of the download are the caller's."""
        reading = item.cleaned_reading()
        if reading is None:
            reading = self._read(item, made)
            if reading is None:
                raise NothingToClean(f"nothing to clean in {item.id}")
            who = [user]
        else:
            who = sorted({*item.cleaned_viewers(), user})
        return self._put(item, reading, who)

    def give_up(self, item: Item, user: str = OWNER_ID) -> Item:
        """ "Przywróć werniks" / "Przywróć ton papieru": ``user`` sees the
        picture as it came again. The reading goes once nobody sees it."""
        if item.cleaned is None:
            return item
        who = [u for u in item.cleaned_viewers() if u != user]
        return self._put(item, item.cleaned if who else None, who or None)

    def _put(self, item: Item, reading: Cleaned | None, who: list[str] | None) -> Item:
        """``reading`` and who sees it kept; the kept pictures made again
        when what the owner sees changed."""
        before = item.cleaned_shown()
        changed = item.model_copy(update={"cleaned": reading, "cleaned_by": who})
        if changed.cleaned_shown() == before:
            return self.library.update(item.id, cleaned=reading, cleaned_by=who) or changed
        return self.apply(item, reading, who)

    # -- another copy takes the picture's place ---------------------------------------

    def renew(self, before: Item) -> Item:
        """After the work's picture changed (``Sharper``; ``before``: the
        work as it was). The restorer's drawing of a picture shown cleaned
        is cleaned the same; any other copy is another photograph and is
        left as it comes."""
        stored = self.library.get(before.id)
        if stored is None or stored.cleaned is None or stored.cleaned_reading() is not None:
            return stored or before
        if stored.sharper is None or not stored.sharper.restored:
            return stored
        if before.cleaned_reading() is None:
            return stored  # drawn from a picture that was not shown cleaned
        cleaned = stored.cleaned.model_copy(update={"drawn": stored.picture_key(), "at": _now()})
        return self.apply(stored, cleaned)

    # -- the sum changed --------------------------------------------------------------

    def catch_up(self) -> int:
        """The works kept without their varnish by an earlier sum, made
        again with this one (``recovery.READING``; Mateusz 2026-11-15
        21:44, of works cleaned with the first: "Korekta werniksu - czasem
        ledwo widoczna"): once, a while after a start. The strength is the
        proposal the first sum took three quarters of; a cleaning whose
        picture is not the one shown now is only noted, and shows the new
        way when its picture does. How many were made again."""
        made = 0
        for item in self.library.all_items():
            cleaned = item.cleaned
            if cleaned is None or cleaned.kind != "varnish" or cleaned.reading >= recovery.READING:
                continue
            strength = cleaned.strength
            if cleaned.reading < 2:
                strength = round(min(strength / FIRST_SHARE, recovery.D_MAX), 2)
            again = cleaned.model_copy(
                update={"strength": strength, "reading": recovery.READING, "at": _now()}
            )
            try:
                if item.cleaned_shown() is None:
                    self.library.update(item.id, cleaned=again)
                else:
                    self.apply(item, again)
                    made += 1
            except (OSError, ValueError) as err:
                log.warning("cleaning of %s not made again: %s", item.id, err)
        if made:
            log.info("cleanings made again with the sum of now: %d", made)
        return made

    # -- putting it on ----------------------------------------------------------------

    def _read(self, item: Item, made: str) -> Cleaned | None:
        """The cleaning the picture shown now would get, None when it has
        nothing to offer."""
        if not by_its_data(item, made):
            return None
        picture = self.images.before_cleaning(item, urgent=True)
        small = picture.convert("RGB")
        small.thumbnail((READ, READ), Image.Resampling.LANCZOS)
        kind = offered(item, made, small)
        if kind == "none":
            return None
        strength = recovery.kept_strength(small) if kind == "varnish" else 0.0
        return Cleaned(
            kind=kind,
            made=made,
            strength=strength,
            reading=recovery.READING,
            picture=item.picture_key(),
            at=_now(),
        )

    def apply(
        self, item: Item, cleaned: Cleaned | None, who: list[str] | Literal["same"] | None = "same"
    ) -> Item:
        """``cleaned`` kept for the work (seen by ``who``, by default those
        who saw it) and its pictures made again from it: the original, the
        thumbnail, the colours, the study's details."""
        changes: dict[str, Any] = {"cleaned": cleaned}
        if who != "same":
            changes["cleaned_by"] = who
        updated = self.library.update(item.id, **changes) or item.model_copy(update=changes)
        self.images.recut(updated)
        if self.importer is not None:
            try:
                updated = self.importer.measure_again(updated)
            except OSError as err:
                log.info("colours of %s: %s", item.id, err)
        details = Path(self.images.thumbs.parent) / "details"
        for old in details.glob(f"{item.file_stem}-*.jpg"):
            old.unlink(missing_ok=True)
        log.info(
            "cleaning of %s: %s",
            item.id,
            "given up" if cleaned is None else f"{cleaned.kind} {cleaned.strength:.2f}",
        )
        return updated
