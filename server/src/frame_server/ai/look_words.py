"""Words for how works look, as the museums can be asked them (Mateusz
2026-11-13, card: "Hasła i ocena wyglądem").

No museum searches by how a work looks: "mglisty poranek nad wodą" finds
nothing in a catalogue that knows titles, subjects and techniques. Haiku
turns the description into a few short searches of the words a catalogue
uses for such pictures ("fog river", "misty morning", "lake mist"), in
Polish, English and French; the museums are asked them in turn, and what
they bring is judged by how it looks (``looks.Looks.judge``). Each
description is asked once and remembered.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from ..library.vocabulary import fold
from ..library.wording import Wording
from .client import HAIKU, request

if TYPE_CHECKING:
    from ..library import Library
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "look_words"
STATE_KEY = "look_words"
#: Descriptions remembered with their searches (in the library's state).
REMEMBERED = 500
#: Searches made of one description, at most.
MOST = 3

SYSTEM = """\
Someone describes, in a Polish art app, how the pictures they want look \
("mglisty poranek nad wodą", "ciemne wnętrze ze świecą", "czerwone maki w \
polu"). Museums' collection search engines know only titles, subjects, \
techniques and keywords, not how a picture looks.

Give up to three short searches (one to three words each) that a museum \
catalogue would answer with such pictures: the subjects and things they \
show, the words their titles use ("fog river", "misty morning", "lake \
mist"). Plain words, no quotes, no colours alone, no artists unless the \
description names one. The likeliest first.

For each: polish (as a Polish museum's catalogue words it), english, french.
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "searches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "polish": {"type": "string"},
                    "english": {"type": "string"},
                    "french": {"type": "string"},
                },
                "required": ["polish", "english", "french"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["searches"],
    "additionalProperties": False,
}


def _key(text: str) -> str:
    return fold(" ".join(text.split()))


def _clean(text: object) -> str:
    return " ".join(str(text or "").replace('"', " ").split())


class LookWords:
    """The museum searches for a description of how works look."""

    def __init__(self, library: Library, claude: Claude, config: AiConfigStore) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        self._lock = threading.Lock()
        #: One question at a time for each description (the museums' streams
        #: all ask for it at once).
        self._asking: dict[str, threading.Lock] = {}
        kept = library.get_state(STATE_KEY, {}) or {}
        self._known: OrderedDict[str, list[dict[str, str]]] = OrderedDict(kept)

    def searches(self, text: str) -> list[Wording]:
        """Up to :data:`MOST` searches for ``text``, each in Polish with its
        English and French; none without Claude."""
        key = _key(text)
        if not key:
            return []
        with self._lock:
            known = self._known.get(key)
            asking = self._asking.setdefault(key, threading.Lock())
        if known is None:
            with asking:  # another museum's stream may have asked meanwhile
                with self._lock:
                    known = self._known.get(key)
                if known is None:
                    known = self._ask(text, key)
        return [Wording(s["pl"], s["en"], s["fr"]) for s in known]

    def _ask(self, text: str, key: str) -> list[dict[str, str]]:
        if not self.config.enabled(KIND):
            return []
        params = request(
            model=HAIKU,
            system=SYSTEM,
            content=[{"type": "text", "text": " ".join(text.split())[:300]}],
            schema=SCHEMA,
            max_tokens=600,
        )
        try:
            data = self.claude.ask(KIND, params).data
        except Exception as err:
            log.warning("searches for the look %r failed: %s", text, err)
            return []
        found: list[dict[str, str]] = []
        for one in (data or {}).get("searches") or []:
            if not isinstance(one, dict):
                continue
            english = _clean(one.get("english"))
            polish = _clean(one.get("polish")) or english
            if english and all(fold(english) != fold(f["en"]) for f in found):
                found.append({"pl": polish, "en": english, "fr": _clean(one.get("french"))})
        found = found[:MOST]
        log.info("look %r -> %s", text, [f["en"] for f in found])
        with self._lock:
            self._known[key] = found
            while len(self._known) > REMEMBERED:
                self._known.popitem(last=False)
            saved = dict(self._known)
        if found:
            self.library.set_state(STATE_KEY, saved)
        return found
