"""A change the app asked for is done once, however often it asks.

The phone freezes the app a moment after it goes to the background, and a
request still running then is cut off on the phone's side, though the
server may well have got it (Mateusz 2026-11-13: „Przerwane, gdy aplikacja
była w tle”). The app sends every change (POST, PUT, PATCH, DELETE) with an
``Idempotency-Key`` and, once it is back, sends the very same request again.
:class:`Replays` then answers what the first one answered: from memory when
it is done, after waiting for it while it still runs. A change never runs
twice and the app hears how it ended.

The first request is not cut off on the server's side either: once its
body has come, the work under it never hears that the phone went away, so
it is finished and kept for the second.

Every answer under ``/api/`` says ``Frame-Replays: 1``: an app that has not
seen it (an older server) does not send a change twice.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: The request header the app sends with every change.
KEY_HEADER = b"idempotency-key"
#: On every answer under /api/: this server keeps changes' answers.
MARK = (b"frame-replays", b"1")
#: On an answer given again from memory.
REPLAYED = (b"frame-replayed", b"1")

#: How long an answer is kept. The app asks again once it is back in front,
#: which may be hours later; then the change was long done and its answer
#: no longer waited for (the app reads the state anew when it comes back).
KEEP_FOR = 2 * 3600.0
#: At most so many answers are kept, the oldest go first.
MOST = 500
#: An answer longer than this is not kept: the request runs again.
LARGEST = 4 * 1024 * 1024

_READS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass
class _Answer:
    at: float
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    status: int = 0
    headers: list[tuple[bytes, bytes]] = field(default_factory=list)
    body: list[bytes] = field(default_factory=list)
    size: int = 0
    whole: bool = False  # the response ended, was no error and is small enough to keep

    async def replay(self, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [*self.headers, REPLAYED],
            }
        )
        await send({"type": "http.response.body", "body": b"".join(self.body), "more_body": False})


class Replays:
    """ASGI middleware: the answer to a change with an ``Idempotency-Key``
    is kept, and the same request again gets it instead of a second run."""

    def __init__(self, app: Any, clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self.clock = clock
        self._answers: dict[tuple[str, str, str, str], _Answer] = {}

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return
        marked = _marked(send)
        key = _header(scope, KEY_HEADER)
        if scope.get("method", "GET") in _READS or not key or len(key) > 200:
            await self.app(scope, receive, marked)
            return
        who = hashlib.sha256(_header(scope, b"authorization").encode()).hexdigest()
        ident = (scope["method"], scope["path"], who, key)
        while True:
            self._forget_old()
            earlier = self._answers.get(ident)
            if earlier is None:
                break
            await earlier.finished.wait()
            if earlier.whole:
                await earlier.replay(marked)
                return
            # The first one came to nothing (or was too long to keep): this
            # one runs, unless another retry started it meanwhile.
            if self._answers.get(ident) is earlier:
                del self._answers[ident]
        answer = _Answer(at=self.clock())
        self._answers[ident] = answer
        try:
            await self.app(scope, _shielded(receive, answer), _kept(marked, answer))
        except BaseException:
            answer.whole = False  # what ended in an error may be tried again
            if self._answers.get(ident) is answer:
                del self._answers[ident]
            raise
        finally:
            answer.finished.set()
        if not answer.whole and self._answers.get(ident) is answer:
            del self._answers[ident]

    def _forget_old(self) -> None:
        now = self.clock()
        old = [
            ident
            for ident, answer in self._answers.items()
            if answer.finished.is_set() and now - answer.at > KEEP_FOR
        ]
        for ident in old:
            del self._answers[ident]
        if len(self._answers) > MOST:
            done = sorted(
                (answer.at, ident)
                for ident, answer in self._answers.items()
                if answer.finished.is_set()
            )
            for _, ident in done[: len(self._answers) - MOST]:
                del self._answers[ident]


def _header(scope: dict[str, Any], name: bytes) -> str:
    for key, value in scope.get("headers", ()):
        if key.lower() == name:
            return bytes(value).decode("latin-1")
    return ""


def _marked(send: Any) -> Any:
    async def marked(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            message = {**message, "headers": [*message.get("headers", ()), MARK]}
        await send(message)

    return marked


def _kept(send: Any, answer: _Answer) -> Any:
    """Passes the response on and keeps a copy; the phone having gone away
    does not stop the work under it."""

    async def kept(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            answer.status = message["status"]
            answer.headers = [(bytes(k), bytes(v)) for k, v in message.get("headers", ())]
        elif message["type"] == "http.response.body":
            chunk = bytes(message.get("body", b""))
            answer.size += len(chunk)
            if answer.size <= LARGEST:
                answer.body.append(chunk)
            else:
                answer.body = []
            if not message.get("more_body", False):
                # A server error is not kept: asked again, it is tried again.
                answer.whole = answer.size <= LARGEST and 0 < answer.status < 500
                answer.finished.set()
        with contextlib.suppress(OSError):  # the phone went away: the answer waits for its return
            await send(message)

    return kept


def _shielded(receive: Any, answer: _Answer) -> Any:
    """``receive`` that never says the client left once the body has come,
    so nothing under it gives up on the work for that."""
    came = False

    async def shielded() -> dict[str, Any]:
        nonlocal came
        if came:
            await answer.finished.wait()
            return {"type": "http.disconnect"}
        message: dict[str, Any] = await receive()
        if message["type"] == "http.request" and not message.get("more_body", False):
            came = True
        return message

    return shielded
