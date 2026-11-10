"""The works of chosen places through Wikidata, for museums with no source of
their own (Szukaj's "Muzeum": Prado, Uffizi, the cathedral in Ghent).

Wikidata knows where many paintings are (their collection, P195) and their
picture on Commons (P18). Its own search finds them by those statements
(``haswbstatement``), and by words in their labels, through the wikis'
Action API: no query service, whose limits are far stricter. The pictures
come from Commons as any Commons work (``wmc``), with the place they are in
already known (``Item.place``)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .models import Item
from .museums import Access, Discovery, Kind, Museum, WikimediaCommons, plain_text
from .places import known_places
from .wikidata import API, Wikidata

log = logging.getLogger(__name__)

#: What a work is (P31), for each kind asked for: paintings, watercolours,
#: drawings and prints; sculpture and the rest stay with the museums' own.
KINDS: dict[str, tuple[str, ...]] = {
    "any": ("Q3305213", "Q18761202", "Q93184", "Q11060274"),
    "painting": ("Q3305213", "Q18761202"),
    "drawing": ("Q93184",),
    "print": ("Q11060274",),
}
#: How a kind of work is classified on the item.
CLASSIFICATION = {
    "Q3305213": "Painting",
    "Q18761202": "Painting",
    "Q93184": "Drawing",
    "Q11060274": "Print",
}
#: Wikidata items asked about at once (the API's limit).
BATCH = 50


def statements(prop: str, values: tuple[str, ...]) -> str:
    """A search term for any of ``values`` of ``prop``
    (``haswbstatement:"P195=Q1|P195=Q2"``)."""
    return 'haswbstatement:"' + "|".join(f"{prop}={v}" for v in values) + '"'


def claim_ids(entity: dict[str, Any], prop: str) -> list[str]:
    out: list[str] = []
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            out.append(value["id"])
        elif isinstance(value, str):
            out.append(value)
    return out


class WikidataPlaces(Museum):
    key = "wd"
    name = "Wikidata"
    draws = False

    def __init__(
        self,
        http: httpx.Client,
        private_use: bool = False,
        access: Access | None = None,
        places: tuple[str, ...] = (),
    ) -> None:
        super().__init__(http, private_use, access)
        self.places = tuple(p for p in places if p.startswith("Q"))

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        return self.search_kind(query, "any", limit, page)

    def search_kind(
        self, query: str, kind: Kind, limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        query = plain_text(query)
        kinds = KINDS.get(kind)
        if not self.places or kinds is None:
            return 0, []
        words = " ".join(
            [
                query.strip(),
                statements("P195", self.places),
                statements("P31", kinds),
                "haswbstatement:P18",
            ]
        ).strip()
        resp = self.http.get(
            API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": words,
                "srnamespace": 0,
                "srlimit": limit,
                "sroffset": (page - 1) * limit,
                "srinfo": "totalhits",
                "srprop": "",
                "format": "json",
            },
        )
        resp.raise_for_status()
        body = resp.json().get("query", {})
        total = int((body.get("searchinfo") or {}).get("totalhits") or 0)
        qids = [str(hit["title"]) for hit in body.get("search") or [] if hit.get("title")]
        return total, self._works(qids)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        """The places' works, without words (a place alone chosen)."""
        if spec.highlight:
            return 0, []
        return self.search_kind(spec.style, spec.kind, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        return None  # its works are Commons files (``wmc``)

    def _works(self, qids: list[str]) -> list[Item]:
        """The works ``qids`` as Commons' files, in their order."""
        if not qids:
            return []
        entities: dict[str, Any] = {}
        for start in range(0, len(qids), BATCH):
            entities.update(Wikidata._entities(self.http, qids[start : start + BATCH], "claims"))
        files: dict[str, tuple[str, str, str]] = {}  # qid → (file, place, classification)
        for qid in qids:
            entity = entities.get(qid) or {}
            pictures = claim_ids(entity, "P18")
            here = [p for p in claim_ids(entity, "P195") if p in self.places]
            if not pictures or not here:
                continue
            kind = next(
                (CLASSIFICATION[k] for k in claim_ids(entity, "P31") if k in CLASSIFICATION),
                "Painting",
            )
            files[qid] = (pictures[0], here[0], kind)
        commons = WikimediaCommons(self.http, access=self.access)
        pages: dict[str, dict[str, Any]] = {}
        names = [f"File:{f}" for f, _, _ in files.values()]
        for start in range(0, len(names), BATCH):
            resp = self.http.get(
                commons.api, params=commons._params(titles="|".join(names[start : start + BATCH]))
            )
            resp.raise_for_status()
            body = resp.json().get("query", {})
            renamed = {n["to"]: n["from"] for n in body.get("normalized") or []}
            for page in (body.get("pages") or {}).values():
                title = str(page.get("title") or "")
                pages[renamed.get(title, title)] = page
        places = known_places()
        items: list[Item] = []
        for name, place, kind in files.values():
            page = pages.get(f"File:{name}")
            if page is None or "pageid" not in page:
                continue
            item = commons._map(page, classification=kind, any_year=True)
            if item is None:
                continue
            holder = places.name(place)
            items.append(item.model_copy(update={"place": place, "holder": holder or item.holder}))
        return items
