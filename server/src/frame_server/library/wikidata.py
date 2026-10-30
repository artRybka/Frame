"""What Wikidata knows about a museum's work, for its Polish texts.

Wikidata links many works to their museum records (the Met's object id,
Cleveland's accession number, ...). From there it gives an established
Polish title, when the work has one, what the work depicts (P180) in
Polish, the author's gender, for "Holender" or "Holenderka", and the
Wikipedia articles a note can lean on. Few works have Polish labels (the
Met: 177 of ~12 900 paintings), so everything here is optional.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .models import Item
from .nationality import Gender

API = "https://www.wikidata.org/w/api.php"

#: Source → the Wikidata property holding its record id.
PROPERTIES = {
    "met": "P3634",  # Met object ID
    "aic": "P4610",  # Art Institute of Chicago artwork ID
    "cma": "P11110",  # Cleveland Museum of Art ID: the accession number
    "rijks": "P13234",  # Rijksmuseum ID (Linked Art)
    "wikiart": "P6002",  # WikiArt ID: "artist/work"
}

#: P21 (sex or gender) values.
GENDERS: dict[str, Gender] = {
    "Q6581097": "male",
    "Q6581072": "female",
    "Q2449503": "male",  # trans man
    "Q1052281": "female",  # trans woman
}


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


def _label(entity: dict[str, Any], lang: str) -> str:
    return str((entity.get("labels") or {}).get(lang, {}).get("value") or "")


def _ids(entity: dict[str, Any], prop: str) -> list[str]:
    out = []
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            out.append(value["id"])
    return out


class Wikidata:
    """Facts by item id, kept in memory; ``None`` when Wikidata has none."""

    def __init__(self) -> None:
        self._known: dict[str, Facts | None] = {}
        self._lock = threading.Lock()

    def facts(self, http: httpx.Client, item: Item) -> Facts | None:
        with self._lock:
            if item.id in self._known:
                return self._known[item.id]
        ref = record_id(item)
        if ref is None:
            return None
        try:
            qid = self._find(http, *ref)
            facts = self._facts(http, qid) if qid else None
        except (httpx.HTTPError, ValueError, KeyError):
            return None  # not remembered: asked again next time
        with self._lock:
            self._known[item.id] = facts
        return facts

    @staticmethod
    def _find(http: httpx.Client, prop: str, value: str) -> str | None:
        resp = http.get(
            API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"haswbstatement:{prop}={value}",
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


def wikipedia_text(http: httpx.Client, lang: str, title: str, chars: int = 8000) -> str:
    """A Wikipedia article as plain text, cut to about ``chars``; "" when
    unavailable. Longer than the opening paragraph: what a work led to is
    usually further down ("Legacy", "Wpływ")."""
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
    return text[:chars].rsplit("\n", 1)[0]
