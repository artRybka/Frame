"""What the app's "Teraz" says about the panel: the picture it downloaded,
not just the one published last."""

from __future__ import annotations

import json
from pathlib import Path

from frame_server.config import Settings
from frame_server.service import FrameService
from frame_server.store import ContentStore, PanelRequest
from frame_server.web.player_api import _player_view


def _download(store: ContentStore, file_name: str, time: str = "2026-10-26T07:00:00") -> None:
    store.log_request(
        PanelRequest(
            time=time,
            client="198.51.100.20",
            method="GET",
            path=f"/panel/images/{file_name}",
            status=200,
            user_agent="",
            headers={},
        )
    )


def _service(tmp_path: Path) -> FrameService:
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        device_host="127.0.0.1",
        device_pin="123456",
    )
    service = FrameService(settings)
    service.app.store_package(b"PK\x03\x04signed", "2.0.0")  # the app can be started
    return service


def test_delivery_follows_the_panel_downloads(tmp_path: Path) -> None:
    service = _service(tmp_path)
    store = service.store
    first = store.publish(b"png", "png", title="Most w Argenteuil")
    assert _player_view(service).delivery.state == "unknown"  # never seen a download
    _download(store, first.file_name)
    assert _player_view(service).delivery.state == "shown"

    # The scheduled change: published, sent, never downloaded.
    second = store.publish(b"png", "png", title="Słoneczniki")
    store.note_failed(second.file_id, "timeout", "panel did not download the image in time")
    delivery = _player_view(service).delivery
    assert delivery.state == "failed"
    assert delivery.failure == "timeout"
    assert delivery.on_frame is not None
    assert delivery.on_frame.title == "Most w Argenteuil"

    # The panel did not answer: the picture waits for it to wake.
    service.power.mark_pending(True)
    delivery = _player_view(service).delivery
    assert delivery.state == "waiting"
    assert delivery.on_frame is not None

    # It woke and downloaded the picture on its own.
    service.power.mark_pending(False)
    _download(store, second.file_name, "2026-10-26T07:30:00")
    delivery = _player_view(service).delivery
    assert delivery.state == "shown"
    assert delivery.on_frame is None
    assert delivery.shown_at == "2026-10-26T07:30:00"
    assert store.delivery().failure is None

    # A stale image fetched later does not count: content.json points elsewhere.
    _download(store, first.file_name)
    assert store.on_panel() is True


def test_delivery_recovered_from_the_request_log(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    info = store.publish(b"png", "png", title="Wieża")
    log = tmp_path / "panel-requests.jsonl"
    lines = [
        {"time": "t0", "path": f"/panel/images/{info.file_name}", "status": 200},
        {"time": "t1", "path": "/panel/content.json", "status": 200},
    ]
    log.write_text("".join(json.dumps(line) + "\n" for line in lines))
    assert ContentStore(tmp_path).on_panel() is True

    # An older picture fetched last: not known what is on the panel.
    (tmp_path / "delivery.json").unlink()
    store.publish(b"png", "png", title="Nowy")
    assert ContentStore(tmp_path).on_panel() is None
