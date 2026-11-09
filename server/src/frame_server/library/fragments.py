"""Fragments of a work: its museum's own photographs of its parts, sharp
where the whole, fit into the frame's pixels, is not (Mateusz 2026-11-09:
"Historia Fukutomiego", a handscroll 30 times as long as it is tall, came
out mush).

- The Cleveland Museum of Art photographs a handscroll in sections besides
  the whole ("alternate_images" of its record, each 3400 px long): asked
  for works more elongated than :data:`CMA_RATIO`.
- Wikimedia Commons keeps a few very large files also as sets of tiles
  (``{{Tile set available}}``: "The Garden of Earthly Delights" in 18
  files of 29 952 px): the files that have one are listed once a month
  (:data:`TILED_FOR`), and only theirs are asked about.

A fragment is a work of its own for the app, ``<work id>~p<n>``
(:func:`part_id`): its card, the frame, the queue and playlists take it as
any other; :meth:`Importer.remote <frame_server.library.importer.Importer.remote>`
makes it from its work. What a source said is kept on disk for
:data:`KEPT_FOR` (also that a work has none).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from .models import Item

log = logging.getLogger(__name__)

#: Between a work's id and its fragment's number.
PART = "~p"
_PART_ID = re.compile(rf"^(.+?){re.escape(PART)}(\d+)$")
#: Cleveland works this many times longer than wide (or tall) are asked for
#: their sections: other works' photographs are of the back, the frame, a
#: detail, not parts of the picture in order.
CMA_RATIO = 3.0
CMA_API = "https://openaccess-api.clevelandart.org/api/artworks"
#: A Cleveland photograph this close to the whole work's shape is of the
#: whole (its first "alternate image" often is), not of a part.
WHOLE_SHAPE = 0.8
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
TILED_TEMPLATE = "Template:Tile set available"
#: A tile's name: "<name>-x<column>-y<row>.<ext>".
_TILE = re.compile(
    r"\[\[\s*(?:File|Image)\s*:\s*([^|\]]+?-x(\d+)-y(\d+)\.(?:jpe?g|png|tiff?))", re.I
)
_GRID = re.compile(r"\{\{\s*(Tile set/[^{}|]+?)\s*\}\}")
#: Commons answers imageinfo for this many files at once.
COMMONS_BATCH = 50
#: How long what a source said about a work's fragments is kept.
KEPT_FOR = 30 * 86400.0
#: How long the list of Commons files with tiles is kept.
TILED_FOR = 30 * 86400.0
#: Fragments kept of one work, at most.
MOST = 60


class Part(BaseModel):
    """One fragment's picture as its source gives it, and where on the
    whole work it lies when that is known (a Commons tile set's grid): its
    left, top, width and height as fractions of the whole's."""

    url: str
    thumb: str
    width: int
    height: int
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None

    @property
    def placed(self) -> bool:
        return self.w is not None and self.h is not None


def part_id(work_id: str, n: int) -> str:
    """The id of the ``n``-th fragment (from 1) of the work ``work_id``."""
    return f"{work_id}{PART}{n}"


def split_part(item_id: str) -> tuple[str, int] | None:
    """(the work's id, the fragment's number) of a fragment's id; None for
    any other id."""
    m = _PART_ID.match(item_id)
    if not m or int(m.group(2)) < 1:
        return None
    return m.group(1), int(m.group(2))


def ratio(width: int | None, height: int | None) -> float:
    if not width or not height:
        return 1.0
    return max(width, height) / min(width, height)


class Fragments:
    def __init__(self, path: Path, http: Callable[[], httpx.Client]) -> None:
        self.path = path
        self.http = http
        self.clock: Callable[[], float] = time.time
        self._lock = threading.Lock()
        #: By work id: when asked, and the parts found.
        self._kept: dict[str, tuple[float, list[Part]]] = self._load()
        #: Commons page ids with a tile set, and when listed.
        self._tiled: tuple[float, frozenset[str]] | None = None
        self._asking: dict[str, threading.Lock] = {}

    # -- kept on disk ------------------------------------------------------------

    def _load(self) -> dict[str, tuple[float, list[Part]]]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        kept: dict[str, tuple[float, list[Part]]] = {}
        if not isinstance(data, dict):
            return kept
        for key, value in data.items():
            try:
                parts = [Part(**p) for p in value["parts"]]
                at = float(value["at"])
            except (KeyError, TypeError, ValueError):
                continue
            if key.startswith("wmc:") and parts and not parts[0].placed:
                continue  # kept before tiles had their places: asked again
            kept[key] = (at, parts)
        return kept

    def _save(self) -> None:
        data = {
            k: {"at": at, "parts": [p.model_dump() for p in parts]}
            for k, (at, parts) in self._kept.items()
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(self.path)
        except OSError as err:
            log.warning("fragments not kept: %s", err)

    # -- which works -------------------------------------------------------------

    def may_have(self, item: Item) -> bool:
        """Whether ``item``'s source may have fragments of it (no request)."""
        if item.part_of:
            return False
        if item.source == "cma":
            return ratio(item.width, item.height) >= CMA_RATIO
        return item.source == "wmc"  # only files with tiles are asked about

    def parts(self, item: Item) -> list[Part]:
        """The fragments' pictures of ``item``, in order; [] when it has
        none, or its source cannot be asked now (asked again next time)."""
        if not self.may_have(item):
            return []
        with self._lock:
            kept = self._kept.get(item.id)
            asking = self._asking.setdefault(item.id, threading.Lock())
        if kept is not None and self.clock() - kept[0] < KEPT_FOR:
            return kept[1]
        with asking:  # one look per work at once
            with self._lock:
                kept = self._kept.get(item.id)
            if kept is not None and self.clock() - kept[0] < KEPT_FOR:
                return kept[1]
            try:
                found = self._ask(item)
            except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as err:
                log.info("fragments of %s not asked: %s", item.id, err)
                return kept[1] if kept is not None else []
            if found is None:  # a Commons file without tiles: nothing kept
                return []
            with self._lock:
                self._kept[item.id] = (self.clock(), found[:MOST])
                self._save()
            return found[:MOST]

    def tiled(self, item_id: str) -> bool:
        """Whether ``item_id`` is a Commons file with a tile set (the list
        asked once a month; False when Commons cannot be asked now)."""
        source, _, source_id = item_id.partition(":")
        if source != "wmc" or split_part(item_id) is not None:
            return False
        with self._lock:
            tiled = self._tiled
        if tiled is not None and self.clock() - tiled[0] < TILED_FOR:
            return source_id in tiled[1]
        try:
            with self.http() as http:
                return source_id in self._tiled_pages(http)
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as err:
            log.info("Commons tile sets not listed: %s", err)
            return False

    def items(self, item: Item) -> list[Item]:
        """``item``'s fragments as works of their own."""
        parts = self.parts(item)
        return [fragment(item, n, len(parts), p) for n, p in enumerate(parts, 1)]

    def part(self, work: Item, n: int) -> Item | None:
        """The ``n``-th fragment of ``work``; None when it has no such."""
        parts = self.parts(work)
        if not 1 <= n <= len(parts):
            return None
        return fragment(work, n, len(parts), parts[n - 1])

    # -- the sources -------------------------------------------------------------

    def _ask(self, item: Item) -> list[Part] | None:
        with self.http() as http:
            if item.source == "cma":
                return self._cleveland(http, item)
            return self._commons(http, item)

    def _cleveland(self, http: httpx.Client, item: Item) -> list[Part]:
        resp = http.get(f"{CMA_API}/{item.source_id}")
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        whole = ratio(item.width, item.height)
        parts: list[Part] = []
        for alt in data.get("alternate_images") or []:
            picture = alt.get("print") or alt.get("web") or {}
            web = alt.get("web") or picture
            try:
                width, height = int(picture["width"]), int(picture["height"])
            except (KeyError, TypeError, ValueError):
                continue
            if not picture.get("url") or not width or not height:
                continue
            if ratio(width, height) >= whole * WHOLE_SHAPE:
                continue  # the whole work again
            parts.append(
                Part(
                    url=picture["url"],
                    thumb=web.get("url") or picture["url"],
                    width=width,
                    height=height,
                )
            )
        return parts

    def _tiled_pages(self, http: httpx.Client) -> frozenset[str]:
        """Page ids of the Commons files that have a tile set."""
        with self._lock:
            tiled = self._tiled
        if tiled is not None and self.clock() - tiled[0] < TILED_FOR:
            return tiled[1]
        ids: set[str] = set()
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "list": "embeddedin",
            "eititle": TILED_TEMPLATE,
            "einamespace": 6,
            "eilimit": 500,
        }
        for _ in range(10):
            resp = http.get(COMMONS_API, params=params)
            resp.raise_for_status()
            body = resp.json()
            ids.update(str(p["pageid"]) for p in body.get("query", {}).get("embeddedin", []))
            more = body.get("continue")
            if not more:
                break
            params.update(more)
        found = frozenset(ids)
        with self._lock:
            self._tiled = (self.clock(), found)
        return found

    def _commons(self, http: httpx.Client, item: Item) -> list[Part] | None:
        if item.source_id not in self._tiled_pages(http):
            return None
        text = _wikitext(http, pageids=item.source_id)
        tiles = _TILE.findall(text)
        if not tiles and (grid := _GRID.search(text)):
            tiles = _TILE.findall(_wikitext(http, titles=f"Template:{grid.group(1)}"))
        order: dict[str, tuple[int, int]] = {}
        for name, column, row in tiles:
            order.setdefault(f"File:{name.strip()}", (int(row), int(column)))
        names = sorted(order, key=order.__getitem__)
        infos: dict[str, dict[str, Any]] = {}
        for start in range(0, len(names), COMMONS_BATCH):
            resp = http.get(
                COMMONS_API,
                params={
                    "action": "query",
                    "format": "json",
                    "prop": "imageinfo",
                    "iiprop": "url|size",
                    "iiurlwidth": 500,
                    "titles": "|".join(names[start : start + COMMONS_BATCH]),
                },
            )
            resp.raise_for_status()
            query = resp.json().get("query", {})
            renamed = {n["to"]: n["from"] for n in query.get("normalized", [])}
            for page in query.get("pages", {}).values():
                info = (page.get("imageinfo") or [None])[0]
                if info:
                    infos[renamed.get(page.get("title", ""), page.get("title", ""))] = info
        parts: list[Part] = []
        cells: list[tuple[int, int]] = []
        for name in names:
            info = infos.get(name)
            if not info or not info.get("url") or not info.get("width") or not info.get("height"):
                continue
            parts.append(
                Part(
                    url=info["url"],
                    thumb=info.get("thumburl") or info["url"],
                    width=int(info["width"]),
                    height=int(info["height"]),
                )
            )
            cells.append(order[name])
        return place(parts, cells)


def place(parts: list[Part], cells: list[tuple[int, int]]) -> list[Part]:
    """``parts`` (tiles at (row, column) ``cells``) with their places on
    the whole: a column is as wide as its tiles, a row as tall, and the
    grid is the whole picture. Left unplaced when a row or a column has no
    tile at all, or the tiles of one disagree (not a grid then)."""
    widths: dict[int, int] = {}
    heights: dict[int, int] = {}
    for part, (row, column) in zip(parts, cells, strict=True):
        if widths.setdefault(column, part.width) != part.width:
            return parts
        if heights.setdefault(row, part.height) != part.height:
            return parts
    if not parts or sorted(widths) != list(range(len(widths))):
        return parts
    if sorted(heights) != list(range(len(heights))):
        return parts
    total_w, total_h = sum(widths.values()), sum(heights.values())
    left = [sum(widths[c] for c in range(column)) for column in range(len(widths))]
    top = [sum(heights[r] for r in range(row)) for row in range(len(heights))]
    return [
        part.model_copy(
            update={
                "x": left[column] / total_w,
                "y": top[row] / total_h,
                "w": part.width / total_w,
                "h": part.height / total_h,
            }
        )
        for part, (row, column) in zip(parts, cells, strict=True)
    ]


def _wikitext(http: httpx.Client, **page: str) -> str:
    resp = http.get(
        COMMONS_API,
        params={
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            **page,
        },
    )
    resp.raise_for_status()
    for found in resp.json().get("query", {}).get("pages", {}).values():
        for rev in found.get("revisions") or []:
            return str(rev.get("slots", {}).get("main", {}).get("*", ""))
    return ""


def fragment(work: Item, n: int, parts: int, part: Part) -> Item:
    """The ``n``-th of ``parts`` fragments of ``work``, as a work of its own:
    the work's texts, the fragment's picture."""
    return Item(
        id=part_id(work.id, n),
        kind=work.kind,
        source=work.source,
        source_id=f"{work.source_id}{PART}{n}",
        title=f"{work.title} (fragment {n}/{parts})" if work.title else f"Fragment {n}/{parts}",
        artist=work.artist,
        artist_bio=work.artist_bio,
        date_text=work.date_text,
        year=work.year,
        medium=work.medium,
        classification=work.classification,
        styles=list(work.styles),
        subjects=list(work.subjects),
        culture=work.culture,
        museum=work.museum,
        credit=work.credit,
        license=work.license,
        url=work.url,
        description=work.description,
        image_url=part.url,
        thumb_url=part.thumb,
        width=part.width,
        height=part.height,
        holder=work.holder,
        place=work.place,
        part_of=work.id,
        part=n,
        parts=parts,
    )
