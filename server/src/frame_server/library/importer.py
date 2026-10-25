"""Adding pictures to the library: museum works, uploads, background jobs."""

from __future__ import annotations

import logging
import random
import secrets
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import chain, zip_longest

import httpx
from PIL import Image

from ..imaging.palette import Palette
from .colors import analyse, tint_spread
from .images import ImageCache
from .models import Item, ItemKind, PhotoInfo, PlaylistRules
from .museums import MUSEUMS, Discovery, Museum, client, museum
from .repo import Library, matches, now_iso

log = logging.getLogger(__name__)

#: Pseudo source: every museum at once.
ALL = "all"


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
        private_use: Callable[[], bool] = lambda: False,
    ) -> None:
        self.library = library
        self.cache = cache
        self.palette = palette
        self.http = http
        self.private_use = private_use
        self.jobs: dict[str, Job] = {}

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
            return museum(source, http, self.private_use()).search(query, limit=limit, page=page)

    def import_one(self, source: str, source_id: str) -> Item | None:
        existing = self.library.get(f"{source}:{source_id}")
        if existing is not None:
            return existing
        with self.http() as http:
            item = museum(source, http, self.private_use()).fetch(source_id)
        return self.add(item) if item else None

    def search_all(
        self, query: str, limit: int = 8, page: int = 1
    ) -> tuple[int, list[Item], list[str]]:
        """``limit`` results from every museum at once, interleaved; returns
        (total, items, museums that failed)."""
        with ThreadPoolExecutor(len(MUSEUMS)) as pool:
            futures = {k: pool.submit(self.search, k, query, limit, page) for k in MUSEUMS}
        found: list[list[Item]] = []
        failed: list[str] = []
        total = 0
        for key, future in futures.items():
            try:
                count, items = future.result()
            except (httpx.HTTPError, ValueError) as err:
                log.warning("search in %s failed: %s", key, err)
                failed.append(key)
                continue
            total += count
            found.append(items)
        mixed = [i for i in chain.from_iterable(zip_longest(*found)) if i is not None]
        return total, mixed, failed

    def search_many(self, source: str, query: str, limit: int) -> list[Item]:
        """Up to ``limit`` results, over as many result pages as that takes."""
        with self.http() as http:
            source_museum = museum(source, http, self.private_use())
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
            share = -(-limit // len(MUSEUMS))
            found = []
            for key in MUSEUMS:
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
            streams = [museum(s, http, self.private_use()).random_draw(spec, rng) for s in sources]
            self._take(
                streams,
                count,
                job,
                before=spec.fits,
                after=lambda item: (item.suitability or 0.0) >= min_suitability,
            )

    def fill(
        self, rules: PlaylistRules, count: int, job: Job, rng: random.Random | None = None
    ) -> None:
        """Add ``count`` museum works that ``rules`` (a smart playlist) would
        pick, from every museum the rules allow."""
        rng = rng or random.Random()
        sources = [s for s in rules.sources if s in MUSEUMS] or list(MUSEUMS)
        # Colours and suitability are only known once the thumbnail is in.
        cheap = rules.model_copy(update={"colors": [], "min_suitability": None})
        with self.http() as http:
            museums = [museum(s, http, self.private_use()) for s in sources]
            if rules.artists or rules.query:
                # Named artists or words: the museums' own search finds them.
                queries = rules.artists or [rules.query]
                streams = [_search_stream(m, q) for q in queries for m in museums]
            else:
                texts = [*rules.styles, *rules.subjects] or [""]
                streams = [
                    m.random_draw(
                        Discovery(year_from=rules.year_from, year_to=rules.year_to, style=text),
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
            )

    def _take(
        self,
        streams: list[Iterator[Item]],
        count: int,
        job: Job,
        before: Callable[[Item], bool],
        after: Callable[[Item], bool],
    ) -> None:
        """Take turns between ``streams`` until ``count`` new works pass
        ``before`` (on museum data) and ``after`` (once analysed)."""
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
                self.library.upsert(analysed)
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
