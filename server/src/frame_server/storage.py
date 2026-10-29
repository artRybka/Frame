"""How much disk the library takes, and how much it may take.

Two limits: ``catalogue_mb`` for the catalogue's thumbnails and
``image_cache_mb`` for the originals the server can download again (museum
works, shared-album photos). Uploads and other only copies are always kept
and fall under neither. frame.env (or the add-on options) gives the
defaults; a limit set in the app wins and survives restarts, and picking the
default again (or resetting) goes back to frame.env. The values live on the
shared ``Settings``, so the next trim or growth of the catalogue uses them.

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
from .library.icloud import only_copy

if TYPE_CHECKING:
    from .config import Settings
    from .library import ImageCache, Library
    from .store import ContentStore

#: Up to add-on 0.28: one limit for both, split in frame.env's proportion.
OLD_KEY = "storage_limit"
CATALOGUE_KEY = "catalogue_limit"
ORIGINALS_KEY = "originals_limit"
#: The originals' default before add-on 0.29, for the old limit's split.
OLD_CACHE_MB = 500
MB = 1024 * 1024
#: How long a measurement is good for, in seconds.
MEASURE_MAX_AGE = 600.0


class StorageUsage(BaseModel):
    catalogue_bytes: int  # thumbnails of the works the app browses
    originals_bytes: int  # display-size originals the server can download again
    own_bytes: int  # uploads and photos it cannot: always kept, outside the limits
    panel_bytes: int  # pictures prepared for the panel and their previews
    database_bytes: int
    total_bytes: int
    free_bytes: int | None  # free on the disk the library is on
    measured_at: float  # Unix time


class StorageView(BaseModel):
    usage: StorageUsage
    catalogue_mb: int
    catalogue_default_mb: int  # from frame.env / add-on options
    catalogue_from_app: bool
    originals_mb: int
    originals_default_mb: int
    originals_from_app: bool


class StorageUpdate(BaseModel):
    """Either limit or both; the default value goes back to frame.env."""

    catalogue_mb: int | None = Field(default=None, ge=100, le=1_000_000)
    originals_mb: int | None = Field(default=None, ge=100, le=1_000_000)


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
        self._migrate()
        catalogue = library.get_state(CATALOGUE_KEY)
        if catalogue:
            settings.catalogue_mb = int(catalogue)
        originals = library.get_state(ORIGINALS_KEY)
        if originals:
            settings.image_cache_mb = int(originals)

    def _migrate(self) -> None:
        """The one limit of add-on 0.28 and before: the catalogue keeps its
        share, the originals keep theirs if it was larger than the new
        default."""
        old = self.library.get_state(OLD_KEY)
        if not old:
            return
        catalogue, cache = self.defaults
        then = cache if "image_cache_mb" in self.settings.model_fields_set else OLD_CACHE_MB
        share = catalogue / (catalogue + then) if catalogue + then else 2 / 3
        old_catalogue = round(int(old) * share)
        with self.library.batch():
            if old_catalogue != catalogue:
                self.library.set_state(CATALOGUE_KEY, old_catalogue)
            if int(old) - old_catalogue > cache:
                self.library.set_state(ORIGINALS_KEY, int(old) - old_catalogue)
            self.library.delete_state(OLD_KEY)

    def view(self) -> StorageView:
        return StorageView(
            usage=self.usage(),
            catalogue_mb=self.settings.catalogue_mb,
            catalogue_default_mb=self.defaults[0],
            catalogue_from_app=self.library.get_state(CATALOGUE_KEY) is not None,
            originals_mb=self.settings.image_cache_mb,
            originals_default_mb=self.defaults[1],
            originals_from_app=self.library.get_state(ORIGINALS_KEY) is not None,
        )

    def save(self, update: StorageUpdate) -> bool:
        """Keep the app's limits; True when one is lower than before (the
        library may need trimming now)."""
        old = (self.settings.catalogue_mb, self.settings.image_cache_mb)
        if update.catalogue_mb is not None:
            self.settings.catalogue_mb = self._keep(
                CATALOGUE_KEY, update.catalogue_mb, self.defaults[0]
            )
        if update.originals_mb is not None:
            self.settings.image_cache_mb = self._keep(
                ORIGINALS_KEY, update.originals_mb, self.defaults[1]
            )
        return self.settings.catalogue_mb < old[0] or self.settings.image_cache_mb < old[1]

    def reset(self) -> bool:
        """Back to frame.env / add-on options; True when a limit went down."""
        catalogue, originals = self.defaults
        return self.save(StorageUpdate(catalogue_mb=catalogue, originals_mb=originals))

    def _keep(self, key: str, mb: int, default: int) -> int:
        if mb == default:
            self.library.delete_state(key)
        else:
            self.library.set_state(key, mb)
        return mb

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
        own = sum(
            _size(self.images.image_path(i))
            for i in self.library.query(include_excluded=True)[1]
            if only_copy(i)
        )
        panel = dir_bytes(self.store.images) + dir_bytes(self.store.previews)
        database = sum(_size(root / f"library.db{end}") for end in ("", "-wal", "-shm"))
        try:
            free: int | None = shutil.disk_usage(root).free
        except OSError:
            free = None
        return StorageUsage(
            catalogue_bytes=catalogue,
            originals_bytes=originals - own,
            own_bytes=own,
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
