"""Open-access museum collections: search and metadata import.

Only public-domain / CC0 works are returned. Every museum maps its records
onto :class:`Item` (without colours; those are computed from the thumbnail
at import time).
"""

from __future__ import annotations

import html
import random
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

import httpx

from .commons import commons_html, commons_year
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
        timeout=30,
        follow_redirects=True,
    )


Kind = Literal["any", "painting", "print", "drawing", "poster"]


@dataclass(frozen=True)
class Discovery:
    """What to draw from a collection at random; every field is optional."""

    year_from: int | None = None
    year_to: int | None = None
    #: Free text matched against styles and movements, e.g. "Impressionism".
    style: str = ""
    kind: Kind = "any"

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

    def __init__(self, http: httpx.Client, private_use: bool = False) -> None:
        self.http = http
        self.private_use = private_use

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
        size = min(self.page_size, 24)
        total, _ = self.discover(spec, limit=1, page=1)
        pages = list(range(1, -(-min(total, self.random_depth) // size) + 1))
        rng.shuffle(pages)
        for page in pages:
            _, items = self.discover(spec, limit=size, page=page)
            rng.shuffle(items)
            yield from items

    def _item(self, source_id: str, **fields: Any) -> Item:
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
            image_url=f"{self.iiif}/{d['image_id']}/full/1686,/0/default.jpg",
            thumb_url=f"{self.iiif}/{d['image_id']}/full/600,/0/default.jpg",
            width=thumb.get("width"),
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
    }

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
            description="",
            image_url=d.get("primaryImage") or d["primaryImageSmall"],
            thumb_url=d["primaryImageSmall"],
        )

    page_size = 24  # every result is one more request

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        return self._search({"q": query}, limit, page)

    # Departments: European Paintings; Drawings and Prints.
    departments: ClassVar[dict[str, int]] = {"painting": 11, "print": 9, "drawing": 9, "poster": 9}

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        words = [spec.style.strip(), "poster" if spec.kind == "poster" else ""]
        params: dict[str, Any] = {"q": " ".join(w for w in words if w) or "*"}
        if spec.kind in self.departments:
            params["departmentId"] = self.departments[spec.kind]
        if spec.year_from is not None or spec.year_to is not None:
            # The Met wants both ends of the range.
            params["dateBegin"] = spec.year_from if spec.year_from is not None else -5000
            params["dateEnd"] = spec.year_to if spec.year_to is not None else 2100
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
    meta = "ObjectName|Artist|DateTimeOriginal|LicenseShortName|ImageDescription|Credit"

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

    def _map(self, page: dict[str, Any], artist_hint: str = "") -> Item | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        licence = self._meta(info, "LicenseShortName")
        public = "public domain" in licence.casefold() or "cc0" in licence.casefold()
        # Everything on Commons is freely licensed; attribution is kept in ``credit``.
        if not public and not (self.private_use and licence):
            return None
        title = self._text(info, "ObjectName", title=True) or re.sub(
            r"^File:|\.[a-zA-Z]+$", "", page.get("title", "")
        )
        date_text = self._text(info, "DateTimeOriginal")
        artist = artist_hint or self._meta(info, "Artist").split("\n")[0]
        return self._item(
            str(page["pageid"]),
            title=title,
            artist=artist,
            date_text=date_text[:40],
            year=commons_year(self._meta(info, "DateTimeOriginal")),
            classification="Painting",
            license=licence,
            credit=self._meta(info, "Credit")[:200],
            url=info.get("descriptionurl", ""),
            description=self._text(info, "ImageDescription")[:2000],
            image_url=info.get("url", ""),
            thumb_url=info.get("thumburl") or info.get("url", ""),
            width=info.get("width"),
            height=info.get("height"),
        )

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        artist_hint = ""
        offset = (page - 1) * limit
        if query.startswith("Category:"):
            artist_hint = re.sub(r"^Category:(Paintings|Works|Drawings|Prints) by ", "", query)
            if artist_hint == query:
                artist_hint = ""
            body = self._category_page(query, limit, offset)
        else:
            resp = self.http.get(
                self.api,
                params=self._params(
                    generator="search",
                    gsrsearch=f"{query} filetype:bitmap",
                    gsrnamespace=6,
                    gsrlimit=limit,
                    gsroffset=offset,
                ),
            )
            resp.raise_for_status()
            body = resp.json()
        pages = body.get("query", {}).get("pages", {})
        items = [i for p in pages.values() if (i := self._map(p, artist_hint))]
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
        if spec.style.strip():
            return 0, []  # no field for styles or movements
        decade = self._decades(spec)[0]
        total, ids = self._ids(self._discovery_params(spec, decade), (page - 1) * limit, limit)
        return total, self._objects(ids)

    def random_draw(self, spec: Discovery, rng: random.Random) -> Iterator[Item]:
        """Decades in random order (the API has no date ranges), then the
        first results of each, shuffled."""
        if spec.style.strip():
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


MUSEUMS: dict[str, type[Museum]] = {
    m.key: m
    for m in (
        ArtInstituteChicago,
        ClevelandMuseum,
        MetropolitanMuseum,
        Rijksmuseum,
        WikimediaCommons,
    )
}


def museum(key: str, http: httpx.Client, private_use: bool = False) -> Museum:
    if key not in MUSEUMS:
        raise KeyError(f"unknown museum {key!r}; choose from {sorted(MUSEUMS)}")
    return MUSEUMS[key](http, private_use)
