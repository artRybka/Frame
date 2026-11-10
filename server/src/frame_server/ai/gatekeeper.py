"""The catalogue's gatekeeper: what a picture from a source that gathers
pictures really is (Mateusz 2026-11-10, "K1").

Commons, Europeana, Openverse and WikiArt carry anything their providers
call art: stamps as still lifes, typed proclamations as posters, old
black-and-white photographs of paintings, photographs of a gallery's wall.
The rules in :mod:`..library.vocabulary` leave out what their words give
away, each written after one was found. What no word gives away the
picture does: at night Haiku looks at the works such sources brought into
the catalogue and says what each one is; a work it would leave out goes to
the critic (Haiku again, looking for evidence that it is an artwork shown
whole), and only what the critic confirms is set aside (``Item.seen_as``).
The museums' own works are never asked about. What was set aside is listed
for the owner, who can bring any of it back (it is then never asked again).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..library.models import COLLECTIONS, ItemKind
from ..library.vocabulary import set_aside
from .client import image_block, request
from .critic_night import CriticNight
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import Item

KIND = "gatekeeper"
SWITCH = "gatekeeper"

#: What a picture can be set aside as, most telling first, with the name
#: the app shows. (``Item.seen_as`` keeps the key.)
SEEN_AS = {
    "postal": "Znaczek, banknot albo koperta",
    "text": "Strona z tekstem albo dokument",
    "room": "Zdjęcie sali albo ściany z dziełem",
    "grey_copy": "Czarno-białe zdjęcie obrazu",
    "not_art": "Nie dzieło sztuki albo pusty obraz",
}
#: The judge's question for each, as a yes or no.
QUESTIONS = {
    "postal": "a postage stamp, a banknote, a coin, an envelope or the back of a postcard",
    "text": (
        "mostly text: a page of a book, newspaper or magazine, a document, a letter, a title "
        "page, a catalogue card, a notice or poster made only of words"
    ),
    "room": (
        "a photograph of a room, a wall, an exhibition or a stand in which the artwork takes up "
        "less than about half the picture (a picture frame alone around the artwork does not count)"
    ),
    "grey_copy": (
        "a black-and-white or one-colour photograph of a painting that was made in colour (a "
        "drawing, print, grisaille or photograph made as art in black and white does not count)"
    ),
    "not_art": (
        "no artwork at all: a blank, damaged, unreadable or placeholder image, or an ordinary "
        "snapshot of people, a street or a building"
    ),
}

SYSTEM = (
    """You check pictures entering the catalogue of a home art frame. The frame shows \
artworks: paintings, drawings, prints, watercolours, posters, miniatures, photographs and \
objects made as art, each shown whole by itself. Some sources also carry pictures that are not \
such an artwork. You get one picture and what its source says about it.

First write "why": in at most 25 words, what the picture actually shows. Then answer each \
question with true or false, judging by the picture; titles and types from the source are \
often wrong. Answer true only when it is plainly so; when in doubt, false.

"""
    + "\n".join(f'- "{key}": is the picture {text}?' for key, text in QUESTIONS.items())
    + '\n\nLast, "confidence" from 0 to 1 in your answers.'
)

SCHEMA = _object(
    why=_str(),
    **{key: {"type": "boolean"} for key in QUESTIONS},
    confidence={"type": "number"},
)

CRITIC = """You check a claim about one catalogue picture before a home art frame acts on it. \
If the claim is accepted, the picture is left out of the frame's catalogue: a wrong claim \
hides an artwork the owner wanted to see.

Look for evidence against the claim: that the picture is an artwork shown whole by itself, \
fit to hang on the frame. A real painting, drawing, print, poster with an image, illuminated \
page, photograph made as art or a work in its own frame is an artwork. Titles and types from \
the source are often wrong: judge by the picture.

"confirm" only when the claim is plainly true; otherwise "reject". Answer with "why" in at \
most 20 words first, then "verdict" and "confidence" from 0 to 1."""

CRITIC_SCHEMA = _object(
    why=_str(),
    verdict={"type": "string", "enum": ["confirm", "reject"]},
    confidence={"type": "number"},
)


def facts(item: Item) -> str:
    lines = [
        f"Title: {item.title or '(none)'}",
        f"Maker: {item.artist or '?'}",
        f"Date: {item.date_text or item.year or '?'}",
        f"Source: {item.source}",
    ]
    if item.classification:
        lines.append(f"Type: {item.classification}")
    if item.medium:
        lines.append(f"Medium: {item.medium}")
    if item.credit or item.museum:
        lines.append(f"Provider: {item.credit or item.museum}")
    return "\n".join(lines)


def asked_by_rules(item: Item) -> bool:
    """A work the gatekeeper looks at: a picture of a gathering source the
    rules let into the catalogue."""
    return (
        item.kind == ItemKind.ARTWORK
        and item.source not in COLLECTIONS
        and not item.excluded
        and not item.seen_as
        and not item.part_of
        and item.look is None
        and bool(item.thumb_url)
        and not set_aside(item)
    )


class Gatekeeper(CriticNight):
    kind = KIND
    switch = SWITCH
    version = 1
    #: About 0.01 cent a work through the Batch API: 200 a night is at most
    #: some 0.6 USD a month, until the catalogue's backlog is through.
    per_night = 200

    def candidates(self, asked: dict[str, Any]) -> list[Item]:
        kept_by_owner = self.kept_by_owner()
        found = [
            i
            for i in self.library.all_items()
            if i.id not in asked and i.id not in kept_by_owner and asked_by_rules(i)
        ]
        # What the owner keeps or saw first, then the newest of the catalogue.
        found.sort(key=lambda i: i.added_at or "", reverse=True)
        found.sort(key=lambda i: not (not i.pooled or i.favorite or i.show_count > 0))
        return found

    def kept_by_owner(self) -> set[str]:
        return set(self.state().get("kept") or [])

    def question(self, item: Item) -> dict[str, Any]:
        content = [image_block(self.images, item), {"type": "text", "text": facts(item)}]
        return request(
            model=self.judge_model, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=3000
        )

    def claim(self, item: Item, data: dict[str, Any]) -> dict[str, Any] | None:
        for key in SEEN_AS:
            if data.get(key) is True:
                return {"seen_as": key, "why": str(data.get("why") or "")[:300]}
        return None

    def critic_question(self, item: Item, claim: dict[str, Any]) -> dict[str, Any]:
        key = str(claim.get("seen_as") or "")
        text = f"{facts(item)}\n\nThe claim: the picture is {QUESTIONS.get(key, key)}."
        content = [image_block(self.images, item), {"type": "text", "text": text}]
        return request(
            model=self.critic_model,
            system=CRITIC,
            content=content,
            schema=CRITIC_SCHEMA,
            max_tokens=3000,
        )

    def confirmed(self, item: Item, claim: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        if data.get("verdict") != "confirm" or claim.get("seen_as") not in SEEN_AS:
            return {}
        return {**claim, "critic": str(data.get("why") or "")[:300]}

    def write(self, item: Item, claim: dict[str, Any]) -> bool:
        if item.source in COLLECTIONS or item.excluded:
            return False  # a museum's own work is never set aside
        return self.library.update(item.id, seen_as=claim["seen_as"]) is not None

    def bring_back(self, item_id: str) -> bool:
        """The owner's "Przywróć": the work in the catalogue again, never
        asked about again."""
        item = self.library.get(item_id)
        if item is None:
            return False
        self.library.update(item_id, seen_as="")
        self.forget_written(item_id)
        state = self.state()
        state["kept"] = sorted({*(state.get("kept") or []), item_id})
        self._save(state)
        return True
