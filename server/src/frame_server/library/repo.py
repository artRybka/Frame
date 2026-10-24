"""SQLite-backed library: items, playlists, key-value state, display history.

Items and playlists are stored as JSON documents. The library is small
(hundreds to a few thousand pictures), so filtering happens in memory on a
cached copy; SQLite gives durability and atomic writes.
"""

from __future__ import annotations

import json
import random
import sqlite3
import threading
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .models import (
    Facets,
    FacetValue,
    Item,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    PlaylistSummary,
)

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
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _fold(values: Iterable[str]) -> set[str]:
    return {v.casefold() for v in values if v}


def matches(item: Item, rules: PlaylistRules) -> bool:
    if item.excluded:
        return False
    if rules.favorites_only and not item.favorite:
        return False
    if rules.kinds and item.kind not in rules.kinds:
        return False
    if rules.sources and item.source not in rules.sources:
        return False
    if rules.artists and item.artist.casefold() not in _fold(rules.artists):
        return False
    if rules.styles and not _fold(item.styles) & _fold(rules.styles):
        return False
    if rules.subjects and not _fold(item.subjects) & _fold(rules.subjects):
        return False
    if rules.colors and not set(item.color_tags) & set(rules.colors):
        return False
    if rules.year_from is not None and (item.year is None or item.year < rules.year_from):
        return False
    if rules.year_to is not None and (item.year is None or item.year > rules.year_to):
        return False
    if rules.min_suitability is not None and (item.suitability or 0) < rules.min_suitability:
        return False
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


class Library:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._items: dict[str, Item] | None = None
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:
                yield conn
        finally:
            conn.close()

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
                    }
                )
            elif not item.added_at:
                item = item.model_copy(update={"added_at": now_iso()})
            with self._db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO items (id, data) VALUES (?, ?)",
                    (item.id, item.model_dump_json()),
                )
            self._all()[item.id] = item
            return item

    def update(self, item_id: str, **changes: Any) -> Item | None:
        with self._lock:
            item = self.get(item_id)
            if item is None:
                return None
            updated = item.model_copy(update=changes)
            with self._db() as db:
                db.execute(
                    "UPDATE items SET data = ? WHERE id = ?", (updated.model_dump_json(), item_id)
                )
            self._all()[item_id] = updated
            return updated

    def delete(self, item_id: str) -> bool:
        with self._lock:
            if item_id not in self._all():
                return False
            with self._db() as db:
                db.execute("DELETE FROM items WHERE id = ?", (item_id,))
            del self._all()[item_id]
            return True

    def query(
        self,
        rules: PlaylistRules | None = None,
        *,
        sort: SortKey = "recent",
        offset: int = 0,
        limit: int | None = None,
        seed: int = 0,
        include_excluded: bool = False,
    ) -> tuple[int, list[Item]]:
        rules = rules or PlaylistRules()

        def selected(item: Item) -> bool:
            if include_excluded and item.excluded:
                return matches(item.model_copy(update={"excluded": False}), rules)
            return matches(item, rules)

        items = sort_items([i for i in self._all().values() if selected(i)], sort, seed)
        end = None if limit is None else offset + limit
        return len(items), items[offset:end]

    def facets(self) -> Facets:
        items = [i for i in self._all().values() if not i.excluded]

        def top(counter: Counter[str], limit: int = 60) -> list[FacetValue]:
            return [FacetValue(value=v, count=c) for v, c in counter.most_common(limit) if v]

        return Facets(
            artists=top(Counter(i.artist for i in items)),
            styles=top(Counter(s for i in items for s in i.styles)),
            subjects=top(Counter(s for i in items for s in i.subjects)),
            colors=top(Counter(c for i in items for c in i.color_tags)),
            sources=top(Counter(i.source for i in items)),
            kinds=top(Counter(i.kind.value for i in items)),
        )

    # -- playlists ----------------------------------------------------------

    def playlists(self) -> list[Playlist]:
        with self._db() as db:
            rows = db.execute("SELECT id, data FROM playlists ORDER BY id").fetchall()
        return [
            Playlist.model_validate_json(data).model_copy(update={"id": pid}) for pid, data in rows
        ]

    def playlist(self, playlist_id: int) -> Playlist | None:
        with self._db() as db:
            row = db.execute("SELECT data FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if row is None:
            return None
        return Playlist.model_validate_json(row[0]).model_copy(update={"id": playlist_id})

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

    def playlist_items(self, playlist: Playlist, sort: SortKey = "recent") -> list[Item]:
        if playlist.kind == PlaylistKind.MANUAL:
            all_items = self._all()
            return [
                all_items[i]
                for i in playlist.item_ids
                if i in all_items and not all_items[i].excluded
            ]
        return self.query(playlist.rules, sort=sort)[1]

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
        )

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

    def history(self, limit: int = 50) -> list[dict[str, str]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT item_id, shown_at, reason FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"item_id": i, "shown_at": s, "reason": r} for i, s, r in rows]
