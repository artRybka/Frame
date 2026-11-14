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
The museums' own works are asked one question alone (Mateusz 2026-11-14,
"Wszędzie (jak Strażnik)"): whether the photograph is a bound object seen
from outside or an empty page, a sketchbook's or album's closed cover, a
binding, a spine, a blank sheet (the National Museums in Kraków and Warsaw
photograph a whole sketchbook, a Chinese printed book, an album by its
cover). Only works whose words name such an object (:func:`bound`), or
that look like one already set aside (``alike``: Szukanie wyglądem's
numbers), are asked: a cover designed by an artist is a work, so the words
alone never decide. What was set aside is listed for the owner, who can
bring any of it back (it is then never asked again).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..library.models import COLLECTIONS, ItemKind
from ..library.verdict import Place, against
from .client import image_block, request
from .critic_night import REST, CriticNight
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
    "blank": "Okładka, oprawa albo pusta karta",
}
#: What a museum's own work can be set aside as: nothing else is asked of it.
MUSEUM_SEEN_AS = ("blank",)
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
    # Tried on 248 works of the catalogue (2026-11-14): of 32 claims the
    # critic confirmed 20, every one a closed cover or an empty sheet; the
    # covers designed by artists (Wyspiański, Mucha) were never claimed.
    "blank": (
        "a book, album, sketchbook, portfolio or folder seen from outside or left empty: its "
        "closed cover, binding, box or spine, or an empty or almost empty page, sheet or board, "
        "with no drawing, painting, print or decoration made as art to look at. A cover or title "
        "page designed by an artist, with a picture or ornament made as art, does not count; nor "
        "does an open page with a picture or text on it"
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

#: The question of a museum's own work.
MUSEUM_SYSTEM = (
    """You check pictures in the catalogue of a home art frame. The frame shows artworks, \
each shown whole by itself. Museums sometimes photograph a whole bound object instead of its \
contents. You get one picture and what its museum says about it.

First write "why": in at most 25 words, what the picture actually shows. Then answer with true \
or false, judging by the picture; titles and types from the source are often wrong. Answer true \
only when it is plainly so; when in doubt, false.

"""
    + "\n".join(f'- "{key}": is the picture {QUESTIONS[key]}?' for key in MUSEUM_SEEN_AS)
    + '\n\nLast, "confidence" from 0 to 1 in your answers.'
)
MUSEUM_SCHEMA = _object(
    why=_str(),
    **{key: {"type": "boolean"} for key in MUSEUM_SEEN_AS},
    confidence={"type": "number"},
)

CRITIC = """You check a claim about one catalogue picture before a home art frame acts on it. \
If the claim is accepted, the picture is left out of the frame's catalogue: a wrong claim \
hides an artwork the owner wanted to see.

Look for evidence against the claim: that the picture is an artwork shown whole by itself, \
fit to hang on the frame. A real painting, drawing, print, poster with an image, illuminated \
page, photograph made as art or a work in its own frame is an artwork. Titles and types from \
the source are often wrong: judge by the picture.

Faint sketches on a page still count as a drawing.

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


#: A museum's words for a bound or many-leaved object, or its back: a
#: sketchbook, album, album amicorum, portfolio, book, volume, binding,
#: cover. Most such works are a page or a cover designed by an artist; the
#: picture decides (some 5 700 of the 117 000 works of 2026-11-13).
_BOUND = re.compile(
    r"\b(sketch ?books?|skizzenb[üu]ch\w*|schetsboek\w*|szkicownik\w*|carnets?|notebooks?|"
    r"notatni\w*|zeszyt\w*|scrapbooks?|albums?|albumy?|albumu|sztambuch\w*|stammb[üu]ch\w*|"
    r"album amicorum|portfolios?|tek[aię]|books?|ksi[ąę]\w*|volumes?|vols?\.|tom\s+[ivx\d]+|"
    r"bound|bindings?|bookbindings?|oprawa|opraw\w*|covers?|okładk\w*|spines?|grzbiet\w*|"
    r"endpapers?|wyklejk\w*|boards|wzornik\w*|pattern ?books?|verso|odwrocie|"
    r"informacje ogólne)\b",
    re.IGNORECASE,
)
#: A museum's number for many leaves at once ("MNK III-r.a-18649/1-12"): the
#: whole object, photographed by its cover.
_LEAVES = re.compile(r"/\s*\d+\s*-\s*\d+\b")


def bound(item: Item) -> bool:
    """A museum's work its words say may be a bound object or a sheet's
    back: asked whether its photograph is only a cover or an empty page."""
    words = f"{item.title}\n{item.classification}\n{item.medium}"
    return bool(_BOUND.search(words) or _LEAVES.search(item.credit or ""))


def _open(item: Item) -> bool:
    """A work the gatekeeper may look at: none it set aside, the owner's
    own pictures, a detail, one the image model drew again for the owner
    (``SharperCopy.restored``: his, kept as he wanted it)."""
    return (
        item.kind == ItemKind.ARTWORK
        and not item.excluded
        and not item.seen_as
        and not item.part_of
        and item.look is None
        and not (item.sharper is not None and item.sharper.restored)
        and bool(item.thumb_url)
        and not against(item, Place.TIDIED)
    )


def asked_by_rules(item: Item) -> bool:
    """A work the gatekeeper looks at: a picture of a gathering source the
    rules let into the catalogue, or a museum's whose words name a bound
    object (:func:`bound`)."""
    if not _open(item):
        return False
    return item.source not in COLLECTIONS or bound(item)


def museum(item: Item) -> bool:
    """A museum's own work: asked only :data:`MUSEUM_SEEN_AS`."""
    return item.source in COLLECTIONS


class Gatekeeper(CriticNight):
    kind = KIND
    switch = SWITCH
    version = 1
    #: About 0.007 cent a work through the Batch API (Haiku 5.5, measured
    #: 2026-11-14): 1000 a night is at most some 2 USD a month, until the
    #: catalogue's backlog (the museums' bound objects among it) is through.
    per_night = 1000
    #: Works set aside as a cover whose look-alikes are asked too, newest.
    ALIKE_SEEDS = 200
    #: Look-alikes asked of each.
    ALIKE_EACH = 40

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        #: The ids of the works that look like a work, nearest first (the
        #: numbers of Szukanie wyglądem, ``Looks.near_ids``; Google is not
        #: asked); none without them.
        self.alike: Callable[[str, int], list[str]] = lambda _id, _limit: []

    def candidates(self, asked: dict[str, Any]) -> list[Item]:
        kept_by_owner = self.kept_by_owner()
        like_cover = self.like_covers()
        found = [
            i
            for i in self.library.all_items()
            if i.id not in asked
            and i.id not in kept_by_owner
            and (asked_by_rules(i) or (i.id in like_cover and _open(i)))
        ]
        # Favourites, playlists and Discover first (Mateusz 2026-11-11), then
        # what the owner keeps or saw, then the museums' bound objects (what
        # he saw in Szukaj, 2026-11-14), then the newest of the catalogue.
        found.sort(key=lambda i: i.added_at or "", reverse=True)
        found.sort(key=lambda i: not (museum(i) and (i.id in like_cover or bound(i))))
        found.sort(key=lambda i: not (not i.pooled or i.favorite or i.show_count > 0))
        cared = self.cared()
        found.sort(key=lambda i: cared.get(i.id, REST))
        return found

    def like_covers(self) -> set[str]:
        """The works that look like those set aside as a cover: a museum's
        bound object its words do not name ("Starannie wydane ilustracje…")."""
        seeds = [w["id"] for w in self.written() if w.get("seen_as") == "blank"]
        found: set[str] = set()
        for seed in seeds[: self.ALIKE_SEEDS]:
            found.update(self.alike(seed, self.ALIKE_EACH))
        return found

    def kept_by_owner(self) -> set[str]:
        return set(self.state().get("kept") or [])

    def question(self, item: Item) -> dict[str, Any]:
        content = [image_block(self.images, item), {"type": "text", "text": facts(item)}]
        system, schema = (MUSEUM_SYSTEM, MUSEUM_SCHEMA) if museum(item) else (SYSTEM, SCHEMA)
        return request(
            model=self.judge_model, system=system, content=content, schema=schema, max_tokens=3000
        )

    def claim(self, item: Item, data: dict[str, Any]) -> dict[str, Any] | None:
        for key in MUSEUM_SEEN_AS if museum(item) else SEEN_AS:
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
        if item.excluded:
            return False
        if museum(item) and claim["seen_as"] not in MUSEUM_SEEN_AS:
            return False  # a museum's own work only as a cover or an empty page
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
