"""What the search field suggests while typing, counted fast.

The artists, the works' keywords and the vocabulary's terms that fit what is
typed, each with how many works the catalogue's search finds for it. The
counts are the search's own answers (``Library.query``, quick with the
:class:`.search_index.SearchIndex`), remembered while the catalogue stays
as it is: a suggestion says exactly what picking it shows (2026-11-09: "97"
for vermeer showed 114 works). Who is who among the artists
(:class:`.artists.ArtistNames`) is worked out when the index is made.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass

from .artists import ArtistNames, is_artist
from .models import PlaylistRules
from .phrases import fold as phrase_fold
from .phrases import has_phrase, quote
from .search_index import SearchIndex
from .vocabulary import fold

#: Words a title may start with that nobody types ("The Starry Night").
ARTICLES = (
    "the ",
    "a ",
    "an ",
    "la ",
    "le ",
    "les ",
    "l'",
    "der ",
    "die ",
    "das ",
    "de ",
    "het ",
    "el ",
    "il ",
    "lo ",
)


#: Counts of the whole catalogue going on at once, for every index.
COUNTING = 2
_counting = threading.BoundedSemaphore(COUNTING)


@dataclass(frozen=True)
class TitleHit:
    """A work whose title has the words typed."""

    title: str
    artist: str
    item_id: str
    #: The words are the title (without "The"), or its start when two words
    #: or more: Return picks the title.
    exact: bool


class TermIndex:
    """The catalogue's artists and phrases at one moment (``version``), with
    counts asked of the search."""

    def __init__(
        self,
        index: SearchIndex,
        by_artist: Mapping[str, Set[int]],
        version: int,
        query: Callable[[PlaylistRules], int],
        ids: Mapping[str, str] | None = None,
        labels: Mapping[str, str] | None = None,
        titles: Sequence[tuple[str, str, str, str]] = (),
    ) -> None:
        """``by_artist``: each artist's name as the catalogue spells it, with
        its works (``SearchIndex.by_artist``); ``query``: how many works the
        catalogue has for rules; ``ids`` and ``labels``: who Wikidata says
        they are (:class:`ArtistNames`)."""
        self.version = version
        self._index = index
        self._query = query
        artists = {name: works for name, works in by_artist.items() if is_artist(name)}
        #: Who is who among the artists: one row for Rembrandt, not four.
        self.names = ArtistNames(artists, ids, labels)
        people: dict[str, tuple[list[str], set[int]]] = {}
        for name, works in artists.items():
            written, works_of = people.setdefault(self.names.shown(name), ([], set()))
            written.append(fold(name))
            works_of |= works
        #: (each spelling folded, the name shown, it folded, about how many
        #: works), most works first.
        self._artists = sorted(
            ((tuple(w), name, fold(name), len(found)) for name, (w, found) in people.items()),
            key=lambda a: (-a[3], a[1]),
        )
        self._counts: dict[tuple[str, str], int] = {}
        #: Counts under way, set when done (or failed: asked again).
        self._running: dict[tuple[str, str], threading.Event] = {}
        self._lock = threading.Lock()
        #: The works' titles (``Library._titles``): folded, as written,
        #: the artist, the work's id.
        self._titles = list(titles)
        self._titled: dict[tuple[str, ...], list[TitleHit]] = {}

    def __len__(self) -> int:
        return len(self._index)

    def _count(self, kind: str, key: str, rules: PlaylistRules) -> int:
        """One count once: an asker of a count under way waits for it, and
        at most :data:`COUNTING` counts go through the catalogue at a time
        (22-40 threads counted the whole catalogue at once while words were
        typed in Szukaj, and the event loop stood for up to 36 s with them,
        2026-11-13)."""
        while True:
            with self._lock:
                known = self._counts.get((kind, key))
                if known is not None:
                    return known
                running = self._running.get((kind, key))
                if running is None:
                    running = self._running[(kind, key)] = threading.Event()
                    break
            running.wait()
        try:
            with _counting:
                count = self._query(rules)
            with self._lock:
                self._counts[(kind, key)] = count
            return count
        finally:
            with self._lock:
                self._running.pop((kind, key), None)
            running.set()

    def artists(self, text: str, limit: int = 5) -> list[tuple[str, int]]:
        """Artists whose name has ``text`` in it, most works first; one
        artist once, under the name :class:`ArtistNames` shows."""
        wanted = fold(text.strip())
        if not wanted:
            return []
        # The people of that name first, then those only some museum's
        # spelling has it in ("Roeloffzen & Hübner (mentioned on object)"
        # for "van gogh", Mateusz 2026-11-09).
        named: list[str] = []
        spelt: list[str] = []
        for spellings, name, folded_name, _ in self._artists:
            if wanted in folded_name:
                named.append(name)
                if len(named) == limit * 2:
                    break
            elif len(spelt) < limit * 2 and any(wanted in folded for folded in spellings):
                spelt.append(name)
        found: list[tuple[str, int]] = []
        for group in (named, spelt):
            counted = [(n, self.artist_count(n)) for n in group]
            found += sorted((c for c in counted if c[1] > 0), key=lambda c: (-c[1], c[0]))
        return found[:limit]

    def artist_count(self, name: str) -> int:
        """How many works the artist's chip finds."""
        return self._count("artist", name, PlaylistRules(artists=[name]))

    def phrases(self, text: str, limit: int = 4) -> list[str]:
        """Keywords and subjects of the works ("wielka fala", "Mount Fuji")
        that start like ``text`` or have a word starting so; those starting
        so first, then those of the most works."""
        return self._index.phrases(text, limit)

    def term_count(self, key: str) -> int:
        """How many works ``query(PlaylistRules(terms=[key]))`` finds."""
        return self._count("term", key, PlaylistRules(terms=[key]))

    def word_count(self, words: str) -> int:
        """How many works ``words`` as one chip finds: a phrase when there
        are several (:mod:`.phrases`)."""
        return self._count("words", words, PlaylistRules(query=quote([words])))

    def titles(self, forms: Sequence[str], limit: int = 3) -> list[TitleHit]:
        """Works whose title has the words typed in one of ``forms`` (as
        typed, as the museums were asked them): the title itself first,
        then those it starts, then the rest, the shortest first; each work
        once (Mateusz 2026-11-13: "szukanie po tytule dzieła")."""
        wanted = tuple(dict.fromkeys(w for w in (phrase_fold(f).strip() for f in forms) if w))
        if not wanted or len(wanted[0]) < 3:
            return []
        with self._lock:
            kept = self._titled.get(wanted)
        if kept is not None:
            return kept[:limit]
        ranked: dict[str, tuple[tuple[int, int], TitleHit]] = {}
        for folded, title, artist, item_id in self._titles:
            for words in wanted:
                # At a word's start, so that a title shows while it is typed.
                at_start = (" " + words) in (" " + folded)
                if not at_start and not has_phrase(words, folded, folded=True):
                    continue
                bare = next((folded[len(a) :] for a in ARTICLES if folded.startswith(a)), folded)
                several = " " in words
                if words in (folded, bare):
                    rank = 0
                elif bare.startswith(words + " ") or folded.startswith(words + " "):
                    rank = 1 if several else 2
                else:
                    rank = 3
                key = (rank, len(folded))
                hit = TitleHit(title, artist, item_id, exact=rank <= 1)
                if item_id not in ranked or key < ranked[item_id][0]:
                    ranked[item_id] = (key, hit)
                break
        found = [hit for _, hit in sorted(ranked.values(), key=lambda r: r[0])][:10]
        with self._lock:
            if len(self._titled) > 500:
                self._titled.clear()
            self._titled[wanted] = found
        return found[:limit]
