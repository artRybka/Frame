"""Yale's art museums through LUX: the Yale Center for British Art and the
Yale University Art Gallery.

LUX searches every Yale collection and answers with record ids only; each
object's record names its IIIF manifest, and the manifest holds what the
frame needs (title, creator, date, medium, the picture in full size) and the
museum's copyright statement. Only works it calls "Public Domain" are taken.
A work's id is its manifest's path: ``ycba-34`` for ``ycba/obj/34``.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, ClassVar

import httpx

from .hosts import Resting, as_asked
from .models import Item
from .museums import Discovery, Museum

MANIFESTS = "https://manifests.collections.yale.edu"
#: Collections whose works are taken (LUX also holds books and specimens).
MUSEUMS = ("ycba", "yuag")


class YaleMuseums(Museum):
    key = "yale"
    name = "Yale"
    api = "https://lux.collections.yale.edu/api/search/item"
    #: Two requests per work.
    page_size = 24
    kinds: ClassVar[dict[str, tuple[str, ...]]] = {
        "painting": ("paintings",),
        "drawing": ("drawings",),
        "print": ("prints",),
        "poster": ("posters",),
        "photograph": ("photographs",),
        "sculpture": ("sculpture",),
    }
    pictures = ("paintings", "drawings", "prints")

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, dict):
            values: list[Any] = (
                value.get("en") or value.get("none") or next(iter(value.values()), [])
            )
            return "; ".join(str(v) for v in values)
        return str(value or "")

    def _map(self, source_id: str, m: dict[str, Any]) -> Item | None:
        meta = {
            self._text(e.get("label")): self._text(e.get("value")) for e in m.get("metadata") or []
        }
        if meta.get("Copyright Statement", "").strip().lower() != "public domain":
            return None
        try:
            canvas = m["items"][0]
            body = canvas["items"][0]["items"][0]["body"]
            service = body["service"][0]
        except (KeyError, IndexError, TypeError):
            return None
        iiif = str(service.get("@id") or service.get("id") or "").rstrip("/")
        if not iiif:
            return None
        creator = meta.get("Creator(s)") or meta.get("Creator") or ""
        creator = re.sub(r"^[A-Z][\w ]*:\s*", "", creator.split(";")[0]).strip()
        bio = ""
        bracket = re.match(r"^(.*?)\s*\((.*)\)\s*$", creator)
        if bracket:
            creator, bio = bracket.group(1), bracket.group(2)
        else:  # "J. M. W. Turner, born in London, ...", "John Buckler FSA, 1770–1851"
            creator = creator.split(", born")[0]
            dated = re.match(r"^(.*?),\s*(\d{4}\s*[–-]\s*\d{4})$", creator)
            if dated:
                creator, bio = dated.group(1), dated.group(2)
        title = meta.get("Title") or self._text(m.get("label"))
        date = meta.get("Date") or ""
        if not date:
            found = re.search(r",\s*([^,]*\d{3,4}[^,]*)$", self._text(m.get("label")))
            date = found.group(1).strip() if found else ""
        year = re.search(r"-?\d{3,4}", date)
        homepage = (m.get("homepage") or [{}])[0].get("id") or ""
        width = canvas.get("width")
        return self._item(
            source_id,
            title=title,
            artist=creator,
            artist_bio=bio,
            date_text=date,
            year=int(year.group(0)) if year else None,
            medium=meta.get("Medium", ""),
            classification=meta.get("Classification") or meta.get("Collection", ""),
            culture=meta.get("Culture", ""),
            credit=", ".join(
                p
                for p in (
                    meta.get("Institution"),
                    meta.get("Credit Line") or meta.get("Creditline"),
                )
                if p
            ),
            license="Public Domain",
            url=str(homepage),
            museum=meta.get("Institution") or self.name,
            description=meta.get("Alternative Text", ""),
            image_url=f"{iiif}/full/!2560,2560/0/default.jpg",
            thumb_url=f"{iiif}/full/{'full' if width and width <= 600 else '600,'}/0/default.jpg",
            width=width,
            height=canvas.get("height"),
        )

    def _item(self, source_id: str, **fields: Any) -> Item:
        museum = fields.pop("museum", self.name)
        item = super()._item(source_id, **fields)
        return item.model_copy(update={"museum": museum})

    def _manifest(self, record: str) -> str | None:
        """The manifest path (``ycba/obj/34``) of a LUX object record."""
        resp = self.http.get(record)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        found = re.search(rf"{MANIFESTS}/(?:v\d/)?((?:{'|'.join(MUSEUMS)})/obj/\d+)", resp.text)
        return found.group(1) if found else None

    def _one(self, record: str) -> Item | None:
        path = self._manifest(record)
        return self.fetch(path.replace("/obj/", "-")) if path else None

    def _search(self, terms: list[dict[str, Any]], limit: int, page: int) -> tuple[int, list[Item]]:
        query = {"AND": [*terms, {"hasDigitalImage": 1}]}
        resp = self.http.get(
            self.api,
            params={"q": json.dumps(query), "page": page, "pageLength": limit},
        )
        resp.raise_for_status()
        body = resp.json()
        total = int(((body.get("partOf") or [{}])[0]).get("totalItems") or 0)
        records = [o["id"] for o in body.get("orderedItems") or [] if o.get("id")]
        items: list[Item] = []
        with ThreadPoolExecutor(4) as pool:
            for result in pool.map(as_asked(self._safe), records):
                if isinstance(result, Resting):
                    raise result
                if isinstance(result, Item):
                    items.append(result)
        return total, items

    def _safe(self, record: str) -> Item | Exception | None:
        try:
            return self._one(record)
        except Resting as err:
            return err
        except httpx.HTTPError:
            return None

    def _kinds(self, names: tuple[str, ...]) -> dict[str, Any]:
        if len(names) == 1:
            return {"classification": {"name": names[0]}}
        return {"OR": [{"classification": {"name": n}} for n in names]}

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        terms: list[dict[str, Any]] = [self._kinds(self.pictures)]
        if query.strip():
            terms.insert(0, {"text": query.strip()})
        return self._search(terms, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.highlight or spec.kind == "decorative":
            return 0, []
        terms: list[dict[str, Any]] = [self._kinds(self.kinds.get(spec.kind, self.pictures))]
        if spec.style.strip():
            terms.insert(0, {"text": spec.style.strip()})
        if spec.year_from is not None:
            terms.append(
                {"producedDate": f"{spec.year_from:04d}-01-01T00:00:00.000Z", "_comp": ">="}
            )
        if spec.year_to is not None:
            terms.append({"producedDate": f"{spec.year_to:04d}-12-31T23:59:59.999Z", "_comp": "<="})
        return self._search(terms, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        museum, _, number = source_id.partition("-")
        if museum not in MUSEUMS or not number.isdigit():
            return None
        resp = self.http.get(f"{MANIFESTS}/{museum}/obj/{number}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._map(source_id, resp.json())
