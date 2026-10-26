"""The library's size on disk and its limit set in the app."""

from __future__ import annotations

from pathlib import Path

from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.fsutil import dir_bytes
from frame_server.library import Item
from frame_server.service import FrameService
from frame_server.storage import StorageUpdate
from frame_server.web import create_app


def _settings(tmp_path: Path, **kw: object) -> Settings:
    return Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        **kw,  # type: ignore[arg-type]
    )


def test_dir_bytes_skips_nas_entries(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"x" * 100)
    (tmp_path / "b.jpg").write_bytes(b"x" * 20)
    (tmp_path / ".DS_Store").write_bytes(b"x" * 1000)
    (tmp_path / "@eaDir").mkdir()
    (tmp_path / "@eaDir" / "c.jpg").write_bytes(b"x" * 1000)
    assert dir_bytes(tmp_path) == 120
    assert dir_bytes(tmp_path / "missing") == 0


def test_usage_is_measured_once_in_a_while(service: FrameService) -> None:
    item = service.library.upsert(Item(id="aic:1", source="aic", source_id="1"))
    service.images.store(item, jpeg_bytes((200, 40, 40)))
    usage = service.storage.usage()
    thumb = service.images.thumb_path(item).stat().st_size
    original = service.images.image_path(item).stat().st_size
    assert usage.catalogue_bytes == thumb
    assert usage.originals_bytes == original
    assert usage.database_bytes > 0
    assert usage.total_bytes == (
        usage.catalogue_bytes + usage.originals_bytes + usage.panel_bytes + usage.database_bytes
    )
    assert usage.free_bytes is not None and usage.free_bytes > 0

    service.images.remove(item)
    assert service.storage.usage() == usage  # kept, the disk is slow
    service.player.trim_cache()  # nothing to trim: still kept
    assert service.storage.usage() == usage
    service.storage.forget()
    assert service.storage.usage().catalogue_bytes == 0


def test_app_limit_splits_like_frame_env_and_survives_restart(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, catalogue_mb=1000, image_cache_mb=500))
    with TestClient(app) as client:
        view = client.get("/api/library/storage").json()
        assert view["limit_mb"] == view["default_mb"] == 1500
        assert view["from_app"] is False
        assert set(view["usage"]) >= {"catalogue_bytes", "originals_bytes", "total_bytes"}

        saved = client.put("/api/library/storage", json={"limit_mb": 3000})
        assert saved.status_code == 200, saved.text
        assert saved.json()["limit_mb"] == 3000
        assert saved.json()["from_app"] is True
        svc: FrameService = app.state.service
        assert (svc.settings.catalogue_mb, svc.settings.image_cache_mb) == (2000, 1000)

        assert client.put("/api/library/storage", json={"limit_mb": 10}).status_code == 422

    app = create_app(_settings(tmp_path, catalogue_mb=1000, image_cache_mb=500))
    with TestClient(app) as client:
        assert client.get("/api/library/storage").json()["limit_mb"] == 3000
        reset = client.delete("/api/library/storage").json()
        assert reset["limit_mb"] == 1500 and reset["from_app"] is False
        svc = app.state.service
        assert (svc.settings.catalogue_mb, svc.settings.image_cache_mb) == (1000, 500)


def test_a_lower_limit_trims_now(tmp_path: Path, monkeypatch) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        svc: FrameService = app.state.service
        trims: list[int] = []
        monkeypatch.setattr(svc.player, "trim_cache", lambda: trims.append(1) or 0)
        client.put("/api/library/storage", json={"limit_mb": 3000})
        assert trims == []
        client.put("/api/library/storage", json={"limit_mb": 600})
        assert trims == [1]
        client.delete("/api/library/storage")  # back to 1500: more room
        assert trims == [1]


def test_split_when_frame_env_turns_the_catalogue_off(service: FrameService) -> None:
    service.settings.catalogue_mb, service.settings.image_cache_mb = 0, 0
    from frame_server.storage import StorageStore

    store = StorageStore(service.settings, service.library, service.images, service.store)
    store.save(StorageUpdate(limit_mb=900))
    assert (service.settings.catalogue_mb, service.settings.image_cache_mb) == (600, 300)
