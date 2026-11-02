"""Polish words typed in Szukaj, translated for the museums abroad.

Most museums search their own catalogue in English (Paris Musées in
French), so "gitara" finds nothing there and "guitar" a lot. What the
library already knows is used first: the Polish names of the app's styles
and subjects, and the model's keywords of described works (each Polish tag
beside its English one). Anything else is asked of Haiku once and
remembered; without a key, or with the owner's switch off, only what the
library knows is translated. The Polish museums always get the words as
typed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter, OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import TYPE_CHECKING, Any

from ..library.vocabulary import TERMS, fold
from ..library.wording import Wording
from .client import HAIKU, request
from .keywords import KIND as KEYWORDS
from .keywords import MAX_TAGS, _clean

if TYPE_CHECKING:
    from ..library import Library
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "search_words"
STATE_KEY = "search_words"
#: Answers kept (in the library's state, so a restart asks nothing again).
REMEMBERED = 2000
#: Longer texts are not translated: a pasted title, not words.
MAX_CHARS = 80
#: How often the library's words are gathered again, at most (seconds).
LOCAL_EVERY = 600.0

SYSTEM = """\
You translate what someone typed into the search box of a Polish art app, \
for museums' collection search engines.

The text is usually one or a few Polish words for what a picture shows \
("gitara", "stara kobieta", "zimowy pejzaż", "martwa natura z kwiatami"). \
It may also be an artist's name, a title, words already in English or another \
language, or a word still being typed.

Answer:
- polish: true when the text has Polish words to translate; false when it is \
only a name, already English, another language, or not a word.
- english: the text as an English museum catalogue would word it: plain lower \
case words, nouns in the singular ("guitar", "old woman", "winter landscape", \
"still life with flowers"). Names of people stay as they are; places as \
English writes them ("Wenecja" -> "Venice"). No quotes, no added words, no \
alternatives.
- french: the same for a French catalogue ("guitare", "vieille femme").

When polish is false, english and french repeat the text unchanged.
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "polish": {"type": "boolean"},
        "english": {"type": "string"},
        "french": {"type": "string"},
    },
    "required": ["polish", "english", "french"],
    "additionalProperties": False,
}


def _key(text: str) -> str:
    return fold(" ".join(text.split()))


def _vocabulary() -> dict[str, str]:
    """The Polish names of the app's styles, subjects and techniques, with
    the English word museums are asked ("Wnętrza", "wnętrza" -> "interior")."""
    words: dict[str, str] = {}
    for term in TERMS:
        if not term.query:
            continue
        for name in (term.name, term.name.split(" i ")[0]):
            words.setdefault(fold(name), term.query)
    return words


def _keyword_pairs(notes: dict[str, Any]) -> dict[str, str]:
    """Each Polish keyword of the described works with its English one
    (the model writes them in the same order), the commonest if several."""
    votes: dict[str, Counter[str]] = {}
    for note in notes.values():
        pl = _clean(note.data.get("tags_pl"), MAX_TAGS)
        en = _clean(note.data.get("tags_en"), MAX_TAGS)
        if len(pl) != len(en):  # one list lost a word: the pairs would slip
            continue
        for polish, english in zip(pl, en, strict=True):
            if fold(polish) != fold(english):
                votes.setdefault(fold(polish), Counter())[english] += 1
    return {word: counts.most_common(1)[0][0] for word, counts in votes.items()}


class SearchWords:
    def __init__(self, library: Library, claude: Claude, config: AiConfigStore) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        self._lock = threading.Lock()
        self._asking: dict[str, Future[Wording | None]] = {}
        self._pool = ThreadPoolExecutor(2, thread_name_prefix="search-words")
        self._known: OrderedDict[str, dict[str, str]] = OrderedDict(
            library.get_state(STATE_KEY, {}) or {}
        )
        self._local: dict[str, str] = {}
        self._local_at = -LOCAL_EVERY
        self._local_version = -1

    def wording(self, text: str, wait: float = 5.0) -> Wording:
        """``text`` for each museum's language. The model's answer is waited
        for at most ``wait`` seconds; one that comes later serves the next
        search."""
        text = " ".join(text.split())
        key = _key(text)
        if not key or len(text) > MAX_CHARS or any(c in text for c in '"=&:'):
            return Wording(text)
        with self._lock:
            known = self._known.get(key)
        if known is not None:
            return Wording(text, known.get("en", ""), known.get("fr", ""))
        local = self._from_library(key)
        if local:
            return Wording(text, en=local)
        if not self.config.enabled(KIND):
            return Wording(text)
        future = self._ask(text, key)
        try:
            return future.result(timeout=wait) or Wording(text)
        except FutureTimeout:
            log.info("translating %r took longer than %.1f s: as typed for now", text, wait)
            return Wording(text)
        except Exception:
            return Wording(text)

    # -- what the library knows ---------------------------------------------

    def _from_library(self, key: str) -> str:
        """The English of ``key`` from the library's own words: the whole
        text, or every word of it; "" when something is not known."""
        words = self._library_words()
        if key in words:
            return words[key]
        parts = key.split()
        if len(parts) > 1 and all(p in words for p in parts):
            return " ".join(words[p] for p in parts)
        return ""

    def _library_words(self) -> dict[str, str]:
        now = time.monotonic()
        version = self.library.notes_version
        with self._lock:
            fresh = now - self._local_at < LOCAL_EVERY
            if self._local_at >= 0 and (fresh or version == self._local_version):
                return self._local
            self._local_at = now
            self._local_version = version
        try:
            pairs = _keyword_pairs(self.library.notes(KEYWORDS))
        except Exception:
            log.exception("reading the library's keywords failed")
            pairs = {}
        words = {**pairs, **_vocabulary()}
        with self._lock:
            self._local = words
        return words

    # -- the model ----------------------------------------------------------

    def _ask(self, text: str, key: str) -> Future[Wording | None]:
        """The model's answer for ``text``, asked once however many
        museums wait for it."""
        with self._lock:
            future = self._asking.get(key)
            if future is None:
                future = self._asking[key] = self._pool.submit(self._translate, text, key)
        return future

    def _translate(self, text: str, key: str) -> Wording | None:
        try:
            return self._answer(text, key)
        except Exception as err:
            log.warning("translating %r failed: %s", text, err)
            return None
        finally:  # after the answer is remembered: no second question
            with self._lock:
                self._asking.pop(key, None)

    def _answer(self, text: str, key: str) -> Wording | None:
        params = request(
            model=HAIKU,
            system=SYSTEM,
            content=[{"type": "text", "text": text}],
            schema=SCHEMA,
            max_tokens=600,
        )
        data = self.claude.ask(KIND, params).data
        if not data:
            return None
        english = " ".join(str(data.get("english") or "").split())
        french = " ".join(str(data.get("french") or "").split())
        found = {"en": english, "fr": french} if data.get("polish") else {}
        # The same words back: nothing to translate (names, English).
        if fold(english) == key and fold(french) == key:
            found = {}
        self._remember(key, found)
        log.info("search words %r -> %s", text, found or "as typed")
        return Wording(text, found.get("en", ""), found.get("fr", ""))

    def _remember(self, key: str, found: dict[str, str]) -> None:
        with self._lock:
            self._known[key] = found
            self._known.move_to_end(key)
            while len(self._known) > REMEMBERED:
                self._known.popitem(last=False)
            saved = dict(self._known)
        self.library.set_state(STATE_KEY, saved)
