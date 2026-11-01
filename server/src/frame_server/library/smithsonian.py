"""Smithsonian Open Access: the art museums of the Smithsonian Institution.

The Smithsonian American Art Museum, the National Portrait Gallery, the
National Museum of Asian Art (Freer and Sackler), the Hirshhorn and Cooper
Hewitt answer through one API at api.si.edu. It needs a free api.data.gov
key (1000 requests an hour), entered in the app; without one the
source is not offered. Only pictures marked CC0 are taken; they come from
the IDS image server in any size.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .models import Item
from .museums import Access, Discovery, Museum

IDS = "https://ids.si.edu/ids/deliveryService"
#: Art museums asked (the rest of the Smithsonian is science and history).
UNITS = ("SAAM", "NPG", "FSG", "HMSG", "CHNDM", "NMAfA")  # FSG finds nothing yet


class Smithsonian(Museum):
    key = "si"
    name = "Smithsonian"
    api = "https://api.si.edu/openaccess/api/v1.0"
    page_size = 100

    @classmethod
    def offered(cls, access: Access) -> bool:
        return bool(access.smithsonian_key)

    kinds: ClassVar[dict[str, str]] = {
        "painting": "Paintings",
        "drawing": "Drawings",
        "print": "Prints",
        "poster": "Posters",
        "photograph": "Photographs",
        "sculpture": "Sculpture",
    }
    units: ClassVar[dict[str, str]] = {
        "SAAM": "Smithsonian American Art Museum",
        "NPG": "National Portrait Gallery",
        "FSG": "National Museum of Asian Art",
        "HMSG": "Hirshhorn Museum and Sculpture Garden",
        "CHNDM": "Cooper Hewitt, Smithsonian Design Museum",
        "NMAfA": "National Museum of African Art",
    }

    @staticmethod
    def _free(content: dict[str, Any], field: str, label: str = "") -> list[str]:
        entries = (content.get("freetext") or {}).get(field) or []
        return [
            str(e.get("content") or "")
            for e in entries
            if e.get("content") and (not label or str(e.get("label") or "").startswith(label))
        ]

    def _map(self, row: dict[str, Any]) -> Item | None:
        content = row.get("content") or {}
        about = content.get("descriptiveNonRepeating") or {}
        media = [
            m
            for m in (about.get("online_media") or {}).get("media") or []
            if m.get("type") == "Images"
            and (m.get("usage") or {}).get("access") == "CC0"
            and m.get("idsId")
        ]
        if not media or not row.get("id"):
            return None
        picture = media[0]
        resource: dict[str, Any] = next(
            (r for r in picture.get("resources") or [] if r.get("label") == "High-resolution JPEG"),
            {},
        )
        indexed = content.get("indexedStructured") or {}
        names = self._free(content, "name", "Artist") or self._free(content, "name")
        artist, bio = names[0] if names else "", ""
        # "Thomas Eakins, 25 Jul 1844 - 25 Jun 1916", "Wilhelm Funk, born Hanover 1866"
        dated = re.match(r"^(.*?),\s*((?:born\b|\d|active\b|ca\.).*\d{4}.*)$", artist)
        if dated:
            artist, bio = dated.group(1), dated.group(2)
        dates = self._free(content, "date")
        decades = indexed.get("date") or []
        found = [m for d in [*dates, *decades] if (m := re.search(r"\d{4}", str(d)))]
        year = int(found[0].group(0)) if found else None
        unit = str(row.get("unitCode") or about.get("unit_code") or "")
        title = (about.get("title") or {}).get("content") or row.get("title") or ""
        width = resource.get("width") or picture.get("width")
        return self._item(
            str(row["id"]),
            title=str(title),
            artist=artist,
            artist_bio=bio,
            date_text=dates[0] if dates else "",
            year=year,
            medium=", ".join(self._free(content, "physicalDescription", "Medium")),
            classification=", ".join(indexed.get("object_type") or []),
            styles=[],
            subjects=[str(t) for t in indexed.get("topic") or []][:12],
            culture=", ".join(indexed.get("culture") or []),
            credit=", ".join([self.units.get(unit, unit), *self._free(content, "creditLine")][:2]),
            license="CC0 1.0",
            url=str(about.get("record_link") or about.get("guid") or ""),
            museum=self.units.get(unit, self.name),
            description=" ".join(self._free(content, "notes", "Description"))[:2000],
            image_url=f"{IDS}?id={picture['idsId']}&max=2560",
            thumb_url=f"{IDS}?id={picture['idsId']}&max=600",
            width=int(width) if width else None,
            height=int(height)
            if (height := resource.get("height") or picture.get("height"))
            else None,
        )

    def _item(self, source_id: str, **fields: Any) -> Item:
        museum = fields.pop("museum", self.name)
        return super()._item(source_id, **fields).model_copy(update={"museum": museum})

    def _get(self, words: list[str], limit: int, page: int) -> tuple[int, list[Item]]:
        key = self.access.smithsonian_key
        if not key:
            return 0, []
        units = " OR ".join(f'unit_code:"{u}"' for u in UNITS)
        query = " AND ".join([*words, "online_media_type:Images", f"({units})"])
        resp = self.http.get(
            f"{self.api}/category/art_design/search",
            params={"q": query, "start": (page - 1) * limit, "rows": limit, "api_key": key},
        )
        resp.raise_for_status()
        body = resp.json().get("response") or {}
        items = [i for r in body.get("rows") or [] if (i := self._map(r))]
        return int(body.get("rowCount") or len(items)), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        words = [f"({query.strip()})"] if query.strip() else ['object_type:"Paintings"']
        return self._get(words, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.highlight or spec.kind == "decorative":
            return 0, []
        words = [f'object_type:"{self.kinds.get(spec.kind, "Paintings")}"']
        if spec.style.strip():
            words.insert(0, f"({spec.style.strip()})")
        if spec.year_from is not None or spec.year_to is not None:
            first = (spec.year_from if spec.year_from is not None else 1500) // 10 * 10
            last = spec.year_to if spec.year_to is not None else 2000
            decades = [f'date:"{d}s"' for d in range(first, last + 1, 10)]
            if len(decades) <= 60:
                words.append(f"({' OR '.join(decades)})")
        return self._get(words, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        key = self.access.smithsonian_key
        if not key:
            return None
        resp = self.http.get(f"{self.api}/content/{source_id}", params={"api_key": key})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        row = resp.json().get("response")
        return self._map(row) if isinstance(row, dict) else None
