"""When artists died, for the EU copyright rule.

In Poland and the rest of the EU a work is free 70 years after its author's
death, counted from 1 January of the following year. American museums flag
works by US rules (roughly: published before 1931), so Kandinsky, Mondrian
or Matisse stay out of their open access although they are free here.

Death years come from Europeana's entity collection (built from Wikidata)
and from Wikidata itself, and are kept in memory: a source asks about the
same few artists over and over.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from datetime import date
from typing import Any

import httpx

#: Years of protection after the author's death (art. 36 of the Polish act).
TERM_YEARS = 70

EUROPEANA_AGENT = re.compile(r"^https?://data\.europeana\.eu/agent/(?:base/)?(\d+)$")
WIKIDATA_ENTITY = re.compile(r"^https?://www\.wikidata\.org/entity/(Q\d+)$")


def free_in_eu(death_year: int, today: date | None = None) -> bool:
    """True once the 70 years after ``death_year`` have run out."""
    return death_year + TERM_YEARS < (today or date.today()).year


def _year(text: str) -> int | None:
    match = re.match(r"^[+]?(-?\d{1,4})-", text)
    return int(match.group(1)) if match else None


def _fold(name: str) -> str:
    """Name for comparisons: "Matisse, Henri" and "henri matisse" match."""
    if "," in name:
        last, _, first = name.partition(",")
        name = f"{first} {last}"
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.casefold().split())


class LifeDates:
    """Death years of artists, by entity URI or by name; ``None`` when unknown
    or still alive."""

    europeana = "https://api.europeana.eu/entity"
    wikidata = "https://www.wikidata.org/w/api.php"

    def __init__(self, europeana_key: str = "api2demo") -> None:
        self.europeana_key = europeana_key
        self._known: dict[str, int | None] = {}
        self._lock = threading.Lock()

    def _cached(self, key: str) -> tuple[bool, int | None]:
        with self._lock:
            return key in self._known, self._known.get(key)

    def _keep(self, key: str, year: int | None) -> int | None:
        with self._lock:
            self._known[key] = year
        return year

    def death_year(self, http: httpx.Client, ref: str) -> int | None:
        """``ref``: a Europeana agent or Wikidata entity URI, or a name."""
        ref = ref.strip()
        if not ref:
            return None
        found, year = self._cached(ref)
        if found:
            return year
        try:
            if match := EUROPEANA_AGENT.match(ref):
                year = self._europeana_agent(http, match.group(1))
            elif match := WIKIDATA_ENTITY.match(ref):
                year = self._wikidata(http, match.group(1))
            elif ref.startswith(("http://", "https://")):
                year = None  # other authorities (ULAN, GND): no dates here
            else:
                year = self._europeana_name(http, ref)
        except (httpx.HTTPError, ValueError):
            return None  # not remembered: asked again next time
        return self._keep(ref, year)

    def _europeana_agent(self, http: httpx.Client, number: str) -> int | None:
        resp = http.get(
            f"{self.europeana}/agent/{number}.json", params={"wskey": self.europeana_key}
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._agent_year(resp.json())

    def _europeana_name(self, http: httpx.Client, name: str) -> int | None:
        """Only an exact name match counts: a near miss could be anyone."""
        resp = http.get(
            f"{self.europeana}/search",
            params={
                "wskey": self.europeana_key,
                "query": name,
                "type": "agent",
                "pageSize": 5,
            },
        )
        resp.raise_for_status()
        wanted = _fold(name)
        for agent in resp.json().get("items") or []:
            labels = [
                *(agent.get("prefLabel") or {}).values(),
                *(label for labels in (agent.get("altLabel") or {}).values() for label in labels),
            ]
            if any(_fold(str(label)) == wanted for label in labels):
                return self._agent_year(agent)
        return None

    @staticmethod
    def _agent_year(agent: dict[str, Any]) -> int | None:
        dates = agent.get("dateOfDeath") or []
        if isinstance(dates, str):  # one record: a string; search results: lists
            dates = [dates]
        years = [y for d in dates if isinstance(d, str) and (y := _year(d)) is not None]
        return max(years) if years else None

    def _wikidata(self, http: httpx.Client, qid: str) -> int | None:
        resp = http.get(
            self.wikidata,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            },
        )
        resp.raise_for_status()
        claims = resp.json().get("entities", {}).get(qid, {}).get("claims", {})
        years = []
        for claim in claims.get("P570") or []:  # date of death
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if isinstance(value, dict) and (y := _year(str(value.get("time", "")))) is not None:
                years.append(y)
        return max(years) if years else None
