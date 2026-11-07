"""The Met's object records, kept on disk.

A page of the Met's search is one request for the ids and one more for
each work on it (``/v1/objects/<id>``): a set of 24 works is 25 requests,
and a few sets opened at once are hundreds a minute from the home
address, which the Met's bot wall (Imperva) turned away (2026-10-30,
2026-11-07). A work's record hardly ever changes, so each one is asked
once and read from here after that, for :data:`KEEP_DAYS` days; works
the Met no longer has (404) are remembered too. Only the fields the
server reads are kept (~1 KB a work)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

#: How long a record is trusted: the Met corrects dates and titles, and
#: now and then a picture.
KEEP_DAYS = 90
#: The fields :class:`~frame_server.library.museums.MetropolitanMuseum`
#: maps; the rest of a record (constituents, measurements…) is left out.
FIELDS = (
    "objectID",
    "isPublicDomain",
    "isHighlight",
    "primaryImage",
    "primaryImageSmall",
    "title",
    "artistDisplayName",
    "artistDisplayBio",
    "objectDate",
    "objectBeginDate",
    "medium",
    "classification",
    "objectName",
    "period",
    "culture",
    "dynasty",
    "department",
    "tags",
    "creditLine",
    "objectURL",
)
#: A record asked lately that the Met does not have.
_GONE = "null"


def trimmed(record: dict[str, Any]) -> dict[str, Any]:
    """``record`` with only :data:`FIELDS`."""
    return {k: record[k] for k in FIELDS if k in record}


class MetObjects:
    """Records by object id in one SQLite file, shared by every thread."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, record TEXT, at REAL)"
            )

    def get(self, object_id: str, now: float | None = None) -> tuple[bool, dict[str, Any] | None]:
        """(True, record) when kept and fresh, (True, None) when the Met
        did not have it, (False, None) when it must be asked."""
        with self._lock:
            row = self._db.execute(
                "SELECT record, at FROM objects WHERE id = ?", (object_id,)
            ).fetchone()
        if row is None:
            return False, None
        record, at = row
        if (now if now is not None else time.time()) - at > KEEP_DAYS * 86400:
            return False, None
        return True, None if record == _GONE else json.loads(record)

    def put(self, object_id: str, record: dict[str, Any] | None, now: float | None = None) -> None:
        text = _GONE if record is None else json.dumps(trimmed(record), ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO objects (id, record, at) VALUES (?, ?, ?)",
                (object_id, text, now if now is not None else time.time()),
            )

    def __len__(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM objects").fetchone()[0])


_stores: dict[Path, MetObjects] = {}
_stores_lock = threading.Lock()


def met_objects(folder: Path) -> MetObjects:
    """The store under ``folder`` (the server's data folder), one per file."""
    path = folder / "met" / "objects.sqlite"
    with _stores_lock:
        if path not in _stores:
            _stores[path] = MetObjects(path)
        return _stores[path]
