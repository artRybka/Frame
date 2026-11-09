"""Pages of museum searches, kept on disk (Mateusz 2026-11-07: "przyspieszenie
serwowania wyników").

The importer kept 300 pages for three hours in the process: every update of
the server forgot them, and a set of Odkrywaj opened the next morning asked
every museum again (the Met's 24 works a request each, Yale's two). Here
pages outlive a restart: one asked within :data:`FRESH` comes as it is; an
older one, up to :data:`STALE` (or one read by older code of its museum,
:data:`READINGS`), comes at once while the museum is asked again behind it,
for the next look. Every page still comes from the museum's own search, only
earlier.

A release of the server no longer makes every page old (2026-11-07: eight
releases a day asked every set opened again): only a change to how one
museum's answers are read does, and only that museum's pages.

The file stays below :data:`MAX_BYTES`; the pages looked at longest ago go
first.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import zlib
from pathlib import Path
from typing import Any

from .models import Item

log = logging.getLogger(__name__)

#: A page this young (seconds) is not asked for again: museums add works a
#: few times a year, so a set shows a new one at most this late.
FRESH = 3 * 86400.0
#: A page this old at most is shown while it is asked for again.
STALE = 30 * 86400.0
#: How the pages are kept: a new number makes every page old.
PAGES_VERSION = "2"
#: How each museum's answers are read into works (museums.py and the like):
#: raise a museum's number with a change to its reading (titles, dates,
#: pictures, what is left out), so that its kept pages are asked again.
#: Museums not named read as "1".
READINGS: dict[str, str] = {
    # 2026-11-07: old photographs (Fotografia, photo categories); 3: the
    # artist's visible name only ("Nieznany", not "NieznanyUnknown author");
    # 4: archive papers and chemical diagrams left out; 5: archives'
    # documents, backs of paintings and museums' objects too.
    "wmc": "5",
    # 2026-11-09: searches ask for digitised artworks only, no illustrations.
    "openverse": "2",
    # 2026-11-09: Foto Marburg's photographs of works left out; 3: and
    # the Hertziana's; 4: types in every language and as AAT links.
    "europeana": "4",
}


def reading(source: str) -> str:
    """The version of ``source``'s reading pages are kept under."""
    return READINGS.get(source, "1")


#: The pages' room on disk.
MAX_BYTES = 200_000_000
#: The room is looked at every this many pages written.
TRIM_EVERY = 100


class SearchPages:
    def __init__(self, path: Path, version: str = "") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        #: How pages are kept (:data:`PAGES_VERSION`): pages of another
        #: count as stale, as do those of an older reading of their museum.
        self.version = version
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._written = 0
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS pages ("
                " key TEXT PRIMARY KEY, at REAL, version TEXT, total INTEGER,"
                " items BLOB, size INTEGER)"
            )

    @staticmethod
    def key(*parts: Any) -> str:
        return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))

    def get(self, key: str, now: float | None = None) -> tuple[bool, int, list[Item]] | None:
        """(fresh, total, items) of a page kept; None when there is none
        young enough to show."""
        with self._lock:
            row = self._db.execute(
                "SELECT at, version, total, items FROM pages WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        at, version, total, blob = row
        age = (now if now is not None else time.time()) - at
        if age > STALE:
            return None
        try:
            items = [Item.model_validate(d) for d in json.loads(zlib.decompress(blob))]
        except (zlib.error, ValueError) as err:
            log.info("search page %s unreadable: %s", key, err)
            return None
        return age < FRESH and version == self._version(key), int(total), items

    def put(self, key: str, total: int, items: list[Item], now: float | None = None) -> None:
        blob = zlib.compress(
            json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False).encode(), 6
        )
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO pages (key, at, version, total, items, size)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    key,
                    now if now is not None else time.time(),
                    self._version(key),
                    total,
                    blob,
                    len(blob),
                ),
            )
            self._written += 1
            trim = self._written % TRIM_EVERY == 0
        if trim:
            self.trim()

    def _version(self, key: str) -> str:
        """The version a page of ``key`` is kept under: the store's and its
        museum's reading (the key's first part)."""
        try:
            source = str(json.loads(key)[0])
        except (ValueError, IndexError, KeyError, TypeError):
            source = ""
        return f"{self.version}/{reading(source)}"

    def trim(self, room: int = MAX_BYTES) -> int:
        """The oldest pages removed until the rest fit ``room``; how many went."""
        with self._lock:
            used = int(self._db.execute("SELECT COALESCE(SUM(size), 0) FROM pages").fetchone()[0])
            if used <= room:
                return 0
            gone = 0
            for key, size in self._db.execute("SELECT key, size FROM pages ORDER BY at").fetchall():
                if used <= room:
                    break
                self._db.execute("DELETE FROM pages WHERE key = ?", (key,))
                used -= int(size)
                gone += 1
            return gone

    def __len__(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM pages").fetchone()[0])


_stores: dict[Path, SearchPages] = {}
_stores_lock = threading.Lock()


def search_pages(folder: Path) -> SearchPages:
    """The store under ``folder`` (the server's data folder), one per file."""
    path = folder / "search_pages.sqlite"
    with _stores_lock:
        if path not in _stores:
            _stores[path] = SearchPages(path, PAGES_VERSION)
        return _stores[path]
