"""Adding pictures to the library: museum works, uploads, background jobs."""

from __future__ import annotations

import logging
import random
import re
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from dataclasses import dataclass, field, replace
from itertools import chain, zip_longest
from typing import Any, cast

import httpx
from PIL import Image

from ..imaging.palette import Palette
from .colors import analyse, has_colours, tint_spread
from .commons import OWN_SOURCES
from .dates import text_year
from .duplicates import dedupe, rank
from .fragments import Fragments, split_part
from .hosts import as_asked, deferrable
from .images import ImageCache
from .lifespan import LifeDates
from .models import Item, ItemKind, Look, PhotoInfo, PlaylistRules
from .museums import (
    MUSEUMS,
    Access,
    Discovery,
    Kind,
    Museum,
    WikimediaCommons,
    available,
    client,
    museum,
    reachable,
)
from .pages import search_pages
from .phrases import quote, tokens
from .repo import Library, matches, now_iso
from .vocabulary import (
    HIGHLIGHT,
    TECHNIQUE_KINDS,
    is_copy,
    is_grey_copy,
    may_be_grey_copy,
    museum_kind,
    museum_queries,
    object_category,
    set_aside,
    years,
)
from .wording import Wording

log = logging.getLogger(__name__)

#: Pseudo source: every museum at once.
ALL = "all"
#: Museums asked for works by the artists the owner likes (those on offer).
TASTE_SOURCES = (
    *("aic", "cma", "met", "rijks", "europeana", "smk"),
    *("nga", "mnw", "mnk", "yale", "si", "wellcome", "courtauld", "louvre", "getty"),
    "wikiart",
)
#: Museums that draw random paintings for variety (those on offer). Paris
#: Musées searches titles only, so it is not asked for artists. The Wellcome
#: Collection's paintings are often about medicine (operations, diseases),
#: so it is asked for artists and themes but not for random paintings.
DRAW_SOURCES = (*(s for s in TASTE_SOURCES if s not in ("wellcome", "wikiart")), "paris")
#: Museums that can be asked for their most important works.
HIGHLIGHT_SOURCES = ("met", "cma", "mnw", "mnk")
#: How long a search waits for typed words to be translated (seconds); an
#: answer that comes later serves the next search.
TRANSLATE_SECONDS = 5.0
#: Museum works seen in search results, kept in memory so that opening one
#: needs no second request.
REMOTE_MEMO = 5000
#: Sources whose paintings often come as black-and-white copies (album
#: plates, old photographs): their results' thumbnails are looked at before
#: they are shown. How many verdicts are remembered.
GREY_PRONE = ("wmc", "europeana")
SPREAD_MEMO = 20_000
#: Works a search showed, waiting to join the catalogue; more are left out.
SEARCHED_QUEUE = 400
#: Works a search showed that were taken or left out, not looked at again.
SEARCHED_MEMO = 5_000
#: Works a search brought but did not show (another colour, other years,
#: another artist) whose thumbnail is here already, waiting to join the
#: catalogue after the shown ones; more are left out ...
SPARE_QUEUE = 400
#: ... and this many are taken at a time, so works shown meanwhile go first.
SPARE_BATCH = 24
#: Museum searches answered lately, kept for the same page asked again (a
#: set of Odkrywaj opened once more): how many and how long. The Met asks
#: for each of a page's 24 works on its own, so a page takes it seconds.
SEARCH_MEMO = 300
SEARCH_SECONDS = 3 * 3600.0
#: How long a search's answer waits for the shapes of works whose museum
#: gives no size (Europeana, the Met, the Rijksmuseum...), measured on their
#: thumbnails; those not measured by then come as landscape and are known
#: the next time.
ASPECT_SECONDS = 2.5


def language_of(key: str) -> str:
    """The language museum ``key`` searches in."""
    found = MUSEUMS.get(key)
    return found.language if found is not None else "en"


def quotes_of(key: str) -> bool:
    """Whether museum ``key``'s search keeps to a quoted phrase."""
    found = MUSEUMS.get(key)
    return found.phrases if found is not None else False


@dataclass(frozen=True)
class Asked:
    """Words typed in Szukaj as the museums are asked them: each museum's
    text (its language; phrases quoted where its search keeps to them) and,
    for each phrase, its forms a work found must have one of (the phrase as
    typed and translated: "nocna straż", "night watch", "ronde de nuit")."""

    texts: dict[str, str]
    phrases: list[list[str]]


def small_thumb(item: Item) -> str:
    """A small version of ``item``'s thumbnail, enough to judge its colour:
    Commons' 120 px step, Europeana's 200 px preview. (Works are looked at on
    their kept thumbnails since 2026-11-07, :meth:`Importer._thumbnail`.)"""
    url = item.thumb_url
    if item.source == "wmc" and "/thumb/" in url:
        return re.sub(r"/\d+px-([^/]+)$", r"/120px-\1", url)
    if item.source == "europeana":
        return url.replace("size=w400", "size=w200")
    return url


def span(rules: PlaylistRules) -> tuple[int | None, int | None]:
    """The years to ask museums for ``rules``: their own range within their
    periods'. Most museums' date filters know no years before Christ, so
    such a start is left open and such an end is year 1; what comes back is
    checked against the exact years anyway."""
    start, end = years(rules.terms)
    if rules.year_from is not None:
        start = rules.year_from if start is None else max(start, rules.year_from)
    if rules.year_to is not None:
        end = rules.year_to if end is None else min(end, rules.year_to)
    if start is not None and start < 1:
        start = None
    if end is not None and end < 1:
        end = 1
    return start, end


def fill_queries(rules: PlaylistRules) -> list[str]:
    """What Discover's search asks the museums for ``rules``, one text per
    artist: the words, the artist and the first style or subject."""
    topics = museum_queries(rules.terms)[:1]
    words = rules.query.strip()
    texts = [" ".join(w for w in (words, artist, *topics) if w) for artist in rules.artists or [""]]
    return [t for t in dict.fromkeys(texts) if t]


def _search_stream(source: Museum, query: str, kind: Kind = "any") -> Iterator[Item]:
    """A museum's search results, page after page (of ``kind``, when one)."""
    size = min(source.page_size, 24)
    page = 1
    while True:
        if kind == "any":
            total, items = source.search(query, limit=size, page=page)
        else:
            total, items = source.search_kind(query, kind, limit=size, page=page)
        yield from items
        if page * size >= total:
            return
        page += 1


@dataclass
class Job:
    id: str
    description: str
    total: int = 0
    done: int = 0
    failed: int = 0
    #: Drawn but left out, e.g. too weak on e-paper.
    skipped: int = 0
    finished: bool = False
    error: str = ""
    item_ids: list[str] = field(default_factory=list)


def dated(item: Item) -> Item:
    """``item`` with the year its date in words gives ("1st century A.D.",
    Getty, V&A, Yale), when its source's reader left none: as an imported
    work gets it, so that a set of a period (Epoki) keeps it."""
    if item.year is not None or item.source in OWN_SOURCES or not item.date_text:
        return item
    year = text_year(item.date_text)
    return item if year is None else item.model_copy(update={"year": year})


class Importer:
    def __init__(
        self,
        library: Library,
        cache: ImageCache,
        palette: Palette,
        http: Callable[[], httpx.Client] = client,
        access: Callable[[], Access] = Access,
    ) -> None:
        self.library = library
        self.cache = cache
        self.palette = palette
        self.http = http
        self._access = access
        self.life = LifeDates()
        self.jobs: dict[str, Job] = {}
        self._remote: OrderedDict[str, Item] = OrderedDict()
        self._remote_lock = threading.Lock()
        #: ``tint_spread`` of works looked at in search results, by id.
        self._spreads: OrderedDict[str, float] = OrderedDict()
        #: Colour tags of works looked at in search results, by id.
        self._tags: OrderedDict[str, tuple[list[str], dict[str, float]]] = OrderedDict()
        #: Width / height of works whose source gave no size, from their
        #: thumbnails, by id.
        self._aspects: OrderedDict[str, float] = OrderedDict()
        #: Works a search showed, on their way into the catalogue.
        self._searched: OrderedDict[str, Item] = OrderedDict()
        #: Works a search brought but did not show (:meth:`keep_spare`).
        self._spare: OrderedDict[str, Item] = OrderedDict()
        self._searched_seen: OrderedDict[str, None] = OrderedDict()
        self._searched_lock = threading.Lock()
        self._searching: threading.Thread | None = None
        #: Techniques of "Sztuki inne" with room left in the catalogue: works
        #: of them a search showed are kept too.
        self._searched_room: tuple[str, ...] = ()
        #: Pages of museum searches (:data:`SEARCH_MEMO`): when asked, how
        #: many in all, the works.
        self._pages: OrderedDict[
            tuple[str, str, int, int, str, bool], tuple[float, int, list[Item]]
        ] = OrderedDict()
        #: Pages kept on disk that are asked again behind (library/pages.py).
        self._asking: set[tuple[str, str, int, int, str, bool]] = set()
        #: Pages being asked for now, and whether by work that may wait (the
        #: background's): another asking for the same one waits for that
        #: answer instead of asking the museum again, unless it may not wait
        #: and that one may.
        self._inflight: dict[tuple[str, str, int, int, str, bool], tuple[Future[Any], bool]] = {}
        #: Words typed in Szukaj in the museums' languages (the language
        #: model's, set by the service); none: asked as typed.
        self.translate: Callable[[str, float], Wording] | None = None
        #: Fragments of works (library/fragments.py), set by the service:
        #: a fragment's id (``<work>~p<n>``) is made from its work's.
        self.fragments: Fragments | None = None

    def access(self) -> Access:
        """The owner's current choices, with the shared death-year cache."""
        access = self._access()
        if self.life.europeana_key != access.europeana_key:
            self.life = LifeDates(access.europeana_key)
        return replace(access, life=self.life)

    def sources(self) -> list[str]:
        """Keys of the sources on offer now."""
        return list(available(self.access()))

    def reachable(self) -> list[str]:
        """Sources that may answer, those the owner turned off too (for the
        works of museums chosen in Szukaj)."""
        return reachable(self.access())

    def asked_sources(self, kind: Kind = "any") -> list[str]:
        """The sources on offer that a search for ``kind`` asks: those of one
        kind only (``Museum.only``) just for that kind."""
        return [k for k in self.sources() if MUSEUMS[k].only in (None, kind)]

    def known(self, item_id: str) -> Item | None:
        """A museum work a search showed lately, without asking the museum."""
        with self._remote_lock:
            return self._remote.get(item_id)

    def remember(self, items: Iterable[Item]) -> None:
        with self._remote_lock:
            for item in items:
                self._remote[item.id] = item
                self._remote.move_to_end(item.id)
            while len(self._remote) > REMOTE_MEMO:
                self._remote.popitem(last=False)

    def remote(self, item_id: str) -> Item | None:
        """A museum work by its id, without adding it to the library: from
        recent search results, else asked from the museum."""
        with self._remote_lock:
            if item_id in self._remote:
                return self._remote[item_id]
        if (split := split_part(item_id)) is not None:
            return self._fragment(*split)
        source, _, source_id = item_id.partition(":")
        if source not in self.sources() or not source_id:
            return None
        with self.http() as http:
            item = museum(source, http, self.access()).fetch(source_id)
        if item is not None:
            self.remember([item])
        return item

    def _fragment(self, work_id: str, n: int) -> Item | None:
        """The ``n``-th fragment of the work ``work_id`` (library/fragments.py)."""
        work = self.resolve(work_id) if self.fragments is not None else None
        if work is None or self.fragments is None:
            return None
        item = self.fragments.part(work, n)
        if item is not None:
            self.remember([item])
        return item

    def fragments_of(self, item: Item) -> list[Item]:
        """``item``'s fragments as works of their own, remembered for their
        cards and thumbnails; [] when it has none."""
        if self.fragments is None:
            return []
        found = self.fragments.items(item)
        self.remember(found)
        return found

    def resolve(self, item_id: str) -> Item | None:
        """A library item, or a museum work that is not (yet) in the library."""
        return self.library.get(item_id) or self.remote(item_id)

    def save(self, item_id: str) -> Item | None:
        """The library item, adding the museum work first if it is not there:
        a work is kept once the owner does something with it."""
        existing = self.library.get(item_id)
        if existing is not None:
            if existing.pooled:
                return self.library.update(item_id, pooled=False) or existing
            return existing
        item = self.remote(item_id)
        return self.add(item) if item else None

    def add(self, item: Item) -> Item:
        """Download the thumbnail, analyse colours and store the item."""
        return self.library.upsert(self._analysed(item))

    def measure_again(self, item: Item) -> Item:
        """The stored work's colours, colour tags and tint from its thumbnail
        as it is now (another picture took the place of the one before);
        its size is the work's and stays."""
        with Image.open(self.cache.ensure_thumb(item)) as thumb:
            spread = tint_spread(thumb)
            colors, tags, score, shares = analyse(thumb, self.palette, spread)
        changes: dict[str, Any] = {
            "colors": colors,
            "color_tags": tags,
            "color_shares": shares,
            "tint_spread": spread,
        }
        if item.suitability is not None:
            changes["suitability"] = score
        return self.library.update(item.id, **changes) or item.model_copy(update=changes)

    def _analysed(self, item: Item) -> Item:
        with Image.open(self.cache.ensure_thumb(item)) as thumb:
            spread = tint_spread(thumb)
            colors, tags, score, shares = analyse(thumb, self.palette, spread)
            width, height = item.width, item.height
            if not width or not height:
                width, height = thumb.size
        year = item.year
        if year is None and item.source not in OWN_SOURCES:
            # Dates in words the source's reader left without a year.
            year = text_year(item.date_text)
        return item.model_copy(
            update={
                "year": year,
                "colors": colors,
                "color_tags": tags,
                "color_shares": shares,
                "suitability": score,
                "tint_spread": spread,
                "width": width,
                "height": height,
            }
        )

    def search(
        self,
        source: str,
        query: str,
        limit: int = 24,
        page: int = 1,
        wait: float | None = None,
        kind: Kind = "any",
    ) -> tuple[int, list[Item]]:
        """``limit`` works from ``source``; ``wait``: seconds the source may
        take to answer, when not the client's own; ``kind``: what the
        search asks for (Fotografia: photographs). A page asked lately
        comes from memory (:data:`SEARCH_SECONDS`), an older one from disk
        while it is asked again behind (library/pages.py)."""
        access = self.access()
        # Licences differ with private use: its pages are other pages.
        memo = (source, query, limit, page, str(kind), access.private_use)
        with self._remote_lock:
            kept = self._pages.get(memo)
            if kept is not None and time.monotonic() - kept[0] < SEARCH_SECONDS:
                return kept[1], list(kept[2])
        disk = search_pages(access.data_dir) if access.data_dir else None
        if disk is not None:
            stored = disk.get(disk.key(*memo))
            if stored is not None:
                fresh, total, items = stored
                self.remember(items)
                if fresh:
                    self._memo(memo, total, items)
                else:  # shown now, asked again behind for the next look
                    self._ask_behind(memo)
                return total, list(items)
        return self._ask(memo, wait)

    def _ask(
        self, memo: tuple[str, str, int, int, str, bool], wait: float | None = None
    ) -> tuple[int, list[Item]]:
        """The museum's page of ``memo``, kept in memory and on disk; asked
        once when several want it at the same time (a set's stream, the
        same page asked again behind, the catalogue)."""
        may_wait = deferrable()
        with self._remote_lock:
            other = self._inflight.get(memo)
            # The background's request waits while the app is in use
            # (hosts.HostGuard.wait_calm): what the app waits for never
            # waits behind it, it asks on its own (2026-11-07: the copies'
            # searches stood until the app was left alone).
            if other is not None and (may_wait or not other[1]):
                asking = other[0]
                mine = False
            else:
                entry: tuple[Future[Any], bool] = (Future(), may_wait)
                asking, mine = entry[0], True
                self._inflight[memo] = entry
        if not mine:
            total, items = asking.result()
            return total, list(items)
        try:
            found = self._ask_museum(memo, wait)
        except BaseException as err:
            asking.set_exception(err)
            raise
        finally:
            with self._remote_lock:
                if self._inflight.get(memo) is entry:
                    del self._inflight[memo]
        asking.set_result(found)
        return found[0], list(found[1])

    def _ask_museum(
        self, memo: tuple[str, str, int, int, str, bool], wait: float | None = None
    ) -> tuple[int, list[Item]]:
        source, query, limit, page, kind, _ = memo
        access = self.access()
        with self.http() as http:
            if wait is not None:
                http.timeout = httpx.Timeout(wait)
            found = museum(source, http, access)
            if kind == "any":
                total, items = found.search(query, limit=limit, page=page)
            else:
                total, items = found.search_kind(query, cast(Kind, kind), limit=limit, page=page)
        items = self.without_grey([dated(i) for i in items if not is_copy(i)])
        self.remember(items)
        if items:
            self._memo(memo, total, items)
            if access.data_dir:
                pages = search_pages(access.data_dir)
                pages.put(pages.key(*memo), total, items)
        return total, items

    def _memo(
        self, memo: tuple[str, str, int, int, str, bool], total: int, items: list[Item]
    ) -> None:
        with self._remote_lock:
            self._pages[memo] = (time.monotonic(), total, list(items))
            self._pages.move_to_end(memo)
            while len(self._pages) > SEARCH_MEMO:
                self._pages.popitem(last=False)

    def _ask_behind(self, memo: tuple[str, str, int, int, str, bool]) -> None:
        """``memo``'s page asked again in the background (once at a time)."""
        with self._remote_lock:
            if memo in self._asking:
                return
            self._asking.add(memo)

        def ask() -> None:
            try:
                self._ask(memo)
            except Exception as err:
                log.info("search page %s not asked again: %s", memo[:2], err)
            finally:
                with self._remote_lock:
                    self._asking.discard(memo)

        threading.Thread(target=ask, name="search-page", daemon=True).start()

    def spread_of(self, item: Item) -> float | None:
        """``item``'s tint spread, from the library, memory or a small
        thumbnail; None when the thumbnail cannot be had."""
        if item.tint_spread is not None:
            return item.tint_spread
        stored = self.library.get(item.id)
        if stored is not None and stored.tint_spread is not None:
            return stored.tint_spread
        with self._remote_lock:
            if item.id in self._spreads:
                return self._spreads[item.id]
        try:
            with self._thumbnail(item) as img:
                spread = tint_spread(img)
                self._remember_aspect(item, img)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.info("no thumbnail of %s to look at: %s", item.id, err)
            return None
        with self._remote_lock:
            self._spreads[item.id] = spread
            while len(self._spreads) > SPREAD_MEMO:
                self._spreads.popitem(last=False)
        return spread

    def colours_of(self, item: Item) -> tuple[list[str], dict[str, float]] | None:
        """``item``'s colour tags and shares, from the library, memory or a
        small thumbnail; None when the thumbnail cannot be had."""
        if item.color_tags and item.color_shares:
            return item.color_tags, item.color_shares
        stored = self.library.get(item.id)
        if stored is not None and stored.color_tags and stored.color_shares:
            return stored.color_tags, stored.color_shares
        with self._remote_lock:
            if item.id in self._tags:
                return self._tags[item.id]
        try:
            with self._thumbnail(item) as img:
                spread = tint_spread(img)
                _, tags, _, shares = analyse(img, self.palette, spread)
                self._remember_aspect(item, img)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.info("no thumbnail of %s to look at: %s", item.id, err)
            return None
        with self._remote_lock:
            self._tags[item.id] = (tags, shares)
            self._spreads[item.id] = spread
            for memo in (self._tags, self._spreads):
                while len(memo) > SPREAD_MEMO:
                    memo.popitem(last=False)
        return tags, shares

    def _thumbnail(self, item: Item, urgent: bool = False) -> Image.Image:
        """``item``'s thumbnail to look at, downloaded once and kept: the app
        shows the server's copy of it too, so a sample thrown away was asked
        for again a moment later (2026-11-07)."""
        return Image.open(self.cache.ensure_thumb(item, urgent))

    def _remember_aspect(self, item: Item, img: Image.Image) -> None:
        width, height = img.size
        if (item.width and item.height) or not width or not height:
            return
        with self._remote_lock:
            self._aspects[item.id] = width / height
            self._aspects.move_to_end(item.id)
            while len(self._aspects) > SPREAD_MEMO:
                self._aspects.popitem(last=False)

    def known_aspect(self, item: Item) -> float | None:
        """``item``'s width / height without asking anyone: from its source's
        size, the library's copy, a thumbnail looked at before or the one
        kept here; None when none of them knows."""
        if item.width and item.height:
            return item.width / item.height
        stored = self.library.get(item.id)
        if stored is not None and stored.width and stored.height:
            return stored.width / stored.height
        with self._remote_lock:
            if item.id in self._aspects:
                return self._aspects[item.id]
        path = self.cache.thumb_path(item)
        if path.is_file():
            try:
                with Image.open(path) as img:  # the header only
                    self._remember_aspect(item, img)
            except OSError:
                return None
            with self._remote_lock:
                return self._aspects.get(item.id)
        return None

    def aspect_of(self, item: Item) -> float | None:
        """Like :meth:`known_aspect`, measuring a small thumbnail when need
        be; None when it cannot be had."""
        known = self.known_aspect(item)
        if known is not None or not item.thumb_url:
            return known
        try:
            with self._thumbnail(item, urgent=True) as img:
                self._remember_aspect(item, img)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.info("no thumbnail of %s to measure: %s", item.id, err)
            return None
        with self._remote_lock:
            return self._aspects.get(item.id)

    def measure(self, items: Iterable[Item], seconds: float = ASPECT_SECONDS) -> None:
        """Measure the shapes of ``items`` whose museum gives no size, for
        at most ``seconds``: the app lays out its grid by them, so a work
        shown as landscape would be cropped. Those not measured in time are
        left for later (the next page, the same search again)."""
        unknown = [i for i in items if self.known_aspect(i) is None and i.thumb_url]
        if not unknown:
            return
        pool = ThreadPoolExecutor(min(len(unknown), 8))
        try:
            futures = [pool.submit(as_asked(self.aspect_of), i) for i in unknown]
            wait_for(futures, timeout=seconds)
        finally:
            # The late ones go on into the memo; those not started don't.
            pool.shutdown(wait=False, cancel_futures=True)

    def in_colors(self, items: list[Item], colors: list[str]) -> list[Item]:
        """``items`` that fit ``colors`` (colour, accent or mood tags, as
        :func:`has_colours`), judged from their thumbnails; museums don't
        know colours."""
        if not colors or not items:
            return items
        with ThreadPoolExecutor(min(len(items), 16)) as pool:
            found = list(pool.map(as_asked(self.colours_of), items))
        return [
            i
            for i, colours in zip(items, found, strict=True)
            if colours and colours[0] and has_colours(colours[0], colors, colours[1])
        ]

    def without_grey(self, items: list[Item]) -> list[Item]:
        """``items`` without black-and-white copies of paintings and old
        photographs from art photo archives (:func:`is_grey_copy`), for the
        sources that have many (:data:`GREY_PRONE`)."""
        suspects = [
            i for i in items if i.source in GREY_PRONE and i.thumb_url and may_be_grey_copy(i)
        ]
        if not suspects:
            return items
        with ThreadPoolExecutor(min(len(suspects), 8)) as pool:
            found = pool.map(as_asked(self.spread_of), suspects)
            spreads = {i.id: spread for i, spread in zip(suspects, found, strict=True)}
        return [
            i for i in items if i.id not in spreads or not is_grey_copy(i, spread=spreads[i.id])
        ]

    def import_one(self, source: str, source_id: str) -> Item | None:
        return self.save(f"{source}:{source_id}")

    def search_all(
        self,
        query: str | Mapping[str, str],
        limit: int = 8,
        page: int = 1,
        keys: list[str] | None = None,
        kind: Kind = "any",
    ) -> tuple[int, list[Item], list[str]]:
        """``limit`` results from every museum (or those of ``keys``) at
        once, interleaved; returns (total, items, museums that failed).
        ``query``: one text for all, or each museum's own (:meth:`typed`);
        ``kind``: what the search asks for, when one kind."""

        def ask(key: str) -> tuple[int, list[Item]]:
            text = query if isinstance(query, str) else query.get(key, "")
            return self.search(key, text, limit, page, kind=kind)

        return self._from_all(ask, keys)

    def wording(self, text: str, wait: float = TRANSLATE_SECONDS) -> Wording:
        """Words someone typed, with their English and French when Polish."""
        if self.translate is None or not text.strip():
            return Wording(text)
        try:
            return self.translate(text, wait)
        except Exception:
            log.exception("translating %r failed", text)
            return Wording(text)

    def typed(
        self, text: str, keys: Iterable[str] | None = None, wait: float = TRANSLATE_SECONDS
    ) -> dict[str, str]:
        """What each museum of ``keys`` (all on offer) is asked for words
        someone typed: in its own language ("gitara" in Warsaw, "guitar" at
        the Met)."""
        return self.asked(text, keys, wait).texts

    def asked(
        self, query: str, keys: Iterable[str] | None = None, wait: float = TRANSLATE_SECONDS
    ) -> Asked:
        """Szukaj's tokens (:mod:`.phrases`) as museums of ``keys`` (all on
        offer) are asked them: each translated on its own, all of them
        wanted (Mateusz, 2026-11-09: never "any of them")."""
        wordings = [self.wording(t, wait) for t in tokens(query)]
        texts: dict[str, str] = {}
        for key in keys or self.sources():
            language = language_of(key)
            said = [w.in_language(language) for w in wordings]
            texts[key] = quote(said) if quotes_of(key) else " ".join(said)
        forms = [
            list(dict.fromkeys(f for f in (w.text, w.en, w.fr) if f))
            for w in wordings
            if " " in w.text
        ]
        return Asked(texts, forms)

    def _from_all(
        self, ask: Callable[[str], tuple[int, list[Item]]], keys: list[str] | None = None
    ) -> tuple[int, list[Item], list[str]]:
        keys = keys or self.asked_sources()
        with ThreadPoolExecutor(len(keys)) as pool:
            futures = {k: pool.submit(as_asked(ask), k) for k in keys}
        found: list[list[Item]] = []
        failed: list[str] = []
        total = 0
        for key, future in futures.items():
            try:
                count, items = future.result()
            except (httpx.HTTPError, ValueError) as err:
                log.warning("asking %s failed: %s", key, err)
                failed.append(key)
                continue
            except Exception:
                # One museum's odd answer must not cost the others' works.
                log.exception("asking %s failed", key)
                failed.append(key)
                continue
            total += count
            found.append(items)
        mixed = dedupe(
            [
                i
                for i in chain.from_iterable(zip_longest(*found))
                if i is not None and not is_copy(i)
            ]
        )
        self.remember(mixed)
        return total, mixed, failed

    def commons_file(self, name: str) -> Item | None:
        """The work in the Commons file ``name`` (a museum work's picture
        on Wikidata), not added to the library."""
        with self.http() as http:
            found = WikimediaCommons(http, access=self.access()).file(name)
        if found is not None:
            self.remember([found])
        return found

    def copy_of(self, item: Item) -> Item | None:
        """The library's copy of ``item``'s work from another source, unless
        ``item`` is from a more reliable source than a copy only the server
        added."""
        twin = self.library.twin(item)
        if twin is None or (twin.pooled and rank(item.source) < rank(twin.source)):
            return None
        return twin

    def search_many(self, source: str, query: str, limit: int) -> list[Item]:
        """Up to ``limit`` results, over as many result pages as that takes."""
        with self.http() as http:
            source_museum = museum(source, http, self.access())
            size = min(limit, source_museum.page_size)
            found: list[Item] = []
            page = 1
            while len(found) < limit:
                total, items = source_museum.search(query, limit=size, page=page)
                found += [i for i in items if not is_copy(i)]
                if page * size >= total:
                    break
                page += 1
        return found[:limit]

    def import_search(
        self, source: str, query: str, limit: int, job: Job | None = None
    ) -> list[Item]:
        if source == ALL:
            keys = self.asked_sources()
            share = -(-limit // len(keys))
            found = []
            for key in keys:
                try:
                    found += self.search_many(key, query, share)
                except (httpx.HTTPError, ValueError) as err:
                    log.warning("search in %s failed: %s", key, err)
        else:
            found = self.search_many(source, query, limit)
        found = dedupe(found)
        if job is not None:
            job.total += len(found)
        added = []
        for item in found:
            try:
                stored = self.library.get(item.id) or self.copy_of(item) or self.add(item)
                added.append(stored)
                if job is not None:
                    job.done += 1
                    job.item_ids.append(stored.id)
            except (httpx.HTTPError, OSError) as err:
                log.warning("import of %s failed: %s", item.id, err)
                if job is not None:
                    job.failed += 1
        return added

    def draw(
        self,
        spec: Discovery,
        count: int,
        sources: list[str],
        job: Job,
        min_suitability: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        """Add ``count`` random works matching ``spec``, taking turns between
        ``sources``; works below ``min_suitability`` are drawn again."""
        rng = rng or random.Random()
        with self.http() as http:
            streams = [museum(s, http, self.access()).random_draw(spec, rng) for s in sources]
            self._take(
                streams,
                count,
                job,
                before=spec.fits,
                after=lambda item: (item.suitability or 0.0) >= min_suitability,
            )

    def fill(
        self,
        rules: PlaylistRules,
        count: int,
        job: Job,
        rng: random.Random | None = None,
        pooled: bool = False,
    ) -> None:
        """Add ``count`` museum works that ``rules`` (a smart playlist) would
        pick, from every museum the rules allow."""
        rng = rng or random.Random()
        offered = self.sources()
        # Sources of one kind only when it asks for that kind.
        named = [s for s in rules.sources if s in offered]
        sources = named or self.asked_sources(museum_kind(rules.terms))
        sources = [s for s in sources if s not in rules.exclude_sources]
        # Colours and suitability are only known once the thumbnail is in.
        cheap = rules.model_copy(update={"colors": [], "min_suitability": None})
        highlight = HIGHLIGHT in rules.terms
        if highlight:
            sources = [s for s in sources if MUSEUMS[s].highlights] or sources
        with self.http() as http:
            museums = [museum(s, http, self.access()) for s in sources]
            if rules.artists or rules.query:
                # Named artists or words: the museums' own search finds them,
                # asked first as Discover's search asks (with the words and a
                # style or subject), then by the artist or words alone.
                alone = rules.artists or [rules.query]
                queries = list(dict.fromkeys([*fill_queries(rules), *alone]))
                kind = museum_kind(rules.terms)
                streams = [_search_stream(m, q, kind) for q in queries for m in museums]
            else:
                texts = [*rules.styles, *rules.subjects, *museum_queries(rules.terms)] or [""]
                year_from, year_to = span(rules)
                kind = museum_kind(rules.terms)
                # Sources that cannot filter (WikiArt) just when named.
                streams = [
                    m.random_draw(
                        Discovery(
                            year_from=year_from,
                            year_to=year_to,
                            style=text,
                            kind=kind,
                            highlight=highlight,
                        ),
                        rng,
                    )
                    for text in texts
                    for m in museums
                    if m.draws or named
                ]
            rng.shuffle(streams)
            self._take(
                streams,
                count,
                job,
                before=lambda item: matches(item, cheap),
                after=lambda item: matches(item, rules),
                pooled=pooled,
                terms=rules.terms,
            )

    def collect(
        self,
        count: int,
        job: Job,
        *,
        artists: Iterable[str] = (),
        queries: Iterable[tuple[str, str]] = (),
        kinds: Iterable[Kind] = ("painting",),
        highlights: Iterable[Kind] = (),
        min_suitability: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        """Add ``count`` works the server picks (``pooled``), taking turns
        between works by ``artists``, the museum searches ``queries`` (e.g.
        a theme), works of ``kinds`` drawn at random and museums' most
        important works of ``highlights``; works below ``min_suitability``
        are left out."""
        rng = rng or random.Random()
        with self.http() as http:

            def source(key: str) -> Museum:
                return museum(key, http, self.access())

            # Sources needing a key or a download are left out without them.
            offered = set(self.sources())
            taste = [s for s in TASTE_SOURCES if s in offered]
            draw = [s for s in DRAW_SOURCES if s in offered]
            streams = [_search_stream(source(s), a) for a in artists for s in taste]
            streams += [_search_stream(source(s), q) for s, q in queries if s in offered]
            streams += [
                source(s).random_draw(Discovery(kind=kind), rng) for kind in kinds for s in draw
            ]
            streams += [
                source(s).random_draw(Discovery(kind=kind, highlight=True), rng)
                for kind in highlights
                for s in HIGHLIGHT_SOURCES
                if s in offered
            ]
            rng.shuffle(streams)
            self._take(
                streams,
                count,
                job,
                before=lambda item: True,
                after=lambda item: (item.suitability or 0.0) >= min_suitability,
                pooled=True,
            )

    def collect_other_art(
        self,
        category: str,
        count: int,
        job: Job,
        queries: Iterable[tuple[str, str]] = (),
        rng: random.Random | None = None,
    ) -> None:
        """Add ``count`` works (``pooled``) of one technique of "Sztuki inne"
        (one of ``OBJECT_CATEGORIES``), taking turns between the museums'
        most important works of that kind, the searches ``queries`` (of the
        group's themes) and random draws of the kind; only works of that
        technique are taken."""
        rng = rng or random.Random()
        kind = TECHNIQUE_KINDS[category]
        offered = [s for s in self.asked_sources(kind) if MUSEUMS[s].draws]
        with self.http() as http:

            def source(key: str) -> Museum:
                return museum(key, http, self.access())

            streams = [
                source(s).random_draw(Discovery(kind=kind, highlight=True), rng)
                for s in HIGHLIGHT_SOURCES
                if s in offered
            ]
            streams += [_search_stream(source(s), q) for s, q in queries if s in offered]
            streams += [source(s).random_draw(Discovery(kind=kind), rng) for s in offered]
            rng.shuffle(streams)
            self._take(
                streams,
                count,
                job,
                before=lambda item: object_category(item) == category,
                after=lambda item: True,
                pooled=True,
                terms=[category],
            )

    def collect_searched(
        self,
        category: str,
        searches: Iterable[tuple[str, str]],
        count: int,
        job: Job,
        fits: Callable[[Item], bool],
        most: int = 60,
    ) -> None:
        """Add up to ``count`` works (``pooled``) of one technique of "Sztuki
        inne" that a theme's ``searches`` find and that ``fits`` (its rules,
        once analysed: "Pierwsze kolory" wants colour): a card the catalogue
        has too few works of. ``most`` museum works are looked at, at most:
        each costs the museum requests (2026-11-07: the Library of Congress
        and the Met turned the home address away after a morning's
        catalogue round)."""
        offered = self.asked_sources(TECHNIQUE_KINDS[category])
        with self.http() as http:
            streams = [
                _search_stream(museum(s, http, self.access()), q)
                for s, q in searches
                if s in offered
            ]
            self._take(
                streams,
                count,
                job,
                before=lambda item: object_category(item) == category,
                after=fits,
                pooled=True,
                terms=[category],
                most=most,
            )

    def discover_all(
        self, spec: Discovery, limit: int = 8, page: int = 1, keys: list[str] | None = None
    ) -> tuple[int, list[Item], list[str]]:
        """Like :meth:`search_all`, for works matching ``spec``."""

        def one(key: str) -> tuple[int, list[Item]]:
            with self.http() as http:
                return museum(key, http, self.access()).discover(spec, limit, page)

        return self._from_all(one, keys)

    def _take(
        self,
        streams: list[Iterator[Item]],
        count: int,
        job: Job,
        before: Callable[[Item], bool],
        after: Callable[[Item], bool],
        pooled: bool = False,
        terms: list[str] | None = None,
        most: int | None = None,
        fits: Callable[[Item], bool] | None = None,
    ) -> None:
        """Take turns between ``streams`` until ``count`` new works pass
        ``before`` (on museum data) and ``after`` (once analysed); pages of
        manuscripts, photographs, sculpture and decorative arts only when
        ``terms`` ask for them; ``most``: museum works looked at, at most.
        A work found by a museum search (``Item.found_for``) that the library
        has already, in this or another copy, remembers that search; with
        ``fits`` (a smart playlist's rules) it counts too, when only that
        made it fit."""
        job.total = count
        drawn = 0
        most = max(count * 20, 200) if most is None else most
        while streams and job.done < count and drawn < most:
            for stream in list(streams):
                if job.done >= count:
                    break
                try:
                    item = next(stream)
                except StopIteration:
                    streams.remove(stream)
                    continue
                except Exception as err:
                    log.warning("a museum stopped answering: %s", err)
                    streams.remove(stream)
                    continue
                drawn += 1
                if (known := self.library.get(item.id)) is not None:
                    if item.highlight and not known.highlight:  # taken in before 0.42
                        self.library.update(item.id, highlight=True)
                    self._found_again(known, item.found_for, job, fits)
                    continue
                if (twin := self.copy_of(item)) is not None:
                    self._found_again(twin, item.found_for, job, fits)
                    continue
                if not before(item):
                    continue
                if set_aside(item, terms or []):
                    job.skipped += 1
                    continue
                try:
                    analysed = self._analysed(item)
                except (httpx.HTTPError, OSError) as err:
                    log.warning("import of %s failed: %s", item.id, err)
                    job.failed += 1
                    continue
                # Black-and-white copies of paintings only show once analysed.
                if is_grey_copy(analysed) or not after(analysed):
                    self.cache.remove(item)
                    job.skipped += 1
                    continue
                worse = self.library.twin(analysed)  # pooled, from a less reliable source
                self.library.upsert(analysed.model_copy(update={"pooled": pooled}))
                if worse is not None and worse.id in job.item_ids:
                    # A better copy of a work taken already, in its place.
                    job.item_ids[job.item_ids.index(worse.id)] = item.id
                    continue
                job.done += 1
                job.item_ids.append(item.id)

    def _found_again(
        self, known: Item, found: list[str], job: Job, fits: Callable[[Item], bool] | None
    ) -> None:
        """``known`` (in the library) found again by the museum searches
        ``found``: it fits them from now on (:meth:`Library.found`), and is
        one of ``job``'s works when only that makes it ``fits``."""
        new = [k for k in found if k not in known.found_for]
        if not new:
            return
        was = fits is not None and fits(known)
        now: Item | None = known
        for key in new:
            now = self.library.found(known.id, key)
        if fits is None or was or now is None or now.excluded or now.id in job.item_ids:
            return
        if job.done < (job.total or 0) and fits(now):
            job.done += 1
            job.item_ids.append(now.id)

    def keep_searched(
        self, items: Iterable[Item], room: Iterable[str] = (), found: str = ""
    ) -> None:
        """Works a search showed, into the catalogue (``pooled``) in the
        background, one at a time so the museums aren't hurried: what the
        owner looks for beats a random draw. As with the catalogue's own
        draws, copies and black-and-white copies are left out, however the
        works would do on e-paper, and manuscripts and the like unless
        their technique has ``room`` (of "Sztuki inne") left. ``found``:
        the search that found them (:meth:`PlaylistRules.search_key`), which
        they fit from then on."""
        with self._searched_lock:
            self._searched_room = tuple(room)
            for item in items:
                if item.id in self._searched or item.id in self._searched_seen:
                    continue
                if len(self._searched) >= SEARCHED_QUEUE:
                    break
                if found and found not in item.found_for:
                    item = item.model_copy(update={"found_for": [*item.found_for, found]})
                self._spare.pop(item.id, None)
                self._searched[item.id] = item
            self._start_searched()

    def keep_spare(self, items: Iterable[Item], room: Iterable[str] = ()) -> None:
        """Works a search brought but did not show (another colour, other
        years, another artist: :meth:`.search.MuseumSearch.pages`) into the
        catalogue (``pooled``) like :meth:`keep_searched`'s, after them:
        the museum was asked for them already (Mateusz 2026-11-07). Only
        those whose thumbnail is here, so they cost no request; they
        remember no search, as they don't fit it."""
        here = [i for i in items if self.cache.thumb_path(i).is_file()]
        with self._searched_lock:
            self._searched_room = tuple(room)
            for item in here:
                if (
                    item.id in self._searched
                    or item.id in self._spare
                    or item.id in self._searched_seen
                ):
                    continue
                if len(self._spare) >= SPARE_QUEUE:
                    break
                self._spare[item.id] = item
            self._start_searched()

    def _start_searched(self) -> None:
        """Starts taking works in, unless it is under way (with
        ``_searched_lock`` held)."""
        if not (self._searched or self._spare) or (self._searching and self._searching.is_alive()):
            return
        self._searching = threading.Thread(target=self._take_searched, name="searched", daemon=True)
        self._searching.start()

    def _take_searched(self) -> None:
        while True:
            with self._searched_lock:
                if self._searched:
                    batch = list(self._searched.values())
                    self._searched.clear()
                elif self._spare:
                    count = min(SPARE_BATCH, len(self._spare))
                    batch = [self._spare.popitem(last=False)[1] for _ in range(count)]
                else:
                    self._searching = None
                    return
                for item in batch:
                    self._searched_seen[item.id] = None
                while len(self._searched_seen) > SEARCHED_MEMO:
                    self._searched_seen.popitem(last=False)
            try:
                self._take(
                    [iter(batch)],
                    len(batch),
                    Job(id="searched", description="searched"),
                    before=lambda item: True,
                    after=lambda item: True,
                    pooled=True,
                    terms=list(self._searched_room),
                )
            except Exception:
                log.exception("keeping searched works failed")

    def add_upload(
        self,
        data: bytes,
        *,
        kind: ItemKind,
        title: str = "",
        artist: str = "",
        description: str = "",
        photo: PhotoInfo | None = None,
        look: Look | None = None,
    ) -> Item:
        item = Item(
            id=f"upload:{secrets.token_hex(6)}",
            kind=kind,
            source="upload",
            source_id="",
            title=title,
            artist=artist,
            description=description,
            date_text=(photo.taken_at or "")[:10] if photo else "",
            added_at=now_iso(),
            photo=photo,
            look=look,
        )
        width, height = self.cache.store(item, data)
        return self.add(item.model_copy(update={"width": width, "height": height}))

    def start_job(self, description: str, work: Callable[[Job], None]) -> Job:
        job = Job(id=secrets.token_hex(4), description=description)
        self.jobs[job.id] = job

        def run() -> None:
            try:
                work(job)
            except Exception as err:
                log.exception("job %s failed", description)
                job.error = str(err)
            finally:
                job.finished = True

        threading.Thread(target=run, name=f"job-{description}", daemon=True).start()
        return job
