"""`frame updater`: the helper that updates the server container on Synology.

It runs as a second container of the same image, with the Docker socket and
no network (the Docker daemon itself pulls from the registry). It acts only
on the container it was told about (``frame``): pulls the image that
container was created from, and when there is a newer one, recreates the
container with the same settings. A new container that does not stay up is
removed and the previous one started again.

The server asks for it through data/update/ (updates.py); nothing else can.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .updates import HEARTBEAT, ImageInfo, LastUpdate, UpdateFolder, UpdaterStatus

log = logging.getLogger(__name__)

SOCKET = "/var/run/docker.sock"
# Docker 20.10 (DSM 7.1) speaks 1.41; newer engines accept it too.
API = "v1.41"
CHECK_EVERY = timedelta(hours=6)
# A new container still running this long after its start counts as up.
SETTLE_S = 20.0

Json = dict[str, Any]


class DockerError(RuntimeError):
    pass


def split_ref(ref: str) -> tuple[str, str]:
    """``repo[:tag]`` → (repo, tag); a digest pins the image for good."""
    if "@" in ref:
        raise DockerError(f"obraz {ref} jest przypięty do skrótu, nie ma czego aktualizować")
    name, sep, tag = ref.rpartition(":")
    if sep and "/" not in tag:
        return name, tag
    return ref, "latest"


class Docker:
    """The few Engine API calls the helper needs, over the unix socket."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    @classmethod
    def connect(cls, socket: str = SOCKET) -> Docker:
        transport = httpx.HTTPTransport(uds=socket)
        timeout = httpx.Timeout(60.0, read=120.0)
        client = httpx.Client(transport=transport, base_url=f"http://docker/{API}", timeout=timeout)
        return cls(client)

    def _call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Json | None = None,
        missing_ok: bool = False,
    ) -> httpx.Response | None:
        response = self.client.request(method, path, params=params, json=body)
        if missing_ok and response.status_code == 404:
            return None
        if response.status_code >= 400:
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            raise DockerError(f"{method} {path}: {response.status_code} {message}".strip())
        return response

    def container(self, name: str) -> Json | None:
        response = self._call("GET", f"/containers/{name}/json", missing_ok=True)
        return response.json() if response else None

    def image(self, ref: str) -> Json | None:
        response = self._call("GET", f"/images/{ref}/json", missing_ok=True)
        return response.json() if response else None

    def pull(self, ref: str) -> None:
        repo, tag = split_ref(ref)
        params = {"fromImage": repo, "tag": tag}
        # Progress streams for as long as the layers download.
        timeout = httpx.Timeout(60.0, read=None)
        stream = self.client.stream("POST", "/images/create", params=params, timeout=timeout)
        with stream as response:
            if response.status_code >= 400:
                response.read()
                raise DockerError(f"pull {ref}: {response.status_code} {response.text}")
            for line in response.iter_lines():
                if line.strip() and "error" in (message := json.loads(line)):
                    raise DockerError(f"pull {ref}: {message['error']}")

    def stop(self, id: str, timeout: int = 30) -> None:
        self._call("POST", f"/containers/{id}/stop", params={"t": timeout})

    def start(self, id: str) -> None:
        self._call("POST", f"/containers/{id}/start")

    def rename(self, id: str, name: str) -> None:
        self._call("POST", f"/containers/{id}/rename", params={"name": name})

    def create(self, name: str, body: Json) -> str:
        response = self._call("POST", "/containers/create", params={"name": name}, body=body)
        assert response is not None
        return str(response.json()["Id"])

    def connect_network(self, network: str, id: str, endpoint: Json) -> None:
        body = {"Container": id, "EndpointConfig": endpoint}
        self._call("POST", f"/networks/{network}/connect", body=body)

    def remove(self, id: str) -> None:
        self._call("DELETE", f"/containers/{id}", params={"force": "true"}, missing_ok=True)

    def remove_image(self, id: str) -> None:
        try:
            self._call("DELETE", f"/images/{id}", missing_ok=True)
        except DockerError as exc:  # still used by another container: keep it
            log.info("old image kept: %s", exc)


def describe(image: Json) -> ImageInfo:
    labels = (image.get("Config") or {}).get("Labels") or {}
    return ImageInfo(
        id=image["Id"],
        version=labels.get("org.opencontainers.image.version") or None,
        revision=labels.get("org.opencontainers.image.revision") or None,
        created=image.get("Created"),
    )


# Settings a container takes from its image unless given its own: keeping the
# old image's values would hide the new image's (its CMD, its ENV, ...).
_FROM_IMAGE = (
    "Cmd",
    "Entrypoint",
    "WorkingDir",
    "User",
    "Healthcheck",
    "ExposedPorts",
    "Volumes",
    "StopSignal",
    "Shell",
    "OnBuild",
)


def create_body(old: Json, old_image: Json, ref: str) -> tuple[Json, list[tuple[str, Json]]]:
    """What `docker create` needs for a copy of ``old`` on the image ``ref``,
    and the networks to connect it to after creating it."""
    config: Json = dict(old.get("Config") or {})
    image_config: Json = old_image.get("Config") or {}
    config["Image"] = ref
    image_env = set(image_config.get("Env") or [])
    config["Env"] = [e for e in config.get("Env") or [] if e not in image_env]
    image_labels = image_config.get("Labels") or {}
    config["Labels"] = {
        k: v for k, v in (config.get("Labels") or {}).items() if image_labels.get(k) != v
    }
    for key in _FROM_IMAGE:
        if key in config and config[key] == image_config.get(key):
            del config[key]
    host_config: Json = old.get("HostConfig") or {}
    mode = str(host_config.get("NetworkMode") or "")
    short_id = str(old.get("Id", ""))[:12]
    if (
        mode in ("host", "none")
        or mode.startswith("container:")
        or (config.get("Hostname") == short_id)
    ):
        config.pop("Hostname", None)
        config.pop("Domainname", None)
    config.pop("MacAddress", None)
    body: Json = config | {"HostConfig": host_config}

    extra: list[tuple[str, Json]] = []
    networks: Json = (old.get("NetworkSettings") or {}).get("Networks") or {}
    if mode not in ("host", "none") and not mode.startswith("container:") and networks:
        endpoints = []
        for name, endpoint in networks.items():
            aliases = [a for a in endpoint.get("Aliases") or [] if a != short_id]
            endpoints.append(
                (
                    name,
                    {
                        "IPAMConfig": endpoint.get("IPAMConfig"),
                        "Links": endpoint.get("Links"),
                        "Aliases": aliases or None,
                    },
                )
            )
        first, *extra = endpoints
        body["NetworkingConfig"] = {"EndpointsConfig": {first[0]: first[1]}}
    return body, extra


def recreate(
    docker: Docker,
    name: str,
    ref: str,
    *,
    settle_s: float = SETTLE_S,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Replace container ``name`` by a copy on the image ``ref``; the old one
    comes back when the new one does not stay up. Returns the new id."""
    old = docker.container(name)
    if old is None:
        raise DockerError(f"nie ma kontenera {name}")
    old_image = docker.image(old["Image"]) or {}
    body, extra = create_body(old, old_image, ref)
    was_running = bool((old.get("State") or {}).get("Running"))
    backup = f"{name}-previous"
    if (leftover := docker.container(backup)) is not None:
        docker.remove(leftover["Id"])

    docker.stop(old["Id"])
    docker.rename(old["Id"], backup)
    new_id: str | None = None
    try:
        new_id = docker.create(name, body)
        for network, endpoint in extra:
            docker.connect_network(network, new_id, endpoint)
        docker.start(new_id)
        sleep(settle_s)
        new = docker.container(new_id) or {}
        state = new.get("State") or {}
        if not state.get("Running") or state.get("Restarting") or new.get("RestartCount"):
            reason = state.get("Error") or f"kod wyjścia {state.get('ExitCode')}"
            raise DockerError(f"nowy kontener nie działa ({reason})")
    except Exception:
        log.exception("recreating %s failed, starting the previous container again", name)
        if new_id is not None:
            docker.remove(new_id)
        docker.rename(old["Id"], name)
        if was_running:
            docker.start(old["Id"])
        raise
    docker.remove(old["Id"])
    new_image = (docker.container(new_id) or {}).get("Image")
    if new_image and new_image != old["Image"]:
        docker.remove_image(old["Image"])
    return new_id


def _stamp(now: datetime) -> str:
    return now.isoformat(timespec="seconds")


class Updater:
    def __init__(
        self,
        docker: Docker,
        folder: Path,
        *,
        container: str = "frame",
        me: str | None = None,
        check_every: timedelta = CHECK_EVERY,
        settle_s: float = SETTLE_S,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.docker = docker
        self.folder = UpdateFolder(folder)
        self.name = container
        # This helper's own container (its hostname is the container id).
        self.me = me
        self.check_every = check_every
        self.settle_s = settle_s
        self.clock = clock
        self.sleep = sleep
        status = self.folder.status() or UpdaterStatus()
        status.container = container
        if status.state in ("checking", "updating"):  # stopped half-way
            status.state = "idle"
        self.status = status

    def _save(self, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(self.status, key, value)
        self.status.alive_at = _stamp(self.clock())
        self.folder.save_status(self.status)

    def _due(self, now: datetime) -> bool:
        checked = self.status.checked_at
        return checked is None or datetime.fromisoformat(checked) <= now - self.check_every

    def tick(self) -> None:
        now = self.clock()
        action = self.folder.take_request()
        if action == "update":
            self.update()
        elif action == "check" or self._due(now):
            self.check()
        alive = self.status.alive_at
        if alive is None or datetime.fromisoformat(alive) <= now - HEARTBEAT:
            self._save()

    def run(self, poll_s: float = 5.0) -> None:
        log.info("updater: watching container %s, requests in %s", self.name, self.folder.folder)
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("updater tick failed")
            self.sleep(poll_s)

    def _target(self) -> tuple[Json, str]:
        container = self.docker.container(self.name)
        if container is None:
            raise DockerError(f"nie ma kontenera {self.name}")
        return container, str(container["Config"]["Image"])

    def check(self) -> bool:
        """Pull the image and compare it with the running one."""
        self._save(state="checking", error=None)
        try:
            container, ref = self._target()
            self.docker.pull(ref)
            latest = self.docker.image(ref)
            running = self.docker.image(container["Image"])
            if latest is None:
                raise DockerError(f"po pobraniu nie ma obrazu {ref}")
        except Exception as exc:
            log.warning("update check failed: %s", exc)
            self._save(state="failed", error=str(exc), checked_at=_stamp(self.clock()))
            return False
        self._save(
            state="idle",
            image=ref,
            running=describe(running) if running else ImageInfo(id=container["Image"]),
            latest=describe(latest),
            checked_at=_stamp(self.clock()),
        )
        log.info(
            "update check: running %s, latest %s",
            self.status.running and self.status.running.version,
            self.status.latest and self.status.latest.version,
        )
        return self.status.update_available

    def update(self) -> None:
        if not self.check():
            if self.status.state != "failed":
                log.info("update requested, already on the latest image")
            return
        before, after = self.status.running, self.status.latest
        assert before is not None and after is not None and self.status.image
        self._save(state="updating")
        log.info("updating %s: %s -> %s", self.name, before.version, after.version)
        try:
            recreate(
                self.docker, self.name, self.status.image, settle_s=self.settle_s, sleep=self.sleep
            )
        except Exception as exc:
            error = f"Nie udało się, działa poprzednia wersja: {exc}"
            self._save(
                state="failed",
                error=error,
                last_update=LastUpdate(
                    at=_stamp(self.clock()),
                    from_version=before.version,
                    to_version=after.version,
                    ok=False,
                    error=str(exc),
                ),
            )
            return
        self._save(
            state="idle",
            running=after,
            last_update=LastUpdate(
                at=_stamp(self.clock()),
                from_version=before.version,
                to_version=after.version,
                ok=True,
            ),
        )
        self.update_self()

    def update_self(self) -> None:
        """A container cannot recreate itself: when this helper's image is
        out of date, a short-lived one from the new image does it."""
        if not self.me:
            return
        try:
            me = self.docker.container(self.me)
            if me is None:
                return
            ref = str(me["Config"]["Image"])
            if ref != self.status.image:
                self.docker.pull(ref)
            latest = self.docker.image(ref)
            if latest is None or latest["Id"] == me["Image"]:
                return
            name = str(me["Name"]).lstrip("/")
            socket = next(
                (m["Source"] for m in me.get("Mounts") or [] if m.get("Destination") == SOCKET),
                SOCKET,
            )
            body: Json = {
                "Image": ref,
                "Cmd": ["frame", "updater", "--replace", name],
                "HostConfig": {
                    "Binds": [f"{socket}:{SOCKET}"],
                    "NetworkMode": "none",
                    "AutoRemove": True,
                },
            }
            helper = f"{name}-replace"
            if (leftover := self.docker.container(helper)) is not None:
                self.docker.remove(leftover["Id"])
            self.docker.start(self.docker.create(helper, body))
            log.info("the updater itself is replaced by %s", helper)
        except Exception:
            log.exception("could not update the updater itself")


def replace(docker: Docker, name: str, sleep: Callable[[float], None] = time.sleep) -> None:
    """`frame updater --replace NAME`, run by update_self()."""
    sleep(2.0)  # let the old helper finish saving
    container = docker.container(name)
    if container is None:
        raise DockerError(f"nie ma kontenera {name}")
    recreate(docker, name, str(container["Config"]["Image"]), settle_s=10.0, sleep=sleep)


def run(folder: Path, container: str, socket: str = SOCKET) -> None:
    docker = Docker.connect(socket)
    Updater(docker, folder, container=container, me=os.environ.get("HOSTNAME")).run()
