"""What Wikidata knows about a museum's work, for its Polish texts.

Wikidata links many works to their museum records (the Met's object id,
Cleveland's accession number, ...). From there it gives an established
Polish title, when the work has one, what the work depicts (P180) in
Polish, the author's gender, for "Holender" or "Holenderka", and the
Wikipedia articles a note can lean on. Few works have Polish labels (the
Met: 177 of ~12 900 paintings), so everything here is optional.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .models import Item
from .nationality import Gender
from .records import Records

API = "https://www.wikidata.org/w/api.php"

#: Source → the Wikidata property holding its record id.
PROPERTIES = {
    "met": "P3634",  # Met object ID
    "aic": "P4610",  # Art Institute of Chicago artwork ID
    "cma": "P11110",  # Cleveland Museum of Art ID: the accession number
    "rijks": "P13234",  # Rijksmuseum ID (Linked Art)
    "wikiart": "P6002",  # WikiArt ID: "artist/work"
    "louvre": "P9394",  # Louvre Museum ARK ID: the number without "cl"
}

#: Sources whose works Wikidata knows by another record id, used for their
#: Commons file only (counted 2026-11-08: works with the id / with a file).
COMMONS_IDS = {
    "nga": "P4683",  # National Gallery of Art artwork ID: 127 915 / 53 090
    "paris": "P6246",  # Paris Musées work ID, the node: 8751 / 4522
    "vam": "P3929",  # V&A item ID, the system number "O115274": 434 / 322
}
#: Yale's museums by the start of the id ("yuag-25955"): Yale University Art
#: Gallery ID (19 694 / 14 990), Yale Center for British Art's TMS id (30 388
#: / 30 384).
YALE = {"yuag": "P8583", "ycba": "P9789"}
#: Smithsonian resource ID: "saam_1909.7.35" of "edanmdm-saam_1909.7.35"
#: (18 125 / 6229).
SMITHSONIAN = "P7851"


@dataclass(frozen=True)
class Inventory:
    """How Wikidata tells one museum's inventory numbers (P217) from
    another's: every number carries the museum's ``mark`` ("MNK XII-209",
    "MP 431 MNW"), or the number's statement names the museum's item
    (``collection``, its P195 qualifier). ``in_credit``: the number is the
    credit line's last part, else the work's record id."""

    mark: str = ""
    collection: str = ""
    in_credit: bool = True


#: Sources whose works Wikidata knows by their inventory number.
INVENTORIES = {
    "mnk": Inventory(mark="MNK"),
    "mnw": Inventory(mark="MNW"),
    "smk": Inventory(collection="Q671384", in_credit=False),  # 7005 / 4741
    "courtauld": Inventory(collection="Q12110695"),  # 529 / 380
}
#: Wikidata's property of an inventory number.
INVENTORY = "P217"
#: Sources whose pictures Commons keeps by the work's Wikidata item.
MIRRORED = frozenset(
    [*(k for k in PROPERTIES if k != "wikiart"), *COMMONS_IDS, "yale", "si", *INVENTORIES]
)

#: P21 (sex or gender) values.
GENDERS: dict[str, Gender] = {
    "Q6581097": "male",
    "Q6581072": "female",
    "Q2449503": "male",  # trans man
    "Q1052281": "female",  # trans woman
}


def _facts_from(record: Any) -> Facts | None:
    """Facts as kept on disk (tuples come back as lists)."""
    if not isinstance(record, dict):
        return None
    try:
        return Facts(
            qid=str(record["qid"]),
            title_pl=str(record.get("title_pl") or ""),
            depicts_pl=tuple(record.get("depicts_pl") or ()),
            depicts_en=tuple(record.get("depicts_en") or ()),
            creator_gender=record.get("creator_gender"),
            wiki_pl=str(record.get("wiki_pl") or ""),
            wiki_en=str(record.get("wiki_en") or ""),
        )
    except (KeyError, TypeError):
        return None


@dataclass(frozen=True)
class Facts:
    qid: str
    title_pl: str = ""
    depicts_pl: tuple[str, ...] = ()
    #: What the work depicts, where Wikidata has no Polish label.
    depicts_en: tuple[str, ...] = ()
    creator_gender: Gender | None = None
    #: Titles of the Wikipedia articles about the work.
    wiki_pl: str = ""
    wiki_en: str = ""


def record_id(item: Item) -> tuple[str, str] | None:
    """(property, value) that finds ``item`` on Wikidata, if its source has one."""
    prop = PROPERTIES.get(item.source)
    if prop is None:
        return None
    if item.source == "cma":  # the record id is numeric; Wikidata has the accession
        value = urlsplit(item.url).path.rstrip("/").rsplit("/", 1)[-1]
    elif item.source == "wikiart":  # "https://www.wikiart.org/en/<artist>/<work>"
        parts = urlsplit(item.url).path.strip("/").split("/")
        value = "/".join(parts[1:3]) if len(parts) >= 3 else ""
    else:
        value = item.source_id
    return (prop, value) if value else None


def inventory_number(item: Item) -> str:
    """The museum's inventory number of ``item``, when its source is one
    Wikidata knows by it (:data:`INVENTORIES`); "" otherwise. The Polish
    museums and the Courtauld give it after their name in the credit line."""
    known = INVENTORIES.get(item.source)
    if known is None:
        return ""
    if known.in_credit:
        number = item.credit.rsplit(", ", 1)[-1].strip() if item.credit else ""
    else:
        number = item.source_id
    if not number or (known.mark and not re.search(rf"\b{known.mark}\b", number)):
        return ""
    return number


def commons_ref(item: Item) -> tuple[str, str] | None:
    """(property, value) that finds ``item`` on Wikidata for its Commons
    file: its record id, as :func:`record_id` or by the ids used for that
    only, else its inventory number."""
    if (ref := record_id(item)) is not None:
        return ref
    if (prop := COMMONS_IDS.get(item.source)) is not None:
        return (prop, item.source_id) if item.source_id else None
    if item.source == "yale":
        museum, _, number = item.source_id.partition("-")
        return (YALE[museum], number) if museum in YALE and number.isdigit() else None
    if item.source == "si":
        value = item.source_id.removeprefix("edanmdm-")
        return (SMITHSONIAN, value) if value and value != item.source_id else None
    if number := inventory_number(item):
        return (INVENTORY, number)
    return None


def _label(entity: dict[str, Any], lang: str) -> str:
    return str((entity.get("labels") or {}).get(lang, {}).get("value") or "")


def _ids(entity: dict[str, Any], prop: str) -> list[str]:
    out = []
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            out.append(value["id"])
    return out


#: Facts kept on disk under this name (library/records.py), by item id.
KEPT = "wikidata-facts"


class Wikidata:
    """Facts by item id, kept in memory and, with ``kept``, on disk for
    :data:`.records.KEEP_DAYS` (an update of the server asked Wikidata about
    every work again, 428 requests on 2026-11-07); ``None`` when Wikidata
    has none."""

    def __init__(self, kept: Records | None = None) -> None:
        self._known: dict[str, Facts | None] = {}
        self._lock = threading.Lock()
        self.kept = kept

    def facts(self, http: httpx.Client, item: Item) -> Facts | None:
        with self._lock:
            if item.id in self._known:
                return self._known[item.id]
        ref = record_id(item)
        if ref is None:
            return None
        if self.kept is not None:
            found, record = self.kept.get(KEPT, item.id)
            if found:
                facts = _facts_from(record)
                with self._lock:
                    self._known[item.id] = facts
                return facts
        try:
            qid = self._find(http, *ref)
            facts = self._facts(http, qid) if qid else None
        except (httpx.HTTPError, ValueError, KeyError):
            return None  # not remembered: asked again next time
        with self._lock:
            self._known[item.id] = facts
        if self.kept is not None:
            self.kept.put(KEPT, item.id, None if facts is None else asdict(facts))
        return facts

    @staticmethod
    def _find(http: httpx.Client, prop: str, value: str) -> str | None:
        resp = http.get(
            API,
            params={
                "action": "query",
                "list": "search",
                # A number with spaces ("MNK XII-209") whole, in quotes.
                "srsearch": f'haswbstatement:"{prop}={value}"'
                if not re.fullmatch(r"[\w.-]+", value)
                else f"haswbstatement:{prop}={value}",
                "srlimit": 1,
                "format": "json",
            },
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search") or []
        return str(hits[0]["title"]) if hits else None

    @staticmethod
    def _entities(http: httpx.Client, ids: list[str], props: str) -> dict[str, Any]:
        resp = http.get(
            API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": props,
                "languages": "pl|en",
                "sitefilter": "plwiki|enwiki",
                "format": "json",
            },
        )
        resp.raise_for_status()
        entities: dict[str, Any] = resp.json().get("entities") or {}
        return entities

    def _facts(self, http: httpx.Client, qid: str) -> Facts:
        work = self._entities(http, [qid], "labels|claims|sitelinks").get(qid) or {}
        depicts = _ids(work, "P180")[:20]
        labels = self._entities(http, depicts, "labels") if depicts else {}
        pl, en = [], []
        for ref in depicts:
            entity = labels.get(ref) or {}
            if label := _label(entity, "pl"):
                pl.append(label)
            elif label := _label(entity, "en"):
                en.append(label)
        gender = None
        if creators := _ids(work, "P170")[:1]:
            creator = self._entities(http, creators, "claims").get(creators[0]) or {}
            gender = next((GENDERS[g] for g in _ids(creator, "P21") if g in GENDERS), None)
        links = work.get("sitelinks") or {}
        return Facts(
            qid=qid,
            title_pl=_label(work, "pl"),
            depicts_pl=tuple(pl),
            depicts_en=tuple(en),
            creator_gender=gender,
            wiki_pl=str(links.get("plwiki", {}).get("title") or ""),
            wiki_en=str(links.get("enwiki", {}).get("title") or ""),
        )


def wikipedia_intro(http: httpx.Client, lang: str, title: str) -> str:
    """The opening paragraph of a Wikipedia article; "" when unavailable."""
    if not title:
        return ""
    try:
        resp = http.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
            + quote(title.replace(" ", "_"), safe="")
        )
        resp.raise_for_status()
        return str(resp.json().get("extract") or "")
    except (httpx.HTTPError, ValueError):
        return ""


#: A section heading in an article's plain text ("== Composition ==").
HEADING = re.compile(r"\n(?=={2,} [^=\n]+ ={2,}\n)")


def _sections_first(text: str, first: tuple[str, ...]) -> str:
    """``text`` with the opening and then the sections whose heading holds
    one of ``first`` (lower case) ahead of the rest, so that cutting the
    article does not cut them off."""
    parts = HEADING.split(text)
    head, rest = parts[0], parts[1:]

    def wanted(part: str) -> bool:
        heading = part.split("\n", 1)[0].casefold()
        return any(word in heading for word in first)

    ordered = [head, *[p for p in rest if wanted(p)], *[p for p in rest if not wanted(p)]]
    return "\n".join(ordered)


def wikipedia_text(
    http: httpx.Client, lang: str, title: str, chars: int = 8000, first: tuple[str, ...] = ()
) -> str:
    """A Wikipedia article as plain text, cut to about ``chars``; "" when
    unavailable. Longer than the opening paragraph: what a work led to is
    usually further down ("Legacy", "Wpływ"). Sections whose heading holds
    one of ``first`` come right after the opening when the article is cut."""
    if not title:
        return ""
    try:
        resp = http.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "redirects": 1,
                "titles": title,
                "format": "json",
            },
        )
        resp.raise_for_status()
        pages = (resp.json().get("query") or {}).get("pages") or {}
        text = next((str(p.get("extract") or "") for p in pages.values()), "")
    except (httpx.HTTPError, ValueError):
        return ""
    if len(text) <= chars:
        return text
    if first:
        text = _sections_first(text, first)
    return text[:chars].rsplit("\n", 1)[0]


#: Widths of a Commons copy: a grid's thumbnail, the card's and the frame's original.
COPY_THUMB_WIDTH = 960
COPY_WIDTH = 2560
#: Works whose Commons copy is remembered (found or not).
COPIES_KEPT = 4000


class CommonsCopies:
    """The museum's picture as Wikimedia Commons keeps it (the work's P18
    on Wikidata): another address for a museum whose image server turns
    programs away (the Art Institute of Chicago behind Cloudflare) or does
    not answer (the National Museum in Kraków's, 2026-11-07). The work is
    found by its record id or, for the Polish museums, by its inventory
    number."""

    def __init__(self, http: Callable[[], httpx.Client]) -> None:
        self.http = http
        self._known: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def __call__(self, item: Item, thumb: bool = False) -> list[str]:
        name = self.file(item)
        if not name:
            return []
        width = COPY_THUMB_WIDTH if thumb else COPY_WIDTH
        return [
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            + quote(name, safe="")
            + f"?width={width}"
        ]

    def file(self, item: Item) -> str:
        """The Commons file name of the work's picture; "" when Wikidata
        has none (remembered) or did not answer (asked again next time)."""
        with self._lock:
            if item.id in self._known:
                self._known.move_to_end(item.id)
                return self._known[item.id]
        ref = commons_ref(item)
        if ref is None:
            return ""
        try:
            with self.http() as http:
                qid = Wikidata._find(http, *ref)
                claims = Wikidata._entities(http, [qid], "claims").get(qid, {}) if qid else {}
        except (httpx.HTTPError, ValueError, KeyError):
            return ""
        name = ""
        if ref[0] == INVENTORY and not _holds(
            claims, INVENTORY, ref[1], INVENTORIES[item.source].collection
        ):
            claims = {}  # another museum's number, or part of a longer one
        for claim in (claims.get("claims") or {}).get("P18") or []:
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, str) and value:
                name = value
                break
        with self._lock:
            self._known[item.id] = name
            while len(self._known) > COPIES_KEPT:
                self._known.popitem(last=False)
        return name


def _holds(entity: dict[str, Any], prop: str, value: str, collection: str = "") -> bool:
    """Whether ``entity`` says ``value`` for ``prop`` word for word, in
    ``collection`` (its P195 qualifier) when one is given."""
    for claim in (entity.get("claims") or {}).get(prop) or []:
        if claim.get("mainsnak", {}).get("datavalue", {}).get("value") != value:
            continue
        if not collection:
            return True
        for qualifier in (claim.get("qualifiers") or {}).get("P195") or []:
            if (qualifier.get("datavalue", {}).get("value") or {}).get("id") == collection:
                return True
    return False
