"""What the panel is (supposed to be) showing, persisted on disk.

The panel remembers the content URL it was given and re-fetches it later
(e.g. after waking up). If that URL ever 404s it shows "Configuration
error", so the current content must survive server restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .device.manifest import Manifest, ManifestItem, new_file_id

log = logging.getLogger(__name__)

KEEP_IMAGES = 20


@dataclass
class ContentInfo:
    file_id: str
    file_name: str
    mime: str
    size: int
    created: str
    title: str = ""
    description: str = ""
    source: str = ""
    render: dict[str, object] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class PanelRequest:
    time: str
    client: str
    method: str
    path: str
    status: int
    user_agent: str
    headers: dict[str, str]


class ContentStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir
        self.images = data_dir / "images"
        self.previews = data_dir / "previews"
        for d in (self.root, self.images, self.previews):
            d.mkdir(parents=True, exist_ok=True)
        self._current_file = data_dir / "current.json"
        self._log_file = data_dir / "panel-requests.jsonl"
        self.recent_requests: deque[PanelRequest] = deque(maxlen=200)
        self._fetch_waiters: dict[str, asyncio.Event] = {}

    # -- content ------------------------------------------------------------

    def current(self) -> ContentInfo | None:
        if not self._current_file.is_file():
            return None
        return ContentInfo(**json.loads(self._current_file.read_text()))

    def publish(
        self,
        image: bytes,
        ext: str,
        *,
        preview_png: bytes | None = None,
        title: str = "",
        description: str = "",
        source: str = "",
        render: dict[str, object] | None = None,
        extra: dict[str, object] | None = None,
    ) -> ContentInfo:
        file_id = new_file_id()
        name = f"{file_id}.{ext}"
        (self.images / name).write_bytes(image)
        if preview_png is not None:
            (self.previews / f"{file_id}.png").write_bytes(preview_png)
        info = ContentInfo(
            file_id=file_id,
            file_name=name,
            mime="image/png" if ext == "png" else "image/jpeg",
            size=len(image),
            created=datetime.now(UTC).isoformat(timespec="seconds"),
            title=title,
            description=description,
            source=source,
            render=render or {},
            extra=extra or {},
        )
        tmp = self._current_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(info), indent=2))
        tmp.replace(self._current_file)
        self._prune()
        return info

    def _prune(self) -> None:
        current = self.current()
        files = sorted(self.images.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[KEEP_IMAGES:]:
            if current and old.name == current.file_name:
                continue
            old.unlink(missing_ok=True)
            (self.previews / f"{old.stem}.png").unlink(missing_ok=True)

    def image_path(self, name: str) -> Path | None:
        path = self.images / Path(name).name
        return path if path.is_file() else None

    def preview_path(self, file_id: str) -> Path | None:
        path = self.previews / f"{Path(file_id).name}.png"
        return path if path.is_file() else None

    def manifest(self, base_url: str) -> Manifest | None:
        info = self.current()
        if info is None:
            return None
        item = ManifestItem(
            image_url=f"{base_url}/panel/images/{info.file_name}",
            file_id=info.file_id,
            file_name=info.file_name,
            file_size=info.size,
        )
        return Manifest.single(item, manifest_id=info.file_id)

    # -- panel request log -------------------------------------------------

    def log_request(self, req: PanelRequest) -> None:
        self.recent_requests.append(req)
        with self._log_file.open("a") as fh:
            fh.write(json.dumps(asdict(req)) + "\n")
        if req.path.startswith("/panel/images/") and req.status == 200:
            file_id = Path(req.path).stem
            waiter = self._fetch_waiters.get(file_id)
            if waiter:
                waiter.set()

    def expect_fetch(self, file_id: str) -> None:
        """Start listening for the panel's download before triggering it."""
        self._fetch_waiters.setdefault(file_id, asyncio.Event())

    async def wait_for_fetch(self, file_id: str, timeout: float) -> bool:
        event = self._fetch_waiters.setdefault(file_id, asyncio.Event())
        start = time.monotonic()
        try:
            await asyncio.wait_for(event.wait(), timeout)
            log.info("panel fetched %s after %.1fs", file_id, time.monotonic() - start)
            return True
        except TimeoutError:
            return False
        finally:
            self._fetch_waiters.pop(file_id, None)
