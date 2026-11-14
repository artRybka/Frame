"""How much disk the library takes, and how much it may take.

Two limits: ``catalogue_mb`` for the catalogue's thumbnails and
``image_cache_mb`` for the originals the server can download again (museum
works, shared-album photos). Uploads and other only copies are always kept
and fall under neither. frame.env (or the add-on options) gives the
defaults; a limit set in the app wins and survives restarts, and picking the
default again (or resetting) goes back to frame.env. The values live on the
shared ``Settings``, so the next trim or growth of the catalogue uses them.

Measuring asks the disk about every thumbnail and original, slow on a NAS
disk (3.5 to 45 s, the audit of 2026-11-14): a measurement is kept for a
while, also over a restart, and taken again after the library was trimmed.
Konfiguracja is shown the one kept at once (:meth:`StorageStore.shown`).
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

from .fsutil import dir_bytes, own_names
from .library.icloud import only_copy
from .library.models import ItemKind

if TYPE_CHECKING:
    from .config import Settings
    from .library import ImageCache, Library
    from .store import ContentStore

log = logging.getLogger(__name__)

#: Up to add-on 0.28: one limit for both, split in frame.env's proportion.
OLD_KEY = "storage_limit"
CATALOGUE_KEY = "catalogue_limit"
ORIGINALS_KEY = "originals_limit"
#: The originals' default before add-on 0.29, for the old limit's split.
OLD_CACHE_MB = 500
MB = 1024 * 1024
#: The last measurement, kept over a restart.
USAGE_KEY = "storage_usage"
#: How long a measurement is good for, in seconds.
MEASURE_MAX_AGE = 600.0
#: How long Konfiguracja waits for a new measurement before it is shown the
#: one kept (seconds): a fast disk answers within it.
SHOWN_WAIT = 1.0
#: How long a count of the catalogue is good for, in seconds.
COUNT_MAX_AGE = 60.0
#: The frame's long side: an original at least this large shows it whole.
FRAME_SIDE = 2560


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
    #: The catalogue reached its limit: the server takes no more works in
    #: itself, none to replace others (Mateusz 2026-11-07).
    catalogue_full: bool = False


class CatalogueCounts(BaseModel):
    """How many works the server has gathered (Konfiguracja → Miejsce na
    serwerze, Mateusz 2026-11-10), hidden ones and fragments of works left
    out."""

    #: Museum works, each once: other copies of one work, its details and
    #: photographs of it on a wall are not counted.
    works: int
    #: Museum pictures in all, copies, details and those photographs counted.
    pictures: int
    #: Works whose original (the picture for the frame, not the thumbnail) is
    #: on the server.
    originals: int
    #: Of those, the ones whose source gave a picture at least as large as
    #: the frame (:data:`FRAME_SIDE` on its long side).
    frame_size: int
    #: Uploaded works and photos.
    own: int
    counted_at: float  # Unix time


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
        self._usage: StorageUsage | None = self._kept_usage()
        self._measuring = threading.Lock()
        self._again: threading.Thread | None = None
        self._forgets = 0
        self._starting = threading.Lock()
        self._counts: CatalogueCounts | None = None
        self._counting = threading.Lock()
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
        usage = self.shown()
        return StorageView(
            usage=usage,
            catalogue_mb=self.settings.catalogue_mb,
            catalogue_default_mb=self.defaults[0],
            catalogue_from_app=self.library.get_state(CATALOGUE_KEY) is not None,
            originals_mb=self.settings.image_cache_mb,
            originals_default_mb=self.defaults[1],
            originals_from_app=self.library.get_state(ORIGINALS_KEY) is not None,
            catalogue_full=usage.catalogue_bytes >= self.settings.catalogue_mb * MB > 0,
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
                forgets = self._forgets
                usage = self._measure()
                if forgets != self._forgets:  # trimmed while it was measured
                    usage = self._measure()
                self._usage = usage
                self.library.keep_state(USAGE_KEY, usage.model_dump(mode="json"))
            return usage

    def shown(self) -> StorageUsage:
        """The measurement for Konfiguracja: the one kept, at once. When it
        is older than :data:`MEASURE_MAX_AGE` a new one is taken beside it,
        waited for :data:`SHOWN_WAIT` and shown the next time otherwise: the
        page stood with a spinner for as long as the disk took (45 s on the
        NAS after a start). What decides by the measurement (the room for
        originals) asks :meth:`usage`, as before."""
        usage = self._usage
        if usage is None:  # never measured, or the library was trimmed since
            return self.usage()
        if time.time() - usage.measured_at <= MEASURE_MAX_AGE:
            return usage
        again = self._measure_behind()
        again.join(SHOWN_WAIT)
        return self._usage or usage

    def measure_behind(self) -> None:
        """A measurement taken beside, when none is kept: after a start with
        none (the first of this version) and after the library was trimmed,
        so that Konfiguracja, opened later, need not wait for the disk
        (over two minutes while the server was starting, the NAS on
        2026-11-14)."""
        if self._usage is None:
            self._measure_behind()

    def _measure_behind(self) -> threading.Thread:
        """The thread that measures now: one at a time."""
        with self._starting:
            again = self._again
            if again is None or not again.is_alive():
                again = self._again = threading.Thread(
                    target=self._measure_again, name="storage-measure", daemon=True
                )
                again.start()
            return again

    def _measure_again(self) -> None:
        try:
            self.usage()
        except Exception as err:  # the disk, or the library closed meanwhile
            log.info("storage: not measured: %s", err)

    def _kept_usage(self) -> StorageUsage | None:
        kept = self.library.get_state(USAGE_KEY)
        if not kept:
            return None
        try:
            return StorageUsage.model_validate(kept)
        except ValidationError:
            return None

    def forget(self) -> None:
        """The library changed a lot (trimmed): measured again, beside."""
        self._forgets += 1
        self._usage = None
        self.library.keep_state(USAGE_KEY, None)
        self._measure_behind()

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

    # -- counting ------------------------------------------------------------

    def counts(self, max_age: float = COUNT_MAX_AGE) -> CatalogueCounts:
        """The catalogue counted, at most ``max_age`` seconds ago: the works
        in memory, the originals by one read of their folder."""
        with self._counting:
            counts = self._counts
            if counts is None or time.time() - counts.counted_at > max_age:
                counts = self._counts = self._count()
            return counts

    def _count(self) -> CatalogueCounts:
        on_disk = set(own_names(self.images.images))
        works = pictures = originals = frame_size = own = 0
        for item in self.library.all_items():
            if item.excluded or item.part_of:
                continue
            if item.kind != ItemKind.ARTWORK:
                own += 1
                continue
            pictures += 1
            if item.copy_of or item.detail_of or item.scene_of:
                continue
            works += 1
            if f"{item.file_stem}.jpg" not in on_disk:
                continue
            originals += 1
            size = self.images.known_size(item)
            if size is None and item.width and item.height:
                size = (item.width, item.height)
            if size is not None and max(size) >= FRAME_SIDE:
                frame_size += 1
        return CatalogueCounts(
            works=works,
            pictures=pictures,
            originals=originals,
            frame_size=frame_size,
            own=own,
            counted_at=time.time(),
        )


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
