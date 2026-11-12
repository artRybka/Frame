"""The study sheets the analyses of composition are drawn on
(``imaging.sheet``): made ahead, kept on disk.

A sheet is made from the work's picture (its field alone, when the
analysis found one on a reproduction with margins) and the analysis's pen
sketch, in the light page's colours and in the dark one's. The app asks
for it by the address its page gives (``DailyWork.composition_sheet``),
which changes with the analysis, so a sheet is kept by the app for long.

It is kept as its two layers, the stains and what the pen drew, which the
app lays one on the other as each is "painted" and "drawn" before the
reader, and whole, for apps from before that. The layers are kept twice:
with the page's margin beside the field, where a stain runs out and a
stroke goes on past the frame (Mateusz 2026-11-12 11:04), and cut back to
the field, for the app that lays them in the frame.

Making one takes seconds here and much longer on a small server, and the
reader waited for it on an empty page (Mateusz 2026-11-12: "Po wejściu w
studium sporo czasu czekam aż pojawi się obraz analizy kompozycji"). So
the sheets of the pages there are get made in the background, the newest
page's first (:meth:`Sheets.ahead`); one asked for before its turn is
still made at once.
"""

from __future__ import annotations

import contextlib
import logging
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

log = logging.getLogger(__name__)

#: A sheet nobody asked for this long is let go (it is made again when asked).
SHEET_DAYS = 60
#: The picture a sheet is made from is at most this long: the sheet is no longer.
SOURCE_SIDE = 2000
#: What may be asked of a sheet, and the end of the file it is kept in:
#: whole (apps from before the layers), the stains alone, the pen alone
#: (the field, for apps from before the margin), and those two with the
#: margin beside the field (``sheet.BLEED``).
LAYERS = {
    "": ".jpg",
    "wash": "-w.jpg",
    "pen": "-p.png",
    "wash-bleed": "-wb.jpg",
    "pen-bleed": "-pb.png",
}
#: How long the background rests between two sheets made ahead, and before
#: it looks again once all are made; a work whose picture could not be had
#: is tried again after this long.
AHEAD_REST = 2.0
AHEAD_IDLE = 45.0
AHEAD_AGAIN = 3600.0
#: The background lets the server start first.
AHEAD_START = 90.0


class Sheets:
    def __init__(self, library: Library, images: ImageCache) -> None:
        self.library = library
        self.images = images
        self.dir = images.thumbs.parent / "sheets"
        self._making = threading.Lock()
        #: Works whose sheet could not be made ahead, and when.
        self._failed: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def key(view: View) -> str:
        """What a take's sheet is made of, as a few letters: the look, the
        picture's field, the strokes of its pen sketch."""
        field = view.field.model_dump_json() if view.field is not None else ""
        strokes = "|".join(s.model_dump_json() for s in view.sketch)
        return text_hash(sheets.LOOK, field, strokes)[:10]

    def path(self, item: Item, view: View, dark: bool, layer: str = "") -> Path:
        shade = "d" if dark else "l"
        return self.dir / f"{item.file_stem}-{self.key(view)}-{shade}{LAYERS[layer]}"

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

    def sheet(self, item: Item, view: View, dark: bool, layer: str = "") -> Path:
        """The take's sheet (one of :data:`LAYERS`), made now when it is
        not kept."""
        path = self.path(item, view, dark, layer)
        if path.is_file():
            with contextlib.suppress(OSError):
                path.touch()  # asked for: kept
            return path
        with self._making:  # one at a time: each takes seconds and a good deal of memory
            if not path.is_file():
                self._make(item, view, dark)
        return path

    def _make(self, item: Item, view: View, dark: bool) -> None:
        source, _ = self.images.picture(item)
        img = load_image(source.read_bytes()).convert("RGB")
        img.thumbnail((SOURCE_SIDE, SOURCE_SIDE), Image.Resampling.LANCZOS)
        if view.field is not None:
            img = cropped(img, view.field)
        strokes = [([(p.x, p.y) for p in s.points], s.sharp, s.closed) for s in view.sketch]
        wash, pen = sheets.layers(
            img,
            strokes,
            dark=dark,
            seed=zlib.crc32(item.id.encode()),
            weights=[s.weight for s in view.sketch],
        )
        whole = wash.convert("RGBA")
        whole.alpha_composite(pen)
        self.dir.mkdir(parents=True, exist_ok=True)
        made = {
            "": sheets.jpeg(sheets.field(whole.convert("RGB"))),
            "wash": sheets.jpeg(sheets.field(wash)),
            "pen": sheets.png(sheets.field(pen)),
            "wash-bleed": sheets.jpeg(wash),
            "pen-bleed": sheets.png(pen),
        }
        for layer, data in made.items():
            path = self.path(item, view, dark, layer)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        cutoff = time.time() - SHEET_DAYS * 86400
        for old in self.dir.iterdir():
            with contextlib.suppress(OSError):
                if old.suffix in (".jpg", ".png") and old.stat().st_mtime < cutoff:
                    old.unlink()

    # -- made ahead -----------------------------------------------------------

    def wanting(self) -> list[tuple[Item, View, bool]]:
        """The sheets the pages there are show and that are not kept yet:
        the newest page's first, its light one before its dark one."""
        now = time.monotonic()
        found: list[tuple[str, Item, View, bool]] = []
        for kind in PAGES:
            for item_id, note in self.library.notes(kind).items():
                if now - self._failed.get(item_id, -AHEAD_AGAIN) < AHEAD_AGAIN:
                    continue
                views = page_views(note.data)
                item = self.library.get(item_id) if views else None
                if item is None:
                    continue
                for dark in (False, True):
                    if not self.path(item, views[0], dark, "wash").is_file():
                        found.append((str(note.created_at), item, views[0], dark))
        found.sort(key=lambda entry: entry[0], reverse=True)
        return [(item, view, dark) for _, item, view, dark in found]

    def ahead(self) -> bool:
        """Makes one sheet that is not kept yet; False when all are."""
        wanting = self.wanting()
        if not wanting:
            return False
        item, view, dark = wanting[0]
        try:
            self.sheet(item, view, dark, "wash")
        except Exception as err:  # the picture cannot be had, or is no picture
            log.warning("sheet of %s not made ahead: %s", item.id, err)
            self._failed[item.id] = time.monotonic()
        return True

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="sheets", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def _run(self) -> None:
        if self._stop.wait(AHEAD_START):
            return
        while not self._stop.wait(AHEAD_REST):
            try:
                if not self.ahead() and self._stop.wait(AHEAD_IDLE):
                    return
            except Exception:
                log.exception("sheets made ahead")
                if self._stop.wait(AHEAD_IDLE):
                    return
