"""How much disk the library takes, and how much it may take.

frame.env (or the add-on options) gives the starting limits:
``catalogue_mb`` for the catalogue's thumbnails and ``image_cache_mb`` for
downloaded museum originals. The app sets one limit for the whole library,
split between the two in the same proportion; it wins over frame.env and
survives restarts, and resetting goes back to frame.env. The values live on
the shared ``Settings``, so the next trim or growth of the catalogue uses them.

Measuring reads a few thousand files, slow on a NAS disk: a measurement is
kept for a while and taken again after the library was trimmed.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .fsutil import dir_bytes

if TYPE_CHECKING:
    from .config import Settings
    from .library import ImageCache, Library
    from .store import ContentStore

STATE_KEY = "storage_limit"
MB = 1024 * 1024
#: How long a measurement is good for, in seconds.
MEASURE_MAX_AGE = 600.0
#: The catalogue's share of the limit when frame.env leaves both parts at 0.
CATALOGUE_SHARE = 2 / 3


class StorageUsage(BaseModel):
    catalogue_bytes: int  # thumbnails of the works the app browses
    originals_bytes: int  # display-size originals: museum cache, uploads, photos
    panel_bytes: int  # pictures prepared for the panel and their previews
    database_bytes: int
    total_bytes: int
    free_bytes: int | None  # free on the disk the library is on
    measured_at: float  # Unix time


class StorageView(BaseModel):
    usage: StorageUsage
    limit_mb: int  # catalogue + originals; what the app shows and sets
    default_mb: int  # from frame.env / add-on options
    catalogue_mb: int
    image_cache_mb: int
    from_app: bool


class StorageUpdate(BaseModel):
    limit_mb: int = Field(ge=100, le=1_000_000)


class StorageStore:
    def __init__(
        self, settings: Settings, library: Library, images: ImageCache, store: ContentStore
    ) -> None:
        self.settings = settings
        self.library = library
        self.images = images
        self.store = store
        self.defaults = (settings.catalogue_mb, settings.image_cache_mb)
        self._usage: StorageUsage | None = None
        self._measuring = threading.Lock()
        saved = library.get_state(STATE_KEY)
        if saved:
            self._apply(int(saved))

    @property
    def from_app(self) -> bool:
        return self.library.get_state(STATE_KEY) is not None

    @property
    def default_mb(self) -> int:
        return sum(self.defaults)

    @property
    def limit_mb(self) -> int:
        return self.settings.catalogue_mb + self.settings.image_cache_mb

    def view(self) -> StorageView:
        return StorageView(
            usage=self.usage(),
            limit_mb=self.limit_mb,
            default_mb=self.default_mb,
            catalogue_mb=self.settings.catalogue_mb,
            image_cache_mb=self.settings.image_cache_mb,
            from_app=self.from_app,
        )

    def save(self, update: StorageUpdate) -> bool:
        """Keep the app's limit; True when it is lower than before (the
        library may need trimming now)."""
        old = self.limit_mb
        self.library.set_state(STATE_KEY, update.limit_mb)
        self._apply(update.limit_mb)
        return update.limit_mb < old

    def reset(self) -> bool:
        """Back to frame.env / add-on options; True when the limit went down."""
        old = self.limit_mb
        self.library.delete_state(STATE_KEY)
        self.settings.catalogue_mb, self.settings.image_cache_mb = self.defaults
        return self.limit_mb < old

    def _apply(self, limit_mb: int) -> None:
        catalogue, cache = self.defaults
        share = catalogue / (catalogue + cache) if catalogue + cache else CATALOGUE_SHARE
        self.settings.catalogue_mb = round(limit_mb * share)
        self.settings.image_cache_mb = limit_mb - self.settings.catalogue_mb

    # -- measuring -----------------------------------------------------------

    def usage(self, max_age: float = MEASURE_MAX_AGE) -> StorageUsage:
        """The last measurement, or a new one when it is older than ``max_age``."""
        with self._measuring:
            usage = self._usage
            if usage is None or time.time() - usage.measured_at > max_age:
                usage = self._usage = self._measure()
            return usage

    def forget(self) -> None:
        """The library changed a lot (trimmed): measure again when asked."""
        self._usage = None

    def _measure(self) -> StorageUsage:
        root = self.settings.data_dir
        catalogue = dir_bytes(self.images.thumbs)
        originals = dir_bytes(self.images.images)
        panel = dir_bytes(self.store.images) + dir_bytes(self.store.previews)
        database = sum(_size(root / f"library.db{end}") for end in ("", "-wal", "-shm"))
        try:
            free: int | None = shutil.disk_usage(root).free
        except OSError:
            free = None
        return StorageUsage(
            catalogue_bytes=catalogue,
            originals_bytes=originals,
            panel_bytes=panel,
            database_bytes=database,
            total_bytes=catalogue + originals + panel + database,
            free_bytes=free,
            measured_at=time.time(),
        )


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
