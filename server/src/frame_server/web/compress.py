"""The app's larger answers go out gzipped.

``/api/themes`` is 670 KB of JSON at every start of the app and Discover's
rows half a megabyte; gzipped they are a sixth of that (the audit of
2026-11-14), which is what the owner waits for away from home. Only what
the app reads whole: the answer to a GET under ``/api/`` that is text (JSON)
of :data:`GZIP_FROM` bytes or more and comes in one piece. Never the
panel's requests, pictures (compressed as they are), or the answers that
come line by line (each line is shown as it comes).

The app asks for it without being told to (``URLSession`` sends
``Accept-Encoding: gzip`` and unpacks by itself); one that does not ask
gets the answer as before.
"""

from __future__ import annotations

import gzip
from typing import Any

from anyio import CapacityLimiter, to_thread

#: Answers shorter than this go as they are (bytes).
GZIP_FROM = 10_000
#: 670 KB of themes: 119 KB in 8 ms; the best level saves 6% more for 22 ms.
GZIP_LEVEL = 5
#: Answers from this size are packed in a thread, not in the event loop.
IN_THREAD_FROM = 64 * 1024
#: The packing has threads of its own: it never waits behind the catalogue.
GZIP_THREADS = CapacityLimiter(4)

_TEXT = (b"application/json", b"text/plain", b"text/html", b"application/xml")


def _asks(scope: dict[str, Any]) -> bool:
    """A GET under ``/api/`` from someone who reads gzip."""
    if scope["type"] != "http" or scope.get("method") != "GET":
        return False
    if not scope.get("path", "").startswith("/api/"):
        return False
    for name, value in scope.get("headers") or ():
        if name == b"accept-encoding":
            for token in value.decode("latin-1").lower().split(","):
                coding, _, weight = token.partition(";")
                if coding.strip() == "gzip":
                    return weight.replace(" ", "") not in ("q=0", "q=0.0", "q=0.00", "q=0.000")
    return False


def _packs(head: dict[str, Any]) -> bool:
    """A whole answer (200) of text, not packed already."""
    if head.get("status") != 200:
        return False
    kind = b""
    for name, value in head.get("headers") or ():
        if name.lower() == b"content-encoding":
            return False
        if name.lower() == b"content-type":
            kind = value.split(b";")[0].strip().lower()
    return kind in _TEXT


def _pack(body: bytes) -> bytes:
    return gzip.compress(body, GZIP_LEVEL, mtime=0)


class Compressed:
    """ASGI middleware, to sit under the ones that pass an answer on piece
    by piece (``app.middleware("http")``): here an answer is still whole."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not _asks(scope):
            await self.app(scope, receive, send)
            return
        # The answer's head waits for its body: the length and the encoding
        # are known only then.
        head: dict[str, Any] | None = None

        async def packed(message: dict[str, Any]) -> None:
            nonlocal head
            if message["type"] == "http.response.start":
                head = message
                return
            held, head = head, None
            if held is None:  # the next pieces of an answer in pieces
                await send(message)
                return
            body = message.get("body", b"") if message["type"] == "http.response.body" else b""
            if message.get("more_body") or len(body) < GZIP_FROM or not _packs(held):
                await send(held)
                await send(message)
                return
            if len(body) >= IN_THREAD_FROM:
                small = await to_thread.run_sync(_pack, body, limiter=GZIP_THREADS)
            else:
                small = _pack(body)
            headers = [
                (name, value)
                for name, value in held["headers"]
                if name.lower() not in (b"content-length", b"vary")
            ]
            vary = [v for n, v in held["headers"] if n.lower() == b"vary"]
            headers += [
                (b"content-encoding", b"gzip"),
                (b"content-length", str(len(small)).encode()),
                (b"vary", b", ".join([*vary, b"Accept-Encoding"])),
            ]
            await send({**held, "headers": headers})
            await send({**message, "body": small})

        await self.app(scope, receive, packed)
