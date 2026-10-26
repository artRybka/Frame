"""Adding pictures to the library: museum works, uploads, background jobs."""

from __future__ import annotations

import logging
import random
import re
import secrets
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from itertools import chain, zip_longest

import httpx
from PIL import Image

from ..imaging.palette import Palette
from .colors import analyse, tint_spread
from .duplicates import dedupe, rank
from .images import ImageCache
from .lifespan import LifeDates
from .models import Item, ItemKind, PhotoInfo, PlaylistRules
from .museums import MUSEUMS, Access, Discovery, Kind, Museum, available, client, museum
from .repo import Library, matches, now_iso
from .vocabulary import (
    is_copy,
    is_grey_painting,
    is_manuscript,
    is_painting,
    museum_kind,
    museum_queries,
    wants_manuscripts,
    years,
)

log = logging.getLogger(__name__)

#: Pseudo source: every museum at once.
ALL = "all"
#: Museums asked for works by the artists the owner likes.
TASTE_SOURCES = ("aic", "cma", "met", "rijks", "europeana")
#: Museums that draw random paintings for variety.
DRAW_SOURCES = ("aic", "cma", "met", "rijks", "europeana")
#: Museum works seen in search results, kept in memory so that opening one
#: needs no second request.
REMOTE_MEMO = 500
#: Sources whose paintings often come as black-and-white copies (album
#: plates, old photographs): their results' thumbnails are looked at before
#: they are shown. How many verdicts are remembered.
GREY_PRONE = ("wmc", "europeana")
SPREAD_MEMO = 20_000


def small_thumb(item: Item) -> str:
    """A small version of ``item``'s thumbnail, enough to judge its colour:
    Commons' 120 px step, Europeana's 200 px preview."""
    url = item.thumb_url
    if item.source == "wmc" and "/thumb/" in url:
        return re.sub(r"/\d+px-([^/]+)$", r"/120px-\1", url)
    if item.source == "europeana":
        return url.replace("size=w400", "size=w200")
    return url


def span(rules: PlaylistRules) -> tuple[int | None, int | None]:
    """The years ``rules`` allow: their own range within their periods'."""
    start, end = years(rules.terms)
    if rules.year_from is not None:
        start = rules.year_from if start is None else max(start, rules.year_from)
    if rules.year_to is not None:
        end = rules.year_to if end is None else min(end, rules.year_to)
    return start, end


def fill_queries(rules: PlaylistRules) -> list[str]:
    """What Discover's search asks the museums for ``rules``, one text per
    artist: the words, the artist and the first style or subject."""
    topics = museum_queries(rules.terms)[:1]
    words = rules.query.strip()
    texts = [" ".join(w for w in (words, artist, *topics) if w) for artist in rules.artists or [""]]
    return [t for t in dict.fromkeys(texts) if t]


def _search_stream(source: Museum, query: str) -> Iterator[Item]:
    """A museum's search results, page after page."""
    size = min(source.page_size, 24)
    page = 1
    while True:
        total, items = source.search(query, limit=size, page=page)
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
        self._tags: OrderedDict[str, list[str]] = OrderedDict()

    def access(self) -> Access:
        """The owner's current choices, with the shared death-year cache."""
        access = self._access()
        if self.life.europeana_key != access.europeana_key:
            self.life = LifeDates(access.europeana_key)
        return replace(access, life=self.life)

    def sources(self) -> list[str]:
        """Keys of the sources on offer now."""
        return list(available(self.access()))

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
        source, _, source_id = item_id.partition(":")
        if source not in self.sources() or not source_id:
            return None
        with self.http() as http:
            item = museum(source, http, self.access()).fetch(source_id)
        if item is not None:
            self.remember([item])
        return item

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

    def _analysed(self, item: Item) -> Item:
        with Image.open(self.cache.ensure_thumb(item)) as thumb:
            spread = tint_spread(thumb)
            colors, tags, score = analyse(thumb, self.palette, spread)
            width, height = item.width, item.height
            if not width or not height:
                width, height = thumb.size
        return item.model_copy(
            update={
                "colors": colors,
                "color_tags": tags,
                "suitability": score,
                "tint_spread": spread,
                "width": width,
                "height": height,
            }
        )

    def search(
        self, source: str, query: str, limit: int = 24, page: int = 1
    ) -> tuple[int, list[Item]]:
        with self.http() as http:
            total, items = museum(source, http, self.access()).search(query, limit=limit, page=page)
        items = self.without_grey([i for i in items if not is_copy(i)])
        self.remember(items)
        return total, items

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
            with self.cache.sample(small_thumb(item)) as img:
                spread = tint_spread(img)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.info("no thumbnail of %s to look at: %s", item.id, err)
            return None
        with self._remote_lock:
            self._spreads[item.id] = spread
            while len(self._spreads) > SPREAD_MEMO:
                self._spreads.popitem(last=False)
        return spread

    def color_tags_of(self, item: Item) -> list[str] | None:
        """``item``'s colour tags, from the library, memory or a small
        thumbnail; None when the thumbnail cannot be had."""
        if item.color_tags:
            return item.color_tags
        stored = self.library.get(item.id)
        if stored is not None and stored.color_tags:
            return stored.color_tags
        with self._remote_lock:
            if item.id in self._tags:
                return self._tags[item.id]
        try:
            with self.cache.sample(small_thumb(item)) as img:
                spread = tint_spread(img)
                _, tags, _ = analyse(img, self.palette, spread)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.info("no thumbnail of %s to look at: %s", item.id, err)
            return None
        with self._remote_lock:
            self._tags[item.id] = tags
            self._spreads[item.id] = spread
            for memo in (self._tags, self._spreads):
                while len(memo) > SPREAD_MEMO:
                    memo.popitem(last=False)
        return tags

    def in_colors(self, items: list[Item], colors: list[str]) -> list[Item]:
        """``items`` with any of ``colors`` (colour or mood tags), judged
        from their thumbnails; museums don't know colours."""
        if not colors or not items:
            return items
        with ThreadPoolExecutor(min(len(items), 16)) as pool:
            found = list(pool.map(self.color_tags_of, items))
        wanted = set(colors)
        return [i for i, tags in zip(items, found, strict=True) if tags and wanted & set(tags)]

    def without_grey(self, items: list[Item]) -> list[Item]:
        """``items`` without black-and-white copies of paintings, for the
        sources that have many (:data:`GREY_PRONE`)."""
        suspects = [i for i in items if i.source in GREY_PRONE and i.thumb_url and is_painting(i)]
        if not suspects:
            return items
        with ThreadPoolExecutor(min(len(suspects), 8)) as pool:
            found = pool.map(self.spread_of, suspects)
            spreads = {i.id: spread for i, spread in zip(suspects, found, strict=True)}
        return [
            i for i in items if i.id not in spreads or not is_grey_painting(i, spread=spreads[i.id])
        ]

    def import_one(self, source: str, source_id: str) -> Item | None:
        return self.save(f"{source}:{source_id}")

    def search_all(
        self, query: str, limit: int = 8, page: int = 1, keys: list[str] | None = None
    ) -> tuple[int, list[Item], list[str]]:
        """``limit`` results from every museum (or those of ``keys``) at
        once, interleaved; returns (total, items, museums that failed)."""
        return self._from_all(lambda key: self.search(key, query, limit, page), keys)

    def _from_all(
        self, ask: Callable[[str], tuple[int, list[Item]]], keys: list[str] | None = None
    ) -> tuple[int, list[Item], list[str]]:
        keys = keys or self.sources()
        with ThreadPoolExecutor(len(keys)) as pool:
            futures = {k: pool.submit(ask, k) for k in keys}
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
            keys = self.sources()
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
        # Test-only sources just when the playlist names them.
        sources = [s for s in rules.sources if s in offered] or [
            s for s in offered if not MUSEUMS[s].testing
        ]
        # Colours and suitability are only known once the thumbnail is in.
        cheap = rules.model_copy(update={"colors": [], "min_suitability": None})
        with self.http() as http:
            museums = [museum(s, http, self.access()) for s in sources]
            if rules.artists or rules.query:
                # Named artists or words: the museums' own search finds them,
                # asked first as Discover's search asks (with the words and a
                # style or subject), then by the artist or words alone.
                alone = rules.artists or [rules.query]
                queries = list(dict.fromkeys([*fill_queries(rules), *alone]))
                streams = [_search_stream(m, q) for q in queries for m in museums]
            else:
                texts = [*rules.styles, *rules.subjects, *museum_queries(rules.terms)] or [""]
                year_from, year_to = span(rules)
                kind = museum_kind(rules.terms)
                streams = [
                    m.random_draw(
                        Discovery(year_from=year_from, year_to=year_to, style=text, kind=kind),
                        rng,
                    )
                    for text in texts
                    for m in museums
                ]
            rng.shuffle(streams)
            self._take(
                streams,
                count,
                job,
                before=lambda item: matches(item, cheap),
                after=lambda item: matches(item, rules),
                pooled=pooled,
                manuscripts=wants_manuscripts(rules.terms),
            )

    def collect(
        self,
        count: int,
        job: Job,
        *,
        artists: Iterable[str] = (),
        queries: Iterable[tuple[str, str]] = (),
        kinds: Iterable[Kind] = ("painting",),
        min_suitability: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        """Add ``count`` works the server picks (``pooled``), taking turns
        between works by ``artists``, the museum searches ``queries`` (e.g.
        a theme) and works of ``kinds`` drawn at random; works below
        ``min_suitability`` are left out."""
        rng = rng or random.Random()
        with self.http() as http:

            def source(key: str) -> Museum:
                return museum(key, http, self.access())

            streams = [_search_stream(source(s), a) for a in artists for s in TASTE_SOURCES]
            streams += [_search_stream(source(s), q) for s, q in queries]
            streams += [
                source(s).random_draw(Discovery(kind=kind), rng)
                for kind in kinds
                for s in DRAW_SOURCES
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
        manuscripts: bool = False,
    ) -> None:
        """Take turns between ``streams`` until ``count`` new works pass
        ``before`` (on museum data) and ``after`` (once analysed); pages of
        manuscripts only with ``manuscripts``."""
        job.total = count
        drawn = 0
        while streams and job.done < count and drawn < max(count * 20, 200):
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
                if self.library.has(item.id) or self.copy_of(item) or not before(item):
                    continue
                if is_copy(item) or (not manuscripts and is_manuscript(item)):
                    job.skipped += 1
                    continue
                try:
                    analysed = self._analysed(item)
                except (httpx.HTTPError, OSError) as err:
                    log.warning("import of %s failed: %s", item.id, err)
                    job.failed += 1
                    continue
                # Black-and-white copies of paintings only show once analysed.
                if is_grey_painting(analysed) or not after(analysed):
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

    def add_upload(
        self,
        data: bytes,
        *,
        kind: ItemKind,
        title: str = "",
        artist: str = "",
        description: str = "",
        photo: PhotoInfo | None = None,
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

        threading.Thread(target=run, name=f"job-{job.id}", daemon=True).start()
        return job
