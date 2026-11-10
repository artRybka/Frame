"""Two pictures shown to a model: one work, a part of it, a photograph of it
on its wall, a copy by another hand, or two works.

The pictures tell most copies apart on their own (``library.twins``), but
not all: one scan in two colours, a print after a painting, two landscapes
of one dune. Before a model judges the pairs the pictures were unsure of
every night, Haiku, Sonnet, Opus and Fable are tried on pairs Mateusz's Vermeer
search showed (labelled by hand): the cheapest one that never calls two
works one is the judge (Mateusz 2026-11-10, card "Reguły teraz, potem test
i sędzia"). This is the question each of them is asked.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .client import FABLE, HAIKU, OPUS, SONNET, image_block, request
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import ImageCache, Item
    from .client import Claude

KIND = "twins.judge"
#: The models tried, by the names the app and the test script use.
MODELS = {"haiku": HAIKU, "sonnet": SONNET, "opus": OPUS, "fable": FABLE}
#: The pictures go out as the server keeps its thumbnails (640 px).
SIDE = 640
#: How the second picture relates to the first, as the test script counts.
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
#: What the model is asked: what kind of pair, and for a part or a
#: photograph, which picture is the whole work. One label naming both
#: ("a_detail_of_b") was read backwards by Haiku 6 times in 73 pairs while
#: its own reason said it right (test of 2026-11-10).
KINDS = ("same", "part", "photo", "copy_by_other_hand", "different", "unsure")
WHOLE = ("A", "B", "none")

SYSTEM = """You compare two catalogue pictures of artworks, A and B, for a home art frame \
that must show each artwork once. Decide what kind of pair they are.

"kind":
- "same": both show the same physical artwork whole. Different photographs, colour, \
lighting, sharpness, a trimmed or kept frame, a few percent cropped off an edge, a \
restoration state: still "same".
- "part": one picture shows only a part of the artwork the other shows whole (a head, a \
corner, a window), so much is missing that it is no longer the whole work.
- "photo": one picture is a photograph of the artwork the other shows, together with \
what is around it: a wide frame, the museum wall, a room, a label, visitors.
- "copy_by_other_hand": a different object repeating the composition: a print or \
engraving after a painting, a painted copy, a replica or version by the artist or the \
workshop, a pastiche, a photograph of such a print. Look for different brushwork or line, \
changed details, hatching, a plate margin or lettering.
- "different": two artworks, even by the same artist or of the same subject.
- "unsure": the pictures do not allow a decision.

"whole": for "part" and "photo", the letter of the picture that shows the artwork whole \
and alone ("A" or "B"); the other one is the part or the photograph. For every other \
kind, "none".

Titles, makers and dates come from different museums and languages and are often wrong: \
judge by the pictures, using the texts only as hints. Calling two different artworks \
"same", or taking the whole work for the part, hides an artwork from the owner, so say \
"same" only when the picture content matches figure for figure. Answer with "why" in at \
most 20 words first, then "kind", "whole" and "confidence" from 0 to 1."""

SCHEMA = _object(
    why=_str(),
    kind={"type": "string", "enum": list(KINDS)},
    whole={"type": "string", "enum": list(WHOLE)},
    confidence={"type": "number"},
)


def relation(kind: str, whole: str) -> str:
    """The answer as one of :data:`RELATIONS` ("" when it makes no sense:
    a part without its whole)."""
    if kind in ("part", "photo"):
        if whole not in ("A", "B"):
            return ""
        what = "detail" if kind == "part" else "photo"
        return f"b_{what}_of_a" if whole == "A" else f"a_{what}_of_b"
    return kind if kind in RELATIONS else ""


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
        return Verdict(
            name,
            relation(str(data.get("kind") or ""), str(data.get("whole") or "")),
            float(data.get("confidence") or 0.0),
            str(data.get("why") or ""),
            answer.cost_usd,
            time.monotonic() - started,
            refused=answer.refused,
        )

    with ThreadPoolExecutor(max_workers=len(models) or 1) as pool:
        return list(pool.map(one, models))
