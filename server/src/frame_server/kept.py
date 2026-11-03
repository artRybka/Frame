"""Originals of the works the owner keeps, always on the server.

Up to 1.90 the server downloaded an original only when someone needed it
(the frame, a card, a study), so a favourite nobody had opened had none.
Mateusz, 2026-11-03 (rule A of the proposal "Więcej oryginałów dzieł na
serwerze"): the works in Favourites (anyone's) and on manual and album
playlists keep their original on the server. A work just kept is downloaded
in the background at once; what is still missing (added before, the museum
was down) is downloaded at night, gently for the museums: one at a time
with a pause, a host that turns us away left alone for the night, a work
whose original is refused not asked for again for a month. Only up to
``FILL`` of the originals' limit, so the trim does not delete at once what
the night downloaded.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

from .library import Item
from .library.hosts import Resting
from .library.icloud import only_copy
from .library.images import Unavailable, display_copy

if TYPE_CHECKING:
    from .night import Night
    from .service import FrameService

log = logging.getLogger(__name__)

#: Originals downloaded in one night, at most.
A_NIGHT = 300
#: Seconds between two downloads at night.
PAUSE = 2.0
#: Downloading stops when the originals take this share of their limit.
FILL = 0.9
#: How long a refused original is not asked for again.
REFUSED_FOR = timedelta(days=30)
#: Refused originals (by item id: when), across restarts.
REFUSED_KEY = "kept_refused"
#: Answers after which a host is left alone for the rest of the night.
THROTTLED = {403, 429}


def kept_ids(service: FrameService) -> set[str]:
    """The works kept by someone: anyone's Favourites and every work on a
    manual or album playlist (smart ones list none of their own)."""
    ids = {i for p in service.library.playlists() for i in p.item_ids}
    for hearts in service.library.fans().values():
        ids |= hearts
    return ids


class KeptOriginals:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self._lock = threading.Lock()
        #: Works waiting for the background download, in order.
        self._waiting: list[str] = []
        self._running = False
        self.now: Callable[[], datetime] = lambda: datetime.now(UTC)

    # -- which -----------------------------------------------------------------

    def _refused(self) -> dict[str, str]:
        data = self.service.library.get_state(REFUSED_KEY, {})
        return data if isinstance(data, dict) else {}

    def refused(self, item_id: str) -> bool:
        at = self._refused().get(item_id)
        if at is None:
            return False
        try:
            return self.now() - datetime.fromisoformat(at) < REFUSED_FOR
        except ValueError:
            return False

    def _note_refused(self, item_id: str) -> None:
        since = self.now() - REFUSED_FOR
        notes = {}
        for key, at in self._refused().items():
            try:
                if datetime.fromisoformat(at) >= since:
                    notes[key] = at
            except ValueError:
                continue
        notes[item_id] = self.now().isoformat()
        self.service.library.set_state(REFUSED_KEY, notes)

    def _wanted(self, item: Item) -> bool:
        images = self.service.images
        return (
            not item.excluded
            and not only_copy(item)  # an upload: its original is here for good
            and not images.has_image(item)
            and not images.gone(item.id)
            and not self.refused(item.id)
        )

    def missing(self) -> list[Item]:
        """Kept works without their original here, favourites first."""
        library = self.service.library
        ids = kept_ids(self.service)
        items = [i for i in map(library.get, sorted(ids)) if i is not None and self._wanted(i)]
        return sorted(items, key=lambda i: (not i.favorite, i.id))

    # -- room --------------------------------------------------------------------

    def room(self) -> int:
        """Bytes the originals may still grow by before ``FILL`` of their limit."""
        limit = self.service.settings.image_cache_mb * 1024 * 1024
        used = self.service.storage.usage().originals_bytes
        return int(limit * FILL) - used

    # -- downloading -------------------------------------------------------------

    def _download(self, item: Item) -> int:
        """The original of ``item``: its size, 0 when it cannot be had now;
        a refusal is remembered. Resting and throttled hosts raise."""
        try:
            path = self.service.images.ensure_image(item)
        except Unavailable as err:
            log.info("kept: %s; not asked again for %s days", err, REFUSED_FOR.days)
            self._note_refused(item.id)
            return 0
        except Resting:
            raise
        except httpx.HTTPStatusError as err:
            if err.response.status_code in THROTTLED:
                raise
            log.info("kept: original of %s failed: %s", item.id, err)
            return 0
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.info("kept: original of %s failed: %s", item.id, err)
            return 0
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def soon(self, item_ids: Iterable[str]) -> None:
        """Download the originals of works just kept, in the background,
        one at a time (never before what someone looks at)."""
        library = self.service.library
        new = [i.id for i in map(library.get, item_ids) if i is not None and self._wanted(i)]
        if not new:
            return
        with self._lock:
            self._waiting.extend(i for i in new if i not in self._waiting)
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._drain, name="kept", daemon=True).start()

    def _drain(self) -> None:
        library = self.service.library
        try:
            room = self.room()
        except OSError:
            room = 0
        while True:
            with self._lock:
                if not self._waiting or room <= 0:
                    self._waiting.clear()
                    self._running = False
                    return
                item_id = self._waiting.pop(0)
            item = library.get(item_id)
            if item is None or not self._wanted(item):
                continue
            try:
                room -= self._download(item)
            except httpx.HTTPError as err:  # the host is resting: the night tries again
                log.info("kept: original of %s left for the night: %s", item_id, err)

    def at_night(self, night: Night) -> int:
        """The night's task: the kept works' missing originals; how many."""
        try:
            room = self.room()
        except OSError as err:
            log.warning("kept: the originals could not be measured: %s", err)
            return 0
        resting: set[str] = set()
        done = 0
        for item in self.missing():
            if done == A_NIGHT or room <= 0 or not night.quiet():
                break
            host = urlsplit(display_copy(item)).hostname or ""
            if host in resting:
                continue
            try:
                size = self._download(item)
            except httpx.HTTPError as err:
                log.info("kept: %s turned us away (%s); the rest another night", host, err)
                resting.add(host)
                continue
            if size:
                done += 1
                room -= size
            if not night.sleep(PAUSE):
                break
        if done:
            self.service.storage.forget()
        log.info("kept: %d originals downloaded, %d hosts left for later", done, len(resting))
        return done
