"""The catalogue's search index: which works a search can be, found in a
moment, kept up to date with every change.

``Library.query`` used to look at every one of the catalogue's works for
each search, each page and each chip: 1-6 s on the NAS with 79 000 works,
tens of seconds while anything else ran (Mateusz, 2026-11-09: "to co mamy w
katalogu musi się wyszukiwać błyskawicznie"). :class:`SearchIndex` knows
the words of every work (folded: lower case, no accents), the words of its
artist, the searches that found it, and remembers, once asked, which works
each term, colour, period, place or source fits. A search is then the works
all its parts allow, and only those are checked in full (``repo.matches``):
the index only ever narrows, the answer is the same as before.

It changes with the library (:meth:`add`, :meth:`remove`): a work changed
gets a new entry and its old one is left dead, so nothing is taken out of
the long lists; :meth:`dead_share` tells when it is time to make it anew.
"""

from __future__ import annotations

import re
import threading
from array import array
from bisect import bisect_left, insort
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable, Iterator

from .artists import known_names, name_key
from .colors import has_colours
from .given_names import given
from .models import MINE, Item, PlaylistRules
from .phrases import fold, parsed
from .phrases import words as phrase_words
from .places import known_places
from .vocabulary import (
    HIGHLIGHT,
    OBJECT_CATEGORIES,
    STYLE_ARTISTS,
    Term,
    grouped,
    in_style_years,
    name_words,
    term,
    term_matches,
    text_of,
)

_WORD = re.compile(r"\w+")
#: Letters of a word the vocabulary is bucketed by.
_BUCKET = 2
#: Remembered answers of parts of searches (a term, colours, a place).
ATOMS = 400
#: Phrases (keywords, subjects) the suggestions offer: at most this many
#: words to a phrase.
PHRASE_WORDS = 6
#: Letters a phrase's word may have past the typed word's stem ("straży"
#: for "straż"): as :mod:`.phrases` checks them.
_ENDING = "aeiouy"


def item_text(item: Item) -> str:
    """What typed words are looked for in: the work's title, artist,
    technique, culture, styles, subjects and keywords; not the museum's
    description, which mentions what isn't there ("La berceuse" was to hang
    "between two paintings of sunflowers", a portrait's painter "worked in
    Venice", Polish "most" in "the most famous"; Mateusz 2026-11-13: the
    words in Szukaj and playlists alike)."""
    return " ".join(
        [
            item.title,
            item.artist,
            item.medium,
            item.classification,
            item.culture,
            *item.styles,
            *item.subjects,
            *item.keywords,
        ]
    )


def _stem(word: str) -> str:
    stem = word.rstrip(_ENDING)
    return stem if len(stem) >= 3 else word


def _in_years(item: Item, low: int | None, high: int | None) -> bool:
    year = item.year
    return year is not None and (low is None or year >= low) and (high is None or year <= high)


def _discard[K](kept: dict[K, set[int]], key: K, n: int) -> None:
    entries = kept.get(key)
    if entries is not None:
        entries.discard(n)
        if not entries:
            del kept[key]


class SearchIndex:
    """The catalogue as searches see it, kept up to date."""

    def __init__(self, items: Iterable[Item] = ()) -> None:
        self._lock = threading.RLock()
        #: Each entry's work (None: changed or taken out since).
        self._items: list[Item | None] = []
        #: Each work's current entry.
        self._entry: dict[str, int] = {}
        #: Folded words of the works' texts -> their entries, in order (4 bytes
        #: each: 79 000 works have some 5 million).
        self._words: dict[str, array[int]] = {}
        #: The same words, sorted in buckets by their first letters, for
        #: the words starting like a typed one.
        self._buckets: dict[str, list[str]] = {}
        #: Folded words of the artists' names -> entries.
        self._artist_words: dict[str, array[int]] = {}
        #: Each artist as written -> entries (who is who: ArtistNames).
        self.by_artist: dict[str, set[int]] = {}
        #: Each artist's name words (``artists.name_key``) -> entries: the
        #: same person under every spelling the catalogue has.
        self._by_key: dict[frozenset[str], set[int]] = {}
        #: The vocabulary's terms the works are tagged with -> entries.
        self._tagged: dict[str, set[int]] = {}
        #: Museum searches (``Item.found_for``) -> entries they found.
        self._found: dict[str, array[int]] = {}
        #: Keywords and subjects, folded -> how many works have each spelling.
        self._phrases: dict[str, dict[str, int]] = {}
        #: Words of those phrases -> the phrases, for the suggestions.
        self._phrase_words: dict[str, set[str]] = {}
        #: Parts of searches asked before -> their entries, kept up to date.
        self._atoms: OrderedDict[Hashable, tuple[Callable[[Item], bool], set[int]]] = OrderedDict()
        self._dead = 0
        #: Goes up with every change.
        self.version = 0
        for item in items:
            self._add(item)

    # -- changes ---------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entry)

    def dead_share(self) -> float:
        """How much of the index is entries of works changed since."""
        return self._dead / max(1, len(self._items))

    def add(self, item: Item) -> None:
        """``item`` new or changed."""
        with self._lock:
            old = self._entry.get(item.id)
            if old is not None:
                if self._items[old] is item:
                    return
                self._kill(old)
            self._add(item)
            self.version += 1

    def remove(self, item_id: str) -> None:
        with self._lock:
            old = self._entry.pop(item_id, None)
            if old is not None:
                self._kill(old)
                self.version += 1

    def _kill(self, n: int) -> None:
        item = self._items[n]
        self._items[n] = None
        self._dead += 1
        if item is None:
            return
        if item.artist:
            _discard(self.by_artist, item.artist, n)
            _discard(self._by_key, name_key(item.artist), n)
        for key in item.terms:
            _discard(self._tagged, key, n)
        for folded, spelling in self._phrases_of(item):
            spellings = self._phrases.get(folded)
            if spellings is not None:
                spellings[spelling] = spellings.get(spelling, 1) - 1
        for _, entries in self._atoms.values():
            entries.discard(n)

    def _add(self, item: Item) -> None:
        n = len(self._items)
        self._items.append(item)
        self._entry[item.id] = n
        # The description's words too: terms are still looked for in it
        # (``vocabulary.text_of``), the typed words no longer (``item_text``).
        for word in set(_WORD.findall(fold(f"{item_text(item)} {item.description}"))):
            have = self._words.get(word)
            if have is None:
                self._words[word] = array("i", (n,))
                insort(self._buckets.setdefault(word[:_BUCKET], []), word)
            else:
                have.append(n)
        # First names in their Polish form, which every spelling of them
        # shares (``given_names``: "Alphonse Mucha" is "Alfons Mucha").
        for word in given(frozenset(_WORD.findall(fold(item.artist)))):
            self._artist_words.setdefault(word, array("i")).append(n)
        if item.artist:
            self.by_artist.setdefault(item.artist, set()).add(n)
            self._by_key.setdefault(name_key(item.artist), set()).add(n)
        for key in set(item.found_for):
            self._found.setdefault(key, array("i")).append(n)
        for key in item.terms:
            self._tagged.setdefault(key, set()).add(n)
        for folded, spelling in self._phrases_of(item):
            spellings = self._phrases.get(folded)
            if spellings is None:
                spellings = self._phrases[folded] = {}
                for word in folded.split():
                    self._phrase_words.setdefault(word, set()).add(folded)
            spellings[spelling] = spellings.get(spelling, 0) + 1
        for fits, entries in self._atoms.values():
            if fits(item):
                entries.add(n)

    @staticmethod
    def _phrases_of(item: Item) -> set[tuple[str, str]]:
        found = set()
        for phrase in (*item.keywords, *item.subjects):
            spelling = " ".join(phrase.split())
            folded = fold(spelling)
            if spelling and len(folded.split()) <= PHRASE_WORDS:
                found.add((folded, spelling))
        return found

    # -- what the works are ----------------------------------------------------

    def items(self, entries: Iterable[int]) -> Iterator[Item]:
        """The works of ``entries`` still there (each once)."""
        for n in sorted(set(entries)):
            item = self._items[n]
            if item is not None:
                yield item

    def all_entries(self) -> set[int]:
        with self._lock:
            return set(self._entry.values())

    # -- words -----------------------------------------------------------------

    def _starting(self, prefix: str) -> Iterator[str]:
        """The texts' words that start with ``prefix``."""
        if len(prefix) >= _BUCKET:
            buckets = [self._buckets.get(prefix[:_BUCKET], [])]
        else:
            buckets = [b for k, b in self._buckets.items() if k.startswith(prefix)]
        for words in buckets:
            at = bisect_left(words, prefix)
            while at < len(words) and words[at].startswith(prefix):
                yield words[at]
                at += 1

    def _with_word_starting(self, prefix: str) -> set[int]:
        found: set[int] = set()
        for word in self._starting(prefix):
            found.update(self._words[word])
        return found

    def with_words(self, query: str, said: list[list[str]] | None = None) -> set[int]:
        """Entries that may have every token of ``query`` (:func:`repo.has_words`):
        a word starting like each of a token's runs of letters, a word starting
        like each word's stem of a phrase. ``said``: each token's forms
        (:func:`repo.said_as`), one of which will do."""
        forms = said if said is not None else [[token] for token, _ in parsed(query)]
        found: set[int] | None = None
        with self._lock:
            for token_forms in forms:
                have: set[int] = set()
                for form in token_forms:
                    have |= self._with_form(form)
                found = have if found is None else found & have
                if not found:
                    return set()
            return found if found is not None else self.all_entries()

    def _with_form(self, form: str) -> set[int]:
        """Entries that may have ``form``, one token (under the lock)."""
        form = form.strip()
        # A phrase (as typed in quotes, or translated) by its words' stems.
        phrase = " " in form
        parts = [_stem(w) for w in phrase_words(form)] if phrase else _WORD.findall(fold(form))
        found: set[int] | None = None
        for part in parts:
            have = self._with_word_starting(part)
            found = have if found is None else found & have
            if not found:
                return set()
        return found if found is not None else self.all_entries()

    # -- artists ---------------------------------------------------------------

    def artists(self) -> dict[str, frozenset[int]]:
        """Each artist as the catalogue writes them, with their entries."""
        with self._lock:
            return {name: frozenset(entries) for name, entries in self.by_artist.items()}

    def by_artists(self, wanted: list[str]) -> set[int]:
        """Entries that may be by one of ``wanted`` (``artists.made_by``):
        their artist has all the words of the name, or is the same person
        under another spelling."""
        names = known_names()
        found: set[int] = set()
        with self._lock:
            for name in wanted:
                found |= self._by_artist_words(name)
                person = names.person(name)
                if person is not None:
                    for key in names.keys_of(person):
                        found |= self._by_key.get(key, set())
        return found

    def found_by(self, key: str) -> set[int]:
        """Entries a museums' search ``key`` found."""
        return set(self._found.get(key, ()))

    # -- parts of searches -------------------------------------------------------

    def atom(
        self,
        key: Hashable,
        fits: Callable[[Item], bool],
        within: Callable[[], set[int] | None] | None = None,
    ) -> set[int]:
        """Entries ``fits``: worked out once over every work (without
        holding the index up), then kept up to date as works come and
        change. ``within``: the entries that may fit, when known."""
        with self._lock:
            kept = self._atoms.get(key)
            if kept is not None:
                self._atoms.move_to_end(key)
                return set(kept[1])
            items, upto = self._items, len(self._items)
            pool = within() if within is not None else None
        looked_at = range(upto) if pool is None else (n for n in pool if n < upto)
        entries = {n for n in looked_at if (i := items[n]) is not None and fits(i)}
        with self._lock:
            kept = self._atoms.get(key)
            if kept is None:
                # Works that came, changed or went meanwhile.
                for n in range(upto, len(items)):
                    if (i := items[n]) is not None and fits(i):
                        entries.add(n)
                entries = {n for n in entries if items[n] is not None}
                kept = self._atoms[key] = (fits, entries)
                while len(self._atoms) > ATOMS:
                    self._atoms.popitem(last=False)
            self._atoms.move_to_end(key)
            return set(kept[1])

    def term_entries(self, key: str) -> set[int]:
        """Entries the term ``key`` fits (``term_matches``)."""
        found = term(key)
        if found is None:
            return self.all_entries()
        return self.atom(
            ("term", key),
            lambda i: term_matches(found, i, text_of(i)),
            lambda: self._may_be(found),
        )

    def _may_be(self, found: Term) -> set[int] | None:
        """Entries the term ``found`` may fit (with the lock held): tagged
        with it, with a word starting like one of its words, by one of its
        style's painters; None when that tells nothing (a period, a kind of
        object, the highlights)."""
        if (
            found.key in OBJECT_CATEGORIES
            or found.key == HIGHLIGHT
            or found.year_from is not None
            or found.year_to is not None
            or not found.words
        ):
            return None
        pool = set(self._tagged.get(found.key, ()))
        for word in found.words:
            # Its pattern finds the word at a word's start, any case.
            runs = _WORD.findall(fold(word.rstrip("*")))
            if not runs:
                return None
            pool |= self._with_word_starting(runs[0])
        for artist in STYLE_ARTISTS.get(found.key, ()):
            pool |= self._by_artist_words(artist)
        return pool

    def _by_artist_words(self, name: str) -> set[int]:
        """Entries whose artist has every word of ``name`` (a first name in
        any of its languages)."""
        words = given(name_words(name))
        if not words:
            return set()
        lists = sorted((self._artist_words.get(w, array("i")) for w in words), key=len)
        have = set(lists[0])
        for more in lists[1:]:
            have &= set(more)
            if not have:
                break
        return have

    def candidates(
        self,
        rules: PlaylistRules,
        hearts: frozenset[str] | None,
        said: list[list[str]] | None = None,
    ) -> set[int] | None:
        """Entries that may fit ``rules`` (all that do are among them), or
        None when nothing in them narrows the catalogue down. ``hearts``:
        the works liked, for "Ulubione"; ``said``: the words' forms
        (:func:`repo.said_as`)."""
        parts: list[Callable[[], set[int]]] = []
        if rules.query.strip():
            parts.append(lambda: self.with_words(rules.query, said))
        if rules.artists:
            parts.append(lambda: self.by_artists(rules.artists))
        terms = [t for t in rules.terms if t not in MINE]
        # A style's years are checked for every "style:" asked for, as
        # ``vocabulary.matches_terms`` does.
        styles = tuple(sorted(t for t in terms if t.startswith("style:")))
        for kind, of_kind in grouped(terms).items():
            parts.append(
                self._terms_part([t.key for t in of_kind], styles if kind == "style" else ())
            )
        if rules.colors:
            colours = list(rules.colors)
            parts.append(
                self._atom_part(
                    ("colours", tuple(colours)),
                    lambda i: has_colours(i.color_tags, colours, i.color_shares),
                )
            )
        if rules.year_from is not None or rules.year_to is not None:
            low, high = rules.year_from, rules.year_to
            parts.append(self._atom_part(("year", low, high), lambda i: _in_years(i, low, high)))
        if rules.places:
            places = known_places()
            wanted = frozenset(places.canon(p) for p in rules.places)
            # Museums learnt later may place works anew.
            parts.append(
                self._atom_part(("places", id(places), wanted), lambda i: i.held_at in wanted)
            )
        if rules.sources:
            sources = frozenset(rules.sources)
            parts.append(self._atom_part(("sources", sources), lambda i: i.source in sources))
        if rules.kinds:
            kinds = frozenset(rules.kinds)
            parts.append(self._atom_part(("kinds", kinds), lambda i: i.kind in kinds))
        if hearts is not None and rules.favorites_only:
            liked = hearts
            parts.append(lambda: {n for i in liked if (n := self._entry.get(i)) is not None})
        if not parts:
            return None
        found: set[int] | None = None
        for part in parts:
            have = part()
            found = have if found is None else found & have
            if not found:
                break
        assert found is not None
        key = rules.search_key()
        if key:
            # Works the museums' search for these choices found fit them
            # as it judged them (``repo.matches``).
            found |= self.found_by(key)
        return found

    def _atom_part(self, key: Hashable, fits: Callable[[Item], bool]) -> Callable[[], set[int]]:
        return lambda: self.atom(key, fits)

    def _terms_part(self, keys: list[str], styles: tuple[str, ...]) -> Callable[[], set[int]]:
        """Entries one of ``keys`` fits; of a style's years too."""

        def part() -> set[int]:
            found: set[int] = set()
            for key in keys:
                found |= self.term_entries(key)
            if styles:
                found &= self.atom(("years", styles), lambda i: in_style_years(i, styles))
            return found

        return part

    # -- suggestions -------------------------------------------------------------

    def phrases(self, text: str, limit: int = 4) -> list[str]:
        """Keywords and subjects of the works ("wielka fala", "Mount Fuji")
        that start like ``text`` or have a word starting so; those starting
        so first, then those of the most works."""
        wanted = fold(text.strip())
        if len(wanted) < 2:
            return []
        first = wanted.split()[0]
        with self._lock:
            found = {p for w, ps in self._phrase_words.items() if w.startswith(first) for p in ps}
            rows = []
            for folded in found:
                if folded == wanted:
                    continue  # the typed words' own row says it
                spellings = self._phrases[folded]
                works = sum(spellings.values())
                if works <= 0:
                    continue
                starts = folded.startswith(wanted)
                if not starts and f" {wanted}" not in f" {folded}":
                    continue
                spelling = max(spellings, key=lambda s: spellings[s])
                rows.append((not starts, -works, folded, spelling))
        rows.sort()
        return [r[3] for r in rows[:limit]]
