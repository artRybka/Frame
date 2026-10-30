"""Updating the server from the app, on Synology.

The server has no access to Docker. Next to it runs `frame updater` (see
updater.py), a second container of the same image with the Docker socket and
no network. They share data/update/: the server leaves a request there
(``request.json``, "check" or "update") and the helper answers in
``status.json``: what the `frame` container runs, what the registry has, and
how the last update went.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from . import build_version
from .config import ADDON_OPTIONS

Action = Literal["check", "update"]
State = Literal["idle", "checking", "updating", "failed"]

# The helper writes status.json at least this often while it runs.
HEARTBEAT = timedelta(minutes=5)
# Longer than a heartbeat and a slow pull: no word from it since, no helper.
GONE_AFTER = timedelta(minutes=15)


class ImageInfo(BaseModel):
    id: str
    version: str | None = None  # org.opencontainers.image.version (publish.yml)
    revision: str | None = None  # the commit it was built from
    created: str | None = None


class LastUpdate(BaseModel):
    at: str
    from_version: str | None = None
    to_version: str | None = None
    ok: bool
    error: str | None = None


class UpdaterStatus(BaseModel):
    """status.json, written only by the helper."""

    alive_at: str | None = None
    container: str = "frame"
    image: str | None = None  # the reference the container was created from
    state: State = "idle"
    running: ImageInfo | None = None
    latest: ImageInfo | None = None
    checked_at: str | None = None
    error: str | None = None
    last_update: LastUpdate | None = None

    @property
    def update_available(self) -> bool:
        return bool(self.running and self.latest and self.latest.id != self.running.id)


class ServerUpdateView(BaseModel):
    """GET /api/server/update."""

    version: str  # this server
    # A Home Assistant add-on: HA updates it, not the app.
    addon: bool = False
    # The helper runs next to the server (Synology with the `updater`
    # service); otherwise the app explains the one-time setup.
    updater: bool
    state: State = "idle"
    update_available: bool = False
    latest_version: str | None = None
    latest_revision: str | None = None
    # While updating: the version being replaced. The new server answers
    # before the helper is done with it, so `version` is already the new one.
    updating_from: str | None = None
    checked_at: str | None = None
    error: str | None = None
    last_update: LastUpdate | None = None
    # Left for the helper, not picked up yet (it looks every few seconds).
    pending: Action | None = None


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(text)
    tmp.replace(path)


class UpdateFolder:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.status_file = folder / "status.json"
        self.request_file = folder / "request.json"

    def status(self) -> UpdaterStatus | None:
        try:
            return UpdaterStatus.model_validate_json(self.status_file.read_text())
        except (OSError, ValidationError):
            return None

    def save_status(self, status: UpdaterStatus) -> None:
        _write(self.status_file, status.model_dump_json(indent=2))

    def request(self, action: Action) -> None:
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        _write(self.request_file, json.dumps({"action": action, "at": stamp}))

    def pending(self) -> Action | None:
        try:
            action = json.loads(self.request_file.read_text()).get("action")
        except (OSError, ValueError, AttributeError):
            return None
        return action if action in ("check", "update") else None

    def take_request(self) -> Action | None:
        action = self.pending()
        self.request_file.unlink(missing_ok=True)
        return action

    def helper_alive(self, now: datetime | None = None) -> bool:
        status = self.status()
        if status is None or status.alive_at is None:
            return False
        now = now or datetime.now(UTC)
        return datetime.fromisoformat(status.alive_at) > now - GONE_AFTER

    def view(self, now: datetime | None = None) -> ServerUpdateView:
        status = self.status()
        if status is None or not self.helper_alive(now):
            return ServerUpdateView(
                version=build_version(), addon=ADDON_OPTIONS.is_file(), updater=False
            )
        latest = status.latest
        version = build_version()
        # The helper notes what runs at its checks (every few hours): the
        # server rebuilt in Container Manager meanwhile already runs the
        # newest image, though the helper still has the old one down.
        current = latest is not None and latest.version == version
        return ServerUpdateView(
            version=version,
            updater=True,
            state=status.state,
            update_available=status.update_available and not current,
            latest_version=latest.version if latest else None,
            latest_revision=latest.revision if latest else None,
            updating_from=(
                status.running.version if status.state == "updating" and status.running else None
            ),
            checked_at=status.checked_at,
            error=status.error,
            last_update=status.last_update,
            pending=self.pending(),
        )
