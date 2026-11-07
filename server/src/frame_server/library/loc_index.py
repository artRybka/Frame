"""The Library of Congress's photograph collections the server draws from,
kept at home (Mateusz 2026-11-07, after www.loc.gov blocked the home
address for the second morning).

The LoC's rules are the strictest of our sources: 20 requests a minute to
its JSON API, else the address is blocked for an hour, and every request
during the block starts the hour again. Its collections the server draws
from (Prokudin-Gorsky, the photochroms, FSA/OWI in colour, the Civil War
glass negatives, Frances Benjamin Johnston, the National Child Labor
Committee: ~29 000 photographs together) are archives that hardly change.
So every three months, at night, each is read whole, a thousand results a
request (~30 requests), and kept here: drawing from them, a set of
"Pierwsze kolory" and a search within one of them (``collection:<slug>
words``) then cost the LoC nothing. Words typed in Szukaj still go to the
LoC's own search of all its photographs, and so does the FSA's
black-and-white collection (170 000 negatives), drawn from by the app only.

Results are kept as the LoC gave them (only the fields read, compressed)
and read into works by :class:`.loc.LibraryOfCongress` each time, so a new
reading applies to them at once.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

API = "https://www.loc.gov"
#: The collections kept, by their slug on www.loc.gov/collections/.
KEPT = (
    "prokudin-gorskii",
    "photochrom-prints",
    "fsa-owi-color-photographs",
    "civil-war-glass-negatives",
    "frances-benjamin-johnston",
    "national-child-labor-committee",
)
#: Results a request: the most the API gives (loc.gov/apis, 2026-11-07).
PAGE = 1000
#: The night reads them again this old.
NIGHT_REFRESH_SECONDS = 90 * 24 * 3600 - 36 * 3600
#: After a failed build, the next try waits this long.
RETRY_SECONDS = 6 * 3600
#: The fields of a result :meth:`.loc.LibraryOfCongress._map` reads.
FIELDS = (
    "number_lccn",
    "control_number",
    "access_restricted",
    "rights_advisory",
    "medium",
    "genre",
    "image_url",
    "mime_type",
    "creators",
    "contributor_names",
    "contributors",
    "created_published_date",
    "created_published",
    "date",
    "dates",
    "subject_headings",
    "title",
    "source_collection",
    "part_of",
    "summary",
)
#: The texts searched, and how much a word found in each counts (bm25).
TEXTS = (("title", 6.0), ("people", 6.0), ("subjects", 3.0), ("summary", 1.0))

SCHEMA = f"""
CREATE TABLE works (
    number TEXT PRIMARY KEY, collection TEXT, ord INTEGER, year INTEGER, record BLOB
);
CREATE INDEX works_collection ON works (collection, ord);
CREATE VIRTUAL TABLE texts USING fts5(
    {", ".join(name for name, _ in TEXTS)},
    tokenize = 'unicode61 remove_diacritics 2'
);
"""
_WORD = re.compile(r"\w+")


def flat(result: dict[str, Any]) -> dict[str, Any]:
    """A result with the facts it keeps under "item" brought up, only the
    fields read."""
    merged = {**(result.get("item") or {}), **{k: v for k, v in result.items() if k != "item"}}
    return {k: merged[k] for k in FIELDS if k in merged}


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values() if isinstance(v, str))
    return str(value or "")


def _year(record: dict[str, Any]) -> int | None:
    for key in ("created_published_date", "created_published", "date", "dates"):
        found = re.search(r"\b(1[89]\d\d|20\d\d)\b", _text(record.get(key)))
        if found:
            return int(found.group(1))
    return None


def _number(record: dict[str, Any]) -> str:
    for key in ("number_lccn", "control_number"):
        value = record.get(key)
        value = value[0] if isinstance(value, list) and value else value
        if isinstance(value, str) and value.isdigit():
            return value
    return ""


def results(http: httpx.Client, slug: str) -> Iterator[dict[str, Any]]:
    """Every result of collection ``slug``, page by page."""
    page = 1
    while True:
        resp = http.get(
            f"{API}/collections/{slug}/",
            params={
                "fo": "json",
                "c": PAGE,
                "sp": page,
                "fa": "online-format:image",
                "at": "results,pagination",
            },
            timeout=120,
        )
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        body = resp.json()
        found = [r for r in body.get("results") or [] if isinstance(r, dict)]
        yield from found
        pagination = body.get("pagination") or {}
        if not found or not pagination.get("next"):
            return
        page += 1


def build(path: Path, collections: dict[str, Iterator[dict[str, Any]]]) -> int:
    """The index of ``collections``' results (by slug) written to ``path``;
    returns how many photographs it holds."""
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    count = 0
    with sqlite3.connect(tmp) as db:
        db.executescript(SCHEMA)
        for slug, rows in collections.items():
            for ord_, result in enumerate(rows):
                record = flat(result)
                number = _number(record)
                if not number:
                    continue
                blob = zlib.compress(json.dumps(record, ensure_ascii=False).encode(), 6)
                cursor = db.execute(
                    "INSERT OR IGNORE INTO works (number, collection, ord, year, record)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (number, slug, ord_, _year(record), blob),
                )
                if not cursor.rowcount:
                    continue  # in two collections: kept in the first
                db.execute(
                    "INSERT INTO texts (rowid, title, people, subjects, summary)"
                    " VALUES ((SELECT rowid FROM works WHERE number = ?), ?, ?, ?, ?)",
                    (
                        number,
                        _text(record.get("title")),
                        _text(record.get("contributor_names") or record.get("creators")),
                        _text(record.get("subject_headings")),
                        _text(record.get("summary")),
                    ),
                )
                count += 1
        db.execute("INSERT INTO texts (texts) VALUES ('optimize')")
        db.commit()
    os.replace(tmp, path)
    return count


def match(words: str) -> str:
    """An FTS5 query of every word typed, each quoted."""
    return " ".join(f'"{w}"' for w in _WORD.findall(words))


class LocIndex:
    """Searches of one index file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)

    def collections(self) -> set[str]:
        with self._lock:
            return {row[0] for row in self._db.execute("SELECT DISTINCT collection FROM works")}

    def search(
        self,
        collection: str,
        words: str = "",
        begin: int | None = None,
        end: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[dict[str, Any]]]:
        """(how many fit, the records of ``limit`` of them from ``offset``):
        in the collection's own order, words found best first."""
        where = ["w.collection = ?"]
        args: list[Any] = [collection]
        if begin is not None:
            where.append("w.year >= ?")
            args.append(begin)
        if end is not None:
            where.append("w.year <= ?")
            args.append(end)
        query = match(words)
        if query:
            source = "texts JOIN works w ON w.rowid = texts.rowid"
            where.insert(0, "texts MATCH ?")
            args.insert(0, query)
            weights = ", ".join(str(w) for _, w in TEXTS)
            order = f"bm25(texts, {weights})"
        else:
            source = "works w"
            order = "w.ord"
        clause = " AND ".join(where)
        with self._lock:
            count = int(
                self._db.execute(f"SELECT COUNT(*) FROM {source} WHERE {clause}", args).fetchone()[
                    0
                ]
            )
            rows = self._db.execute(
                f"SELECT w.record FROM {source} WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return count, [json.loads(zlib.decompress(row[0])) for row in rows]

    def record(self, number: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT record FROM works WHERE number = ?", (number,)
            ).fetchone()
        return json.loads(zlib.decompress(row[0])) if row else None


class _Index:
    """The index file, built in the background when missing or old."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.building = False
        self.failed_at = 0.0
        self._open: dict[Path, tuple[float, LocIndex]] = {}

    def get(self, folder: Path) -> LocIndex | None:
        """The index under ``folder``; None while there is none yet. It is
        built and read again only at night (:func:`refresh_at_night`): built
        behind a draw, it asked the LoC twice during its block on 2026-11-07
        and so started the block's hour again."""
        path = index_path(folder)
        if not path.is_file():
            return None
        stamp = path.stat().st_mtime
        with self.lock:
            kept = self._open.get(path)
            if kept is None or kept[0] != stamp:  # rebuilt meanwhile
                kept = (stamp, LocIndex(path))
                self._open[path] = kept
            return kept[1]

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
            with client() as http:
                count = build(path, {slug: results(http, slug) for slug in KEPT})
            log.info("loc: %d photographs kept in %.0f s", count, time.monotonic() - started)
        except Exception:
            path.with_suffix(".tmp").unlink(missing_ok=True)
            log.exception("loc: keeping the collections failed")
            self.failed_at = time.time()
        finally:
            self.building = False

    def refresh(self, folder: Path, older: float = NIGHT_REFRESH_SECONDS) -> bool:
        """The night's task: the collections read again before the index
        gets three months old (or for the first time). Whether there is
        an index."""
        path = index_path(folder)
        if path.is_file() and time.time() - path.stat().st_mtime < older:
            return False
        if not self._claim():
            return False
        self._build(path)
        return path.is_file()


def index_path(folder: Path) -> Path:
    return folder / "loc" / "collections.sqlite"


INDEX = _Index()


def refresh_at_night(data_dir: Path) -> bool:
    return INDEX.refresh(data_dir)
