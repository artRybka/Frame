"""The Louvre's paintings, where Commons has none as good (Mateusz
2026-11-05: "Tak, jako uzupełnienie").

The Louvre's collections site has no search API (its search pages sit behind
a bot wall), but every entry comes as JSON (``<entry>.json``: French title,
creator, dates, size, technique, room, photographs with their credits).
Its photographs are 1500 px on the longer side, less than most Commons
copies of the famous works, so the list is Wikidata's paintings with a
Louvre ARK id (P9394, ~10 400) and only those whose Commons picture (P18)
is missing or smaller than :data:`COMMONS_BETTER` are taken (~7 500 in
2026-11; Valenciennes's oil sketches, Oudry, Prud'hon, Hubert Robert…).
Commons keeps the rest, in full size.

Terms of use (art. 4.1.1.2 a): photographs of works out of copyright are
free "for any non-collective use within a strictly private context", with
the photo credit and a link to the entry, so the source is offered only
with "Użytek prywatny". Photographs credited to another institution (a
work on loan, "© GrandPalaisRmn (musée d'Orsay)") need that institution's
consent and are left out. Works still in copyright come with
:data:`PRIVATE_LICENCE`, as from the Rijksmuseum and SMK.

The server writes the list to a JSON file under the data folder: Wikidata
once (one query), the Commons sizes 50 files a request, then each entry
needed, paced by ``hosts.PACE`` (about an hour the first time, written as it
goes). Once a
month (night task) Wikidata and Commons are asked again and only new entries
fetched.
"""

from __future__ import annotations

import csv
import functools
import io
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx

from .hosts import Resting, retry_after
from .lifespan import free_in_eu
from .models import Item
from .museums import PRIVATE_LICENCE, Access, Discovery, Museum, client

log = logging.getLogger(__name__)

SITE = "https://collections.louvre.fr"
HOST = "collections.louvre.fr"
#: The Louvre's ARK names: Wikidata keeps the number without "cl".
ARK = f"{SITE}/ark:/53355/cl"
SPARQL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
#: Paintings with a Louvre entry, their Commons picture, author and his death.
QUERY = """SELECT ?ark ?work ?workLabel ?file ?creatorLabel ?died WHERE {
  ?work wdt:P9394 ?ark; wdt:P31 wd:Q3305213.
  OPTIONAL { ?work wdt:P18 ?file }
  OPTIONAL { ?work wdt:P170 ?creator. OPTIONAL { ?creator wdt:P570 ?died } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr". }
}"""
#: A Commons picture this big (longer side) is at least the Louvre's own.
COMMONS_BETTER = 1500
#: Commons files asked about in one request (the API's limit).
COMMONS_BATCH = 50
#: A Commons request turned away (429) is asked again this many times, after
#: the wait it names, at most LONGEST_WAIT.
TRIES = 5
LONGEST_WAIT = 300.0
#: Written to the list this often while fetching entries.
SAVE_EVERY = 200
REFRESH_SECONDS = 30 * 24 * 3600
RETRY_SECONDS = 6 * 3600
LICENCE = "Domena publiczna, zdjęcie Luwru (użytek prywatny)"
NAME = "Luwr"
#: Wikidata's names for an unknown author.
_ANONYMOUS = {"anonymous", "anonyme", "unknown"}
_QID = re.compile(r"^Q\d+$")
_UNITS = {"m": 100.0, "cm": 1.0, "mm": 0.1}


def _value(row: dict[str, str], key: str) -> str:
    return str(row.get(key) or "").strip()


def paintings(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Wikidata's answer (CSV rows) by ARK number: the work, its English
    title, author, the author's death year and the Commons file, if any."""
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        ark = _value(row, "ark").removeprefix("cl")
        if not ark.isdigit():
            continue
        entry = found.setdefault(
            ark, {"qid": _value(row, "work").rsplit("/", 1)[-1], "title": "", "artist": ""}
        )
        title = _value(row, "workLabel")
        if title and not _QID.match(title):
            entry["title"] = entry["title"] or title
        artist = _value(row, "creatorLabel")
        if artist and not _QID.match(artist) and artist.casefold() not in _ANONYMOUS:
            entry["artist"] = entry["artist"] or artist
        if died := re.match(r"^-?(\d{3,4})-", _value(row, "died")):
            entry["died"] = max(entry.get("died") or 0, int(died.group(1)))
        if file := _value(row, "file"):
            entry.setdefault("file", unquote(file.rsplit("/", 1)[-1]))
    return found


def _patiently(ask: Callable[[], httpx.Response], sleep: Callable[[float], None]) -> httpx.Response:
    """``ask``'s answer, asked again after the wait a 429 names (the guard
    lets nothing through before), a few times."""
    for attempt in range(TRIES):
        try:
            resp = ask()
        except Resting:
            if attempt == TRIES - 1:
                raise
            sleep(LONGEST_WAIT)
            continue
        if resp.status_code != 429 or attempt == TRIES - 1:
            resp.raise_for_status()
            return resp
        sleep(min((retry_after(resp) or 60.0) + 1, LONGEST_WAIT))
    raise AssertionError("unreachable")


def commons_sizes(
    http: httpx.Client, files: list[str], sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """The longer side of each Commons file (missing ones left out)."""
    sizes: dict[str, int] = {}
    for start in range(0, len(files), COMMONS_BATCH):
        batch = files[start : start + COMMONS_BATCH]
        data = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "size",
            "titles": "|".join(f"File:{f}" for f in batch),
        }
        resp = _patiently(functools.partial(http.post, COMMONS_API, data=data), sleep)
        query = resp.json().get("query") or {}
        # Titles come back normalised ("_" as " "): map them to ours.
        names = {n["to"]: n["from"] for n in query.get("normalized") or []}
        for page in (query.get("pages") or {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            if "width" not in info:
                continue
            title = names.get(page.get("title", ""), page.get("title", ""))
            sizes[title.removeprefix("File:")] = max(int(info["width"]), int(info["height"]))
    return sizes


def _photo(images: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The photograph to show: the Louvre's own (another institution's needs
    its consent), the whole work before a detail."""
    own = [
        i
        for i in sorted(images, key=lambda i: int(i.get("position") or 0))
        if "louvre" in str(i.get("copyright") or "").casefold() and i.get("urlImage")
    ]
    whole = [i for i in own if "détail" not in str(i.get("type") or "")]
    chosen = whole or own
    return chosen[0] if chosen else None


def size_cm(dimension: list[dict[str, Any]]) -> tuple[float, float] | None:
    """(height, width) in centimetres from the entry's ``dimension``:
    "Hauteur" 0,794 m and "Largeur" 0,534 m -> (79.4, 53.4)."""
    sides: dict[str, float] = {}
    for d in dimension or []:
        kind = str(d.get("type") or "").strip().casefold()
        if kind not in ("hauteur", "largeur") or kind in sides:
            continue
        try:
            value = float(str(d.get("value") or "").replace(",", ".").replace(" ", ""))
        except ValueError:
            continue
        scale = _UNITS.get(str(d.get("unit") or "").strip().casefold())
        if scale and value > 0:
            sides[kind] = round(value * scale, 1)
    return (sides["hauteur"], sides["largeur"]) if len(sides) == 2 else None


def record(entry: dict[str, Any]) -> dict[str, Any] | None:
    """What the frame keeps of one entry's JSON; None without a photograph
    of the Louvre's own."""
    photo = _photo(entry.get("image") or [])
    if photo is None:
        return None
    dates = entry.get("dateCreated") or [{}]
    first = dates[0] if dates else {}
    start, end = first.get("startYear"), first.get("endYear")
    years = f"{start}–{end}" if start and end and start != end else str(start or "")
    numbers = entry.get("objectNumber") or []
    number = next((str(n.get("value")) for n in numbers if n.get("value")), "")
    creators = [c for c in entry.get("creator") or [] if c.get("label")]
    size = size_cm(entry.get("dimension") or [])
    return {
        "title_fr": str(entry.get("title") or "").strip(),
        "artist_fr": str(creators[0]["label"]).strip() if creators else "",
        "date": str(first.get("text") or "").strip() or years,
        "year": int(start) if isinstance(start, int) else None,
        "medium": str(entry.get("materialsAndTechniques") or "").strip(),
        "number": number,
        "room": str(entry.get("room") or "").strip(),
        "image": str(photo["urlImage"]),
        "thumb": str(photo.get("urlThumbnail") or photo["urlImage"]),
        "credit": str(photo.get("copyright") or "").strip(),
        "size": list(size) if size else None,
    }


def look(http: httpx.Client, ark: str) -> dict[str, Any] | None:
    """One entry's record, None when the Louvre has no usable one."""
    resp = http.get(f"{ARK}{ark}.json")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    try:
        entry = resp.json()
    except ValueError as err:  # the bot wall's page instead of the entry
        raise httpx.HTTPError(f"no JSON for {ark}") from err
    return record(entry) if isinstance(entry, dict) else None


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, path)


def wanted(entry: dict[str, Any]) -> bool:
    """Whether the Louvre's copy is taken: Commons has none as big."""
    return int(entry.get("commons") or 0) < COMMONS_BETTER


def build(path: Path, http: httpx.Client) -> int:
    """Write the paintings to ``path``: Wikidata's list and the Commons
    sizes asked again, entries already looked up kept, new ones wanted
    looked up (paced by ``hosts.PACE``), gone ones dropped. Returns how
    many the frame takes."""
    old = _read(path).get("works") or {}
    # CSV: a third of the JSON's 8 MB.
    resp = http.get(SPARQL, params={"query": QUERY}, headers={"Accept": "text/csv"}, timeout=180)
    resp.raise_for_status()
    found = paintings(csv.DictReader(io.StringIO(resp.text)))
    if not found:
        raise RuntimeError("Wikidata lists no Louvre paintings")
    sizes = commons_sizes(http, sorted({e["file"] for e in found.values() if e.get("file")}))
    works: dict[str, dict[str, Any]] = {}
    for ark, entry in found.items():
        entry["commons"] = sizes.get(entry.pop("file", ""), 0)
        if "work" in (old.get(ark) or {}):
            entry["work"] = old[ark]["work"]
        works[ark] = entry
    data = {"complete": False, "works": works}
    _write(path, data)
    looked = 0
    for ark, entry in works.items():
        if "work" in entry or not wanted(entry):
            continue
        try:
            entry["work"] = look(http, ark)
        except httpx.HTTPError as err:
            log.warning("louvre: %s left for next time: %s", ark, err)
            continue
        looked += 1
        if looked % SAVE_EVERY == 0:
            _write(path, data)
    data["complete"] = True
    _write(path, data)
    return sum(1 for e in works.values() if e.get("work") and wanted(e))


class _Index:
    """The list, written in the background when missing, unfinished or a
    month old, and kept in memory."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.building = False
        self.failed_at = 0.0
        self._loaded: tuple[Path, float, dict[str, dict[str, Any]]] | None = None

    def works(self, path: Path) -> dict[str, dict[str, Any]]:
        """The paintings taken (by ARK number); starts writing the list when
        it is missing, unfinished or old."""
        if not path.is_file():
            self._start(path)
            return {}
        stamp = path.stat().st_mtime
        loaded = self._loaded
        if loaded is None or loaded[0] != path or loaded[1] != stamp:
            data = _read(path)
            if not data.get("complete") or time.time() - stamp >= REFRESH_SECONDS:
                self._start(path)
            taken = {
                ark: {
                    **e["work"],
                    "title": e.get("title"),
                    "artist": e.get("artist"),
                    "died": e.get("died"),
                }
                for ark, e in (data.get("works") or {}).items()
                if e.get("work") and wanted(e)
            }
            loaded = (path, stamp, taken)
            self._loaded = loaded
        elif time.time() - stamp >= REFRESH_SECONDS:
            self._start(path)
        return loaded[2]

    def _start(self, path: Path) -> None:
        if self._claim():
            threading.Thread(
                target=self._build, args=(path,), name="louvre-index", daemon=True
            ).start()

    def _claim(self) -> bool:
        with self.lock:
            if self.building or time.time() - self.failed_at < RETRY_SECONDS:
                return False
            self.building = True
            return True

    def _build(self, path: Path) -> None:
        try:
            started = time.monotonic()
            with client() as http:
                count = build(path, http)
            log.info("louvre: %d paintings listed in %.0f s", count, time.monotonic() - started)
        except Exception:
            log.exception("louvre: listing the paintings failed")
            self.failed_at = time.time()
        finally:
            self.building = False

    def refresh(self, path: Path) -> bool:
        """The night's task: the list looked at again once a month, or
        finished when a restart cut it short (never before the first search
        asked for it). Whether it was."""
        if not path.is_file():
            return False
        old = time.time() - path.stat().st_mtime >= REFRESH_SECONDS
        if not old and _read(path).get("complete"):
            return False
        if not self._claim():
            return False
        self._build(path)
        return True


INDEX = _Index()


def list_path(data_dir: Path) -> Path:
    return data_dir / "louvre" / "paintings.json"


def refresh_at_night(data_dir: Path) -> bool:
    return INDEX.refresh(list_path(data_dir))


class Louvre(Museum):
    key: str = "louvre"
    name: str = NAME
    page_size = 100

    @classmethod
    def offered(cls, access: Access) -> bool:
        return access.private_use and access.data_dir is not None

    def _works(self) -> dict[str, dict[str, Any]]:
        folder = self.access.data_dir
        if folder is None or not self.private_use:
            return {}
        return INDEX.works(list_path(folder))

    @staticmethod
    def _free(w: dict[str, Any]) -> bool:
        died = w.get("died")
        if died:
            return free_in_eu(int(died))
        year = w.get("year")
        return year is not None and year < 1850

    def _map(self, ark: str, w: dict[str, Any]) -> Item:
        return self._item(
            ark,
            title=w.get("title") or w.get("title_fr") or "",
            artist=w.get("artist") or "",
            date_text=w.get("date") or "",
            year=w.get("year"),
            medium=w.get("medium") or "",
            classification="Painting",
            credit=", ".join(
                p for p in (w.get("credit") or "Musée du Louvre", w.get("number")) if p
            ),
            license=LICENCE if self._free(w) else PRIVATE_LICENCE,
            url=f"{ARK}{ark}",
            image_url=w["image"],
            thumb_url=w.get("thumb") or w["image"],
        )

    def _pick(self, keep: Any, limit: int, page: int) -> tuple[int, list[Item]]:
        found = [(ark, w) for ark, w in self._works().items() if keep(w)]
        found.sort(key=lambda aw: (aw[1].get("year") or 9999, aw[0]))
        start = (page - 1) * limit
        return len(found), [self._map(a, w) for a, w in found[start : start + limit]]

    @staticmethod
    def _matches(words: list[str], w: dict[str, Any]) -> bool:
        text = " ".join(
            str(w.get(k) or "")
            for k in ("title", "title_fr", "artist", "artist_fr", "date", "medium", "number")
        ).casefold()
        return all(word in text for word in words)

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        words = query.casefold().split()
        return self._pick(lambda w: self._matches(words, w), limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.highlight or spec.kind not in ("any", "painting"):
            return 0, []
        words = spec.style.casefold().split()

        def keep(w: dict[str, Any]) -> bool:
            year = w.get("year")
            if spec.year_from is not None and (year is None or year < spec.year_from):
                return False
            if spec.year_to is not None and (year is None or year > spec.year_to):
                return False
            return self._matches(words, w)

        return self._pick(keep, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        w = self._works().get(source_id)
        return self._map(source_id, w) if w else None
