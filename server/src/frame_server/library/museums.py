"""Open-access museum collections: search and metadata import.

Only works free to show are returned: public domain / CC0, public domain in
the EU (author dead for more than 70 years), and with ``private_use`` also
works under free licences. Every museum maps its records onto :class:`Item`
(without colours; those are computed from the thumbnail at import time).
"""

from __future__ import annotations

import html
import random
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar, Literal
from urllib.parse import quote, unquote, urlsplit

import httpx

from .commons import commons_html, commons_year
from .hosts import guard
from .lifespan import (
    EUROPEANA_AGENT,
    TERM_YEARS,
    WIKIDATA_ENTITY,
    LifeDates,
    death_in_name,
    free_in_eu,
)
from .markup import VECTOR, WEB_IMAGES, commons_rendition, extension, strip_markup
from .models import Item, ItemKind

USER_AGENT = "Frame/0.2 (home e-paper art frame; +https://github.com/artRybka/Frame)"


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"</p>\s*<p>", "\n\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "AIC-User-Agent": USER_AGENT},
        event_hooks=guard.hooks(),
        timeout=30,
        follow_redirects=True,
    )


#: What to draw: pictures (the frame's own) and, only when asked for,
#: photographs, sculpture and decorative arts (ceramics, textiles, glass…).
Kind = Literal[
    "any", "painting", "print", "drawing", "poster", "photograph", "sculpture", "decorative"
]


@dataclass(frozen=True)
class Access:
    """What the owner lets sources return, and how to reach them."""

    #: The frame is only seen at home: also free licences (CC BY-SA and the like).
    private_use: bool = False
    #: WikiArt, only to test the panel (it shows works without licences).
    wikiart: bool = False
    #: Only to test the app as it will be in some years: works whose authors
    #: died less than 70 years ago count too, marked with ``TEST_LICENCE``.
    ignore_term: bool = False
    #: Death years for the EU rule; without it only works marked free count.
    life: LifeDates | None = None
    europeana_key: str = "api2demo"
    #: Openverse app credentials (client id, secret); anonymous without them.
    openverse_app: tuple[str, str] | None = None


@dataclass(frozen=True)
class Discovery:
    """What to draw from a collection at random; every field is optional."""

    year_from: int | None = None
    year_to: int | None = None
    #: Free text matched against styles and movements, e.g. "Impressionism".
    style: str = ""
    kind: Kind = "any"
    #: Only the works the museum counts among its most important.
    highlight: bool = False

    def fits(self, item: Item) -> bool:
        """Museums' date filters are coarse; this checks the year exactly."""
        if item.year is None:
            return self.year_from is None and self.year_to is None
        if self.year_from is not None and item.year < self.year_from:
            return False
        return self.year_to is None or item.year <= self.year_to


class Museum(ABC):
    key: str
    name: str
    #: Most results one search request may ask for.
    page_size = 100
    #: How deep random draws reach into results (search engines stop paging
    #: at 10 000).
    random_depth = 10_000
    #: Only offered while the owner has switched it on for tests.
    testing: ClassVar[bool] = False
    #: Marks its most important works and can be asked for only those.
    highlights: ClassVar[bool] = False

    def __init__(
        self, http: httpx.Client, private_use: bool = False, access: Access | None = None
    ) -> None:
        self.http = http
        self.access = access or Access(private_use=private_use)
        self.private_use = self.access.private_use

    @abstractmethod
    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        """Public-domain works matching ``query``; returns (total, items)."""

    @abstractmethod
    def fetch(self, source_id: str) -> Item | None:
        """One work by its id in the museum's collection."""

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        """Works matching ``spec`` (in any order); returns (total, items).

        Sources that cannot filter this way return nothing.
        """
        return 0, []

    def random_draw(self, spec: Discovery, rng: random.Random) -> Iterator[Item]:
        """Works matching ``spec``, from result pages taken in random order."""
        if spec.highlight and not self.highlights:
            return
        size = min(self.page_size, 24)
        total, _ = self.discover(spec, limit=1, page=1)
        pages = list(range(1, -(-min(total, self.random_depth) // size) + 1))
        rng.shuffle(pages)
        for page in pages:
            _, items = self.discover(spec, limit=size, page=page)
            rng.shuffle(items)
            yield from items

    def _item(self, source_id: str, **fields: Any) -> Item:
        for key in ("title", "artist"):
            if key in fields:
                fields[key] = strip_markup(fields[key])
        return Item(
            id=f"{self.key}:{source_id}",
            kind=ItemKind.ARTWORK,
            source=self.key,
            source_id=source_id,
            museum=self.name,
            **fields,
        )


class ArtInstituteChicago(Museum):
    key = "aic"
    name = "Art Institute of Chicago"
    api = "https://api.artic.edu/api/v1"
    iiif = "https://www.artic.edu/iiif/2"
    fields = (
        "id,title,artist_title,artist_display,date_display,date_start,medium_display,"
        "artwork_type_title,style_titles,subject_titles,place_of_origin,credit_line,"
        "description,short_description,image_id,thumbnail,is_public_domain"
    )

    def _map(self, d: dict[str, Any]) -> Item | None:
        if not d.get("image_id") or not d.get("is_public_domain"):
            return None
        display = (d.get("artist_display") or "").split("\n")
        thumb = d.get("thumbnail") or {}
        # The IIIF server refuses (403) a picture asked wider than it is.
        width = thumb.get("width")

        def size(most: int) -> str:
            return "full" if width and width <= most else f"{most},"

        return self._item(
            str(d["id"]),
            title=d.get("title") or "",
            artist=d.get("artist_title") or display[0].strip(),
            artist_bio=display[1].strip() if len(display) > 1 else "",
            date_text=d.get("date_display") or "",
            year=d.get("date_start"),
            medium=d.get("medium_display") or "",
            classification=d.get("artwork_type_title") or "",
            styles=d.get("style_titles") or [],
            subjects=d.get("subject_titles") or [],
            culture=d.get("place_of_origin") or "",
            credit=d.get("credit_line") or "",
            license="CC0 1.0",
            url=f"https://www.artic.edu/artworks/{d['id']}",
            description=strip_html(d.get("description") or d.get("short_description")),
            image_url=f"{self.iiif}/{d['image_id']}/full/{size(1686)}/0/default.jpg",
            thumb_url=f"{self.iiif}/{d['image_id']}/full/{size(600)}/0/default.jpg",
            width=width,
            height=thumb.get("height"),
        )

    # Searched by the must-clause below; ``q`` alone only ranks and matches
    # the whole collection when nothing fits.
    search_fields = (
        "title",
        "alt_titles",
        "artist_title",
        "artist_display",
        "style_titles",
        "subject_titles",
        "term_titles",
        "classification_titles",
        "place_of_origin",
        "medium_display",
    )

    artwork_types: ClassVar[dict[str, str]] = {
        "painting": "Painting",
        "print": "Print",
        "drawing": "Drawing and Watercolor",
        "photograph": "Photograph",
        "sculpture": "Sculpture",
    }
    decorative_types = (
        "Ceramics",
        "Vessel",
        "Glass",
        "Metalwork",
        "Textile",
        "Furniture",
        "Costume and Accessories",
        "Jewelry",
    )

    @staticmethod
    def _text(query: str, fields: tuple[str, ...]) -> dict[str, Any]:
        return {
            "simple_query_string": {
                "query": query,
                "fields": list(fields),
                "default_operator": "and",
            }
        }

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        must = [self._text(query, self.search_fields)] if query.strip() else []
        return self._post(query, must, [], limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        must: list[dict[str, Any]] = []
        filters: list[dict[str, Any]] = []
        if spec.style.strip():
            fields = ("style_titles", "term_titles", "subject_titles", "classification_titles")
            must.append(self._text(spec.style, fields))
        if spec.kind == "poster":
            must.append(self._text("poster", ("classification_titles", "term_titles")))
        elif spec.kind in self.artwork_types:
            must.append({"match": {"artwork_type_title": self.artwork_types[spec.kind]}})
        elif spec.kind == "decorative":
            must.append({"terms": {"artwork_type_title.keyword": list(self.decorative_types)}})
        if spec.year_from is not None:
            filters.append({"range": {"date_start": {"gte": spec.year_from}}})
        if spec.year_to is not None:
            filters.append({"range": {"date_start": {"lte": spec.year_to}}})
        return self._post("", must, filters, limit, page)

    def _post(
        self,
        query: str,
        must: list[dict[str, Any]],
        filters: list[dict[str, Any]],
        limit: int,
        page: int,
    ) -> tuple[int, list[Item]]:
        public = {"term": {"is_public_domain": True}}
        body: dict[str, Any] = {
            "limit": limit,
            "page": page,
            "fields": self.fields.split(","),
            "query": {"bool": {"must": must, "filter": [public, *filters]}},
        }
        if query:
            body["q"] = query
        resp = self.http.post(f"{self.api}/artworks/search", json=body)
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("data", []) if (i := self._map(d))]
        return int(body.get("pagination", {}).get("total", len(items))), items

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(f"{self.api}/artworks/{source_id}", params={"fields": self.fields})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(resp.json().get("data", {}))


class ClevelandMuseum(Museum):
    key = "cma"
    name = "Cleveland Museum of Art"
    api = "https://openaccess-api.clevelandart.org/api"
    highlights = True

    @staticmethod
    def _creator(d: dict[str, Any]) -> tuple[str, str]:
        creators = d.get("creators") or []
        if not creators:
            return "", ""
        text = creators[0].get("description") or ""
        match = re.match(r"^(.*?)\s*\((.*)\)\s*$", text)
        return (match.group(1), match.group(2)) if match else (text, "")

    def _map(self, d: dict[str, Any]) -> Item | None:
        images = d.get("images") or {}
        web = images.get("web") or {}
        large = images.get("print") or images.get("full") or web
        if not web.get("url") or d.get("share_license_status") != "CC0":
            return None
        artist, bio = self._creator(d)
        culture = d.get("culture") or []
        return self._item(
            str(d["id"]),
            title=d.get("title") or "",
            artist=artist,
            artist_bio=bio,
            date_text=d.get("creation_date") or "",
            year=d.get("creation_date_earliest"),
            medium=d.get("technique") or "",
            classification=d.get("type") or "",
            styles=[c for c in culture if c],
            subjects=[],
            culture=culture[0] if culture else "",
            credit=d.get("creditline") or "",
            license="CC0 1.0",
            url=d.get("url") or "",
            highlight=bool(d.get("is_highlight")),
            description=strip_html(d.get("description") or d.get("wall_description")),
            image_url=large.get("url") or web["url"],
            thumb_url=web["url"],
            width=int(web["width"]) if web.get("width") else None,
            height=int(web["height"]) if web.get("height") else None,
        )

    types: ClassVar[dict[str, str]] = {
        "painting": "Painting",
        "print": "Print",
        "drawing": "Drawing",
        "photograph": "Photograph",
        "sculpture": "Sculpture",
        "decorative": "Ceramic",  # one type per request
    }

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        return self._get({"q": query}, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        words = [spec.style.strip(), "poster" if spec.kind == "poster" else ""]
        params: dict[str, Any] = {"q": " ".join(w for w in words if w)}
        if spec.kind in self.types:
            params["type"] = self.types[spec.kind]
        if spec.year_from is not None:
            params["created_after"] = spec.year_from
        if spec.year_to is not None:
            params["created_before"] = spec.year_to
        if spec.highlight:
            params["highlight"] = 1
        return self._get(params, limit, page)

    def _get(self, params: dict[str, Any], limit: int, page: int) -> tuple[int, list[Item]]:
        resp = self.http.get(
            f"{self.api}/artworks/",
            params={
                **params,
                "has_image": 1,
                "cc0": 1,
                "limit": limit,
                "skip": (page - 1) * limit,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("data", []) if (i := self._map(d))]
        return int(body.get("info", {}).get("total", len(items))), items

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(f"{self.api}/artworks/{source_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(resp.json().get("data", {}))


class MetropolitanMuseum(Museum):
    key = "met"
    name = "The Metropolitan Museum of Art"
    api = "https://collectionapi.metmuseum.org/public/collection"
    highlights = True

    def _map(self, d: dict[str, Any]) -> Item | None:
        if not d.get("isPublicDomain") or not d.get("primaryImageSmall"):
            return None
        styles = [s for s in (d.get("period"), d.get("culture"), d.get("dynasty")) if s]
        return self._item(
            str(d["objectID"]),
            title=d.get("title") or "",
            artist=d.get("artistDisplayName") or "",
            artist_bio=d.get("artistDisplayBio") or "",
            date_text=d.get("objectDate") or "",
            year=d.get("objectBeginDate"),
            medium=d.get("medium") or "",
            classification=d.get("classification") or d.get("objectName") or "",
            styles=styles,
            subjects=[t["term"] for t in d.get("tags") or [] if t.get("term")],
            culture=d.get("culture") or "",
            credit=d.get("creditLine") or "",
            license="CC0 1.0",
            url=d.get("objectURL") or "",
            highlight=bool(d.get("isHighlight")),
            description="",
            image_url=d.get("primaryImage") or d["primaryImageSmall"],
            thumb_url=d["primaryImageSmall"],
        )

    page_size = 24  # every result is one more request

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        return self._search({"q": query}, limit, page)

    # Departments: European Paintings; Drawings and Prints; Photographs;
    # European Sculpture and Decorative Arts.
    departments: ClassVar[dict[str, int]] = {
        "painting": 11,
        "print": 9,
        "drawing": 9,
        "poster": 9,
        "photograph": 19,
        "sculpture": 12,
        "decorative": 12,
    }

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        # Posters share a department with prints, sculpture with crafts.
        word = spec.kind if spec.kind in ("poster", "sculpture") else ""
        params: dict[str, Any] = {"q": " ".join(w for w in (spec.style.strip(), word) if w) or "*"}
        if spec.kind in self.departments:
            params["departmentId"] = self.departments[spec.kind]
        if spec.year_from is not None or spec.year_to is not None:
            # The Met wants both ends of the range.
            params["dateBegin"] = spec.year_from if spec.year_from is not None else -5000
            params["dateEnd"] = spec.year_to if spec.year_to is not None else 2100
        if spec.highlight:
            params["isHighlight"] = "true"
        return self._search({**params, "isPublicDomain": "true"}, limit, page)

    def _search(self, params: dict[str, Any], limit: int, page: int) -> tuple[int, list[Item]]:
        resp = self.http.get(
            f"{self.api}/v1.1/search",
            params={**params, "hasImages": "true", "limit": limit, "offset": (page - 1) * limit},
        )
        resp.raise_for_status()
        body = resp.json()
        items = []
        for object_id in body.get("objectIDs") or []:
            item = self.fetch(str(object_id))
            if item is not None:
                items.append(item)
        return int(body.get("total", len(items))), items

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(f"{self.api}/v1/objects/{source_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(resp.json())


class WikimediaCommons(Museum):
    """Public-domain files on Wikimedia Commons, used mainly for Polish art.

    ``query`` is either free text or ``Category:<name>`` (e.g.
    ``Category:Paintings by Józef Chełmoński``), which is far more precise.
    Note: Commons rate-limits datacenter IPs; from a home network it is fine.
    """

    key = "wmc"
    name = "Wikimedia Commons"
    page_size = 50
    api = "https://commons.wikimedia.org/w/api.php"
    meta = "ObjectName|Artist|DateTimeOriginal|LicenseShortName|ImageDescription|Credit|Categories"
    #: Categories that mark a file as someone's photograph rather than a
    #: reproduction of a work of art.
    snapshot = re.compile(
        r"photographs taken on|taken with|photographs by|photos by|self-published work|"
        r"uploaded with|files by user|images by user|quality images|valued images",
        re.IGNORECASE,
    )
    #: Categories that mark a file as a copy of a painting from a library or
    #: an archive: plates of albums, pages of books and magazines, slides and
    #: postcards, mostly black and white. (Prints and drawings from the same
    #: libraries are originals, so this only applies to paintings.)
    printed_copy = re.compile(
        r"files from polona|national library (?:in|of) warsaw|biblioteka narodowa|"
        r"glass slides|lantern slides|postcards|pocztówk|scans? of books|"
        r"internet archive book images|album reprodukcji|"
        r"reproductions of paintings|tygodnik ilustrowany|kłosy|biesiada literacka|wędrowiec|"
        r"gartenlaube",
        re.IGNORECASE,
    )
    #: Category queries whose works are not paintings, and what they are.
    category_kinds: ClassVar[dict[str, str]] = {"Drawings": "Drawing", "Prints": "Print"}

    def _params(self, **extra: Any) -> dict[str, Any]:
        return {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            # Commons serves (and rate-limits by) a fixed set of widths.
            "iiurlwidth": 500,
            "iiextmetadatafilter": self.meta,
            "iiextmetadatalanguage": "pl",
            **extra,
        }

    @staticmethod
    def _raw(info: dict[str, Any], key: str) -> str:
        return str(info.get("extmetadata", {}).get(key, {}).get("value", ""))

    def _meta(self, info: dict[str, Any], key: str) -> str:
        return strip_html(self._raw(info, key))

    def _text(self, info: dict[str, Any], key: str, *, title: bool = False) -> str:
        """Rendered wikitext in one language, without the hidden QuickStatements."""
        return commons_html(self._raw(info, key), title=title)

    def _map(
        self, page: dict[str, Any], artist_hint: str = "", classification: str = "Painting"
    ) -> Item | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        categories = self._meta(info, "Categories")
        if self.snapshot.search(categories):
            return None
        if classification == "Painting" and self.printed_copy.search(categories):
            return None
        licence = self._meta(info, "LicenseShortName")
        public = "public domain" in licence.casefold() or "cc0" in licence.casefold()
        # Everything on Commons is freely licensed; attribution is kept in ``credit``.
        if not public and not (self.private_use and licence):
            return None
        title = self._text(info, "ObjectName", title=True) or re.sub(
            r"^File:|\.[a-zA-Z]+$", "", page.get("title", "")
        )
        image_url = str(info.get("url", ""))
        if (ext := extension(image_url)) and ext not in WEB_IMAGES:
            # SVG drawings, TIFF, PDF and DjVu scans: Commons' rendered copy.
            rendition = commons_rendition(image_url, 3840, info.get("width"))
            if not rendition and ext in VECTOR:
                return None
            image_url = rendition or image_url
        date_text = self._text(info, "DateTimeOriginal")
        artist = artist_hint or self._meta(info, "Artist").split("\n")[0]
        return self._item(
            str(page["pageid"]),
            title=title,
            artist=artist,
            date_text=date_text[:40],
            year=commons_year(self._meta(info, "DateTimeOriginal")),
            classification=classification,
            license=licence,
            credit=self._meta(info, "Credit")[:200],
            url=info.get("descriptionurl", ""),
            description=self._text(info, "ImageDescription")[:2000],
            image_url=image_url,
            thumb_url=info.get("thumburl") or image_url,
            width=info.get("width"),
            height=info.get("height"),
        )

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        artist_hint = ""
        classification = "Painting"
        offset = (page - 1) * limit
        if query.startswith("Category:"):
            if by := re.match(r"^Category:(Paintings|Works|Drawings|Prints) by (.+)", query):
                artist_hint = by.group(2)
                classification = self.category_kinds.get(by.group(1), classification)
            body = self._category_page(query, limit, offset)
        else:
            resp = self.http.get(
                self.api,
                params=self._params(
                    generator="search",
                    # Only files described as works of art ({{Artwork}},
                    # {{Painting}}): free text alone finds mostly photographs.
                    gsrsearch=f"{query} filetype:bitmap hastemplate:Artwork",
                    gsrnamespace=6,
                    gsrlimit=limit,
                    gsroffset=offset,
                ),
            )
            resp.raise_for_status()
            body = resp.json()
        pages = body.get("query", {}).get("pages", {})
        items = [i for p in pages.values() if (i := self._map(p, artist_hint, classification))]
        # Commons gives no total; claim one more page while it says there is one.
        total = offset + len(pages) + (limit if "continue" in body else 0)
        return total, items

    def _category_page(self, category: str, limit: int, offset: int) -> dict[str, Any]:
        """Category members ``offset:offset+limit``; categories page by token only."""
        cont: dict[str, Any] = {}
        skipped = 0
        while True:
            want = limit if skipped >= offset else min(self.page_size, offset - skipped)
            resp = self.http.get(
                self.api,
                params=self._params(
                    generator="categorymembers",
                    gcmtitle=category,
                    gcmtype="file",
                    gcmlimit=want,
                    **cont,
                ),
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
            if skipped >= offset or "continue" not in body:
                return body if skipped >= offset else {}
            skipped += want
            cont = body["continue"]

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(self.api, params=self._params(pageids=source_id))
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        page = pages.get(source_id)
        return self._map(page) if page else None


class Rijksmuseum(Museum):
    """Rijksmuseum's Linked Art API (no key needed).

    The search only matches whole fields, so plain text is tried as a creator,
    then as a title. ``creator=Johannes Vermeer&type=painting`` passes the
    search parameters as they are.
    """

    key = "rijks"
    name = "Rijksmuseum"
    api = "https://data.rijksmuseum.nl/search/collection"
    english = "http://vocab.getty.edu/aat/300388277"
    open_licences: ClassVar[dict[str, str]] = {
        "https://creativecommons.org/publicdomain/mark/1.0/": "Public Domain Mark 1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/": "CC0 1.0",
    }
    # Getty AAT types of the ``referred_to_by`` statements we read.
    medium_type = "http://vocab.getty.edu/aat/300435429"
    description_type = "http://vocab.getty.edu/aat/300435452"
    credit_type = "http://vocab.getty.edu/aat/300026687"

    @staticmethod
    def _types(node: dict[str, Any]) -> set[str]:
        return {c.get("id", "") for c in node.get("classified_as") or []}

    def _is_english(self, node: dict[str, Any]) -> bool:
        return any(lang.get("id") == self.english for lang in node.get("language") or [])

    def _text(self, nodes: list[dict[str, Any]]) -> str:
        """The English content among ``nodes`` (any language as a fallback)."""
        texts = [n for n in nodes if n.get("content")]
        english = [n for n in texts if self._is_english(n)]
        return str((english or texts)[0]["content"]) if texts else ""

    def _statement(self, d: dict[str, Any], aat: str) -> str:
        return self._text([r for r in d.get("referred_to_by") or [] if aat in self._types(r)])

    @staticmethod
    def _notation(node: dict[str, Any]) -> str:
        # Either language-tagged values or plain strings.
        values = [v if isinstance(v, dict) else {"@value": v} for v in node.get("notation") or []]
        english = [v for v in values if v.get("@language") == "en"]
        return str((english or values or [{}])[0].get("@value", ""))

    def _image(self, d: dict[str, Any]) -> tuple[str, str]:
        """IIIF base of the public-domain image and its licence, if any."""
        for subject in d.get("subject_of") or []:
            for carrier in subject.get("digitally_carried_by") or []:
                rights = [r.get("content", "") for r in carrier.get("referred_to_by") or []]
                licence = next(
                    (self.open_licences[r] for r in rights if r in self.open_licences), ""
                )
                for point in carrier.get("access_point") or []:
                    url = point.get("id", "")
                    if licence and "iiif" in url:
                        return re.sub(r"/full/.*$", "", url), licence
        return "", ""

    def _page_url(self, d: dict[str, Any]) -> str:
        for subject in d.get("subject_of") or []:
            for carrier in subject.get("digitally_carried_by") or []:
                if carrier.get("format") == "text/html":
                    for point in carrier.get("access_point") or []:
                        if point.get("id"):
                            return str(point["id"])
        return str(d.get("id", ""))

    def _map(self, d: dict[str, Any]) -> Item | None:
        iiif, licence = self._image(d)
        if not iiif:
            return None
        names = [n for n in d.get("identified_by") or [] if n.get("type") == "Name"]
        production = d.get("produced_by") or {}
        makers = [
            agent
            for part in [production, *(production.get("part") or [])]
            for agent in part.get("carried_out_by") or []
        ]
        timespan = production.get("timespan") or {}
        if isinstance(timespan, list):  # some records give several spans
            timespan = timespan[0] if timespan else {}
        year_match = re.match(r"(\d{4})", timespan.get("begin_of_the_begin", ""))
        classes = d.get("classified_as") or []
        return self._item(
            str(d["id"]).rsplit("/", 1)[-1],
            title=self._text(names),
            artist=self._notation(makers[0])
            if makers
            else self._text(production.get("referred_to_by") or []),
            date_text=self._text(timespan.get("identified_by") or []),
            year=int(year_match.group(1)) if year_match else None,
            medium=self._statement(d, self.medium_type),
            classification=self._notation(classes[0]) if classes else "",
            credit=self._statement(d, self.credit_type),
            license=licence,
            url=self._page_url(d),
            description=self._statement(d, self.description_type),
            image_url=f"{iiif}/full/max/0/default.jpg",
            thumb_url=f"{iiif}/full/600,/0/default.jpg",
        )

    def _ids(self, params: dict[str, str], skip: int, limit: int) -> tuple[int, list[str]]:
        """Object ids ``skip:skip+limit`` of a search; pages of 100 follow tokens."""
        url: str | None = self.api
        query: dict[str, str] | None = {**params, "imageAvailable": "true"}
        ids: list[str] = []
        total = 0
        while url and len(ids) < skip + limit:
            resp = self.http.get(url, params=query)
            resp.raise_for_status()
            body = resp.json()
            total = int(body.get("partOf", {}).get("totalItems") or 0)
            ids += [o["id"] for o in body.get("orderedItems") or [] if o.get("id")]
            url, query = (body.get("next") or {}).get("id"), None
        return total, ids[skip : skip + limit]

    def _discovery_params(self, spec: Discovery, decade: int | None = None) -> dict[str, str]:
        params: dict[str, str] = {"type": spec.kind if spec.kind != "any" else "painting"}
        if decade is not None:
            params["creationDate"] = f"{decade // 10:03d}*"  # dates match by prefix
        return params

    def _decades(self, spec: Discovery) -> list[int | None]:
        if spec.year_from is None and spec.year_to is None:
            return [None]
        first = (spec.year_from if spec.year_from is not None else 1000) // 10 * 10
        last = spec.year_to if spec.year_to is not None else 2000
        return list(range(first, last + 1, 10))

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.style.strip() or spec.kind == "decorative":
            return 0, []  # no field for styles or movements, no one type of crafts
        decade = self._decades(spec)[0]
        total, ids = self._ids(self._discovery_params(spec, decade), (page - 1) * limit, limit)
        return total, self._objects(ids)

    def random_draw(self, spec: Discovery, rng: random.Random) -> Iterator[Item]:
        """Decades in random order (the API has no date ranges), then the
        first results of each, shuffled."""
        if spec.highlight or spec.style.strip() or spec.kind == "decorative":
            return
        decades = self._decades(spec)
        rng.shuffle(decades)
        for decade in decades:
            _, ids = self._ids(self._discovery_params(spec, decade), 0, 200)
            rng.shuffle(ids)
            for start in range(0, len(ids), 10):
                yield from self._objects(ids[start : start + 10])

    def _objects(self, ids: list[str]) -> list[Item]:
        return [i for object_id in ids if (i := self.fetch(object_id.rsplit("/", 1)[-1]))]

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        query = query.strip()
        if "=" in query:
            attempts = [dict(p.split("=", 1) for p in query.split("&") if "=" in p)]
        else:
            attempts = [{"creator": query}, {"title": query}]
        total, ids = 0, list[str]()
        for params in attempts:
            total, ids = self._ids(params, (page - 1) * limit, limit)
            if total:
                break
        items = []
        for object_id in ids:
            item = self.fetch(object_id.rsplit("/", 1)[-1])
            if item is not None:
                items.append(item)
        return total, items

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(
            f"https://id.rijksmuseum.nl/{source_id}",
            headers={"Accept": "application/ld+json"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(resp.json())


def _first(values: Any) -> str:
    """The first string of an API list field (Europeana wraps most in lists)."""
    if isinstance(values, list):
        return str(values[0]) if values else ""
    return str(values or "")


def _person(name: str) -> str:
    """ "Matisse, Henri (1869-1954)" -> "Henri Matisse"."""
    name = re.sub(r"(?:\s*\([^)]*\))+\s*$", "", name).strip()
    last, comma, first = name.partition(",")
    if comma and first.strip() and "," not in first and not re.search(r"\d", name):
        return f"{first.strip()} {last.strip()}"
    return name


def _bare(name: str) -> str:
    """A name without the roles and dates in brackets: "Mondrian, Piet
    (Künstler/in)" -> "Mondrian, Piet"."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


#: Creative Commons licence URLs: "creativecommons.org/licenses/by-sa/4.0/".
CC_LICENCE = re.compile(r"creativecommons\.org/licenses/([a-z-]+)/(\d\.\d)")
PUBLIC_MARKS = {
    "creativecommons.org/publicdomain/mark/": "Public Domain Mark 1.0",
    "creativecommons.org/publicdomain/zero/": "CC0 1.0",
}


#: Start of the licence of works let in only while the 70-year term is
#: switched off for tests; they leave the library with the switch.
TEST_LICENCE = "Tylko do testów"


def cc_name(code: str, version: str) -> str:
    return f"CC {code.upper()} {version}"


#: Hosts of Europeana's providers that answer programs with a "verify you
#: are human" page, Europeana's own media proxy included: their works'
#: originals can never be had (2026-10: the Belvedere's collection, files
#: on Dropbox: Orsay, Alte Pinakothek, Nationalmuseum).
EUROPEANA_UNREACHABLE = frozenset({"sammlung.belvedere.at", "www.dropbox.com", "dropbox.com"})


def europeana_mirrors(item: Item) -> list[str]:
    """Europeana's media proxy for the original: Europeana's servers fetch
    the provider's file, which some providers (the Mauritshuis, behind
    Cloudflare) refuse to send to programs like this one."""
    if item.source != "europeana" or not item.image_url:
        return []
    record = item.source_id.replace("~", "/")
    return [f"https://proxy.europeana.eu/{record}?view={quote(item.image_url, safe='')}"]


class Europeana(Museum):
    """Europe's cultural heritage portal, Polish collections included.

    Besides works marked free it takes those whose authors died more than 70
    years ago (the EU rule): many providers still mark Kandinsky or Matisse
    "in copyright". With ``Access.ignore_term`` (tests only) any author's
    death will do. Without a key of its own (``FRAME_EUROPEANA_KEY``, free
    at europeana.eu) it uses the shared demo key.
    """

    key = "europeana"
    name = "Europeana"
    api = "https://api.europeana.eu/record/v2/search.json"
    page_size = 100
    #: Deeper result pages need a cursor.
    random_depth = 1000
    #: ``what`` (object type) values; "any" stays with artworks, not photos
    #: of buildings or film stills.
    whats: ClassVar[dict[str, str]] = {
        "any": "what:(painting OR drawing OR print OR poster)",
        "painting": "what:painting",
        "print": "what:print",
        "drawing": "what:drawing",
        "poster": "what:poster",
    }
    #: Types of photographs and copies of works: art history slides (KU
    #: Leuven, Marburg), reproductions, postcards.
    copies = re.compile(
        r"\b(slides?|transparenc\w*|photograph(?:s|y)?|reproduc\w*|postcards?)\b", re.IGNORECASE
    )
    #: Types of objects that are no pictures: stamps, coins, medals,
    #: banknotes and the post's envelopes and proofs. Providers mark them
    #: "print" too.
    objects = re.compile(
        r"\b(stamps?|postage|postal|philatel\w*|postmarks?|envelopes?|coins?|medals?|"
        r"bank ?notes?|numismat\w*)\b",
        re.IGNORECASE,
    )
    #: Aggregators of natural history, not art: OpenUp! brings botanical
    #: photos with names like "Rosa 'Claude Monet'", found by artist. The
    #: city of Girona's photo archive calls its photographs paintings and
    #: posters (see ``vocabulary.PHOTO_ARCHIVES``). Athens' Philatelic
    #: Postal Museum calls its stamps, first-day covers and proofs prints:
    #: nearly every print after 1950 (see ``vocabulary.NOT_ART_PROVIDERS``).
    not_art = (
        '-PROVIDER:"OpenUp!"',
        '-DATA_PROVIDER:"Ajuntament de Girona"',
        '-DATA_PROVIDER:"Philatelic Postal Museum"',
        '-what:(stamp OR "postage stamp" OR "postal services" OR coin OR coins OR medal '
        "OR medals OR banknote OR banknotes)",
    )

    def _death(self, d: dict[str, Any]) -> int | None:
        """When the work's last author died, if every author is known."""
        life = self.access.life
        if life is None:
            return None
        creators = [str(c) for c in d.get("dcCreator") or []]
        refs = [c for c in creators if EUROPEANA_AGENT.match(c) or WIKIDATA_ENTITY.match(c)]
        if not refs:
            names = [c for c in creators if not c.startswith("http")][:1]
            # "Kandinsky, Wassily (1866-1944) (Künstler/Hersteller)"
            if names and (died := death_in_name(names[0])) is not None:
                return died
            refs = [_bare(n) for n in names]
        years = [life.death_year(self.http, ref) for ref in refs if ref]
        if not years or any(y is None for y in years):
            return None
        return max(y for y in years if y is not None)

    def _licence(self, d: dict[str, Any]) -> str:
        """What makes the work free to show here; empty when nothing does."""
        rights = _first(d.get("rights"))
        for mark, label in PUBLIC_MARKS.items():
            if mark in rights:
                return label
        if (cc := CC_LICENCE.search(rights)) and self.private_use:
            return cc_name(*cc.groups())
        # A licence on the photograph of a free work does not make the
        # work less free: Kandinsky's paintings often come as CC BY-SA.
        died = self._death(d)
        if died is not None and free_in_eu(died):
            return f"Domena publiczna w UE (twórca zm. {died})"
        if died is not None and self.access.ignore_term:
            return f"{TEST_LICENCE}, w UE wolne od {died + TERM_YEARS + 1} (twórca zm. {died})"
        return ""

    def _map(self, d: dict[str, Any]) -> Item | None:
        image = _first(d.get("edmIsShownBy"))
        preview = _first(d.get("edmPreview"))
        if not image or not preview or not d.get("id"):
            return None
        if (urlsplit(image).hostname or "") in EUROPEANA_UNREACHABLE:
            return None
        kinds = [t for t in (d.get("dcTypeLangAware") or {}).get("en") or [] if "://" not in t]
        # Types often come as vocabulary links only; their labels are among
        # the record's concepts ("slides (photographs)").
        concepts = (d.get("edmConceptPrefLabelLangAware") or {}).get("en") or []
        if any(self.copies.search(str(k)) for k in [*kinds, *concepts]):
            return None
        if any(self.objects.search(str(k)) for k in [*kinds, *concepts]):
            return None
        licence = self._licence(d)
        if not licence:
            return None
        if "/thumbnail/" in preview and "size=" not in preview:
            preview += "&size=w400"
        # Labels by language; "def" mixes in authority URIs.
        labels = d.get("dcCreatorLangAware") or {}
        names = [
            str(n)
            for lang in ("en", "pl", "def", *labels)
            for n in labels.get(lang) or []
            if "://" not in str(n)
        ] or [str(c) for c in d.get("dcCreator") or [] if "://" not in str(c)]
        year = _first(d.get("year"))
        record = str(d["id"])
        return self._item(
            record.strip("/").replace("/", "~"),
            title=_first(d.get("title")),
            artist=_person(names[0]) if names else "",
            date_text=year,
            year=int(year) if year.isdigit() else None,
            classification=kinds[0] if kinds else "",
            credit=_first(d.get("dataProvider")),
            license=licence,
            url=_first(d.get("guid")) or f"https://www.europeana.eu/item{record}",
            description=strip_html(_first(d.get("dcDescription")))[:2000],
            image_url=image,
            thumb_url=preview,
        )

    def _get(self, query: str, qf: list[str], limit: int, page: int) -> tuple[int, list[Item]]:
        start = (page - 1) * limit + 1
        if start + limit > self.random_depth + 1:
            return 0, []
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("wskey", self.access.europeana_key),
            ("query", query.strip() or "*"),
            ("qf", "TYPE:IMAGE"),
            # Tier 1 is anything from 0.1 megapixel: thumbnails, not pictures.
            ("qf", "contentTier:(2 OR 3 OR 4)"),
            *(("qf", q) for q in self.not_art),
            *(("qf", q) for q in qf),
            ("media", "true"),
            ("thumbnail", "true"),
            ("profile", "rich"),
            ("rows", limit),
            ("start", start),
        ]
        resp = self.http.get(self.api, params=params)
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("items") or [] if (i := self._map(d))]
        return int(body.get("totalResults") or 0), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        # Works of art only: free text alone finds medals, stamps, horse
        # collars and photos of buildings, and buries the paintings.
        return self._get(query, [self.whats["any"]], limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.kind not in self.whats:
            # Its photographs are mostly records of places and events, its
            # "sculpture" mostly shoes and jewellery.
            return 0, []
        qf = [self.whats[spec.kind]]
        if spec.year_from is not None or spec.year_to is not None:
            low = "*" if spec.year_from is None else spec.year_from
            high = "*" if spec.year_to is None else spec.year_to
            qf.append(f"YEAR:[{low} TO {high}]")
        elif not spec.style.strip():
            # Nothing to narrow by: most images are still in copyright, so ask
            # for openly licensed ones or the pages come back empty.
            free = "*publicdomain*"
            if self.private_use:
                free = f"({free} OR *creativecommons.org/licenses*)"
            qf.append(f"RIGHTS:{free}")
        return self._get(spec.style, qf, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        record = "/" + source_id.replace("~", "/")
        _, items = self._get(f'europeana_id:"{record}"', [], 1, 1)
        return items[0] if items else None


class Openverse(Museum):
    """Openly licensed images (Flickr, Wikimedia Commons, museums) via Openverse.

    Without ``private_use`` only CC0 and public-domain works; with it every
    Creative Commons licence, credited on the frame. Anonymous use allows 20
    requests a minute, 200 a day and 240 results a search; app credentials
    (``FRAME_OPENVERSE_CLIENT_ID`` and ``_SECRET``) lift that.
    """

    key = "openverse"
    name = "Openverse"
    api = "https://api.openverse.org/v1"
    page_size = 20  # the most an anonymous page may hold
    random_depth = 240
    public: ClassVar[tuple[str, ...]] = ("cc0", "pdm")
    licensed: ClassVar[tuple[str, ...]] = (
        "by",
        "by-sa",
        "by-nc",
        "by-nd",
        "by-nc-sa",
        "by-nc-nd",
    )
    categories: ClassVar[dict[str, str]] = {
        "any": "digitized_artwork",
        "painting": "digitized_artwork",
        "print": "illustration",
        "drawing": "illustration",
        "poster": "illustration",
    }
    _tokens: ClassVar[dict[str, tuple[str, float]]] = {}
    _token_lock: ClassVar[threading.Lock] = threading.Lock()

    def _licences(self) -> tuple[str, ...]:
        return (*self.public, *self.licensed) if self.private_use else self.public

    def _headers(self) -> dict[str, str]:
        if not self.access.openverse_app:
            return {}
        client_id, secret = self.access.openverse_app
        with self._token_lock:
            token, expires = self._tokens.get(client_id, ("", 0.0))
            if time.time() > expires - 60:
                resp = self.http.post(
                    f"{self.api}/auth_tokens/token/",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": secret,
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                token = str(body["access_token"])
                expires = time.time() + float(body.get("expires_in") or 3600)
                self._tokens[client_id] = (token, expires)
        return {"Authorization": f"Bearer {token}"}

    def _map(self, d: dict[str, Any]) -> Item | None:
        code = str(d.get("license") or "")
        if code not in self._licences() or not d.get("url") or not d.get("id"):
            return None
        version = str(d.get("license_version") or "")
        licence = {"cc0": "CC0", "pdm": "Public Domain Mark"}.get(code) or f"CC {code.upper()}"
        image_url, thumb_url = str(d["url"]), str(d.get("thumbnail") or d["url"])
        kind = str(d.get("filetype") or extension(image_url)).casefold()
        if kind in VECTOR:
            # Neither the app nor Openverse's thumbnailer reads these; Commons
            # renders its own as PNG, others are left out.
            original, width = image_url, d.get("width")
            image_url = commons_rendition(original, 3840, width)
            thumb_url = commons_rendition(original, 500, width)
            if not image_url:
                return None
        attribution = str(d.get("attribution") or "").split(". To view", 1)[0]
        tags = [
            t["name"] for t in d.get("tags") or [] if t.get("name") and t.get("accuracy") is None
        ]
        return self._item(
            str(d["id"]),
            title=str(d.get("title") or ""),
            artist=str(d.get("creator") or ""),
            classification=str(d.get("category") or ""),
            subjects=tags[:12],
            credit=attribution[:300],
            license=f"{licence} {version}".strip(),
            url=str(d.get("foreign_landing_url") or ""),
            image_url=image_url,
            thumb_url=thumb_url,
            width=d.get("width"),
            height=d.get("height"),
        )

    def _get(self, params: dict[str, Any], limit: int, page: int) -> tuple[int, list[Item]]:
        size = min(limit, self.page_size)
        if page * size > self.random_depth and not self.access.openverse_app:
            return 0, []
        resp = self.http.get(
            f"{self.api}/images/",
            params={
                **params,
                "license": ",".join(self._licences()),
                "page_size": size,
                "page": page,
                "mature": "false",
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("results") or [] if (i := self._map(d))]
        return int(body.get("result_count") or 0), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        # Art only: without a category most of Openverse is Flickr photos.
        return self._get({"q": query, "category": "digitized_artwork,illustration"}, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.year_from is not None or spec.year_to is not None:
            return 0, []  # no dates to filter by
        if spec.kind not in self.categories:
            return 0, []  # its photographs are Flickr's, not museums'
        params = {"category": self.categories[spec.kind]}
        words = [spec.style.strip(), "poster" if spec.kind == "poster" else ""]
        if text := " ".join(w for w in words if w):
            params["q"] = text
        return self._get(params, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(f"{self.api}/images/{source_id}/", headers=self._headers())
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(resp.json())


class StatensMuseum(Museum):
    """Statens Museum for Kunst, Copenhagen: an open API without a key.
    Only works in the public domain (the Danish Golden Age, Hammershøi, the
    Skagen painters); answers in English where it has English."""

    key = "smk"
    name = "Statens Museum for Kunst"
    api = "https://api.smk.dk/api/v1"
    #: Works offered: public domain with a picture.
    filters = "[public_domain:true],[has_image:true]"
    #: ``object_names`` with ``lang=en``; other kinds are not drawn.
    names: ClassVar[dict[str, str]] = {
        "painting": "painting",
        "print": "print",
        "drawing": "drawing",
    }
    #: The title in English, when there is one.
    english = "engelsk"

    def _map(self, d: dict[str, Any]) -> Item | None:
        iiif = d.get("image_iiif_id")
        if not d.get("public_domain") or not iiif or not d.get("object_number"):
            return None
        titles = [t for t in d.get("titles") or [] if t.get("title")]
        english = [t for t in titles if t.get("language") == self.english]
        made = (d.get("production") or [{}])[0]
        life = [str(made.get(f"creator_date_of_{end}") or "")[:4] for end in ("birth", "death")]
        bio = ", ".join(
            p for p in (made.get("creator_nationality") or "", "–".join(life).strip("–")) if p
        )
        dates = (d.get("production_date") or [{}])[0]
        start = str(dates.get("start") or "")
        year = int(start[:4]) if start[:4].isdigit() else None
        names = d.get("object_names") or [{}]
        thumb = d.get("image_thumbnail") or ""
        thumb = (
            thumb.replace("/full/!1024,/", "/full/600,/")
            if thumb
            else f"{iiif}/full/600,/0/default.jpg"
        )
        return self._item(
            str(d["object_number"]),
            title=str((english or titles or [{"title": ""}])[0]["title"]),
            artist=str((d.get("artist") or [made.get("creator") or ""])[0]),
            artist_bio=bio,
            date_text=str(dates.get("period") or ""),
            year=year,
            medium=", ".join(d.get("techniques") or d.get("materials") or []),
            classification=str(names[0].get("name") or ""),
            styles=[],
            subjects=[],
            culture="Danish" if made.get("creator_nationality") == "Danish" else "",
            credit=self.name,
            license="Public Domain Mark 1.0",
            url=d.get("frontend_url") or "",
            description=strip_html(" ".join(d.get("content_description") or [])),
            image_url=f"{iiif}/full/!2560,2560/0/default.jpg",
            thumb_url=thumb,
            width=d.get("image_width"),
            height=d.get("image_height"),
        )

    def _get(self, params: dict[str, Any], limit: int, page: int) -> tuple[int, list[Item]]:
        resp = self.http.get(
            f"{self.api}/art/search/",
            params={**params, "lang": "en", "offset": (page - 1) * limit, "rows": limit},
        )
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("items") or [] if (i := self._map(d))]
        return int(body.get("found", len(items))), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        return self._get({"keys": query or "*", "filters": self.filters}, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.highlight or (spec.kind != "any" and spec.kind not in self.names):
            return 0, []
        filters = self.filters
        if spec.kind in self.names:
            filters += f",[object_names:{self.names[spec.kind]}]"
        params: dict[str, Any] = {"keys": spec.style.strip() or "*", "filters": filters}
        if spec.year_from is not None or spec.year_to is not None:
            start = spec.year_from if spec.year_from is not None else 1
            end = spec.year_to if spec.year_to is not None else 2100
            params["range"] = (
                f"[production_dates_start:{{{start:04d}-01-01T00:00:00.000Z;"
                f"{end:04d}-12-31T23:59:59.999Z}}]"
            )
        return self._get(params, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(f"{self.api}/art/", params={"object_number": source_id, "lang": "en"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        found = resp.json().get("items") or []
        return self._map(found[0]) if found else None


class WikiArt(Museum):
    """WikiArt, only to test the panel with newer art.

    WikiArt shows works still under copyright without licences, so it is no
    lawful source for keeping copies: it is offered only while switched on in
    the app, never feeds Suggestions, and its works leave the library when it
    is switched off again.
    """

    key = "wikiart"
    name = "WikiArt"
    testing = True
    api = "https://www.wikiart.org/en/api/2"
    #: WikiArt's own pages hold 60 works.
    page_size = 60
    licence = "Tylko do testów ramki (WikiArt)"
    #: (search, page) -> token that asks for that page.
    _tokens: ClassVar[dict[tuple[str, int], str]] = {}

    def _map(self, d: dict[str, Any]) -> Item | None:
        image = str(d.get("image") or "")
        if not image or not d.get("id"):
            return None
        year = d.get("completitionYear")
        artist_url = str(d.get("artistUrl") or "")
        page = f"https://www.wikiart.org/en/{artist_url}"
        if d.get("url"):
            page += f"/{d['url']}"
        return self._item(
            str(d["id"]),
            title=str(d.get("title") or ""),
            artist=str(d.get("artistName") or ""),
            date_text=str(year or ""),
            year=year if isinstance(year, int) else None,
            classification="Painting",
            styles=list(d.get("styles") or []),
            subjects=list(d.get("genres") or []),
            license=self.licence,
            url=page,
            # "...jpg!Large.jpg" is a resized copy; without the suffix, the original.
            image_url=re.sub(r"![^/]*$", "", image),
            thumb_url=image,
            width=d.get("width"),
            height=d.get("height"),
        )

    def _page(self, term: str, number: int) -> tuple[list[dict[str, Any]], bool]:
        """WikiArt's ``number``-th page of results (from 1) and whether more
        follow; without a ``term``, its most viewed paintings."""
        params: dict[str, str] = {"term": term} if term else {}
        if number > 1:
            token = self._tokens.get((term, number))
            if token is None:
                _, more = self._page(term, number - 1)
                token = self._tokens.get((term, number))
                if not more or token is None:
                    return [], False
            params["paginationToken"] = token
        endpoint = "PaintingSearch" if term else "MostViewedPaintings"
        resp = self.http.get(f"{self.api}/{endpoint}", params=params)
        resp.raise_for_status()
        body = resp.json()
        more = bool(body.get("hasMore")) and bool(body.get("paginationToken"))
        if more:
            if len(self._tokens) > 500:
                self._tokens.clear()
            # Tokens come URL-encoded; sent encoded again, WikiArt fails.
            self._tokens[(term, number + 1)] = unquote(str(body["paginationToken"]))
        return list(body.get("data") or []), more

    def _results(self, term: str, limit: int, page: int) -> tuple[int, list[Item]]:
        start = (page - 1) * limit
        first = start // self.page_size + 1
        last = (start + limit - 1) // self.page_size + 1
        found: list[dict[str, Any]] = []
        more = False
        for number in range(first, last + 1):
            rows, more = self._page(term, number)
            found += rows
            if not more:
                break
        skip = start - (first - 1) * self.page_size
        items = [i for d in found[skip : skip + limit] if (i := self._map(d))]
        seen = (first - 1) * self.page_size + len(found)
        return (start + limit * 2 if more else seen), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        term = query.strip()
        return self._results(term, limit, page) if term else (0, [])

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        """Works of a style; with nothing asked, the most viewed paintings."""
        return self._results(spec.style.strip(), limit, page)

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(f"{self.api}/Painting", params={"id": source_id})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body = resp.json()
        return self._map(body) if isinstance(body, dict) else None


MUSEUMS: dict[str, type[Museum]] = {
    m.key: m
    for m in (
        ArtInstituteChicago,
        ClevelandMuseum,
        MetropolitanMuseum,
        Rijksmuseum,
        WikimediaCommons,
        Europeana,
        Openverse,
        StatensMuseum,
        WikiArt,
    )
}


def available(access: Access) -> dict[str, type[Museum]]:
    """The sources on offer: test-only ones just while switched on."""
    return {k: m for k, m in MUSEUMS.items() if not m.testing or access.wikiart}


def museum(key: str, http: httpx.Client, access: Access | bool = False) -> Museum:
    if isinstance(access, bool):
        access = Access(private_use=access)
    sources = available(access)
    if key not in sources:
        raise KeyError(f"unknown museum {key!r}; choose from {sorted(sources)}")
    return sources[key](http, access=access)
