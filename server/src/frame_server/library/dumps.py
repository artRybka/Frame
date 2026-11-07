"""Museums' published data dumps, searched at home (Mateusz 2026-11-07:
"to co robimy w NGA, Courtauld i Luwr ... mocno przyspiesza działanie
aplikacji i ogranicza zbędne odpytania").

Four sources publish their whole open collection as files: the Art
Institute of Chicago (one archive of the API's own records, monthly; its
docs ask for it instead of the API), the Cleveland Museum of Art (one JSON
file on GitHub), the Smithsonian (line JSON files per museum on S3, weekly)
and the Wellcome Collection (its whole catalogue, daily). The server asks
for each every two months, at night, and reads it only when it changed
(the file's ETag); Mateusz: "Wątpliwe że van Gogh coś jeszcze namaluje".
The first build is the night's too: until then the museums are asked as
before.

Each source's works go into one SQLite file under the data folder: the
record as the source's API gives it (trimmed to what its mapping reads),
the work's kinds for the filters, its year, and its texts in a full-text
index. The source's own :meth:`Museum._map` reads the records, so a work
found at home is the same work its API would have given. Searches and
draws (Szukaj, Odkrywaj, playlists, colours, copies) then ask the museum
nothing; only pictures still come from its image server. Words the index
finds too few works for still go to the museum's own search
(:data:`LOCAL_MIN`), and so does everything while no index is there yet.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import tarfile
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from xml.etree import ElementTree

import httpx

if TYPE_CHECKING:
    from .models import Item
    from .museums import Museum

log = logging.getLogger(__name__)

#: A dump is asked for again after this long, and read only when it changed.
REFRESH_SECONDS = 60 * 24 * 3600
#: The night asks for it this old, before a search would.
NIGHT_REFRESH_SECONDS = REFRESH_SECONDS - 36 * 3600
#: After a failed build, the next try waits this long.
RETRY_SECONDS = 6 * 3600
#: Works an index must find for words typed before the museum's own search
#: is left alone: its search reads texts the dump may lack, and finds
#: forms of words the index does not.
LOCAL_MIN = 12
#: The texts searched, and how much a word found in each counts (bm25).
COLUMNS: tuple[tuple[str, float], ...] = (
    ("title", 6.0),
    ("artist", 6.0),
    ("tags", 3.0),
    ("place", 2.0),
    ("medium", 1.0),
    ("kind", 1.0),
    ("about", 0.3),
)
NAMES = tuple(name for name, _ in COLUMNS)

SCHEMA = f"""
CREATE TABLE works (
    n INTEGER PRIMARY KEY, id TEXT UNIQUE, year INTEGER, highlight INTEGER,
    private INTEGER, rank REAL, record TEXT
);
CREATE INDEX works_year ON works (year);
CREATE TABLE kinds (n INTEGER, kind TEXT);
CREATE INDEX kinds_kind ON kinds (kind, n);
CREATE VIRTUAL TABLE texts USING fts5(
    {", ".join(NAMES)},
    tokenize = 'porter unicode61 remove_diacritics 2'
);
"""
_WORD = re.compile(r"\w+")


class Unchanged(Exception):
    """The dump is the one the index was built from."""


@dataclass
class Entry:
    """One work as the index keeps it."""

    id: str
    record: dict[str, Any]
    year: int | None
    highlight: bool
    #: Shown only with "Użytek prywatny" (its licence).
    private: bool
    #: Order of works without words: lower first.
    rank: float
    kinds: list[str]
    texts: dict[str, str] = field(default_factory=dict)


def match(words: str) -> str:
    """An FTS5 query of every word typed (all must be there), each quoted:
    nothing typed can be read as the query language's own."""
    return " ".join(f'"{w}"' for w in _WORD.findall(words))


#: Kinds in the order results show them: what the frame shows best first
#: (as the NGA's index does).
_KIND_ORDER = (
    (re.compile(r"paint|gouache|tempera|oil", re.IGNORECASE), 0),
    (re.compile(r"draw|water-?colou?r|pastel|sketch", re.IGNORECASE), 1),
    (re.compile(r"print|engrav|etch|woodcut|lithograph|mezzotint|aquatint|poster", re.I), 2),
    (re.compile(r"photo", re.IGNORECASE), 3),
)


def kind_order(classification: str) -> float:
    return next((at for found, at in _KIND_ORDER if found.search(classification)), 4)


def item_texts(item: Item) -> dict[str, str]:
    """A work's texts from its :class:`Item`, as most sources search them."""
    return {
        "title": item.title,
        "artist": " ".join((item.artist, item.artist_bio)),
        "tags": " ".join((*item.styles, *item.subjects)),
        "place": item.culture,
        "medium": item.medium,
        "kind": item.classification,
        "about": item.description,
    }


class Dump(ABC):
    """One source's published dump: where it is, and how its records become
    the index's entries."""

    #: The source's key (``Museum.key``).
    key: ClassVar[str]

    @abstractmethod
    def records(self, http: httpx.Client, stamp: str, seen: dict[str, str]) -> Iterator[Any]:
        """The dump's records as they arrive; :class:`Unchanged` when it is
        still the one of ``stamp``. Its new stamp goes to ``seen["stamp"]``."""

    @abstractmethod
    def museum(self, private_use: bool) -> Museum:
        """The source, to map records as its API's (no requests)."""

    def trim(self, record: dict[str, Any]) -> dict[str, Any]:
        """What of a record is kept: what the source's mapping reads."""
        return record

    def kinds(self, record: dict[str, Any], item: Item) -> list[str]:
        """What the source's filters call the work (its type, genres)."""
        return [item.classification] if item.classification else []

    def texts(self, record: dict[str, Any], item: Item) -> dict[str, str]:
        return item_texts(item)

    def rank(self, record: dict[str, Any], item: Item) -> float:
        """Order among works that fit equally (lower first): the frame's
        pictures before the rest, a museum's highlights first among them."""
        return kind_order(item.classification) - (0.5 if item.highlight else 0.0)

    def entries(self, records: Iterable[Any]) -> Iterator[Entry]:
        public, private = self.museum(False), self.museum(True)
        for raw in records:
            if not isinstance(raw, dict):
                continue
            record = self.trim(raw)
            try:
                item = private._map(record)  # type: ignore[attr-defined]
                if item is None:
                    continue
                shown = public._map(record)  # type: ignore[attr-defined]
            except Exception as err:  # one odd record costs no other
                log.debug("%s: record left out: %s", self.key, err)
                continue
            yield Entry(
                id=item.source_id,
                record=record,
                year=item.year,
                highlight=item.highlight,
                private=shown is None,
                rank=self.rank(record, item),
                kinds=self.kinds(record, item),
                texts=self.texts(record, item),
            )


def build(path: Path, entries: Iterable[Entry]) -> int:
    """The index of ``entries`` written to ``path``; returns how many works
    it holds."""
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    count = 0
    with sqlite3.connect(tmp) as db:
        db.executescript(SCHEMA)
        seen: set[str] = set()
        works: list[tuple[Any, ...]] = []
        kinds: list[tuple[Any, ...]] = []
        texts: list[tuple[Any, ...]] = []

        def flush() -> None:
            db.executemany("INSERT INTO works VALUES (?,?,?,?,?,?,?)", works)
            db.executemany("INSERT INTO kinds VALUES (?,?)", kinds)
            db.executemany(
                f"INSERT INTO texts (rowid, {', '.join(NAMES)}) VALUES (?{', ?' * len(NAMES)})",
                texts,
            )
            works.clear()
            kinds.clear()
            texts.clear()

        for entry in entries:
            if entry.id in seen:
                continue
            seen.add(entry.id)
            count += 1
            works.append(
                (
                    count,
                    entry.id,
                    entry.year,
                    int(entry.highlight),
                    int(entry.private),
                    entry.rank,
                    json.dumps(entry.record, separators=(",", ":"), ensure_ascii=False),
                )
            )
            kinds += [(count, k) for k in dict.fromkeys(entry.kinds) if k]
            texts.append((count, *(entry.texts.get(name, "") or "" for name in NAMES)))
            if len(works) >= 2000:
                flush()
        flush()
        if not count:
            raise ValueError("the dump held no work to show")
        db.execute("INSERT INTO texts (texts) VALUES ('optimize')")
        db.commit()
    os.replace(tmp, path)
    return count


class DumpIndex:
    """Searches of one index file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)

    def search(
        self,
        words: str = "",
        *,
        columns: tuple[str, ...] = (),
        also: Iterable[tuple[str, tuple[str, ...]]] = (),
        kinds: Iterable[str] = (),
        year_from: int | None = None,
        year_to: int | None = None,
        highlight: bool = False,
        private_use: bool = False,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[int, list[dict[str, Any]]]:
        """(how many works fit, the records of ``limit`` of them from
        ``offset``): every word in any text (or in ``columns`` only), of
        one of ``kinds``, from years; found best first (highlights before
        the rest), without words in the source's own order. ``also``: more
        words that must be there too, each in its own texts."""
        where: list[str] = []
        args: list[Any] = []
        parts = []
        for text, where_in in [(words, columns), *also]:
            if group := match(text):
                inside = " ".join(c for c in where_in if c in NAMES)
                parts.append(f"{{{inside}}} : ({group})" if inside else f"({group})")
        query = " AND ".join(parts)
        if not private_use:
            where.append("w.private = 0")
        wanted = [k for k in kinds if k]
        if wanted:
            marks = ",".join("?" * len(wanted))
            where.append(f"w.n IN (SELECT n FROM kinds WHERE kind IN ({marks}))")
            args += wanted
        if year_from is not None:
            where.append("w.year >= ?")
            args.append(year_from)
        if year_to is not None:
            where.append("w.year <= ?")
            args.append(year_to)
        if highlight:
            where.append("w.highlight = 1")
        if query:
            source = "texts JOIN works w ON w.n = texts.rowid"
            where.insert(0, "texts MATCH ?")
            args.insert(0, query)
            weights = ", ".join(str(w) for _, w in COLUMNS)
            order = f"w.highlight DESC, w.rank, bm25(texts, {weights})"
        else:
            source = "works w"
            order = "w.rank, w.n"
        clause = " AND ".join(where) or "1"
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
        return count, [json.loads(row[0]) for row in rows]

    def get(self, work_id: str) -> dict[str, Any] | None:
        """One work's record, None when the index has none of that id."""
        with self._lock:
            row = self._db.execute("SELECT record FROM works WHERE id = ?", (work_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self) -> None:
        with self._lock:
            self._db.close()


def index_path(folder: Path, key: str) -> Path:
    return folder / "dumps" / f"{key}.sqlite"


def stamp_path(path: Path) -> Path:
    """Where the stamp (ETag) of the dump ``path`` was built from is kept."""
    return path.with_suffix(".stamp")


class _Indexes:
    """The index files, built in the background when missing or old."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.building: set[str] = set()
        self.failed_at: dict[str, float] = {}
        self._open: dict[Path, tuple[float, DumpIndex]] = {}
        #: Builds may start when a search finds no index or an old one. Off:
        #: dumps are read at night only (the night's tasks), as the LoC's
        #: collections are, never while the owner uses the app.
        self.build_on_demand = False

    def get(self, dump: Dump, folder: Path) -> DumpIndex | None:
        """``dump``'s index under ``folder``, None while there is none yet
        (the night builds it)."""
        path = index_path(folder, dump.key)
        if not path.is_file():
            self._start(dump, path)
            return None
        stamp = path.stat().st_mtime
        if time.time() - stamp >= REFRESH_SECONDS:
            self._start(dump, path)
        with self.lock:
            kept = self._open.get(path)
            if kept is None or kept[0] != stamp:  # rebuilt meanwhile
                try:
                    kept = (stamp, DumpIndex(path))
                except sqlite3.Error as err:
                    log.warning("%s: index not opened: %s", dump.key, err)
                    return None
                self._open[path] = kept
            return kept[1]

    def _start(self, dump: Dump, path: Path) -> None:
        if self.build_on_demand and self._claim(dump.key):
            threading.Thread(
                target=self._build, args=(dump, path), name=f"{dump.key}-index", daemon=True
            ).start()

    def _claim(self, key: str) -> bool:
        with self.lock:
            if key in self.building or time.time() - self.failed_at.get(key, 0.0) < RETRY_SECONDS:
                return False
            self.building.add(key)
            return True

    def _build(self, dump: Dump, path: Path, http: httpx.Client | None = None) -> None:
        from .museums import client

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            stamp_file = stamp_path(path)
            stamp = (
                stamp_file.read_text().strip() if path.is_file() and stamp_file.is_file() else ""
            )
            seen: dict[str, str] = {}
            with http or client() as session:
                count = build(path, dump.entries(dump.records(session, stamp, seen)))
            stamp_file.write_text(seen.get("stamp", ""))
            log.info("%s: %d works indexed in %.0f s", dump.key, count, time.monotonic() - started)
        except Unchanged:
            path.with_suffix(".tmp").unlink(missing_ok=True)
            os.utime(path)  # fresh for another REFRESH_SECONDS
            log.info("%s: the dump has not changed; the index stays", dump.key)
        except Exception:
            path.with_suffix(".tmp").unlink(missing_ok=True)
            log.exception("%s: building the index failed", dump.key)
            with self.lock:
                self.failed_at[dump.key] = time.time()
        finally:
            with self.lock:
                self.building.discard(dump.key)

    def refresh(
        self,
        dump: Dump,
        folder: Path,
        older: float = NIGHT_REFRESH_SECONDS,
        http: httpx.Client | None = None,
    ) -> bool:
        """The night's task: the dump asked for again before the index gets
        REFRESH_SECONDS old (or for the first time), so that it never falls
        on a search; read only when it changed. Whether there is an index."""
        path = index_path(folder, dump.key)
        if path.is_file() and time.time() - path.stat().st_mtime < older:
            return False
        if not self._claim(dump.key):
            return False
        self._build(dump, path, http)
        return path.is_file()


INDEXES = _Indexes()


# -- the sources -----------------------------------------------------------------


def _etag_get(
    http: httpx.Client, url: str, stamp: str, seen: dict[str, str], timeout: float = 600
) -> Iterator[httpx.Response]:
    """The streamed answer for ``url``, unless it still has the ETag
    ``stamp`` (:class:`Unchanged`)."""
    headers = {"If-None-Match": stamp} if stamp else {}
    with http.stream("GET", url, headers=headers, timeout=timeout) as resp:
        if resp.status_code == 304:
            raise Unchanged
        resp.raise_for_status()
        seen["stamp"] = resp.headers.get("etag", "")
        yield resp


class _Stream(io.RawIOBase):
    """A file-like reader of a streamed answer's bytes (for tarfile, gzip)."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        super().__init__()
        self._chunks = chunks
        self._left = memoryview(b"")

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        while not self._left:
            chunk = next(self._chunks, None)
            if chunk is None:
                return 0
            self._left = memoryview(chunk)
        size = min(len(buffer), len(self._left))
        buffer[:size] = self._left[:size]
        self._left = self._left[size:]
        return size


class AicDump(Dump):
    """The AIC's whole API as one archive, refreshed monthly
    (api.artic.edu/docs: "please download the data dump ... rather than
    scraping our API"): a JSON file a record, ~130 MB compressed."""

    key = "aic"
    url = "https://artic-api-data.s3.amazonaws.com/artic-api-data.tar.bz2"

    def museum(self, private_use: bool) -> Museum:
        from .museums import Access, ArtInstituteChicago

        return ArtInstituteChicago(None, access=Access(private_use=private_use))  # type: ignore[arg-type]

    def records(self, http: httpx.Client, stamp: str, seen: dict[str, str]) -> Iterator[Any]:
        for resp in _etag_get(http, self.url, stamp, seen, timeout=900):
            with tarfile.open(
                fileobj=io.BufferedReader(_Stream(resp.iter_bytes()), 1 << 20), mode="r|bz2"
            ) as archive:
                for member in archive:
                    if not member.isfile() or "/artworks/" not in member.name:
                        continue
                    if not member.name.endswith(".json"):
                        continue
                    data = archive.extractfile(member)
                    if data is None:
                        continue
                    try:
                        yield json.loads(data.read())
                    except ValueError:
                        continue

    #: What the mapping and the filters read, of the API's ~100 fields.
    kept = frozenset(
        {
            "id",
            "title",
            "alt_titles",
            "artist_title",
            "artist_display",
            "date_display",
            "date_start",
            "medium_display",
            "artwork_type_title",
            "style_titles",
            "subject_titles",
            "term_titles",
            "classification_titles",
            "place_of_origin",
            "credit_line",
            "description",
            "short_description",
            "image_id",
            "thumbnail",
            "is_public_domain",
            "boost_rank",
            "is_boosted",
        }
    )

    def trim(self, record: dict[str, Any]) -> dict[str, Any]:
        kept = {k: v for k, v in record.items() if k in self.kept}
        thumb = kept.get("thumbnail")
        if isinstance(thumb, dict):  # its blurred preview is a picture of its own
            kept["thumbnail"] = {k: thumb.get(k) for k in ("width", "height")}
        return kept

    def kinds(self, record: dict[str, Any], item: Item) -> list[str]:
        return [str(record.get("artwork_type_title") or "")]

    def texts(self, record: dict[str, Any], item: Item) -> dict[str, str]:
        # As the API's search reads them (ArtInstituteChicago.search_fields),
        # descriptions aside.
        def joined(*keys: str) -> str:
            values: list[str] = []
            for key in keys:
                value = record.get(key)
                values += value if isinstance(value, list) else [value or ""]
            return " ".join(str(v) for v in values if v)

        return {
            "title": joined("title", "alt_titles"),
            "artist": joined("artist_title", "artist_display"),
            "tags": joined("style_titles", "subject_titles"),
            "place": joined("place_of_origin"),
            "medium": joined("medium_display"),
            "kind": joined("artwork_type_title", "classification_titles", "term_titles"),
        }

    def rank(self, record: dict[str, Any], item: Item) -> float:
        # The works its own search puts first ("boosted": its best known).
        boosted = record.get("is_boosted") or record.get("boost_rank") is not None
        return super().rank(record, item) - (0.5 if boosted else 0.0)


class ClevelandDump(Dump):
    """The CMA's open data as one JSON file on GitHub (CC0, ~340 MB): every
    record as its API gives it, an array printed two spaces deep."""

    key = "cma"
    url = "https://media.githubusercontent.com/media/ClevelandMuseumArt/openaccess/master/data.json"

    def museum(self, private_use: bool) -> Museum:
        from .museums import Access, ClevelandMuseum

        return ClevelandMuseum(None, access=Access(private_use=private_use))  # type: ignore[arg-type]

    #: The museum's highlights, which the file does not mark: one request.
    highlights = (
        "https://openaccess-api.clevelandart.org/api/artworks/"
        "?highlight=1&cc0=1&has_image=1&fields=id&limit=1000"
    )

    def records(self, http: httpx.Client, stamp: str, seen: dict[str, str]) -> Iterator[Any]:
        for resp in _etag_get(http, self.url, stamp, seen, timeout=900):
            asked = http.get(self.highlights, timeout=120)
            asked.raise_for_status()
            marked = {d.get("id") for d in asked.json().get("data") or []}
            for record in json_array(resp.iter_lines()):
                if isinstance(record, dict) and record.get("id") in marked:
                    record["is_highlight"] = True
                yield record

    kept = frozenset(
        {
            "id",
            "share_license_status",
            "title",
            "creators",
            "creation_date",
            "creation_date_earliest",
            "technique",
            "type",
            "culture",
            "creditline",
            "url",
            "is_highlight",
            "description",
            "wall_description",
            "images",
        }
    )

    def trim(self, record: dict[str, Any]) -> dict[str, Any]:
        kept = {k: v for k, v in record.items() if k in self.kept}
        images = kept.get("images")
        if isinstance(images, dict):
            kept["images"] = {
                size: {k: (images.get(size) or {}).get(k) for k in ("url", "width", "height")}
                for size in ("web", "print", "full")
                if images.get(size)
            }
        creators = kept.get("creators")
        if isinstance(creators, list):
            kept["creators"] = [{"description": c.get("description")} for c in creators[:1]]
        return kept

    def kinds(self, record: dict[str, Any], item: Item) -> list[str]:
        return [str(record.get("type") or "")]


def json_array(lines: Iterable[str]) -> Iterator[Any]:
    """The objects of a JSON array printed one item per block, two spaces
    deep (``[``, ``  {``, ..., ``  },``, ..., ``]``), read as they come."""
    block: list[str] = []
    for line in lines:
        if not block:
            if line.rstrip() == "  {":
                block.append("{")
            continue
        if line.rstrip() in ("  }", "  },"):
            block.append("}")
            try:
                yield json.loads("\n".join(block))
            except ValueError as err:
                log.debug("a record left out: %s", err)
            block = []
        else:
            block.append(line)


class SmithsonianDump(Dump):
    """The Smithsonian's open access metadata on S3 (CC0, weekly): line JSON
    files a museum, 256 each; only its art museums are read."""

    key = "si"
    bucket = "https://smithsonian-open-access.s3-us-west-2.amazonaws.com"

    def museum(self, private_use: bool) -> Museum:
        from .museums import Access
        from .smithsonian import Smithsonian

        access = Access(private_use=private_use, smithsonian_key="dump")
        return Smithsonian(None, access=access)  # type: ignore[arg-type]

    def _files(self, http: httpx.Client) -> list[tuple[str, str]]:
        """Each art museum's files and their ETags, from the bucket's lists."""
        from .smithsonian import UNITS

        files: list[tuple[str, str]] = []
        names = "{http://s3.amazonaws.com/doc/2006-03-01/}"
        for unit in UNITS:
            token = ""
            while True:
                params = {"list-type": "2", "prefix": f"metadata/edan/{unit.lower()}/"}
                if token:
                    params["continuation-token"] = token
                resp = http.get(self.bucket + "/", params=params, timeout=60)
                resp.raise_for_status()
                root = ElementTree.fromstring(resp.content)
                for node in root.iter(f"{names}Contents"):
                    key = node.findtext(f"{names}Key") or ""
                    if key.endswith(".txt") and not key.endswith("index.txt"):
                        files.append((key, node.findtext(f"{names}ETag") or ""))
                token = root.findtext(f"{names}NextContinuationToken") or ""
                if not token:
                    break
        return files

    def records(self, http: httpx.Client, stamp: str, seen: dict[str, str]) -> Iterator[Any]:
        files = self._files(http)
        if not files:
            raise ValueError("no files in the bucket's lists")
        now = hashlib.sha256("\n".join(f"{k} {e}" for k, e in files).encode()).hexdigest()
        if stamp and stamp == now:
            raise Unchanged
        seen["stamp"] = now
        for key, _ in files:
            resp = http.get(f"{self.bucket}/{key}", timeout=120)
            resp.raise_for_status()
            for line in resp.text.splitlines():
                if line.strip():
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue

    @staticmethod
    def _picture(about: dict[str, Any]) -> dict[str, Any] | None:
        """The first CC0 picture, with what the mapping reads of it."""
        for media in (about.get("online_media") or {}).get("media") or []:
            if (
                media.get("type") == "Images"
                and (media.get("usage") or {}).get("access") == "CC0"
                and media.get("idsId")
            ):
                large = [
                    {k: r.get(k) for k in ("label", "width", "height")}
                    for r in media.get("resources") or []
                    if r.get("label") == "High-resolution JPEG"
                ]
                return {
                    "type": "Images",
                    "idsId": media["idsId"],
                    "usage": {"access": "CC0"},
                    "width": media.get("width"),
                    "height": media.get("height"),
                    "resources": large[:1],
                }
        return None

    def trim(self, record: dict[str, Any]) -> dict[str, Any]:
        content = record.get("content") or {}
        about = dict(content.get("descriptiveNonRepeating") or {})
        picture = self._picture(about)
        about["online_media"] = {"media": [picture] if picture else []}
        free = dict(content.get("freetext") or {})
        notes = [n for n in free.get("notes") or [] if str(n.get("label", "")).startswith("Desc")]
        free["notes"] = [
            {"label": n.get("label"), "content": str(n.get("content"))[:2000]} for n in notes[:2]
        ]
        indexed = content.get("indexedStructured") or {}
        return {
            "id": record.get("id"),
            "title": record.get("title"),
            "unitCode": record.get("unitCode"),
            "content": {
                "descriptiveNonRepeating": {
                    k: about.get(k)
                    for k in ("title", "online_media", "record_link", "guid", "unit_code")
                    if about.get(k) is not None
                },
                "freetext": {
                    k: free.get(k)
                    for k in ("name", "date", "physicalDescription", "creditLine", "notes")
                    if free.get(k) is not None
                },
                "indexedStructured": {
                    k: indexed.get(k)
                    for k in ("date", "object_type", "topic", "culture")
                    if indexed.get(k) is not None
                },
            },
        }

    def kinds(self, record: dict[str, Any], item: Item) -> list[str]:
        indexed = (record.get("content") or {}).get("indexedStructured") or {}
        return [str(t) for t in indexed.get("object_type") or []]


class WellcomeDump(Dump):
    """The Wellcome Collection's whole catalogue (daily, ~530 MB compressed,
    a work a line); only its pictures to be seen online are kept."""

    key = "wellcome"
    url = "https://data.wellcomecollection.org/catalogue/v2/works.json.gz"

    def museum(self, private_use: bool) -> Museum:
        from .museums import Access
        from .wellcome import WellcomeCollection

        return WellcomeCollection(None, access=Access(private_use=private_use))  # type: ignore[arg-type]

    def records(self, http: httpx.Client, stamp: str, seen: dict[str, str]) -> Iterator[Any]:
        for resp in _etag_get(http, self.url, stamp, seen, timeout=1800):
            packed = gzip.GzipFile(
                fileobj=io.BufferedReader(_Stream(resp.iter_bytes()), 1 << 20), mode="rb"
            )
            with io.TextIOWrapper(packed, encoding="utf-8") as lines:
                for line in lines:
                    # Pictures only ("k"), read whole only then: most of the
                    # catalogue is books and archives.
                    if '"id":"k"' not in line:
                        continue
                    try:
                        work = json.loads(line)
                    except ValueError:
                        continue
                    if (work.get("workType") or {}).get("id") != "k":
                        continue
                    online = {a.get("id") for a in work.get("availabilities") or []}
                    if "online" in online:
                        yield work

    def trim(self, record: dict[str, Any]) -> dict[str, Any]:
        kept = {
            k: record.get(k)
            for k in (
                "id",
                "title",
                "thumbnail",
                "genres",
                "physicalDescription",
                "subjects",
                "contributors",
                "production",
                "referenceNumber",
                "description",
            )
            if record.get(k) is not None
        }
        kept["genres"] = [
            {
                "label": g.get("label"),
                "concepts": [{"label": c.get("label")} for c in g.get("concepts") or []],
            }
            for g in kept.get("genres") or []
        ]
        kept["subjects"] = [{"label": s.get("label")} for s in kept.get("subjects") or []]
        kept["contributors"] = [
            {
                "agent": {k: (c.get("agent") or {}).get(k) for k in ("label", "type")},
                "primary": c.get("primary"),
            }
            for c in kept.get("contributors") or []
        ]
        kept["production"] = [
            {
                "dates": [{"label": d.get("label")} for d in p.get("dates") or []],
                "places": [{"label": d.get("label")} for d in p.get("places") or []],
            }
            for p in kept.get("production") or []
        ]
        return kept

    def kinds(self, record: dict[str, Any], item: Item) -> list[str]:
        # The API's genre filter matches a genre's label or its concepts'.
        found: list[str] = []
        for genre in record.get("genres") or []:
            found.append(str(genre.get("label") or ""))
            found += [str(c.get("label") or "") for c in genre.get("concepts") or []]
        return found


DUMPS: dict[str, Dump] = {
    d.key: d for d in (AicDump(), ClevelandDump(), SmithsonianDump(), WellcomeDump())
}


def local_index(key: str, folder: Path | None) -> DumpIndex | None:
    """The index of source ``key``'s dump, None when it has none (yet)."""
    dump = DUMPS.get(key)
    if dump is None or folder is None:
        return None
    return INDEXES.get(dump, folder)


def refresh_at_night(key: str, data_dir: Path) -> bool:
    return INDEXES.refresh(DUMPS[key], data_dir)
