"""Victoria and Albert Museum, London: an open API without a key.

The V&A's pictures are not openly licensed: its terms allow personal,
non-commercial use, so the source is offered only with "Użytek prywatny"
(the frame is seen at home only). Works made before 1900 only, so that no
artist's own rights are still running. Pictures come over IIIF (most about
2500 px).
"""

from __future__ import annotations

from typing import Any, ClassVar

from .models import Item
from .museums import Access, Discovery, Museum, _person

#: Latest year of making asked for.
LAST_YEAR = 1899


class VictoriaAndAlbert(Museum):
    key = "vam"
    name = "Victoria and Albert Museum"
    api = "https://api.vam.ac.uk/v2"
    page_size = 100

    @classmethod
    def offered(cls, access: Access) -> bool:
        return access.private_use

    licence = "© Victoria and Albert Museum, London (użytek prywatny)"
    kinds: ClassVar[dict[str, str]] = {
        "painting": "painting",
        "drawing": "drawing",
        "print": "print",
        "poster": "poster",
        "photograph": "photograph",
        "sculpture": "sculpture",
    }

    def _map(self, d: dict[str, Any]) -> Item | None:
        images = d.get("_images") or {}
        iiif = str(images.get("_iiif_image_base_url") or "").rstrip("/")
        number = d.get("systemNumber")
        if not iiif or not number:
            return None
        maker = d.get("_primaryMaker") or {}
        name = str(maker.get("name") or "")
        date = str(d.get("_primaryDate") or "")
        year = next((int(w) for w in date.replace("-", " ").split() if w.isdigit()), None)
        return self._item(
            str(number),
            title=str(d.get("_primaryTitle") or d.get("objectType") or ""),
            artist=_person(name.replace(" (RA)", "")) if name.lower() != "unknown" else "",
            date_text=date,
            year=year,
            classification=str(d.get("objectType") or ""),
            culture=str(d.get("_primaryPlace") or ""),
            credit=f"{self.name}, {d['accessionNumber']}"
            if d.get("accessionNumber")
            else self.name,
            license=self.licence,
            url=f"https://collections.vam.ac.uk/item/{number}/",
            image_url=f"{iiif}/full/!2560,2560/0/default.jpg",
            thumb_url=f"{iiif}/full/!600,600/0/default.jpg",
        )

    def _get(self, params: dict[str, Any], limit: int, page: int) -> tuple[int, list[Item]]:
        if not self.private_use:
            return 0, []
        year_to = params.pop("year_made_to", LAST_YEAR)
        resp = self.http.get(
            f"{self.api}/objects/search",
            params={
                **params,
                "images_exist": 1,
                "year_made_to": min(int(year_to), LAST_YEAR),
                "page": page,
                "page_size": limit,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        items = [i for d in body.get("records") or [] if (i := self._map(d))]
        return int((body.get("info") or {}).get("record_count") or len(items)), items

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if not query.strip():
            return self._get({"q_object_type": "painting"}, limit, page)
        return self._get({"q": query.strip()}, limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        if spec.highlight or spec.kind == "decorative":
            return 0, []
        if spec.year_from is not None and spec.year_from > LAST_YEAR:
            return 0, []
        params: dict[str, Any] = {"q_object_type": self.kinds.get(spec.kind, "painting")}
        if spec.style.strip():
            params["q"] = spec.style.strip()
        if spec.year_from is not None:
            params["year_made_from"] = spec.year_from
        if spec.year_to is not None:
            params["year_made_to"] = spec.year_to
        return self._get(params, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        if not self.private_use:
            return None
        resp = self.http.get(f"{self.api}/objects/search", params={"q": source_id, "page_size": 5})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        found = [d for d in resp.json().get("records") or [] if d.get("systemNumber") == source_id]
        return self._map(found[0]) if found else None
