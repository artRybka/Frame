"""The server's recent log in memory, for ``/api/debug/log``: the container's
log is only on the NAS, and reading it there needs Container Manager
(2026-11-01). Lost at a restart; the container log keeps everything."""

from __future__ import annotations

import logging
import threading
from collections import deque

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
KEEP = 5000  # records, about 1.5 MB
LONGEST = 4000  # characters of one record, traceback included


class LogBuffer(logging.Handler):
    def __init__(self, keep: int = KEEP) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter(FORMAT))
        self._records: deque[str] = deque(maxlen=keep)
        self._last: logging.LogRecord | None = None
        self._guard = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)[:LONGEST]
        except Exception:
            self.handleError(record)
            return
        with self._guard:
            # Attached to the root and to uvicorn's error logger: a record
            # that propagates from one to the other only once.
            if record is self._last:
                return
            self._last = record
            self._records.append(text)

    def lines(self, count: int, grep: str | None = None) -> list[str]:
        """The last ``count`` records, oldest first; with ``grep`` only the
        ones containing it (any case)."""
        with self._guard:
            texts = list(self._records)
        if grep:
            needle = grep.lower()
            texts = [t for t in texts if needle in t.lower()]
        return texts[-count:] if count > 0 else []


_buffer: LogBuffer | None = None


def install() -> LogBuffer:
    """The process's buffer, attached to the root logger (the server's own
    records) and to uvicorn's error logger (failed requests, which uvicorn
    keeps from the root). Not its access log: the panel's requests are
    logged by the server already.

    Called again once the server runs: uvicorn sets up its loggers with
    ``dictConfig`` after the app is made, which drops the handlers they had,
    so the buffer is attached wherever it is missing."""
    global _buffer
    if _buffer is None:
        _buffer = LogBuffer()
    for logger in (logging.getLogger(), logging.getLogger("uvicorn.error")):
        if _buffer not in logger.handlers:
            logger.addHandler(_buffer)
    return _buffer
