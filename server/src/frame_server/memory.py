"""How much memory the server takes, and how much the machine has left.

The catalogue lives in memory (about 2.2 GB for 117 thousand works, the
audit of 2026-11-14). On a NAS with little memory the system moves part of
it to the disk (swap), and then everything is many times slower with
nothing in the log to say why: this reading says it
(``GET /api/debug/memory``, the owner's). Linux only; elsewhere the
numbers are missing.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

_PROCESS = {"VmRSS": "resident", "VmHWM": "resident_peak", "VmSwap": "swapped"}
_MACHINE = {
    "MemTotal": "total",
    "MemAvailable": "available",
    "SwapTotal": "swap_total",
    "SwapFree": "swap_free",
}
#: The container's own limit and use (cgroup v2), when it has one.
_CONTAINER = {"memory.max": "limit", "memory.current": "used", "memory.swap.current": "swapped"}


def _kb_lines(path: Path, names: dict[str, str]) -> dict[str, int]:
    """``Name:   123 kB`` lines of ``path`` as megabytes, under our names."""
    found: dict[str, int] = {}
    try:
        text = path.read_text()
    except OSError:
        return found
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if name in names and parts and parts[0].isdigit():
            found[names[name]] = int(parts[0]) // 1024
    return found


def reading(proc: Path = Path("/proc"), cgroup: Path = Path("/sys/fs/cgroup")) -> dict[str, object]:
    """The process's memory, the machine's and the container's, in MB."""
    container: dict[str, int] = {}
    for file, name in _CONTAINER.items():
        try:
            text = (cgroup / file).read_text().strip()
        except OSError:
            continue
        if text.isdigit():  # "max": no limit
            container[name] = int(text) // (1024 * 1024)
    return {
        "process_mb": _kb_lines(proc / "self" / "status", _PROCESS),
        "machine_mb": _kb_lines(proc / "meminfo", _MACHINE),
        "container_mb": container,
    }


# -- finding where it goes (2026-11-21) ----------------------------------------------------

#: How often :class:`MemoryLog` writes its line.
LOG_EVERY = 600.0


def trim() -> bool:
    """glibc's free memory handed back to the system (``malloc_trim``);
    False where there is no glibc. A day after 1.145.295 the server held
    8.3 GB with 3.4 GB of it in swap, untouched (2026-11-21): freed but
    kept, or still held? A trim that frees gigabytes says the first."""
    import ctypes
    import ctypes.util

    name = ctypes.util.find_library("c")
    if not name:
        return False
    try:
        libc = ctypes.CDLL(name)
        trim_fn = libc.malloc_trim
    except (OSError, AttributeError):
        return False
    trim_fn.argtypes = [ctypes.c_size_t]
    trim_fn.restype = ctypes.c_int
    trim_fn(0)
    return True


def census(top: int = 30) -> list[dict[str, object]]:
    """Python's objects by type, the most numerous first, with their own
    sizes (not what they hold). Goes through every object: seconds with the
    catalogue in memory, the owner's question only."""
    import gc
    import sys

    counts: dict[str, list[int]] = {}
    for obj in gc.get_objects():
        name = type(obj).__qualname__
        entry = counts.get(name)
        if entry is None:
            entry = counts[name] = [0, 0]
        entry[0] += 1
        with contextlib.suppress(TypeError):
            entry[1] += sys.getsizeof(obj)
    ranked = sorted(counts.items(), key=lambda kv: kv[1][1], reverse=True)[:top]
    return [
        {"type": name, "count": n, "mb": round(size / 1048576, 1)} for name, (n, size) in ranked
    ]


class MemoryLog:
    """A line in the log every :data:`LOG_EVERY` seconds: the process's
    memory, the machine's and what ``parts`` say (works, indexes, the
    model), so a day's log shows when it grew and beside what."""

    def __init__(self, parts: Callable[[], dict[str, object]], every: float = LOG_EVERY) -> None:
        self.parts = parts
        self.every = every
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, name="memory-log", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def line(self) -> str:
        now = reading()
        process = now["process_mb"]
        machine = now["machine_mb"]
        assert isinstance(process, dict) and isinstance(machine, dict)
        try:
            parts = self.parts()
        except Exception as err:  # a part read mid-change: the numbers still
            parts = {"parts": f"unread ({err})"}
        said = " ".join(f"{k}={v}" for k, v in parts.items())
        return (
            f"memory: resident {process.get('resident', '?')} MB "
            f"(peak {process.get('resident_peak', '?')}), "
            f"swapped {process.get('swapped', '?')} MB, "
            f"machine available {machine.get('available', '?')} MB; {said}"
        )

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            log.info("%s", self.line())
