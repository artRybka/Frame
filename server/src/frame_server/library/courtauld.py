"""The Courtauld Gallery, London: its paintings, from its own list.

The gallery has no search API (its site searches through a form with a
session), but lists every object in its sitemap, links each object's page to
a IIIF manifest with the record (title, maker, date, medium, size, copyright
statement) and serves the pictures over IIIF in full size (Manet's "A Bar at
the Folies-Bergère" 7506 px). Its pictures are CC BY-NC, so the source is
offered only with "Użytek prywatny"; works still in copyright come with
:data:`PRIVATE_LICENCE`, as from the Rijksmuseum and SMK.

Only the paintings (~580, ``object-p-…``; Mateusz 2026-11-04: "Tylko
obrazy"). The server writes them to a small JSON file under the data folder
once, slowly (two requests a work, paced: under an hour), and looks for
new ones once a month ("sprawdzenie katalogu raz na miesiąc wystarczy").

Some of its scans are CMYK files, which its IIIF server reads as RGBA with
nothing opaque: their JPEGs come out plain white (Borghese di Piero's
predella, P.1966.GP.264; 2026-11-05). The tiles take the picture the
object's page prints (``v0_high.jpg``, 768 px, drawn right), and the
original comes as PNG, whose four channels are the CMYK ones
(:func:`repair`).
"""

from __future__ import annotations

import html
import io
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from .images import BYTES
from .models import Item
from .museums import PRIVATE_LICENCE, Access, Discovery, Museum, client, strip_html

log = logging.getLogger(__name__)

SITE = "https://gallerycollections.courtauld.ac.uk"
#: Paintings' pages: "object-p-1934-sc-234" for P.1934.SC.234.
_PAINTING = re.compile(rf"<loc>\s*{re.escape(SITE)}/(object-p-[a-z0-9-]+)\s*</loc>")
_MANIFEST = re.compile(r"api/iiif/(O\d+)/manifest\.json")
#: The picture the object's page prints, drawn by the site itself.
_PRINTED = re.compile(r'<img\b[^>]*\bid="print-image"[^>]*>')
_SRC = re.compile(r'\bsrc="([^"]+)"')
HOST = "gallerycollections.courtauld.ac.uk"
#: A picture from its IIIF server: …/iiif/3/<media>/<region>/<size>/0/default.jpg.
_IIIF_JPEG = re.compile(rf"^{re.escape(SITE)}/iiif/3/[^/]+/.+/default\.jpg$")
#: The longest side of an original asked for (the frame's 2560 px).
ORIGINAL = 2560
#: A picture whose every pixel is at least this light is no picture.
BLANK = 250
#: Looked at again after this long (the night's task, or a search).
REFRESH_SECONDS = 30 * 24 * 3600
RETRY_SECONDS = 6 * 3600
#: Pictures smaller than this (longer side) are no use on the frame.
SMALLEST = 1000
LICENCE = "CC BY-NC 4.0"
PUBLIC_DOMAIN = "work in the public domain"


def _text(value: Any) -> str:
    if isinstance(value, dict):
        values: list[Any] = value.get("none") or value.get("en") or next(iter(value.values()), [])
        return " ".join(str(v) for v in values).strip()
    return str(value or "").strip()


def record(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """What the frame keeps of one work's manifest; None without a picture
    big enough."""
    meta = {_text(m.get("label")): _text(m.get("value")) for m in manifest.get("metadata") or []}
    try:
        canvas = manifest["items"][0]
        body = canvas["items"][0]["items"][0]["body"]
        width, height = int(body.get("width") or 0), int(body.get("height") or 0)
        iiif = str(body["id"]).split("/full/")[0]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if max(width, height) < SMALLEST:
        return None
    year = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", meta.get("Production date", ""))
    return {
        "title": meta.get("Title") or _text(manifest.get("label")),
        "artist": meta.get("Maker", ""),
        "date": meta.get("Production date", "").replace("(circa)", "c.").strip(),
        "year": int(year.group(1)) if year else None,
        "medium": meta.get("Medium", "").strip(),
        "number": meta.get("Accession number", ""),
        "dimensions": meta.get("Dimensions", ""),
        "credit": meta.get("Credit", ""),
        "free": meta.get("Copyright statement", "").strip().lower() == PUBLIC_DOMAIN,
        "about": strip_html(meta.get("Label text", "")),
        "iiif": iiif,
        "width": width,
        "height": height,
    }


def printed(page: str) -> str:
    """The address of the picture the object's page prints ("" without one)."""
    tag = _PRINTED.search(page)
    src = _SRC.search(tag.group(0)) if tag else None
    url = html.unescape(src.group(1)) if src else ""
    return url if url.startswith(f"{SITE}/") else ""


def look(http: httpx.Client, slug: str) -> dict[str, Any] | None:
    """One painting's record: its page names the manifest."""
    page = http.get(f"{SITE}/{slug}")
    if page.status_code == 404:
        return None
    page.raise_for_status()
    found = _MANIFEST.search(page.text)
    if not found:
        return None
    resp = http.get(f"{SITE}/api/iiif/{found.group(1)}/manifest.json")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    work = record(resp.json())
    if work is not None:
        work["picture"] = printed(page.text)
    return work


def original_url(iiif: str, width: int | None, height: int | None) -> str:
    """The picture at most 2560 px: IIIF 3 does not enlarge without "^",
    so a smaller scan is asked whole (``!2560,2560`` of it is a 400)."""
    small = bool(width and height) and max(width or 0, height or 0) <= ORIGINAL
    return f"{iiif}/full/{'max' if small else f'!{ORIGINAL},{ORIGINAL}'}/0/default.jpg"


def blank(img: Image.Image) -> bool:
    """Whether every pixel is (nearly) white."""
    darkest = img.convert("L").getextrema()[0]
    return isinstance(darkest, int | float) and darkest >= BLANK


def from_cmyk_png(data: bytes) -> Image.Image:
    """A PNG of a CMYK scan as the IIIF server gives it: its four channels,
    taken for RGBA, are cyan, magenta, yellow and black."""
    img = Image.open(io.BytesIO(data))
    if img.mode != "RGBA":
        raise OSError(f"a {img.mode} PNG, not a CMYK scan read as RGBA")
    fixed = Image.merge("CMYK", img.split()).convert("RGB")
    if blank(fixed):
        raise OSError("the PNG is white too")
    fixed.info[BYTES] = len(data)
    return fixed


def repair(url: str, img: Image.Image, fetch: Callable[[str], bytes]) -> Image.Image:
    """The IIIF server's white JPEG of a CMYK scan, asked again as PNG and
    read right; any other picture as it came (:attr:`ImageCache.repairs`)."""
    if not _IIIF_JPEG.match(url) or not blank(img):
        return img
    log.info("courtauld: %s came white; asking for the PNG", url)
    return from_cmyk_png(fetch(url.removesuffix(".jpg") + ".png"))


def dimensions(text: str) -> tuple[float, float] | None:
    """ "Height: 96 cm (canvas)<br>Width: 130 cm (canvas)" -> (96, 130)."""
    sides = dict(
        (kind.lower(), float(value))
        for kind, value in re.findall(r"(Height|Width):\s*(\d+(?:\.\d+)?)\s*cm", text)
    )
    return (sides["height"], sides["width"]) if {"height", "width"} <= sides.keys() else None


def build(path: Path, http: httpx.Client) -> int:
    """Write the paintings to ``path``: the ones already there are kept,
    new ones in the sitemap looked up (paced by ``hosts.PACE``),
    gone ones dropped. Returns how many there are."""
    known: dict[str, dict[str, Any] | None] = {}
    if path.is_file():
        try:
            known = json.loads(path.read_text())
        except (OSError, ValueError):
            known = {}
    resp = http.get(f"{SITE}/sitemap.xml", timeout=120)
    resp.raise_for_status()
    slugs = list(dict.fromkeys(_PAINTING.findall(resp.text)))
    if not slugs:
        raise RuntimeError("the sitemap lists no paintings")
    works: dict[str, dict[str, Any] | None] = {}
    for slug in slugs:
        work = known.get(slug)
        if work is not None and "picture" not in work:
            # Listed before the tiles took the page's picture (1.100.7).
            try:
                page = http.get(f"{SITE}/{slug}")
                page.raise_for_status()
                work["picture"] = printed(page.text)
            except httpx.HTTPError as err:
                log.warning("courtauld: picture of %s left for next time: %s", slug, err)
        if slug in known:
            works[slug] = work
            continue
        try:
            works[slug] = look(http, slug)
        except httpx.HTTPError as err:
            log.warning("courtauld: %s left for next time: %s", slug, err)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(works, ensure_ascii=False))
    os.replace(tmp, path)
    return sum(1 for w in works.values() if w)


def forget_white(folders: list[Path]) -> int:
    """Remove the gallery's pictures kept white (before :func:`repair`), so
    they are downloaded again; how many went."""
    gone = 0
    for folder in folders:
        for path in folder.glob("courtauld_*.jpg"):
            try:
                with Image.open(path) as img:
                    white = blank(img)
            except OSError:
                continue
            if white:
                path.unlink(missing_ok=True)
                gone += 1
    return gone


class _Index:
    """The list, written in the background when missing or a month old, and
    kept in memory."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.building = False
        self.failed_at = 0.0
        self._loaded: tuple[Path, float, dict[str, dict[str, Any]]] | None = None

    def works(self, path: Path) -> dict[str, dict[str, Any]]:
        """The paintings (by page) to search; starts writing the list when
        it is missing or old."""
        fresh = path.is_file() and time.time() - path.stat().st_mtime < REFRESH_SECONDS
        if not fresh:
            self._start(path)
        if not path.is_file():
            return {}
        stamp = path.stat().st_mtime
        loaded = self._loaded
        if loaded is None or loaded[0] != path or loaded[1] != stamp:
            try:
                raw = json.loads(path.read_text())
            except (OSError, ValueError):
                return {}
            loaded = (path, stamp, {k: v for k, v in raw.items() if v})
            self._loaded = loaded
            unseen = any("picture" not in w for w in loaded[2].values())
            if unseen and time.time() - stamp > RETRY_SECONDS:
                self._start(path)  # listed before the tiles took the page's picture
        return loaded[2]

    def _start(self, path: Path) -> None:
        if self._claim():
            threading.Thread(
                target=self._build, args=(path,), name="courtauld-index", daemon=True
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
            log.info("courtauld: %d paintings listed in %.0f s", count, time.monotonic() - started)
        except Exception:
            log.exception("courtauld: listing the paintings failed")
            self.failed_at = time.time()
        finally:
            self.building = False

    def refresh(self, path: Path) -> bool:
        """The night's task: the list looked at again once a month (never
        before the first search asked for it). Whether it was."""
        if not path.is_file() or time.time() - path.stat().st_mtime < REFRESH_SECONDS:
            return False
        if not self._claim():
            return False
        self._build(path)
        return True


INDEX = _Index()


def list_path(data_dir: Path) -> Path:
    return data_dir / "courtauld" / "paintings.json"


def refresh_at_night(data_dir: Path) -> bool:
    return INDEX.refresh(list_path(data_dir))


class CourtauldGallery(Museum):
    key: str = "courtauld"
    name: str = "Courtauld Gallery"
    page_size = 100

    @classmethod
    def offered(cls, access: Access) -> bool:
        return access.private_use and access.data_dir is not None

    def _works(self) -> dict[str, dict[str, Any]]:
        folder = self.access.data_dir
        if folder is None or not self.private_use:
            return {}
        return INDEX.works(list_path(folder))

    def _map(self, slug: str, w: dict[str, Any]) -> Item:
        iiif = str(w["iiif"])
        return self._item(
            slug.removeprefix("object-"),
            title=w.get("title") or "",
            artist=w.get("artist") or "",
            date_text=w.get("date") or "",
            year=w.get("year"),
            medium=w.get("medium") or "",
            classification="Painting",
            credit=", ".join(p for p in (w.get("credit") or self.name, w.get("number")) if p),
            license=LICENCE if w.get("free") else PRIVATE_LICENCE,
            url=f"{SITE}/{slug}",
            description=w.get("about") or "",
            image_url=original_url(iiif, w.get("width"), w.get("height")),
            # The page's own picture: the IIIF one of a CMYK scan is white,
            # and the phone takes tiles straight from the gallery.
            thumb_url=w.get("picture") or f"{iiif}/full/!600,600/0/default.jpg",
            width=w.get("width"),
            height=w.get("height"),
        )

    def _pick(self, keep: Any, limit: int, page: int) -> tuple[int, list[Item]]:
        found = [(slug, w) for slug, w in self._works().items() if keep(w)]
        found.sort(key=lambda sw: (sw[1].get("year") or 9999, sw[0]))
        start = (page - 1) * limit
        return len(found), [self._map(s, w) for s, w in found[start : start + limit]]

    @staticmethod
    def _matches(words: list[str], w: dict[str, Any]) -> bool:
        text = " ".join(
            str(w.get(k) or "") for k in ("title", "artist", "date", "medium", "about", "number")
        ).casefold()
        return all(word in text for word in words)

    def only_at_home(self, query: str, limit: int = 8) -> tuple[int, list[Item]] | None:
        """Searched at home anyway (the list is kept here)."""
        return self.search(query, limit, 1)

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        words = query.casefold().split()
        return self._pick(lambda w: self._matches(words, w), limit, page)

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        said, names = words.casefold().split(), artist.casefold().split()

        def by(w: dict[str, Any]) -> bool:
            made = " ".join(str(w.get(k) or "") for k in ("artist", "artist_fr")).casefold()
            return all(n in made for n in names) and self._matches(said, w)

        return self._pick(by, limit, page)

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
        slug = f"object-{source_id}"
        w = self._works().get(slug)
        return self._map(slug, w) if w else None
