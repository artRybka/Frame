"""The curator of Discover: cards for "Dziś dla Ciebie" that the rules
cannot make (Mateusz 2026-11-06: "odrobina urozmaicenia").

A language model writes recipes, never works: a name, one sentence, terms
of the app's vocabulary and painters of the catalogue. The server keeps
only those it can check (:func:`~frame_server.library.themes.check_proposals`)
and fills them from the catalogue as any card of the week. Two such cards
stand in for two of the week's pairs of terms; each is made again after a
week, or the night after someone opened it. The question goes through the
Batch API at night, for half the price; without a key, with the switch off
or when nothing passes, "Dziś dla Ciebie" is what it was before.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from ..library.artists import is_artist
from ..library.models import ItemKind, PlaylistRules
from ..library.themes import (
    CURATED_DESCRIPTION,
    CURATED_KEY,
    CURATED_NAME,
    GROUPS,
    THEMES,
    WEEKLY_MIN,
    Proposal,
    check_proposals,
    colour_themes,
    curated,
    curated_due,
    curated_history,
    curated_terms,
    for_you,
    occasion,
    put_curated,
    season,
)
from .client import OPUS, AiUnavailable, request

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..library import Library
    from ..night import Night
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "curator"
#: Proposals asked for: more than the cards, since some do not pass.
PROPOSALS = 6
#: Painters of the catalogue shown to the model, most works first.
ARTISTS = 300
#: How long the night waits for the batch's answer, and how often it asks.
WAIT_SECONDS = 3600.0
POLL_SECONDS = 60.0
SEASONS = {"winter": "zima", "spring": "wiosna", "summer": "lato", "autumn": "jesień"}

SYSTEM = f"""\
You are the curator of a Polish home art frame: a colour e-paper screen in \
someone's home that shows public-domain paintings, drawings and prints from \
museums. The app's Discover tab has cards, each a set of works to browse \
and turn into a playlist. Rules already make cards for styles, subjects, \
periods, colours, the artist of the week and pairs like "Landscape: \
impressionism". You add a few cards the rules cannot think of: a thread \
through time or across places, a mood, a motif, a quiet idea a curator \
would hang together on one wall. Examples of the spirit: "Twarze przez dwa \
tysiące lat" (portraits from Fayum to Rembrandt and Sargent), "Arkadia, \
kraina, której nie było" (Puvis de Chavannes, Hubert Robert, Roman \
gardens), "Okna i światło" (interiors with a window).

Each card is a recipe the server fills from the catalogue:
- name: Polish, at most {CURATED_NAME} characters, a title not a description; no \
quotes, no emoji.
- description: one Polish sentence of at most {CURATED_DESCRIPTION} characters, \
usually names of painters or places, ending with a full stop.
- terms: keys from the vocabulary given (copied exactly). Terms of one kind \
are alternatives (period:15c or period:16c), terms of different kinds must \
all fit (a portrait AND from the 17th century).
- artists: painters exactly as the catalogue list spells them. A work fits \
when it is by one of them (and fits the terms).
Use at least two terms, or one term and two painters, or three painters. \
Cards must not repeat the existing cards or the ones made lately (given). \
Prefer ideas with many works in the catalogue: counts are given. Vary the \
cards: different times, places and moods; antiquity and Byzantium may \
appear now and then, not in every card. Mind the season and occasions of \
the coming days. Write natural, correct Polish (as a museum would).
Never use manuscripts, photographs, sculpture or decorative arts: the \
vocabulary given has none of them.
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "terms": {"type": "array", "items": {"type": "string"}},
                    "artists": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "description", "terms", "artists"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}


def catalogue_artists(library: Library) -> list[tuple[str, int]]:
    """The catalogue's painters with at least a few works, most first."""
    items = library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]))[1]
    counts = Counter(i.artist for i in items if is_artist(i.artist))
    return [(a, n) for a, n in counts.most_common(ARTISTS) if n >= 3]


def _occasions(day: date) -> list[str]:
    found = []
    for n in range(8):
        when = day + timedelta(days=n)
        if (o := occasion(when)) is not None:
            found.append(f"{when.isoformat()}: {o.name}")
    return found


def prompt(library: Library, day: date, taste: list[str], wanted: int) -> str:
    """What the model is told: the vocabulary with counts, the catalogue's
    painters, the cards there are, those made lately, taste and the days
    ahead."""
    index = library.term_index()
    vocabulary = [
        f"{t.key} | {t.name} | {index.term_count(t.key)}"
        for t in curated_terms()
        if index.term_count(t.key) >= WEEKLY_MIN
    ]
    artists = [f"{a} | {n}" for a, n in catalogue_artists(library)]
    shown = [*THEMES, *for_you(library, day), *colour_themes(library, day), *curated(library)]
    cards = sorted({f"{t.name} ({t.group})" for t in shown}, key=lambda c: c.casefold())
    lines = [
        f"Date: {day.isoformat()}, season: {SEASONS[season(day)]}.",
        "Occasions in the coming week: " + ("; ".join(_occasions(day)) or "none") + ".",
        f"Make {PROPOSALS} cards; the best {wanted} will be shown.",
        "",
        "Painters the owner likes most (inspiration, not a rule): "
        + (", ".join(taste[:12]) or "not known yet")
        + ".",
        "",
        "Vocabulary (key | Polish name | works in the catalogue):",
        *vocabulary,
        "",
        "Catalogue painters (name | works):",
        *artists,
        "",
        "Existing cards (group order: " + ", ".join(GROUPS) + "):",
        *cards,
        "",
        "Cards made lately (do not repeat):",
        *(curated_history(library)[-40:] or ["none"]),
    ]
    return "\n".join(lines)


class Curator:
    """Orders the curator's cards at night and puts in what passes."""

    def __init__(
        self,
        library: Library,
        claude: Claude,
        config: AiConfigStore,
        taste: Callable[[], list[str]] = list,
    ) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        self.taste = taste

    def _state(self) -> dict[str, Any]:
        return dict(self.library.get_state(CURATED_KEY, {}) or {})

    def _set_order(self, order: dict[str, Any] | None) -> None:
        state = self._state()
        if order is None:
            state.pop("order", None)
        else:
            state["order"] = order
        self.library.set_state(CURATED_KEY, state)

    def params(self, day: date, wanted: int) -> dict[str, Any]:
        text = prompt(self.library, day, self.taste(), wanted)
        return request(
            model=OPUS,
            system=SYSTEM,
            content=[{"type": "text", "text": text}],
            schema=SCHEMA,
            max_tokens=16000,
            effort="medium",
        )

    def order(self, day: date) -> bool:
        """The cards due for ``day`` asked of the Batch API, unless an order
        is under way or nothing is due. Whether one was sent."""
        if not self.config.enabled(KIND) or self._state().get("order"):
            return False
        wanted = curated_due(self.library, day)
        if not wanted:
            return False
        try:
            batch = self.claude.create_batch(
                [{"custom_id": f"{KIND}-{day.isoformat()}", "params": self.params(day, wanted)}]
            )
        except AiUnavailable as err:
            log.info("curator: not asked (%s)", err)
            return False
        except Exception:
            log.exception("curator: the order failed")
            return False
        self._set_order({"batch": batch, "day": day.isoformat()})
        log.info("curator: %d cards ordered for %s (batch %s)", wanted, day, batch)
        return True

    def collect(self) -> bool | None:
        """The order's answer put in, once the batch is done: True when it
        was, False while it runs, None without an order."""
        order = self._state().get("order")
        if not order:
            return None
        try:
            ended, _ = self.claude.batch_ended(order["batch"])
            if not ended:
                return False
            messages = [m for _, m in self.claude.batch_results(order["batch"])]
        except Exception:
            log.exception("curator: the batch could not be read")
            return False
        self._set_order(None)
        message = next((m for m in messages if m is not None), None)
        if message is None:
            log.warning("curator: the batch had no answer")
            return True
        answer = self.claude.answer(KIND, OPUS, message, batch=True)
        self.apply(answer.data or {}, date.fromisoformat(order["day"]))
        return True

    def apply(self, data: dict[str, Any], day: date) -> list[str]:
        """The answer's cards that pass, in place of those due. Their names."""
        proposals = [
            Proposal(
                name=str(c.get("name") or ""),
                description=str(c.get("description") or ""),
                terms=tuple(str(t) for t in c.get("terms") or []),
                artists=tuple(str(a) for a in c.get("artists") or []),
            )
            for c in data.get("cards") or []
            if isinstance(c, dict)
        ]
        artists = [a for a, _ in catalogue_artists(self.library)]
        found = check_proposals(self.library, proposals, artists, day)
        wanted = curated_due(self.library, day)
        if found and wanted:
            put_curated(self.library, found[:wanted], day)
        log.info("curator: %d of %d proposals passed", len(found), len(proposals))
        return [t.name for t in found[:wanted]]

    def at_night(self, night: Night) -> None:
        """An answer from the night before put in, then tomorrow's cards
        ordered (the night runs after midnight: "tomorrow" is the day that
        has begun) and waited for while the night lasts."""
        self.collect()
        if not self.order(date.today()):
            return
        waited = 0.0
        while waited < WAIT_SECONDS and night.quiet():
            if not night.sleep(POLL_SECONDS):
                return
            waited += POLL_SECONDS
            if self.collect() is not False:
                return
