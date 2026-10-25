"""Adding pictures to the library: museum works, uploads, background jobs."""

from __future__ import annotations

import logging
import random
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
from .images import ImageCache
from .lifespan import LifeDates
from .models import Item, ItemKind, PhotoInfo, PlaylistRules
from .museums import MUSEUMS, Access, Discovery, Kind, Museum, available, client, museum
from .repo import Library, matches, now_iso
from .vocabulary import is_manuscript, museum_kind, museum_queries, wants_manuscripts, years

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


def span(rules: PlaylistRules) -> tuple[int | None, int | None]:
    """The years ``rules`` allow: their own range within their periods'."""
    start, end = years(rules.terms)
    if rules.year_from is not None:
        start = rules.year_from if start is None else max(start, rules.year_from)
    if rules.year_to is not None:
        end = rules.year_to if end is None else min(end, rules.year_to)
    return start, end


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
            colors, tags, score = analyse(thumb, self.palette)
            spread = tint_spread(thumb)
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
        self.remember(items)
        return total, items

    def import_one(self, source: str, source_id: str) -> Item | None:
        return self.save(f"{source}:{source_id}")

    def search_all(
        self, query: str, limit: int = 8, page: int = 1
    ) -> tuple[int, list[Item], list[str]]:
        """``limit`` results from every museum at once, interleaved; returns
        (total, items, museums that failed)."""
        return self._from_all(lambda key: self.search(key, query, limit, page))

    def _from_all(
        self, ask: Callable[[str], tuple[int, list[Item]]]
    ) -> tuple[int, list[Item], list[str]]:
        keys = self.sources()
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
        mixed = [i for i in chain.from_iterable(zip_longest(*found)) if i is not None]
        self.remember(mixed)
        return total, mixed, failed

    def search_many(self, source: str, query: str, limit: int) -> list[Item]:
        """Up to ``limit`` results, over as many result pages as that takes."""
        with self.http() as http:
            source_museum = museum(source, http, self.access())
            size = min(limit, source_museum.page_size)
            found: list[Item] = []
            page = 1
            while len(found) < limit:
                total, items = source_museum.search(query, limit=size, page=page)
                found += items
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
        if job is not None:
            job.total += len(found)
        added = []
        for item in found:
            try:
                stored = self.library.get(item.id) or self.add(item)
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
                # Named artists or words: the museums' own search finds them.
                queries = rules.artists or [rules.query]
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
        self, spec: Discovery, limit: int = 8, page: int = 1
    ) -> tuple[int, list[Item], list[str]]:
        """Like :meth:`search_all`, for works matching ``spec``."""

        def one(key: str) -> tuple[int, list[Item]]:
            with self.http() as http:
                return museum(key, http, self.access()).discover(spec, limit, page)

        return self._from_all(one)

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
                if self.library.has(item.id) or not before(item):
                    continue
                if not manuscripts and is_manuscript(item):
                    job.skipped += 1
                    continue
                try:
                    analysed = self._analysed(item)
                except (httpx.HTTPError, OSError) as err:
                    log.warning("import of %s failed: %s", item.id, err)
                    job.failed += 1
                    continue
                if not after(analysed):
                    self.cache.remove(item)
                    job.skipped += 1
                    continue
                self.library.upsert(analysed.model_copy(update={"pooled": pooled}))
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
