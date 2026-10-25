"""The content store shares its folders with whatever the NAS puts there."""

from __future__ import annotations

import os
from pathlib import Path

from frame_server.fsutil import own_dirs, own_files
from frame_server.store import KEEP_IMAGES, ContentStore


def _nas_litter(directory: Path) -> None:
    """What Synology and macOS leave in a mounted folder, older than anything."""
    thumbs = directory / "@eaDir" / "old.png"
    thumbs.mkdir(parents=True)
    (thumbs / "SYNOFILE_THUMB_M.jpg").write_bytes(b"thumb")
    (directory / "#recycle").mkdir()
    (directory / ".DS_Store").write_bytes(b"x")
    for path in (directory / "@eaDir", directory / "#recycle", directory / ".DS_Store"):
        os.utime(path, (0, 0))


def test_publish_ignores_nas_folders(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    _nas_litter(store.images)
    for _ in range(KEEP_IMAGES + 3):
        info = store.publish(b"png", ext="png")
    assert store.current() == info
    assert len(list(own_files(store.images))) == KEEP_IMAGES
    assert (store.images / "@eaDir" / "old.png" / "SYNOFILE_THUMB_M.jpg").is_file()
    assert (store.images / "#recycle").is_dir()
    assert (store.images / ".DS_Store").is_file()
    assert store.image_path("@eaDir") is None


def test_own_entries(tmp_path: Path) -> None:
    _nas_litter(tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.png").write_bytes(b"b")
    (tmp_path / "dir.jpg").mkdir()
    (tmp_path / "0123456789ab").mkdir()
    assert sorted(p.name for p in own_files(tmp_path)) == ["a.jpg", "b.png"]
    assert [p.name for p in own_files(tmp_path, "*.jpg")] == ["a.jpg"]
    assert sorted(p.name for p in own_dirs(tmp_path)) == ["0123456789ab", "dir.jpg"]
