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
import sqlite3
import threading
import time
import weakref
from collections import Counter
from collections.abc import Collection, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

from .artists import is_artist, known_names, learn, made_by
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
from .phrases import has_phrase, parsed
from .phrases import words as phrase_words
from .places import Places, known_places, learn_places
from .term_index import TermIndex
from .viewer import OWNER_ID, STORE, viewer_id
from .vocabulary import (
    is_art_archive_photo,
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
#: Seconds between rebuilds of the suggestions' index while the library changes.
TERM_INDEX_EVERY = 10.0


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


SortKey = Literal["recent", "title", "artist", "year", "random", "suitability", "shown"]

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
) -> bool:
    """Whether ``item`` fits ``rules``; ``listed`` are the works on the
    person's playlists, for ``mine:playlists``, ``favorites`` their hearts
    (None: anyone's, the stored ``Item.favorite``). A work the museums'
    search for ``rules`` found (``key``: :meth:`PlaylistRules.search_key`,
    worked out when not given) fits as that search judged it: Szukaj and a
    smart playlist of the same choices hold the same works (Mateusz,
    2026-11-07)."""
    liked = item.favorite if favorites is None else item.id in favorites
    if item.excluded or item.id in rules.exclude_ids:
        return False
    # Photographs, sculpture, crafts and manuscripts are found only when
    # asked for, even those the owner kept: Monet's bust is no Monet.
    # Stamps never: Athens 2004's coins are no still life. Nor Foto
    # Marburg's black-and-white prints on a catalogue card.
    category = object_category(item)
    if category is not None and category not in rules.terms and _searches(rules):
        return False
    if _searches(rules) and (
        is_postal(item) or (is_art_archive_photo(item) and is_grey_copy(item))
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
            return search_fits(item, rules)
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
    return not rules.query or has_words(item, rules.query)


def item_text(item: Item) -> str:
    """What typed words are looked for in: the work's title, artist,
    technique, culture, description, styles, subjects and keywords."""
    return " ".join(
        [
            item.title,
            item.artist,
            item.medium,
            item.classification,
            item.culture,
            item.description,
            *item.styles,
            *item.subjects,
            *item.keywords,
        ]
    )


def has_words(item: Item, query: str) -> bool:
    """Whether ``item`` has every token of ``query`` (:mod:`.phrases`): a
    word anywhere in its texts, a phrase as a phrase."""
    text = item_text(item)
    haystack = text.casefold()
    seen: list[str] | None = None
    for token, wanted in parsed(query):
        if " " in token:
            seen = phrase_words(text) if seen is None else seen
            if not has_phrase(wanted, seen):
                return False
        elif token.casefold() not in haystack:
            return False
    return True


def says(item: Item, phrases: list[list[str]]) -> bool:
    """Whether ``item`` has each of ``phrases`` in one of its forms (as
    typed or translated, :class:`.importer.Asked`)."""
    if not phrases:
        return True
    seen = phrase_words(item_text(item))
    return all(any(has_phrase(form, seen) for form in forms) for forms in phrases)


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
        self._lock = threading.RLock()
        self._items: dict[str, Item] | None = None
        self._works: Works | None = None  # the items grouped by work
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
        self._favorites: dict[str, set[str]] | None = None
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
        #: Smart playlists' counts and covers as last worked out, by id.
        self._counted: dict[int, _Counted] = {}
        #: A smart playlist's count and cover may be shown as last worked
        #: out while the catalogue changed since (the server adding works in
        #: the background): counted afresh when it is opened and at night
        #: (Mateusz, 2026-11-02); set when the server runs its background.
        #: A playlist changed is counted at once, and one of hearts once
        #: they change.
        self.counts_may_lag = False
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
        consistent after a power cut and syncs only at checkpoints."""
        with self._lock:
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
                raise
            finally:
                self._depth -= 1

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Make the writes inside one transaction (one disk sync for all)."""
        with self._db():
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
            del self._all()[item_id]
            self._version += 1
            self._catalogue_version += 1
            for hearts in (self._favorites or {}).values():
                hearts.discard(item_id)
            if self._works is None or not self._works.remove(item_id):
                self._drop_works(f"deletion of {item_id}")
            return True

    # -- hearts, one set for each person -------------------------------------

    def _move_favorites(self) -> None:
        """Once: the hearts from before there were people become the
        owner's."""
        if self.get_state(FAVORITES_MOVED_KEY):
            return
        with self._db() as db:
            stamp = now_iso()
            db.executemany(
                "INSERT OR IGNORE INTO favorites (user_id, item_id, added_at) VALUES (?, ?, ?)",
                [(OWNER_ID, i.id, stamp) for i in self._all().values() if i.favorite],
            )
            self.set_state(FAVORITES_MOVED_KEY, True)
        self._favorites = None
        self._hearts_version += 1

    def _hearts(self) -> dict[str, set[str]]:
        with self._lock:
            if self._favorites is None:
                with self._db() as db:
                    rows = db.execute("SELECT user_id, item_id FROM favorites").fetchall()
                hearts: dict[str, set[str]] = {}
                for user_id, item_id in rows:
                    hearts.setdefault(user_id, set()).add(item_id)
                self._favorites = hearts
            return self._favorites

    def favorites(self, user_id: str | None = None) -> frozenset[str]:
        """The works ``user_id`` likes (default: whoever is asking)."""
        user_id = user_id or viewer_id()
        with self._lock:  # a heart given meanwhile would change the set
            return frozenset(self._hearts().get(user_id, ()))

    def likes(self, user_id: str, item_id: str) -> bool:
        return item_id in self._hearts().get(user_id, ())

    def fans(self) -> dict[str, frozenset[str]]:
        """Everyone's hearts, by person."""
        with self._lock:
            return {u: frozenset(ids) for u, ids in self._hearts().items()}

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
                    hearts.setdefault(user_id, set()).add(item_id)
                else:
                    db.execute(
                        "DELETE FROM favorites WHERE user_id = ? AND item_id = ?",
                        (user_id, item_id),
                    )
                    hearts.get(user_id, set()).discard(item_id)
                self._hearts_version += 1
                anyone = any(item_id in ids for ids in hearts.values())
                return self._update(item_id, favorite=anyone)

    def forget_person(self, user_id: str) -> None:
        """A person removed from the server: their hearts go."""
        with self._lock, self._db() as db:
            ids = self._hearts().pop(user_id, set())
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
        if old is None:
            if works is not None:
                works.add(new)
        elif regroups(old, new):
            fields = sorted(k for k in type(new).model_fields if getattr(old, k) != getattr(new, k))
            self._drop_works(f"{what} of {new.id} ({', '.join(fields)})")
        elif works is not None:
            works.replace(new)

    def _drop_works(self, why: str) -> None:
        if self._works is not None:
            self._works = None
            self._works_dropped_by = f"{why}, in {threading.current_thread().name}"
            self._works_drops = 0
        else:
            self._works_drops += 1

    def works(self) -> Works:
        """The library's items grouped by work: copies of one work from
        several sources together, the best copy first."""
        with self._lock:
            if self._works is None:
                started = time.monotonic()
                self._works = Works(self._all().values())
                took = time.monotonic() - started
                more = self._works_drops
                log.log(
                    logging.INFO if took >= SLOW_WORKS else logging.DEBUG,
                    "works regrouped in %.1f s (%d items) after %s%s",
                    took,
                    len(self._all()),
                    self._works_dropped_by,
                    f" and {more} more change(s)" if more > 0 else "",
                )
            return self._works

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
        with self._lock:
            version = self._version
            items = list(self._all().values())
            works = self.works()
            spare = works.spare()
            groups = {i.id: g for i in items if (g := works.group_index(i.id)) is not None}
        index = TermIndex(items, spare, groups, version, lambda rules: self.query(rules)[0])
        learn(index.names)  # who is who for the searches, too
        self._term_index_built_at = time.monotonic()
        return index

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

    def spare_copies(self, skip: Iterable[str] = ()) -> set[str]:
        """Works the server added again from a less reliable source, or of
        which the owner kept another copy; with the copies of the sources
        ``skip`` left out, the next copy of their works is the one shown."""
        return self.works().spare(skip)

    def hidden(self) -> Hidden:
        """The works hidden in the app ("Ukryj dzieło"): the hidden items and
        every copy of their works, here or at a museum."""
        ids = {i.id for i in self._snapshot() if i.excluded}
        if not ids:
            return Hidden()
        works = self.works()
        groups = {g for i in ids if (g := works.group_index(i)) is not None}
        ids |= {c.id for g in groups for c in works.groups[g]}
        return Hidden(ids, groups, works)

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
        (default: whoever is asking, the owner in the background)."""
        rules = rules or PlaylistRules()
        user = user or viewer_id()
        # Spare copies of a work stay out, unless a source is asked for.
        spare = (
            set() if include_excluded or rules.sources else self.spare_copies(rules.exclude_sources)
        )
        listed = self.listed(user) if MINE_PLAYLISTS in rules.terms else set()
        mine = rules.favorites_only or any(t in MINE for t in rules.terms)
        hearts = self.favorites(user) if mine else None
        hidden = Hidden() if include_excluded else self.hidden()
        key = rules.search_key()

        # Photographs and pages of manuscripts the server picked only when
        # asked for (photographs never).
        def selected(item: Item) -> bool:
            if item.id in spare or item.look is not None:  # photos sent once: never listed
                return False
            if item.id in hidden.ids:  # another copy of a hidden work too
                return False
            if not include_excluded and item.pooled and set_aside(item, rules.terms):
                return False
            if include_excluded and item.excluded:
                unexcluded = item.model_copy(update={"excluded": False})
                return matches(unexcluded, rules, listed, hearts, key)
            return matches(item, rules, listed, hearts, key)

        items = [i for i in self._snapshot() if selected(i)]
        if not include_excluded:
            # Copies the owner kept of one work: the best of those asked for
            # stands for them.
            items = self.works().once(items)
        items = sort_items(items, sort, seed)
        end = None if limit is None else offset + limit
        return len(items), items[offset:end]

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
        """Every note of one kind, by item."""
        with self._db() as db:
            rows = db.execute(
                f"SELECT {_NOTE_COLUMNS} FROM ai_notes WHERE kind = ?", (kind,)
            ).fetchall()
        return {row[0]: _note(row) for row in rows}

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
