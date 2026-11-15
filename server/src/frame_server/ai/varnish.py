"""A blue under yellowed varnish: Haiku says whether a green is one.

Old varnish yellows, and the blue of a sky, a river or the Virgin's robe
reads as teal or green in a museum's photograph; the work was found by no
blue. Colours alone cannot tell such a sky from a real green: of the 15
works of the owner's library the colour analysis found such an area in
(``colors.varnished_blue``), half were blue (Cranach's sky and Cupid's
wings, Bosch's Mary, Wyczółkowski's water), half green (the robes of
Cosmas and Damian, Mehoffer's leaves, Saada's skirt). Haiku, shown the
work and the same picture with only that area in colour, told them apart
in all 15 (Sonnet answered the same), for 0.002 USD (Mateusz 2026-11-15
09:41, card after the test: „Wdrożyć”). It is asked at night through the
Batch API; the blue it names is the work's accent (``colors.with_blue``),
kept through the colour analysis done again (``Player.rescore``).
"""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from ..imaging.color import linear_to_oklab
from ..imaging.layout import load_image
from ..library.colors import VARNISH_NOTE, _grid, saw_blue, varnish_area, with_blue
from .client import HAIKU, IMAGE_SIDE, request
from .jobs import NoteJob, Usage, text_hash

if TYPE_CHECKING:
    from ..library import Item
    from ..library.models import Note

KIND = VARNISH_NOTE
PROMPT_VERSION = "vb-1"
#: The colour analysis's grid (``colors.analyse``), the area's resolution.
GRID = 128
#: Outside the area the picture is grey and this bright.
DIM = 0.35

SYSTEM = """\
You look at old paintings. Yellowed varnish makes blues look green: a sky, \
a river or a blue robe can read as teal or green in a photograph of the \
painting.
You get the painting and the same painting with one area left in colour \
(everything else dimmed). Say what that area shows and which colour the \
painter most likely put there: "blue" (sky, water, distant hills, a blue \
cloth that the varnish turned greenish), "green" (foliage, grass, a green \
cloth, green stone), or "other". Answer "blue" only when the area is blue \
paint, not when blue merely could be there."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "area": {"type": "string", "description": "what the marked area shows, a few words"},
        "painted": {"type": "string", "enum": ["blue", "green", "other"]},
    },
    "required": ["area", "painted"],
    "additionalProperties": False,
}


def _block(img: Image.Image) -> dict[str, Any]:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    data = base64.standard_b64encode(out.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def pictures(thumb: Image.Image) -> tuple[Image.Image, Image.Image]:
    """The work, and the work with only its area that may be a blue under
    varnish in colour (``colors.varnish_area``), the rest dimmed grey."""
    whole = load_image(thumb).convert("RGB")
    whole.thumbnail((IMAGE_SIDE, IMAGE_SIDE), Image.Resampling.LANCZOS)
    area = varnish_area(linear_to_oklab(_grid(thumb, GRID)))
    mask = Image.fromarray((area * 255).astype(np.uint8)).resize(
        whole.size, Image.Resampling.BILINEAR
    )
    grey = whole.convert("L").point(lambda v: int(v * DIM)).convert("RGB")
    return whole, Image.composite(whole, grey, mask)


def _facts(item: Item) -> str:
    parts = (item.artist, item.title, item.date_text, item.medium)
    return ", ".join(p for p in parts if p)


class VarnishJob(NoteJob):
    kind = KIND
    model = HAIKU
    prompt_version = PROMPT_VERSION
    typical = Usage(input_tokens=1000, cache_read_input_tokens=0, output_tokens=250)
    steady = True
    night = True

    def wanted(self, item: Item) -> bool:
        return item.varnish_blue > 0 and not item.excluded

    def source_hash(self, item: Item) -> str:
        return text_hash(item.thumb_url)

    def params(self, item: Item) -> dict[str, Any]:
        with Image.open(self.images.ensure_thumb(item)) as thumb:
            whole, marked = pictures(thumb)
        content = [_block(whole), _block(marked), {"type": "text", "text": _facts(item)}]
        return request(
            model=self.model, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=1000
        )

    def apply(self, item: Item, note: Note) -> None:
        if not saw_blue(note):
            return
        latest = self.library.get(item.id) or item  # the night's rescore may have written
        tags = with_blue(latest.color_tags)
        if tags != latest.color_tags:
            self.library.update(item.id, color_tags=tags)
