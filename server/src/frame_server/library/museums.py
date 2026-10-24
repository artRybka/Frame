"""Open-access museum collections: search and metadata import.

Only public-domain / CC0 works are returned. Every museum maps its records
onto :class:`Item` (without colours; those are computed from the thumbnail
at import time).
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

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


class Museum(ABC):
    key: str
    name: str

    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    @abstractmethod
    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        """Public-domain works matching ``query``; returns (total, items)."""

    @abstractmethod
    def fetch(self, source_id: str) -> Item | None:
        """One work by its id in the museum's collection."""

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

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        must: list[dict[str, Any]] = []
        if query.strip():
            must.append(
                {
                    "simple_query_string": {
                        "query": query,
                        "fields": list(self.search_fields),
                        "default_operator": "and",
                    }
                }
            )
        resp = self.http.post(
            f"{self.api}/artworks/search",
            json={
                "q": query,
                "limit": limit,
                "page": page,
                "fields": self.fields.split(","),
                "query": {"bool": {"must": must, "filter": [{"term": {"is_public_domain": True}}]}},
            },
        )
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

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        resp = self.http.get(
            f"{self.api}/artworks/",
            params={
                "q": query,
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

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        resp = self.http.get(
            f"{self.api}/v1.1/search",
            params={"q": query, "hasImages": "true", "limit": limit, "offset": (page - 1) * limit},
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
    api = "https://commons.wikimedia.org/w/api.php"
    meta = "ObjectName|Artist|DateTimeOriginal|LicenseShortName|ImageDescription|Credit"

    def _params(self, **extra: Any) -> dict[str, Any]:
        return {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 600,
            "iiextmetadatafilter": self.meta,
            **extra,
        }

    @staticmethod
    def _meta(info: dict[str, Any], key: str) -> str:
        return strip_html(info.get("extmetadata", {}).get(key, {}).get("value", ""))

    def _map(self, page: dict[str, Any], artist_hint: str = "") -> Item | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        licence = self._meta(info, "LicenseShortName")
        if "public domain" not in licence.casefold() and "cc0" not in licence.casefold():
            return None
        title = self._meta(info, "ObjectName") or re.sub(
            r"^File:|\.[a-zA-Z]+$", "", page.get("title", "")
        )
        date_text = self._meta(info, "DateTimeOriginal")
        year_match = re.search(r"\b(1[0-9]{3})\b", date_text)
        artist = artist_hint or self._meta(info, "Artist").split("\n")[0]
        return self._item(
            str(page["pageid"]),
            title=title,
            artist=artist,
            date_text=date_text[:40],
            year=int(year_match.group(1)) if year_match else None,
            classification="Painting",
            license=licence,
            credit=self._meta(info, "Credit")[:200],
            url=info.get("descriptionurl", ""),
            description=self._meta(info, "ImageDescription")[:2000],
            image_url=info.get("url", ""),
            thumb_url=info.get("thumburl") or info.get("url", ""),
            width=info.get("width"),
            height=info.get("height"),
        )

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        artist_hint = ""
        if query.startswith("Category:"):
            params = self._params(
                generator="categorymembers", gcmtitle=query, gcmtype="file", gcmlimit=limit
            )
            artist_hint = re.sub(r"^Category:(Paintings|Works|Drawings|Prints) by ", "", query)
            if artist_hint == query:
                artist_hint = ""
        else:
            params = self._params(
                generator="search",
                gsrsearch=f"{query} filetype:bitmap",
                gsrnamespace=6,
                gsrlimit=limit,
                gsroffset=(page - 1) * limit,
            )
        resp = self.http.get(self.api, params=params)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        items = [i for p in pages.values() if (i := self._map(p, artist_hint))]
        return len(items), items

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(self.api, params=self._params(pageids=source_id))
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        page = pages.get(source_id)
        return self._map(page) if page else None


MUSEUMS: dict[str, type[Museum]] = {
    m.key: m for m in (ArtInstituteChicago, ClevelandMuseum, MetropolitanMuseum, WikimediaCommons)
}


def museum(key: str, http: httpx.Client) -> Museum:
    if key not in MUSEUMS:
        raise KeyError(f"unknown museum {key!r}; choose from {sorted(MUSEUMS)}")
    return MUSEUMS[key](http)
