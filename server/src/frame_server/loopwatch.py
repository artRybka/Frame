"""Notices when the server's event loop stands still, and says where.

Everything the frame and the app ask goes through one event loop: work done
on it (not in a thread) holds up every answer. After a start on 2026-11-04
the loop stood still for 104 s with nothing in the log, the frame's question
was answered that late and the server took its clock for 104 s off. Now a
thread looks at the loop every second; when it has not moved for
:data:`STALL_S`, the log gets the loop's stack (again every
:data:`STACK_EVERY` while it stays stuck), and how long it stood once it
moves on."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback

log = logging.getLogger(__name__)

#: The loop has stood still this long: worth a line with its stack.
STALL_S = 5.0
#: While it stays stuck, its stack again this often (where the time goes).
STACK_EVERY = 30.0
#: How often the loop says it is alive, and the watcher looks.
BEAT_S = 1.0


class LoopWatch:
    def __init__(
        self, stall: float = STALL_S, every: float = STACK_EVERY, beat: float = BEAT_S
    ) -> None:
        self.stall = stall
        self.every = every
        self.beat = beat
        self._beat_at = time.monotonic()
        self._ident: int | None = None
        self._stop = threading.Event()

    async def run(self) -> None:
        """The loop's side: a beat every :attr:`beat` seconds; a late one
        tells how long the loop stood still."""
        self._ident = threading.get_ident()
        self._beat_at = time.monotonic()
        threading.Thread(target=self._watch, name="loop-watch", daemon=True).start()
        try:
            while True:
                await asyncio.sleep(self.beat)
                now = time.monotonic()
                stood = now - self._beat_at - self.beat
                self._beat_at = now
                if stood >= self.stall:
                    log.warning("the event loop stood still for %.1f s", stood)
        finally:
            self._stop.set()

    def _watch(self) -> None:
        stuck_since: float | None = None  # the last beat before the stall told of
        told_at = 0.0
        while not self._stop.wait(self.beat):
            beat_at = self._beat_at
            stood = time.monotonic() - beat_at - self.beat
            if stood < self.stall:
                continue
            if beat_at == stuck_since and stood - told_at < self.every:
                continue
            stuck_since, told_at = beat_at, stood
            log.warning("the event loop has stood still for %.0f s, at:\n%s", stood, self.stack())

    def stack(self) -> str:
        """Where the loop's thread is now, innermost call last."""
        frame = sys._current_frames().get(self._ident) if self._ident is not None else None
        if frame is None:
            return "  (the loop's thread is gone)"
        return "".join(traceback.format_stack(frame)).rstrip()

    def stop(self) -> None:
        self._stop.set()
