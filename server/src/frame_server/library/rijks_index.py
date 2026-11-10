"""The Rijksmuseum's collection kept at home, read over OAI-PMH (Mateusz
2026-11-10, after AIC, Cleveland, the Smithsonian and Wellcome got theirs:
library/dumps.py).

The Rijksmuseum publishes no current dump of its objects (its data dumps
hold pictures and library records; the object dumps are from 2020), but
its OAI-PMH endpoint gives every record, fifty a request, with what its
Linked Art API gives for a work: titles, maker, date, type, materials,
the IIIF picture and its licence, and also the museum's "Top 1000". The
set read is "Alleen beeld" (every object with a picture, ~737 000):
~14 800 requests the first time, read a few hours a night, one request
after another, and taken up again the next night where it stopped (the
endpoint's resumption tokens hold their place). Until it is whole the
museum is asked as before; then its works are searched at home, as the
other dumps' are. Every two months the records changed since are read
again (OAI-PMH's ``from``): a few requests, unless the museum re-stamps
everything.

The records are kept as a small dict of their own (``"edm": 1``,
compressed) that :meth:`.museums.Rijksmuseum._map` reads into the same
works its API gives (~1 KB a work, ~0.7 GB in all). The index is the
dumps' (:data:`.dumps.SCHEMA`), so :class:`.dumps.DumpIndex` searches it:
titles, makers, Iconclass subjects, places, materials and types, not the
descriptions (mostly Dutch, a fifth of the file; the museum's own search
reads makers and titles only).
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
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

import httpx

from .dumps import NAMES, SCHEMA, DumpIndex, Entry, kind_order

if TYPE_CHECKING:
    from .museums import Rijksmuseum

log = logging.getLogger(__name__)

KEY = "rijks"
OAI = "https://data.rijksmuseum.nl/oai"
#: "Alleen beeld": every object with a picture.
SET = "260238"
#: "Top 1000": the museum's highlights (a set of the record's header).
TOP = "260214"
#: The records changed since are read again this long after a reading.
REFRESH_SECONDS = 60 * 24 * 3600
#: How long one night reads at most (the night's other work comes after).
NIGHT_SECONDS = 2.5 * 3600
#: Between two requests (no rates published; one at a time).
PAUSE = 1.0
#: A description is kept this long at most.
ABOUT_MAX = 1500

_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "rdf": _RDF,
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "edm": "http://www.europeana.eu/schemas/edm/",
    "ore": "http://www.openarchives.org/ore/terms/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "mrel": "http://id.loc.gov/vocabulary/relators/",
    "edmfp": "http://www.europeanafashion.eu/edmfp/",
}
_ABOUT = f"{{{_RDF}}}about"
_RESOURCE = f"{{{_RDF}}}resource"
_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

STATE = """
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


# -- the records ------------------------------------------------------------------


@dataclass
class Page:
    """One answer of ``ListRecords``."""

    records: list[dict[str, Any]] = field(default_factory=list)
    #: Ids the museum took back (deleted, or no longer in the set).
    gone: list[str] = field(default_factory=list)
    #: The next page's token; "" after the last.
    token: str = ""
    #: When the endpoint answered (the next reading's ``from``).
    answered: str = ""
    #: How many records the whole list holds.
    size: int | None = None


def _texts(node: ElementTree.Element, path: str) -> dict[str, list[str]]:
    """The texts at ``path`` by their language ("" without one)."""
    found: dict[str, list[str]] = {}
    for child in node.findall(path, _NS):
        text = (child.text or "").strip()
        if text:
            found.setdefault(child.get(_LANG) or "", []).append(text)
    return found


def _english(texts: dict[str, list[str]]) -> str:
    """The English text (else the untagged, the Dutch, any)."""
    for lang in ("en", "", "nl"):
        if texts.get(lang):
            return texts[lang][0]
    return next((t[0] for t in texts.values() if t), "")


def _refs(node: ElementTree.Element, path: str) -> list[str]:
    return [r for child in node.findall(path, _NS) if (r := child.get(_RESOURCE) or "")]


def _year(date: str) -> int | None:
    """The first year of a date as the museum writes it ("c. 1638",
    "1863 - 1900", "c. 800", "50 BC"); None for "18th century"."""
    if re.search(r"\b(BC|BCE|v\.\s?Chr)", date, re.IGNORECASE):
        found = re.search(r"(?<!\d)(\d{1,4})(?!\d)", date)
        return -int(found.group(1)) if found else None
    found = re.search(r"(?<!\d)(\d{3,4})(?!\d)", date)
    return int(found.group(1)) if found else None


def _plain(label: str) -> str:
    """A concept's label without its qualifier: "oil paint (paint)"."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()


#: Materials a work is made on: they come last ("oil paint on canvas").
SUPPORTS = frozenset(
    {"canvas", "panel", "paper", "copper", "cardboard", "parchment", "vellum", "wood", "linen"}
)
#: Techniques saying nothing the materials don't.
_PLAIN_TECHNIQUES = frozenset({"paint", "painting", "drawing", "draw"})


def medium(techniques: list[str], materials: list[str]) -> str:
    """The medium as a line: techniques and materials, those the work is
    made on last ("etching on paper", "oil paint on canvas")."""
    named = [t for t in map(_plain, techniques) if t and t not in _PLAIN_TECHNIQUES]
    named += [m for m in map(_plain, materials) if m and m not in SUPPORTS]
    under = [m for m in map(_plain, materials) if m in SUPPORTS]
    made = ", ".join(dict.fromkeys(named))
    on = ", ".join(dict.fromkeys(under))
    return f"{made} on {on}" if made and on else made or on


def record(rdf: ElementTree.Element) -> dict[str, Any] | None:
    """A record's ``rdf:RDF`` as the dict kept (``"edm": 1``); None
    without a picture."""
    labels: dict[str, dict[str, list[str]]] = {}
    for node in rdf:
        about = node.get(_ABOUT)
        if about:
            labels[about] = _texts(node, "skos:prefLabel")

    def label(ref: str) -> str:
        return _english(labels.get(ref) or {})

    aggregation = rdf.find("ore:Aggregation", _NS)
    cho = rdf.find("edm:ProvidedCHO", _NS)
    if aggregation is None or cho is None:
        return None
    shown = _refs(aggregation, "edm:isShownBy")
    if not shown or "iiif" not in shown[0]:
        return None
    work = cho.get(_ABOUT) or ""
    creators = [label(r) for r in _refs(cho, "dc:creator")]
    creators += [t for ts in _texts(cho, "dc:creator").values() for t in ts]
    date = _english(_texts(cho, "dcterms:created"))
    types = [t for r in _refs(cho, "dc:type") if (t := label(r))]
    about = _english(_texts(cho, "dc:description"))
    return {
        "edm": 1,
        "id": work.rsplit("/", 1)[-1],
        "number": _english(_texts(cho, "dc:identifier")),
        "title": _english(_texts(cho, "dc:title")),
        "artist": next((c for c in creators if c), ""),
        "date": date,
        "year": _year(date),
        "types": types,
        "medium": medium(
            [label(r) for r in _refs(cho, "edmfp:technique")],
            [label(r) for r in _refs(cho, "dcterms:medium")],
        ),
        "about": about[:ABOUT_MAX],
        "credit": _english(_texts(cho, "mrel:spn")),
        "places": [p for r in _refs(cho, "dcterms:spatial") if (p := label(r))],
        "subjects": [s for r in _refs(cho, "dc:subject") if (s := label(r))],
        "iiif": re.sub(r"/full/.*$", "", shown[0]),
        "rights": next(iter(_refs(aggregation, "edm:rights")), ""),
        "page": next(iter(_refs(aggregation, "edm:isShownAt")), ""),
        "top": False,
    }


class OaiError(ValueError):
    """An OAI-PMH error answer."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(f"OAI-PMH {code}: {text}")
        self.code = code


def parse(body: bytes) -> Page:
    """One ``ListRecords`` answer (raises on an OAI-PMH error other than
    "nothing changed")."""
    root = ElementTree.fromstring(body)
    page = Page(answered=(root.findtext("oai:responseDate", "", _NS) or "").strip())
    error = root.find("oai:error", _NS)
    if error is not None:
        if error.get("code") == "noRecordsMatch":
            return page
        raise OaiError(error.get("code") or "", (error.text or "").strip())
    listed = root.find("oai:ListRecords", _NS)
    if listed is None:
        raise ValueError("OAI-PMH: no ListRecords in the answer")
    for entry in listed.findall("oai:record", _NS):
        header = entry.find("oai:header", _NS)
        if header is None:
            continue
        work = (header.findtext("oai:identifier", "", _NS) or "").rsplit("/", 1)[-1]
        sets = {(s.text or "").strip() for s in header.findall("oai:setSpec", _NS)}
        rdf = entry.find("oai:metadata/rdf:RDF", _NS)
        kept = None
        if header.get("status") != "deleted" and SET in sets and rdf is not None:
            kept = record(rdf)
        if kept is None:
            if work:
                page.gone.append(work)
            continue
        kept["top"] = TOP in sets
        page.records.append(kept)
    token = listed.find("oai:resumptionToken", _NS)
    if token is not None:
        page.token = (token.text or "").strip()
        size = token.get("completeListSize")
        page.size = int(size) if size and size.isdigit() else None
    return page


def pages(http: httpx.Client, since: str = "", token: str = "") -> Iterator[Page]:
    """The set's pages from ``token`` (else from the start, changed
    ``since`` when given), one request each."""
    while True:
        if token:
            params = {"verb": "ListRecords", "resumptionToken": token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": "edm", "set": SET}
            if since:
                params["from"] = since
        resp = http.get(OAI, params=params, timeout=180)
        resp.raise_for_status()
        page = parse(resp.content)
        yield page
        if not page.token:
            return
        token = page.token


# -- the index ----------------------------------------------------------------------


def entry(museums: tuple[Rijksmuseum, Rijksmuseum], kept: dict[str, Any]) -> Entry | None:
    """A kept record as the index's entry; None when the museum's mapping
    shows nothing of it (``museums``: without and with private use)."""
    public, private = museums
    item = private._map(kept)
    if item is None:
        return None
    return Entry(
        id=item.source_id,
        record=kept,
        year=item.year,
        highlight=item.highlight,
        private=public._map(kept) is None,
        rank=kind_order(item.classification) - (0.5 if item.highlight else 0.0),
        kinds=[t.lower() for t in kept.get("types") or []],
        texts={
            "title": item.title,
            "artist": item.artist,
            "tags": " ".join(kept.get("subjects") or []),
            "place": " ".join(kept.get("places") or []),
            "medium": item.medium,
            "kind": " ".join(kept.get("types") or []),
            # Not the descriptions (mostly Dutch): the museum's own search
            # reads makers and titles only, and they are a fifth of the file.
            "about": "",
        },
    )


def _museums() -> tuple[Rijksmuseum, Rijksmuseum]:
    from .museums import Access, Rijksmuseum

    return (
        Rijksmuseum(None, access=Access(private_use=False)),  # type: ignore[arg-type]
        Rijksmuseum(None, access=Access(private_use=True)),  # type: ignore[arg-type]
    )


class Store:
    """The file a reading writes to: the works and where the reading is."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not path.is_file()
        self.db = sqlite3.connect(path, timeout=30)
        if fresh:
            self.db.executescript(SCHEMA)
        self.db.executescript(STATE)
        self.db.commit()

    def get(self, key: str) -> str:
        row = self.db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else ""

    def set(self, **values: str | None) -> None:
        for key, value in values.items():
            if value is None:
                self.db.execute("DELETE FROM state WHERE key = ?", (key,))
            else:
                self.db.execute("REPLACE INTO state VALUES (?, ?)", (key, value))

    def _drop(self, n: int) -> None:
        self.db.execute("DELETE FROM kinds WHERE n = ?", (n,))
        self.db.execute("DELETE FROM texts WHERE rowid = ?", (n,))

    def put(self, entry: Entry) -> None:
        row = self.db.execute("SELECT n FROM works WHERE id = ?", (entry.id,)).fetchone()
        values = (
            entry.year,
            int(entry.highlight),
            int(entry.private),
            entry.rank,
            zlib.compress(
                json.dumps(entry.record, separators=(",", ":"), ensure_ascii=False).encode()
            ),
        )
        if row:
            n = int(row[0])
            self._drop(n)
            self.db.execute(
                "UPDATE works SET year=?, highlight=?, private=?, rank=?, record=? WHERE n=?",
                (*values, n),
            )
        else:
            cursor = self.db.execute(
                "INSERT INTO works (id, year, highlight, private, rank, record)"
                " VALUES (?,?,?,?,?,?)",
                (entry.id, *values),
            )
            n = int(cursor.lastrowid or 0)
        self.db.executemany(
            "INSERT INTO kinds VALUES (?,?)", [(n, k) for k in dict.fromkeys(entry.kinds) if k]
        )
        self.db.execute(
            f"INSERT INTO texts (rowid, {', '.join(NAMES)}) VALUES (?{', ?' * len(NAMES)})",
            (n, *(entry.texts.get(name, "") or "" for name in NAMES)),
        )

    def remove(self, work: str) -> None:
        row = self.db.execute("SELECT n FROM works WHERE id = ?", (work,)).fetchone()
        if row:
            self._drop(int(row[0]))
            self.db.execute("DELETE FROM works WHERE n = ?", (int(row[0]),))

    def count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM works").fetchone()[0])

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.close()


def index_path(folder: Path) -> Path:
    """The index searched (there once the first reading is whole)."""
    return folder / "dumps" / f"{KEY}.sqlite"


def reading_path(folder: Path) -> Path:
    """The first reading, until it is whole."""
    return folder / "dumps" / f"{KEY}.reading.sqlite"


class RijksIndex:
    """The index, read a few hours at a time."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reading = False
        self.failed_at = 0.0
        self.failed_why = ""
        self._open: dict[Path, tuple[float, DumpIndex]] = {}

    def get(self, folder: Path) -> DumpIndex | None:
        """The index under ``folder``; None until the first reading is whole."""
        path = index_path(folder)
        if not path.is_file():
            return None
        stamp = path.stat().st_mtime
        with self.lock:
            kept = self._open.get(path)
            if kept is None or kept[0] != stamp:  # written to meanwhile
                try:
                    kept = (stamp, DumpIndex(path))
                except sqlite3.Error as err:
                    log.warning("rijks: index not opened: %s", err)
                    return None
                self._open[path] = kept
            return kept[1]

    def due(self, folder: Path, now: float | None = None) -> bool:
        """Whether there is reading to do: the first, unfinished, or the
        changes after REFRESH_SECONDS."""
        path = index_path(folder)
        if not path.is_file():
            return True
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
                rows = dict(db.execute("SELECT key, value FROM state").fetchall())
        except sqlite3.Error:
            return False
        if rows.get("token"):
            return True
        read = rows.get("read_at", "")
        return not read or (now or time.time()) - float(read) >= REFRESH_SECONDS

    def read(
        self,
        folder: Path,
        go: Callable[[], bool],
        pause: Callable[[float], bool],
        seconds: float = NIGHT_SECONDS,
        http: httpx.Client | None = None,
    ) -> int:
        """Reads pages for ``seconds`` at most, while ``go()`` (the night's
        quiet) lets it, ``pause`` between them; takes up the last reading
        where it stopped. Returns how many pages it read."""
        if not self.due(folder):
            return 0
        with self.lock:
            if self.reading or time.time() - self.failed_at < 3600:
                return 0
            self.reading = True
        try:
            return self._read(folder, go, pause, seconds, http)
        except Exception as err:
            if isinstance(err, OaiError) and err.code == "badResumptionToken":
                # Its place lost: the reading starts again (what it wrote stays).
                log.warning("rijks: %s; the reading starts again", err)
                store = Store(self._path(folder))
                store.set(token=None)
                store.commit()
                store.close()
                return 0
            log.exception("rijks: reading the collection failed")
            self.failed_at = time.time()
            self.failed_why = f"{type(err).__name__}: {err}"
            return 0
        finally:
            self.reading = False

    def _read(
        self,
        folder: Path,
        go: Callable[[], bool],
        pause: Callable[[float], bool],
        seconds: float,
        http: httpx.Client | None,
    ) -> int:
        from .museums import client

        live = index_path(folder)
        path = self._path(folder)
        store = Store(path)
        museums = _museums()
        until = time.monotonic() + seconds
        done = 0
        try:
            token = store.get("token")
            since = store.get("since") if token else store.get("next_since")
            if not token:
                store.set(since=since, started=None)
            started = time.monotonic()
            with http or client() as session:
                for page in pages(session, since, token):
                    for kept in page.records:
                        found = entry(museums, kept)
                        if found is None:
                            store.remove(str(kept.get("id") or ""))
                        else:
                            store.put(found)
                    for work in page.gone:
                        store.remove(work)
                    done += 1
                    if not store.get("started"):
                        store.set(started=page.answered)
                    if page.size is not None:
                        store.set(size=str(page.size))
                    store.set(token=page.token or None)
                    store.commit()
                    if not page.token:
                        self._finish(store, path, live)
                        break
                    if time.monotonic() >= until or not pause(PAUSE) or not go():
                        log.info(
                            "rijks: %d pages read in %.0f s (%d works), the rest another night",
                            done,
                            time.monotonic() - started,
                            store.count(),
                        )
                        break
        finally:
            store.close()
        return done

    @staticmethod
    def _path(folder: Path) -> Path:
        """The file a reading writes to: the index, else the first reading."""
        live = index_path(folder)
        return live if live.is_file() else reading_path(folder)

    def _finish(self, store: Store, path: Path, live: Path) -> None:
        """A reading whole: the next reads what changed since it began."""
        store.set(next_since=store.get("started"), read_at=str(time.time()), token=None)
        store.db.execute("INSERT INTO texts (texts) VALUES ('optimize')")
        store.commit()
        count = store.count()
        log.info("rijks: the collection read whole, %d works indexed", count)
        if path != live:
            store.close()
            os.replace(path, live)
        else:
            os.utime(live)

    def state(self, folder: Path) -> dict[str, Any]:
        """For ``/api/debug/dumps``: whether there is an index, how far the
        reading is, why the last failed."""
        live = index_path(folder)
        path = live if live.is_file() else reading_path(folder)
        state: dict[str, Any] = {"key": KEY, "index": live.is_file(), "building": self.reading}
        if self.failed_why:
            state["failed"] = self.failed_why
            state["failed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.failed_at))
        if path.is_file():
            state["bytes"] = path.stat().st_size
            try:
                with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
                    state["works"] = db.execute("SELECT count(*) FROM works").fetchone()[0]
                    rows = dict(db.execute("SELECT key, value FROM state").fetchall())
            except sqlite3.Error as err:
                state["unreadable"] = str(err)
                return state
            state["reading"] = bool(rows.get("token"))
            state["records"] = rows.get("size")
            if rows.get("read_at"):
                state["built"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(rows["read_at"]))
                )
        return state


INDEX = RijksIndex()


def local_index(folder: Path | None) -> DumpIndex | None:
    return INDEX.get(folder) if folder is not None else None


def read_at_night(data_dir: Path, go: Callable[[], bool], pause: Callable[[float], bool]) -> int:
    return INDEX.read(data_dir, go, pause)


def read_now(data_dir: Path, go: Callable[[], bool], pause: Callable[[float], bool]) -> bool:
    """A reading started now, in the background (the owner's test,
    ``/api/debug/dumps/rijks``); False while one runs."""
    if INDEX.reading:
        return False
    INDEX.failed_at = 0.0
    threading.Thread(
        target=INDEX.read, args=(data_dir, go, pause), name="rijks-index", daemon=True
    ).start()
    return True
