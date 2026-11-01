"""The server's recent log over the API, for a look from outside the NAS."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from frame_server import logbuffer
from frame_server.config import Settings
from frame_server.web import create_app

OWNER = {"Authorization": "Bearer secret"}


def test_the_owner_reads_the_recent_log(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, seed_library=False, scheduler=False, api_token="secret")
    with TestClient(create_app(settings)) as client:
        log = logging.getLogger("frame_server.test")
        log.warning("the frame's app did not ask after a wake")
        log.warning("something else")
        logging.getLogger("uvicorn.error").error("Exception in ASGI application")
        assert client.get("/api/debug/log").status_code == 401
        text = client.get("/api/debug/log", headers=OWNER).text
        assert "WARNING frame_server.test: the frame's app did not ask after a wake" in text
        assert text.count("Exception in ASGI application") == 1
        found = client.get("/api/debug/log", params={"grep": "DID NOT ASK"}, headers=OWNER).text
        assert found.count("\n") == 1 and "did not ask" in found
        last = client.get("/api/debug/log", params={"lines": 1}, headers=OWNER).text
        assert last.strip().endswith("Exception in ASGI application")


def test_a_record_through_two_loggers_is_kept_once() -> None:
    buffer = logbuffer.LogBuffer(keep=3)
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "once", None, None)
    buffer.handle(record)
    buffer.handle(record)
    for n in range(4):
        buffer.handle(logging.LogRecord("x", logging.INFO, __file__, 1, f"r{n}", None, None))
    assert [line.rsplit(" ", 1)[-1] for line in buffer.lines(10)] == ["r1", "r2", "r3"]
    assert buffer.lines(0) == []
