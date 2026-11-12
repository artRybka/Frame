"""Szukaj by a sentence: what it asks for, as the search's own choices
(Mateusz 2026-11-10, "A1").

"Spokojne zimowe pejzaże z wodą o zmierzchu, raczej XIX wiek" is no word
any museum or the catalogue knows. Haiku reads it once and answers in the
app's terms: the vocabulary's styles, subjects, periods and techniques,
years, colours and the Tonacja's sides, artists, and a few plain words for
what no term says. The server keeps only what it knows (an artist under
the catalogue's own spelling when it has them), and the app puts it in as
the search's chips, each one the owner can take away. Answers are kept
for a while: the same sentence costs nothing the second time.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..library.colors import COLOR_FAMILIES, GROUNDS, LEVELS, TONE_GROUPS
from ..library.vocabulary import TERMS, fold
from .client import HAIKU, AiUnavailable, request
from .daily import _object, _str

if TYPE_CHECKING:
    from ..library import Library
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "sentence"
#: Sentences remembered with their answers.
REMEMBERED = 300
#: At most this many of each kind of choice.
MAX_TERMS = 5
MAX_ARTISTS = 3
MAX_WORDS = 2
MAX_COLOURS = 3
#: A sentence this long at most is read.
MAX_CHARS = 300

FAMILY_NAMES = {
    "red": "czerwony",
    "orange": "pomarańczowy",
    "yellow": "żółty",
    "green": "zielony",
    "teal": "turkusowy",
    "blue": "niebieski",
    "purple": "fioletowy",
    "pink": "różowy",
    "brown": "brązowy",
    "cream": "beżowy",
    "black": "czarny",
    "gray": "szary",
    "white": "biały",
}
TONE_NAMES = {
    "warm": "ciepłe",
    "neutral": "neutralne",
    "cool": "chłodne",
    "vivid": "żywe",
    "moderate": "umiarkowane",
    "muted": "stonowane",
    "colorful": "kolorowe",
    "monochrome": "jednobarwne",
    "dark": "ciemne",
    "medium": "średnie",
    "light": "jasne",
}
LEVEL_NAMES = {
    "accent": "akcent (mała, żywa część; nigdy dla cream, black, gray)",
    "clear": "wyraźnie obecny (co najmniej)",
    "much": "dużo (co najmniej)",
    "most": "przeważa",
}
TONES = [side for group in TONE_GROUPS for side in group]
TERM_KEYS = [t.key for t in TERMS if t.kind != "tag"]


def _terms_list() -> str:
    lines = []
    for kind in ("style", "subject", "period", "technique"):
        terms = [t for t in TERMS if t.kind == kind]
        lines.append(f"{kind}:")
        lines += [f"- {t.key}: {t.name}" for t in terms]
    return "\n".join(lines)


SYSTEM = (
    """You turn a sentence typed into the search of a home art frame's app (mostly in Polish) \
into the app's own search choices. Every choice narrows the search: choose only what the \
sentence plainly asks for, never more, and prefer fewer choices.

First write "reading": in Polish, at most 15 words, what the person is looking for. Then:
- "terms": keys from the list below (styles, subjects, periods, techniques). A subject only \
when it is what the pictures should show; a period or style only when the sentence names \
one or plainly means one.
- "year_from", "year_to": years when the sentence names a time not covered by a period key \
("XIX wiek" is 1801-1900, "około 1900" is 1890-1910); 0 for none.
- "colours": colours the pictures should have, each a "family" and a "level".
- "tones": the pictures' overall tone, from the list below.
- "artists": artists named in the sentence, as their usual full names.
- "words": at most 2 short Polish phrases for things the sentence asks for that no key above \
says (an object, a place, a name), each as a museum's catalogue would word it; none when the \
keys say it all. Never words for moods, colours or times you already chose.

"""
    + _terms_list()
    + "\n\nColour families: "
    + ", ".join(f"{k} ({v})" for k, v in FAMILY_NAMES.items())
    + "\nColour levels: "
    + ", ".join(f"{k} ({v})" for k, v in LEVEL_NAMES.items())
    + "\nTones: "
    + ", ".join(f"{k} ({v})" for k, v in TONE_NAMES.items())
)

SCHEMA = _object(
    reading=_str(),
    terms={"type": "array", "items": {"type": "string", "enum": TERM_KEYS}},
    year_from={"type": "integer"},
    year_to={"type": "integer"},
    colours={
        "type": "array",
        "items": _object(
            family={"type": "string", "enum": list(COLOR_FAMILIES)},
            level={"type": "string", "enum": list(LEVELS)},
        ),
    },
    tones={"type": "array", "items": {"type": "string", "enum": TONES}},
    artists={"type": "array", "items": _str()},
    words={"type": "array", "items": _str()},
)


@dataclass
class Reading:
    """What a sentence asks for: the app's chips ("kind", "key", "name")."""

    reading: str = ""
    hits: list[dict[str, str]] = field(default_factory=list)
    cost_usd: float = 0.0


def _year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 0 < year <= 2100 else None


class Sentence:
    def __init__(self, library: Library, claude: Claude, config: AiConfigStore) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        self._kept: OrderedDict[str, Reading] = OrderedDict()
        self._lock = threading.Lock()

    def enabled(self) -> bool:
        return self.config.enabled(KIND)

    def understand(self, text: str) -> Reading:
        """The chips ``text`` asks for. Raises ``AiUnavailable`` without a
        key, with the switch off or over this month's limit."""
        sentence = " ".join(text.split())[:MAX_CHARS]
        key = fold(sentence)
        with self._lock:
            kept = self._kept.get(key)
            if kept is not None:
                self._kept.move_to_end(key)
                return kept
        if not self.enabled():
            raise AiUnavailable("Szukaj zdaniem is off or there is no API key")
        params = request(
            model=HAIKU,
            system=SYSTEM,
            content=[{"type": "text", "text": f"The sentence: {sentence}"}],
            schema=SCHEMA,
            max_tokens=2000,
        )
        answer = self.claude.ask(KIND, params)
        found = self.read(answer.data or {})
        found.cost_usd = answer.cost_usd
        with self._lock:
            self._kept[key] = found
            while len(self._kept) > REMEMBERED:
                self._kept.popitem(last=False)
        return found

    def read(self, data: dict[str, Any]) -> Reading:
        """The answer as chips the app knows, what the server cannot check left out."""
        names = {t.key: t.name for t in TERMS}
        hits: list[dict[str, str]] = []

        def add(kind: str, key: str, name: str) -> None:
            if key and not any(h["kind"] == kind and h["key"] == key for h in hits):
                hits.append({"kind": kind, "key": key, "name": name})

        for artist in [str(a).strip() for a in data.get("artists") or []][:MAX_ARTISTS]:
            if artist:
                own = self._artist(artist)
                add("artist", own, own)
        for key in [str(k) for k in data.get("terms") or []][:MAX_TERMS]:
            if key in names:
                kind = key.split(":", 1)[0]
                add("period" if kind == "years" else kind, key, names[key])
        start, end = _year(data.get("year_from")), _year(data.get("year_to"))
        if start or end:
            if start and end and start > end:
                start, end = end, start
            span = f"{start or ''}-{end or ''}"
            add("period", f"years:{span}", span.replace("-", "–"))
        for colour in (data.get("colours") or [])[:MAX_COLOURS]:
            if not isinstance(colour, dict):
                continue
            family, level = colour.get("family"), colour.get("level")
            if family in FAMILY_NAMES and level in LEVELS:
                # Grey, black and beige are never an accent: no work has one.
                if level == "accent" and family in GROUNDS and family != "white":
                    level = "clear"
                add("color", f"{family}@{level}", FAMILY_NAMES[family])
        for side in data.get("tones") or []:
            if side in TONE_NAMES:
                add("color", f"tone:{side}", TONE_NAMES[side])
        for word in [" ".join(str(w).split()) for w in data.get("words") or []][:MAX_WORDS]:
            if word:
                add("word", word, word)
        return Reading(reading=str(data.get("reading") or "").strip()[:200], hits=hits)

    def _artist(self, name: str) -> str:
        """The catalogue's own spelling of the artist, when it has them."""
        try:
            index = self.library.term_index()
        except Exception:  # the index is being made: the name as given
            return name
        surname = name.split()[-1]
        for found, _ in index.artists(surname, limit=5):
            if fold(surname) in fold(found) and fold(name.split()[0]) in fold(found):
                return found
        best = index.artists(name, limit=1)
        return best[0][0] if best else name
