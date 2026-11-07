"""The museums' search: one for Szukaj (``/discover/search``, its stream)
and for what a smart playlist fetches (:func:`fill`), so that the same
choices find the same works in both (Mateusz, 2026-11-07). Works it finds
remember the search (``Item.found_for``), and the catalogue counts them in
for it as the museum judged them (:func:`repo.matches`)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass

from .importer import Importer, Job, span
from .models import Item, PlaylistRules
from .museums import Discovery
from .repo import matches, search_fits
from .vocabulary import category_fits, museum_kind, museum_queries

#: With colours asked, museum pages of this many works are looked at, until
#: ``limit`` fit, this many pages are seen or this many seconds have passed.
COLOR_PAGE = 24
COLOR_PAGES = 6
COLOR_SECONDS = 15.0
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
    artist = rules.artists[(page - 1) % len(rules.artists)] if rules.artists else ""
    topics = museum_queries(rules.terms)[:1]
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

    @classmethod
    def of(
        cls,
        rules: PlaylistRules,
        keys: list[str] | None = None,
        limit: int = 8,
        skip: list[str] | tuple[str, ...] = (),
    ) -> MuseumSearch:
        """The search for ``rules`` (their museums as ``keys`` and ``skip``
        unless given)."""
        asked = searched(rules)
        start, end = span(asked)
        spec = Discovery(year_from=start, year_to=end, kind=museum_kind(asked.terms))
        return cls(
            rules=asked,
            spec=spec,
            keys=list(dict.fromkeys(keys if keys is not None else rules.sources)),
            limit=limit,
            skip=tuple(dict.fromkeys(skip or rules.exclude_sources)),
        )

    @property
    def key(self) -> str:
        """What the works it finds remember (:meth:`PlaylistRules.search_key`)."""
        return self.rules.search_key()

    def asked(self, offered: list[str]) -> list[str]:
        """The museums to ask: those chosen or, none chosen, every one on
        offer; without those left out. Empty when nothing is asked, or every
        museum is left out."""
        if self.empty:
            return []
        keys = self.keys or offered
        return [k for k in keys if k not in self.skip]

    @property
    def empty(self) -> bool:
        """Nothing asked: chosen museums show what they have, all of them
        nothing; the owner's own works (favourites, playlists) none."""
        if self.rules.asks_mine():
            return True
        start, end = self.spec.year_from, self.spec.year_to
        return (
            not self.keys
            and not museum_text(self.rules, 1)
            and not self.rules.colors
            and start is None
            and end is None
            and self.spec.kind == "any"
        )

    def fits(self, item: Item) -> bool:
        """A work a museum's search brought for this search: of its years
        and categories, and of its periods and tags (:func:`search_fits`)."""
        terms = self.rules.terms
        return self.spec.fits(item) and category_fits(item, terms) and search_fits(item, self.rules)

    def pages(
        self, importer: Importer, keys: list[str], page: int
    ) -> Iterator[tuple[int, list[Item], list[str], int | None]]:
        """Works of ``keys`` from ``page`` on, a museum page at a time:
        (total, items, museums that failed, the page to ask next). Museums
        don't know colours, so with colours their works are judged by their
        thumbnails, pages deep, until ``limit`` fit or time runs out."""
        rules = self.rules
        colors = rules.colors
        asked = COLOR_PAGE if colors else self.limit
        left = COLOR_PAGES if colors else 1
        started = time.monotonic()
        total = fitting = 0
        at: int | None = page
        # The words typed, in each museum's language ("gitara": "guitar").
        named = keys or importer.asked_sources(self.spec.kind)
        typed = importer.typed(rules.query, named) if rules.query.strip() else {}
        while at is not None and left > 0:
            text = museum_text(rules, at)
            # Several artists take turns, so each page asks for one of them.
            round_ = (at - 1) // len(rules.artists) + 1 if rules.artists else at
            if text:
                texts = {k: museum_text(rules, at, typed.get(k)) for k in named}
                count, items, failed = importer.search_all(
                    texts, asked, round_, keys, kind=self.spec.kind
                )
            else:
                count, items, failed = importer.discover_all(self.spec, asked, at, keys)
            total = total or count
            found = [i for i in importer.in_colors(items, colors) if self.fits(i)]
            # The app lays its grid out by the works' shapes.
            importer.measure(found)
            fitting += len(found)
            # Totals of several artists' searches don't add up page by page.
            done = not items or (not rules.artists and 0 < count <= round_ * asked)
            at = None if done else at + 1
            left -= 1
            yield total, found, failed, at
            if fitting >= self.limit or time.monotonic() - started > COLOR_SECONDS:
                return

    def ask(
        self, importer: Importer, keys: list[str], page: int
    ) -> tuple[int, list[Item], list[str], int | None]:
        """All of :meth:`pages` at once."""
        answers = list(self.pages(importer, keys, page))
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
    if rules.sources and not any(s in offered for s in rules.sources):
        return  # only the owner's own sources (photos, albums)
    search = MuseumSearch.of(
        rules, keys=[s for s in rules.sources if s in offered], limit=FILL_PAGE
    )
    keys = search.asked(importer.asked_sources(search.spec.kind))
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
        fits=lambda item: matches(item, rules),
    )
