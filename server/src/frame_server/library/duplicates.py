"""The same work from several sources.

Aggregators carry the museums' works again (Openverse has the Met's and
Commons' files, Europeana the Rijksmuseum's, Commons nearly everything),
so a search over all of them, or a rotation filled from all of them, finds
one painting two or three times. Copies are told apart by title and
artist, with the year and the picture's shape as checks; the copy kept is
the one from the most reliable source: a museum before Europeana, Commons,
Openverse and WikiArt. An art history archive's photograph of a work on
Europeana (Foto Marburg's colour slides, faded blue and pale) comes after
them all. Copies whose titles share nothing ("Lekcja muzyki", "The music
lesson") are found by their pictures (``twins``, ``Item.copy_of``).
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from collections.abc import Iterable
from functools import lru_cache
from typing import NamedTuple
from urllib.parse import unquote

from .artists import NOBODY as NAMELESS
from .artists import ROLES
from .models import Item, ItemKind
from .vocabulary import PER_WORK, fold, is_art_archive_photo

#: Lower is more reliable: museums describe their own works; Europeana
#: passes on what its member collections say; Commons, Openverse and WikiArt
#: are written by volunteers or gathered from elsewhere.
RANKS = {
    "aic": 0,
    "cma": 0,
    "met": 0,
    "rijks": 0,
    "smk": 0,
    "nga": 0,
    "mnw": 0,
    "mnk": 0,
    "yale": 0,
    "si": 0,
    "paris": 0,
    "vam": 0,
    "wellcome": 0,
    "courtauld": 0,
    "louvre": 0,
    "loc": 0,
    "getty": 0,
    "europeana": 1,
    "wmc": 2,
    "openverse": 3,
    "wikiart": 4,
}
#: Sources not in ``RANKS``.
OTHER_RANK = 5
#: An art history archive's photograph of a work (Europeana's Foto
#: Marburg: 95 of its first 100 van Goghs, 2026-11-09), after every copy
#: from elsewhere: Marburg's colour slides were taken decades ago and their
#: dyes have faded (no yellow left, skies white and blue), while Commons
#: and WikiArt have the museums' own scans.
ARCHIVE_PHOTO_RANK = OTHER_RANK + 1
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
NOISE = re.compile(r"google art project\w*|google cultural institute|\bcropped\b|\bdetail\b")
#: Where Commons' descriptions go on with the work's other titles.
OTHER_TITLES = re.compile(r"\b(?:inne tytuly|other titles?|also known as)\b")
#: Parts of Commons file names that say where the work hangs or which scan
#: this is: "… - WGA24652", "… - 406 - Mauritshuis", "…, The Metropolitan
#: Museum of Art", "… - rijksmuseum - 001".
PART_NOISE = re.compile(
    r"wga\d+|\d+|negative|(the )?metropolitan museum( of art)?|national gallery( of art)?|"
    r"london|washington|mauritshuis|rijksmuseum|louvre|musee du louvre|prado|uffizi|"
    r"(the )?art institute of chicago|cleveland museum of art|nationalmuseum|"
    r"kunsthistorisches museum|gemaldegalerie( alte meister)?"
)
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
#: Aggregators: their items come from many collections, two of which may
#: hold copies of one work.
AGGREGATORS = frozenset({"openverse", "europeana"})
#: Collections of files rather than works: Commons has several scans of
#: many paintings ("Het melkmeisje" five times), as has Openverse of it.
FILES = frozenset({"wmc", "openverse:commons.wikimedia.org", "openverse:flickr.com"})
#: Europeana datasets that keep the museum's inventory number in the record
#: id ("90402/SK_A_2344"): dataset -> the museum's key.
EUROPEANA_SETS = {"90402": "rijks"}
#: The Rijksmuseum's inventory number at the end of its page address
#: (".../object/SK-A-2344--42dd…").
RIJKS_NUMBER = re.compile(r"rijksmuseum\.nl/.*/([a-z]{1,4}-[a-z0-9_.-]+?)(?:--[0-9a-f]+)?$")
#: Names that are no artist at all.
NOBODY = NAMELESS | ROLES


def rank(source: str) -> int:
    return RANKS.get(source, OTHER_RANK)


def item_rank(item: Item) -> int:
    """How reliable ``item``'s copy is (lower: more): its source's
    :func:`rank`, an art archive's photograph last."""
    return ARCHIVE_PHOTO_RANK if is_art_archive_photo(item) else rank(item.source)


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


@lru_cache(maxsize=PER_WORK)
def artist_words(artist: str) -> frozenset[str]:
    words = frozenset(_clean_name(artist).split())
    return frozenset() if words <= NOBODY else words


@lru_cache(maxsize=PER_WORK)
def surname(artist: str) -> str:
    """The last word of the name: what most sources agree on."""
    words = _clean_name(artist).split()
    return "" if not words or set(words) <= NOBODY else words[-1]


def _names(part: str, artist: str) -> bool:
    """``part`` of a title only names the artist: "Vincent van Gogh", or as
    file names on Commons have it, "Jan Vermeer van Delft" for Johannes
    Vermeer (his surname, at most two other words)."""
    name = artist_words(artist)
    words = set(re.findall(r"[^\W\d_]+", part)) - STOPWORDS
    if not name or not words:
        return False
    return words <= name or (surname(artist) in words and len(words - name) <= 2)


@lru_cache(maxsize=PER_WORK)
def title_key(title: str, artist: str = "") -> str:
    """The title's words without articles, dates, brackets and, in Commons
    file names, the artist: "Claude Monet - The Water Lilies (1906) - Google
    Art Project" -> "water lilies"."""
    text = fold(title.split("\n")[0])
    # Commons' "Woman reading a letter.[1] Inne tytuły: Woman in Blue…".
    text = OTHER_TITLES.split(text, maxsplit=1)[0]
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)
    text = re.sub(r"\.(jpe?g|png|tiff?)$", "", text)
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+|\s*[|/,]\s*", text) if p.strip()]
    kept = [
        p
        for p in parts
        if not NOISE.fullmatch(p) and not PART_NOISE.fullmatch(p) and not _names(p, artist)
    ]
    text = NOISE.sub(" ", " ".join(kept or parts))
    words = [w for w in re.findall(r"[^\W_]+", text) if w not in STOPWORDS]
    return " ".join(w for w in words if not re.fullmatch(r"\d{4}", w))


@lru_cache(maxsize=PER_WORK)
def _link(url: str) -> str:
    """A page or picture's address written one way."""
    link = unquote(url).strip().casefold()
    return re.sub(r"^https?://(www\.)?", "", link).rstrip("/")


def _inventory(item: Item) -> str:
    """The museum's inventory number, as a pseudo address, where the item
    tells it: a Rijksmuseum page, a Europeana record of its dataset."""
    if item.source == "europeana":
        dataset, _, number = item.source_id.partition("~")
        if museum := EUROPEANA_SETS.get(dataset):
            return f"inventory:{museum}:{number.replace('_', '-').casefold()}"
    elif match := RIJKS_NUMBER.search(_link(item.url)):
        return f"inventory:rijks:{match.group(1).replace('_', '-')}"
    return ""


def _copy_links(item: Item) -> set[str]:
    """Pseudo addresses copies found by their pictures share (``Item.copy_of``,
    ``library.twins``): the item's own and the one it is a copy of."""
    links = {f"copy:{item.id}"}
    if item.copy_of:
        links.add(f"copy:{item.copy_of}")
    return links


def _links(item: Item) -> set[str]:
    links = {link for url in (item.url, item.image_url) if (link := _link(url))}
    if inventory := _inventory(item):
        links.add(inventory)
    return links | _copy_links(item)


def _twins(a: Item, b: Item) -> bool:
    """``a`` and ``b`` were found to show one picture (``library.twins``)."""
    return bool((a.copy_of or b.copy_of) and _copy_links(a) & _copy_links(b))


def origin(item: Item) -> str:
    """The collection an item comes from: its source, or for an aggregator
    the collection it passes on (Openverse: the site of its page; Europeana:
    its dataset). A museum's works are never copies of each other."""
    if item.source == "openverse":
        return f"openverse:{_link(item.url).split('/', 1)[0]}"
    if item.source == "europeana":
        return f"europeana:{item.source_id.partition('~')[0]}"
    return item.source


def work_key(item: Item) -> str:
    """A key copies of one work usually share: the artist's surname and
    the title's words; the year as well for titles like "Landscape". Empty
    when the item says too little."""
    if item.kind != ItemKind.ARTWORK or item.part_of:
        return ""  # a fragment (library.fragments) is no copy of its work
    title = title_key(item.title, item.artist)
    name = surname(item.artist)
    if not title or not name:
        return ""
    if title in GENERIC:
        return f"{name}|{title}|{item.year or ''}"
    return f"{name}|{title}"


def _apart(a: Item, b: Item) -> bool:
    """``a`` and ``b`` can't be copies of one work: they come from one
    collection, and only file collections hold several of a work (or their
    pictures showed them to be one: WikiArt has some works twice)."""
    return origin(a) == origin(b) and origin(a) not in FILES and not _twins(a, b)


def same_work(a: Item, b: Item) -> bool:
    """``a`` and ``b`` are copies of one work: from two sources, or two files
    of it on Commons."""
    if a.id == b.id:
        return True
    if a.kind != ItemKind.ARTWORK or b.kind != ItemKind.ARTWORK or _apart(a, b):
        return False
    if a.part_of or b.part_of:
        return False  # fragments (library.fragments) are parts, not copies
    if _links(a) & _links(b):
        return True
    files = origin(a) == origin(b)
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
    elif title in GENERIC or files:
        # One artist's paintings of a name (a series) set apart by the year.
        return False
    if a.width and a.height and b.width and b.height:
        ratio = (a.width / a.height) / (b.width / b.height)
        if max(ratio, 1 / ratio) > ASPECT_SLACK:
            return False
    elif files:
        return False
    return True


#: The fields grouping looks at (:func:`same_work`, :func:`origin`,
#: :func:`preference`): a change of another one leaves the groups as they are.
GROUPING_FIELDS = frozenset(
    {
        "kind",
        "source",
        "source_id",
        "title",
        "artist",
        "year",
        "width",
        "height",
        "url",
        "image_url",
        "pooled",
        "copy_of",
    }
)


def regroups(old: Item, new: Item) -> bool:
    """Whether ``old`` becoming ``new`` may change the groups. Only works
    of art are grouped: anything else (an album photo with a fresh signed
    link) stays alone in its group whatever it says."""
    if old.kind != ItemKind.ARTWORK and new.kind != ItemKind.ARTWORK:
        return False
    return any(getattr(old, f) != getattr(new, f) for f in GROUPING_FIELDS)


def preference(item: Item) -> tuple[bool, bool, int]:
    """Sort key, best copy first: an art archive's photograph after every
    other copy, even one the owner kept (Mateusz 2026-11-09: a heart or a
    playlist says nothing of the picture); then kept by the owner, then the
    most reliable source."""
    return is_art_archive_photo(item), item.pooled, item_rank(item)


class Works:
    """Items grouped into works, each group with one copy per collection
    (:func:`origin`) at most, but for files (:data:`FILES`); a group's first
    item is its best copy."""

    def __init__(self, items: Iterable[Item] = ()) -> None:
        self.groups: list[list[Item]] = []
        self._group: dict[str, int] = {}
        self._by_title: dict[str, list[int]] = defaultdict(list)
        self._by_link: dict[str, list[int]] = defaultdict(list)
        #: Goes up with every change; :meth:`spare` as last worked out.
        self._changes = 0
        self._spare: tuple[int, frozenset[str], frozenset[str]] | None = None
        for item in sorted(items, key=preference):
            self.add(item)

    def group_of(self, item: Item) -> int | None:
        """The group holding ``item``, or the one it would join: with a copy
        of it and no other item from its collection (files aside)."""
        if item.id in self._group:
            return self._group[item.id]
        if item.kind != ItemKind.ARTWORK:
            return None
        found = set(self._by_title.get(title_key(item.title, item.artist), ()))
        for link in _links(item):
            found.update(self._by_link.get(link, ()))
        for index in sorted(found):
            group = self.groups[index]
            if not any(_apart(i, item) for i in group) and any(same_work(i, item) for i in group):
                return index
        return None

    def group_index(self, item_id: str) -> int | None:
        """The group ``item_id`` is in, if it is grouped here."""
        return self._group.get(item_id)

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
        self._changes += 1
        if item.kind == ItemKind.ARTWORK:
            if title := title_key(item.title, item.artist):
                self._by_title[title].append(index)
            for link in _links(item):
                self._by_link[link].append(index)
        return index

    def replace(self, item: Item) -> bool:
        """The grouped copy of ``item`` swapped for this one, in its place;
        only for a change :func:`regroups` lets through. False when ``item``
        is not grouped here."""
        index = self._group.get(item.id)
        if index is None:
            return False
        group = self.groups[index]
        for n, held in enumerate(group):
            if held.id == item.id:
                group[n] = item
                self._changes += 1
                return True
        return False

    def remove(self, item_id: str) -> bool:
        """``item_id`` taken out when it is alone in its group: the other
        groups are what they would be without it. False (nothing changed)
        when it has copies: they may have been grouped through it, and only
        grouping them again tells."""
        index = self._group.get(item_id)
        if index is None:
            return True
        if len(self.groups[index]) != 1:
            return False
        self.groups[index] = []  # the other groups keep their numbers
        del self._group[item_id]
        self._changes += 1
        return True

    def spare(self, skip: Iterable[str] = ()) -> frozenset[str]:
        """Ids of needless copies: works the server added (``pooled``) of
        which the owner kept another copy, or the server holds one from a
        more reliable source. Copies the owner kept all stay. Copies from
        the sources ``skip`` don't count: the next copy takes their place.
        Kept while nothing changes (every search asks: 20 ms of 79 000)."""
        left_out = frozenset(skip)
        kept = self._spare
        if kept is not None and kept[0] == self._changes and kept[1] == left_out:
            return kept[2]
        changes = self._changes
        found = frozenset(
            i.id
            for group in self.groups
            for i in [i for i in group if i.source not in left_out][1:]
            if i.pooled
        )
        if not left_out:
            self._spare = (changes, left_out, found)
        return found

    def once(self, items: list[Item]) -> list[Item]:
        """``items`` (grouped here) with each work once: of its copies among
        them the best, where they were."""
        kept: dict[int, tuple[int, str]] = {}
        for item in items:
            index = self._group.get(item.id)
            if index is None:
                continue
            group = self.groups[index]
            # None: taken out meanwhile (``remove``, from another thread).
            place = next((n for n, i in enumerate(group) if i.id == item.id), None)
            if place is None:
                continue
            if index not in kept or place < kept[index][0]:
                kept[index] = (place, item.id)
        best = {item_id for _, item_id in kept.values()}
        return [i for i in items if i.id in best or i.id not in self._group]

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


class Taken(NamedTuple):
    item: Item
    #: What copies of the work share: :func:`work_key` of the first copy
    #: that has one.
    work: str
    #: The id of the worse copy shown before, which ``item`` replaces.
    replaces: str | None


class Shown:
    """Works already shown, for answers that come one after another (a
    search's museums as each answers, its later pages): each work once, and
    a better copy in place of the one shown before it came. Safe to share
    between threads."""

    def __init__(self) -> None:
        self._works = Works()
        #: Group -> the copy shown.
        self._shown: dict[int, Item] = {}
        self._lock = threading.Lock()

    def take(self, items: Iterable[Item]) -> list[Taken]:
        """Of ``items``, the works not shown yet and better copies of those
        shown; from now on they count as shown."""
        taken: list[Taken] = []
        with self._lock:
            for item in items:
                index = self._works.add(item)
                shown = self._shown.get(index)
                if shown is not None and (
                    shown.id == item.id or preference(shown) <= preference(item)
                ):
                    continue
                self._shown[index] = item
                work = next((k for i in self._works.groups[index] if (k := work_key(i))), "")
                taken.append(Taken(item, work, shown.id if shown is not None else None))
        return taken
