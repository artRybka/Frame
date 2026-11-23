"""Which Wikidata item each picture is of, and pictures naming one item made
copies of one work.

A Commons page says which work its file shows ({{Artwork |wikidata=Q...}}).
Three files of van Gogh's "Poppy Flowers", stolen from Cairo in 2010 (a
faded photograph from an exhibition, a small cutting from the news, a
shop's painted copy), name Q4118041 all three; their pictures matched no
keypoints, their hashes were far apart and the judge called two of them
different, so they were three tiles of a playlist (Mateusz 2026-11-23).

At night the library's pictures from Commons are read for their item, fifty
pages a request (``Item.work_qid``; "-" when the page names none). The
items found are asked of Wikidata for the museums' record ids they carry
(:data:`library.wikidata.PROPERTIES`), so a museum's own copy of the work
names it too. Then every item named by pictures of more than one work joins
them (:meth:`library.twins.Twins.join_work`)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

import httpx

from .holders import COMMONS_API, commons_file, work_qid
from .library import Item, ItemKind
from .library.wikidata import BATCH, COMMONS_IDS, PROPERTIES, Wikidata, record_id

if TYPE_CHECKING:
    from .library import Library
    from .library.twins import Twins

log = logging.getLogger(__name__)

#: ``Item.work_qid`` of a picture whose page names no item.
NONE = "-"
#: Pictures read in one night at most (a request a :data:`BATCH`).
A_NIGHT = 10_000


def applies(item: Item) -> bool:
    """A work of art whose picture may name its Wikidata item: from Commons,
    or a museum's record Wikidata knows by its id."""
    if item.kind != ItemKind.ARTWORK or item.look is not None or item.own is not None:
        return False
    return commons_file(item) != ("", "") or _record(item) is not None


def _record(item: Item) -> tuple[str, str] | None:
    """(property, value) Wikidata knows ``item``'s museum record by."""
    if (ref := record_id(item)) is not None:
        return ref
    prop = COMMONS_IDS.get(item.source)
    return (prop, item.source_id) if prop and item.source_id else None


class WorkIds:
    def __init__(self, library: Library, twins: Twins, http: Callable[[], httpx.Client]) -> None:
        self.library = library
        self.twins = twins
        self.http = http

    def at_night(
        self,
        quiet: Callable[[], bool] = lambda: True,
        first: Callable[[list[Item]], list[Item]] = lambda items: items,
    ) -> tuple[int, int]:
        """The items of pictures not read yet, then the works joined: (how
        many pictures were read, how many joined a work)."""
        read = self.read(quiet, first)
        return read, self.join()

    # -- reading -------------------------------------------------------------------

    def read(
        self,
        quiet: Callable[[], bool] = lambda: True,
        first: Callable[[list[Item]], list[Item]] = lambda items: items,
    ) -> int:
        """The pictures from Commons not read yet (``first`` orders them),
        :data:`A_NIGHT` at most; how many were."""
        items = self.library.all_items()
        due = first([i for i in items if not i.work_qid and commons_file(i)[0] and applies(i)])
        records = {ref: i.id for i in items if not i.work_qid and (ref := _record(i)) is not None}
        done = 0
        with self.http() as http:
            for start in range(0, min(len(due), A_NIGHT), BATCH):
                if not quiet():
                    break
                chunk = due[start : start + BATCH]
                try:
                    found = self._pages(http, [commons_file(i)[0] for i in chunk])
                    named = {i.id: found.get(commons_file(i)[0], NONE) for i in chunk}
                    qids = sorted({q for q in named.values() if q != NONE})
                    held = self._records(http, qids, records) if records and qids else {}
                except (httpx.HTTPError, ValueError, KeyError) as err:
                    log.info("work ids: Commons not read (%s)", err)
                    break
                with self.library.batch():
                    for item_id, qid in {**named, **held}.items():
                        self.library.update(item_id, work_qid=qid)
                done += len(chunk)
        if done:
            log.info("work ids: %d pictures read", done)
        return done

    @staticmethod
    def _pages(http: httpx.Client, page_ids: list[str]) -> dict[str, str]:
        """The item each Commons page names, by page id (pages naming none
        left out)."""
        resp = http.get(
            COMMONS_API,
            params={
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "pageids": "|".join(page_ids),
            },
        )
        resp.raise_for_status()
        found: dict[str, str] = {}
        for page in resp.json().get("query", {}).get("pages") or []:
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            text = revisions[0].get("slots", {}).get("main", {}).get("content") or ""
            if qid := work_qid(str(text)):
                found[str(page.get("pageid"))] = qid
        return found

    @staticmethod
    def _records(
        http: httpx.Client, qids: list[str], records: dict[tuple[str, str], str]
    ) -> dict[str, str]:
        """The library's museum records the items ``qids`` carry the ids of
        (item id -> its Wikidata item)."""
        props = set(PROPERTIES.values()) | set(COMMONS_IDS.values())
        held: dict[str, str] = {}
        for qid, entity in Wikidata._many(http, qids, "claims").items():
            for prop in props:
                for value in _values(entity, prop):
                    item_id = records.get((prop, value))
                    if item_id is not None:
                        held[item_id] = qid
        return held

    # -- joining -------------------------------------------------------------------

    def join(self) -> int:
        """Pictures naming one item made copies of one work; how many joined."""
        named: dict[str, list[str]] = defaultdict(list)
        for item in self.library.all_items():
            if item.work_qid and item.work_qid != NONE:
                named[item.work_qid].append(item.id)
        joined = 0
        for qid, ids in named.items():
            if len(ids) > 1:
                joined += self.twins.join_work(qid, ids)
        return joined


def _values(entity: dict[str, Any], prop: str) -> Iterable[str]:
    """The string values of ``entity``'s statements of ``prop``."""
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str):
            yield value
