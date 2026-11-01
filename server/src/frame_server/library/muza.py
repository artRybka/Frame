"""Polish national museums on the Muza CMS (Warsaw and Kraków).

Both run the same collection site with a JSON API behind it (no key, not
documented): ``api/search/Object/page/<n>?filter[...]`` and
``api/object/<id>``. Each object carries the museum's own rights statement;
only those it marks "Domena publiczna" are asked for. Titles and texts are
Polish. Pictures: ``upload/multimedia/<path>.<ext>`` is the original
(4000–6000 px), ``upload/cache/multimedia_big/`` a 1024 px copy.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any, ClassVar
from urllib.parse import quote

from .models import Item
from .museums import Discovery, Museum, _person, strip_html


class MuzaMuseum(Museum):
    #: Root of the JSON API.
    api: ClassVar[str]
    #: Pictures, originals and resized copies.
    cdn: ClassVar[str]
    #: The collection site's page of one object.
    site: ClassVar[str]
    #: Id of the museum's "public domain" rights statement.
    public_domain: ClassVar[int]
    #: Object types (ids of the museum's dictionary) asked for each kind.
    types: ClassVar[dict[str, tuple[int, ...]]]
    page_size = 100

    #: The kind of work an object type is, in the words other sources use.
    classifications: ClassVar[dict[str, str]] = {
        "obraz": "Painting",
        "obraz dwustronny": "Painting",
        "malarstwo": "Painting",
        "szkic olejny": "Painting",
        "rysunek": "Drawing",
        "szkic": "Drawing",
        "rysunek w szkicowniku": "Drawing",
        "akwarela": "Drawing and Watercolor",
        "pastel": "Drawing",
        "gwasz": "Drawing",
        "odbitka graficzna": "Print",
        "grafika": "Print",
        "grafika (dzieło wizualne)": "Print",
        "grafika druku": "Print",
        "plakat": "Poster",
        "afisz": "Poster",
        "miniatura": "Painting",
        "rzeźba": "Sculpture",
        "fotografia": "Photograph",
        "odbitka fotograficzna": "Photograph",
    }

    def _pictures(self) -> tuple[int, ...]:
        """Types searched when no kind is asked: pictures, not postcards,
        reproductions or archive papers."""
        return tuple(
            t for kind in ("painting", "drawing", "print", "poster") for t in self.types[kind]
        )

    def _object_url(self, path: str, size: str = "") -> str:
        folder = f"upload/cache/{size}/" if size else "upload/multimedia/"
        return f"{self.cdn}/{folder}{path}"

    @staticmethod
    def _year(text: str) -> int | None:
        """The year of a Polish date: "ok. 1880", "1880-1890", "lata 80. XIX w.",
        "koniec XIX w."."""
        match = re.search(r"\b(\d{4})\b", text)
        if match:
            return int(match.group(1))
        century = re.search(r"\b([IVX]+)\s*w\.?", text)
        if not century:
            return None
        numerals = {"I": 1, "V": 5, "X": 10}
        letters = century.group(1)
        value = 0
        for i, letter in enumerate(letters):
            n = numerals[letter]
            value += -n if i + 1 < len(letters) and numerals[letters[i + 1]] > n else n
        start = (value - 1) * 100
        decade = re.search(r"\blata\s+(\d0)", text)
        if decade:
            return start + int(decade.group(1))
        for word, offset in (("pocz", 10), ("poł", 50), ("koni", 90), ("schył", 90)):
            if word in text.lower():
                return start + offset
        return start + 50

    def _map(self, d: dict[str, Any], *, checked: bool = True) -> Item | None:
        """An object as an item; ``checked`` when the search asked for public
        domain works only (a single object says so itself)."""
        image = d.get("image") or {}
        path, ext = image.get("filePath") or "", image.get("extension") or ""
        if not path or ext.lower() not in ("jpg", "jpeg", "png") or not d.get("id"):
            return None
        rights = d.get("copyrights")
        if rights is not None:
            checked = any(r.get("id") == self.public_domain for r in rights)
        if not checked:
            return None
        file = f"{path}.{ext}"
        authors = d.get("authors") or []
        makers = [a for a in authors if a.get("role") not in ("wydawca", "wydawnictwo")]
        maker = (makers or authors or [{}])[0]
        name = str(maker.get("name") or "")
        life = re.search(r"\(([^)]*\d{4}[^)]*)\)\s*$", name)
        dates = " ".join(str(c.get("name") or "") for c in d.get("createDates") or [])
        types = [str(t.get("name") or "") for t in d.get("types") or []]
        kind = next((self.classifications[t] for t in types if t in self.classifications), "")
        techniques = [str(t.get("name") or "") for t in d.get("techniques") or []]
        materials = [str(m.get("name") or "") for m in d.get("materials") or []]
        places = [str(p.get("name") or "") for p in d.get("createPlaces") or []]
        texts = [strip_html(t.get("description")) for t in d.get("publicDescriptions") or []]
        description = "\n\n".join(t for t in texts if t) or strip_html(d.get("description"))
        if description in types or len(description) < 25:
            description = ""  # "pocztówka bez obiegu" and the like
        return self._item(
            str(d["id"]),
            title=str(d.get("title") or ""),
            artist=_person(name),
            artist_bio=re.sub(r"\s*-\s*", "–", life.group(1)) if life else "",
            date_text=dates,
            year=self._year(dates),
            medium=", ".join(t for t in [*techniques, *materials] if t),
            classification=kind or (types[0] if types else ""),
            styles=[],
            subjects=[str(t.get("name") or "") for t in d.get("tags") or [] if t.get("name")][:12],
            culture=next((p for p in places if p and p != "nieznane"), ""),
            credit=f"{self.name}, {d['inventoryNumber']}" if d.get("inventoryNumber") else "",
            license="Public Domain Mark 1.0",
            url=f"{self.site}/{d['id']}",
            highlight=bool(d.get("masterpieces")),
            description=description,
            image_url=self._object_url(file),
            thumb_url=self._object_url(file, "multimedia_big"),
        )

    def _get(self, filters: list[str], limit: int, page: int) -> tuple[int, list[Item]]:
        query = "&".join(
            [*filters, f"filter[copyrights][]={self.public_domain}", "filter[formFeature][]=3"]
        )
        # The filters go in the URL as they are (``params`` would replace them).
        resp = self.http.get(f"{self.api}/search/Object/page/{page}?{query}&maxPerPage={limit}")
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        items = [i for d in data.get("items") or [] if (i := self._map(d))]
        total = int((data.get("paginatorDetails") or {}).get("totalItemsCount") or len(items))
        return total, items

    @staticmethod
    def _phrase(text: str) -> str:
        return f"filter[phrase]={quote(text, safe='')}"

    @staticmethod
    def _type_filters(ids: tuple[int, ...]) -> list[str]:
        return [f"filter[types][]={i}" for i in ids]

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        filters = self._type_filters(self._pictures())
        if query.strip():
            filters.append(self._phrase(polish(query.strip())))
        return self._get(filters, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        types = self.types.get(spec.kind) if spec.kind != "any" else self._pictures()
        if not types:
            return 0, []
        filters = self._type_filters(types)
        if spec.style.strip():
            filters.append(self._phrase(polish(spec.style.strip())))
        if spec.year_from is not None:
            filters.append(f"filter[createDates][from]={spec.year_from}")
        if spec.year_to is not None:
            filters.append(f"filter[createDates][to]={spec.year_to}")
        if spec.highlight:
            filters.append("filter[masterpieces]=1")
        return self._get(filters, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        if not source_id.isdigit():
            return None
        resp = self.http.get(f"{self.api}/object/{source_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json().get("data")
        return self._map(data, checked=False) if isinstance(data, dict) else None


@cache
def _names() -> dict[str, str]:
    """The Polish names of the app's styles and subjects, by the English
    word museums are asked ("landscape" -> "pejzaż")."""
    from .vocabulary import TERMS  # vocabulary imports the museums

    return {t.query: t.name.split(" i ")[0].lower() for t in TERMS if t.query}


def polish(text: str) -> str:
    """Words for a Polish catalogue: the app's English style and subject
    words in Polish, anything else as it is."""
    names = _names()
    whole = names.get(text.lower())
    if whole:
        return whole
    return " ".join(names.get(w.lower(), w) for w in text.split())


class NationalMuseumWarsaw(MuzaMuseum):
    """Muzeum Narodowe w Warszawie: ~7700 public-domain paintings with
    pictures (Malczewski, Chełmoński, Gierymski, Boznańska, Makowski)."""

    key = "mnw"
    name = "Muzeum Narodowe w Warszawie"
    api = "https://cyfrowe-api.mnw.art.pl/api"
    cdn = "https://cyfrowe-cdn.mnw.art.pl"
    site = "https://cyfrowe.mnw.pl/pl/katalog"
    public_domain = 500
    highlights = True
    types: ClassVar[dict[str, tuple[int, ...]]] = {
        "painting": (116727, 117008, 116652, 116732),
        "drawing": (116729, 116712, 116711, 116710, 116596),
        "print": (116061, 116786),
        "poster": (117009, 116602),
        "sculpture": (116728,),
        "photograph": (116704, 116963),
    }


class NationalMuseumKrakow(MuzaMuseum):
    """Muzeum Narodowe w Krakowie: ~2300 public-domain paintings with
    pictures (Leonardo's Lady with an Ermine, Matejko, Wyspiański, Mehoffer)."""

    key = "mnk"
    name = "Muzeum Narodowe w Krakowie"
    api = "https://api-zbiory.mnk.pl/api"
    cdn = "https://cdn-zbiory.mnk.pl"
    site = "https://zbiory.mnk.pl/pl/katalog"
    public_domain = 74188
    highlights = True
    types: ClassVar[dict[str, tuple[int, ...]]] = {
        "painting": (100489, 99813, 113913, 100380),
        "drawing": (100566, 113295, 113910, 113460, 99860),
        "print": (100433, 100041),
        "poster": (100134, 99969, 99988),
        "sculpture": (100003,),
        "photograph": (100457, 100452),
    }
