"""Museums' records of single works, kept on disk (Mateusz 2026-11-07,
"spójna polityka korzystania ze źródeł").

The Rijksmuseum's search answers with ids only and Yale's LUX with records
that name a IIIF manifest: a page of 24 works was 25 requests to the
Rijksmuseum and 49 to Yale, every time it was opened. A work's record hardly
ever changes, so each is asked once and read from here for
:data:`KEEP_DAYS` days (the Met's have their own store, :mod:`.met_objects`).
Records are kept whole, compressed (the Rijksmuseum's 70 KB of Linked Art
take ~7 KB): the server maps them afresh each time, so a new version's
mapping applies to them at once. Works a museum no longer has (404) are
remembered too.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import zlib
from pathlib import Path
from typing import Any

#: How long a record is trusted: museums correct dates and titles, and now
#: and then a picture.
KEEP_DAYS = 90
#: A record the museum does not have.
_GONE = b""


class Records:
    """Records by source and id in one SQLite file, shared by every thread."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS records ("
                " source TEXT, id TEXT, record BLOB, at REAL, PRIMARY KEY (source, id))"
            )

    def get(
        self, source: str, key: str, days: float = KEEP_DAYS, now: float | None = None
    ) -> tuple[bool, Any]:
        """(True, record) when kept and fresh, (True, None) when the museum
        did not have it, (False, None) when it must be asked."""
        with self._lock:
            row = self._db.execute(
                "SELECT record, at FROM records WHERE source = ? AND id = ?", (source, key)
            ).fetchone()
        if row is None:
            return False, None
        record, at = row
        if (now if now is not None else time.time()) - at > days * 86400:
            return False, None
        if record == _GONE:
            return True, None
        try:
            return True, json.loads(zlib.decompress(record))
        except (zlib.error, ValueError):
            return False, None

    def put(self, source: str, key: str, record: Any, now: float | None = None) -> None:
        """Keeps ``record`` (None: the museum does not have the work)."""
        data = (
            _GONE
            if record is None
            else zlib.compress(json.dumps(record, ensure_ascii=False).encode(), 6)
        )
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO records (source, id, record, at) VALUES (?, ?, ?, ?)",
                (source, key, data, now if now is not None else time.time()),
            )

    def __len__(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM records").fetchone()[0])


_stores: dict[Path, Records] = {}
_stores_lock = threading.Lock()


def records(folder: Path) -> Records:
    """The store under ``folder`` (the server's data folder), one per file."""
    path = folder / "records.sqlite"
    with _stores_lock:
        if path not in _stores:
            _stores[path] = Records(path)
        return _stores[path]
