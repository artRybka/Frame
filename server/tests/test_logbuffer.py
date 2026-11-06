"""The server's recent log over the API, for a look from outside the NAS."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frame_server import logbuffer
from frame_server.config import Settings
from frame_server.web import create_app

OWNER = {"Authorization": "Bearer secret"}


@pytest.fixture(autouse=True)
def _own_buffer(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The process has one buffer: a test's app gets a new one, without what
    the tests before it logged. Threads other tests left behind can still log
    into it while it runs (2026-11-06: an import between the lines below),
    so what a test reads it picks out by its own logger or words."""
    monkeypatch.setattr(logbuffer, "_buffer", None)
    yield
    if (buffer := logbuffer._buffer) is not None:
        for logger in (logging.getLogger(), logging.getLogger("uvicorn.error")):
            logger.removeHandler(buffer)


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
        mine = {"lines": 1, "grep": "frame_server.test"}
        last = client.get("/api/debug/log", params=mine, headers=OWNER).text
        assert last.count("\n") == 1 and last.strip().endswith("something else")


def test_the_log_survives_uvicorns_logging_setup(tmp_path: Path) -> None:
    """uvicorn configures its loggers (``dictConfig``) after the app is made,
    which drops their handlers: the app attaches the buffer again as it
    starts, so failed requests still reach it."""
    import logging.config

    import uvicorn.config

    settings = Settings(data_dir=tmp_path, seed_library=False, scheduler=False, api_token="secret")
    app = create_app(settings)
    logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
    with TestClient(app) as client:
        logging.getLogger("uvicorn.error").error("Exception after uvicorn's setup")
        text = client.get("/api/debug/log", headers=OWNER).text
        assert text.count("Exception after uvicorn's setup") == 1


def test_a_record_through_two_loggers_is_kept_once() -> None:
    buffer = logbuffer.LogBuffer(keep=3)
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "once", None, None)
    buffer.handle(record)
    buffer.handle(record)
    for n in range(4):
        buffer.handle(logging.LogRecord("x", logging.INFO, __file__, 1, f"r{n}", None, None))
    assert [line.rsplit(" ", 1)[-1] for line in buffer.lines(10)] == ["r1", "r2", "r3"]
    assert buffer.lines(0) == []


def test_a_long_traceback_keeps_its_end() -> None:
    """A failed request's traceback is mostly Starlette's middleware frames;
    what failed is at its end (2026-11-04: cut off in the middle)."""
    buffer = logbuffer.LogBuffer()
    log = logging.getLogger("test.long")
    log.addHandler(buffer)
    try:
        try:
            raise ValueError("what failed")
        except ValueError:
            log.error("Exception in ASGI application\n%s", "  frame\n" * 2000, exc_info=True)
    finally:
        log.removeHandler(buffer)
    [text] = buffer.lines(1)
    assert "Exception in ASGI application" in text
    assert text.rstrip().endswith("ValueError: what failed")
    assert "characters left out" in text and len(text) < logbuffer.LONGEST + 100


def test_the_owner_reads_what_the_battery_estimate_learns_from(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, seed_library=False, scheduler=False, api_token="secret")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/debug/battery").status_code == 401
        data = client.get("/api/debug/battery", headers=OWNER).json()
        assert data["runs"] == [] and "wake_minutes" in data["activity"]
        assert len(data["fit"]["mean"]) == 5
