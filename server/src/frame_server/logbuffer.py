"""The server's recent log in memory, for ``/api/debug/log``: the container's
log is only on the NAS, and reading it there needs Container Manager
(2026-11-01).

Since 2026-11-07 it is written to the data folder too, a file a day for
:data:`DAYS` days (:func:`keep_on_disk`), and a start reads the end of the
last one back: an update of the server lost the morning the LoC and the Met
turned us away, and with it what had asked them."""

from __future__ import annotations

import logging
import logging.handlers
import threading
from collections import deque
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
KEEP = 5000  # records, about 1.5 MB
LONGEST = 4000  # characters of one record, traceback included
#: Of a longer record, this much of its start is kept (the message and the
#: first frames), the rest from its end: a traceback through Starlette's
#: middleware is mostly its frames, and what failed is at the very end.
HEAD = 1000
#: Days of the log kept on disk (a file each).
DAYS = 7
#: The file's name in its folder; older days get the date after it.
FILE = "server.log"


class LogBuffer(logging.Handler):
    def __init__(self, keep: int = KEEP) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter(FORMAT))
        self._records: deque[str] = deque(maxlen=keep)
        self._last: logging.LogRecord | None = None
        self._guard = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = _shorten(self.format(record))
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

    def preload(self, texts: list[str]) -> None:
        """Records of before the start, oldest first, ahead of the new ones."""
        with self._guard:
            room = (self._records.maxlen or len(texts)) - len(self._records)
            for text in reversed(texts[-room:] if room > 0 else []):
                self._records.appendleft(text)

    def lines(self, count: int, grep: str | None = None) -> list[str]:
        """The last ``count`` records, oldest first; with ``grep`` only the
        ones containing it (any case)."""
        with self._guard:
            texts = list(self._records)
        if grep:
            needle = grep.lower()
            texts = [t for t in texts if needle in t.lower()]
        return texts[-count:] if count > 0 else []


def _shorten(text: str) -> str:
    if len(text) <= LONGEST:
        return text
    cut = len(text) - (LONGEST - HEAD)
    return f"{text[:HEAD]}\n  [... {cut - HEAD} characters left out ...]\n{text[cut:]}"


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
        for handler in (_buffer, _file):
            if handler is not None and handler not in logger.handlers:
                logger.addHandler(handler)
    return _buffer


_file: logging.Handler | None = None


class _DayFiles(logging.handlers.TimedRotatingFileHandler):
    """A file a day; a record on both loggers it is attached to written once."""

    _last: logging.LogRecord | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if record is self._last:
            return
        self._last = record
        super().emit(record)


def keep_on_disk(folder: Path) -> None:
    """The log written to ``folder`` too (a file a day, :data:`DAYS` kept),
    and the end of what it held before this start read back into the
    buffer. Once per process; the buffer must be installed."""
    global _file
    if _file is not None or _buffer is None:
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / FILE
        before = _records_of(path)
        handler = _DayFiles(path, when="midnight", backupCount=DAYS - 1, encoding="utf-8")
    except OSError as err:
        logging.getLogger(__name__).warning("the log is not kept on disk: %s", err)
        return
    handler.setFormatter(logging.Formatter(FORMAT))
    _file = handler
    _buffer.preload(before[-KEEP:])
    install()


def _records_of(path: Path) -> list[str]:
    """The records of a log file (a record's further lines go with it)."""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            tail = deque(f, maxlen=KEEP * 3)
    except OSError:
        return []
    records: list[str] = []
    for line in tail:
        line = line.rstrip("\n")
        if line[:4].isdigit() and line[4:5] == "-":
            records.append(line)
        elif records:
            records[-1] += "\n" + line
    return [_shorten(r) for r in records]
