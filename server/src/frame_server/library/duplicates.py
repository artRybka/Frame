"""The same work from several sources.

Aggregators carry the museums' works again (Openverse has the Met's and
Commons' files, Europeana the Rijksmuseum's, Commons nearly everything),
so a search over all of them, or a rotation filled from all of them, finds
one painting two or three times. Copies are told apart by title and
artist, with the year and the picture's shape as checks; the copy kept is
the one from the most reliable source: a museum before Europeana, Commons,
Openverse and WikiArt.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from functools import lru_cache
from urllib.parse import unquote

from .models import Item, ItemKind
from .vocabulary import fold

#: Lower is more reliable: museums describe their own works; Europeana
#: passes on what its member collections say; Commons, Openverse and WikiArt
#: are written by volunteers or gathered from elsewhere.
RANKS = {
    "aic": 0,
    "cma": 0,
    "met": 0,
    "rijks": 0,
    "europeana": 1,
    "wmc": 2,
    "openverse": 3,
    "wikiart": 4,
}
#: Sources not in ``RANKS``.
OTHER_RANK = 5
#: Copies of one work are dated a year or two apart (begun, finished).
YEAR_SLACK = 2
#: Copies of one work are cropped differently, with or without the frame.
ASPECT_SLACK = 1.15

#: Articles and the like, which sources put in or leave out.
# fmt: off
STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "and", "in", "on", "at", "to", "with", "by", "from",
        "de", "het", "een", "van", "en", "op",
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "und", "im", "am", "zu",
        "von", "mit",
        "le", "la", "les", "l", "un", "une", "du", "et", "au", "aux", "d", "sur",
        "il", "lo", "gli", "i", "el", "los", "las", "y", "del", "al", "con",
        "o", "w", "z", "na",
    }
)
# fmt: on
#: Words that only say where a file comes from (Commons file names).
NOISE = re.compile(r"google art project|google cultural institute|\bcropped\b|\bdetail\b")
#: Titles shared by many works of one artist: copies need a year to match.
GENERIC = frozenset(
    {
        "untitled",
        "bez tytulu",
        "landscape",
        "portrait",
        "self portrait",
        "selfportrait",
        "study",
        "sketch",
        "still life",
        "head",
        "nude",
        "figure",
        "composition",
        "view",
        "seascape",
        "flowers",
        "portrait man",
        "portrait woman",
        "portrait young woman",
        "portrait young man",
        "portrait lady",
        "portrait gentleman",
        "pejzaz",
        "martwa natura",
        "autoportret",
        "portret",
    }
)
#: Names that are no artist at all.
NOBODY = frozenset({"unknown", "anonymous", "unidentified", "nieznany", "anonim", "artist"})


def rank(source: str) -> int:
    return RANKS.get(source, OTHER_RANK)


def _clean_name(artist: str) -> str:
    """ "Vincent van Gogh (1853–1890)\\n…" -> "vincent van gogh";
    "Gogh, Vincent van" -> "vincent van gogh"."""
    name = fold(artist.split("\n")[0])
    name = re.sub(r"[(\[].*$", "", name)
    name = re.sub(r"\d+", " ", name)
    last, comma, first = name.partition(",")
    if comma and first.strip() and "," not in first:
        name = f"{first} {last}"
    return " ".join(re.findall(r"[^\W\d_]+", name))


@lru_cache(maxsize=1 << 15)
def artist_words(artist: str) -> frozenset[str]:
    words = frozenset(_clean_name(artist).split())
    return frozenset() if words <= NOBODY else words


@lru_cache(maxsize=1 << 15)
def surname(artist: str) -> str:
    """The last word of the name: what most sources agree on."""
    words = _clean_name(artist).split()
    return "" if not words or set(words) <= NOBODY else words[-1]


@lru_cache(maxsize=1 << 16)
def title_key(title: str, artist: str = "") -> str:
    """The title's words without articles, dates, brackets and, in Commons
    file names, the artist: "Claude Monet - The Water Lilies (1906) - Google
    Art Project" -> "water lilies"."""
    text = fold(title.split("\n")[0])
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)
    text = re.sub(r"\.(jpe?g|png|tiff?)$", "", text)
    name = artist_words(artist)
    parts = [p for p in re.split(r"\s+[-–—]\s+|\s*[|/]\s*", text) if p.strip()]
    kept = [
        p
        for p in parts
        if not NOISE.fullmatch(p.strip())
        and not (name and set(re.findall(r"[^\W\d_]+", p)) <= name)
    ]
    text = NOISE.sub(" ", " ".join(kept or parts))
    words = [w for w in re.findall(r"[^\W_]+", text) if w not in STOPWORDS]
    return " ".join(w for w in words if not re.fullmatch(r"\d{4}", w))


@lru_cache(maxsize=1 << 16)
def _link(url: str) -> str:
    """A page or picture's address written one way."""
    link = unquote(url).strip().casefold()
    return re.sub(r"^https?://(www\.)?", "", link).rstrip("/")


def _links(item: Item) -> set[str]:
    return {link for url in (item.url, item.image_url) if (link := _link(url))}


def work_key(item: Item) -> str:
    """A key copies of one work usually share: the artist's surname and
    the title's words; the year as well for titles like "Landscape". Empty
    when the item says too little."""
    if item.kind != ItemKind.ARTWORK:
        return ""
    title = title_key(item.title, item.artist)
    name = surname(item.artist)
    if not title or not name:
        return ""
    if title in GENERIC:
        return f"{name}|{title}|{item.year or ''}"
    return f"{name}|{title}"


def same_work(a: Item, b: Item) -> bool:
    """``a`` and ``b`` are copies of one work from two sources."""
    if a.id == b.id:
        return True
    if a.kind != ItemKind.ARTWORK or b.kind != ItemKind.ARTWORK or a.source == b.source:
        return False
    if _links(a) & _links(b):
        return True
    title = title_key(a.title, a.artist)
    if not title or title != title_key(b.title, b.artist):
        return False
    have, other = artist_words(a.artist), artist_words(b.artist)
    if not have or not other:
        return False
    if not (have <= other or other <= have or surname(a.artist) == surname(b.artist)):
        return False
    if a.year is not None and b.year is not None:
        if abs(a.year - b.year) > YEAR_SLACK:
            return False
    elif title in GENERIC:
        return False
    if a.width and a.height and b.width and b.height:
        ratio = (a.width / a.height) / (b.width / b.height)
        if max(ratio, 1 / ratio) > ASPECT_SLACK:
            return False
    return True


def preference(item: Item) -> tuple[bool, int]:
    """Sort key, best copy first: kept by the owner, then the most
    reliable source."""
    return item.pooled, rank(item.source)


class Works:
    """Items grouped into works, each group with one copy per source at
    most; a group's first item is its best copy."""

    def __init__(self, items: Iterable[Item] = ()) -> None:
        self.groups: list[list[Item]] = []
        self._group: dict[str, int] = {}
        self._by_title: dict[str, list[int]] = defaultdict(list)
        self._by_link: dict[str, list[int]] = defaultdict(list)
        for item in sorted(items, key=preference):
            self.add(item)

    def group_of(self, item: Item) -> int | None:
        """The group holding ``item``, or the one it would join: with a copy
        of it and no other item from its source."""
        if item.id in self._group:
            return self._group[item.id]
        if item.kind != ItemKind.ARTWORK:
            return None
        found = set(self._by_title.get(title_key(item.title, item.artist), ()))
        for link in _links(item):
            found.update(self._by_link.get(link, ()))
        for index in sorted(found):
            group = self.groups[index]
            if all(i.source != item.source for i in group) and any(
                same_work(i, item) for i in group
            ):
                return index
        return None

    def add(self, item: Item) -> int:
        """Put ``item`` in its group (a new one if none fits); returns the group."""
        index = self.group_of(item)
        if index is not None and item.id in self._group:
            return index
        if index is None:
            index = len(self.groups)
            self.groups.append([])
        group = self.groups[index]
        # After the copies it is not better than: the best stays first.
        at = next((n for n, i in enumerate(group) if preference(item) < preference(i)), len(group))
        group.insert(at, item)
        self._group[item.id] = index
        if item.kind == ItemKind.ARTWORK:
            if title := title_key(item.title, item.artist):
                self._by_title[title].append(index)
            for link in _links(item):
                self._by_link[link].append(index)
        return index

    def spare(self) -> set[str]:
        """Ids of needless copies: works the server added (``pooled``) of
        which the owner kept another copy, or the server holds one from a
        more reliable source. Copies the owner kept all stay."""
        return {i.id for group in self.groups for i in group[1:] if i.pooled}

    def best(self, item: Item) -> Item | None:
        """The best copy of ``item``'s work, if one is here."""
        index = self.group_of(item)
        return None if index is None else self.groups[index][0]


def dedupe(items: list[Item]) -> list[Item]:
    """``items`` with each work once, in its best copy, where its first copy
    was."""
    works = Works(items)
    result: list[Item] = []
    seen: set[int] = set()
    for item in items:
        index = works.group_of(item)
        assert index is not None
        if index not in seen:
            seen.add(index)
            result.append(works.groups[index][0])
    return result
