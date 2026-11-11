"""Why a work is no picture for the frame: every reason the rules know, as
one list (docs/RULES.md, stage 4).

The rules themselves are ``vocabulary``'s (``is_detail``, ``is_postal``,
``object_category``…); they were put together anew in about sixty places,
each with its own choice of them (the audit of 2026-11-11). Here they are
asked once, in one order, and answer with names: what a place does with a
work is then a matter of which reasons it minds, not of which functions it
happened to call.

What a place minds is :data:`MINDS`: one row a place, for the works the
server took in on its own (``Item.pooled``) and for those the owner kept (a
heart, a playlist). :func:`against` is the verdict: the reasons a place
has against a work, none when it is shown there.
"""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum

from .models import Item
from .vocabulary import (
    DECORATIVE,
    MANUSCRIPTS,
    OBJECT_CATEGORIES,
    PHOTOGRAPHY,
    SCULPTURE,
    is_archive_photo,
    is_art_archive_photo,
    is_detail,
    is_document,
    is_grey_copy,
    is_openverse_copy,
    is_photograph,
    is_postal,
    is_reproduction,
    object_category,
)


class Why(StrEnum):
    """A reason a work is no picture for the frame."""

    #: The catalogue's gatekeeper saw it to be no artwork (``Item.seen_as``).
    SEEN = "seen"
    #: A photograph Openverse has from Flickr.
    OPENVERSE_PHOTO = "openverse_photo"
    #: Openverse's copy of a work the server asks its museum for itself.
    OPENVERSE_COPY = "openverse_copy"
    #: A detail of a work (its title, or its picture inside another's).
    DETAIL = "detail"
    #: A photograph of a work in its frame or on a museum's wall.
    SCENE = "scene"
    #: A photograph from a photo archive that calls them paintings.
    ARCHIVE_PHOTO = "archive_photo"
    #: A stamp, banknote or envelope.
    POSTAL = "postal"
    #: A page of text, printed matter, the back of a work.
    DOCUMENT = "document"
    #: A plate, page, slide or postcard reproducing a work.
    REPRODUCTION = "reproduction"
    #: A black-and-white copy of a painting.
    GREY_COPY = "grey_copy"
    #: A black-and-white photograph of a work from an art history archive.
    GREY_SLIDE = "grey_slide"
    #: "Sztuki inne": works that keep to their own group.
    MANUSCRIPT = "manuscript"
    PHOTOGRAPH = "photograph"
    SCULPTURE = "sculpture"
    DECORATIVE = "decorative"


#: The reasons that make a work a copy: never what the frame looks for.
COPIES = frozenset(
    {
        Why.SEEN,
        Why.OPENVERSE_PHOTO,
        Why.OPENVERSE_COPY,
        Why.DETAIL,
        Why.SCENE,
        Why.ARCHIVE_PHOTO,
        Why.POSTAL,
        Why.DOCUMENT,
        Why.REPRODUCTION,
        Why.GREY_COPY,
        Why.GREY_SLIDE,
    }
)
#: The reasons of "Sztuki inne" (``vocabulary.other_art``), by the category
#: a search asks for them with.
OTHER_ART = {
    MANUSCRIPTS: Why.MANUSCRIPT,
    PHOTOGRAPHY: Why.PHOTOGRAPH,
    SCULPTURE: Why.SCULPTURE,
    DECORATIVE: Why.DECORATIVE,
}

#: The category each reason of "Sztuki inne" is asked for with.
CATEGORY = {why: category for category, why in OTHER_ART.items()}
EVERY = frozenset(Why)
OTHER = frozenset(OTHER_ART.values())

#: The reasons as the app would say them.
NAMES = {
    Why.SEEN: "odłożone przez Strażnika",
    Why.OPENVERSE_PHOTO: "fotografia z Openverse",
    Why.OPENVERSE_COPY: "kopia z Openverse",
    Why.DETAIL: "detal dzieła",
    Why.SCENE: "zdjęcie dzieła w ramie albo na ścianie",
    Why.ARCHIVE_PHOTO: "zdjęcie z archiwum fotografii",
    Why.POSTAL: "znaczek albo banknot",
    Why.DOCUMENT: "dokument albo odwrocie",
    Why.REPRODUCTION: "reprodukcja",
    Why.GREY_COPY: "czarno-biała kopia",
    Why.GREY_SLIDE: "czarno-białe zdjęcie z archiwum sztuki",
    Why.MANUSCRIPT: "rękopis",
    Why.PHOTOGRAPH: "fotografia",
    Why.SCULPTURE: "rzeźba",
    Why.DECORATIVE: "rzemiosło artystyczne",
}


def whys(item: Item) -> tuple[Why, ...]:
    """Every reason ``item`` is no picture for the frame; none for a
    picture."""
    found = [
        why
        for why, holds in (
            (Why.SEEN, bool(item.seen_as)),
            (Why.OPENVERSE_PHOTO, is_photograph(item) and item.source == "openverse"),
            (Why.OPENVERSE_COPY, is_openverse_copy(item)),
            (Why.DETAIL, is_detail(item)),
            (Why.SCENE, bool(item.scene_of and not item.part_of)),
            (Why.ARCHIVE_PHOTO, is_archive_photo(item)),
            (Why.POSTAL, is_postal(item)),
            (Why.DOCUMENT, is_document(item)),
            (Why.REPRODUCTION, is_reproduction(item)),
        )
        if holds
    ]
    if is_grey_copy(item):
        found.append(Why.GREY_SLIDE if is_art_archive_photo(item) else Why.GREY_COPY)
    category = object_category(item)
    if category is not None:
        found.append(OTHER_ART[category])
    return tuple(found)


def copy_whys(item: Item) -> tuple[Why, ...]:
    """The reasons ``item`` is a copy; none for a work."""
    return tuple(why for why in whys(item) if why in COPIES)


class Place(StrEnum):
    """Where a work is asked about."""

    #: The catalogue listed as it stands: the favourites, a playlist put
    #: together by hand, everything.
    LISTED = "listed"
    #: The catalogue asked for works: a word, an artist, a filter.
    FOUND = "found"
    #: What the server proposes on its own: the work of the day, Discover's
    #: cards and pages, Propozycje dnia, the works beside a study.
    PROPOSED = "proposed"
    #: A museum's answer as it is read, before any search's own wishes.
    MUSEUM = "museum"
    #: What a search in the museums, or a card of Discover filled from
    #: them, takes on.
    SOUGHT = "sought"
    #: What the night looks over: the gatekeeper, the audit.
    TIDIED = "tidied"
    #: What may be a copy or a detail of another work: the twins, their
    #: judge, the sharper copies.
    COMPARED = "compared"


#: The reasons each place minds: of a work the server took in on its own,
#: and of one the owner kept. A reason of "Sztuki inne" is minded unless its
#: category is asked for.
MINDS: dict[Place, tuple[frozenset[Why], frozenset[Why]]] = {
    # What the owner kept is his to see, whatever it is.
    Place.LISTED: (EVERY, frozenset()),
    # A stamp or a page he kept is no still life, Foto Marburg's grey slide
    # no painting (Mateusz 2026-11-09); a detail he kept is found.
    Place.FOUND: (EVERY, OTHER | {Why.POSTAL, Why.DOCUMENT, Why.GREY_SLIDE}),
    # The details, reproductions and stamps he kept stay his (Ulubione, his
    # playlists, Szukaj): the server proposes none of them itself (Mateusz
    # 2026-11-11).
    Place.PROPOSED: (EVERY, EVERY),
    Place.MUSEUM: (COPIES, COPIES),
    Place.SOUGHT: (EVERY, EVERY),
    Place.TIDIED: (EVERY, EVERY),
    Place.COMPARED: (COPIES, COPIES),
}


def against(
    item: Item,
    place: Place,
    asked: Collection[str] = (),
    kept: bool | None = None,
) -> tuple[Why, ...]:
    """The reasons ``place`` has against ``item``; none when it is shown (or
    taken on) there. ``asked`` are the keys a search asks with: a category
    of "Sztuki inne" among them lets its works in. ``kept`` says whose the
    work is when the item does not (a museum's answer not stored yet): the
    owner's, or one the server took in; the item's own ``pooled`` when not
    given."""
    if kept is None:
        kept = not item.pooled
    minded = MINDS[place][1 if kept else 0]
    if not minded:
        return ()
    return tuple(why for why in whys(item) if why in minded and CATEGORY.get(why) not in asked)


def category_fits(item: Item, keys: Collection[str]) -> bool:
    """A work of a museum's search for ``keys``: of a category asked for, or
    a picture while nothing but such categories is asked for as technique
    (rzeźba alone: no paintings)."""
    if against(item, Place.SOUGHT, keys):
        return False
    if object_category(item) is not None:
        return True
    asked = [k for k in keys if k in OBJECT_CATEGORIES]
    techniques = [k for k in keys if k.startswith("technique:")]
    return not asked or len(techniques) > len(asked)
