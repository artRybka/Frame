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
from typing import Any, Literal

from .artists import is_artist
from .colors import has_colours
from .duplicates import Works, dedupe
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
    Playlist,
    PlaylistKind,
    PlaylistRules,
    PlaylistSummary,
)
from .term_index import TermIndex
from .viewer import OWNER_ID, STORE, viewer_id
from .vocabulary import artist_matches, is_postal, matches_terms, object_category, set_aside

#: Item fields that tell copies of a work apart or choose between them.
log = logging.getLogger(__name__)

#: Seconds between rebuilds of the suggestions' index while the library changes.
TERM_INDEX_EVERY = 10.0

WORK_FIELDS = frozenset(
    {"kind", "source", "title", "artist", "year", "width", "height", "url", "image_url", "pooled"}
)

#: The playlist "Historia przesłanych" (see ``Player.remember_sent``); one
#: for each person (the owner's under the key from before, ``sent_key``).
SENT_KEY = "sent_photos_playlist"
#: Hearts were moved from ``Item.favorite`` to the owner's in ``favorites``.
FAVORITES_MOVED_KEY = "favorites_moved"


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


def matches(
    item: Item,
    rules: PlaylistRules,
    listed: Collection[str] = (),
    favorites: Collection[str] | None = None,
) -> bool:
    """Whether ``item`` fits ``rules``; ``listed`` are the works on the
    person's playlists, for ``mine:playlists``, ``favorites`` their hearts
    (None: anyone's, the stored ``Item.favorite``)."""
    liked = item.favorite if favorites is None else item.id in favorites
    if item.excluded or item.id in rules.exclude_ids:
        return False
    # Photographs, sculpture, crafts and manuscripts are found only when
    # asked for, even those the owner kept: Monet's bust is no Monet.
    # Stamps never: Athens 2004's coins are no still life.
    category = object_category(item)
    if category is not None and category not in rules.terms and _searches(rules):
        return False
    if _searches(rules) and is_postal(item):
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
    if rules.artists and not artist_matches(item.artist, rules.artists):
        return False
    if rules.styles and not _fold(item.styles) & _fold(rules.styles):
        return False
    if rules.subjects and not _fold(item.subjects) & _fold(rules.subjects):
        return False
    if rules.colors and not has_colours(item.color_tags, rules.colors):
        return False
    if rules.terms and not matches_terms(item, rules.terms):
        return False
    if rules.year_from is not None and (item.year is None or item.year < rules.year_from):
        return False
    if rules.year_to is not None and (item.year is None or item.year > rules.year_to):
        return False
    # ``min_suitability`` of older playlists and themes is no longer kept to
    # (Mateusz, 2026-10-31: the e-paper threshold left out important works).
    if rules.query:
        haystack = " ".join(
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
        ).casefold()
        if not all(word in haystack for word in rules.query.casefold().split()):
            return False
    return True


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


class Library:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._items: dict[str, Item] | None = None
        self._works: Works | None = None  # the items grouped by work
        self._conn: sqlite3.Connection | None = None
        self._depth = 0  # nested _db() blocks share the outermost transaction
        self._favorites: dict[str, set[str]] | None = None
        #: Goes up with every change of an item (for the suggestions' index).
        self._version = 0
        self._term_index: TermIndex | None = None
        self._term_index_lock = threading.Lock()
        self._term_index_building = False
        self._term_index_built_at = 0.0
        with self._db() as db:
            db.executescript(SCHEMA)
        self._move_favorites()

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
                self._works = None
                self._version += 1
                self._favorites = None
                raise
            finally:
                self._depth -= 1

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Make the writes inside one transaction (one disk sync for all)."""
        with self._db():
            yield

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- items --------------------------------------------------------------

    def _all(self) -> dict[str, Item]:
        with self._lock:
            if self._items is None:
                with self._db() as db:
                    rows = db.execute("SELECT data FROM items").fetchall()
                self._items = {}
                for (data,) in rows:
                    item = Item.model_validate_json(data)
                    self._items[item.id] = item
            return self._items

    def count(self) -> int:
        return len(self._all())

    def all_items(self) -> list[Item]:
        return list(self._all().values())

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
                        "sharper": existing.sharper,
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
            if existing is None and item.favorite:  # brought in liked: the asker's heart
                self.set_favorite(viewer_id(), item.id, True)
            if existing is None and self._works is not None:
                self._works.add(item)
            else:
                self._works = None
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
            updated = item.model_copy(update=changes)
            with self._db() as db:
                db.execute(
                    "UPDATE items SET data = ? WHERE id = ?",
                    (updated.model_dump_json(context=STORE), item_id),
                )
            self._all()[item_id] = updated
            self._version += 1
            if WORK_FIELDS & changes.keys():
                self._works = None
            return updated

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
            for hearts in (self._favorites or {}).values():
                hearts.discard(item_id)
            self._works = None
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
        return frozenset(self._hearts().get(user_id or viewer_id(), ()))

    def likes(self, user_id: str, item_id: str) -> bool:
        return item_id in self._hearts().get(user_id, ())

    def fans(self) -> dict[str, frozenset[str]]:
        """Everyone's hearts, by person."""
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
                anyone = any(item_id in ids for ids in hearts.values())
                return self._update(item_id, favorite=anyone)

    def forget_person(self, user_id: str) -> None:
        """A person removed from the server: their hearts go."""
        with self._lock, self._db() as db:
            ids = self._hearts().pop(user_id, set())
            db.execute("DELETE FROM favorites WHERE user_id = ?", (user_id,))
            hearts = self._hearts()
            for item_id in ids:
                if item_id in self._all() and not any(item_id in h for h in hearts.values()):
                    self._update(item_id, favorite=False)

    def works(self) -> Works:
        """The library's items grouped by work: copies of one work from
        several sources together, the best copy first."""
        with self._lock:
            if self._works is None:
                self._works = Works(self._all().values())
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

    def spare_copies(self) -> set[str]:
        """Works the server added again from a less reliable source, or of
        which the owner kept another copy."""
        return self.works().spare()

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
        spare = set() if include_excluded or rules.sources else self.spare_copies()
        listed = self.listed(user) if MINE_PLAYLISTS in rules.terms else set()
        mine = rules.favorites_only or any(t in MINE for t in rules.terms)
        hearts = self.favorites(user) if mine else None

        # Photographs and pages of manuscripts the server picked only when
        # asked for (photographs never).
        def selected(item: Item) -> bool:
            if item.id in spare or item.look is not None:  # photos sent once: never listed
                return False
            if not include_excluded and item.pooled and set_aside(item, rules.terms):
                return False
            if include_excluded and item.excluded:
                unexcluded = item.model_copy(update={"excluded": False})
                return matches(unexcluded, rules, listed, hearts)
            return matches(item, rules, listed, hearts)

        items = [i for i in self._all().values() if selected(i)]
        if not include_excluded:
            # Copies the owner kept of one work: the best of those asked for
            # stands for them.
            items = self.works().once(items)
        items = sort_items(items, sort, seed)
        end = None if limit is None else offset + limit
        return len(items), items[offset:end]

    def facets(self) -> Facets:
        items = [i for i in self._all().values() if not i.excluded]

        def top(counter: Counter[str], limit: int = 60) -> list[FacetValue]:
            return [FacetValue(value=v, count=c) for v, c in counter.most_common(limit) if v]

        return Facets(
            artists=top(Counter(i.artist for i in items if is_artist(i.artist))),
            styles=top(Counter(s for i in items for s in i.styles)),
            subjects=top(Counter(s for i in items for s in i.subjects)),
            colors=top(Counter(c for i in items for c in i.color_tags)),
            sources=top(Counter(i.source for i in items)),
            kinds=top(Counter(i.kind.value for i in items)),
        )

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
        return playlist

    def delete_playlist(self, playlist_id: int) -> bool:
        with self._db() as db:
            cur = db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
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
            all_items = self._all()
            skip = set(playlist.rules.exclude_ids)  # album photos taken out
            return dedupe(
                [
                    all_items[i]
                    for i in playlist.item_ids
                    if i in all_items and not all_items[i].excluded and i not in skip
                ]
            )
        items = dedupe(self.query(playlist.rules, sort=sort, user=playlist.owner)[1])
        if not playlist.limit:
            return items
        return limited(items, playlist, self.favorites(playlist.owner))

    def playlist_summary(self, playlist: Playlist) -> PlaylistSummary:
        items = self.playlist_items(playlist, sort="suitability")
        assert playlist.id is not None
        return PlaylistSummary(
            id=playlist.id,
            name=playlist.name,
            description=playlist.description,
            kind=playlist.kind,
            rules=playlist.rules,
            item_count=len(items),
            cover_item_ids=[i.id for i in items[:4]],
            cover_colors=cover_colors(items[:4]),
            album=playlist.album,
            album_sync=self.album_sync(playlist.id),
            theme=playlist.theme,
            owner=playlist.owner,
            shared=playlist.shared,
            mine=playlist.owner == viewer_id(),
            limit=playlist.limit,
        )

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

    def get_state(self, key: str, default: Any = None) -> Any:
        with self._db() as db:
            row = db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def set_state(self, key: str, value: Any) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json.dumps(value))
            )

    def delete_state(self, key: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM kv WHERE key = ?", (key,))

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
