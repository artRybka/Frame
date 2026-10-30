"""The update helper against a fake Docker engine, and the server's side."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.updater import Docker, DockerError, Updater, create_body, recreate, split_ref
from frame_server.updates import UpdateFolder, UpdaterStatus
from frame_server.web import create_app

REF = "ghcr.io/artrybka/frame:latest"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def image(id: str, version: str) -> dict[str, Any]:
    return {
        "Id": id,
        "Created": "2026-10-29T20:00:00Z",
        "Config": {
            "Env": ["PATH=/usr/bin", f"FRAME_RELEASE={version}"],
            "Cmd": ["frame", "serve"],
            "WorkingDir": "/data",
            "Labels": {"org.opencontainers.image.version": version},
        },
    }


class FakeEngine:
    """Just enough of the Docker Engine API, keyed like the real one."""

    def __init__(self) -> None:
        self.images: dict[str, dict[str, Any]] = {"sha256:old": image("sha256:old", "0.35.0")}
        self.tags = {REF: "sha256:old"}
        self.registry = "sha256:old"  # what a pull of REF brings
        self.containers: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []
        self.created: list[dict[str, Any]] = []
        self.fail_start_of_new = False
        self.add("frame", "sha256:old", cmd=["frame", "serve"], env=["FRAME_API_TOKEN=t"])
        self.add("frame-updater", "sha256:old", cmd=["frame", "updater"], env=[])

    def add(self, name: str, image_id: str, cmd: list[str], env: list[str]) -> str:
        id = self.new_id(name)
        img = self.images[image_id]["Config"]
        self.containers[id] = {
            "Id": id,
            "Name": f"/{name}",
            "Image": image_id,
            "State": {"Running": True},
            "RestartCount": 0,
            "Config": {
                "Image": REF,
                "Hostname": "nas",
                "Env": img["Env"] + env,
                "Cmd": cmd,
                "WorkingDir": "/data",
                "Labels": img["Labels"] | {"com.docker.compose.project": "frame"},
            },
            "HostConfig": {"NetworkMode": "host", "Binds": ["/volume1/docker/frame/data:/data"]},
            "NetworkSettings": {"Networks": {"host": {}}},
            "Mounts": [],
        }
        return id

    def new_id(self, name: str) -> str:
        return hashlib.sha256(f"{name}{len(self.calls)}{len(self.containers)}".encode()).hexdigest()

    def find(self, key: str) -> dict[str, Any] | None:
        for c in self.containers.values():
            if c["Name"] == f"/{key}" or (len(key) >= 12 and c["Id"].startswith(key)):
                return c
        return None

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1.41")
        method = request.method
        self.calls.append(f"{method} {path}")
        parts = path.strip("/").split("/")
        if parts[0] == "images" and method == "POST":  # pull
            assert request.url.params["fromImage"] == "ghcr.io/artrybka/frame"
            assert request.url.params["tag"] == "latest"
            if self.registry not in self.images:
                self.images[self.registry] = image(self.registry, "0.36.0")
            self.tags[REF] = self.registry
            return httpx.Response(200, text='{"status":"Pulling"}\n{"status":"Done"}\n')
        if parts[0] == "images" and method == "GET":
            ref = "/".join(parts[1:-1])
            found = self.images.get(self.tags.get(ref, ref))
            return httpx.Response(200, json=found) if found else httpx.Response(404, json={})
        if parts[0] == "images" and method == "DELETE":
            ref = "/".join(parts[1:])
            if any(c["Image"] == ref for c in self.containers.values()):
                return httpx.Response(409, json={"message": "image is being used"})
            self.images.pop(ref, None)
            return httpx.Response(200, json=[])
        if path == "/containers/create":
            body = json.loads(request.content)
            self.created.append(body)
            name = request.url.params["name"]
            id = self.new_id(name)
            config = {k: v for k, v in body.items() if k not in ("HostConfig", "NetworkingConfig")}
            self.containers[id] = {
                "Id": id,
                "Name": f"/{name}",
                "Image": self.tags[body["Image"]],
                "State": {"Running": False},
                "RestartCount": 0,
                "Config": config,
                "HostConfig": body["HostConfig"],
                "NetworkSettings": {"Networks": {}},
                "Mounts": [],
            }
            return httpx.Response(201, json={"Id": id})
        if parts[0] == "networks":
            return httpx.Response(200)
        container = self.find(parts[1])
        if container is None:
            return httpx.Response(404, json={"message": "no such container"})
        action = parts[2] if len(parts) > 2 else ""
        if method == "GET":
            return httpx.Response(200, json=container)
        if method == "DELETE":
            del self.containers[container["Id"]]
            return httpx.Response(204)
        if action == "stop":
            container["State"] = {"Running": False}
        elif action == "start":
            new = container["Image"] != "sha256:old"
            if new and self.fail_start_of_new:
                container["State"] = {"Running": False, "ExitCode": 1}
            else:
                container["State"] = {"Running": True}
        elif action == "rename":
            container["Name"] = "/" + request.url.params["name"]
        return httpx.Response(204)

    def docker(self) -> Docker:
        transport = httpx.MockTransport(self.handler)
        return Docker(httpx.Client(transport=transport, base_url="http://docker/v1.41"))

    def named(self, name: str) -> dict[str, Any]:
        found = self.find(name)
        assert found is not None
        return found


def updater(engine: FakeEngine, folder: Path, **kwargs: Any) -> Updater:
    return Updater(
        engine.docker(), folder, clock=lambda: NOW, sleep=lambda s: None, settle_s=0, **kwargs
    )


def test_split_ref() -> None:
    assert split_ref(REF) == ("ghcr.io/artrybka/frame", "latest")
    assert split_ref("ghcr.io/artrybka/frame") == ("ghcr.io/artrybka/frame", "latest")
    assert split_ref("localhost:5000/frame") == ("localhost:5000/frame", "latest")
    with pytest.raises(DockerError):
        split_ref("ghcr.io/artrybka/frame@sha256:abc")


def test_the_copy_takes_the_new_images_defaults() -> None:
    engine = FakeEngine()
    old = engine.named("frame")
    body, extra = create_body(old, engine.images["sha256:old"], REF)
    # The old image's ENV, CMD and labels would hide the new image's.
    assert body["Env"] == ["FRAME_API_TOKEN=t"]
    assert "Cmd" not in body and "WorkingDir" not in body
    assert body["Labels"] == {"com.docker.compose.project": "frame"}
    assert "Hostname" not in body  # host network: the NAS's own name
    assert body["HostConfig"]["Binds"] == ["/volume1/docker/frame/data:/data"]
    assert "NetworkingConfig" not in body and extra == []


def test_check_finds_a_newer_image(tmp_path: Path) -> None:
    engine = FakeEngine()
    helper = updater(engine, tmp_path)
    helper.tick()  # never checked: checks at once
    assert not helper.status.update_available
    engine.registry = "sha256:new"
    UpdateFolder(tmp_path).request("check")
    helper.tick()
    status = UpdateFolder(tmp_path).status()
    assert status is not None and status.update_available
    assert status.running and status.running.version == "0.35.0"
    assert status.latest and status.latest.version == "0.36.0"
    assert status.state == "idle"


def test_update_recreates_the_server_and_then_the_helper(tmp_path: Path) -> None:
    engine = FakeEngine()
    engine.registry = "sha256:new"
    me = engine.named("frame-updater")["Id"][:12]
    helper = updater(engine, tmp_path, me=me)
    UpdateFolder(tmp_path).request("update")
    helper.tick()

    frame = engine.named("frame")
    assert frame["Image"] == "sha256:new" and frame["State"]["Running"]
    assert frame["Config"]["Env"] == ["FRAME_API_TOKEN=t"]
    assert engine.find("frame-previous") is None
    status = UpdateFolder(tmp_path).status()
    assert status and status.last_update and status.last_update.ok
    assert status.last_update.to_version == "0.36.0"
    assert not status.update_available
    # The helper still runs the old image: a short-lived container replaces it.
    replace = engine.named("frame-updater-replace")
    assert replace["Config"]["Cmd"] == ["frame", "updater", "--replace", "frame-updater"]
    assert replace["HostConfig"]["NetworkMode"] == "none"
    assert "sha256:old" in engine.images  # in use by the helper


def test_a_new_container_that_does_not_stay_up_is_rolled_back(tmp_path: Path) -> None:
    engine = FakeEngine()
    engine.registry = "sha256:new"
    engine.fail_start_of_new = True
    old_id = engine.named("frame")["Id"]
    helper = updater(engine, tmp_path)
    UpdateFolder(tmp_path).request("update")
    helper.tick()

    frame = engine.named("frame")
    assert frame["Id"] == old_id and frame["State"]["Running"]
    assert [c["Name"] for c in engine.containers.values()].count("/frame") == 1
    status = UpdateFolder(tmp_path).status()
    assert status and status.state == "failed"
    assert status.last_update and not status.last_update.ok
    assert status.error and "poprzednia wersja" in status.error


def test_nothing_newer_nothing_recreated(tmp_path: Path) -> None:
    engine = FakeEngine()
    helper = updater(engine, tmp_path)
    UpdateFolder(tmp_path).request("update")
    helper.tick()
    assert engine.created == []
    assert not any(call.endswith("/stop") for call in engine.calls)


def test_checks_again_after_hours_and_keeps_a_heartbeat(tmp_path: Path) -> None:
    engine = FakeEngine()
    now = [NOW]
    helper = Updater(engine.docker(), tmp_path, clock=lambda: now[0], sleep=lambda s: None)
    helper.tick()
    pulls = engine.calls.count("POST /images/create")
    now[0] += timedelta(minutes=6)
    helper.tick()
    assert engine.calls.count("POST /images/create") == pulls
    status = UpdateFolder(tmp_path).status()
    assert status and status.alive_at == now[0].isoformat(timespec="seconds")
    now[0] += timedelta(hours=6)
    helper.tick()
    assert engine.calls.count("POST /images/create") == pulls + 1


def test_recreate_keeps_networks_and_aliases() -> None:
    engine = FakeEngine()
    frame = engine.named("frame")
    frame["HostConfig"]["NetworkMode"] = "frame_default"
    frame["NetworkSettings"]["Networks"] = {
        "frame_default": {"Aliases": ["frame", frame["Id"][:12]], "IPAMConfig": None},
        "other": {"Aliases": None},
    }
    engine.registry = "sha256:new"
    docker = engine.docker()
    docker.pull(REF)
    recreate(docker, "frame", REF, settle_s=0, sleep=lambda s: None)
    body = engine.created[-1]
    endpoint = body["NetworkingConfig"]["EndpointsConfig"]["frame_default"]
    assert endpoint["Aliases"] == ["frame"]
    assert "POST /networks/other/connect" in engine.calls


# -- the server's side --------------------------------------------------------


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        api_token="secret",
    )
    client = TestClient(create_app(settings))
    client.headers["Authorization"] = "Bearer secret"
    return client


def test_without_the_helper_the_app_is_told_so(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRAME_RELEASE", "0.36.0")
    with _client(tmp_path) as client:
        view = client.get("/api/server/update").json()
        assert view["updater"] is False and view["version"] == "0.36.0"
        assert client.post("/api/server/update").status_code == 409
        assert client.get("/api/health").json()["version"] == "0.36.0"


def test_the_app_asks_the_helper(tmp_path: Path) -> None:
    folder = UpdateFolder(tmp_path / "update")
    engine = FakeEngine()
    engine.registry = "sha256:new"
    now = datetime.now(UTC)
    helper = Updater(engine.docker(), folder.folder, clock=lambda: now, sleep=lambda s: None)
    helper.tick()
    with _client(tmp_path) as client:
        view = client.get("/api/server/update").json()
        assert view["updater"] is True and view["update_available"] is True
        assert view["latest_version"] == "0.36.0"
        assert client.post("/api/server/update/check").json()["pending"] == "check"
        assert client.post("/api/server/update").json()["pending"] == "update"
        assert folder.pending() == "update"
        # A check asked after the update does not replace it.
        assert client.post("/api/server/update/check").json()["pending"] == "update"


def test_a_silent_helper_counts_as_gone(tmp_path: Path) -> None:
    folder = UpdateFolder(tmp_path)
    stale = (NOW - timedelta(minutes=20)).isoformat(timespec="seconds")
    folder.save_status(UpdaterStatus(alive_at=stale))
    assert not folder.helper_alive(NOW)
    assert folder.helper_alive(NOW - timedelta(minutes=10))
