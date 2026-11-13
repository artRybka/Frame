"""Notices when the server's event loop stands still, and says where.

Everything the frame and the app ask goes through one event loop: work done
on it (not in a thread) holds up every answer. After a start on 2026-11-04
the loop stood still for 104 s with nothing in the log, the frame's question
was answered that late and the server took its clock for 104 s off. Now a
thread looks at the loop every second; when it has not moved for
:data:`STALL_S`, the log gets the loop's stack (again every
:data:`STACK_EVERY` while it stays stuck), and how long it stood once it
moves on. With the loop's stack go the other threads at work: on 2026-11-09
the loop stood 78 s waiting for the library's lock, and the log could not
say which thread held it."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback
from collections.abc import Sequence

log = logging.getLogger(__name__)

#: The loop has stood still this long: worth a line with its stack.
STALL_S = 5.0
#: While it stays stuck, its stack again this often (where the time goes).
STACK_EVERY = 30.0
#: How often the loop says it is alive, and the watcher looks.
BEAT_S = 1.0
#: A thread whose innermost call is in one of these waits for work: not shown.
IDLE = ("/threading.py", "/queue.py", "/selectors.py", "/concurrent/futures/thread.py")
#: The innermost calls shown of each other thread, and at most this many threads.
THREAD_DEPTH = 10
#: The loop's own innermost calls shown: its outer ones (the command line,
#: uvicorn, asyncio) are always the same, and a long dump had its middle,
#: where the loop stood, cut out of the log (2026-11-09).
LOOP_DEPTH = 16
THREADS_SHOWN = 12


def compact(frames: Sequence[traceback.FrameSummary], code: bool = False) -> str:
    """One line a call, innermost last: the file from its package on, the
    line, the function, and with ``code`` the line's code: a third of
    Python's own format, so that a stack fits in a log record."""
    lines = []
    for frame in frames:
        name = frame.filename
        for marker in ("site-packages/", "/lib/python3"):
            if marker in name:
                name = name.rsplit(marker, 1)[1]
                break
        line = f"    {name}:{frame.lineno} {frame.name}"
        if code and frame.line:
            line += f": {frame.line.strip()[:80]}"
        lines.append(line)
    return "\n".join(lines)


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
            others = self.others()
            # Two records: the log keeps a record's start and end only
            # (logbuffer.LONGEST), and with the threads in the same one the
            # loop's innermost calls fell in the cut (2026-11-13).
            log.warning("the event loop has stood still for %.0f s, at:\n%s", stood, self.stack())
            if others:
                log.warning("other threads at work while the loop stood:\n%s", others)

    def stack(self) -> str:
        """Where the loop's thread is now, innermost call last."""
        frame = sys._current_frames().get(self._ident) if self._ident is not None else None
        if frame is None:
            return "  (the loop's thread is gone)"
        return compact(traceback.extract_stack(frame)[-LOOP_DEPTH:], code=True)

    def others(self) -> str:
        """The other threads not waiting for work, innermost call last of
        each: among them whoever holds what the loop waits for."""
        names = {t.ident: t.name for t in threading.enumerate()}
        shown: list[str] = []
        for ident, frame in sys._current_frames().items():
            if ident in (self._ident, threading.get_ident()):
                continue
            stack = traceback.extract_stack(frame)
            if not stack or stack[-1].filename.endswith(IDLE):
                continue
            calls = compact(stack[-THREAD_DEPTH:])
            shown.append(f"  thread {names.get(ident, ident)}:\n{calls}")
        more = len(shown) - THREADS_SHOWN
        return "\n".join(shown[:THREADS_SHOWN] + ([f"  and {more} more"] if more > 0 else []))

    def stop(self) -> None:
        self._stop.set()
