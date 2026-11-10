"""Open-access museum collections: search and metadata import.

Only works free to show are returned: public domain / CC0, public domain in
the EU (author dead for more than 70 years), and with ``private_use`` also
works under free licences, works still in copyright whose museum publishes
full pictures of them (``PRIVATE_LICENCE``) and WikiArt. Every museum maps
its records onto :class:`Item` (without colours; those are computed from the
thumbnail at import time).
"""

from __future__ import annotations

import html
import logging
import random
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal
from urllib.parse import quote, unquote, urlsplit

import httpx

from .aic import AIC_IIIF, AIC_THUMB, aic_original, aic_picture
from .commons import commons_html, commons_year, file_title
from .dumps import LOCAL_MIN, DumpIndex, local_index
from .dumps import match as dump_words
from .hosts import Resting, guard
from .lifespan import (
    EUROPEANA_AGENT,
    TERM_YEARS,
    WIKIDATA_ENTITY,
    LifeDates,
    death_in_name,
    europeana_key,
    free_in_eu,
)
from .markup import (
    VECTOR,
    WEB_IMAGES,
    clean_title,
    commons_rendition,
    extension,
    strip_artist,
)
from .met_index import INDEX as MET_INDEX
from .met_objects import met_objects
from .models import Item, ItemKind
from .records import records
from .rijks_index import local_index as rijks_local_index

log = logging.getLogger(__name__)

#: A museum text asking for an artist's works by the museum's own author
#: field (``search.museum_text``): the artist, then the other words.
_BY = re.compile(r"^@by:([^\t]*)\t(.*)$", re.DOTALL)


#: A poster's type in the languages museums write it.
_POSTER_WORD = re.compile(r"\b(poster|affiche|plakat)", re.IGNORECASE)


def by_artist(artist: str, words: str = "") -> str:
    """The text asking a museum for ``artist``'s works (with ``words``)."""
    return f"@by:{' '.join(artist.split())}\t{' '.join(words.split())}"


def asked_by(text: str) -> tuple[str, str] | None:
    """(the artist, the other words) of a :func:`by_artist` text; None for
    plain words."""
    found = _BY.match(text)
    return (found.group(1), found.group(2)) if found else None


def plain_text(text: str) -> str:
    """``text`` as plain words: a :func:`by_artist` text's words and artist."""
    found = asked_by(text)
    if found is None:
        return text
    artist, words = found
    return " ".join(w for w in (words, artist) if w)


def surname_first(artist: str) -> str:
    """ "Vilhelm Hammershøi" -> "Hammershøi, Vilhelm"; "Vincent van Gogh"
    -> "Gogh, Vincent van" (as SMK files its makers)."""
    parts = artist.split()
    if len(parts) < 2 or "," in artist:
        return artist
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


USER_AGENT = "Frame/0.2 (home e-paper art frame; +https://github.com/artRybka/Frame)"


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"</p>\s*<p>", "\n\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def client() -> httpx.Client:
    """A client for every source: our name and address in the headers
    (Wikimedia and the AIC ask for them), the shared :data:`guard`'s paces,
    rests and limits."""
    return guard.client(
        headers={"User-Agent": USER_AGENT, "AIC-User-Agent": USER_AGENT},
        timeout=30,
        follow_redirects=True,
    )


#: What to draw: pictures (the frame's own) and, only when asked for,
#: photographs, sculpture, decorative arts (ceramics, textiles, glass…) and
#: pages and miniatures of manuscripts.
Kind = Literal[
    "any",
    "painting",
    "print",
    "drawing",
    "poster",
    "photograph",
    "sculpture",
    "decorative",
    "manuscript",
]


@dataclass(frozen=True)
class Access:
    """What the owner lets sources return, and how to reach them."""

    #: The frame is only seen at home: also free licences (CC BY-SA and the
    #: like), works still in copyright that their collections publish, and
    #: WikiArt.
    private_use: bool = False
    #: Death years for the EU rule; without it only works marked free count.
    life: LifeDates | None = None
    europeana_key: str = "api2demo"
    #: Openverse app credentials (client id, secret); anonymous without them.
    openverse_app: tuple[str, str] | None = None
    #: Smithsonian Open Access key (api.data.gov); the source is off without it.
    smithsonian_key: str = ""
    #: Paris Musées token (an account of one's own); the source is off without it.
    paris_token: str = ""
    #: WikiArt API keys (access code, secret code); without them WikiArt's
    #: free limit is shared with everyone who asks without keys.
    wikiart_keys: tuple[str, str] | None = None
    #: Where sources keep downloaded indexes (the National Gallery of Art's).
    data_dir: Path | None = None
    #: Sources the owner turned off (Commons, Europeana…): not on offer, yet
    #: still asked for the works of museums chosen in Szukaj.
    sources_off: frozenset[str] = frozenset()


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
    #: Drawn from at random for playlists and Odkrywaj; a source that cannot
    #: filter by kind or years (WikiArt) is only searched, unless a playlist
    #: names it.
    draws: ClassVar[bool] = True
    #: Marks its most important works and can be asked for only those.
    highlights: ClassVar[bool] = False
    #: The language its search understands: Polish words typed in Szukaj
    #: are translated for the others (``Wording``).
    language: ClassVar[str] = "en"
    #: Its search keeps to a phrase in double quotes ("night watch": the
    #: words next to each other): Szukaj's phrases are asked quoted; the
    #: others get the words bare, and Szukaj checks the phrase itself.
    phrases: ClassVar[bool] = False
    #: A source of one kind only (the Library of Congress's photographs):
    #: asked just when that kind is, never by every search.
    only: ClassVar[Kind | None] = None

    @classmethod
    def offered(cls, access: Access) -> bool:
        """Whether the owner's choices and keys let this source answer."""
        return True

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

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        """Works by ``artist`` (with ``words``), asked by the museum's own
        author field where it has one: no pages of works only naming them
        (Mateusz 2026-11-09). Without one, the name among the words."""
        return self.search(" ".join(w for w in (words, artist) if w), limit, page)

    def search_artist(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        """:meth:`search_by`, and the name among the words when the author
        field finds nothing or is refused: the museum may spell the artist
        otherwise ("Rembrandt Harmensz. van Rijn")."""
        if type(self).search_by is Museum.search_by:
            return self.search_by(artist, words, limit, page)
        try:
            found = self.search_by(artist, words, limit, page)
        except httpx.HTTPStatusError as err:
            if not 400 <= err.response.status_code < 500 or err.response.status_code == 429:
                raise
            log.info("%s: author field refused (%s); the name as words", self.key, err)
            found = (0, [])
        if found[0]:
            return found
        return self.search(" ".join(w for w in (words, artist) if w), limit, page)

    def search_kind(
        self, query: str, kind: Kind, limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        """:meth:`search` when a search asks for one kind (Fotografia):
        sources whose results don't say what each work is search that kind
        alone (the Getty), those that can filter by it do (AIC). A text
        asking for an artist (:func:`by_artist`) is asked by the author
        field (:meth:`search_artist`); the others' works of other kinds are
        left out by their type (``vocabulary.searched_technique_fits``)."""
        by = asked_by(query)
        if by is not None:
            return self.search_artist(*by, limit=limit, page=page)
        return self.search(query, limit, page)

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

    # -- the source's dump, searched at home (library/dumps.py) -----------------

    def _index(self) -> DumpIndex | None:
        """The index of this source's published dump, None without one."""
        return local_index(self.key, self.access.data_dir)

    def _from_dump(
        self,
        index: DumpIndex,
        words: str = "",
        *,
        limit: int,
        page: int,
        spec: Discovery | None = None,
        **filters: Any,
    ) -> tuple[int, list[Item]]:
        """A page of the index's works, mapped as the API's records are."""
        if spec is not None:
            filters.setdefault("year_from", spec.year_from)
            filters.setdefault("year_to", spec.year_to)
        total, found = index.search(
            words,
            private_use=self.private_use,
            offset=(page - 1) * limit,
            limit=limit,
            **filters,
        )
        return total, [i for r in found if (i := self._map(r))]  # type: ignore[attr-defined]

    def only_at_home(self, query: str, limit: int = 8) -> tuple[int, list[Item]] | None:
        """Works for words typed from what is kept at home only (this
        source's dump), never asking the museum; None when nothing is kept.
        For the hint while typing (Mateusz 2026-11-09: it waited 40-90 s for
        the museums)."""
        index = self._index()
        if index is None or not dump_words(query) or re.search(r"[:=]", query):
            return None
        return self._from_dump(index, query, limit=limit, page=1)

    def _at_home(
        self,
        query: str,
        limit: int,
        page: int,
        ask: Callable[[], tuple[int, list[Item]]],
        artist: str = "",
        **filters: Any,
    ) -> tuple[int, list[Item]]:
        """Works for words typed (and by ``artist``, in the dump's artist
        texts): from the dump's index when it finds enough
        (:data:`LOCAL_MIN`), else from the museum's own search, as before
        there was an index; the index's when the museum cannot be asked."""
        index = self._index()
        if artist:
            if index is None or not dump_words(artist) or re.search(r"[:=]", query):
                return ask()
            filters["also"] = [*filters.get("also", ()), (artist, ("artist",))]
        elif index is None or not dump_words(query) or re.search(r"[:=]", query):
            return ask()
        found = self._from_dump(index, query, limit=limit, page=page, **filters)
        if found[0] >= LOCAL_MIN:
            return found
        try:
            asked = ask()
        except (Resting, httpx.HTTPError) as err:
            if not found[0]:
                raise
            log.info("%s: %s; the works found at home instead", self.key, err)
            return found
        return asked if asked[0] >= found[0] else found

    def _from_index(self, source_id: str) -> dict[str, Any] | None:
        """``source_id``'s record from the dump's index, if it has it."""
        index = self._index()
        return index.get(source_id) if index is not None else None

    def _item(self, source_id: str, **fields: Any) -> Item:
        for key in ("title", "artist"):
            if key in fields:
                fields[key] = clean_title(fields[key])
        if "title" in fields:
            fields["title"] = strip_artist(fields["title"], fields.get("artist", ""))
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
    phrases = True
    name = "Art Institute of Chicago"
    api = "https://api.artic.edu/api/v1"
    iiif = AIC_IIIF
    fields = (
        "id,title,artist_title,artist_display,date_display,date_start,medium_display,"
        "artwork_type_title,classification_titles,style_titles,subject_titles,"
        "place_of_origin,credit_line,"
        "description,short_description,image_id,thumbnail,is_public_domain"
    )

    @staticmethod
    def _type(d: dict[str, Any]) -> str:
        """Its type; a poster's is "Print", the word only among its
        classifications: "Poster" then, for Plakaty (``vocabulary.is_poster``)."""
        kind = str(d.get("artwork_type_title") or "")
        classes = [str(c).casefold() for c in d.get("classification_titles") or []]
        return "Poster" if kind == "Print" and "poster" in classes else kind

    def _map(self, d: dict[str, Any]) -> Item | None:
        if not d.get("image_id") or not d.get("is_public_domain"):
            return None
        display = (d.get("artist_display") or "").split("\n")
        thumb = d.get("thumbnail") or {}
        width = thumb.get("width")
        return self._item(
            str(d["id"]),
            title=d.get("title") or "",
            artist=d.get("artist_title") or display[0].strip(),
            artist_bio=display[1].strip() if len(display) > 1 else "",
            date_text=d.get("date_display") or "",
            year=d.get("date_start"),
            medium=d.get("medium_display") or "",
            classification=self._type(d),
            styles=d.get("style_titles") or [],
            subjects=d.get("subject_titles") or [],
            culture=d.get("place_of_origin") or "",
            credit=d.get("credit_line") or "",
            license="CC0 1.0",
            url=f"https://www.artic.edu/artworks/{d['id']}",
            description=strip_html(d.get("description") or d.get("short_description")),
            image_url=aic_original(f"{self.iiif}/{d['image_id']}", width, thumb.get("height")),
            thumb_url=aic_picture(f"{self.iiif}/{d['image_id']}", AIC_THUMB, width),
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
        def ask() -> tuple[int, list[Item]]:
            must = [self._text(query, self.search_fields)] if query.strip() else []
            return self._post(query, must, [], limit, page)

        if not query.strip() and (index := self._index()) is not None:
            return self._from_dump(index, limit=limit, page=page)
        return self._at_home(query, limit, page, ask)

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        def ask() -> tuple[int, list[Item]]:
            must: list[dict[str, Any]] = [
                {"match": {"artist_title": {"query": artist, "operator": "and"}}}
            ]
            if words.strip():
                must.append(self._text(words, self.search_fields))
            return self._post(words, must, [], limit, page)

        return self._at_home(words, limit, page, ask, artist=artist)

    def search_kind(
        self, query: str, kind: Kind, limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        """Works of one type (Malarstwo: "Painting"): its search for an
        artist or words brings any, his caricatures too (Mateusz
        2026-11-10). Posters and manuscripts are prints and books by their
        type, so by their classification ("poster": Toulouse-Lautrec's 26,
        none of which his plain search's first page had)."""
        dump: dict[str, Any]
        if kind in ("poster", "manuscript"):
            kept = self._text(kind, ("classification_titles", "term_titles"))
            dump = {"also": [(kind, ("kind",))]}
        elif kind in self.artwork_types:
            kept = {"term": {"artwork_type_title.keyword": self.artwork_types[kind]}}
            dump = {"kinds": (self.artwork_types[kind],)}
        else:
            return super().search_kind(query, kind, limit, page)
        artist, words = asked_by(query) or ("", query)

        def ask() -> tuple[int, list[Item]]:
            must: list[dict[str, Any]] = [kept]
            if artist:
                must.append({"match": {"artist_title": {"query": artist, "operator": "and"}}})
            if words.strip():
                must.append(self._text(words, self.search_fields))
            return self._post(words, must, [], limit, page)

        if not artist and not words.strip():
            return self.discover(Discovery(kind=kind), limit, page)
        return self._at_home(words, limit, page, ask, artist=artist, **dump)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        index = self._index()
        if index is not None:
            kinds: tuple[str, ...] = ()
            also: list[tuple[str, tuple[str, ...]]] = []
            if spec.kind in ("poster", "manuscript"):
                also.append((spec.kind, ("kind",)))
            elif spec.kind in self.artwork_types:
                kinds = (self.artwork_types[spec.kind],)
            elif spec.kind == "decorative":
                kinds = self.decorative_types
            return self._from_dump(
                index,
                spec.style,
                columns=("tags", "kind"),
                also=also,
                kinds=kinds,
                spec=spec,
                limit=limit,
                page=page,
            )
        must: list[dict[str, Any]] = []
        filters: list[dict[str, Any]] = []
        if spec.style.strip():
            fields = ("style_titles", "term_titles", "subject_titles", "classification_titles")
            must.append(self._text(spec.style, fields))
        if spec.kind in ("poster", "manuscript"):
            must.append(self._text(spec.kind, ("classification_titles", "term_titles")))
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
        if (record := self._from_index(source_id)) is not None:
            return self._map(record)
        resp = self.http.get(f"{self.api}/artworks/{source_id}", params={"fields": self.fields})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(resp.json().get("data", {}))


class ClevelandMuseum(Museum):
    key = "cma"
    phrases = True
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
        "manuscript": "Manuscript",
    }

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if not query.strip() and (index := self._index()) is not None:
            return self._from_dump(index, limit=limit, page=page)
        return self._at_home(query, limit, page, lambda: self._get({"q": query}, limit, page))

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        params = {"artists": artist, **({"q": words} if words.strip() else {})}
        return self._at_home(
            words, limit, page, lambda: self._get(params, limit, page), artist=artist
        )

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        words = [spec.style.strip(), "poster" if spec.kind == "poster" else ""]
        if (index := self._index()) is not None:
            return self._from_dump(
                index,
                " ".join(w for w in words if w),
                kinds=(self.types[spec.kind],) if spec.kind in self.types else (),
                highlight=spec.highlight,
                spec=spec,
                limit=limit,
                page=page,
            )
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
        if (record := self._from_index(source_id)) is not None:
            return self._map(record)
        resp = self.http.get(f"{self.api}/artworks/{source_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(resp.json().get("data", {}))


#: Works the Met's open data must find for words before its own search is
#: left alone (met_index.py).
MET_LOCAL_MIN = 24


class MetropolitanMuseum(Museum):
    key = "met"
    phrases = True
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
            # The Egyptian department leaves its works' culture out.
            culture=d.get("culture") or self.cultures.get(d.get("department") or "", ""),
            credit=d.get("creditLine") or "",
            license="CC0 1.0",
            url=d.get("objectURL") or "",
            highlight=bool(d.get("isHighlight")),
            description="",
            image_url=d.get("primaryImage") or d["primaryImageSmall"],
            thumb_url=d["primaryImageSmall"],
        )

    page_size = 24  # every result is one more request
    #: A department's culture, for works that name none.
    cultures: ClassVar[dict[str, str]] = {"Egyptian Art": "Egyptian"}

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        return self._search({"q": query}, limit, page)

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        # The open data's artist texts at home; the Met's own search for its
        # artist or culture field (``artistOrCulture``) when they find few.
        params: dict[str, Any] = {"q": f"{words} {artist}"}
        if not words.strip():
            params = {"q": artist, "artistOrCulture": "true"}
        return self._search(params, limit, page, artist=artist, words=words)

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
        # Posters share a department with prints, sculpture with crafts;
        # manuscripts are in several (Islamic, Asian, Medieval Art).
        word = spec.kind if spec.kind in ("poster", "sculpture", "manuscript") else ""
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

    def _search(
        self, params: dict[str, Any], limit: int, page: int, artist: str = "", words: str = ""
    ) -> tuple[int, list[Item]]:
        # The Met's open data searched at home once it is in (met_index.py):
        # the Met is asked only for the works found.
        index = MET_INDEX.get(self.access.data_dir) if self.access.data_dir else None
        local = 0
        if index is not None:
            local, ids = index.search(
                str(params.get("q") or "") if not artist else words,
                artist=artist,
                department=params.get("departmentId"),
                begin=params.get("dateBegin"),
                end=params.get("dateEnd"),
                highlight=params.get("isHighlight") == "true",
                offset=(page - 1) * limit,
                limit=limit,
            )
            total = local
        # Words the open data has too few works for: the Met's own search
        # reads its descriptions too ("Cimabue" in a Madonna's), and the
        # open data only keeps the works it can show.
        if index is None or (local < MET_LOCAL_MIN and str(params.get("q", "*")) != "*"):
            resp = self.http.get(
                f"{self.api}/v1.1/search",
                params={
                    **params,
                    "hasImages": "true",
                    "limit": limit,
                    "offset": (page - 1) * limit,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            ids = [str(i) for i in body.get("objectIDs") or []]
            total = int(body.get("total", len(ids)))
            if index is not None:
                ids = index.showable(ids)
        items = []
        missed: httpx.HTTPError | None = None
        for object_id in ids:
            try:
                item = self.fetch(str(object_id))
            except Resting:
                raise  # the bot wall turned us away: the rest would fail too
            except httpx.HTTPError as err:
                # One object that doesn't load (a timeout, a 5xx) is left
                # out instead of the whole page.
                log.info("met: object %s left out: %s", object_id, err)
                missed = err
                continue
            if item is not None:
                items.append(item)
            elif index is not None:
                index.no_picture(str(object_id))  # not shown: not asked again
        if missed is not None and not items:
            raise missed
        return total, items

    def fetch(self, source_id: str) -> Item | None:
        # Each work's record asked once (library/met_objects.py): a page of
        # the search is a request a work.
        kept = met_objects(self.access.data_dir) if self.access.data_dir else None
        if kept is not None:
            found, record = kept.get(source_id)
            if found:
                return None if record is None else self._map(record)
        resp = self.http.get(f"{self.api}/v1/objects/{source_id}")
        if resp.status_code == 404:
            if kept is not None:
                kept.put(source_id, None)
            return None
        resp.raise_for_status()
        record = resp.json()
        if kept is not None and isinstance(record, dict) and record.get("objectID"):
            kept.put(source_id, record)
        return self._map(record)


class WikimediaCommons(Museum):
    """Public-domain files on Wikimedia Commons, used mainly for Polish art.

    ``query`` is either free text or ``Category:<name>`` (e.g.
    ``Category:Paintings by Józef Chełmoński``), which is far more precise.
    Note: Commons rate-limits datacenter IPs; from a home network it is fine.
    """

    key = "wmc"
    phrases = True
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
    #: Files described as works of art that are archives' papers and
    #: diagrams: the US National Archives' scans (forms, reports, dog tags)
    #: and chemistry (Mateusz 2026-11-07, Szukaj "bednarski"), France's
    #: archives' documents, backs of paintings, objects. Words typed find
    #: them; a chosen category doesn't.
    not_art = re.compile(
        r"national archives|\bnara\b|records administration|textual reference|file unit|"
        r"record group|missing air crew|dog tags?|identification tags?|chemical|chemistry|"
        r"structural formula|organic synthesis|\bdiagrams?\b|\bcharts?\b|scanned documents|"
        # Archives' papers, backs of paintings, a museum's objects
        # photographed (Szukaj "II wojna światowa", 2026-11-09).
        r"\bdocuments\b|archives nationales|reverses of paintings|unsupported object",
        re.IGNORECASE,
    )
    #: Category queries whose works are not paintings, and what they are.
    category_kinds: ClassVar[dict[str, str]] = {"Drawings": "Drawing", "Prints": "Print"}
    #: Category (``Category:``) and category tree (``deepcat:``) queries of
    #: old photographs: their files are photographs (Mateusz 2026-11-07:
    #: "Pierwsze kolory" without waiting for the Library of Congress).
    photo_queries = re.compile(r"photograph|photochrom|photos? of|autochrom", re.IGNORECASE)
    #: Old photographs only: older than this year, whose 95 years are over…
    photo_before = 1930
    #: …and big enough for the frame (long side; Commons has many 600 px
    #: scans of cabinet cards, 2026-11-07).
    photo_min_side = 1500
    #: …and not older than photography: prints and caricatures of 1800 come
    #: with the Library of Congress's photographs (2026-11-07).
    photo_after = 1839
    #: Files among photographs that are something else (Library of Congress
    #: uploads: prints, posters, maps).
    not_photo = re.compile(
        r"lithograph|engraving|etching|woodcut|aquatint|mezzotint|cartoon|caricature|"
        r"poster|drawing|\bmaps?\b",
        re.IGNORECASE,
    )
    #: Old photographs drawn without words (Fotografia alone), taking turns:
    #: the Library of Congress's uploads (626 000 files, 30 of 50 old,
    #: public-domain and big) and photographs whose US copyright ran out
    #: (68 000, 21 of 50); {{Photograph}} alone gave 0 of 50 (checked from
    #: the home address, 2026-11-07).
    photo_draws = (
        'filetype:bitmap hastemplate:"LOC-image"',
        'filetype:bitmap hastemplate:Photograph hastemplate:"PD-US-expired"',
    )
    #: How a photograph was made, from its categories and description: the
    #: colour processes are what "Pierwsze kolory" asks for (EARLY_COLOUR).
    processes: ClassVar[tuple[tuple[re.Pattern[str], str], ...]] = (
        (re.compile(r"prokudin", re.IGNORECASE), "Three-colour photograph"),
        (re.compile(r"photochrom", re.IGNORECASE), "Photochrom print"),
        (re.compile(r"autochrom", re.IGNORECASE), "Autochrome"),
        (re.compile(r"kodachrome", re.IGNORECASE), "Kodachrome transparency"),
        (
            re.compile(r"color photographs from the farm security", re.IGNORECASE),
            "Kodachrome transparency",
        ),
        (re.compile(r"daguerreotyp", re.IGNORECASE), "Daguerreotype"),
        (re.compile(r"albumen", re.IGNORECASE), "Albumen print"),
        (re.compile(r"cyanotyp", re.IGNORECASE), "Cyanotype"),
    )

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
        self,
        page: dict[str, Any],
        artist_hint: str = "",
        classification: str = "Painting",
        any_year: bool = False,
    ) -> Item | None:
        """``page``'s file as a work of ``classification``, or None. A
        photograph must be big enough and in the public domain; from a
        search of all of Commons also old (``any_year``: from a chosen
        collection, whose FSA colour slides are of the 1940s)."""
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        categories = self._meta(info, "Categories")
        photo = classification == "Photograph"
        # A photograph is what is asked for: none of these are works of art.
        if not photo and self.snapshot.search(categories):
            return None
        if classification == "Painting" and self.printed_copy.search(categories):
            return None
        if not any_year:  # words typed: not a collection someone chose
            told = " ".join(
                (
                    categories,
                    self._meta(info, "Credit"),
                    self._meta(info, "Artist"),
                    str(page.get("title", "")),
                )
            )
            if self.not_art.search(told):
                return None
        licence = self._meta(info, "LicenseShortName")
        public = "public domain" in licence.casefold() or "cc0" in licence.casefold()
        # Everything on Commons is freely licensed; attribution is kept in
        # ``credit``. Photographs: public domain only (the free licences are
        # today's snapshots).
        if not public and (photo or not (self.private_use and licence)):
            return None
        date_text = self._text(info, "DateTimeOriginal")
        year = commons_year(self._meta(info, "DateTimeOriginal"))
        medium = ""
        if photo:
            side = max(int(info.get("width") or 0), int(info.get("height") or 0))
            old = year is not None and self.photo_after <= year < self.photo_before
            if side < self.photo_min_side or not (old or any_year):
                return None
            if not any_year and self.not_photo.search(f"{categories} {page.get('title', '')}"):
                return None
            told = f"{categories} {self._meta(info, 'ImageDescription')}"
            medium = next((m for p, m in self.processes if p.search(told)), "Photograph")
        # Visible text only: {{Unknown|author}} hides its English name in
        # the Polish one ("Nieznany<span style="display: none">Unknown
        # author</span>" came as "NieznanyUnknown author", 2026-11-07).
        artist = artist_hint or self._text(info, "Artist").split("\n")[0].strip()
        title = self._text(info, "ObjectName", title=True) or file_title(
            page.get("title", ""), clean_title(artist), year
        )
        image_url = str(info.get("url", ""))
        if (ext := extension(image_url)) and ext not in WEB_IMAGES:
            # SVG drawings, TIFF, PDF and DjVu scans: Commons' rendered copy.
            rendition = commons_rendition(image_url, 3840, info.get("width"))
            if not rendition and ext in VECTOR:
                return None
            image_url = rendition or image_url
        return self._item(
            str(page["pageid"]),
            title=title,
            artist=artist,
            date_text=date_text[:40],
            year=year,
            classification=classification,
            medium=medium,
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
        named = re.sub(r"^(?:Category:|deepcat:)", "", query).strip('"')
        photos = query.startswith(("Category:", "deepcat:")) and self.photo_queries.search(named)
        return self._search(query, limit, page, photos=bool(photos))

    def search_kind(
        self, query: str, kind: Kind, limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        """Fotografia: old photographs from all of Commons ({{Photograph}},
        :meth:`_map`). Commons says nothing else about what a file shows, so
        sculpture, decorative arts and manuscripts are not asked for here:
        its sculpture is today's snapshots (2026-11-07)."""
        query = plain_text(query)
        if kind == "photograph":
            return self._search(query, limit, page, photos=True)
        if kind in ("sculpture", "decorative", "manuscript"):
            return 0, []
        return self.search(query, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        """Old photographs (Fotografia without words): :data:`photo_draws`
        taking turns page by page; Commons draws nothing else (Mateusz
        2026-11-07: Fotografia + Wikimedia Commons found 0 works)."""
        if spec.kind != "photograph" or spec.highlight:
            return 0, []
        draw = self.photo_draws[(page - 1) % len(self.photo_draws)]
        turn = (page - 1) // len(self.photo_draws) + 1
        words = f"{spec.style.strip()} {draw}".strip()
        total, items = self._search(words, limit, turn, photos=True, words=words)
        # Both have far more than a search reaches (10 000).
        more = total > turn * limit
        return (len(self.photo_draws) * self.random_depth if more else turn * limit), items

    def random_draw(self, spec: Discovery, rng: random.Random) -> Iterator[Item]:
        """Pages of :meth:`discover` taken at random, as deep as Commons'
        search reaches."""
        if spec.kind != "photograph" or spec.highlight:
            return
        size = min(self.page_size, 24)
        pages = list(range(1, len(self.photo_draws) * self.random_depth // size + 1))
        rng.shuffle(pages)
        for page in pages[:40]:
            _, items = self.discover(spec, limit=size, page=page)
            rng.shuffle(items)
            yield from items

    def _search(
        self, query: str, limit: int, page: int, photos: bool, words: str | None = None
    ) -> tuple[int, list[Item]]:
        artist_hint = ""
        classification = "Photograph" if photos else "Painting"
        offset = (page - 1) * limit
        if query.startswith("Category:"):
            if by := re.match(r"^Category:(Paintings|Works|Drawings|Prints) by (.+)", query):
                artist_hint = by.group(2)
                classification = self.category_kinds.get(by.group(1), classification)
            body = self._category_page(query, limit, offset)
        else:
            if words is not None:
                pass  # asked as it is (:meth:`discover`)
            elif query.startswith("deepcat:"):  # a category and those under it
                words = f"{query} filetype:bitmap"
            elif photos:
                # Files described as photographs ({{Photograph}}): 3.3
                # million, archives' scans among today's snapshots, which
                # :meth:`_map` leaves out.
                words = f"{query} filetype:bitmap hastemplate:Photograph"
            else:
                # Only files described as works of art ({{Artwork}},
                # {{Painting}}): free text alone finds mostly photographs.
                words = f"{query} filetype:bitmap hastemplate:Artwork"
            resp = self.http.get(
                self.api,
                params=self._params(
                    generator="search",
                    gsrsearch=words,
                    gsrnamespace=6,
                    gsrlimit=limit,
                    gsroffset=offset,
                ),
            )
            resp.raise_for_status()
            body = resp.json()
        pages = body.get("query", {}).get("pages", {})
        chosen = query.startswith(("Category:", "deepcat:"))
        items = [
            i for p in pages.values() if (i := self._map(p, artist_hint, classification, chosen))
        ]
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
        if not page:
            return None
        # A photograph shown in a search: not a painting, but a photograph.
        return self._map(page) or self._map(page, classification="Photograph", any_year=True)

    def file(self, name: str) -> Item | None:
        """The work in the file ``name`` ("Hokusai Great Wave.jpg", as
        Wikidata's P18 names it); None when Commons has no such file or it
        is no work of art to show."""
        resp = self.http.get(self.api, params=self._params(titles=f"File:{name}"))
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        page = next((p for p in pages.values() if "pageid" in p), None)
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
        # Either language-tagged values or plain strings, in a list or one
        # alone: a lone value read as a list was its keys, "@language"
        # (Toulouse-Lautrec's prints by "@language", 2026-11-10).
        notation = node.get("notation") or []
        if not isinstance(notation, list):
            notation = [notation]
        values = [v if isinstance(v, dict) else {"@value": v} for v in notation]
        english = [v for v in values if v.get("@language") == "en"]
        return str((english or values or [{}])[0].get("@value", ""))

    def _image(self, d: dict[str, Any]) -> tuple[str, str]:
        """IIIF base of the public-domain image and its licence, if any; with
        ``private_use`` also of one still in copyright ("InC")."""
        protected = ""
        for subject in d.get("subject_of") or []:
            for carrier in subject.get("digitally_carried_by") or []:
                rights = [r.get("content", "") for r in carrier.get("referred_to_by") or []]
                licence = next(
                    (self.open_licences[r] for r in rights if r in self.open_licences), ""
                )
                for point in carrier.get("access_point") or []:
                    url = point.get("id", "")
                    if "iiif" not in url:
                        continue
                    if licence:
                        return re.sub(r"/full/.*$", "", url), licence
                    protected = protected or re.sub(r"/full/.*$", "", url)
        if protected and self.private_use:
            return protected, PRIVATE_LICENCE
        return "", ""

    def _page_url(self, d: dict[str, Any]) -> str:
        for subject in d.get("subject_of") or []:
            for carrier in subject.get("digitally_carried_by") or []:
                if carrier.get("format") == "text/html":
                    for point in carrier.get("access_point") or []:
                        if point.get("id"):
                            return str(point["id"])
        return str(d.get("id", ""))

    def _licence(self, rights: str) -> str:
        """The licence of a picture with ``rights`` (its statement's URL);
        "" when it may not be shown."""
        found = self.open_licences.get(re.sub(r"^http:", "https:", rights), "")
        return found or (PRIVATE_LICENCE if self.private_use else "")

    def _map_kept(self, d: dict[str, Any]) -> Item | None:
        """A record read over OAI-PMH and kept at home (library/rijks_index.py)."""
        licence = self._licence(str(d.get("rights") or ""))
        iiif = str(d.get("iiif") or "")
        if not iiif or not licence:
            return None
        types = d.get("types") or []
        return self._item(
            str(d["id"]),
            title=str(d.get("title") or ""),
            artist=str(d.get("artist") or ""),
            date_text=str(d.get("date") or ""),
            year=d.get("year"),
            medium=str(d.get("medium") or ""),
            classification=str(types[0]) if types else "",
            credit=str(d.get("credit") or ""),
            license=licence,
            url=str(d.get("page") or ""),
            highlight=bool(d.get("top")),
            description=str(d.get("about") or ""),
            image_url=f"{iiif}/full/max/0/default.jpg",
            thumb_url=f"{iiif}/full/600,/0/default.jpg",
        )

    def _map(self, d: dict[str, Any]) -> Item | None:
        if d.get("edm"):
            return self._map_kept(d)
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
        last = spec.year_to if spec.year_to is not None else 2000
        # Antiquity (up to 499) asks for its last century.
        start = spec.year_from if spec.year_from is not None else max(0, min(1000, last - 100))
        first = start // 10 * 10
        return list(range(first, last + 1, 10))

    def _index(self) -> DumpIndex | None:
        """The collection kept at home once read whole (library/rijks_index.py)."""
        return rijks_local_index(self.access.data_dir)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.style.strip() or spec.kind == "decorative":
            return 0, []  # no field for styles or movements, no one type of crafts
        if (index := self._index()) is not None:
            kind = spec.kind if spec.kind != "any" else "painting"
            return self._from_dump(index, kinds=(kind,), spec=spec, limit=limit, page=page)
        decade = self._decades(spec)[0]
        total, ids = self._ids(self._discovery_params(spec, decade), (page - 1) * limit, limit)
        return total, self._objects(ids)

    def random_draw(self, spec: Discovery, rng: random.Random) -> Iterator[Item]:
        """Decades in random order (the API has no date ranges), then the
        first results of each, shuffled."""
        if spec.highlight or spec.style.strip() or spec.kind == "decorative":
            return
        if self._index() is not None:  # pages of the index in random order
            yield from Museum.random_draw(self, spec, rng)
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
        if not query and (index := self._index()) is not None:
            return self._from_dump(index, limit=limit, page=page)
        return self._at_home(query, limit, page, lambda: self._search(query, limit, page))

    def _search(self, query: str, limit: int, page: int) -> tuple[int, list[Item]]:
        """The museum's own search: a creator, else a title."""
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
        if (at_home := self._from_index(source_id)) is not None:
            return self._map(at_home)
        # A search page is a request a work: each record asked once
        # (library/records.py).
        kept = records(self.access.data_dir) if self.access.data_dir else None
        if kept is not None:
            found, record = kept.get(self.key, source_id)
            if found:
                return None if record is None else self._map(record)
        resp = self.http.get(
            f"https://id.rijksmuseum.nl/{source_id}",
            headers={"Accept": "application/ld+json"},
        )
        if resp.status_code == 404:
            if kept is not None:
                kept.put(self.key, source_id, None)
            return None
        resp.raise_for_status()
        record = resp.json()
        if kept is not None and isinstance(record, dict):
            kept.put(self.key, source_id, record)
        return self._map(record)


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


#: Start of the licence of works once let in by the test switch "Bez limitu
#: 70 lat" (until 1.111.0); they now carry ``PRIVATE_LICENCE``.
TEST_LICENCE = "Tylko do testów"
#: Works still in copyright whose pictures their museum publishes itself, let
#: in with ``private_use``: the frame is seen at home only, and Polish law
#: lets one copy such pictures for personal use (art. 23).
PRIVATE_LICENCE = "Prawa autorskie w mocy (użytek prywatny)"


def cc_name(code: str, version: str) -> str:
    return f"CC {code.upper()} {version}"


#: Hosts of Europeana's providers that answer programs with a "verify you
#: are human" page, Europeana's own media proxy included: their works'
#: originals can never be had (2026-10: the Belvedere's collection, files
#: on Dropbox: Orsay, Alte Pinakothek, Nationalmuseum).
EUROPEANA_UNREACHABLE = frozenset({"sammlung.belvedere.at", "www.dropbox.com", "dropbox.com"})


def europeana_mirrors(item: Item, thumb: bool = False) -> list[str]:
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
    "in copyright". With ``private_use`` every work its providers publish
    comes, those still in copyright marked ``PRIVATE_LICENCE``. Without a
    key of its own (``FRAME_EUROPEANA_KEY``, free at europeana.eu) it uses
    the shared demo key.
    """

    key = "europeana"
    phrases = True
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
        r"bank ?notes?|numismat\w*|specimens?|herbari\w*)\b",
        re.IGNORECASE,
    )
    #: Concept labels that name a work's type, for records whose type comes
    #: as a vocabulary link only (the German Digital Library's: "paintings
    #: (visual works)", "Art of painting", "Drawing").
    type_concepts = re.compile(
        r"\b(paintings?|drawings?|prints?|posters?|watercolou?rs?|sketch\w*|studies)\b",
        re.IGNORECASE,
    )
    #: Concept labels that name its materials and techniques ("oil paint
    #: (paint)", "canvas (textile material)"); subjects ("Farm") are left out.
    medium_concepts = re.compile(
        r"\b(oil|tempera|canvas|panel|wood|oak|paper|cardboard|parchment|ink|chalk|graphite|"
        r"pencils?|charcoal|pastel|gouache|watercolou?r|silver ?points?|etching|engraving|"
        r"woodcut|lithograph\w*|mezzotint|aquatint|copper|fresco|acrylic)\b",
        re.IGNORECASE,
    )
    #: Aggregators of natural history, not art: OpenUp! brings botanical
    #: photos with names like "Rosa 'Claude Monet'", found by artist. The
    #: city of Girona's photo archive calls its photographs paintings and
    #: posters (see ``vocabulary.PHOTO_ARCHIVES``). Athens' Philatelic
    #: Postal Museum calls its stamps, first-day covers and proofs prints:
    #: nearly every print after 1950 (see ``vocabulary.NOT_ART_PROVIDERS``).
    #: Bildarchiv Foto Marburg photographs works for art historians: files of
    #: 1200 px, half black-and-white prints on a catalogue card, the rest old
    #: colour slides faded blue and white; not asked any more (Mateusz,
    #: 2026-11-09), its works already kept take other copies
    #: (``vocabulary.ART_PHOTO_ARCHIVES``). Nor Rome's Hertziana, whose
    #: photographs of works are as Marburg's (cropped, 400 px).
    not_art = (
        '-PROVIDER:"OpenUp!"',
        '-DATA_PROVIDER:"Ajuntament de Girona"',
        '-DATA_PROVIDER:"Philatelic Postal Museum"',
        '-DATA_PROVIDER:"German Documentation Center for Art History - Marburg Picture Index"',
        '-DATA_PROVIDER:"Bibliotheca Hertziana, Max Planck Institute for Art History Rome. '
        'Photographic Collection"',
        '-what:(stamp OR "postage stamp" OR "postal services" OR coin OR coins OR medal '
        "OR medals OR banknote OR banknotes)",
    )

    #: Concept labels that name a kind of object or a photograph.
    object_concepts = re.compile(
        r"\b(ceramics?|porcelain|pottery|earthenware|stoneware|glass|silver|metalwork|"
        r"textiles?|furniture|bells?|clocks?|sculptures?|statues?|photos?|photographs?|"
        r"posters?|manuscripts?)\b",
        re.IGNORECASE,
    )
    #: Archives of photographs whose records say nothing of their type.
    photo_providers = re.compile(r"\bfortepan\b|sound (?:&|and) vision|beeld en geluid", re.I)
    #: Types given as Getty AAT links only, by their numbers.
    aat_types: ClassVar[dict[str, str]] = {
        "300027221": "Poster",
        "300041575": "Bell",
        "300046300": "Photograph",
        "300033618": "Painting",
        "300033973": "Drawing",
        "300041273": "Print",
    }

    def _kinds(self, d: dict[str, Any]) -> list[str]:
        """The record's types: in English first, then as its provider gives
        them in any language ("aardewerk, keramiek, schotel", "Afiș
        teatral"), then those given as Getty AAT links only. A third of
        Europeana's works came typed in no English and were taken for
        pictures (2026-11-09)."""
        langs: dict[str, list[str]] = d.get("dcTypeLangAware") or {}
        order = ["en", "def", *sorted(k for k in langs if k not in ("en", "def"))]
        kinds: list[str] = []
        for lang in order:
            for kind in langs.get(lang) or []:
                text = str(kind)
                if "://" in text:
                    number = text.rstrip("/").rsplit("/", 1)[-1]
                    if "aat" in text and number in self.aat_types:
                        text = self.aat_types[number]
                    else:
                        continue
                if text not in kinds:
                    kinds.append(text)
        return kinds

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
        if not self.private_use:
            return ""
        # Still in copyright (or its rights not evaluated): its provider
        # publishes the picture, a lawful source for a copy seen at home.
        if died is not None:
            free = died + TERM_YEARS + 1
            return f"{PRIVATE_LICENCE}, w UE wolne od {free} (twórca zm. {died})"
        return PRIVATE_LICENCE

    def _map(self, d: dict[str, Any]) -> Item | None:
        image = _first(d.get("edmIsShownBy"))
        preview = _first(d.get("edmPreview"))
        if not image or not preview or not d.get("id"):
            return None
        if (urlsplit(image).hostname or "") in EUROPEANA_UNREACHABLE:
            return None
        kinds = self._kinds(d)
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
        # All of them: the AAT's "Poster" and the provider's own "Afiș
        # teatral" (a theatre programme) are one record's types.
        classification = ", ".join(kinds[:3])
        if not classification:
            classification = next((c for c in concepts if self.type_concepts.search(c)), "")
        if not classification:
            # "Ceramic", "photo", "clocks" (bells): a category of "Sztuki
            # inne" rather than a picture.
            classification = ", ".join(c for c in concepts if self.object_concepts.search(c))
        if not classification and self.photo_providers.search(_first(d.get("dataProvider"))):
            classification = "Photograph"
        medium = ", ".join(c for c in concepts if self.medium_concepts.search(c))
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
            classification=classification,
            medium=medium,
            credit=_first(d.get("dataProvider")),
            license=licence,
            url=_first(d.get("guid")) or f"https://www.europeana.eu/item{record}",
            description=strip_html(_first(d.get("dcDescription")))[:2000],
            image_url=image,
            thumb_url=preview,
        )

    #: Only works from these data providers (the places chosen in Szukaj:
    #: :func:`museum` with ``europeana:Q…``); none: from every one.
    providers: tuple[str, ...] = ()

    def _providers(self) -> list[str]:
        if not self.providers:
            return []
        names = " OR ".join('"' + p.replace('"', " ") + '"' for p in self.providers)
        return [f"DATA_PROVIDER:({names})"]

    def _get(self, query: str, qf: list[str], limit: int, page: int) -> tuple[int, list[Item]]:
        start = (page - 1) * limit + 1
        if start + limit > self.random_depth + 1:
            return 0, []
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("query", query.strip() or "*"),
            ("qf", "TYPE:IMAGE"),
            # Tier 1 is anything from 0.1 megapixel: thumbnails, not pictures.
            ("qf", "contentTier:(2 OR 3 OR 4)"),
            *(("qf", q) for q in self.not_art),
            *(("qf", q) for q in qf),
            *(("qf", q) for q in self._providers()),
            ("media", "true"),
            ("thumbnail", "true"),
            ("profile", "rich"),
            ("rows", limit),
            ("start", start),
        ]
        headers = europeana_key(self.access.europeana_key)
        resp = self.http.get(self.api, params=params, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("items") or [] if (i := self._map(d))]
        return int(body.get("totalResults") or 0), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        # Works of art only: free text alone finds medals, stamps, horse
        # collars and photos of buildings, and buries the paintings.
        return self._get(query, [self.whats["any"]], limit, page)

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        # ``who:``: the work's maker (dcCreator), not any text naming them.
        name = artist.replace('"', " ").strip()
        query = " ".join(w for w in (f'who:"{name}"', words.strip()) if w)
        return self._get(query, [self.whats["any"]], limit, page)

    def search_kind(
        self, query: str, kind: Kind, limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        """Works of one kind by its ``what`` (Plakaty: Mucha's "JOB", typed
        "Print" by its provider): an artist by ``who``. What ``what:poster``
        finds is a poster, so says so (``vocabulary.is_poster``)."""
        if kind == "any" or kind not in self.whats:
            return super().search_kind(query, kind, limit, page)
        artist, words = asked_by(query) or ("", query)
        name = artist.replace('"', " ").strip()
        text = " ".join(w for w in (f'who:"{name}"' if name else "", words.strip()) if w)
        total, items = self._get(text, [self.whats[kind]], limit, page)
        if kind == "poster":
            items = [
                i
                if _POSTER_WORD.search(i.classification)
                else i.model_copy(
                    update={
                        "classification": ", ".join(k for k in (i.classification, "poster") if k)
                    }
                )
                for i in items
            ]
        return total, items

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
        elif not spec.style.strip() and not self.private_use:
            # Nothing to narrow by: most images are still in copyright, so ask
            # for public-domain ones or the pages come back empty.
            qf.append("RIGHTS:*publicdomain*")
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
        # Art only: without a category most of Openverse is Flickr photos,
        # and its "illustration" anyone's drawings, crests and blank tiles
        # (Dadaizm, Mateusz 2026-11-09).
        return self._get({"q": query, "category": "digitized_artwork"}, limit, page)

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
    Works in the public domain (the Danish Golden Age, Hammershøi, the
    Skagen painters) and, with ``private_use``, those still in copyright it
    shows in full (Picasso, Nolde, Jorn); answers in English where it has
    English."""

    key = "smk"
    name = "Statens Museum for Kunst"
    api = "https://api.smk.dk/api/v1"
    #: Works offered: public domain with a picture.
    public_filters = "[public_domain:true],[has_image:true]"

    @property
    def filters(self) -> str:
        return "[has_image:true]" if self.private_use else self.public_filters

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
        public = bool(d.get("public_domain"))
        if not (public or self.private_use) or not iiif or not d.get("object_number"):
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
            license="Public Domain Mark 1.0" if public else PRIVATE_LICENCE,
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

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        # SMK files its makers surname first ("Hammershøi, Vilhelm").
        name = surname_first(artist).replace("[", " ").replace("]", " ")
        filters = f"{self.filters},[creator:{name}]"
        return self._get({"keys": words.strip() or "*", "filters": filters}, limit, page)

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
    """WikiArt: newer art too, offered with "Użytek prywatny" (Mateusz,
    2026-11-06: the frame is seen at home only).

    Mostly old works free anywhere; those still in copyright it shows without
    licences. Searched for artists (Szukaj, playlists, liked artists in
    Odkrywaj) but not drawn from at random: it cannot filter by kind or
    years. A museum's copy of a work wins over WikiArt's (``duplicates``).
    """

    key = "wikiart"
    name = "WikiArt"
    draws = False
    api = "https://www.wikiart.org/en/api/2"
    #: WikiArt's own pages hold 60 works.
    page_size = 60
    licence = "WikiArt (użytek prywatny)"
    #: What its works were marked with while it was a test source.
    test_licence = "Tylko do testów ramki (WikiArt)"

    @classmethod
    def offered(cls, access: Access) -> bool:
        return access.private_use

    #: (search, page) -> token that asks for that page.
    _tokens: ClassVar[dict[tuple[str, int], str]] = {}
    #: Session keys by access code: (key, when it was given). WikiArt gives
    #: ten sessions an hour; one is used for SESSION seconds.
    _sessions: ClassVar[dict[str, tuple[str, float]]] = {}
    _session_lock: ClassVar[threading.Lock] = threading.Lock()
    SESSION = 50 * 60.0
    #: After a login WikiArt refused, none is tried (nor anything asked)
    #: for this long: its login answered 500 to 50 tries on 2026-11-08, up
    #: to eight in two minutes, one for each search, as each restart of the
    #: server starts without a session and it gives ten an hour.
    LOGIN_AGAIN = 30 * 60.0
    #: When a login with each access code was last refused (monotonic).
    _refused: ClassVar[dict[str, float]] = {}

    def _session(self, fresh: bool = False) -> str | None:
        """A session key from the owner's API keys; None without keys."""
        keys = self.access.wikiart_keys
        if not keys:
            return None
        access, secret = keys
        with self._session_lock:
            session, since = self._sessions.get(access, ("", 0.0))
            if fresh or not session or time.monotonic() - since > self.SESSION:
                refused = self._refused.get(access)
                if refused is not None and time.monotonic() - refused < self.LOGIN_AGAIN:
                    left = self.LOGIN_AGAIN - (time.monotonic() - refused)
                    raise httpx.HTTPError(
                        f"WikiArt refused a login lately; not asked for {left / 60:.0f} min"
                    )
                try:
                    resp = self.http.get(
                        f"{self.api}/login", params={"accessCode": access, "secretCode": secret}
                    )
                    resp.raise_for_status()
                    session = str(resp.json().get("SessionKey") or "")
                    if not session:
                        raise httpx.HTTPError("WikiArt gave no session")
                except httpx.HTTPError:
                    self._refused[access] = time.monotonic()
                    raise
                self._refused.pop(access, None)
                self._sessions[access] = (session, time.monotonic())
            return session

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
            # Only a work's own record (``fetch``) names where it hangs:
            # "Musée d'Orsay, Paris, France".
            holder=next((str(g).strip() for g in d.get("galleries") or [] if str(g).strip()), ""),
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
        session = self._session()
        if session:
            params["authSessionKey"] = session
        resp = self.http.get(f"{self.api}/{endpoint}", params=params)
        if session and resp.status_code == 500 and "session" in resp.text.lower():
            params["authSessionKey"] = self._session(fresh=True) or ""  # it ran out
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
        """Paintings of a style; with nothing asked, the most viewed ones."""
        if spec.highlight or spec.kind not in ("any", "painting"):
            return 0, []
        return self._results(spec.style.strip(), limit, page)

    def fetch(self, source_id: str) -> Item | None:
        resp = self.http.get(f"{self.api}/Painting", params={"id": source_id})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body = resp.json()
        return self._map(body) if isinstance(body, dict) else None


# Collections added later live in modules of their own (they build on the
# classes above).
from .courtauld import CourtauldGallery  # noqa: E402
from .getty import GettyMuseum  # noqa: E402
from .loc import LibraryOfCongress  # noqa: E402
from .louvre import Louvre  # noqa: E402
from .muza import NationalMuseumKrakow, NationalMuseumWarsaw  # noqa: E402
from .nga import NationalGalleryOfArt  # noqa: E402
from .paris import ParisMusees  # noqa: E402
from .smithsonian import Smithsonian  # noqa: E402
from .vam import VictoriaAndAlbert  # noqa: E402
from .wellcome import WellcomeCollection  # noqa: E402
from .yale import YaleMuseums  # noqa: E402

MUSEUMS: dict[str, type[Museum]] = {
    m.key: m
    for m in (
        ArtInstituteChicago,
        ClevelandMuseum,
        MetropolitanMuseum,
        Rijksmuseum,
        NationalGalleryOfArt,
        NationalMuseumWarsaw,
        NationalMuseumKrakow,
        YaleMuseums,
        Smithsonian,
        ParisMusees,
        VictoriaAndAlbert,
        WellcomeCollection,
        CourtauldGallery,
        GettyMuseum,
        Louvre,
        LibraryOfCongress,
        WikimediaCommons,
        Europeana,
        Openverse,
        StatensMuseum,
        WikiArt,
    )
}


def available(access: Access) -> dict[str, type[Museum]]:
    """The sources on offer: those of "Użytek prywatny" just with it, those
    needing a key just with one, none the owner turned off."""
    return {k: m for k, m in MUSEUMS.items() if m.offered(access) and k not in access.sources_off}


def reachable(access: Access) -> list[str]:
    """The sources that may answer, those turned off too: what finds the
    works of museums chosen in Szukaj (:data:`PLACES_WD`)."""
    return [k for k, m in MUSEUMS.items() if m.offered(access)]


#: A search of chosen places rather than of a source (Szukaj's "Muzeum"):
#: ``wd:Q160112|Q1`` their works through Wikidata and Commons,
#: ``europeana:Q2`` Europeana's works from their data providers.
PLACES_WD = "wd:"
PLACES_EUROPEANA = "europeana:"


def places_in(key: str) -> tuple[str, ...]:
    """The places of a key of a places' search, () for a source's key."""
    for prefix in (PLACES_WD, PLACES_EUROPEANA):
        if key.startswith(prefix):
            return tuple(p for p in key[len(prefix) :].split("|") if p)
    return ()


def museum(key: str, http: httpx.Client, access: Access | bool = False) -> Museum:
    if isinstance(access, bool):
        access = Access(private_use=access)
    # A source turned off still fetches its works the catalogue or a
    # chosen museum's search has (a Prado painting from Commons).
    sources = {k: MUSEUMS[k] for k in reachable(access)}
    if key.startswith(PLACES_WD) and WikimediaCommons.offered(access):
        from .wikidata_places import WikidataPlaces

        return WikidataPlaces(http, access=access, places=places_in(key))
    if key.startswith(PLACES_EUROPEANA) and Europeana.offered(access):
        from .places import known_places

        found = Europeana(http, access=access)
        named = (known_places().provider(p) for p in places_in(key))
        found.providers = tuple(dict.fromkeys(n for n in named if n))
        if not found.providers:
            raise KeyError(f"no Europeana provider for {key!r}")
        return found
    if key not in sources:
        raise KeyError(f"unknown museum {key!r}; choose from {sorted(sources)}")
    return sources[key](http, access=access)
