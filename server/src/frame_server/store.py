"""What the panel is (supposed to be) showing, persisted on disk.

The panel remembers the content URL it was given and re-fetches it later
(e.g. after waking up). If that URL ever 404s it shows "Configuration
error", so the current content must survive server restarts.

What it actually shows is the content whose image it downloaded last: a
picture published while the panel slept or did not answer is not on it yet.
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
from .fsutil import own_files

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
class Delivery:
    """What reached the panel: the content it downloaded last, and why the
    last push of another one did not get there."""

    shown: ContentInfo | None = None
    shown_at: str | None = None
    failed_file_id: str | None = None
    failed_at: str | None = None
    failure: str | None = None  # "timeout" (sent, never downloaded) or "error"
    message: str = ""

    @classmethod
    def from_json(cls, data: dict[str, object]) -> Delivery:
        shown = data.get("shown")
        fields = {k: v for k, v in data.items() if k != "shown"}
        return cls(
            shown=ContentInfo(**shown) if isinstance(shown, dict) else None,
            **fields,  # type: ignore[arg-type]
        )


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
        # The Frame app's full-colour 1920x1080 copies (panel_app.py).
        self.app_images = data_dir / "app-images"
        for d in (self.root, self.images, self.previews, self.app_images):
            d.mkdir(parents=True, exist_ok=True)
        self._current_file = data_dir / "current.json"
        self._log_file = data_dir / "panel-requests.jsonl"
        self._delivery_file = data_dir / "delivery.json"
        self.recent_requests: deque[PanelRequest] = deque(maxlen=200)
        self._fetch_waiters: dict[str, asyncio.Event] = {}
        if not self._delivery_file.is_file():
            self._recover_delivery()

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
        app_jpeg: bytes | None = None,
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
        if app_jpeg:
            (self.app_images / f"{file_id}.jpg").write_bytes(app_jpeg)
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
        files = sorted(own_files(self.images), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[KEEP_IMAGES:]:
            if current and old.name == current.file_name:
                continue
            old.unlink(missing_ok=True)
            (self.previews / f"{old.stem}.png").unlink(missing_ok=True)
            (self.app_images / f"{old.stem}.jpg").unlink(missing_ok=True)

    def image_path(self, name: str) -> Path | None:
        path = self.images / Path(name).name
        return path if path.is_file() else None

    def app_image_path(self, file_id: str) -> Path:
        """Where the Frame app's copy of ``file_id`` is (or goes)."""
        return self.app_images / f"{Path(file_id).name}.jpg"

    def panel_file(self, file_id: str) -> Path | None:
        """The panel image of ``file_id``, whatever its extension."""
        found = sorted(own_files(self.images, f"{Path(file_id).name}.*"))
        return found[0] if found else None

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

    # -- what reached the panel ----------------------------------------------

    def delivery(self) -> Delivery:
        if not self._delivery_file.is_file():
            return Delivery()
        try:
            return Delivery.from_json(json.loads(self._delivery_file.read_text()))
        except (OSError, ValueError, TypeError) as err:
            log.warning("ignoring unreadable %s: %s", self._delivery_file, err)
            return Delivery()

    def _save_delivery(self, delivery: Delivery) -> None:
        tmp = self._delivery_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(delivery), indent=2))
        tmp.replace(self._delivery_file)

    def on_panel(self) -> bool | None:
        """Whether the panel has downloaded the current content; None: not known."""
        current, shown = self.current(), self.delivery().shown
        if current is None or shown is None:
            return None
        return shown.file_id == current.file_id

    def note_downloaded(self, file_id: str, at: str | None = None) -> None:
        """The panel downloaded an image. Only the current content's counts:
        it is what content.json points to."""
        current = self.current()
        if current is None or current.file_id != file_id:
            return
        delivery = self.delivery()
        if delivery.shown and delivery.shown.file_id == file_id:
            return
        delivery.shown = current
        delivery.shown_at = at or datetime.now(UTC).isoformat(timespec="seconds")
        if delivery.failed_file_id == file_id:
            delivery.failed_file_id = delivery.failed_at = delivery.failure = None
            delivery.message = ""
        self._save_delivery(delivery)

    def note_failed(self, file_id: str, failure: str, message: str) -> None:
        """A push of ``file_id`` did not get it onto the panel."""
        delivery = self.delivery()
        if delivery.shown and delivery.shown.file_id == file_id:
            return  # downloaded after all
        delivery.failed_file_id = file_id
        delivery.failed_at = datetime.now(UTC).isoformat(timespec="seconds")
        delivery.failure = failure
        delivery.message = message
        self._save_delivery(delivery)

    def _recover_delivery(self) -> None:
        """Before delivery.json: the last download in the request log."""
        if not self._log_file.is_file():
            return
        try:
            with self._log_file.open("rb") as fh:
                fh.seek(max(0, fh.seek(0, 2) - 256 * 1024))
                lines = fh.read().decode(errors="replace").splitlines()
        except OSError:
            return
        for line in reversed(lines):
            try:
                req = json.loads(line)
            except ValueError:
                continue
            path = str(req.get("path", ""))
            if path.startswith("/panel/images/") and req.get("status") == 200:
                self.note_downloaded(Path(path).stem, at=req.get("time"))
                return

    # -- panel request log -------------------------------------------------

    def log_request(self, req: PanelRequest) -> None:
        self.recent_requests.append(req)
        with self._log_file.open("a") as fh:
            fh.write(json.dumps(asdict(req)) + "\n")
        picture = req.path.startswith(("/panel/images/", "/panel/app-images/"))
        if picture and req.status == 200:
            file_id = Path(req.path).stem
            self.note_downloaded(file_id, at=req.time)
            waiter = self._fetch_waiters.get(file_id)
            if waiter:
                waiter.set()

    def expect_fetch(self, file_id: str) -> None:
        """Start listening for the panel's download before triggering it."""
        self._fetch_waiters.setdefault(file_id, asyncio.Event())

    def cancel_fetch(self, file_id: str) -> None:
        self._fetch_waiters.pop(file_id, None)

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
