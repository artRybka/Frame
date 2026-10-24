"""Server + fake panel: upload an image, the panel is told to fetch it and does."""

from __future__ import annotations

import asyncio
import io
import json
import socket
import ssl
from pathlib import Path

import httpx
import pytest
import trustme
import uvicorn
from fake_panel import FakePanel
from PIL import Image

from frame_server.config import Settings
from frame_server.device.mdc import CMD_CONTENT_DOWNLOAD
from frame_server.web import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server_ssl() -> ssl.SSLContext:
    ca = trustme.CA()
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ca.issue_cert("panel.local").configure_cert(ctx)
    return ctx


async def test_display_flow(tmp_path: Path, server_ssl: ssl.SSLContext) -> None:
    fetched: list[str] = []

    async def behave_like_panel(url: str) -> None:
        async with httpx.AsyncClient() as client:
            manifest = (await client.get(url)).json()
            fetched.append(url)
            item = manifest["schedule"][0]["contents"][0]
            image = await client.get(item["image_url"])
            assert image.status_code == 200
            assert len(image.content) == int(item["file_size"])
            fetched.append(item["image_url"])

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_CONTENT_DOWNLOAD:
            asyncio.get_running_loop().create_task(behave_like_panel(data[3:].decode()))
        return True, b""

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    settings = Settings(
        device_host="127.0.0.1",
        device_pin="123456",
        device_port=panel.port,
        public_host="127.0.0.1",
        port=_free_port(),
        data_dir=tmp_path,
        api_token="secret",
        seed_library=False,
        scheduler=False,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings), host="127.0.0.1", port=settings.port, log_level="warning"
        )
    )
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)

    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (200, 120, 60)).save(buf, "JPEG")
    try:
        async with httpx.AsyncClient(base_url=settings.base_url(), timeout=60) as client:
            unauth = await client.get("/api/now")
            assert unauth.status_code == 401
            headers = {"Authorization": "Bearer secret"}
            # A fresh install already serves a placeholder.
            assert (await client.get("/panel/content.json")).status_code == 200

            resp = await client.post(
                "/api/display",
                files={"file": ("test.jpg", buf.getvalue(), "image/jpeg")},
                data={"preset": "photo", "wait": "20"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["fetched"] is True
            assert body["content"]["file_name"].endswith(".jpg")  # photo preset: passthrough

            now = (await client.get("/api/now", headers=headers)).json()
            assert now["file_id"] == body["content"]["file_id"]
            preview = await client.get(now["preview_url"], headers=headers)
            assert preview.headers["content-type"] == "image/png"

            log = (await client.get("/api/debug/panel-requests", headers=headers)).json()
            assert [r["path"] for r in log][-2:] == [
                "/panel/content.json",
                f"/panel/images/{body['content']['file_name']}",
            ]
    finally:
        server.should_exit = True
        await serving
        await panel.stop()

    assert len(fetched) == 2
    raw_manifest = (tmp_path / "current.json").read_text()
    assert json.loads(raw_manifest)["title"] == "test.jpg"
