"""Listing the server's own files in folders that other software writes to.

A NAS adds its own entries to mounted folders: Synology puts thumbnails in
``@eaDir`` directories and deleted files in ``#recycle``, macOS leaves
``.DS_Store``. They are neither ours to serve nor ours to delete.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

_FOREIGN_PREFIXES = (".", "@", "#")


def is_foreign(path: Path) -> bool:
    return path.name.startswith(_FOREIGN_PREFIXES)


def own_files(directory: Path, pattern: str = "*") -> Iterator[Path]:
    """Regular files in ``directory`` matching ``pattern``, without the
    entries a NAS or another OS keeps there."""
    for path in directory.glob(pattern):
        if not is_foreign(path) and path.is_file():
            yield path


def own_dirs(directory: Path) -> Iterator[Path]:
    """Subdirectories of ``directory``, without those of a NAS or another OS."""
    for path in directory.iterdir():
        if not is_foreign(path) and path.is_dir():
            yield path


def dir_bytes(directory: Path) -> int:
    """Bytes in the regular files directly in ``directory`` (none when it is
    missing), without the entries of a NAS or another OS. One directory read
    and one stat per file: the cheapest walk on a slow disk."""
    total = 0
    try:
        entries = os.scandir(directory)
    except FileNotFoundError:
        return 0
    with entries:
        for entry in entries:
            if entry.name.startswith(_FOREIGN_PREFIXES):
                continue
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
            except FileNotFoundError:
                continue  # trimmed meanwhile
    return total
