"""How big a work really is ("Rozmiar obrazu", the study's last section
but the frame; Mateusz 2026-11-02/03): its height and width in
centimetres, drawn next to a sheet of A4 for scale.

Looked up once per work, in the background when its page opens: the
museum's own record where its API says it plainly (the Met, Cleveland,
SMK, Chicago, the V&A, the national museums in Warsaw and Kraków), the
``dimensions`` of a Commons page's {{Artwork}}; else Wikidata's height and
width (P2048, P2049) of the work, found by the museum's record, the
Commons page, the Commons file as its picture (P18), or last by its title,
a painting whose description names the artist and whose year is the
work's (Mateusz 2026-11-03: "dlaczego tak rzadko"). A size is kept only when its proportions are the
picture's (within :data:`PROPORTION`, 15% since Mateusz 2026-11-03): a
museum's "Overall" of a sheet whose picture is a cut-out, or a frame
measured in place of the canvas, would draw a lie. Nothing found is kept
too, and not asked again.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel

from .holders import COMMONS_API, commons_file, work_qid
from .library import Item, ItemKind
from .library.models import Note
from .library.museums import client
from .library.wikidata import API, record_id

if TYPE_CHECKING:
    from .library import Library

log = logging.getLogger(__name__)

KIND = "real_size"
VERSION = "size-3"  # size-3: more sources; works with none asked again
#: How far the size's proportions may be from the picture's.
PROPORTION = 0.15
#: Sides believed, in centimetres: a miniature to a ceiling.
SMALLEST = 1.0
LARGEST = 2000.0

#: Wikidata's units of length → centimetres.
UNITS = {
    "Q174728": 1.0,  # centimetre
    "Q174789": 0.1,  # millimetre
    "Q11573": 100.0,  # metre
    "Q218593": 2.54,  # inch
}

#: "45.7 x 40.6 cm", "45,7 × 40,6 cm", "457 x 406 mm" (height first, as
#: museums write it; a third number is the depth).
_NUMBER = r"(\d+(?:[.,]\d+)?)"
DIMENSIONS = re.compile(
    rf"{_NUMBER}\s*[x×]\s*{_NUMBER}(?:\s*[x×]\s*{_NUMBER})?\s*(cm|mm|m)\b", re.IGNORECASE
)
#: Parts of a measurement that are not the work itself.
NOT_THE_WORK = re.compile(r"\b(framed|frame|mount|mat|sheet|support|brutto)\b", re.IGNORECASE)


class RealSize(BaseModel):
    """The work's height and width, in centimetres."""

    height: float
    width: float


def _cm(value: str, unit: str) -> float:
    scale = {"cm": 1.0, "mm": 0.1, "m": 100.0}[unit.lower()]
    return float(value.replace(",", ".")) * scale


def parse(text: str) -> RealSize | None:
    """The work's size from a museum's text ("Framed: 128.3 x 105.7 x 14.6 cm;
    Unframed: 99 x 79.8 cm" → 99 × 79.8): the first measurement that is not
    of a frame, a mount or the sheet, else the first."""
    found: list[tuple[bool, RealSize]] = []
    for part in re.split(r"[;\n]", text):
        for match in DIMENSIONS.finditer(part):
            height, width, _depth, unit = match.groups()
            size = RealSize(height=_cm(height, unit), width=_cm(width, unit))
            label = part[: match.start()]
            found.append((bool(NOT_THE_WORK.search(label)), size))
    for aside, size in found:
        if not aside:
            return size
    return found[0][1] if found else None


def fits(size: RealSize, item: Item) -> RealSize | None:
    """``size`` when it is believable and has the picture's proportions;
    turned when the museum gave width before height; else None."""
    if not all(SMALLEST <= side <= LARGEST for side in (size.height, size.width)):
        return None
    if not item.width or not item.height:
        return size  # the picture's size unknown: the museum's word for it

    def off(height: float, width: float) -> float:
        return abs(math.log((width / height) / (item.width / item.height)))  # type: ignore[operator]

    limit = math.log(1 + PROPORTION)
    if off(size.height, size.width) <= limit:
        return size
    if off(size.width, size.height) <= limit:
        return RealSize(height=size.width, width=size.height)
    return None


#: Muza's "wys. 12,5 cm, szer. 11 cm".
_POLISH = re.compile(
    rf"wys\.?\s*{_NUMBER}\s*(cm|mm|m)?\b.*?szer\.?\s*{_NUMBER}\s*(cm|mm|m)\b", re.IGNORECASE
)
#: A Commons {{Size|cm|77|53}} (height, width) or {{Size|unit=cm|height=..|width=..}}.
_SIZE_TEMPLATE = re.compile(r"\{\{\s*size\s*\|([^}]*)\}\}", re.IGNORECASE)
#: Muza's names of a measurement of something other than the work.
_NOT_THE_WORK_PL = re.compile(r"ram|passe|oprawa|karton|arkusz|podkład|płyt", re.IGNORECASE)


def commons_size(wikitext: str) -> RealSize | None:
    """The size in a Commons page's {{Artwork |dimensions = ...}}: a
    {{Size}} template, else a "73 × 92 cm" in its text."""
    match = re.search(r"^\s*\|\s*dimensions\s*=(.*)$", wikitext, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    value = match.group(1)
    if template := _SIZE_TEMPLATE.search(value):
        named: dict[str, str] = {}
        plain: list[str] = []
        for part in template.group(1).split("|"):
            key, eq, rest = part.partition("=")
            if eq:
                named[key.strip().casefold()] = rest.strip()
            else:
                plain.append(part.strip())
        unit = named.get("unit") or (plain.pop(0) if plain else "")
        height = named.get("height") or (plain[0] if plain else "")
        width = named.get("width") or (plain[1] if len(plain) > 1 else "")
        if unit.casefold() in ("cm", "mm", "m") and height and width:
            try:
                return RealSize(height=_cm(height, unit), width=_cm(width, unit))
            except ValueError:
                pass
    return parse(value)


def _quantity(entity: dict[str, Any], prop: str) -> float | None:
    for claim in (entity.get("claims") or {}).get(prop) or []:
        if claim.get("rank") == "deprecated" or "P518" in (claim.get("qualifiers") or {}):
            continue  # of a part ("applies to part": the frame, the panel's back...)
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(value, dict):
            continue
        unit = str(value.get("unit") or "").rsplit("/", 1)[-1]
        if unit in UNITS:
            try:
                return float(value["amount"]) * UNITS[unit]
            except (KeyError, TypeError, ValueError):
                continue
    return None


def _search(http: httpx.Client, query: str, limit: int = 1) -> list[str]:
    resp = http.get(
        API,
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        },
    )
    resp.raise_for_status()
    return [str(hit["title"]) for hit in resp.json().get("query", {}).get("search") or []]


def _entities(http: httpx.Client, ids: list[str]) -> dict[str, Any]:
    resp = http.get(
        API,
        params={
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": "claims|descriptions",
            "languages": "en",
            "format": "json",
        },
    )
    resp.raise_for_status()
    return resp.json().get("entities") or {}


def _sides(entity: dict[str, Any]) -> RealSize | None:
    height, width = _quantity(entity, "P2048"), _quantity(entity, "P2049")
    return RealSize(height=height, width=width) if height and width else None


def _year(entity: dict[str, Any]) -> int | None:
    for claim in (entity.get("claims") or {}).get("P571") or []:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and (match := re.match(r"[+-](\d+)-", str(value.get("time")))):
            return int(match.group(1))
    return None


def _surname(artist: str) -> str:
    """The word an English description names the artist by: "Vermeer" of
    "Johannes Vermeer" or "Vermeer, Johannes"."""
    name = artist.split(",")[0] if "," in artist else (artist.split() or [""])[-1]
    return name.strip().casefold() if len(name.strip()) > 2 else ""


def from_wikidata(http: httpx.Client, item: Item) -> RealSize | None:
    """Height (P2048) and width (P2049) of the Wikidata work linked to the
    museum's record."""
    ref = record_id(item)
    if ref is None:
        return None
    found = _search(http, f"haswbstatement:{ref[0]}={ref[1]}")
    if not found:
        return None
    return _sides(_entities(http, found[:1]).get(found[0]) or {})


def from_commons(http: httpx.Client, item: Item) -> RealSize | None:
    """The size on the work's Commons page, else on the Wikidata item that
    page names, else on the one whose picture (P18) is its file."""
    page_id, title = commons_file(item)
    if not page_id and not title:
        return None
    params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
    }
    params["pageids" if page_id else "titles"] = page_id or title
    resp = http.get(COMMONS_API, params=params)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages") or []
    if not pages or "revisions" not in pages[0]:
        return None
    text = str(pages[0]["revisions"][0].get("slots", {}).get("main", {}).get("content") or "")
    if (size := commons_size(text)) is not None:
        return size
    qid = work_qid(text)
    if not qid:
        name = str(pages[0].get("title") or title).removeprefix("File:")
        found = _search(http, f'haswbstatement:"P18={name}"') if name else []
        qid = found[0] if found else ""
    return _sides(_entities(http, [qid]).get(qid) or {}) if qid else None


def by_title(http: httpx.Client, item: Item) -> RealSize | None:
    """A painting on Wikidata by the work's title, whose English description
    names the artist ("painting by Johannes Vermeer") and whose year, when
    both are known, is the work's within two."""
    surname = _surname(item.artist)
    title = re.sub(r"[\"“”„«»]", " ", item.title).strip()
    if not surname or len(title) < 3:
        return None
    found = _search(http, f"{title} haswbstatement:P31=Q3305213", limit=5)
    if not found:
        return None
    entities = _entities(http, found)
    for qid in found:
        entity = entities.get(qid) or {}
        about = str(((entity.get("descriptions") or {}).get("en") or {}).get("value") or "")
        if surname not in about.casefold():
            continue
        year = _year(entity)
        if item.year and year and abs(item.year - year) > 2:
            continue
        if (size := _sides(entity)) is not None:
            return size
    return None


def _met(http: httpx.Client, item: Item) -> RealSize | None:
    resp = http.get(
        f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{item.source_id}"
    )
    resp.raise_for_status()
    data = resp.json()
    for part in data.get("measurements") or []:
        if str(part.get("elementName") or "").casefold() == "overall":
            sides = part.get("elementMeasurements") or {}
            if sides.get("Height") and sides.get("Width"):
                return RealSize(height=float(sides["Height"]), width=float(sides["Width"]))
    return parse(str(data.get("dimensions") or ""))


def _cma(http: httpx.Client, item: Item) -> RealSize | None:
    resp = http.get(f"https://openaccess-api.clevelandart.org/api/artworks/{item.source_id}")
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    dims = data.get("dimensions") or {}
    for part in ("unframed", "overall", "image"):
        sides = dims.get(part) or {}
        if sides.get("height") and sides.get("width"):  # metres
            return RealSize(height=float(sides["height"]) * 100, width=float(sides["width"]) * 100)
    return parse(str(data.get("measurements") or ""))


def _smk(http: httpx.Client, item: Item) -> RealSize | None:
    resp = http.get("https://api.smk.dk/api/v1/art/", params={"object_number": item.source_id})
    resp.raise_for_status()
    found = (resp.json().get("items") or [{}])[0].get("dimensions") or []
    sides: dict[str, float] = {}
    for part in found:
        if str(part.get("part") or "").casefold() != "netto":
            continue
        if str(part.get("unit") or "") not in ("centimeter", "cm"):
            continue
        kind = {"højde": "height", "bredde": "width"}.get(str(part.get("type") or ""))
        if kind and kind not in sides:
            try:
                sides[kind] = float(str(part.get("value")).replace(",", "."))
            except ValueError:
                continue
    return RealSize(**sides) if len(sides) == 2 else None


def _aic(http: httpx.Client, item: Item) -> RealSize | None:
    resp = http.get(
        f"https://api.artic.edu/api/v1/artworks/{item.source_id}",
        params={"fields": "dimensions,dimensions_detail"},
    )
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    for part in data.get("dimensions_detail") or []:  # centimetres
        if not part.get("clarification") and part.get("height") and part.get("width"):
            return RealSize(height=float(part["height"]), width=float(part["width"]))
    return parse(str(data.get("dimensions") or ""))


def _vam(http: httpx.Client, item: Item) -> RealSize | None:
    resp = http.get(f"https://api.vam.ac.uk/v2/museumobject/{item.source_id}")
    resp.raise_for_status()
    sides: dict[str, float] = {}
    for part in (resp.json().get("record") or {}).get("dimensions") or []:
        kind = str(part.get("dimension") or "").casefold()
        unit = str(part.get("unit") or "")
        wanted = kind in ("height", "width") and kind not in sides and not part.get("part")
        if wanted and unit in ("cm", "mm", "m"):
            try:
                sides[kind] = _cm(str(part.get("value")), unit)
            except ValueError:
                continue
    return RealSize(**sides) if len(sides) == 2 else None


def _muza(api: str) -> Callable[[httpx.Client, Item], RealSize | None]:
    def ask(http: httpx.Client, item: Item) -> RealSize | None:
        resp = http.get(f"{api}/object/{item.source_id}")
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        for size in data.get("sizes") or []:
            if _NOT_THE_WORK_PL.search(str(size.get("name") or "")):
                continue
            sides: dict[str, float] = {}
            for part in size.get("dimensions") or []:
                kind = {"wysokość": "height", "szerokość": "width"}.get(str(part.get("name") or ""))
                unit = str(part.get("unit") or "")
                if kind and kind not in sides and unit in ("cm", "mm", "m"):
                    try:
                        sides[kind] = _cm(str(part.get("value")), unit)
                    except ValueError:
                        continue
            if len(sides) == 2:
                return RealSize(**sides)
        if match := _POLISH.search(str(data.get("dimensionText") or "")):
            height, unit_h, width, unit = match.groups()
            return RealSize(height=_cm(height, unit_h or unit), width=_cm(width, unit))
        return None

    return ask


#: Museums whose own record says the size plainly.
MUSEUMS: dict[str, Callable[[httpx.Client, Item], RealSize | None]] = {
    "met": _met,
    "cma": _cma,
    "smk": _smk,
    "aic": _aic,
    "vam": _vam,
    "mnw": _muza("https://cyfrowe-api.mnw.art.pl/api"),
    "mnk": _muza("https://api-zbiory.mnk.pl/api"),
}


class Sizes:
    """Works' real sizes, kept as notes of :data:`KIND` (``{}``: none)."""

    def __init__(self, library: Library, http: Callable[[], httpx.Client] | None = None) -> None:
        self.library = library
        #: Opens a client for one look (the museums' own when None).
        self.http = http
        self._lock = threading.Lock()
        self._looking: set[str] = set()

    def size(self, item: Item) -> RealSize | None:
        note = self.library.note(item.id, KIND)
        if note is None or note.prompt_version != VERSION or not note.data:
            return None
        return RealSize.model_validate(note.data)

    def asked(self, item: Item) -> bool:
        note = self.library.note(item.id, KIND)
        return note is not None and note.prompt_version == VERSION

    def look_soon(self, item: Item) -> bool:
        """Looks the size up in the background, once; True while it does."""
        if item.kind != ItemKind.ARTWORK or self.asked(item):
            return False
        with self._lock:
            if item.id in self._looking:
                return True
            self._looking.add(item.id)
        threading.Thread(target=self._look, args=(item,), name="real-size", daemon=True).start()
        return True

    def _look(self, item: Item) -> None:
        try:
            self.look(item)
        except Exception:
            log.exception("real size of %s", item.id)
        finally:
            with self._lock:
                self._looking.discard(item.id)

    def look(self, item: Item) -> RealSize | None:
        """The museum's size, else Commons', else Wikidata's, when it fits
        the picture; kept (also none)."""
        found: RealSize | None = None
        with (self.http or client)() as http:
            for ask in (MUSEUMS.get(item.source), from_commons, from_wikidata, by_title):
                if ask is None:
                    continue
                try:
                    size = ask(http, item)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as err:
                    log.info("real size of %s: %s", item.id, err)
                    return None  # not kept: asked again next time
                if size is not None and (found := fits(size, item)) is not None:
                    break
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model="",
                prompt_version=VERSION,
                data=found.model_dump() if found else {},
            )
        )
        return found
