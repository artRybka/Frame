"""Which works come first where the server proposes them (a theme of
Odkrywaj, Propozycje dnia): the good ones, by many hands, others each day.

Until 1.145.23 a theme's page was its museums' highlights and then its
artists from A to Z, the nameless before them all, the same every day:
"Sztuka polska" opened with six Gierymskis and seven Malczewskis and never
came to Matejko, "Arcydzieła muzeów" with 24 nameless antiquities. Of the 71
themes of the owner's catalogue a first page had 8 artists and one of them
on 13 of its 24 places; with this order 16, and 5 (Mateusz 2026-11-11:
"Dzieła w Odkrywaj mają być po prostu dobre", and no e-paper score).
Good is what the catalogue knows of a work, not what anyone thinks of it: a
museum's highlight, a maker's name, a description, a picture large enough.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Callable, Hashable
from typing import Any

from .artists import ArtistNames, is_artist, known_names, name_key
from .images import WEAK_SIDE, said_side
from .models import Item
from .vocabulary import archive_own

#: What a work is worth before the day's draw: a museum's highlight, ...
HIGHLIGHT = 1.0
#: ... a work with its maker's name (not "Unknown", "Roman, 1st century"), ...
NAMED = 0.6
#: ... one its museum wrote about.
DESCRIBED = 0.2
DESCRIBED_LENGTH = 200
#: A title that calls the work a sketch or studies (put behind; the curator
#: of the work of the day may still choose one that stands by itself).
SKETCH_TITLE = re.compile(
    r"\b(stud(?:y|ies)|sketch(?:es|book|ing)?|croquis|esquisses?|[ée]tudes?|studien?"
    r"|skizzen?(?:buch)?|schets(?:en|boek)?|szkic\w*|studi(?:um|a)|notebook|carnet)\b",
    re.IGNORECASE,
)
SKETCH_PENALTY = 0.3
#: An art archive's old slide of the work, in its colours only by chance.
ARCHIVE_PENALTY = 0.75
#: The copy's quality (Mateusz 2026-11-11: "bierz pod uwagę także jakość
#: kopii dzieła"): a picture as long as the frame's side (2560 px) shows
#: the work whole, one shorter than ``images.WEAK_SIDE`` is worth a sharper
#: copy, which may not be found.
FRAME_SIDE = 2560
SHARP_BONUS = 0.15
WEAK_PENALTY = 0.25
#: How much the day's draw adds at most: half a highlight, so a page is
#: about half other works the next day and a highlight still mostly first.
DRAW = 0.5
#: What each further work by one hand (the nameless together) loses, and
#: the most of it: an artist's best work stands where it is worth, the
#: others between other artists' works.
AGAIN = 0.15
AGAIN_MOST = 1.0
#: The same, less, for each further work of one museum: the museums that
#: write about their works (Cleveland) or say their pictures' sizes would
#: else have a theme's whole first page ("Arcydzieła muzeów": 23 of 24).
SAME_MUSEUM = 0.02
SAME_MUSEUM_MOST = 0.4


def sketch_title(item: Item) -> bool:
    """The museum calls the work a sketch, studies or a sketchbook page."""
    return bool(SKETCH_TITLE.search(item.title))


def copy_quality(item: Item) -> float:
    """What the copy's size adds to (or takes from) a work's score; nothing
    when its museum says no size (``images.said_side``)."""
    side = said_side(item)
    if side is None:
        return 0.0
    if side >= FRAME_SIDE:
        return SHARP_BONUS
    return -WEAK_PENALTY if side < WEAK_SIDE else 0.0


def worth(item: Item) -> float:
    """How good ``item`` is to propose, whatever was asked for."""
    value = HIGHLIGHT * item.highlight
    value += NAMED * is_artist(item.artist)
    value += DESCRIBED * (len(item.description) >= DESCRIBED_LENGTH)
    value += copy_quality(item)
    value -= SKETCH_PENALTY * sketch_title(item)
    value -= ARCHIVE_PENALTY * archive_own(item)
    return value


def _hand(item: Item, names: ArtistNames) -> Hashable:
    """Whose work ``item`` is, the same for every spelling of one person;
    the nameless are one hand."""
    if not is_artist(item.artist):
        return ""
    person = names.person(item.artist)
    return person if person is not None else name_key(item.artist)


def _draw(key: bytes, item: Item) -> float:
    """``item``'s own draw for the day, 0..1: each work draws by itself, so
    a work that comes into the catalogue moves no other."""
    drawn = hashlib.blake2b(item.id.encode(), digest_size=8, key=key).digest()
    return int.from_bytes(drawn, "big") / 2**64


def good_first(
    items: list[Item],
    seed: int = 0,
    salt: str = "",
    fits: Callable[[Item], tuple[Any, ...]] | None = None,
) -> list[Item]:
    """``items`` with the good ones first: by :func:`worth` and a draw of
    ``seed`` (the day) and ``salt`` (what was asked, so a work lucky in one
    theme is not in all), each further work by the same hand behind other
    hands' works, and a little so each further work of one museum.
    ``fits``: how well each fits what was asked, compared before all that
    (``repo.relevance``'s first fields)."""
    key = hashlib.blake2b(f"{seed}|{salt}".encode(), digest_size=16).digest()
    names = known_names()
    score = {item.id: worth(item) + DRAW * _draw(key, item) for item in items}
    seen: Counter[Hashable] = Counter()
    museums: Counter[str] = Counter()
    for item in sorted(items, key=lambda i: -score[i.id]):
        hand = _hand(item, names)
        score[item.id] -= min(AGAIN * seen[hand], AGAIN_MOST)
        score[item.id] -= min(SAME_MUSEUM * museums[item.source], SAME_MUSEUM_MOST)
        seen[hand] += 1
        museums[item.source] += 1
    if fits is None:
        return sorted(items, key=lambda i: -score[i.id])
    return sorted(items, key=lambda i: (*fits(i), -score[i.id]))
