"""A change cut off by the phone going away runs once; asked again, it gets
the first answer (web/replays.py)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.web.app import create_app
from frame_server.web.replays import KEEP_FOR, Replays


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _app(clock: _Clock | None = None) -> tuple[Replays, dict[str, Any]]:
    seen: dict[str, Any] = {"runs": 0, "gate": None, "fail": False}
    inner = FastAPI()

    @inner.post("/api/change")
    async def change() -> dict[str, int]:
        seen["runs"] += 1
        if seen["gate"] is not None:
            await seen["gate"].wait()
        if seen["fail"]:
            seen["fail"] = False
            raise RuntimeError("the first try came to nothing")
        return {"run": seen["runs"]}

    @inner.post("/api/refused")
    async def refused() -> None:
        seen["runs"] += 1
        raise HTTPException(409, "Teraz się nie da")

    @inner.get("/api/read")
    async def read() -> dict[str, int]:
        seen["runs"] += 1
        return {"run": seen["runs"]}

    return Replays(inner, clock=clock or _Clock()), seen


def _client(app: Replays) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://frame")


def _key(key: str, token: str = "secret") -> dict[str, str]:
    return {"Idempotency-Key": key, "Authorization": f"Bearer {token}"}


async def test_the_same_change_again_gets_the_first_answer() -> None:
    app, seen = _app()
    async with _client(app) as client:
        first = await client.post("/api/change", headers=_key("a"))
        again = await client.post("/api/change", headers=_key("a"))
        other = await client.post("/api/change", headers=_key("b"))
    assert first.json() == again.json() == {"run": 1}
    assert seen["runs"] == 2 and other.json() == {"run": 2}
    assert first.headers["frame-replays"] == "1" and "frame-replayed" not in first.headers
    assert again.headers["frame-replayed"] == "1"


async def test_a_refusal_is_kept_too() -> None:
    app, seen = _app()
    async with _client(app) as client:
        first = await client.post("/api/refused", headers=_key("a"))
        again = await client.post("/api/refused", headers=_key("a"))
    assert first.status_code == again.status_code == 409
    assert again.json() == first.json() and seen["runs"] == 1


async def test_without_a_key_or_by_someone_else_it_runs_anew() -> None:
    app, seen = _app()
    async with _client(app) as client:
        await client.post("/api/change", headers={"Authorization": "Bearer secret"})
        await client.post("/api/change", headers={"Authorization": "Bearer secret"})
        await client.post("/api/change", headers=_key("a"))
        await client.post("/api/change", headers=_key("a", token="someone-else"))
    assert seen["runs"] == 4


async def test_reads_are_marked_and_never_kept() -> None:
    app, _ = _app()
    async with _client(app) as client:
        first = await client.get("/api/read", headers=_key("a"))
        again = await client.get("/api/read", headers=_key("a"))
    assert first.headers["frame-replays"] == "1"
    assert (first.json(), again.json()) == ({"run": 1}, {"run": 2})


async def test_asked_again_while_it_runs_waits_for_the_same_answer() -> None:
    app, seen = _app()
    seen["gate"] = asyncio.Event()
    async with _client(app) as client:
        first = asyncio.create_task(client.post("/api/change", headers=_key("a")))
        await asyncio.sleep(0.05)
        again = asyncio.create_task(client.post("/api/change", headers=_key("a")))
        await asyncio.sleep(0.05)
        assert seen["runs"] == 1 and not again.done()
        seen["gate"].set()
        answers = await asyncio.gather(first, again)
    assert [a.json() for a in answers] == [{"run": 1}, {"run": 1}] and seen["runs"] == 1


async def test_a_first_try_that_came_to_nothing_runs_again() -> None:
    app, seen = _app()
    seen["fail"] = True
    async with _client(app) as client:
        with pytest.raises(RuntimeError):
            await client.post("/api/change", headers=_key("a"))
        again = await client.post("/api/change", headers=_key("a"))
    assert again.json() == {"run": 2} and "frame-replayed" not in again.headers


async def test_the_work_ends_though_the_phone_went_away() -> None:
    """The phone froze mid-answer: sending fails and the client says it left,
    yet the change finishes and its answer waits for the app's return."""
    app, seen = _app()
    seen["gate"] = asyncio.Event()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/change",
        "raw_path": b"/api/change",
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "server": ("frame", 80),
        "client": ("phone", 1234),
        "http_version": "1.1",
        "headers": [
            (b"idempotency-key", b"a"),
            (b"authorization", b"Bearer secret"),
            (b"host", b"frame"),
        ],
    }
    sent_body = False

    async def receive() -> dict[str, Any]:
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}  # the phone is gone

    async def send(message: dict[str, Any]) -> None:
        raise OSError("the phone is gone")

    first = asyncio.create_task(app(scope, receive, send))
    await asyncio.sleep(0.05)
    seen["gate"].set()
    await first
    async with _client(app) as client:
        again = await client.post("/api/change", headers=_key("a"))
    assert again.json() == {"run": 1} and seen["runs"] == 1


async def test_old_answers_are_forgotten() -> None:
    clock = _Clock()
    app, _ = _app(clock)
    async with _client(app) as client:
        await client.post("/api/change", headers=_key("a"))
        clock.now += KEEP_FOR + 1
        again = await client.post("/api/change", headers=_key("a"))
    assert again.json() == {"run": 2}


def test_the_server_makes_a_playlist_once(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        api_token="secret",
    )
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = "Bearer secret"
        before = len(client.get("/api/playlists").json())
        body = {"name": "Na później", "kind": "manual", "item_ids": []}
        first = client.post("/api/playlists", json=body, headers={"Idempotency-Key": "k1"})
        again = client.post("/api/playlists", json=body, headers={"Idempotency-Key": "k1"})
        assert first.status_code == 200, first.text
        assert again.json()["playlist"]["id"] == first.json()["playlist"]["id"]
        assert len(client.get("/api/playlists").json()) == before + 1
        assert client.get("/api/health").headers["frame-replays"] == "1"
