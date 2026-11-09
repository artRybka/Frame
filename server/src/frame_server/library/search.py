"""The museums' search: one for Szukaj (``/discover/search``, its stream)
and for what a smart playlist fetches (:func:`fill`), so that the same
choices find the same works in both (Mateusz, 2026-11-07). Works it finds
remember the search (``Item.found_for``), and the catalogue counts them in
for it as the museum judged them (:func:`repo.matches`)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from .importer import Importer, Job, span
from .models import Item, PlaylistRules
from .museums import PLACES_EUROPEANA, PLACES_WD, Discovery
from .phrases import phrases
from .places import QID, SOURCE_PLACES, known_places
from .repo import matches, said_as, says, search_fits
from .vocabulary import asked_artists, asked_topics, category_fits, museum_kind

#: With colours asked, museum pages of this many works are looked at, until
#: ``limit`` fit, this many pages are seen or this many seconds have passed.
COLOR_PAGE = 24
COLOR_PAGES = 6
COLOR_SECONDS = 15.0
#: With artists asked, museums bring whatever names them (Guillaumin's
#: self-portrait for Van Gogh); this many of their pages are looked at for
#: ``limit`` works by the artists, within ``COLOR_SECONDS``.
ARTIST_PAGES = 3
#: With a phrase typed, museums whose search doesn't keep to phrases bring
#: works with its words anywhere; this many of their pages are looked at for
#: ``limit`` works that have the phrase, within ``COLOR_SECONDS``.
PHRASE_PAGES = 3
#: Works of each museum page that a smart playlist's fetching asks for: the
#: same works, in the same order, as Szukaj's smaller pages.
FILL_PAGE = 24


def searched(rules: PlaylistRules) -> PlaylistRules:
    """What of ``rules`` the museums are asked: the words, artists, terms,
    colours and years (as Szukaj sends them)."""
    return PlaylistRules(
        query=rules.query,
        artists=rules.artists,
        terms=rules.terms,
        colors=rules.colors,
        year_from=rules.year_from,
        year_to=rules.year_to,
    )


def museum_text(rules: PlaylistRules, page: int, words: str | None = None) -> str:
    """What to ask the museums: the words (``words``: as one museum's
    language has them), an artist (one per page, in turns) and the styles
    and subjects."""
    artists = asked_artists(rules.artists, rules.terms)
    artist = artists[(page - 1) % len(artists)] if artists else ""
    topics = asked_topics(rules.artists, artist, rules.terms)
    typed = rules.query.strip() if words is None else words
    return " ".join(w for w in (typed, artist, *topics) if w)


@dataclass(frozen=True)
class MuseumSearch:
    """What the search asks the museums."""

    rules: PlaylistRules
    spec: Discovery
    #: The museums chosen; none means all of them.
    keys: list[str]
    limit: int
    #: Museums left out ("all but Yale"); none chosen, all the others.
    skip: tuple[str, ...] = ()
    #: Places chosen (:mod:`.places`): their own collections are asked, and
    #: Wikidata and Europeana for their works; none, every source.
    places: tuple[str, ...] = ()
    #: Places left out: their works don't come, from whichever source.
    skip_places: tuple[str, ...] = ()

    @classmethod
    def of(
        cls,
        rules: PlaylistRules,
        keys: list[str] | None = None,
        limit: int = 8,
        skip: list[str] | tuple[str, ...] = (),
        places: list[str] | tuple[str, ...] | None = None,
        skip_places: list[str] | tuple[str, ...] | None = None,
    ) -> MuseumSearch:
        """The search for ``rules`` (their museums as ``keys`` and ``skip``,
        their places as ``places`` and ``skip_places``, unless given)."""
        asked = searched(rules)
        start, end = span(asked)
        spec = Discovery(year_from=start, year_to=end, kind=museum_kind(asked.terms))
        known = known_places()
        chosen = rules.places if places is None else places
        left_out = rules.exclude_places if skip_places is None else skip_places
        return cls(
            rules=asked,
            spec=spec,
            keys=list(dict.fromkeys(keys if keys is not None else rules.sources)),
            limit=limit,
            skip=tuple(dict.fromkeys(skip or rules.exclude_sources)),
            places=tuple(dict.fromkeys(known.canon(p) for p in chosen)),
            skip_places=tuple(dict.fromkeys(known.canon(p) for p in left_out)),
        )

    @property
    def key(self) -> str:
        """What the works it finds remember (:meth:`PlaylistRules.search_key`)."""
        return self.rules.search_key()

    def asked(self, offered: list[str], reach: list[str] | None = None) -> list[str]:
        """The museums to ask: those chosen or, none chosen, every one on
        offer; without those left out. Empty when nothing is asked, or every
        museum is left out. ``reach``: the sources that may answer for
        places chosen, those turned off too (``offered`` when not given)."""
        if self.empty:
            return []
        # Keys given: a page further of those the answers named.
        keys = self.keys or (self.place_keys(reach or offered) if self.places else offered)
        skip = set(self.skip) | set(self._sources_left_out())
        return [k for k in keys if k not in skip]

    def place_keys(self, offered: list[str]) -> list[str]:
        """What to ask for the places chosen: a museum's own collection when
        it is on offer; for the others, Wikidata (their works with a picture
        on Commons) and Europeana (works its data providers among them
        brought)."""
        known = known_places()
        keys: list[str] = []
        others: list[str] = []
        for key in self.places:
            place = known.place(key)
            if place is not None and place.source in offered:
                if place.source not in keys:
                    keys.append(place.source)
            elif QID.match(key):
                others.append(key)
        if others and "wmc" in offered:
            keys.append(PLACES_WD + "|".join(others))
        providers = [p for p in others if known.provider(p)]
        if providers and "europeana" in offered:
            keys.append(PLACES_EUROPEANA + "|".join(providers))
        return keys

    def _sources_left_out(self) -> list[str]:
        """Sources every place of which is left out (Yale's two, say): not
        asked at all."""
        known = known_places()
        out: list[str] = []
        for key in self.skip_places:
            place = known.place(key)
            if place is None or not place.source:
                continue
            mine = SOURCE_PLACES.get(place.source, ())
            if mine and all(p in self.skip_places for p in mine) and place.source != "paris":
                out.append(place.source)
        return out

    @property
    def empty(self) -> bool:
        """Nothing asked: chosen museums show what they have, all of them
        nothing; the owner's own works (favourites, playlists) none."""
        if self.rules.asks_mine():
            return True
        start, end = self.spec.year_from, self.spec.year_to
        return (
            not self.keys
            and not self.places
            and not museum_text(self.rules, 1)
            and not self.rules.colors
            and start is None
            and end is None
            and self.spec.kind == "any"
        )

    def fits(self, item: Item) -> bool:
        """A work a museum's search brought for this search: of its years
        and categories, by its artists, and of its periods and tags
        (:func:`search_fits`)."""
        terms = self.rules.terms
        return (
            self.spec.fits(item)
            and category_fits(item, terms)
            and search_fits(item, self.rules)
            and self.in_place(item)
        )

    def in_place(self, item: Item) -> bool:
        """Whether ``item`` is in a place chosen, and in none left out (a
        source of several museums brings the others' works too)."""
        held_at = item.held_at
        if self.places and held_at not in self.places:
            return False
        return not (held_at and held_at in self.skip_places)

    def pages(
        self,
        importer: Importer,
        keys: list[str],
        page: int,
        spare: Callable[[list[Item]], None] | None = None,
    ) -> Iterator[tuple[int, list[Item], list[str], int | None]]:
        """Works of ``keys`` from ``page`` on, a museum page at a time:
        (total, items, museums that failed, the page to ask next). Museums
        don't know colours, so with colours their works are judged by their
        thumbnails, pages deep, until ``limit`` fit or time runs out; with
        artists, a few pages, for the works by them. ``spare`` gets the works
        a page brought that don't fit (another colour, other years, another
        artist): asked for already, they may still do for the catalogue
        (Mateusz 2026-11-07, "szkoda byłoby tracić te odpytania")."""
        rules = self.rules
        colors = rules.colors
        asked = COLOR_PAGE if colors else self.limit
        artists = asked_artists(rules.artists, rules.terms)
        deeper = artists or phrases(rules.query)
        left = COLOR_PAGES if colors else ARTIST_PAGES if deeper else 1
        started = time.monotonic()
        total = fitting = 0
        at: int | None = page
        # The words typed, in each museum's language ("gitara": "guitar"),
        # each phrase quoted where the museum keeps to it.
        named = keys or importer.asked_sources(self.spec.kind)
        words = importer.asked(rules.query, named) if rules.query.strip() else None
        typed = words.texts if words is not None else {}
        said = words.said if words is not None else []
        while at is not None and left > 0:
            text = museum_text(rules, at)
            # Several artists take turns, so each page asks for one of them.
            round_ = (at - 1) // len(artists) + 1 if artists else at
            if text:
                texts = {k: museum_text(rules, at, typed.get(k)) for k in named}
                count, items, failed = importer.search_all(
                    texts, asked, round_, keys, kind=self.spec.kind
                )
            else:
                count, items, failed = importer.discover_all(self.spec, asked, at, keys)
            total = total or count
            # The words checked here too, as typed or translated: most
            # museums find a phrase's words anywhere ("night" in one sentence,
            # "watches" in another) and a name in whatever they think goes
            # with it (ter Borch for "vermeer"); before the colours are judged
            # by thumbnails.
            said_it = [i for i in items if says(i, said)]
            found = [i for i in importer.in_colors(said_it, colors) if self.fits(i)]
            if spare is not None and len(found) < len(items):
                chosen = {i.id for i in found}
                spare([i for i in items if i.id not in chosen])
            # The app lays its grid out by the works' shapes.
            importer.measure(found)
            fitting += len(found)
            # Totals of several artists' searches don't add up page by page.
            done = not items or (not artists and 0 < count <= round_ * asked)
            at = None if done else at + 1
            left -= 1
            yield total, found, failed, at
            if fitting >= self.limit or time.monotonic() - started > COLOR_SECONDS:
                return

    def ask(
        self,
        importer: Importer,
        keys: list[str],
        page: int,
        spare: Callable[[list[Item]], None] | None = None,
    ) -> tuple[int, list[Item], list[str], int | None]:
        """All of :meth:`pages` at once."""
        answers = list(self.pages(importer, keys, page, spare))
        total, _, failed, at = answers[-1]
        return total, [i for _, items, _, _ in answers for i in items], failed, at

    def works(self, importer: Importer, key: str) -> Iterator[Item]:
        """One museum's works for this search, page after page, each
        remembering the search."""
        found = self.key
        at: int | None = 1
        while at is not None:
            following: int | None = None
            for _, items, _, after in self.pages(importer, [key], at):
                following = after
                for item in items:
                    yield item.model_copy(update={"found_for": [*item.found_for, found]})
            at = following


def fill(
    importer: Importer, rules: PlaylistRules, count: int, job: Job, pooled: bool = False
) -> None:
    """Add ``count`` museum works for a smart playlist with ``rules``: what
    Szukaj shows for them, the museums taking turns; works the library has
    already that only the search makes fit count too."""
    offered = importer.sources()
    if rules.sources and not rules.places and not any(s in offered for s in rules.sources):
        return  # only the owner's own sources (photos, albums)
    # Museums chosen are places, asked as their own (``asked``).
    keys = [] if rules.places else [s for s in rules.sources if s in offered]
    search = MuseumSearch.of(rules, keys=keys, limit=FILL_PAGE)
    keys = search.asked(importer.asked_sources(search.spec.kind), importer.reachable())
    job.total = count
    if not keys:
        return
    streams = [search.works(importer, key) for key in keys]
    importer._take(
        streams,
        count,
        job,
        before=lambda item: True,
        after=lambda item: True,
        pooled=pooled,
        terms=rules.terms,
        # The words as the museums were asked them (translated by then).
        fits=lambda item: matches(item, rules, said=said_as(rules.query, importer.library.wording)),
    )
