"""National Gallery of Art, Washington: CC0 works from its open data.

The gallery has no search API, but publishes its whole collection as CSV
files on GitHub, refreshed daily, and serves every open-access picture over
IIIF in full size. The server downloads the files once a week (~230 MB),
keeps the ~45 000 open-access paintings, drawings, prints and photographs in
a small SQLite file under the data folder and searches that.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import httpx

from .models import Item
from .museums import Access, Discovery, Museum, client

log = logging.getLogger(__name__)

DATA = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data"
#: Rebuilt after this long.
REFRESH_SECONDS = 7 * 24 * 3600
#: After a failed build, the next try waits this long.
RETRY_SECONDS = 3600
#: Kinds left out: watercolour records of American crafts (the Index of
#: American Design), bound volumes and the like.
LEFT_OUT = frozenset({"Index of American Design", "Volume", "Portfolio", "Technical Material"})
#: Order of kinds in search results: pictures first.
ORDER = {"Painting": 0, "Drawing": 1, "Print": 2, "Photograph": 3}

SCHEMA = """
CREATE TABLE works (
    id INTEGER PRIMARY KEY,
    title TEXT, artist TEXT, bio TEXT, date_text TEXT, year INTEGER,
    medium TEXT, classification TEXT, styles TEXT, credit TEXT,
    iiif TEXT, width INTEGER, height INTEGER, rank INTEGER, text TEXT
);
CREATE INDEX works_kind ON works (classification, year);
"""


def _rows(http: httpx.Client, name: str) -> Iterator[dict[str, str]]:
    """The rows of one of the gallery's CSV files, read as they arrive."""
    with http.stream("GET", f"{DATA}/{name}.csv", timeout=120) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"
        yield from csv.DictReader(resp.iter_lines())


def build(path: Path, http: httpx.Client) -> int:
    """Download the open data and write the index to ``path``; returns how
    many works it holds."""
    csv.field_size_limit(1 << 24)
    pictures: dict[str, tuple[str, int, int]] = {}
    for r in _rows(http, "published_images"):
        wanted = r.get("openaccess") == "1" and r.get("viewtype") == "primary"
        if wanted and r.get("iiifurl") and r["depictstmsobjectid"] not in pictures:
            pictures[r["depictstmsobjectid"]] = (
                r["iiifurl"],
                int(r.get("width") or 0),
                int(r.get("height") or 0),
            )
    people: dict[str, tuple[str, str, str]] = {}
    for r in _rows(http, "constituents"):
        people[r["constituentid"]] = (
            r.get("forwarddisplayname") or "",
            r.get("displaydate") or "",
            r.get("nationality") or "",
        )
    makers: dict[str, tuple[int, str]] = {}
    for r in _rows(http, "objects_constituents"):
        if r.get("roletype") != "artist" or r["objectid"] not in pictures:
            continue
        order = int(r.get("displayorder") or 99)
        if r["objectid"] not in makers or order < makers[r["objectid"]][0]:
            makers[r["objectid"]] = (order, r["constituentid"])
    styles: dict[str, list[str]] = {}
    for r in _rows(http, "objects_terms"):
        if r.get("termtype") in ("Style", "School", "Theme") and r["objectid"] in pictures:
            styles.setdefault(r["objectid"], []).append(r.get("term") or "")
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    count = 0
    with sqlite3.connect(tmp) as db:
        db.executescript(SCHEMA)
        rows = []
        for r in _rows(http, "objects"):
            object_id = r["objectid"]
            kind = r.get("classification") or ""
            if object_id not in pictures or kind in LEFT_OUT:
                continue
            iiif, width, height = pictures[object_id]
            name, life, nationality = people.get(makers.get(object_id, (0, ""))[1], ("", "", ""))
            artist = name or r.get("attribution") or ""
            year = r.get("beginyear") or ""
            words = styles.get(object_id, [])
            fields = (
                r.get("title") or "",
                artist,
                life if nationality in life else ", ".join(p for p in (nationality, life) if p),
                r.get("displaydate") or "",
                int(year) if re.fullmatch(r"-?\d+", year) else None,
                r.get("medium") or "",
                kind,
                json.dumps(words),
                r.get("creditline") or "",
                iiif,
                width or None,
                height or None,
                ORDER.get(kind, 9),
            )
            text = " ".join(
                [str(f) for f in fields[:3]]
                + [str(fields[5]), kind, *words, r.get("attribution") or ""]
            )
            rows.append((int(object_id), *fields, text.lower()))
            if len(rows) >= 2000:
                db.executemany(f"INSERT INTO works VALUES ({','.join('?' * 15)})", rows)
                count += len(rows)
                rows = []
        db.executemany(f"INSERT INTO works VALUES ({','.join('?' * 15)})", rows)
        count += len(rows)
    os.replace(tmp, path)
    return count


class _Index:
    """The index file, built in the background when missing or old."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.building = False
        self.failed_at = 0.0

    def ready(self, path: Path) -> bool:
        """Whether ``path`` can be searched; starts a build when it is
        missing or a week old."""
        fresh = path.is_file() and time.time() - path.stat().st_mtime < REFRESH_SECONDS
        if not fresh:
            self._start(path)
        return path.is_file()

    def _start(self, path: Path) -> None:
        with self.lock:
            if self.building or time.time() - self.failed_at < RETRY_SECONDS:
                return
            self.building = True

        def run() -> None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                started = time.monotonic()
                with client() as http:
                    count = build(path, http)
                log.info("nga: %d works indexed in %.0f s", count, time.monotonic() - started)
            except Exception:
                log.exception("nga: building the index failed")
                self.failed_at = time.time()
            finally:
                self.building = False

        threading.Thread(target=run, name="nga-index", daemon=True).start()


INDEX = _Index()


class NationalGalleryOfArt(Museum):
    key = "nga"
    name = "National Gallery of Art"
    page_size = 100
    page_url = "https://www.nga.gov/collection/art-object-page.{}.html"

    @classmethod
    def offered(cls, access: Access) -> bool:
        return access.data_dir is not None

    kinds: ClassVar[dict[str, tuple[str, ...]]] = {
        "painting": ("Painting",),
        "drawing": ("Drawing",),
        "print": ("Print",),
        "photograph": ("Photograph",),
        "sculpture": ("Sculpture",),
        "decorative": ("Decorative Art",),
    }

    @property
    def path(self) -> Path | None:
        folder = self.access.data_dir
        return folder / "nga" / "collection.sqlite" if folder else None

    def _query(
        self, where: list[str], args: list[Any], limit: int, page: int
    ) -> tuple[int, list[Item]]:
        path = self.path
        if path is None or not INDEX.ready(path):
            return 0, []
        clause = " AND ".join(where) or "1"
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            total = db.execute(f"SELECT count(*) FROM works WHERE {clause}", args).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM works WHERE {clause} ORDER BY rank, id LIMIT ? OFFSET ?",
                [*args, limit, (page - 1) * limit],
            ).fetchall()
        return int(total), [self._map(dict(r)) for r in rows]

    def _map(self, r: dict[str, Any]) -> Item:
        iiif = str(r["iiif"]).rstrip("/")
        width = r.get("width")
        return self._item(
            str(r["id"]),
            title=r["title"] or "",
            artist=r["artist"] or "",
            artist_bio=r["bio"] or "",
            date_text=r["date_text"] or "",
            year=r["year"],
            medium=r["medium"] or "",
            classification=r["classification"] or "",
            styles=json.loads(r["styles"] or "[]"),
            subjects=[],
            credit=r["credit"] or "",
            license="CC0 1.0",
            url=self.page_url.format(r["id"]),
            image_url=f"{iiif}/full/!2560,2560/0/default.jpg",
            thumb_url=f"{iiif}/full/{'full' if width and width <= 600 else '600,'}/0/default.jpg",
            width=width,
            height=r.get("height"),
        )

    @staticmethod
    def _words(text: str) -> tuple[list[str], list[Any]]:
        words = [w for w in re.split(r"\s+", text.lower().strip()) if w]
        return ["text LIKE ?" for _ in words], [f"%{w}%" for w in words]

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        where, args = self._words(query)
        return self._query(where, args, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.highlight or spec.kind == "poster":
            return 0, []
        where, args = self._words(spec.style)
        kinds = self.kinds.get(spec.kind, ("Painting", "Drawing", "Print"))
        where.append(f"classification IN ({','.join('?' * len(kinds))})")
        args += kinds
        if spec.year_from is not None:
            where.append("year >= ?")
            args.append(spec.year_from)
        if spec.year_to is not None:
            where.append("year <= ?")
            args.append(spec.year_to)
        return self._query(where, args, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        if not source_id.isdigit():
            return None
        _, items = self._query(["id = ?"], [int(source_id)], 1, 1)
        return items[0] if items else None
