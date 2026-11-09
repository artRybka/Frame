"""The Met's open data, searched at home.

The Met publishes its whole collection as one CSV file (CC0, ~340 MB,
github.com/metmuseum/openaccess). The server asks for it every three months
and reads it only when it changed (the file's ETag, a hash of its content:
304 otherwise; Mateusz 2026-11-07: less often, less data), keeps the
public-domain works' texts in an SQLite full-text index (92 MB) under the
data folder and searches that instead of the Met's search API: a
search costs the Met nothing and takes milliseconds instead of seconds
(Mateusz 2026-11-07, after the Met's bot wall turned the home address
away). The file has no pictures: each work found is still asked of the
Met once (``/v1/objects/<id>``, kept by :mod:`.met_objects`), and works
that turn out to have no picture are left out of the next searches, also
after the index is built again.

The file has no changes of its own to fetch: the Met API's ``metadataDate``
lists the works changed since a day (2896 in our four departments in a
month, 2026-11-07), but asking each of them would be thousands of requests a
month to the API whose bot wall turned us away; the file costs the Met
nothing. Works the Met adds reach the index within three months; the words
the index knows too few works for still go to the Met's own search
(``MET_LOCAL_MIN``).
"""

from __future__ import annotations

import csv
import logging
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from .phrases import fts

log = logging.getLogger(__name__)

URL = "https://media.githubusercontent.com/media/metmuseum/openaccess/master/MetObjects.csv"
#: Asked for again after this long (and read only when it changed).
REFRESH_SECONDS = 90 * 24 * 3600
#: After a failed build, the next try waits this long.
RETRY_SECONDS = 6 * 3600
#: The night reads the file again this old, before a search would.
NIGHT_REFRESH_SECONDS = REFRESH_SECONDS - 36 * 3600
#: The departments the server asks for by number (``departmentId``).
DEPARTMENTS = {
    9: "Drawings and Prints",
    11: "European Paintings",
    12: "European Sculpture and Decorative Arts",
    19: "Photographs",
}
#: The texts searched, and how much a word found in each counts (bm25).
TEXTS = (
    ("title", 6.0),
    ("artist", 6.0),
    ("tags", 3.0),
    ("culture", 2.0),
    ("period", 2.0),
    ("medium", 1.0),
    ("kind", 1.0),
    # Where it was made: "Iznik" is a town, in no title of its tiles.
    ("place", 1.0),
)

SCHEMA = f"""
CREATE TABLE works (
    id INTEGER PRIMARY KEY, highlight INTEGER, department TEXT,
    begin INTEGER, end INTEGER, picture INTEGER DEFAULT 1
);
CREATE INDEX works_department ON works (department, begin);
CREATE VIRTUAL TABLE texts USING fts5(
    {", ".join(name for name, _ in TEXTS)},
    tokenize = 'unicode61 remove_diacritics 2'
);
"""
#: The file's columns of where a work was made.
PLACE = ("City", "State", "Country", "Region", "Subregion", "Locale", "Excavation")


def _year(text: str) -> int | None:
    text = (text or "").strip()
    return int(text) if re.fullmatch(r"-?\d+", text) else None


class Unchanged(Exception):
    """The file is the one the index was built from (304)."""


def _rows(
    http: httpx.Client, etag: str = "", seen: dict[str, str] | None = None
) -> Iterator[dict[str, str]]:
    """The file's rows, read as they arrive; :class:`Unchanged` when it is
    still the one of ``etag``. Its new ETag goes to ``seen``."""
    headers = {"If-None-Match": etag} if etag else {}
    with http.stream("GET", URL, headers=headers, timeout=300) as resp:
        if resp.status_code == 304:
            raise Unchanged
        resp.raise_for_status()
        if seen is not None:
            seen["etag"] = resp.headers.get("etag", "")
        resp.encoding = "utf-8-sig"
        yield from csv.DictReader(resp.iter_lines())


def etag_path(path: Path) -> Path:
    """Where the ETag of the file ``path`` was built from is kept."""
    return path.with_suffix(".etag")


def build(path: Path, rows: Iterator[dict[str, str]]) -> int:
    """The index of the public-domain works of ``rows`` written to
    ``path``; returns how many works it holds. Works the index there now
    knows to have no picture keep that mark."""
    csv.field_size_limit(1 << 24)
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    count = 0
    with sqlite3.connect(tmp) as db:
        db.executescript(SCHEMA)
        works: list[tuple[Any, ...]] = []
        texts: list[tuple[Any, ...]] = []

        def flush() -> None:
            db.executemany(
                "INSERT INTO works (id, highlight, department, begin, end) VALUES (?,?,?,?,?)",
                works,
            )
            db.executemany(
                f"INSERT INTO texts (rowid, {', '.join(n for n, _ in TEXTS)}) "
                f"VALUES (?{', ?' * len(TEXTS)})",
                texts,
            )
            works.clear()
            texts.clear()

        for r in rows:
            object_id = (r.get("Object ID") or "").strip()
            if r.get("Is Public Domain") != "True" or not object_id.isdigit():
                continue
            works.append(
                (
                    int(object_id),
                    int(r.get("Is Highlight") == "True"),
                    r.get("Department") or "",
                    _year(r.get("Object Begin Date") or ""),
                    _year(r.get("Object End Date") or ""),
                )
            )
            texts.append(
                (
                    int(object_id),
                    " ".join(r.get(k) or "" for k in ("Title", "Portfolio")),
                    " ".join(r.get(k) or "" for k in ("Artist Display Name", "Artist Alpha Sort")),
                    (r.get("Tags") or "").replace("|", " "),
                    r.get("Culture") or "",
                    " ".join(r.get(k) or "" for k in ("Period", "Dynasty")),
                    r.get("Medium") or "",
                    " ".join(r.get(k) or "" for k in ("Classification", "Object Name")),
                    " ".join(r.get(k) or "" for k in PLACE),
                )
            )
            if len(works) >= 5000:
                count += len(works)
                flush()
        count += len(works)
        flush()
        db.execute("INSERT INTO texts (texts) VALUES ('optimize')")
        db.commit()
        if path.is_file():
            _carry_marks(db, path)
    os.replace(tmp, path)
    return count


def _carry_marks(db: sqlite3.Connection, old: Path) -> None:
    """The works ``old`` knows to have no picture, marked in ``db`` too: the
    Met is not asked about them again after a rebuild."""
    try:
        db.execute("ATTACH DATABASE ? AS old", (str(old),))
    except sqlite3.Error as err:
        log.warning("met: marks of the old index not carried over: %s", err)
        return
    try:
        db.execute(
            "UPDATE works SET picture = 0 WHERE id IN (SELECT id FROM old.works WHERE picture = 0)"
        )
        db.commit()
    except sqlite3.Error as err:
        log.warning("met: marks of the old index not carried over: %s", err)
    finally:
        db.execute("DETACH DATABASE old")


def match(words: str) -> str:
    """An FTS5 query of every word and phrase typed (all must be there),
    each quoted: nothing typed can be read as the query language's own."""
    return fts(words)


class MetIndex:
    """Searches of one index file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(f"file:{path}?mode=rw", uri=True, check_same_thread=False)

    def search(
        self,
        words: str = "",
        department: int | None = None,
        begin: int | None = None,
        end: int | None = None,
        highlight: bool = False,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[int, list[str]]:
        """(how many works fit, the ids of ``limit`` of them from
        ``offset``): words found best first (the Met's highlights before
        the rest), without words by id. A work with a year range fits a
        span it overlaps, as the Met's ``dateBegin``/``dateEnd`` do."""
        where = ["w.picture = 1"]
        args: list[Any] = []
        query = match(words) if words.strip() != "*" else ""
        if department is not None:
            where.append("w.department = ?")
            args.append(DEPARTMENTS.get(department, ""))
        if begin is not None:
            where.append("w.end >= ?")
            args.append(begin)
        if end is not None:
            where.append("w.begin <= ?")
            args.append(end)
        if highlight:
            where.append("w.highlight = 1")
        weights = ", ".join(str(w) for _, w in TEXTS)
        if query:
            source = "texts JOIN works w ON w.id = texts.rowid"
            where.insert(0, "texts MATCH ?")
            args.insert(0, query)
            order = f"w.highlight DESC, bm25(texts, {weights})"
        else:
            source = "works w"
            order = "w.id"
        clause = " AND ".join(where)
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) FROM {source} WHERE {clause}", args)
            count = int(total.fetchone()[0])
            found = self._db.execute(
                f"SELECT w.id FROM {source} WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return count, [str(row[0]) for row in found]

    def showable(self, ids: list[str]) -> list[str]:
        """``ids`` (of the Met's own search) without the works its open data
        says are not in the public domain, or that showed no picture: not
        worth a request each (2026-11-07: of its first 8 for "Monet", none
        was in the public domain)."""
        numbers = [int(i) for i in ids if str(i).isdigit()]
        if not numbers:
            return []
        marks = ",".join("?" * len(numbers))
        with self._lock:
            kept = {
                row[0]
                for row in self._db.execute(
                    f"SELECT id FROM works WHERE picture = 1 AND id IN ({marks})", numbers
                )
            }
        return [str(i) for i in numbers if i in kept]

    def no_picture(self, object_id: str) -> None:
        """A work the Met shows no picture of: left out from now on."""
        if not object_id.isdigit():
            return
        with self._lock:
            self._db.execute("UPDATE works SET picture = 0 WHERE id = ?", (int(object_id),))
            self._db.commit()


class _Index:
    """The index file, built in the background when missing or old."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.building = False
        self.failed_at = 0.0
        self._open: dict[Path, tuple[float, MetIndex]] = {}

    def get(self, folder: Path) -> MetIndex | None:
        """The index under ``folder``, None while there is none yet (its
        first build starts then, in the background); an old one is read
        again behind."""
        path = index_path(folder)
        if not path.is_file():
            self._start(path)
            return None
        stamp = path.stat().st_mtime
        if time.time() - stamp >= REFRESH_SECONDS:
            self._start(path)
        with self.lock:
            kept = self._open.get(path)
            if kept is None or kept[0] != stamp:  # rebuilt meanwhile
                kept = (stamp, MetIndex(path))
                self._open[path] = kept
            return kept[1]

    def _start(self, path: Path) -> None:
        if self._claim():
            threading.Thread(
                target=self._build, args=(path,), name="met-index", daemon=True
            ).start()

    def _claim(self) -> bool:
        with self.lock:
            if self.building or time.time() - self.failed_at < RETRY_SECONDS:
                return False
            self.building = True
            return True

    def _build(self, path: Path) -> None:
        from .museums import client

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            etag_file = etag_path(path)
            etag = etag_file.read_text().strip() if path.is_file() and etag_file.is_file() else ""
            seen: dict[str, str] = {}
            with client() as http:
                count = build(path, _rows(http, etag, seen))
            etag_file.write_text(seen.get("etag", ""))
            log.info("met: %d works indexed in %.0f s", count, time.monotonic() - started)
        except Unchanged:
            path.with_suffix(".tmp").unlink(missing_ok=True)
            os.utime(path)  # fresh for another REFRESH_SECONDS
            log.info("met: the open data has not changed; the index stays")
        except Exception:
            log.exception("met: building the index failed")
            self.failed_at = time.time()
        finally:
            self.building = False

    def refresh(self, folder: Path, older: float = NIGHT_REFRESH_SECONDS) -> bool:
        """The night's task: the file asked for again before the index gets
        REFRESH_SECONDS old (or for the first time), so that it never falls
        on a search; read only when it changed. Whether there is an index."""
        path = index_path(folder)
        if path.is_file() and time.time() - path.stat().st_mtime < older:
            return False
        if not self._claim():
            return False
        self._build(path)
        return path.is_file()


def index_path(folder: Path) -> Path:
    return folder / "met" / "index.sqlite"


INDEX = _Index()


def refresh_at_night(data_dir: Path) -> bool:
    return INDEX.refresh(data_dir)
