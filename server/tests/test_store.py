"""The content store shares its folders with whatever the NAS puts there."""

from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image

from frame_server.fsutil import own_dirs, own_files
from frame_server.store import KEEP_IMAGES, ContentStore, preview_url


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


def _png(size: tuple[int, int] = (64, 36)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, (90, 110, 60, 255)).save(out, "PNG")
    return out.getvalue()


def test_preview_goes_as_a_jpeg(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    info = store.publish(b"png", ext="png", preview_png=_png())
    assert preview_url(info.file_id) == f"/api/previews/{info.file_id}.jpg"
    path = store.preview_jpeg_path(info.file_id)
    assert path is not None and path.read_bytes()[:2] == b"\xff\xd8"
    with Image.open(path) as img:
        assert img.size == (64, 36) and img.mode == "RGB"
    assert store.preview_path(info.file_id) is not None  # older apps ask for the PNG

    # Published before there were JPEGs: made once from the PNG.
    path.unlink()
    again = store.preview_jpeg_path(info.file_id)
    assert again == path and again.is_file()
    assert store.preview_jpeg_path("nothing") is None
    assert store.preview_jpeg_path("../current") is None

    for _ in range(KEEP_IMAGES + 1):
        store.publish(b"png", ext="png", preview_png=_png())
    assert not path.exists()  # pruned with its picture
