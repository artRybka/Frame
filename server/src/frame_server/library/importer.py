"""Adding pictures to the library: museum works, uploads, background jobs."""

from __future__ import annotations

import logging
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from PIL import Image

from ..imaging.palette import Palette
from .colors import analyse
from .images import ImageCache
from .models import Item, ItemKind, PhotoInfo
from .museums import client, museum
from .repo import Library, now_iso

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    description: str
    total: int = 0
    done: int = 0
    failed: int = 0
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
    ) -> None:
        self.library = library
        self.cache = cache
        self.palette = palette
        self.http = http
        self.jobs: dict[str, Job] = {}

    def add(self, item: Item) -> Item:
        """Download the thumbnail, analyse colours and store the item."""
        with Image.open(self.cache.ensure_thumb(item)) as thumb:
            colors, tags, score = analyse(thumb, self.palette)
            width, height = item.width, item.height
            if not width or not height:
                width, height = thumb.size
        return self.library.upsert(
            item.model_copy(
                update={
                    "colors": colors,
                    "color_tags": tags,
                    "suitability": score,
                    "width": width,
                    "height": height,
                }
            )
        )

    def search(
        self, source: str, query: str, limit: int = 24, page: int = 1
    ) -> tuple[int, list[Item]]:
        with self.http() as http:
            return museum(source, http).search(query, limit=limit, page=page)

    def import_one(self, source: str, source_id: str) -> Item | None:
        existing = self.library.get(f"{source}:{source_id}")
        if existing is not None:
            return existing
        with self.http() as http:
            item = museum(source, http).fetch(source_id)
        return self.add(item) if item else None

    def search_many(self, source: str, query: str, limit: int) -> list[Item]:
        """Up to ``limit`` results, over as many result pages as that takes."""
        with self.http() as http:
            source_museum = museum(source, http)
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
