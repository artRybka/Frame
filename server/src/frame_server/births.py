"""Artists' birthdays, for the "Rocznica" notification.

Only the artists of the owner's favourite works are asked about: Wikidata's
search by name, then the first human among the hits with a birth date to
the day, and only if the works' years fit a life that started then (a
namesake born two centuries off is someone else). Answers, a miss too, are
kept in the library's state, so each artist is looked up once a month at
most.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from .library.models import ItemKind, PlaylistRules

if TYPE_CHECKING:
    from .library import Item, Library

log = logging.getLogger(__name__)

WIKIDATA = "https://www.wikidata.org/w/api.php"
USER_AGENT = "Frame/1 (home art frame; https://github.com/artRybka/Frame)"
STATE_KEY = "artist_births"
# A miss is asked about again after this long (Wikidata grows).
RECHECK = timedelta(days=30)
_TIME = re.compile(r"^\+?(-?\d{1,4})-(\d{2})-(\d{2})T")
DAY_PRECISION = 11
HUMAN = "Q5"


def search_name(artist: str) -> str:
    """ "Monet, Claude" is searched as "Claude Monet"; dates in brackets go."""
    name = re.sub(r"\(.*?\)", "", artist).strip()
    if name.count(",") == 1:
        last, first = (p.strip() for p in name.split(","))
        if first and last:
            name = f"{first} {last}"
    return " ".join(name.split())


def _born(claims: dict[str, Any]) -> date | None:
    for claim in claims.get("P569") or []:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if not isinstance(value, dict) or int(value.get("precision", 0)) < DAY_PRECISION:
            continue
        match = _TIME.match(str(value.get("time", "")))
        if not match:
            continue
        year, month, day = (int(g) for g in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def _human(claims: dict[str, Any]) -> bool:
    for claim in claims.get("P31") or []:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(value, dict) and value.get("id") == HUMAN:
            return True
    return False


def fits(born: date, years: list[int]) -> bool:
    """Works made between the age of 10 and 100 (or no years to go by)."""
    return all(born.year + 10 <= y <= born.year + 100 for y in years)


class Births:
    def __init__(self, library: Library) -> None:
        self.library = library

    def _stored(self) -> dict[str, dict[str, str | None]]:
        return dict(self.library.get_state(STATE_KEY, {}))

    def born(self, artist: str) -> date | None:
        entry = self._stored().get(artist)
        text = entry.get("born") if entry else None
        return date.fromisoformat(text) if text else None

    def favourites(self) -> Counter[str]:
        """Artists of the favourite works, with how many there are."""
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK], favorites_only=True)
        items: list[Item] = self.library.query(rules)[1]
        return Counter(i.artist for i in items if i.artist)

    def _years(self, artist: str) -> list[int]:
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK], artists=[artist])
        return [i.year for i in self.library.query(rules)[1] if i.year]

    def missing(self, artists: list[str], now: datetime | None = None) -> list[str]:
        now = now or datetime.now(UTC)
        stored = self._stored()
        out = []
        for artist in artists:
            entry = stored.get(artist)
            if entry is None or (
                not entry.get("born")
                and entry.get("at")
                and datetime.fromisoformat(str(entry["at"])) < now - RECHECK
            ):
                out.append(artist)
        return out

    def look_up(self, artists: list[str], http: httpx.Client | None = None) -> int:
        """Ask Wikidata about ``artists``; how many answers were kept."""
        own = http is None
        client = http or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})
        kept = 0
        try:
            for artist in artists:
                try:
                    born = self._ask(client, artist)
                except (httpx.HTTPError, ValueError) as err:
                    log.info("no birthday of %s: %s", artist, err)
                    continue  # asked again next time
                stored = self._stored()
                stored[artist] = {
                    "born": born.isoformat() if born else None,
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                self.library.set_state(STATE_KEY, stored)
                kept += 1
        finally:
            if own:
                client.close()
        return kept

    def _ask(self, http: httpx.Client, artist: str) -> date | None:
        name = search_name(artist)
        if not name:
            return None
        resp = http.get(
            WIKIDATA,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "type": "item",
                "limit": 5,
                "format": "json",
            },
        )
        resp.raise_for_status()
        ids = [hit["id"] for hit in resp.json().get("search") or [] if "id" in hit]
        if not ids:
            return None
        resp = http.get(
            WIKIDATA,
            params={
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": "claims",
                "format": "json",
            },
        )
        resp.raise_for_status()
        entities = resp.json().get("entities") or {}
        years = self._years(artist)
        for qid in ids:
            claims = (entities.get(qid) or {}).get("claims") or {}
            if not _human(claims):
                continue
            born = _born(claims)
            if born is not None and fits(born, years):
                return born
        return None

    def today(self, day: date, artists: list[str]) -> list[tuple[str, date]]:
        """Those of ``artists`` born on ``day``'s date (29 February: on the
        28th in other years)."""
        found = []
        for artist in artists:
            born = self.born(artist)
            if born is None:
                continue
            month, mday = born.month, born.day
            if (month, mday) == (2, 29) and not _leap(day.year):
                mday = 28
            if (month, mday) == (day.month, day.day):
                found.append((artist, born))
        return found


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
