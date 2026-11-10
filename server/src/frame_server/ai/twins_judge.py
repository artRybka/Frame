"""Two pictures shown to a model: one work, a part of it, a photograph of it
on its wall, a copy by another hand, or two works.

The pictures tell most copies apart on their own (``library.twins``), but
not all: one scan in two colours, a print after a painting, two landscapes
of one dune. Before a model judges the pairs the pictures were unsure of
every night, Haiku, Sonnet and Fable are tried on pairs Mateusz's Vermeer
search showed (labelled by hand): the cheapest one that never calls two
works one is the judge (Mateusz 2026-11-10, card "Reguły teraz, potem test
i sędzia"). This is the question each of them is asked.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .client import FABLE, HAIKU, SONNET, image_block, request
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import ImageCache, Item
    from .client import Claude

KIND = "twins.judge"
#: The models tried, by the names the app and the test script use.
MODELS = {"haiku": HAIKU, "sonnet": SONNET, "fable": FABLE}
#: The pictures go out as the server keeps its thumbnails (640 px).
SIDE = 640
RELATIONS = (
    "same",
    "a_detail_of_b",
    "b_detail_of_a",
    "a_photo_of_b",
    "b_photo_of_a",
    "copy_by_other_hand",
    "different",
    "unsure",
)

SYSTEM = """You compare two catalogue pictures of artworks, A and B, for a home art frame \
that must show each artwork once. Say how B relates to A.

- "same": both show the same physical artwork whole. Different photographs, colour, \
lighting, sharpness, a trimmed or kept frame, a few percent cropped off an edge, a \
restoration state: still "same".
- "a_detail_of_b" / "b_detail_of_a": one shows only a part of the other artwork (a head, \
a corner, a window), so much is missing that it is no longer the whole work.
- "a_photo_of_b" / "b_photo_of_a": one is a photograph of the other artwork together with \
what is around it: a wide frame, the museum wall, a room, a label, visitors.
- "copy_by_other_hand": a different object repeating the composition: a print or \
engraving after a painting, a painted copy, a replica or version by the artist or the \
workshop, a pastiche, a photograph of such a print. Look for different brushwork or line, \
changed details, hatching, a plate margin or lettering.
- "different": two artworks, even by the same artist or of the same subject.
- "unsure": the pictures do not allow a decision.

Titles, makers and dates come from different museums and languages and are often wrong: \
judge by the pictures, using the texts only as hints. Calling two different artworks \
"same" hides one of them from the owner, so say "same" only when the picture content \
matches figure for figure. Answer with "confidence" from 0 to 1 and "why" in at most 20 \
words."""

SCHEMA = _object(
    relation={"type": "string", "enum": list(RELATIONS)},
    confidence={"type": "number"},
    why=_str(),
)


@dataclass
class Verdict:
    model: str
    relation: str  # one of RELATIONS; "" when refused or no answer
    confidence: float
    why: str
    cost_usd: float
    seconds: float
    refused: bool = False
    error: str = ""


def _label(name: str, item: Item) -> str:
    parts = [
        f"{name}: {item.title or '(no title)'}",
        f"maker: {item.artist or '?'}",
        f"date: {item.date_text or item.year or '?'}",
        f"source: {item.source}",
    ]
    if item.medium:
        parts.append(f"medium: {item.medium}")
    if item.width and item.height:
        parts.append(f"picture: {item.width}×{item.height} px")
    return "; ".join(parts)


def params(images: ImageCache, a: Item, b: Item, model: str, effort: str = "low") -> dict[str, Any]:
    """The question about ``a`` and ``b`` for ``model``."""
    content = [
        {"type": "text", "text": "Picture A:"},
        image_block(images, a, SIDE),
        {"type": "text", "text": "Picture B:"},
        image_block(images, b, SIDE),
        {"type": "text", "text": f"{_label('A', a)}\n{_label('B', b)}"},
    ]
    return request(
        model=model, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=4000, effort=effort
    )


def judge(
    claude: Claude,
    images: ImageCache,
    a: Item,
    b: Item,
    models: list[str],
    effort: str = "low",
) -> list[Verdict]:
    """Each of ``models`` (keys of :data:`MODELS`) asked about ``a`` and ``b``
    at once; a model that fails says why, the others still answer."""
    claude.check_budget()
    claude.client()  # no key: nothing asked

    def one(name: str) -> Verdict:
        model = MODELS[name]
        started = time.monotonic()
        try:
            answer = claude.ask(KIND, params(images, a, b, model, effort))
        except Exception as err:  # one model down: the others still answer
            return Verdict(name, "", 0.0, "", 0.0, time.monotonic() - started, error=str(err))
        data = answer.data or {}
        relation = data.get("relation")
        return Verdict(
            name,
            relation if relation in RELATIONS else "",
            float(data.get("confidence") or 0.0),
            str(data.get("why") or ""),
            answer.cost_usd,
            time.monotonic() - started,
            refused=answer.refused,
        )

    with ThreadPoolExecutor(max_workers=len(models) or 1) as pool:
        return list(pool.map(one, models))
