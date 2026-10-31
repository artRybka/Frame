"""Updating the server from the app, on Synology.

The server has no access to Docker. Next to it runs `frame updater` (see
updater.py), a second container of the same image with the Docker socket and
no network. They share data/update/: the server leaves a request there
(``request.json``, "check" or "update") and the helper answers in
``status.json``: what the `frame` container runs, what the registry has, and
how the last update went. A check asked from the app the server answers
itself, from the registry (registry.py), in ``registry.json``: no need to
wait for the helper to pull the image.
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


class RegistryCheck(BaseModel):
    """registry.json, written only by the server: what the tag pointed at
    when the app last asked."""

    checked_at: str
    latest: ImageInfo


def newer(latest: ImageInfo | None, running: ImageInfo | None, version: str) -> bool:
    """A different release than this server is out. By version, since the
    helper notes what runs only at its checks (every few hours): a server
    rebuilt in Container Manager meanwhile already runs the newest image,
    though the helper still has the old one down."""
    if latest is None:
        return False
    if latest.version:
        return latest.version != version
    return running is not None and latest.id != running.id


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
        self.registry_file = folder / "registry.json"

    def status(self) -> UpdaterStatus | None:
        try:
            return UpdaterStatus.model_validate_json(self.status_file.read_text())
        except (OSError, ValidationError):
            return None

    def save_status(self, status: UpdaterStatus) -> None:
        _write(self.status_file, status.model_dump_json(indent=2))

    def registry(self) -> RegistryCheck | None:
        try:
            return RegistryCheck.model_validate_json(self.registry_file.read_text())
        except (OSError, ValidationError):
            return None

    def save_registry(self, check: RegistryCheck) -> None:
        _write(self.registry_file, check.model_dump_json(indent=2))

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
        latest, checked_at = status.latest, status.checked_at
        state, error = status.state, status.error
        # Whichever looked last: the helper's pull or the server's question.
        seen = self.registry()
        if seen is not None and (
            checked_at is None
            or datetime.fromisoformat(seen.checked_at) >= datetime.fromisoformat(checked_at)
        ):
            latest, checked_at = seen.latest, seen.checked_at
            if state == "failed":  # an older failure; last_update keeps its story
                state, error = "idle", None
        version = build_version()
        return ServerUpdateView(
            version=version,
            updater=True,
            state=state,
            update_available=newer(latest, status.running, version),
            latest_version=latest.version if latest else None,
            latest_revision=latest.revision if latest else None,
            updating_from=(
                status.running.version if state == "updating" and status.running else None
            ),
            checked_at=checked_at,
            error=error,
            last_update=status.last_update,
            pending=self.pending(),
        )
