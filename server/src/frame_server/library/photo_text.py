"""How a photo is named where a work shows its title and author.

A photo from a shared album rarely has a caption, so it used to read "Bez
tytułu" over "Album iCloud" (Mateusz, 2026-11-04: variant B). Its title is,
the first there is: its own caption (or a title given in the app), the few
words the language model wrote for what it shows (``PhotoInfo.title``),
the day it was taken. Under it: the day and the place, without what the
title already says.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Item

MONTHS = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
    "września", "października", "listopada", "grudnia",
)  # fmt: skip


def polish_date(day: date) -> str:
    """``29 października 2026``."""
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def taken_on(item: Item) -> date | None:
    """The day the photo was taken: from its EXIF or album date, else the
    day its listing gives."""
    taken = item.photo.taken_at if item.photo else None
    for text in (taken, item.date_text):
        try:
            return date.fromisoformat((text or "")[:10])
        except ValueError:
            continue
    return None


def _day(item: Item) -> str:
    day = taken_on(item)
    return polish_date(day) if day else ""


def photo_title(item: Item) -> str:
    """Its caption, else the model's words, else the day; "" when none is known."""
    info = item.photo
    return (
        item.title or (info.caption if info else "") or (info.title if info else "") or _day(item)
    )


def photo_line(item: Item) -> str:
    """``29 października 2026 · Kraków``: what of the day and the place the
    title does not say already."""
    day = _day(item)
    place = (item.photo.place if item.photo else "") or ""
    parts = [day if day != photo_title(item) else "", place]
    return " · ".join(p for p in parts if p)
