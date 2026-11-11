"""The catalogue's night audit: a few works a night looked over for what
does not add up (Mateusz 2026-11-10, "K4").

Rules catch what someone thought of; the audit finds what nobody did. Each
night Haiku gets :data:`PER_NIGHT` works of the catalogue drawn at random,
the picture with everything the server knows of it (the source's title,
maker, date, type and text, the Polish title and text the app shows), and
says what does not fit: a title that is not what the picture shows, a date
outside the maker's life, a Polish text that adds facts the source does
not give, a picture on its side, with a colour chart, faded or cut. The
critic (Haiku with the opposite question) keeps only what is really there.
Nothing is changed: what is left goes on the owner's list "Do sprawdzenia"
(each a ready example for the rules, and a count of which source errs).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from ..library.models import ItemKind
from ..library.verdict import Place, against
from .client import image_block, request
from .critic_night import CriticNight
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import Item

KIND = "audit"
SWITCH = "audit"
#: Works looked over a night: about 0.01 USD (Haiku, Batch API).
PER_NIGHT = 30
#: Text sent along, at most.
TEXT_CHARS = 1200
#: What a finding is about, with the name the app shows.
FIELDS = {
    "title": "Tytuł",
    "artist": "Autor",
    "date": "Data",
    "polish": "Polski opis",
    "picture": "Obraz",
}
MAX_PROBLEMS = 4

SYSTEM = """You audit the catalogue of a home art frame. You get one artwork: its picture and \
everything the catalogue knows of it (what its source says, and the Polish title and text the \
frame's app shows). Find what does not add up, so the owner can fix it.

First write "why": in at most 25 words, what the picture actually shows. Then answer:
- "title_fits": does the title fit what the picture shows (allowing for the subject's \
own name, a saint, a place, a myth)?
- "date_fits": are the date and the maker possible together (within the maker's life and \
time, as far as you know them)? true when there is no date or no maker.
- "polish_fits": does the Polish text say only what the source's text, the facts above or \
the picture support, without contradicting them? true when there is no Polish text.
- "picture_fits": is the picture the artwork shown upright and whole, without a colour \
chart, ruler, heavy fading, a strong colour cast or a part cut off?
Then "problems": for each answer that is false, one entry with "field" (title, artist, date, \
polish or picture) and "problem": in Polish, at most 20 words, what exactly is wrong. Report \
only what is plainly wrong; style, taste and missing facts are no problems. Last, \
"confidence" from 0 to 1."""

SCHEMA = _object(
    why=_str(),
    title_fits={"type": "boolean"},
    date_fits={"type": "boolean"},
    polish_fits={"type": "boolean"},
    picture_fits={"type": "boolean"},
    problems={
        "type": "array",
        "items": _object(field={"type": "string", "enum": list(FIELDS)}, problem=_str()),
    },
    confidence={"type": "number"},
)

CRITIC = """You check problems someone found in the catalogue of a home art frame, before the \
owner spends time on them. You get one artwork (its picture and what the catalogue knows of it) \
and numbered problems.

For each problem, look for evidence that it is NOT a problem: the title may name the subject \
in another language or by its story, a maker may have worked longer than said, a Polish text \
may rightly tell what the picture shows, an old work may be dark or yellowed by its varnish. \
Keep a problem only when it is plainly real.

Answer with "why" in at most 20 words first, then "real": the numbers of the problems that \
are really there (an empty list when none is), and "confidence" from 0 to 1."""

CRITIC_SCHEMA = _object(
    why=_str(),
    real={"type": "array", "items": {"type": "integer"}},
    confidence={"type": "number"},
)


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= TEXT_CHARS else text[:TEXT_CHARS].rsplit(" ", 1)[0] + " …"


class Audit(CriticNight):
    kind = KIND
    switch = SWITCH
    version = 1
    per_night = PER_NIGHT

    def candidates(self, asked: dict[str, Any]) -> list[Item]:
        found = [
            i
            for i in self.library.all_items()
            if i.kind == ItemKind.ARTWORK
            and i.id not in asked
            and not i.excluded
            and i.look is None
            and bool(i.thumb_url)
            and not against(i, Place.TIDIED)
        ]
        # Favourites, playlists and Discover first (Mateusz 2026-11-11), each
        # part drawn at random.
        cared = self.cared()
        first = [i for i in found if i.id in cared]
        rest = [i for i in found if i.id not in cared]
        picked = random.sample(first, min(len(first), self.per_night))
        room = self.per_night - len(picked)
        return picked + random.sample(rest, min(len(rest), room))

    def facts(self, item: Item) -> str:
        lines = [
            f"Title: {item.title or '(none)'}",
            f"Maker: {item.artist or '?'}" + (f" ({item.artist_bio})" if item.artist_bio else ""),
            f"Date: {item.date_text or item.year or '?'}",
            f"Source: {item.source}" + (f", {item.held_by}" if item.held_by else ""),
        ]
        if item.classification or item.medium:
            lines.append(f"Type: {', '.join(p for p in (item.classification, item.medium) if p)}")
        if item.description:
            lines.append(f"Source's text: {_cut(item.description)}")
        note = self.library.note(item.id, "pl_text")
        data = note.data if note is not None else {}
        if data.get("title"):
            lines.append(f"Polish title: {data['title']}")
        if data.get("full") or data.get("frame"):
            lines.append(f"Polish text: {_cut(str(data.get('full') or data.get('frame')))}")
        return "\n".join(lines)

    def question(self, item: Item) -> dict[str, Any]:
        content = [image_block(self.images, item), {"type": "text", "text": self.facts(item)}]
        return request(
            model=self.judge_model, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=4000
        )

    def claim(self, item: Item, data: dict[str, Any]) -> dict[str, Any] | None:
        problems = [
            {"field": str(p.get("field")), "problem": str(p.get("problem") or "").strip()[:200]}
            for p in data.get("problems") or []
            if isinstance(p, dict) and p.get("field") in FIELDS and p.get("problem")
        ][:MAX_PROBLEMS]
        return {"problems": problems} if problems else None

    def critic_question(self, item: Item, claim: dict[str, Any]) -> dict[str, Any]:
        listed = "\n".join(
            f"{n}. {FIELDS.get(p['field'], p['field'])}: {p['problem']}"
            for n, p in enumerate(claim.get("problems") or [], 1)
        )
        text = f"{self.facts(item)}\n\nProblems found:\n{listed}"
        content = [image_block(self.images, item), {"type": "text", "text": text}]
        return request(
            model=self.critic_model,
            system=CRITIC,
            content=content,
            schema=CRITIC_SCHEMA,
            max_tokens=3000,
        )

    def confirmed(self, item: Item, claim: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        problems = claim.get("problems") or []
        real = {n for n in data.get("real") or [] if isinstance(n, int)}
        kept = [p for n, p in enumerate(problems, 1) if n in real]
        return {"problems": kept} if kept else {}

    def write(self, item: Item, claim: dict[str, Any]) -> bool:
        return True  # nothing changes: the owner's list only
