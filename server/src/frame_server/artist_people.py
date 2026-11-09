"""Who the catalogue's artists are, as Wikidata knows them.

Museums spell one painter many ways ("Johannes Vermeer", "Jan Vermeer",
"Vermeer, Johannes") and two painters alike ("Jan Vermeer" of Delft, "Jan
Vermeer van Haarlem"): the words alone could not tell (Mateusz 2026-11-09,
"vermeer" in Szukaj gave two "Jan Vermeer" rows). Each spelling is looked up
once in Wikidata's search; the first person whose life fits the years of
its works is them (as :mod:`.births` does for birthdays). Spellings of one
item are one artist in the search (:class:`.library.artists.ArtistNames`),
and two items never are.

Asked some minutes after the server starts while any of the catalogue's
artists of several works was never asked, then at night for the new ones;
in the background's share of Wikimedia's pace (``library.hosts``), never
while the app is in use. A spelling Wikidata had no one for is asked again
after :data:`RECHECK`.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from .births import search_name
from .library.artists import IDS_STATE, PEOPLE_STATE, is_artist
from .library.hosts import Resting
from .library.wikidata import API

if TYPE_CHECKING:
    from .library import Library

log = logging.getLogger(__name__)

#: A spelling no one was found for is asked again after this long.
RECHECK = timedelta(days=60)
#: Spellings asked in one go at most: after a start, and in one night.
AFTER_START = 3000
A_NIGHT = 800
#: Seconds after a start before the first are asked (the server's own
#: start-up asks the museums first).
START_DELAY = 300.0
#: Spellings of this many works or more are asked; those of fewer when
#: their person has as many under all their spellings.
MIN_WORKS = 2
#: Wikidata items asked about at once (the API's limit).
BATCH = 50
#: Hits of the search looked at.
HITS = 7
#: Years a work may be made before its maker turned this old, or after
#: they died (prints of a painting, a late casting).
YOUNGEST, AFTER_DEATH = 10, 30
#: A life ends this long after it starts when Wikidata has no death.
LONGEST = 100
#: Share of a spelling's dated works the life must fit.
FITTING = 0.8
#: Words of a hit's description that make it someone who made art, for a
#: spelling with no dated work to go by.
_MAKER = re.compile(
    r"painter|artist|malarz|sculptor|engraver|printmaker|draughtsman|illustrator|"
    r"photographer|architect|designer|lithographer|etcher|woodcut|potter|ceramist|\d{3,4}",
    re.IGNORECASE,
)
SPARQL = "https://query.wikidata.org/sparql"
#: Of each item only whether it is a person, their years and two names: the
#: items themselves are hundreds of kilobytes each (Rembrandt's).
FACTS = """SELECT ?item ?human ?born ?died ?en ?pl WHERE {
  VALUES ?item { %s }
  BIND(EXISTS { ?item wdt:P31 wd:Q5 } AS ?human)
  OPTIONAL { ?item wdt:P569 ?b. BIND(YEAR(?b) AS ?born) }
  OPTIONAL { ?item wdt:P570 ?d. BIND(YEAR(?d) AS ?died) }
  OPTIONAL { ?item rdfs:label ?en. FILTER(LANG(?en) = "en") }
  OPTIONAL { ?item rdfs:label ?pl. FILTER(LANG(?pl) = "pl") }
}"""
#: Items asked about in one query.
FACTS_BATCH = 200
#: A request Wikidata failed (a 5xx, a timeout, no answer) is sent again
#: after each of these waits (seconds); a batch that still fails is left for
#: the next round and the round goes on, until FAILED_BATCHES in a row
#: failed. One 502 of query.wikidata.org ended the first round after 2200 of
#: 3000 spellings (Mateusz 2026-11-09). A 429 or a resting host
#: (``library.hosts``) still ends the round at once: it asked us to stop.
RETRY_WAITS = (15.0, 60.0)
FAILED_BATCHES = 3


def told_to_stop(err: Exception) -> bool:
    """Whether ``err`` asks us to leave Wikidata alone for now: a 429, or
    its host resting (``library.hosts``)."""
    if isinstance(err, Resting):
        return True
    return isinstance(err, httpx.HTTPStatusError) and err.response.status_code == 429


def _passing(err: httpx.HTTPError) -> bool:
    """Whether ``err`` is one that may pass: a server error, a timeout, a
    connection that broke."""
    if isinstance(err, httpx.HTTPStatusError):
        return err.response.status_code >= 500
    return isinstance(err, httpx.TransportError)


class Facts(dict[str, Any]):
    """An item's: ``human``, ``born``, ``died``, ``en``, ``pl``."""


def fits(born: int | None, died: int | None, years: list[int]) -> bool:
    """Whether most of ``years`` fall in a life from ``born`` to ``died``."""
    if born is None or not years:
        return born is not None or died is not None
    end = (died if died is not None else born + LONGEST) + AFTER_DEATH
    inside = sum(born + YOUNGEST <= y <= end for y in years)
    return inside >= FITTING * len(years)


class ArtistPeople:
    """Asks Wikidata who the catalogue's artists are."""

    def __init__(self, library: Library, http: Callable[[], httpx.Client]) -> None:
        self.library = library
        self.http = http
        self.sleep: Callable[[float], None] = time.sleep
        self._lock = threading.Lock()

    # -- what is kept --------------------------------------------------------------

    def ids(self) -> dict[str, list[str]]:
        """Each spelling asked: [its item ("" none), when asked]."""
        return dict(self.library.get_state(IDS_STATE, {}))

    def people(self) -> dict[str, dict[str, Any]]:
        """Each item found: its names ("en", "pl") and years ("born", "died")."""
        return dict(self.library.get_state(PEOPLE_STATE, {}))

    # -- what to ask -----------------------------------------------------------------

    def wanted(self, now: datetime | None = None) -> list[tuple[str, list[int]]]:
        """Spellings to ask about, those of the most works first, each with
        its works' years."""
        now = now or datetime.now(UTC)
        asked = self.ids()
        index = self.library.search_index()
        if index is None:
            return []
        names = self.library.term_index().names
        by_name = index.artists()
        of_person: dict[str, int] = {}
        for name, entries in by_name.items():
            shown = names.shown(name)
            of_person[shown] = of_person.get(shown, 0) + len(entries)
        out: list[tuple[int, str, list[int]]] = []
        for name, entries in by_name.items():
            if not is_artist(name):
                continue
            if len(entries) < MIN_WORKS and of_person.get(names.shown(name), 0) < MIN_WORKS:
                continue
            kept = asked.get(name)
            if kept is not None and (kept[0] or datetime.fromisoformat(kept[1]) > now - RECHECK):
                continue
            years = [i.year for i in index.items(entries) if i.year is not None]
            out.append((len(entries), name, years))
        out.sort(key=lambda w: (-w[0], w[1]))
        return [(name, years) for _, name, years in out]

    # -- asking ---------------------------------------------------------------------

    def after_start(self) -> int:
        """The first round, some minutes after a start."""
        return self.look_up(AFTER_START, why="after start")

    def at_night(self, quiet: Callable[[], bool] = lambda: True) -> int:
        return self.look_up(A_NIGHT, quiet, why="at night")

    def look_up(self, limit: int, quiet: Callable[[], bool] = lambda: True, why: str = "") -> int:
        """Asks about up to ``limit`` spellings; how many people were found.
        The search knows them at once after."""
        if not self._lock.acquire(blocking=False):
            return 0  # a round is under way
        try:
            wanted = self.wanted()[:limit]
            if not wanted:
                return 0
            started = time.monotonic()
            log.info("artist people %s: asking Wikidata about %d spellings", why, len(wanted))
            found = asked = failed = 0
            with self.http() as http:
                for start in range(0, len(wanted), BATCH):
                    if not quiet():
                        break
                    batch = wanted[start : start + BATCH]
                    try:
                        got = self._ask(http, batch)
                    except (httpx.HTTPError, ValueError) as err:
                        if told_to_stop(err):
                            log.info("artist people: %s", err)
                            break  # the rest next time
                        failed += 1
                        log.info(
                            "artist people: %s; %d spellings left for the next round",
                            err,
                            len(batch),
                        )
                        if failed >= FAILED_BATCHES:
                            log.info("artist people: Wikidata keeps failing; the rest next time")
                            break
                        continue
                    failed = 0
                    asked += len(got)
                    found += sum(1 for qid in got.values() if qid)
            log.info(
                "artist people %s: %d of %d spellings found in Wikidata in %.0f s",
                why,
                found,
                asked,
                time.monotonic() - started,
            )
            if asked:
                self.library.refresh_names()
            return found
        finally:
            self._lock.release()

    def _ask(self, http: httpx.Client, wanted: list[tuple[str, list[int]]]) -> dict[str, str]:
        """Each of ``wanted``'s item ("" none), kept."""
        hits: dict[str, list[tuple[str, str]]] = {}
        for name, _ in wanted:
            hits[name] = self._search(http, search_name(name))
        ids = sorted({qid for found in hits.values() for qid, _ in found})
        facts: dict[str, Facts] = {}
        for start in range(0, len(ids), FACTS_BATCH):
            facts.update(self._facts(http, ids[start : start + FACTS_BATCH]))
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        got: dict[str, str] = {}
        people = self.people()
        for name, years in wanted:
            qid = self._choose(hits[name], facts, years)
            got[name] = qid
            if qid:
                known = facts[qid]
                people[qid] = {k: known.get(k) for k in ("en", "pl", "born", "died")}
        kept = self.ids()
        kept.update({name: [qid, stamp] for name, qid in got.items()})
        self.library.set_state(PEOPLE_STATE, people)
        self.library.set_state(IDS_STATE, kept)
        return got

    @staticmethod
    def _choose(hits: list[tuple[str, str]], facts: dict[str, Facts], years: list[int]) -> str:
        """The first person among ``hits`` whose life fits ``years`` (with
        no years: one described as making art)."""
        for qid, description in hits:
            known = facts.get(qid)
            if known is None or not known.get("human"):
                continue
            born, died = known.get("born"), known.get("died")
            if years:
                if fits(born, died, years):
                    return qid
            elif _MAKER.search(description):
                return qid
        return ""

    def _send(self, request: Callable[[], httpx.Response]) -> httpx.Response:
        """``request``'s answer, sent again after each of :data:`RETRY_WAITS`
        while Wikidata fails it (a 5xx, a timeout, no answer)."""
        waits = list(RETRY_WAITS)
        while True:
            try:
                resp = request()
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as err:
                if not waits or told_to_stop(err) or not _passing(err):
                    raise
                wait = waits.pop(0)
                log.info("artist people: %s; again in %.0f s", err, wait)
            self.sleep(wait)

    def _search(self, http: httpx.Client, name: str) -> list[tuple[str, str]]:
        """Wikidata's items for ``name``: (item, description), the likeliest
        first."""
        if not name:
            return []
        resp = self._send(
            lambda: http.get(
                API,
                params={
                    "action": "wbsearchentities",
                    "search": name,
                    "language": "en",
                    "type": "item",
                    "limit": HITS,
                    "format": "json",
                },
            )
        )
        return [
            (str(hit["id"]), str(hit.get("description") or ""))
            for hit in resp.json().get("search") or []
            if "id" in hit
        ]

    def _facts(self, http: httpx.Client, ids: list[str]) -> dict[str, Facts]:
        """Whether each of ``ids`` is a person, their years and names."""
        query = FACTS % " ".join(f"wd:{qid}" for qid in ids if re.fullmatch(r"Q\d+", qid))
        resp = self._send(
            lambda: http.post(
                SPARQL,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
                timeout=60,
            )
        )
        found: dict[str, Facts] = {}
        for row in resp.json().get("results", {}).get("bindings") or []:
            qid = str(row.get("item", {}).get("value", "")).rsplit("/", 1)[-1]
            if not qid:
                continue
            known = found.setdefault(qid, Facts(human=False, born=None, died=None, en="", pl=""))
            known["human"] = known["human"] or row.get("human", {}).get("value") == "true"
            for key in ("born", "died"):
                value = row.get(key, {}).get("value")
                if value and re.fullmatch(r"-?\d{1,4}", value):
                    year = int(value)
                    # The earliest of several: a life is not made shorter.
                    if key == "born":
                        known[key] = year if known[key] is None else min(known[key], year)
                    else:
                        known[key] = year if known[key] is None else max(known[key], year)
            for lang in ("en", "pl"):
                if not known[lang] and (label := row.get(lang, {}).get("value")):
                    known[lang] = str(label)
        return found
