"""SQLite-backed library: items, playlists, key-value state, display history.

Items and playlists are stored as JSON documents. The library is small
(hundreds to a few thousand pictures), so filtering happens in memory on a
cached copy; SQLite gives durability and atomic writes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import sqlite3
import threading
import time
import weakref
from collections import Counter, OrderedDict
from collections.abc import Callable, Collection, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, NamedTuple

from .artists import IDS_STATE, PEOPLE_STATE, is_artist, known_names, learn, made_by
from .colors import has_colours, shown_tags
from .duplicates import Works, dedupe, regroups
from .models import (
    MINE,
    MINE_FAVORITES,
    MINE_PLAYLISTS,
    AlbumSync,
    ColorSwatch,
    Facets,
    FacetValue,
    Item,
    Note,
    PlaceCount,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    PlaylistSummary,
)
from .phrases import fold as phrase_fold
from .phrases import has_phrase, parsed
from .places import Places, known_places, learn_places
from .search_index import SearchIndex, item_text
from .term_index import TermIndex
from .viewer import OWNER_ID, STORE, viewer_id
from .vocabulary import (
    is_art_archive_photo,
    is_document,
    is_grey_copy,
    is_postal,
    matches_terms,
    object_category,
    searched_kinds,
    set_aside,
)

#: Item fields that tell copies of a work apart or choose between them.
log = logging.getLogger(__name__)

#: Seconds the places of the catalogue's works are kept while nothing changes.
PLACES_KEPT = 600.0
#: Seconds they are kept whatever the library does meanwhile.
PLACES_FRESH = 90.0
#: Seconds between rebuilds of the suggestions' artists while the library
#: changes (their counts are always the search's own, asked afresh).
TERM_INDEX_EVERY = 60.0
#: Share of the search index's entries changed since it was made at which
#: it is made anew in the background.
SEARCH_DEAD_SHARE = 0.3
#: A library this small makes its search index when first asked; a larger
#: one makes it in the background and searches item after item meanwhile.
SEARCH_INLINE = 5000
#: Searches whose whole answer is kept for their next pages (while the
#: library stays as it is).
QUERIES_KEPT = 16


class _Counted(NamedTuple):
    """A smart playlist's count and cover as worked out (a search through
    the whole catalogue, a second or more on a NAS)."""

    #: The playlist as it was then (its rules, its limit...).
    key: str
    #: The library then: items, playlists, hearts (:meth:`Library._stamp`).
    stamp: tuple[int, int, int]
    total: int
    cover: list[str]
    colors: list[ColorSwatch]


def _cover(items: list[Item]) -> tuple[list[str], list[ColorSwatch]]:
    """A playlist's cover: its four most suitable works, and their colours."""
    best = sort_items(items, "suitability")[:4]
    return [i.id for i in best], cover_colors(best)


def _personal(playlist: Playlist) -> bool:
    """Made of someone's hearts or playlists: counted afresh once those
    change, not shown as they were."""
    return playlist.rules.favorites_only or any(t in MINE for t in playlist.rules.terms)


#: A regrouping of the works this slow is logged as such: the library
#: waits for it.
SLOW_WORKS = 1.0
#: Groupings made outside the lock before one is made holding it, when
#: changes that regroup keep coming meanwhile.
WORKS_ATTEMPTS = 3


def _apply(works: Works, changes: list[tuple[Item | None, Item | None]]) -> bool:
    """The changes made while ``works`` was made, applied to it; False when
    one may change its groups (it is made again)."""
    for old, new in changes:
        if new is None:
            if old is None or not works.remove(old.id):
                return False
        elif old is None:
            works.add(new)
        elif regroups(old, new) or not works.replace(new):
            return False
    return True


#: The playlist "Historia przesłanych" (see ``Player.remember_sent``); one
#: for each person (the owner's under the key from before, ``sent_key``).
SENT_KEY = "sent_photos_playlist"
#: Each person's order of the cards in Playlisty (playlist ids), under
#: ``playlist_order:<user id>``; set by moving a card in the app.
ORDER_KEY = "playlist_order"
#: Hearts were moved from ``Item.favorite`` to the owner's in ``favorites``.
FAVORITES_MOVED_KEY = "favorites_moved"
#: What was learnt of the museums (:class:`.places.Places`).
PLACES_STATE = "places"


def sent_key(user_id: str) -> str:
    return SENT_KEY if user_id == OWNER_ID else f"{SENT_KEY}:{user_id}"


SortKey = Literal[
    "recent", "title", "artist", "year", "random", "suitability", "shown", "relevance"
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    shown_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ai_notes (
    item_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_id, kind)
);
CREATE INDEX IF NOT EXISTS ai_notes_kind ON ai_notes (kind);
CREATE TABLE IF NOT EXISTS favorites (
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, item_id)
);
"""


_NOTE_COLUMNS = "item_id, kind, model, prompt_version, source_hash, data, created_at"


def _note(row: tuple[Any, ...]) -> Note:
    item_id, kind, model, version, source_hash, data, created_at = row
    return Note(
        item_id=item_id,
        kind=kind,
        model=model,
        prompt_version=version,
        source_hash=source_hash,
        data=json.loads(data),
        created_at=created_at,
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _fold(values: Iterable[str]) -> set[str]:
    return {v.casefold() for v in values if v}


def _searches(rules: PlaylistRules) -> bool:
    """Rules that look for works (not just "the favourites" or "everything")."""
    return bool(
        rules.query.strip()
        or rules.artists
        or rules.styles
        or rules.subjects
        or any(t not in MINE for t in rules.terms)
        or rules.colors
        or rules.year_from is not None
        or rules.year_to is not None
    )


def _is_mine(item: Item, mine: list[str], listed: Collection[str], liked: bool) -> bool:
    """``item`` is one of the person's works ``mine`` asks for (either)."""
    return (MINE_FAVORITES in mine and liked) or (MINE_PLAYLISTS in mine and item.id in listed)


#: Museum searches a work remembers it was found by (``Item.found_for``),
#: the latest kept.
FOUND_KEEP = 24


def found_together(had: list[str], found: list[str]) -> list[str]:
    """The searches of ``had`` and then ``found``, each once, the latest
    :data:`FOUND_KEEP`."""
    keys = list(dict.fromkeys(k for k in [*had, *found] if k))
    return keys[-FOUND_KEEP:]


def search_fits(item: Item, rules: PlaylistRules) -> bool:
    """Whether a work the museums' search found for ``rules`` fits them in
    what that search doesn't decide itself: the artists (museums find
    whatever names them: Guillaumin's self-portrait for Van Gogh, Mateusz
    2026-11-07), periods (with their places), tags and two techniques at
    once. Szukaj shows what passes, and the catalogue counts it in
    (:func:`matches`, ``Item.found_for``)."""
    if rules.artists and not made_by(item.artist, rules.artists):
        return False
    if item.source == "openverse" and item.classification == "illustration":
        return False  # found before searches left them out (Openverse.search)
    return matches_terms(item, rules.terms, searched_kinds(rules.terms))


def matches(
    item: Item,
    rules: PlaylistRules,
    listed: Collection[str] = (),
    favorites: Collection[str] | None = None,
    key: str | None = None,
    said: list[list[str]] | None = None,
) -> bool:
    """Whether ``item`` fits ``rules``; ``listed`` are the works on the
    person's playlists, for ``mine:playlists``, ``favorites`` their hearts
    (None: anyone's, the stored ``Item.favorite``). A work the museums'
    search for ``rules`` found (``key``: :meth:`PlaylistRules.search_key`,
    worked out when not given) fits as that search judged it: Szukaj and a
    smart playlist of the same choices hold the same works (Mateusz,
    2026-11-07), when it has the words asked (``said``: :func:`said_as`,
    the words as typed when not given; Mateusz 2026-11-09)."""
    liked = item.favorite if favorites is None else item.id in favorites
    if item.excluded or item.id in rules.exclude_ids:
        return False
    # Photographs, sculpture, crafts and manuscripts are found only when
    # asked for, even those the owner kept: Monet's bust is no Monet.
    # Stamps never: Athens 2004's coins are no still life. Nor Foto
    # Marburg's black-and-white prints on a catalogue card. Nor pages of
    # text and printed matter (Mateusz 2026-11-09).
    category = object_category(item)
    if category is not None and category not in rules.terms and _searches(rules):
        return False
    if _searches(rules) and (
        is_postal(item) or is_document(item) or (is_art_archive_photo(item) and is_grey_copy(item))
    ):
        return False
    if rules.favorites_only and not liked:
        return False
    mine = [t for t in rules.terms if t in MINE]
    if mine and not _is_mine(item, mine, listed, liked):
        return False
    if rules.kept_only and item.pooled and not item.favorite:
        return False
    if rules.kinds and item.kind not in rules.kinds:
        return False
    if rules.sources and item.source not in rules.sources:
        return False
    if item.source in rules.exclude_sources:
        return False
    if rules.places or rules.exclude_places:
        places = known_places()
        held_at = item.held_at
        if rules.places and held_at not in {places.canon(p) for p in rules.places}:
            return False
        if held_at and held_at in {places.canon(p) for p in rules.exclude_places}:
            return False
    if item.found_for:
        key = rules.search_key() if key is None else key
        if key and key in item.found_for:
            if not search_fits(item, rules):
                return False
            if not rules.query.strip():
                return True
            return says(item, said_as(rules.query) if said is None else said)
    if rules.artists and not made_by(item.artist, rules.artists):
        return False
    if rules.styles and not _fold(item.styles) & _fold(rules.styles):
        return False
    if rules.subjects and not _fold(item.subjects) & _fold(rules.subjects):
        return False
    if rules.colors and not has_colours(item.color_tags, rules.colors, item.color_shares):
        return False
    if rules.terms and not matches_terms(item, rules.terms):
        return False
    if rules.year_from is not None and (item.year is None or item.year < rules.year_from):
        return False
    if rules.year_to is not None and (item.year is None or item.year > rules.year_to):
        return False
    # ``min_suitability`` of older playlists and themes is no longer kept to
    # (Mateusz, 2026-10-31: the e-paper threshold left out important works).
    if not rules.query:
        return True
    # Each word as typed or as the museums were asked it (``said``).
    return has_words(item, rules.query) if said is None else says(item, said)


@lru_cache(maxsize=256)
def word_start(token: str) -> re.Pattern[str]:
    """A folded text's word starting with ``token`` (folded too)."""
    return re.compile(r"(?<!\w)" + re.escape(phrase_fold(token)))


def has_words(item: Item, query: str) -> bool:
    """Whether ``item`` has every token of ``query`` (:mod:`.phrases`): a
    word starting so anywhere in its texts (case and accents aside: "zolw"
    finds "żółw", "art" no longer Stuttgart), a phrase as a phrase."""
    folded = phrase_fold(item_text(item))
    for token, wanted in parsed(query):
        if " " in token:
            if not has_phrase(wanted, folded, folded=True):
                return False
        elif not word_start(token).search(folded):
            return False
    return True


#: Where a search's words are found, the best first (:func:`relevance`).
_FIELDS = 4


def _check(token: str, wanted: tuple[str, ...]) -> Callable[[str], bool]:
    """Whether a folded text has ``token`` as :func:`has_words` looks for it."""
    if " " in token:
        return lambda text: has_phrase(wanted, text, folded=True)
    pattern = word_start(token)
    return lambda text: pattern.search(text) is not None


def relevance(rules: PlaylistRules) -> Callable[[Item], tuple[Any, ...]]:
    """How well each work fits a search, for "Trafność": first those by the
    artists asked for (the museums' search also finds what only names
    them), then those whose artist has the typed words, their title, their
    keywords and subjects, the rest of their texts; highlights first among
    equals, then by artist and year (Mateusz 2026-11-09: Vermeer's works
    first, not works that mention him)."""
    tokens = parsed(rules.query)
    checks = [_check(token, wanted) for token, wanted in tokens if wanted]
    terms = [t for t in rules.terms if t not in MINE]

    def rank(item: Item) -> tuple[Any, ...]:
        by_them = not rules.artists or made_by(item.artist, rules.artists)
        where = 0
        if checks:
            fields = [
                phrase_fold(item.artist),
                phrase_fold(item.title),
                phrase_fold(" ".join([*item.styles, *item.subjects, *item.keywords])),
                phrase_fold(item_text(item)),
            ]
            for check in checks:
                at = next((n for n, text in enumerate(fields) if check(text)), _FIELDS)
                where = max(where, at)
                if where == _FIELDS:
                    break
        tagged = all(t in item.terms for t in terms)
        return (
            not by_them,
            where,
            not tagged,
            not item.highlight,
            item.artist.casefold(),
            item.year is None,
            item.year or 0,
            item.title.casefold(),
        )

    return rank


def _says(form: str, folded: str) -> bool:
    if " " in form.strip():
        return has_phrase(form, folded, folded=True)
    return word_start(form.strip()).search(folded) is not None


def says(item: Item, said: list[list[str]]) -> bool:
    """Whether ``item`` has each token of a search in one of its forms (as
    typed or translated, :class:`.importer.Asked`): a word at a word's
    start, a phrase as a phrase. A museum finds what it likes for a word
    (Getty's ter Borch and Yale's three sheep for "vermeer"); what has none
    of the words asked is no answer (Mateusz 2026-11-09)."""
    if not said:
        return True
    return says_in(phrase_fold(item_text(item)), said)


def says_in(folded: str, said: list[list[str]]) -> bool:
    """Whether the folded text has each token of a search in one of its
    forms (:func:`says`)."""
    return all(any(_says(form, folded) for form in forms if form.strip()) for forms in said)


def said_as(query: str, wording: Callable[[str], tuple[str, ...]] | None = None) -> list[list[str]]:
    """Each token of ``query`` with its forms: as typed and, with
    ``wording``, as the museums were asked it in their languages."""
    out: list[list[str]] = []
    for token, wanted in parsed(query):
        if not wanted:
            continue
        forms = [token, *(wording(token) if wording is not None else ())]
        out.append(list(dict.fromkeys(f for f in forms if f.strip())))
    return out


def _shown_more(item: Item, other: Item) -> bool:
    """Whether ``item`` stands better for its place than ``other``: a
    favourite, then the one shown more, then a highlight."""
    return (item.favorite, item.show_count, item.highlight) > (
        other.favorite,
        other.show_count,
        other.highlight,
    )


def sort_items(items: list[Item], sort: SortKey, seed: int = 0) -> list[Item]:
    if sort == "title":
        return sorted(items, key=lambda i: i.title.casefold())
    if sort == "artist":
        return sorted(items, key=lambda i: (i.artist.casefold(), i.year or 0))
    if sort == "year":
        return sorted(items, key=lambda i: (i.year is None, i.year or 0))
    if sort == "suitability":
        return sorted(items, key=lambda i: -(i.suitability or 0))
    if sort == "shown":
        return sorted(items, key=lambda i: i.last_shown_at or "", reverse=True)
    if sort == "random":
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        return shuffled
    return sorted(items, key=lambda i: i.added_at, reverse=True)


def cover_colors(items: list[Item]) -> list[ColorSwatch]:
    """The main (heaviest, not accent) colour of each cover work."""
    found: list[ColorSwatch] = []
    for item in items:
        main = [c for c in item.colors if not c.accent]
        if main:
            found.append(max(main, key=lambda c: c.weight))
    return found


class Hidden:
    """The works hidden in the app (:meth:`Library.hidden`): ``ids`` are the
    hidden items and the library's other copies of their works, ``groups``
    those works in ``works``."""

    def __init__(
        self,
        ids: set[str] | None = None,
        groups: set[int] | None = None,
        works: Works | None = None,
    ) -> None:
        self.ids = ids or set()
        self.groups = groups or set()
        self.works = works

    def __bool__(self) -> bool:
        return bool(self.ids)

    def __contains__(self, item: Item) -> bool:
        """Whether ``item`` (also one found at a museum, not in the library)
        is a hidden work or a copy of one."""
        if item.id in self.ids:
            return True
        if not self.groups or self.works is None:
            return False
        return self.works.group_of(item) in self.groups


class Library:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        #: The items, their grouping and the hearts in memory: held only
        #: while they change or are first read, never for a read of the
        #: disk alone (the event loop asks for hearts).
        self._lock = threading.RLock()
        #: The one connection to the disk (:meth:`_db`). Taken after
        #: ``_lock`` when both are held, never before it.
        self._db_lock = threading.RLock()
        self._items: dict[str, Item] | None = None
        self._works: Works | None = None  # the items grouped by work
        #: One grouping is made at a time, outside ``_lock``: the changes
        #: made meanwhile are kept here and applied to it when it is done.
        self._works_lock = threading.Lock()
        self._works_changes: list[tuple[Item | None, Item | None]] | None = None
        #: What made the grouping go since it was last made, and how many
        #: changes did (for the log: a regrouping holds up the library).
        self._works_dropped_by = "start"
        self._works_drops = 0
        self._conn: sqlite3.Connection | None = None
        #: The key/value table, read once (:meth:`_kv_rows`).
        self._kv: dict[str, str] | None = None
        #: State kept by :meth:`keep_state` and not yet on disk, by key: read
        #: before the table, written by the thread "state-writer".
        self._pending: dict[str, str] = {}
        self._pending_lock = threading.Lock()
        self._pending_due = threading.Event()
        self._writer: threading.Thread | None = None
        self._depth = 0  # nested _db() blocks share the outermost transaction
        #: Each person's hearts, replaced (never changed in place) so that
        #: they are read without a lock.
        self._favorites: dict[str, frozenset[str]] | None = None
        #: Goes up with every change of an item (for the suggestions' index).
        self._version = 0
        #: ``places()`` as last counted: (library version, when, places).
        self._places_kept: tuple[int, float, list[PlaceCount]] | None = None
        #: Go up with every change of a playlist, and of someone's hearts.
        self._playlists_version = 0
        self._hearts_version = 0
        #: Goes up when an item joins or leaves the catalogue, or is hidden
        #: or shown again (not with every change, e.g. a picture shown).
        self._catalogue_version = 0
        #: Goes up when a language model's note is kept or forgotten.
        self.notes_version = 0
        #: Each kind's notes as read once and kept up to date since: the
        #: language model's sweep asks for them every minute, and reading
        #: them all from the NAS's disk held the library up for seconds.
        self._notes: dict[str, dict[str, Note]] = {}
        self._notes_lock = threading.Lock()
        #: Smart playlists' counts and covers as last worked out, by id.
        self._counted: dict[int, _Counted] = {}
        #: A smart playlist's count and cover may be shown as last worked
        #: out while the catalogue changed since (the server adding works in
        #: the background): counted afresh when it is opened and at night
        #: (Mateusz, 2026-11-02); set when the server runs its background.
        #: A playlist changed is counted at once, and one of hearts once
        #: they change.
        self.counts_may_lag = False
        #: The catalogue's search index (:class:`SearchIndex`), changed with
        #: every item; one is made at a time, outside ``_lock``, with the
        #: changes made meanwhile kept here and applied when it is done.
        self._search: SearchIndex | None = None
        self._search_lock = threading.Lock()
        self._search_changes: list[tuple[str, Item | None]] | None = None
        self._search_building = False
        #: Translations of a search's words known without asking anyone
        #: (``SearchWords.known``): a work a museum found for "nocna straż"
        #: has "night watch" (:func:`said_as`).
        self.wording: Callable[[str], tuple[str, ...]] | None = None
        #: Searches' whole answers, for their next pages (:meth:`query`).
        self._queries: OrderedDict[tuple[Any, ...], tuple[tuple[Any, ...], list[Item]]] = (
            OrderedDict()
        )
        self._queries_lock = threading.Lock()
        #: ``hidden()`` as last worked out: (catalogue version, works, it).
        self._hidden_kept: tuple[int, Works, Hidden] | None = None
        self._term_index: TermIndex | None = None
        self._term_index_lock = threading.Lock()
        self._term_index_building = False
        self._term_index_built_at = 0.0
        with self._db() as db:
            db.executescript(SCHEMA)
        self._move_favorites()
        self._kv_rows()  # read once here, never on the event loop
        # Museums learnt from Wikidata, for every work's place (models).
        learn_places(Places.from_state(self.get_state(PLACES_STATE)))

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        """The library's one connection, a transaction per outermost block.

        A connection per call made SQLite checkpoint and sync the disk on
        every close: several syncs per write, minutes for a few thousand
        writes on a NAS hard disk. In WAL mode ``synchronous=NORMAL`` stays
        consistent after a power cut and syncs only at checkpoints.

        It holds its own lock, not the library's: a long read of the disk
        (the language model's notes) no longer holds up the hearts, the
        items and with them the event loop (2026-11-09, 20-44 s stalls)."""
        with self._db_lock:
            if self._conn is None:
                conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                self._conn = conn
                weakref.finalize(self, conn.close)
            conn = self._conn
            if self._depth:
                yield conn
                return
            self._depth += 1
            try:
                with conn:
                    yield conn
            except BaseException:
                self._items = None  # the cache may hold rolled back changes
                self._kv = None
                self._drop_works("a rolled back write")
                self._version += 1
                self._catalogue_version += 1
                self._favorites = None
                self._hearts_version += 1
                with self._notes_lock:
                    self._notes.clear()
                raise
            finally:
                self._depth -= 1

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Make the writes inside one transaction (one disk sync for all)."""
        with self._lock, self._db():  # the library's lock first, as upsert takes them
            yield

    def close(self) -> None:
        self.write_kept()
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- items --------------------------------------------------------------

    def _all(self) -> dict[str, Item]:
        items = self._items
        if items is not None:  # read without the lock: never waits for a write
            return items
        with self._lock:
            if self._items is None:
                with self._db() as db:
                    rows = db.execute("SELECT data FROM items").fetchall()
                self._items = {}
                for (data,) in rows:
                    item = Item.model_validate_json(data)
                    self._items[item.id] = item
            return self._items

    def _snapshot(self) -> list[Item]:
        """The items as they are now, safe to go through while another
        thread adds or removes some (iterating the cache itself then fails
        with "dictionary changed size during iteration")."""
        with self._lock:
            return list(self._all().values())

    def _snapshot_by_id(self) -> dict[str, Item]:
        with self._lock:
            return dict(self._all())

    def count(self) -> int:
        return len(self._all())

    def all_items(self) -> list[Item]:
        return self._snapshot()

    def get(self, item_id: str) -> Item | None:
        return self._all().get(item_id)

    def has(self, item_id: str) -> bool:
        return item_id in self._all()

    def upsert(self, item: Item) -> Item:
        with self._lock:
            existing = self._all().get(item.id)
            if existing is not None:
                # Keep user state when an item is re-imported.
                item = item.model_copy(
                    update={
                        "favorite": existing.favorite,
                        "excluded": existing.excluded,
                        "added_at": existing.added_at,
                        "last_shown_at": existing.last_shown_at,
                        "show_count": existing.show_count,
                        "framing": existing.framing,
                        "keywords": existing.keywords,
                        "terms": existing.terms,
                        "found_for": found_together(existing.found_for, item.found_for),
                        "sharper": existing.sharper,
                        "holder": item.holder or existing.holder,
                    }
                )
            elif not item.added_at:
                item = item.model_copy(update={"added_at": now_iso()})
            with self._db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO items (id, data) VALUES (?, ?)",
                    (item.id, item.model_dump_json(context=STORE)),
                )
            self._all()[item.id] = item
            self._indexed(item.id, item)
            self._version += 1
            if existing is None or existing.excluded != item.excluded:
                self._catalogue_version += 1
            if existing is None and item.favorite:  # brought in liked: the asker's heart
                self.set_favorite(viewer_id(), item.id, True)
            self._regroup(existing, item, "re-import")
            return item

    def update(self, item_id: str, **changes: Any) -> Item | None:
        """``favorite``: the heart of whoever is asking (the owner in the
        background), see :meth:`set_favorite`."""
        if "favorite" in changes:
            with self._lock:
                liked = bool(changes.pop("favorite"))
                if self.set_favorite(viewer_id(), item_id, liked) is None:
                    return None
                if not changes:
                    return self.get(item_id)
        return self._update(item_id, **changes)

    def _update(self, item_id: str, **changes: Any) -> Item | None:
        with self._lock:
            item = self.get(item_id)
            if item is None:
                return None
            fields = type(item).model_fields
            if all(k in fields and getattr(item, k) == v for k, v in changes.items()):
                return item  # as it was: no write, nothing to group again
            updated = item.model_copy(update=changes)
            with self._db() as db:
                db.execute(
                    "UPDATE items SET data = ? WHERE id = ?",
                    (updated.model_dump_json(context=STORE), item_id),
                )
            self._all()[item_id] = updated
            self._indexed(item_id, updated)
            self._version += 1
            if item.excluded != updated.excluded:
                self._catalogue_version += 1
            self._regroup(item, updated, "change")
            return updated

    def found(self, item_id: str, key: str) -> Item | None:
        """``item_id`` was found by the museums' search ``key``
        (:meth:`PlaylistRules.search_key`): it fits that search from now on."""
        item = self.get(item_id)
        if item is None or not key or key in item.found_for:
            return item
        return self._update(item_id, found_for=found_together(item.found_for, [key]))

    def delete(self, item_id: str) -> bool:
        with self._lock:
            if item_id not in self._all():
                return False
            with self._db() as db:
                db.execute("DELETE FROM items WHERE id = ?", (item_id,))
                db.execute("DELETE FROM ai_notes WHERE item_id = ?", (item_id,))
                db.execute("DELETE FROM favorites WHERE item_id = ?", (item_id,))
            with self._notes_lock:
                for kept in self._notes.values():
                    kept.pop(item_id, None)
            removed = self._all().pop(item_id)
            self._indexed(item_id, None)
            self._version += 1
            self._catalogue_version += 1
            if self._favorites is not None:
                self._favorites = {u: h - {item_id} for u, h in self._favorites.items()}
            if self._works is None and self._works_changes is not None:
                self._works_changes.append((removed, None))  # applied when it is made
            elif self._works is None or not self._works.remove(item_id):
                self._drop_works(f"deletion of {item_id}")
            return True

    # -- hearts, one set for each person -------------------------------------

    def _move_favorites(self) -> None:
        """Once: the hearts from before there were people become the
        owner's."""
        if self.get_state(FAVORITES_MOVED_KEY):
            return
        with self._lock, self._db() as db:
            stamp = now_iso()
            db.executemany(
                "INSERT OR IGNORE INTO favorites (user_id, item_id, added_at) VALUES (?, ?, ?)",
                [(OWNER_ID, i.id, stamp) for i in self._all().values() if i.favorite],
            )
            self.set_state(FAVORITES_MOVED_KEY, True)
        self._favorites = None
        self._hearts_version += 1

    def _hearts(self) -> dict[str, frozenset[str]]:
        """Everyone's hearts. Read without the lock once loaded: each
        person's set is replaced when it changes, never changed in place, so
        the event loop (a tile's heart) never waits for a write."""
        hearts = self._favorites
        if hearts is not None:
            return hearts
        with self._lock:
            if self._favorites is None:
                with self._db() as db:
                    rows = db.execute("SELECT user_id, item_id FROM favorites").fetchall()
                found: dict[str, set[str]] = {}
                for user_id, item_id in rows:
                    found.setdefault(user_id, set()).add(item_id)
                self._favorites = {u: frozenset(ids) for u, ids in found.items()}
            return self._favorites

    def _set_hearts(self, user_id: str, ids: frozenset[str]) -> None:
        """``user_id``'s hearts are now ``ids`` (with ``_lock`` held)."""
        hearts = dict(self._hearts())
        hearts[user_id] = ids
        self._favorites = hearts

    def favorites(self, user_id: str | None = None) -> frozenset[str]:
        """The works ``user_id`` likes (default: whoever is asking)."""
        return self._hearts().get(user_id or viewer_id(), frozenset())

    def likes(self, user_id: str, item_id: str) -> bool:
        return item_id in self._hearts().get(user_id, ())

    def fans(self) -> dict[str, frozenset[str]]:
        """Everyone's hearts, by person."""
        return dict(self._hearts())

    def set_favorite(self, user_id: str, item_id: str, liked: bool) -> Item | None:
        """``user_id``'s heart on ``item_id``; the stored ``Item.favorite``
        says whether anyone likes it (what keeps it in the library)."""
        with self._lock:
            if item_id not in self._all():
                return None
            hearts = self._hearts()
            with self._db() as db:
                if liked:
                    db.execute(
                        "INSERT OR IGNORE INTO favorites (user_id, item_id, added_at)"
                        " VALUES (?, ?, ?)",
                        (user_id, item_id, now_iso()),
                    )
                    self._set_hearts(user_id, hearts.get(user_id, frozenset()) | {item_id})
                else:
                    db.execute(
                        "DELETE FROM favorites WHERE user_id = ? AND item_id = ?",
                        (user_id, item_id),
                    )
                    self._set_hearts(user_id, hearts.get(user_id, frozenset()) - {item_id})
                hearts = self._hearts()
                self._hearts_version += 1
                anyone = any(item_id in ids for ids in hearts.values())
                return self._update(item_id, favorite=anyone)

    def forget_person(self, user_id: str) -> None:
        """A person removed from the server: their hearts go."""
        with self._lock, self._db() as db:
            ids = self._hearts().get(user_id, frozenset())
            self._favorites = {u: h for u, h in self._hearts().items() if u != user_id}
            self._hearts_version += 1
            db.execute("DELETE FROM favorites WHERE user_id = ?", (user_id,))
            self._kv_rows().pop(f"{ORDER_KEY}:{user_id}", None)
            db.execute("DELETE FROM kv WHERE key = ?", (f"{ORDER_KEY}:{user_id}",))
            hearts = self._hearts()
            for item_id in ids:
                if item_id in self._all() and not any(item_id in h for h in hearts.values()):
                    self._update(item_id, favorite=False)

    def _regroup(self, old: Item | None, new: Item, what: str) -> None:
        """Keep the grouping up to date with ``new`` (``old`` before): added
        or swapped in its place when the groups stay as they are, else
        dropped to be made again when next asked for."""
        works = self._works
        if works is None and self._works_changes is not None:
            self._works_changes.append((old, new))  # applied when it is made
        elif old is None:
            if works is not None:
                works.add(new)
        elif regroups(old, new):
            fields = sorted(k for k in type(new).model_fields if getattr(old, k) != getattr(new, k))
            self._drop_works(f"{what} of {new.id} ({', '.join(fields)})")
        elif works is not None:
            works.replace(new)

    def _drop_works(self, why: str) -> None:
        if self._works_changes is not None:
            self._works_changes.append((None, None))  # the one being made is stale
        if self._works is not None:
            self._works = None
            self._works_dropped_by = f"{why}, in {threading.current_thread().name}"
            self._works_drops = 0
        else:
            self._works_drops += 1

    def works(self) -> Works:
        """The library's items grouped by work: copies of one work from
        several sources together, the best copy first.

        Made outside the library's lock (14 s for 79 000 items on the NAS
        held up every heart, write and with them the event loop): whoever
        asks meanwhile waits for it, the rest of the library does not."""
        works = self._works
        if works is not None:
            return works
        if self._lock._is_owned():  # type: ignore[attr-defined]
            # Asked with the lock held (the term index): waiting for the
            # one being made could wait for this lock, so made right here.
            made = self._works = Works(self._all().values())
            return made
        with self._works_lock:
            for attempt in range(WORKS_ATTEMPTS):
                with self._lock:
                    if self._works is not None:
                        return self._works
                    items = list(self._all().values())
                    last = attempt == WORKS_ATTEMPTS - 1
                    if not last:
                        self._works_changes = []
                started = time.monotonic()
                if last:  # changes kept coming: made with the lock held
                    with self._lock:
                        made = Works(self._all().values())
                        self._works = made
                else:
                    made = Works(items)
                    with self._lock:
                        changes, self._works_changes = self._works_changes or [], None
                        if self._works is not None:  # made meanwhile with the lock held
                            return self._works
                        if not _apply(made, changes):
                            continue
                        self._works = made
                took = time.monotonic() - started
                more = self._works_drops
                log.log(
                    logging.INFO if took >= SLOW_WORKS else logging.DEBUG,
                    "works regrouped in %.1f s (%d items) after %s%s",
                    took,
                    len(items),
                    self._works_dropped_by,
                    f" and {more} more change(s)" if more > 0 else "",
                )
                return made
        raise AssertionError("unreachable")  # pragma: no cover

    # -- the search index ------------------------------------------------------

    def _indexed(self, item_id: str, item: Item | None) -> None:
        """``item_id`` is now ``item`` (None: gone), with ``_lock`` held."""
        index = self._search
        if index is not None:
            if item is None:
                index.remove(item_id)
            else:
                index.add(item)
            if index.dead_share() > SEARCH_DEAD_SHARE:
                self._make_search_later()
        if self._search_changes is not None:
            self._search_changes.append((item_id, item))

    def _make_search(self) -> SearchIndex:
        """A new search index of the library (``_search_lock`` held): made
        outside ``_lock``, then brought up to date with the changes made
        meanwhile."""
        started = time.monotonic()
        with self._lock:
            items = list(self._all().values())
            self._search_changes = []
        index = SearchIndex(items)
        with self._lock:
            changes, self._search_changes = self._search_changes or [], None
            for item_id, item in changes:
                if item is None:
                    index.remove(item_id)
                else:
                    index.add(item)
            self._search = index
        log.info("search index made in %.1f s (%d items)", time.monotonic() - started, len(index))
        return index

    def _make_search_later(self) -> None:
        if self._search_building:
            return
        self._search_building = True

        def make() -> None:
            try:
                with self._search_lock:
                    self._make_search()
            except Exception:
                log.exception("search index: making it failed")
            finally:
                self._search_building = False

        threading.Thread(target=make, name="search-index", daemon=True).start()

    def search_index(self, wait: bool = True) -> SearchIndex | None:
        """The catalogue's search index; ``wait``: made now when there is
        none yet (else None, and it is made in the background)."""
        index = self._search
        if index is not None:
            return index
        if not wait:
            self._make_search_later()
            return None
        # With the library's lock held, the one being made may wait for it.
        if not self._search_lock.acquire(blocking=not self._lock._is_owned()):  # type: ignore[attr-defined]
            return None
        try:
            return self._search or self._make_search()
        finally:
            self._search_lock.release()

    def term_index(self) -> TermIndex:
        """The catalogue as searches see it, for the suggestions while typing.

        Built once; when the library has changed since, it answers on while
        a new one is built in the background (at most every
        :data:`TERM_INDEX_EVERY` seconds), so that typing never waits for
        the catalogue: a count may be a few seconds old."""
        with self._term_index_lock:
            index = self._term_index
            if index is None:
                index = self._term_index = self._build_term_index()
                return index
            stale = index.version != self._version
            due = time.monotonic() - self._term_index_built_at >= TERM_INDEX_EVERY
            if stale and due and not self._term_index_building:
                self._term_index_building = True
                threading.Thread(
                    target=self._rebuild_term_index, name="term-index", daemon=True
                ).start()
            return index

    def _build_term_index(self) -> TermIndex:
        self.works()  # made first, outside the lock
        search = self.search_index()
        if search is None:  # being made by a thread waiting for this one
            search = SearchIndex(self._snapshot())
        version = self._version
        ids = {name: kept[0] for name, kept in self.get_state(IDS_STATE, {}).items() if kept[0]}
        people = self.get_state(PEOPLE_STATE, {})
        index = TermIndex(
            search,
            search.artists(),
            version,
            lambda rules: self.query(rules, limit=0)[0],
            ids,
            {qid: str(known.get("en") or "") for qid, known in people.items()},
        )
        learn(index.names)  # who is who for the searches, too
        self._term_index_built_at = time.monotonic()
        return index

    def refresh_names(self) -> None:
        """Who is who among the artists worked out again now (Wikidata
        told more), the suggestions with them."""
        with self._term_index_lock:
            if self._term_index_building:
                return
            self._term_index_building = True
        self._rebuild_term_index()

    def _rebuild_term_index(self) -> None:
        try:
            index = self._build_term_index()
            with self._term_index_lock:
                self._term_index = index
        except Exception:
            log.exception("term index: rebuild failed")
        finally:
            with self._term_index_lock:
                self._term_index_building = False

    def spare_copies(self, skip: Iterable[str] = ()) -> frozenset[str]:
        """Works the server added again from a less reliable source, or of
        which the owner kept another copy; with the copies of the sources
        ``skip`` left out, the next copy of their works is the one shown."""
        return self.works().spare(skip)

    def hidden(self) -> Hidden:
        """The works hidden in the app ("Ukryj dzieło"): the hidden items and
        every copy of their works, here or at a museum."""
        version = self._catalogue_version
        works = self.works()
        kept = self._hidden_kept
        if kept is not None and kept[0] == version and kept[1] is works:
            return kept[2]
        ids = {i.id for i in self._snapshot() if i.excluded}
        if not ids:
            found = Hidden()
        else:
            groups = {g for i in ids if (g := works.group_index(i)) is not None}
            # A work with a copy someone likes is not hidden by another copy
            # hidden: that copy was in the way (Mateusz 2026-11-09: WikiArt's
            # "The Little Street", hidden on 11-06, took the Rijksmuseum's he
            # liked with it once their pictures showed them to be one work).
            liked = set().union(*self._hearts().values())
            groups = {
                g
                for g in groups
                if not any(
                    not c.excluded and (c.favorite or c.id in liked) for c in works.groups[g]
                )
            }
            ids |= {c.id for g in groups for c in works.groups[g]}
            found = Hidden(ids, groups, works)
        self._hidden_kept = (version, works, found)
        return found

    def hidden_items(self) -> list[Item]:
        """The items hidden in the app, the last hidden first (the list
        "Ukryte" in Playlists)."""
        items = [i for i in self._snapshot() if i.excluded and i.look is None]
        return sorted(items, key=lambda i: i.excluded_at or "", reverse=True)

    def twin(self, item: Item) -> Item | None:
        """The library's best copy of ``item``'s work, when that is another
        item."""
        best = self.works().best(item)
        return self.get(best.id) if best is not None and best.id != item.id else None

    def query(
        self,
        rules: PlaylistRules | None = None,
        *,
        sort: SortKey = "recent",
        offset: int = 0,
        limit: int | None = None,
        seed: int = 0,
        include_excluded: bool = False,
        user: str | None = None,
    ) -> tuple[int, list[Item]]:
        """``user``: whose hearts and playlists "Ulubione" and "Moje" mean
        (default: whoever is asking, the owner in the background).

        The search index narrows the catalogue to the works the rules may
        fit and only those are checked (:func:`matches`); the whole answer
        is kept for the next pages while the library stays as it is.
        ``limit=0``: only how many."""
        rules = rules or PlaylistRules()
        user = user or viewer_id()
        if sort in ("relevance", "suitability") and _searches(rules):
            sort = "relevance"  # a search's best first ("suitability" is no more)
        elif sort == "relevance":
            sort = "recent"
        works = self.works()
        kept = (
            rules.model_dump_json(),
            sort,
            seed if sort == "random" else 0,
            include_excluded,
            user,
            self._version,
            self._hearts_version,
            self._playlists_version,
        )
        # What else decides the answer, compared as the objects they are.
        made_with = (works, known_names(), known_places())
        with self._queries_lock:
            found = self._queries.get(kept)
            if found is not None and all(a is b for a, b in zip(found[0], made_with, strict=True)):
                self._queries.move_to_end(kept)
                items: list[Item] | None = found[1]
            else:
                items = None
        if items is None:
            items = self._query(rules, sort, seed, include_excluded, user, limit == 0)
            if limit != 0:
                with self._queries_lock:
                    self._queries[kept] = (made_with, items)
                    while len(self._queries) > QUERIES_KEPT:
                        self._queries.popitem(last=False)
        end = None if limit is None else offset + limit
        return len(items), items[offset:end]

    def _query(
        self,
        rules: PlaylistRules,
        sort: SortKey,
        seed: int,
        include_excluded: bool,
        user: str,
        count_only: bool,
    ) -> list[Item]:
        # Spare copies of a work stay out, unless a source is asked for.
        spare = (
            frozenset()
            if include_excluded or rules.sources
            else self.spare_copies(rules.exclude_sources)
        )
        listed = self.listed(user) if MINE_PLAYLISTS in rules.terms else set()
        mine = rules.favorites_only or any(t in MINE for t in rules.terms)
        hearts = self.favorites(user) if mine else None
        hidden = Hidden() if include_excluded else self.hidden()
        key = rules.search_key()
        # The words as typed and as the museums were asked them (English,
        # French): "uliczka" finds "The Little Street" (Mateusz 2026-11-09).
        said = said_as(rules.query, self.wording) if rules.query.strip() else None
        # Looked up as a set: a list of 2 000 works with no picture cost
        # every query a second, item after item.
        left_out = set(rules.exclude_ids)
        if left_out:
            rules = rules.model_copy(update={"exclude_ids": []})

        # Photographs and pages of manuscripts the server picked only when
        # asked for (photographs never).
        def selected(item: Item) -> bool:
            if item.id in spare or item.id in left_out or item.look is not None:
                return False  # photos sent once: never listed
            if item.id in hidden.ids:  # another copy of a hidden work too
                return False
            if not include_excluded and item.pooled and set_aside(item, rules.terms):
                return False
            if include_excluded and item.excluded:
                unexcluded = item.model_copy(update={"excluded": False})
                return matches(unexcluded, rules, listed, hearts, key, said)
            return matches(item, rules, listed, hearts, key, said)

        index = self.search_index(wait=len(self._all()) <= SEARCH_INLINE)
        entries = index.candidates(rules, hearts, said) if index is not None else None
        pool = list(index.items(entries)) if index is not None and entries is not None else None
        items = [i for i in (self._snapshot() if pool is None else pool) if selected(i)]
        if said and not include_excluded:
            # The words of a work are those of all its copies: Vermeer's
            # "The Little Street" has "uliczka" in the Rijksmuseum's copy's
            # keywords and in the title of one on Commons, while another
            # copy stands for it (Mateusz 2026-11-09).
            plain = rules.model_copy(update={"query": ""})
            works = self.works()
            have = {i.id for i in items}
            if index is None:
                worded: Iterable[Item] = self._snapshot()
            else:
                entries = set().union(*(index.with_words("", [forms]) for forms in said))
                worded = index.items(entries)
            # Works with a copy that has a word: all their copies' words
            # together have them all.
            near = {
                g
                for i in worded
                if (g := works.group_index(i.id)) is not None and len(works.groups[g]) > 1
            }
            groups = [
                g
                for g in near
                if says_in(" ".join(phrase_fold(item_text(c)) for c in works.groups[g]), said)
            ]
            for g in groups:
                for copy in works.groups[g]:
                    if copy.id in have or copy.id in spare or copy.id in left_out:
                        continue
                    if copy.look is not None or copy.id in hidden.ids:
                        continue
                    if copy.pooled and set_aside(copy, rules.terms):
                        continue
                    stored = self.get(copy.id)
                    if stored is not None and matches(stored, plain, listed, hearts, "", None):
                        items.append(stored)
                        have.add(stored.id)
        if not include_excluded:
            # Copies the owner kept of one work: the best of those asked for
            # stands for them.
            items = self.works().once(items)
        if count_only:
            return items
        if sort == "relevance":
            return sorted(items, key=relevance(rules))
        return sort_items(items, sort, seed)

    def facets(self) -> Facets:
        items = [i for i in self._snapshot() if not i.excluded]
        names = known_names()

        def top(counter: Counter[str], limit: int = 60) -> list[FacetValue]:
            return [FacetValue(value=v, count=c) for v, c in counter.most_common(limit) if v]

        return Facets(
            artists=top(Counter(names.shown(i.artist) for i in items if is_artist(i.artist))),
            styles=top(Counter(s for i in items for s in i.styles)),
            subjects=top(Counter(s for i in items for s in i.subjects)),
            colors=top(Counter(c for i in items for c in shown_tags(i.color_tags))),
            sources=top(Counter(i.source for i in items)),
            kinds=top(Counter(i.kind.value for i in items)),
        )

    def save_places(self) -> None:
        """Keep what was learnt of the museums (:mod:`.places`)."""
        self.set_state(PLACES_STATE, known_places().state())
        self._places_kept = None  # their keys and names may have changed

    def places(self) -> list[PlaceCount]:
        """The places of the catalogue's works, the one with most first:
        how many works each has and a work to show for it (the one shown
        most, a favourite first). Kept while the library is the same, for
        ``PLACES_KEPT`` seconds at most (names learnt meanwhile), and
        ``PLACES_FRESH`` seconds whatever comes in: going
        through every work took the Muzeum panel a while (Mateusz
        2026-11-08: "Lista dosyć długo się wczytuje")."""
        kept = self._places_kept
        if kept is not None:
            age = time.monotonic() - kept[1]
            # Works the background adds meanwhile change little of it.
            if age < PLACES_FRESH or (kept[0] == self._version and age < PLACES_KEPT):
                return kept[2]
        version = self._version
        found = self._count_places()
        self._places_kept = (version, time.monotonic(), found)
        return found

    def _count_places(self) -> list[PlaceCount]:
        places = known_places()
        counts: Counter[str] = Counter()
        names: dict[str, Counter[str]] = {}
        best: dict[str, Item] = {}
        hidden = self.hidden()
        for item in self._snapshot():
            if item.excluded or item.look is not None or item in hidden:
                continue
            key = item.held_at
            if not key:
                continue
            counts[key] += 1
            names.setdefault(key, Counter())[item._held_by()] += 1
            if item.source == "europeana" and item.credit:
                places.provides(key, item.credit)  # asked for by that name
            had = best.get(key)
            if had is None or _shown_more(item, had):
                best[key] = item
        out: list[PlaceCount] = []
        for key, count in counts.most_common():
            place = places.place(key)
            out.append(
                PlaceCount(
                    key=key,
                    name=place.name if place else names[key].most_common(1)[0][0],
                    city=place.city if place else "",
                    count=count,
                    item_id=best[key].id,
                    source=place.source if place else "",
                )
            )
        return out

    # -- playlists ----------------------------------------------------------

    def _playlist_of(self, playlist_id: int, data: str) -> Playlist:
        playlist = Playlist.model_validate_json(data).model_copy(update={"id": playlist_id})
        if '"owner"' not in data:
            # From before there were people: the owner's, and shared
            # (Mateusz, 2026-10-31), but "Historia przesłanych".
            mine_only = playlist_id == self.get_state(SENT_KEY, None)
            playlist = playlist.model_copy(update={"owner": OWNER_ID, "shared": not mine_only})
        return playlist

    def playlists(self, user: str | None = None) -> list[Playlist]:
        """All playlists, or those ``user`` sees (theirs and shared ones)."""
        with self._db() as db:
            rows = db.execute("SELECT id, data FROM playlists ORDER BY id").fetchall()
        found = [self._playlist_of(pid, data) for pid, data in rows]
        return found if user is None else [p for p in found if p.visible_to(user)]

    def arranged_playlists(self, user: str) -> list[Playlist]:
        """The playlists ``user`` sees, in the order they put the cards in
        Playlisty; their own "Ulubione" first and the rest as made until they
        move one. Ones made or shared since come after the arranged ones."""
        found = self.playlists(user)
        default = sorted(found, key=lambda p: not (p.is_favorites and p.owner == user))
        order = self.get_state(f"{ORDER_KEY}:{user}", None)
        if not order:
            return default
        place = {pid: n for n, pid in enumerate(order)}
        return sorted(default, key=lambda p: place.get(p.id or 0, len(place)))

    def arrange_playlists(self, user: str, ids: list[int]) -> None:
        """Remember ``user``'s order of the cards (ids they don't see dropped)."""
        seen = {p.id for p in self.playlists(user)}
        order = list(dict.fromkeys(i for i in ids if i in seen))
        self.set_state(f"{ORDER_KEY}:{user}", order)

    def playlist(self, playlist_id: int) -> Playlist | None:
        with self._db() as db:
            row = db.execute("SELECT data FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if row is None:
            return None
        return self._playlist_of(playlist_id, row[0])

    def save_playlist(self, playlist: Playlist) -> Playlist:
        stamp = now_iso()
        playlist = playlist.model_copy(
            update={"updated_at": stamp, "created_at": playlist.created_at or stamp}
        )
        with self._db() as db:
            if playlist.id is None:
                cur = db.execute(
                    "INSERT INTO playlists (data) VALUES (?)",
                    (playlist.model_dump_json(exclude={"id"}),),
                )
                playlist = playlist.model_copy(update={"id": cur.lastrowid})
            else:
                db.execute(
                    "UPDATE playlists SET data = ? WHERE id = ?",
                    (playlist.model_dump_json(exclude={"id"}), playlist.id),
                )
        self._playlists_version += 1
        return playlist

    def delete_playlist(self, playlist_id: int) -> bool:
        with self._db() as db:
            cur = db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self._playlists_version += 1
        with self._lock:
            self._counted.pop(playlist_id, None)
        return cur.rowcount > 0

    def listed(self, user: str | None = None) -> set[str]:
        """The works on ``user``'s own playlists but "Ulubione" (which has
        its own term), smart ones that ask for these themselves left out."""
        user = user or viewer_id()
        ids: set[str] = set()
        for playlist in self.playlists():
            if playlist.owner != user:
                continue
            smart = playlist.kind == PlaylistKind.SMART
            if playlist.is_favorites or (smart and MINE_PLAYLISTS in playlist.rules.terms):
                continue
            ids.update(i.id for i in self.playlist_items(playlist))
        return ids

    def playlist_items(self, playlist: Playlist, sort: SortKey = "recent") -> list[Item]:
        if playlist.kind != PlaylistKind.SMART:
            all_items = self._snapshot_by_id()
            # Album photos taken out, and hidden works.
            skip = set(playlist.rules.exclude_ids) | self.hidden().ids
            return dedupe(
                [all_items[i] for i in playlist.item_ids if i in all_items and i not in skip]
            )
        stamp = self._stamp()
        items = dedupe(self.query(playlist.rules, sort=sort, user=playlist.owner)[1])
        if playlist.limit:
            items = limited(items, playlist, self.favorites(playlist.owner))
        items = fetched_last(items, playlist)
        self._keep_count(playlist, stamp, items)
        return items

    def playlist_summary(self, playlist: Playlist) -> PlaylistSummary:
        assert playlist.id is not None
        counted = self._counts(playlist)
        return PlaylistSummary(
            id=playlist.id,
            name=playlist.name,
            description=playlist.description,
            kind=playlist.kind,
            rules=playlist.rules,
            item_count=counted.total,
            cover_item_ids=counted.cover,
            cover_colors=counted.colors,
            album=playlist.album,
            album_sync=self.album_sync(playlist.id),
            theme=playlist.theme,
            owner=playlist.owner,
            shared=playlist.shared,
            mine=playlist.owner == viewer_id(),
            limit=playlist.limit,
        )

    def _stamp(self) -> tuple[int, int, int]:
        return (self._version, self._playlists_version, self._hearts_version)

    def stamp(self) -> tuple[int, int, int]:
        """Changes with any change of the library: items, playlists, hearts."""
        return self._stamp()

    def catalogue_stamp(self) -> tuple[int, int]:
        """Changes when works join or leave the catalogue (or are hidden),
        and with someone's hearts; not when a work is shown or described:
        what is worked out from the catalogue as a whole stays valid."""
        return (self._catalogue_version, self._hearts_version)

    def _counts(self, playlist: Playlist) -> _Counted:
        """The playlist's count and cover: a smart one's as last worked out
        while nothing changed since; with :attr:`counts_may_lag`, also after
        the catalogue changed (counted afresh when the playlist is opened,
        and every night: :meth:`recount`)."""
        if playlist.kind != PlaylistKind.SMART or playlist.id is None:
            items = self.playlist_items(playlist)
            return _Counted("", self._stamp(), len(items), *_cover(items))
        stamp = self._stamp()
        with self._lock:
            kept = self._counted.get(playlist.id)
        if kept is not None and kept.key == playlist.model_dump_json():
            if kept.stamp == stamp:
                return kept
            if self.counts_may_lag and (not _personal(playlist) or kept.stamp[1:] == stamp[1:]):
                return kept
        self.playlist_items(playlist)  # counts it
        with self._lock:
            return self._counted[playlist.id]

    def _keep_count(
        self, playlist: Playlist, stamp: tuple[int, int, int], items: list[Item]
    ) -> None:
        """A smart playlist's works as just found: its count and cover for
        Playlisty."""
        if playlist.id is None:
            return
        counted = _Counted(playlist.model_dump_json(), stamp, len(items), *_cover(items))
        with self._lock:
            self._counted[playlist.id] = counted

    def recount(self) -> None:
        """Every smart playlist counted afresh where the library changed
        since (the night's task, and once after a start)."""
        for playlist in self.playlists():
            if playlist.kind != PlaylistKind.SMART or playlist.id is None:
                continue
            with self._lock:
                kept = self._counted.get(playlist.id)
            if kept is None or kept.stamp != self._stamp():
                self.playlist_items(playlist)

    def album_sync(self, playlist_id: int) -> AlbumSync | None:
        data = self.get_state(f"album_sync:{playlist_id}")
        return AlbumSync.model_validate(data) if data else None

    def set_album_sync(self, playlist_id: int, sync: AlbumSync | None) -> None:
        key = f"album_sync:{playlist_id}"
        if sync is None:
            self.delete_state(key)
        else:
            self.set_state(key, sync.model_dump(mode="json"))

    # -- key/value state ----------------------------------------------------

    def _kv_rows(self) -> dict[str, str]:
        """The key/value table as kept in memory: read without the library's
        lock, so that the frame's question on the event loop never waits for
        a long write elsewhere (6 s after a start, 2026-11-05)."""
        kv = self._kv
        if kv is None:
            with self._db() as db:
                rows = db.execute("SELECT key, value FROM kv").fetchall()
            kv = self._kv = dict(rows)
        return kv

    def get_state(self, key: str, default: Any = None) -> Any:
        text = self._pending.get(key)
        if text is None:
            text = self._kv_rows().get(key)
        return default if text is None else json.loads(text)

    def set_state(self, key: str, value: Any) -> None:
        text = json.dumps(value)
        with self._pending_lock:
            self._pending.pop(key, None)
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, text))
            self._kv_rows()[key] = text

    def keep_state(self, key: str, value: Any) -> None:
        """:meth:`set_state` for the event loop: read back at once, written to
        disk a moment later by a thread. The frame's question once waited 78 s
        for the library's lock to write when it was last heard from, and with
        it every answer of the server (Szukaj's thumbnails, 2026-11-09)."""
        text = json.dumps(value)
        with self._pending_lock:
            self._pending[key] = text
            if self._writer is None:
                self._writer = threading.Thread(
                    target=self._write_kept_ever, name="state-writer", daemon=True
                )
                self._writer.start()
        self._pending_due.set()

    def _write_kept_ever(self) -> None:
        while True:
            self._pending_due.wait()
            self._pending_due.clear()
            try:
                self.write_kept()
            except Exception:
                log.exception("state: kept state not written, tried again with the next")

    def write_kept(self) -> None:
        """What :meth:`keep_state` kept, written to disk now."""
        if not self._pending:
            return
        with self._db() as db:
            # Taken again with the library's lock held: a set_state since
            # (no longer pending) is not written over with an older value.
            with self._pending_lock:
                pending = dict(self._pending)
            db.executemany("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", pending.items())
            self._kv_rows().update(pending)
        with self._pending_lock:
            for key, text in pending.items():
                if self._pending.get(key) == text:
                    del self._pending[key]

    def delete_state(self, key: str) -> None:
        with self._pending_lock:
            self._pending.pop(key, None)
        with self._db() as db:
            db.execute("DELETE FROM kv WHERE key = ?", (key,))
            self._kv_rows().pop(key, None)

    def sent_photo_ids(self) -> set[str]:
        """Photos sent once that were shown or queued: those in anyone's
        "Historia przesłanych"."""
        ids: set[str] = set()
        with self._db() as db:
            rows = db.execute(
                "SELECT value FROM kv WHERE key = ? OR key LIKE ?", (SENT_KEY, f"{SENT_KEY}:%")
            ).fetchall()
        for (value,) in rows:
            playlist = self.playlist(json.loads(value))
            if playlist is not None:
                ids.update(playlist.item_ids)
        return ids

    # -- notes from a language model (ai) -----------------------------------

    def note(self, item_id: str, kind: str) -> Note | None:
        with self._db() as db:
            row = db.execute(
                f"SELECT {_NOTE_COLUMNS} FROM ai_notes WHERE item_id = ? AND kind = ?",
                (item_id, kind),
            ).fetchone()
        return None if row is None else _note(row)

    def notes(self, kind: str) -> dict[str, Note]:
        """Every note of one kind, by item (a copy: kept in memory after the
        first read, as :meth:`save_note` and :meth:`delete_notes` change it)."""
        with self._notes_lock:
            kept = self._notes.get(kind)
            if kept is not None:
                return dict(kept)
        with self._db() as db:
            rows = db.execute(
                f"SELECT {_NOTE_COLUMNS} FROM ai_notes WHERE kind = ?", (kind,)
            ).fetchall()
            # Kept while the disk's lock is held: no note saved in between.
            read = {row[0]: _note(row) for row in rows}
            with self._notes_lock:
                self._notes[kind] = read
                return dict(read)

    def save_note(self, note: Note) -> Note:
        if not note.created_at:
            note = note.model_copy(update={"created_at": now_iso()})
        with self._db() as db:
            db.execute(
                f"INSERT OR REPLACE INTO ai_notes ({_NOTE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    note.item_id,
                    note.kind,
                    note.model,
                    note.prompt_version,
                    note.source_hash,
                    json.dumps(note.data, ensure_ascii=False),
                    note.created_at,
                ),
            )
            with self._notes_lock:
                if (kept := self._notes.get(note.kind)) is not None:
                    kept[note.item_id] = note
        self.notes_version += 1
        return note

    def delete_notes(self, kind: str, item_id: str | None = None) -> int:
        """Forget notes of one kind (of one item, or all of them)."""
        with self._db() as db:
            if item_id is None:
                cur = db.execute("DELETE FROM ai_notes WHERE kind = ?", (kind,))
            else:
                cur = db.execute(
                    "DELETE FROM ai_notes WHERE kind = ? AND item_id = ?", (kind, item_id)
                )
            with self._notes_lock:
                if item_id is None:
                    self._notes.pop(kind, None)
                elif (kept := self._notes.get(kind)) is not None:
                    kept.pop(item_id, None)
        self.notes_version += 1
        return cur.rowcount

    # -- history ------------------------------------------------------------

    def record_shown(self, item_id: str, reason: str = "") -> None:
        stamp = now_iso()
        with self._db() as db:
            db.execute(
                "INSERT INTO history (item_id, shown_at, reason) VALUES (?, ?, ?)",
                (item_id, stamp, reason),
            )
        item = self.get(item_id)
        if item is not None:
            self.update(item_id, last_shown_at=stamp, show_count=item.show_count + 1)

    def last_shown(self, item_ids: list[str]) -> dict[str, tuple[str, str]]:
        """When each of ``item_ids`` last went on the frame, and why."""
        if not item_ids:
            return {}
        marks = ",".join("?" * len(item_ids))
        with self._db() as db:
            rows = db.execute(
                f"SELECT item_id, shown_at, reason FROM history WHERE id IN "
                f"(SELECT MAX(id) FROM history WHERE item_id IN ({marks}) GROUP BY item_id)",
                item_ids,
            ).fetchall()
        return {i: (s, r) for i, s, r in rows}

    def history(self, limit: int = 50) -> list[dict[str, str]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT item_id, shown_at, reason FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"item_id": i, "shown_at": s, "reason": r} for i, s, r in rows]


#: Works the playlist editor's museum search keeps just before the
#: playlist is saved still count as fetched for it.
FETCHED_BEFORE = timedelta(hours=1)


def fetched_last(items: list[Item], playlist: Playlist) -> list[Item]:
    """A smart playlist's works with those that joined the library since it
    was made (fetched from the museums for it, or found later) at the end,
    each part in the order given (Mateusz 2026-11-09: "dzieła dociągane z
    muzeów dawaj na koniec playlist")."""
    if not playlist.created_at:
        return items
    try:
        made = datetime.fromisoformat(playlist.created_at)
    except ValueError:
        return items
    since = (made - FETCHED_BEFORE).astimezone(UTC).isoformat(timespec="seconds")
    before = [i for i in items if not i.added_at or i.added_at < since]
    if len(before) == len(items):
        return items
    taken = {i.id for i in before}
    return before + [i for i in items if i.id not in taken]


def limited(
    items: list[Item], playlist: Playlist, hearts: frozenset[str] | None = None
) -> list[Item]:
    """A smart playlist's works within its limit, in the order given: the
    favourites first (its owner's ``hearts``; without them anyone's), then
    the others in an order drawn from the rules and the limit, so the same
    works stay until either changes (Mateusz, 2026-10-31: a steady set)."""
    limit = playlist.limit
    if limit is None or len(items) <= limit:
        return items
    seed = playlist.rules.model_dump_json(exclude={"exclude_ids"}) + f"|{limit}"

    def drawn(item: Item) -> tuple[bool, str]:
        digest = hashlib.sha1(f"{seed}|{item.id}".encode()).hexdigest()
        liked = item.favorite if hearts is None else item.id in hearts
        return (not liked, digest)

    taken = {i.id for i in sorted(items, key=drawn)[:limit]}
    return [i for i in items if i.id in taken]
