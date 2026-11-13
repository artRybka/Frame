"""How a work was painted, stage by stage, in its study (Mateusz
2026-11-13, "G2": "mam wątpliwości, bo to troche wróżenie. chyba że
mielibyśmy jakieś dane dotyczęce techniki"; "G2 - ok, w tej formie to dobry
pomysł").

Only for a work whose published technical study the facts from the web
found (``ai.web_facts``: X-rays, infrared, paint samples): its stages as the
study tells them, each drawn by Google's image model (Nano Banana 2.1) on
the same canvas, from the finished picture, at full frame. The last stage
is the work itself, never drawn. The captions are the study's own words;
nothing is guessed when there is no study.

Drawn in the background once the study's page is shown, about 0.04 USD a
stage, kept for good next to the drawn sheets.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from .ai.client import AiUnavailable
from .ai.daily import picture
from .ai.gemini import MODEL, NotDrawn
from .library.markup import strip_markup
from .library.models import ItemKind, Note

if TYPE_CHECKING:
    from .ai.config import AiConfigStore
    from .ai.gemini import Painter
    from .ai.web_facts import Found, WebFacts
    from .library import ImageCache, Item, Library

log = logging.getLogger(__name__)

KIND = "stages"
VERSION = "stages-1"
#: The picture the model is shown, and the size it draws in.
SIDE = 1536
SIZE = "1K"
#: Stages drawn at most (the last of the study's is the work itself).
MOST = 5
#: A work whose stages could not be drawn is not tried again for this long.
RETRY_AFTER = 24 * 3600.0
#: About what one stage costs, USD.
STAGE_USD = 0.04

PROMPT = """This is a finished painting: {work}.
A published technical study ({what}) describes how this very canvas was made, stage by stage:
{stages}

Draw how THIS SAME canvas looked at the end of stage {n}, "{name}". Keep the canvas, its \
proportions, the composition and the place and size of everything exactly as in the finished \
painting; show only what had been put down by then, as the study describes it, and leave the \
rest as the bare ground or priming the study names. It is the same object photographed in \
the studio at that moment: real paint, real ground, real canvas texture.
The canvas fills the whole picture edge to edge: no frame, no border, no wall, no easel, no \
text, no numbers, no labels."""


class Stage(BaseModel):
    title: str
    text: str
    #: Drawn (the last stage is the work's own picture: never).
    drawn: bool = False


class Stages(BaseModel):
    what: str = ""
    stages: list[Stage] = Field(default_factory=list)


def prompt(item: Item, found: Found, n: int) -> str:
    work = ", ".join(
        p for p in (item.artist, f"“{strip_markup(item.title)}”", item.date_text, item.medium) if p
    )
    listed = "\n".join(
        f"{at}. {s.stage}: {s.text}" for at, s in enumerate(found.technical.stages, start=1)
    )
    stage = found.technical.stages[n]
    return PROMPT.format(
        work=work, what=found.technical.what or "", stages=listed, n=n + 1, name=stage.stage
    )


class PaintingStages:
    """The works' stages, kept as notes of :data:`KIND` and pictures under
    ``drawn/stages``."""

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        painter: Painter,
        facts: WebFacts,
        config: AiConfigStore,
    ) -> None:
        self.library = library
        self.images = images
        self.painter = painter
        self.facts = facts
        self.config = config
        self.dir = images.thumbs.parent / "drawn" / "stages"
        self._lock = threading.Lock()
        self._drawing: set[str] = set()
        self._failed: dict[str, float] = {}

    def enabled(self) -> bool:
        return self.painter.enabled() and self.config.config.stages

    def stages(self, item: Item) -> Stages | None:
        note = self.library.note(item.id, KIND)
        if note is None or note.prompt_version != VERSION or not note.data:
            return None
        try:
            return Stages.model_validate(note.data)
        except ValidationError:
            return None

    def path(self, item: Item, n: int) -> Path:
        return self.dir / f"{item.file_stem}-{n}.jpg"

    def part(self, item: Item, n: int) -> Path | None:
        """A stage's picture, when it was drawn."""
        made = self.stages(item)
        if made is None or not 0 <= n < len(made.stages) or not made.stages[n].drawn:
            return None
        path = self.path(item, n)
        return path if path.is_file() else None

    def wanted(self, item: Item) -> Found | None:
        """The facts of a work whose stages are to be drawn: a published
        technical study found, nothing drawn yet."""
        if item.kind != ItemKind.ARTWORK or self.stages(item) is not None:
            return None
        found = self.facts.found(item)
        if found is None or not found.technical.found or len(found.technical.stages) < 2:
            return None
        return found

    def draw_soon(self, item: Item) -> bool:
        """Draws the stages in the background, once; True while it does."""
        if not self.enabled() or self.wanted(item) is None:
            return False
        with self._lock:
            if item.id in self._drawing:
                return True
            if time.monotonic() - self._failed.get(item.id, -RETRY_AFTER) < RETRY_AFTER:
                return False
            self._drawing.add(item.id)
        threading.Thread(target=self._draw, args=(item,), name="stages", daemon=True).start()
        return True

    def drawing(self, item_id: str) -> bool:
        with self._lock:
            return item_id in self._drawing

    def _draw(self, item: Item) -> None:
        try:
            if not self.draw(item):
                with self._lock:
                    self._failed[item.id] = time.monotonic()
        except Exception:
            log.exception("stages of %s", item.id)
        finally:
            with self._lock:
                self._drawing.discard(item.id)

    def draw(self, item: Item) -> bool:
        """Draws every stage but the last (the work itself) and keeps them;
        False when they could not be had (nothing kept, tried later)."""
        found = self.wanted(item)
        if found is None:
            return False
        study = found.technical.stages[-(MOST + 1) :]
        found = found.model_copy(
            update={"technical": found.technical.model_copy(update={"stages": study})}
        )
        img = picture(self.images, item, SIDE)
        self.dir.mkdir(parents=True, exist_ok=True)
        stages: list[Stage] = []
        spent = 0.0
        for n, stage in enumerate(study):
            last = n == len(study) - 1
            if not last:
                try:
                    drawn, usd = self.painter.paint(KIND, prompt(item, found, n), [img], SIZE)
                except (AiUnavailable, NotDrawn) as err:
                    log.warning("stage %d of %s not drawn: %s", n + 1, item.id, err)
                    return False
                spent += usd
                # The same canvas: in the work's own proportions.
                drawn.convert("RGB").resize(img.size, Image.Resampling.LANCZOS).save(
                    self.path(item, n), "JPEG", quality=90
                )
            stages.append(Stage(title=stage.stage, text=stage.text, drawn=not last))
        made = Stages(what=found.technical.what, stages=stages)
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model=MODEL,
                prompt_version=VERSION,
                data=made.model_dump(),
            )
        )
        log.info("stages of %s: %d drawn, %.2f USD", item.id, len(stages) - 1, spent)
        return True
