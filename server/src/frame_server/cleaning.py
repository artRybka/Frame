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

No model is asked and nothing is spent. A study written and a composition
sheet drawn before stay as they are (they cost; the owner asks again).

Another copy of the picture (a sharper one, the work's own again) is
another photograph: it is read anew and cleaned at its own strength, or
not at all when its sheet is not yellowed. A copy the restorer drew is
drawn from the cleaned picture, so it is left as drawn.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx
from PIL import Image

from .imaging import recovery
from .library.models import Cleaned, Item, ItemKind
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

    def clean(self, item: Item, made: str) -> Item:
        """ "Zdejmij werniks" / "Odżółć papier": the work shown cleaned
        from now on. Raises :class:`NothingToClean` when it has nothing to
        offer; errors of the download are the caller's."""
        found = self._read(item, made)
        if found is None:
            raise NothingToClean(f"nothing to clean in {item.id}")
        return self.apply(item, found)

    def give_up(self, item: Item) -> Item:
        """ "Przywróć werniks" / "Przywróć ton papieru": the picture as it
        came again."""
        if item.cleaned is None:
            return item
        return self.apply(item, None)

    # -- another copy takes the picture's place ---------------------------------------

    def renew(self, item: Item) -> Item:
        """After the work's picture changed (``Sharper``): a cleaning read
        on the picture before is read anew on this one. A copy the restorer
        drew was drawn from the cleaned picture: it is left as drawn."""
        stored = self.library.get(item.id)
        if stored is None or stored.cleaned is None or stored.cleaned_shown() is not None:
            return stored or item
        made = stored.cleaned.made
        if stored.sharper is not None and stored.sharper.restored:
            log.info("cleaning of %s: the restorer's copy is left as drawn", item.id)
            return self.library.update(item.id, cleaned=None) or stored
        try:
            found = self._read(stored, made)
        except (httpx.HTTPError, OSError) as err:  # read again when the picture next changes
            log.info("cleaning of %s not renewed: %s", item.id, err)
            return stored
        if found is None:
            log.info("cleaning of %s: nothing to clean in the new picture", item.id)
            return self.library.update(item.id, cleaned=None) or stored
        return self.apply(stored, found)

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
            kind=kind, made=made, strength=strength, picture=item.picture_key(), at=_now()
        )

    def apply(self, item: Item, cleaned: Cleaned | None) -> Item:
        """``cleaned`` kept for the work and its pictures made again from
        it: the original, the thumbnail, the colours, the study's details."""
        changes: dict[str, Any] = {"cleaned": cleaned}
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
