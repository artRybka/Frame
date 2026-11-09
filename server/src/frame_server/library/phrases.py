"""Words typed in Szukaj as its tokens: each token is one phrase, its words
next to each other in that order ("nocna straż" is not "nocna" somewhere
and "straż" somewhere else), and every further token narrows the search
(Mateusz, 2026-11-09: never "any of them").

``PlaylistRules.query`` keeps them as one text: a phrase of several words
in double quotes, a single word bare (``"nocna straż" portret``). Words
outside quotes are each a token of their own, which is what a query saved
before phrases meant: every word somewhere.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache

_TOKEN = re.compile(r'"([^"]*)"|(\S+)')
_WORD = re.compile(r"\w+")
#: Letters a word ends in that its other forms change ("nocna": "nocnej").
_ENDING = "aeiouy"
#: Letters a word of the text may have beyond the typed word's stem: the
#: plural ("watches"), a Polish case ("straży", "nocnej"), but not another
#: word made from it ("watchman").
EXTRA = 2


def tokens(query: str) -> list[str]:
    """The tokens of ``query``: each quoted phrase, and each word outside
    quotes, in order and once."""
    found: list[str] = []
    for quoted, bare in _TOKEN.findall(query):
        text = " ".join((quoted or bare).replace('"', " ").split())
        if text and text not in found:
            found.append(text)
    return found


def quote(phrases: Iterable[str]) -> str:
    """``phrases`` as one query: several words in quotes, one word bare."""
    out: list[str] = []
    for phrase in phrases:
        text = " ".join(phrase.replace('"', " ").split())
        if text:
            out.append(f'"{text}"' if " " in text else text)
    return " ".join(out)


def fold(text: str) -> str:
    """Lower case without accents (as ``vocabulary.fold``, which this module
    is too low to import)."""
    decomposed = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def words(text: str) -> list[str]:
    """The words of ``text``, folded (lower case, no accents)."""
    return _WORD.findall(fold(text))


@lru_cache(maxsize=256)
def parsed(query: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each token of ``query`` with its folded words (a search checks the
    same query against every work of the catalogue)."""
    return tuple((t, tuple(words(t))) for t in tokens(query))


def phrases(query: str) -> list[str]:
    """The tokens of ``query`` of several words: those checked as phrases
    (one word with a hyphen, "pre-raphaelite", stays a word)."""
    return [t for t in tokens(query) if " " in t]


def _stem(word: str) -> str:
    stem = word.rstrip(_ENDING)
    return stem if len(stem) >= 3 else word


def _same(typed: str, found: str) -> bool:
    """Whether ``found`` is ``typed`` or a form of it."""
    if typed == found:
        return True
    stem = _stem(typed)
    return found.startswith(stem) and len(found) - len(stem) <= EXTRA


def has_phrase(
    phrase: str | list[str] | tuple[str, ...], text: str | list[str] | tuple[str, ...]
) -> bool:
    """Whether ``text`` has ``phrase``: its words next to each other, in
    order, each whole or in another form of it ("nocnej straży" for "nocna
    straż", "night watches" for "night watch"; not "night watchman")."""
    wanted = words(phrase) if isinstance(phrase, str) else phrase
    seen = words(text) if isinstance(text, str) else text
    if not wanted:
        return True
    size = len(wanted)
    for at in range(len(seen) - size + 1):
        if all(_same(w, seen[at + i]) for i, w in enumerate(wanted)):
            return True
    return False


def fts(query: str) -> str:
    """An FTS5 query of ``query``'s tokens, all of which must be there:
    each word quoted, each phrase as a phrase; nothing typed can be read as
    the query language's own."""
    parts = []
    for token in tokens(query):
        found = _WORD.findall(token)
        if found:
            parts.append('"' + " ".join(found) + '"')
    return " ".join(parts)
