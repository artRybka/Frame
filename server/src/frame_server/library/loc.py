"""Library of Congress, Washington: photographs only, asked only when
Szukaj (or a playlist) asks for Fotografia (Mateusz 2026-11-06: widen
Fotografia without filling the catalogue).

Its JSON API (www.loc.gov ``?fo=json``) needs no key. A search result
carries the rights advisory, so only works with "No known restrictions"
and not restricted to the library's own rooms are taken, and only
photographs (negatives, slides, autochromes, photochroms…), never its
prints, drawings and books. Words typed search all its photographs; a draw
without words takes turns between collections of known photographers:
FSA/OWI in colour and black and white (Lange, Evans, Delano), Prokudin-
Gorsky's colour photographs of Russia, the photochroms, the Civil War glass
negatives, Frances Benjamin Johnston and Lewis Hine.

Pictures come over IIIF: the full scan (``master:…u``) when there is one
(often 3000-8000 px), else the 1024 px service copy. The API's rules ask
for at most 20 requests in 10 seconds and 80 a minute for searches
(hosts.PACE), or the address is blocked for an hour.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .models import Item
from .museums import Discovery, Kind, Museum

API = "https://www.loc.gov"
IIIF = "https://tile.loc.gov/image-services/iiif"
SERVICE = "https://tile.loc.gov/storage-services/service/"

#: Collections a draw without words takes turns between (all "No known
#: restrictions"), by their slug on www.loc.gov/collections/, with words
#: that pick their photographs: the FSA's black-and-white collection lists
#: prints seen only in the library first, its negatives are free.
COLLECTIONS: dict[str, str] = {
    "fsa-owi-color-photographs": "",
    "prokudin-gorskii": "",
    "photochrom-prints": "",
    "fsa-owi-black-and-white-negatives": "negative",
    "civil-war-glass-negatives": "",
    "frances-benjamin-johnston": "",
    "national-child-labor-committee": "",
}
#: Results asked for a page of words: some are prints or restricted.
SEARCH_PAGE = 40

#: Photographs by their material: negatives and slides are shown as
#: positives. Stereographs are two pictures side by side: never.
_PHOTO = re.compile(
    r"\b(photograph\w*|negatives?|slides?|transparenc\w*|autochromes?|photochroms?|"
    r"daguerreotypes?|ambrotypes?|tintypes?|albumen|gelatin|cyanotypes?|platinum)\b",
    re.IGNORECASE,
)
_STEREO = re.compile(r"\bstereo\w*", re.IGNORECASE)
#: What a contributor's name ends with: "Lange, Dorothea, photographer".
_ROLE = re.compile(r",?\s*(photographer|creator|artist|publisher|author)\.?$", re.IGNORECASE)


def _one(value: Any) -> str:
    """The first of a list, or the value itself, as text."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = next(iter(value), "")
    return str(value or "")


def _joined(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value if isinstance(v, str))
    return str(value or "")


def person(name: str) -> tuple[str, str]:
    """("Dorothea Lange", "") of "Lange, Dorothea, photographer";
    ("Jack Delano", "1914–1997") of "Delano, Jack, 1914-1997"."""
    name = _ROLE.sub("", name.strip()).strip(" ,.")
    bio = ""
    if (years := re.search(r",\s*(?:approximately\s+)?(\d{4}-(?:\d{4})?)$", name)) is not None:
        bio = years.group(1).replace("-", "–").rstrip("–")
        name = name[: years.start()].strip(" ,")
    last, comma, first = name.partition(", ")
    return (f"{first} {last}" if comma and first else name).strip(), bio


def free(d: dict[str, Any]) -> bool:
    """Shown anywhere, as the library's rights advisory says."""
    advisory = _one(d.get("rights_advisory")).strip()
    return not d.get("access_restricted") and advisory.startswith("No known restrictions")


def pictures(d: dict[str, Any]) -> tuple[str, str] | None:
    """The full picture and the thumbnail of a result, over IIIF."""
    urls = [str(u).split("#", 1)[0] for u in d.get("image_url") or []]
    # Newer scans (Highsmith's) come as IIIF addresses already.
    if iiif := next((u for u in urls if u.startswith(f"{IIIF}/") and "/full/" in u), None):
        base = iiif.split("/full/", 1)[0]
        return f"{base}/full/!2560,2560/0/default.jpg", f"{base}/full/600,/0/default.jpg"
    jpegs = [u for u in urls if u.startswith(SERVICE) and u.endswith(".jpg")]
    largest = next((u for u in reversed(jpegs) if u.endswith("v.jpg")), None) or next(
        (u for u in reversed(jpegs) if u.endswith("r.jpg")), None
    )
    if largest is None:
        return None
    path = largest.removeprefix(SERVICE)[: -len("v.jpg")]
    thumb = next((u for u in jpegs if u.endswith("r.jpg")), largest)
    if "image/tif" in (d.get("mime_type") or []):
        image = f"{IIIF}/master:{path.replace('/', ':')}u/full/!2560,2560/0/default.jpg"
    else:
        image = largest
    return image, thumb


def loc_mirrors(item: Item, thumb: bool = False) -> list[str]:
    """The 1024 px service copy, when the full scan's address fails (some
    scans are kept under another name than their copies)."""
    if item.source != "loc" or thumb or f"{IIIF}/master:" not in item.image_url:
        return []
    path = item.image_url.removeprefix(f"{IIIF}/master:").split("/", 1)[0]
    base = f"{SERVICE}{path[:-1].replace(':', '/')}"
    return [f"{base}v.jpg", f"{base}r.jpg"]


class LibraryOfCongress(Museum):
    key: str = "loc"
    name: str = "Library of Congress"
    page_size = 100
    random_depth = 2000
    #: Asked only for photographs (Importer.asked_sources).
    only: ClassVar[Kind | None] = "photograph"

    def _map(self, d: dict[str, Any]) -> Item | None:
        # A search result keeps half its facts under "item".
        d = {**(d.get("item") or {}), **{k: v for k, v in d.items() if k != "item"}}
        number = _one(d.get("number_lccn")) or _one(d.get("control_number"))
        if not number.isdigit() or not free(d):
            return None
        medium = _joined(d.get("medium"))
        what = f"{medium} {_joined(d.get('genre'))}"
        if not _PHOTO.search(what) or _STEREO.search(what):
            return None
        found = pictures(d)
        if found is None:
            return None
        creators = d.get("creators") or []
        names = [c.get("title", "") for c in creators if isinstance(c, dict)]
        names += [n for n in d.get("contributor_names") or [] if isinstance(n, str)]
        names += [n for n in d.get("contributors") or [] if isinstance(n, str) and "," in n]
        artist, bio = person(names[0]) if names else ("", "")
        date = _one(d.get("created_published_date")) or _one(d.get("created_published"))
        date = re.sub(r"[\[\]?]", "", date or _one(d.get("date")))  # "194[1] Jan.?"
        year = re.search(r"\b(\d{4})\b", date) or re.search(r"\b(\d{4})\b", _one(d.get("dates")))
        headings = [h for h in d.get("subject_headings") or [] if isinstance(h, str)]
        image, thumb = found
        return self._item(
            number,
            title=str(d.get("title") or "").strip(),
            artist=artist,
            artist_bio=bio,
            date_text=re.sub(r"(\d)\.$", r"\1", date.strip()),
            year=int(year.group(1)) if year else None,
            medium=medium,
            classification="Photograph",
            subjects=list(dict.fromkeys(h.split("--")[0] for h in headings))[:8],
            culture="",
            credit=_one(d.get("source_collection")) or _one(d.get("part_of")) or self.name,
            license="No known restrictions",
            url=f"{API}/item/{number}/",
            description=_joined(d.get("summary")),
            image_url=image,
            thumb_url=thumb,
        )

    def _get(
        self, path: str, params: dict[str, Any], limit: int, page: int
    ) -> tuple[int, list[dict[str, Any]]]:
        resp = self.http.get(
            f"{API}{path}",
            params={**params, "fo": "json", "c": limit, "sp": page, "at": "results,pagination"},
        )
        if resp.status_code == 404:
            return 0, []
        resp.raise_for_status()
        body = resp.json()
        results = [r for r in body.get("results") or [] if isinstance(r, dict)]
        return int((body.get("pagination") or {}).get("total") or 0), results

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if not query.strip():
            return self.discover(Discovery(kind="photograph"), limit, page)
        return self._words(query.strip(), {}, page)

    def _words(self, words: str, params: dict[str, Any], page: int) -> tuple[int, list[Item]]:
        # Pages of a fixed size, so that the next page follows on; what is
        # restricted or no photograph is left out of each.
        total, results = self._get(
            "/photos/", {"q": words, "fa": "online-format:image", **params}, SEARCH_PAGE, page
        )
        return total, [i for r in results if (i := self._map(r))]

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.kind != "photograph" or spec.highlight:
            return 0, []
        params: dict[str, Any] = {}
        if spec.year_from is not None or spec.year_to is not None:
            start = max(spec.year_from if spec.year_from is not None else 1800, 1800)
            end = spec.year_to if spec.year_to is not None else 2100
            if end < start:
                return 0, []
            params["dates"] = f"{start}/{end}"
        if spec.style.strip():
            return self._words(spec.style.strip(), params, page)
        # A collection a page, in turns; one with nothing for these years
        # gives its turn to the next.
        slugs = list(COLLECTIONS)
        count = len(slugs)
        turn, deep = (page - 1) % count, (page - 1) // count + 1
        for step in range(count):
            slug = slugs[(turn + step) % count]
            asked = {**params, "q": COLLECTIONS[slug]} if COLLECTIONS[slug] else params
            total, results = self._get(f"/collections/{slug}/", asked, limit, deep)
            items = [i for r in results if (i := self._map(r))]
            if items:
                # Every collection's pages count: the draw goes on while any has more.
                return max(total, deep * limit + 1) * count, items
        return 0, []

    def fetch(self, source_id: str) -> Item | None:
        if not source_id.isdigit():
            return None
        resp = self.http.get(f"{API}/item/{source_id}/", params={"fo": "json"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        item = resp.json().get("item") or {}
        return self._map(item) if isinstance(item, dict) else None
