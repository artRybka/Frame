"""The update check asked from the app: the server asks the registry itself
instead of waiting for the helper to pull the image."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from frame_server import registry
from frame_server.config import Settings
from frame_server.registry import Registry, RegistryError, docker_arch, parse_ref
from frame_server.updates import ImageInfo, RegistryCheck, UpdateFolder, UpdaterStatus
from frame_server.web import create_app

INDEX = "application/vnd.oci.image.index.v1+json"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"


class FakeGhcr:
    """ghcr.io as `docker pull` sees it: a token first, then the tag's index,
    the platform's manifest and its config blob."""

    def __init__(self, version: str = "1.56.0") -> None:
        self.version = version
        self.paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        if path == "/token":
            assert request.url.params["scope"] == "repository:artrybka/frame:pull"
            return httpx.Response(200, json={"token": "t0k"})
        if request.headers.get("authorization") != "Bearer t0k":
            challenge = (
                'Bearer realm="https://ghcr.io/token",service="ghcr.io",'
                'scope="repository:artrybka/frame:pull"'
            )
            return httpx.Response(401, headers={"www-authenticate": challenge})
        base = "/v2/artrybka/frame"
        if path == f"{base}/manifests/latest":
            assert INDEX in request.headers["accept"]

            def entry(digest: str, os: str, arch: str) -> dict[str, Any]:
                return {"digest": digest, "platform": {"os": os, "architecture": arch}}

            index: dict[str, Any] = {
                "mediaType": INDEX,
                "manifests": [
                    entry("sha256:m-amd", "linux", "amd64"),
                    entry("sha256:att", "unknown", "unknown"),  # attestation
                    entry("sha256:m-arm", "linux", "arm64"),
                ],
            }
            return httpx.Response(200, json=index)
        if path.startswith(f"{base}/manifests/sha256:m-"):
            arch = path.rsplit("-", 1)[1]
            body = {"mediaType": MANIFEST, "config": {"digest": f"sha256:cfg-{arch}"}}
            return httpx.Response(200, json=body)
        if path.startswith(f"{base}/blobs/sha256:cfg-"):
            labels = {
                "org.opencontainers.image.version": self.version,
                "org.opencontainers.image.revision": "abc123",
            }
            config = {"created": "2026-10-31T21:17:13Z", "config": {"Labels": labels}}
            return httpx.Response(200, content=json.dumps(config))
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def test_parse_ref() -> None:
    assert parse_ref("ghcr.io/artrybka/frame:latest") == ("ghcr.io", "artrybka/frame", "latest")
    assert parse_ref("ghcr.io/artrybka/frame") == ("ghcr.io", "artrybka/frame", "latest")
    assert parse_ref("localhost:5000/frame:1.2") == ("localhost:5000", "frame", "1.2")
    assert parse_ref("python:3.13") == ("registry-1.docker.io", "library/python", "3.13")
    with pytest.raises(RegistryError):
        parse_ref("ghcr.io/artrybka/frame@sha256:abc")
    assert docker_arch("x86_64") == "amd64" and docker_arch("aarch64") == "arm64"


def test_the_registry_tells_the_version_without_a_pull() -> None:
    ghcr = FakeGhcr()
    info = Registry(ghcr.client()).latest("ghcr.io/artrybka/frame:latest", arch="arm64")
    assert info == ImageInfo(
        id="sha256:cfg-arm", version="1.56.0", revision="abc123", created="2026-10-31T21:17:13Z"
    )
    # One token, then three small reads: no layer is downloaded.
    assert all("/blobs/" not in p or "cfg-" in p for p in ghcr.paths)
    assert ghcr.paths.count("/token") == 1


def test_an_architecture_the_tag_lacks() -> None:
    with pytest.raises(RegistryError, match="linux/riscv64"):
        Registry(FakeGhcr().client()).latest("ghcr.io/artrybka/frame", arch="riscv64")


# -- through the API ----------------------------------------------------------


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


def _helper(folder: UpdateFolder, checked: datetime, **changes: Any) -> None:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    status = UpdaterStatus(
        alive_at=stamp,
        image="ghcr.io/artrybka/frame:latest",
        running=ImageInfo(id="sha256:cfg-old", version="1.55.1"),
        latest=ImageInfo(id="sha256:cfg-old", version="1.55.1"),
        checked_at=checked.isoformat(timespec="seconds"),
    )
    folder.save_status(status.model_copy(update=changes))


def test_a_check_is_answered_at_once_from_the_registry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRAME_RELEASE", "1.55.1")
    ghcr = FakeGhcr("1.56.0")
    monkeypatch.setattr(registry, "latest_image", lambda ref: Registry(ghcr.client()).latest(ref))
    folder = UpdateFolder(tmp_path / "update")
    _helper(folder, datetime.now(UTC) - timedelta(hours=3))
    with _client(tmp_path) as client:
        assert client.get("/api/server/update").json()["update_available"] is False
        view = client.post("/api/server/update/check").json()
    # Nothing left for the helper: the app has its answer right away.
    assert view["pending"] is None and view["state"] == "idle"
    assert view["update_available"] is True and view["latest_version"] == "1.56.0"
    assert folder.pending() is None
    # The helper's next check is newer and wins again.
    _helper(folder, datetime.now(UTC) + timedelta(minutes=1))
    assert folder.view().latest_version == "1.55.1"


def test_the_registry_says_the_server_is_current(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRAME_RELEASE", "1.56.0")
    ghcr = FakeGhcr("1.56.0")
    monkeypatch.setattr(registry, "latest_image", lambda ref: Registry(ghcr.client()).latest(ref))
    folder = UpdateFolder(tmp_path / "update")
    # The helper's last pull failed hours ago; a good answer now replaces it.
    _helper(folder, datetime.now(UTC) - timedelta(hours=1), state="failed", error="timeout")
    with _client(tmp_path) as client:
        view = client.post("/api/server/update/check").json()
    assert view["state"] == "idle" and view["error"] is None
    assert view["update_available"] is False and view["latest_version"] == "1.56.0"


def test_while_updating_a_check_changes_nothing(tmp_path: Path, monkeypatch) -> None:
    def never(ref: str) -> ImageInfo:
        raise AssertionError("no registry while the helper works")

    monkeypatch.setattr(registry, "latest_image", never)
    folder = UpdateFolder(tmp_path / "update")
    _helper(folder, datetime.now(UTC), state="updating")
    with _client(tmp_path) as client:
        assert client.post("/api/server/update/check").json()["state"] == "updating"
    assert folder.registry() is None


def test_an_old_registry_answer_does_not_hide_the_helpers(tmp_path: Path) -> None:
    folder = UpdateFolder(tmp_path)
    then = datetime.now(UTC)
    folder.save_registry(
        RegistryCheck(
            checked_at=(then - timedelta(hours=1)).isoformat(timespec="seconds"),
            latest=ImageInfo(id="sha256:cfg-x", version="1.50.0"),
        )
    )
    _helper(folder, then, latest=ImageInfo(id="sha256:cfg-new", version="1.56.0"))
    assert folder.view().latest_version == "1.56.0"
