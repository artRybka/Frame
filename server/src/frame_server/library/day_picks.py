"""Propozycje dnia: the frame's rotation without a playlist, made each day
from the cards of "Dziś dla Ciebie" (Mateusz 2026-11-09: "połączenie zbiorów
Dziś dla Ciebie … w jedną, automatyczną playlistę", then 10:41 "po pierwszych
12 z każdej listy, ale ułożone czwórkami").

The first works of each card, as Odkrywaj opens it, in fours: four from the
first card, four from the next and so on, then each card's next four. The
frame shows them in that order; the list is made once a day for each person
(their "Ponieważ lubisz" cards are their own) and kept until the next day.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from .models import Item
from .repo import Library
from .themes import CARD_MIN, MIX_PREFIX, Theme, for_you, liked, theme_of_the_day

log = logging.getLogger(__name__)

#: ``day_picks:<user id>``: the day's list as last made for that person.
PICKS_KEY = "day_picks"
#: Works from each card, and how many of them come together.
PER_CARD = 12
BLOCK = 4


@dataclass
class DayPicks:
    day: str
    #: The cards, in the order of "Dziś dla Ciebie": (key, name, description).
    cards: list[tuple[str, str, str]] = field(default_factory=list)
    #: The works in the order the frame shows them.
    ids: list[str] = field(default_factory=list)


def picks_key(user: str) -> str:
    return f"{PICKS_KEY}:{user}"


def kept(library: Library, user: str) -> DayPicks | None:
    """The list as last made for ``user`` (maybe another day's)."""
    stored = library.get_state(picks_key(user), None)
    if not stored:
        return None
    cards = [(c["key"], c["name"], c.get("description", "")) for c in stored.get("cards", [])]
    return DayPicks(day=stored.get("day", ""), cards=cards, ids=list(stored.get("ids", [])))


def cards(library: Library, user: str, day: date, private: bool) -> list[Theme]:
    """The cards of "Dziś dla Ciebie" in the app's order: the curator's
    first card, the artist of the week, the curator's other card, the theme
    of the day, ``user``'s "Ponieważ lubisz", the week's pairs."""
    weekly = for_you(library, day)
    pairs = [t for t in weekly if t.key.startswith(MIX_PREFIX)]
    first = [t for t in weekly if t not in pairs]
    every = [*first, theme_of_the_day(day, library), *liked(library, user), *pairs]
    seen: set[str] = set()
    out = []
    for found in every:
        if found.key in seen or (found.private and not private):
            continue
        seen.add(found.key)
        out.append(found)
    return out


def in_fours(lists: list[list[str]], block: int = BLOCK) -> list[str]:
    """Four from each list in turn, then the next four of each."""
    out: list[str] = []
    longest = max((len(ids) for ids in lists), default=0)
    for start in range(0, longest, block):
        for ids in lists:
            out.extend(ids[start : start + block])
    return out


def work_out(library: Library, user: str, day: date, private: bool = False) -> DayPicks:
    """``user``'s list for ``day``, kept for the rest of the day. A query
    of the catalogue for each card (seconds on the NAS): made at night and,
    if the day's is missing, in the background."""
    day_theme = theme_of_the_day(day, library).key
    hidden = library.hidden().ids
    spare = library.spare_copies()
    taken: set[str] = set()
    shown: list[tuple[Theme, list[str]]] = []
    for found in cards(library, user, day, private):
        if found.key == day_theme:
            # As Odkrywaj draws the day's row from the catalogue.
            total, items = library.query(
                found.rules(), sort="random", seed=day.toordinal(), user=user
            )
        else:
            total, items = library.query(
                found.rules(), sort="suitability", limit=PER_CARD * 4, user=user
            )
        if total < CARD_MIN:
            continue  # not shown in Odkrywaj either
        ids = _first(items, PER_CARD, taken | hidden | spare)
        if ids:
            taken.update(ids)
            shown.append((found, ids))
    picks = DayPicks(
        day=day.isoformat(),
        cards=[(t.key, _name(t, day_theme), t.description) for t, _ in shown],
        ids=in_fours([ids for _, ids in shown]),
    )
    library.set_state(
        picks_key(user),
        {
            "day": picks.day,
            "cards": [{"key": k, "name": n, "description": d} for k, n, d in picks.cards],
            "ids": picks.ids,
        },
    )
    log.info("day picks for %s: %d works from %d cards", user, len(picks.ids), len(picks.cards))
    return picks


def _first(items: list[Item], count: int, skip: set[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item.excluded or item.id in skip or item.id in out:
            continue
        out.append(item.id)
        if len(out) == count:
            break
    return out


def _name(found: Theme, day_theme: str) -> str:
    return f"Motyw dnia: {found.name}" if found.key == day_theme else found.name
