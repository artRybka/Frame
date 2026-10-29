"""The library's size on disk and its limit set in the app."""

from __future__ import annotations

from pathlib import Path

from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.fsutil import dir_bytes
from frame_server.library import Item, ItemKind
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
    upload = service.importer.add_upload(jpeg_bytes((40, 40, 200)), kind=ItemKind.OWN)
    usage = service.storage.usage()
    thumbs = sum(service.images.thumb_path(i).stat().st_size for i in (item, upload))
    original = service.images.image_path(item).stat().st_size
    own = service.images.image_path(upload).stat().st_size
    assert usage.catalogue_bytes == thumbs
    assert usage.originals_bytes == original
    assert usage.own_bytes == own
    assert usage.database_bytes > 0
    assert usage.total_bytes == (
        usage.catalogue_bytes
        + usage.originals_bytes
        + usage.own_bytes
        + usage.panel_bytes
        + usage.database_bytes
    )
    assert usage.free_bytes is not None and usage.free_bytes > 0

    service.images.remove(item)
    assert service.storage.usage() == usage  # kept, the disk is slow
    service.player.trim_cache()  # nothing to trim: still kept
    assert service.storage.usage() == usage
    service.storage.forget()
    assert service.storage.usage().originals_bytes == 0


def test_app_limits_win_over_frame_env_and_survive_restart(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, catalogue_mb=1000, image_cache_mb=500))
    with TestClient(app) as client:
        view = client.get("/api/library/storage").json()
        assert view["catalogue_mb"] == view["catalogue_default_mb"] == 1000
        assert view["originals_mb"] == view["originals_default_mb"] == 500
        assert view["catalogue_from_app"] is view["originals_from_app"] is False
        assert set(view["usage"]) >= {"catalogue_bytes", "originals_bytes", "own_bytes"}

        saved = client.put("/api/library/storage", json={"originals_mb": 5000})
        assert saved.status_code == 200, saved.text
        assert saved.json()["originals_mb"] == 5000
        assert saved.json()["originals_from_app"] is True
        assert saved.json()["catalogue_from_app"] is False
        svc: FrameService = app.state.service
        assert (svc.settings.catalogue_mb, svc.settings.image_cache_mb) == (1000, 5000)

        assert client.put("/api/library/storage", json={"catalogue_mb": 10}).status_code == 422
        client.put("/api/library/storage", json={"catalogue_mb": 2000})

    app = create_app(_settings(tmp_path, catalogue_mb=1000, image_cache_mb=500))
    with TestClient(app) as client:
        view = client.get("/api/library/storage").json()
        assert (view["catalogue_mb"], view["originals_mb"]) == (2000, 5000)
        # The default again: back to frame.env.
        view = client.put("/api/library/storage", json={"originals_mb": 500}).json()
        assert view["originals_mb"] == 500 and view["originals_from_app"] is False
        reset = client.delete("/api/library/storage").json()
        assert reset["catalogue_mb"] == 1000 and reset["catalogue_from_app"] is False
        svc = app.state.service
        assert (svc.settings.catalogue_mb, svc.settings.image_cache_mb) == (1000, 500)


def test_a_lower_limit_trims_now(tmp_path: Path, monkeypatch) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        svc: FrameService = app.state.service
        trims: list[int] = []
        monkeypatch.setattr(svc.player, "trim_cache", lambda: trims.append(1) or 0)
        client.put("/api/library/storage", json={"catalogue_mb": 3000})
        assert trims == []
        client.put("/api/library/storage", json={"originals_mb": 600})
        assert trims == [1]
        client.put("/api/library/storage", json={"catalogue_mb": 600, "originals_mb": 5000})
        assert trims == [1, 1]
        client.put("/api/library/storage", json={"catalogue_mb": 1000})  # more room
        assert trims == [1, 1]
        client.delete("/api/library/storage")  # originals back to 3000 MB
        assert trims == [1, 1, 1]


def test_the_one_limit_of_old_becomes_two(service: FrameService) -> None:
    """Up to add-on 0.28 the app set one limit, split 2:1 with the old 500 MB
    default for originals; the catalogue keeps its part, the originals get
    the larger of theirs and the new default."""
    from frame_server.storage import OLD_KEY, StorageStore

    service.library.set_state(OLD_KEY, 3000)
    store = StorageStore(service.settings, service.library, service.images, service.store)
    assert (service.settings.catalogue_mb, service.settings.image_cache_mb) == (2000, 3000)
    assert store.view().catalogue_from_app and not store.view().originals_from_app
    assert service.library.get_state(OLD_KEY) is None

    settings = _settings(service.settings.data_dir)  # frame.env without either limit
    service.library.delete_state("catalogue_limit")
    service.library.set_state(OLD_KEY, 20000)
    StorageStore(settings, service.library, service.images, service.store)
    assert (settings.catalogue_mb, settings.image_cache_mb) == (13333, 6667)


def test_saving_one_limit_leaves_the_other(service: FrameService) -> None:
    service.storage.save(StorageUpdate(catalogue_mb=900))
    assert (service.settings.catalogue_mb, service.settings.image_cache_mb) == (900, 3000)
