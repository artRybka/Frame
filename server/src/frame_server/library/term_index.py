"""What the search field suggests while typing, counted fast.

``/api/terms`` used to ask the whole catalogue a dozen times for every key
pressed (each artist, each term, the words): seconds on a NAS with tens of
thousands of works, and the questions of the letters typed before kept the
processor busy after the app had moved on. :class:`TermIndex` sorts out once
which works a search can find, the words in their texts and their work: a
term is then looked for only in the works with a word starting like one of
its words, typed words in plain strings, and counts of terms are kept until
the catalogue changes.
"""

from __future__ import annotations

import re
import threading
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from .artists import ArtistNames, is_artist
from .models import MINE, Item, PlaylistRules
from .phrases import has_phrase, quote
from .phrases import words as phrase_words
from .vocabulary import (
    OBJECT_CATEGORIES,
    STYLE_ARTISTS,
    Term,
    fold,
    in_style_years,
    is_copy,
    is_postal,
    object_category,
    term,
    term_matches,
    text_of,
)

_WORD = re.compile(r"\w+")


@dataclass(frozen=True, slots=True)
class _Entry:
    item: Item
    work: int | None  # its group in Works: copies of one work count once


def searchable(item: Item, spare: set[str]) -> bool:
    """``item`` is one a search for a term or words can find (``query`` with
    such rules: see ``repo.Library.query`` and ``repo.matches``)."""
    return not (
        item.id in spare
        or item.look is not None
        or item.excluded
        or (item.pooled and is_copy(item))
        or object_category(item) is not None
        or is_postal(item)
    )


class TermIndex:
    """The catalogue as searches see it, at one moment (``version``)."""

    def __init__(
        self,
        items: Iterable[Item],
        spare: set[str],
        groups: dict[str, int],
        version: int,
        query: Callable[[PlaylistRules], int],
    ) -> None:
        """``query``: how many works the catalogue has for rules, for terms
        that change which works a search can find (sculpture, "Moje");
        ``spare`` and ``groups`` as ``Works.spare`` and ``Works.group_index``
        tell them."""
        self.version = version
        self._query = query
        self._entries: list[_Entry] = []
        #: The words of the works' texts (vocabulary.text_of), in lower case:
        #: which works have each.
        self._words: dict[str, list[int]] = {}
        #: The same for the words of their artists' names.
        self._artist_words: dict[str, list[int]] = {}
        #: The terms works were given (Item.terms): which works have each.
        self._given: dict[str, list[int]] = {}
        by_artist: dict[str, set[object]] = {}
        #: Keywords (the model's, in English and Polish) and the museums'
        #: subjects: folded phrase -> its spellings and works.
        by_phrase: dict[str, tuple[Counter[str], set[object]]] = {}
        for item in items:
            if not searchable(item, spare):
                continue
            n = len(self._entries)
            entry = _Entry(item, groups.get(item.id))
            self._entries.append(entry)
            for word in set(_WORD.findall(text_of(item).lower())):
                self._words.setdefault(word, []).append(n)
            for word in set(_WORD.findall(item.artist.lower())):
                self._artist_words.setdefault(word, []).append(n)
            for key in item.terms:
                self._given.setdefault(key, []).append(n)
            if item.artist and is_artist(item.artist):
                works_of = by_artist.setdefault(item.artist, set())
                works_of.add(entry.work if entry.work is not None else item.id)
            for phrase in {p.strip() for p in (*item.keywords, *item.subjects) if p.strip()}:
                spellings, works_with = by_phrase.setdefault(fold(phrase), (Counter(), set()))
                spellings[phrase] += 1
                works_with.add(entry.work if entry.work is not None else item.id)
        self._sorted_words = sorted(self._words)
        #: Who is who among the artists: one row for Rembrandt, not four.
        self.names = ArtistNames(by_artist)
        people: dict[str, tuple[list[str], set[object]]] = {}
        for name, found in by_artist.items():
            shown = self.names.shown(name)
            written, works_of_person = people.setdefault(shown, ([], set()))
            written.append(fold(name))
            works_of_person |= found
        #: (each spelling folded, the name shown, it folded, how many works),
        #: most works first.
        self._artists = sorted(
            (
                (tuple(written), name, fold(name), len(found))
                for name, (written, found) in people.items()
            ),
            key=lambda a: (-a[3], a[1]),
        )
        #: (folded phrase, its words, the commonest spelling, how many
        #: works), most works first.
        self._phrases = sorted(
            (
                (folded, folded.split(), spellings.most_common(1)[0][0], len(found))
                for folded, (spellings, found) in by_phrase.items()
            ),
            key=lambda p: (-p[3], p[0]),
        )
        #: (a word of a phrase, the phrase's place above), in order.
        self._phrase_words = sorted(
            (word, n) for n, phrase in enumerate(self._phrases) for word in set(phrase[1])
        )
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._entries)

    def artists(self, text: str, limit: int = 5) -> list[tuple[str, int]]:
        """Artists whose name has ``text`` in it, most works first; one
        artist once, under the name :class:`ArtistNames` shows."""
        wanted = fold(text.strip())
        if not wanted:
            return []
        # The people of that name first, then those only some museum's
        # spelling has it in ("Roeloffzen & Hübner (mentioned on object)"
        # for "van gogh", Mateusz 2026-11-09).
        named: list[tuple[str, int]] = []
        spelt: list[tuple[str, int]] = []
        for spellings, name, folded_name, count in self._artists:
            if wanted in folded_name:
                named.append((name, count))
                if len(named) == limit:
                    break
            elif len(spelt) < limit and any(wanted in folded for folded in spellings):
                spelt.append((name, count))
        return (named + spelt)[:limit]

    def phrases(self, text: str, limit: int = 4) -> list[str]:
        """Keywords and subjects of the works ("wielka fala", "Mount Fuji")
        that start like ``text`` or have a word starting so; those starting
        so first, then those of the most works."""
        wanted = fold(text.strip())
        if len(wanted) < 2:
            return []
        first = wanted.split()[0]
        found: set[int] = set()
        at = bisect_left(self._phrase_words, (first,))
        while at < len(self._phrase_words) and self._phrase_words[at][0].startswith(first):
            found.add(self._phrase_words[at][1])
            at += 1
        starts: list[str] = []
        inside: list[str] = []
        for n in sorted(found):
            folded, _, spelling, _ = self._phrases[n]
            if folded == wanted:
                continue  # the typed words' own row says it
            if folded.startswith(wanted):
                starts.append(spelling)
            elif f" {wanted}" in f" {folded}":
                inside.append(spelling)
            if len(starts) == limit:
                break
        return (starts + inside)[:limit]

    def term_count(self, key: str) -> int:
        """How many works ``query(PlaylistRules(terms=[key]))`` finds."""
        with self._lock:
            if key in self._counts:
                return self._counts[key]
        found = term(key)
        if found is None or key in OBJECT_CATEGORIES or key in MINE:
            # They change which works are searched: asked as they are.
            count = self._query(PlaylistRules(terms=[key]))
        else:
            sure, maybe = self._found_by_words(found)
            checked = (n for n in maybe - sure if term_matches(found, self._entries[n].item))
            fits = (*sure, *checked)
            if found.kind == "style":  # and made in its years (matches_terms)
                fits = tuple(n for n in fits if in_style_years(self._entries[n].item, [key]))
            count = self._works(self._entries[n] for n in fits)
        with self._lock:
            self._counts[key] = count
        return count

    def _found_by_words(self, found: Term) -> tuple[set[int], set[int]]:
        """Works ``found`` fits for sure, and those it may fit (to be checked
        with ``term_matches``). A term looked for in the text wants one of
        its words at the start of a word there (``Term.pattern``): a plain
        word ("sea", "sea*") settles it, one with more in it ("still life",
        "ukiyo-e") narrows it down to works with a word starting like it."""
        everything = set(range(len(self._entries)))
        textual = (
            found.kind != "technique"
            and found.year_from is None
            and found.year_to is None
            and found.pattern is not None
            # A style's painters fit it whatever the text (STYLE_ARTISTS).
            and found.key not in STYLE_ARTISTS
        )
        if not textual:
            return set(), everything
        sure = set(self._given.get(found.key, ()))
        maybe: set[int] = set()
        for word in (w.lower() for w in found.words):
            stem = word.removesuffix("*")
            plain = _WORD.fullmatch(stem) is not None
            start = _WORD.match(stem)
            if start is None:
                return sure, everything
            for have in self._starting(start.group()):
                if not plain:
                    maybe.update(self._words[have])
                elif word.endswith("*") or have in (stem, stem + "s", stem + "es"):
                    sure.update(self._words[have])
        return sure, maybe

    def _starting(self, prefix: str) -> Iterator[str]:
        """The texts' words that start with ``prefix``."""
        at = bisect_left(self._sorted_words, prefix)
        while at < len(self._sorted_words) and self._sorted_words[at].startswith(prefix):
            yield self._sorted_words[at]
            at += 1

    def word_count(self, words: str) -> int:
        """How many works ``words`` as one chip finds: a phrase when there
        are several (:mod:`.phrases`)."""
        wanted = words.casefold().split()
        if not wanted or any(_WORD.search(w) is None for w in wanted):
            return self._query(PlaylistRules(query=quote([words])))
        # A word is in the text where each of its runs of letters is inside
        # one of the text's words; with more than letters in it ("o'keeffe")
        # the text itself tells.
        found: set[int] | None = None
        for word in wanted:
            have = set.intersection(*(self._containing(run) for run in _WORD.findall(word)))
            found = have if found is None else found & have
        assert found is not None
        if odd := [w for w in wanted if _WORD.fullmatch(w) is None]:
            found = {n for n in found if all(w in self._haystack(n) for w in odd)}
        if len(wanted) > 1:
            phrase = phrase_words(words)
            found = {n for n in found if has_phrase(phrase, phrase_words(self._haystack(n)))}
        return self._works(self._entries[n] for n in found)

    def _containing(self, run: str) -> set[int]:
        """Works with a word in their text or artist's name that has ``run``
        in it."""
        found: set[int] = set()
        for words in (self._words, self._artist_words):
            for word, have in words.items():
                if run in word:
                    found.update(have)
        return found

    def _haystack(self, n: int) -> str:
        """What ``repo.matches`` looks for typed words in."""
        item = self._entries[n].item
        return f"{text_of(item)} {item.artist}".casefold()

    @staticmethod
    def _works(entries: Iterable[_Entry]) -> int:
        """How many works ``entries`` are: copies of one work count once
        (as ``Works.once`` keeps them)."""
        groups: set[int] = set()
        alone = 0
        for entry in entries:
            if entry.work is None:
                alone += 1
            else:
                groups.add(entry.work)
        return len(groups) + alone
