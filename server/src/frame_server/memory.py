"""How much memory the server takes, and how much the machine has left.

The catalogue lives in memory (about 2.2 GB for 117 thousand works, the
audit of 2026-11-14). On a NAS with little memory the system moves part of
it to the disk (swap), and then everything is many times slower with
nothing in the log to say why: this reading says it
(``GET /api/debug/memory``, the owner's). Linux only; elsewhere the
numbers are missing.
"""

from __future__ import annotations

from pathlib import Path

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
