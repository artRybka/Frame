"""The study sheets the analyses of composition are drawn on
(``imaging.sheet``): made when first asked for, kept on disk.

A sheet is made from the work's picture (its field alone, when the
analysis found one on a reproduction with margins) and the analysis's pen
sketch, in the light page's colours and in the dark one's. The app asks
for it by the address its page gives (``DailyWork.composition_sheet``),
which changes with the analysis, so a sheet is kept by the app for long.
"""

from __future__ import annotations

import contextlib
import threading
import time
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from .ai.check import page_views
from .ai.composition import PAGES, cropped
from .ai.jobs import text_hash
from .imaging import sheet as sheets
from .imaging.layout import load_image

if TYPE_CHECKING:
    from .ai.daily import View
    from .library import ImageCache, Item, Library

#: A sheet nobody asked for this long is let go (it is made again when asked).
SHEET_DAYS = 60
#: The picture a sheet is made from is at most this long: the sheet is no longer.
SOURCE_SIDE = 2000


class Sheets:
    def __init__(self, library: Library, images: ImageCache) -> None:
        self.library = library
        self.images = images
        self.dir = images.thumbs.parent / "sheets"
        self._making = threading.Lock()

    @staticmethod
    def key(view: View) -> str:
        """What a take's sheet is made of, as a few letters: the look, the
        picture's field, the strokes of its pen sketch."""
        field = view.field.model_dump_json() if view.field is not None else ""
        strokes = "|".join(s.model_dump_json() for s in view.sketch)
        return text_hash(sheets.LOOK, field, strokes)[:10]

    def path(self, item: Item, view: View, dark: bool) -> Path:
        return self.dir / f"{item.file_stem}-{self.key(view)}-{'d' if dark else 'l'}.jpg"

    def view(self, item: Item, key: str = "") -> View | None:
        """The take whose sheet ``key`` names among those the work's pages
        show (its study, its day's page); the first of them when none does
        (an address kept from before the analysis was made anew)."""
        shown = []
        for kind in PAGES:
            note = self.library.note(item.id, kind)
            if note is not None:
                shown += page_views(note.data)
        return next((v for v in shown if self.key(v) == key), shown[0] if shown else None)

    def sheet(self, item: Item, view: View, dark: bool) -> Path:
        """The take's sheet, made now when it is not kept."""
        path = self.path(item, view, dark)
        if path.is_file():
            with contextlib.suppress(OSError):
                path.touch()  # asked for: kept
            return path
        with self._making:  # one at a time: each takes seconds and a good deal of memory
            if not path.is_file():
                self._make(item, view, dark, path)
        return path

    def _make(self, item: Item, view: View, dark: bool, path: Path) -> None:
        source, _ = self.images.picture(item)
        img = load_image(source.read_bytes()).convert("RGB")
        img.thumbnail((SOURCE_SIDE, SOURCE_SIDE), Image.Resampling.LANCZOS)
        if view.field is not None:
            img = cropped(img, view.field)
        strokes = [([(p.x, p.y) for p in s.points], s.sharp, s.closed) for s in view.sketch]
        made = sheets.render(img, strokes, dark=dark, seed=zlib.crc32(item.id.encode()))
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(sheets.jpeg(made))
        tmp.replace(path)
        cutoff = time.time() - SHEET_DAYS * 86400
        for old in self.dir.glob("*.jpg"):
            with contextlib.suppress(OSError):
                if old.stat().st_mtime < cutoff:
                    old.unlink()
