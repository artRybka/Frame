"""Discover: Suggestions and themes, the words to search by, and one search
over the catalogue and the museums."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..library import Item, Job, Playlist, PlaylistKind, PlaylistRules, PlaylistSummary
from ..library.duplicates import Shown
from ..library.importer import ALL, span
from ..library.museums import Discovery, Kind
from ..library.themes import GROUPS, THEMES, Theme, browse_theme, theme, theme_of_the_day
from ..library.vocabulary import (
    TERMS,
    artist_matches,
    fold,
    is_copy,
    is_manuscript,
    museum_kind,
    museum_queries,
    set_aside,
    suggest,
    wants_manuscripts,
)
from ..player import POOL_SIZE
from ..service import FrameService
from .deps import require_token, service
from .library_api import RemoteItem, RemotePage, remote_items

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]

ROW_SIZE = 24
#: Rows of works by artists like the ones the owner likes.
TASTE_ROWS = 2
#: Theme covers and counts are worked out again (in the background) after
#: this many seconds.
CARDS_TTL = 600.0
#: The theme of the day comes from the catalogue when it has this many
#: fresh works for it, else from the museums.
DAY_ROW_MIN = 8
#: How long Suggestions wait for the museums' theme of the day; a slower
#: answer shows up next time.
DAY_ROW_WAIT = 3.0
#: Museums that did not answer are asked again after this many seconds.
DAY_ROW_RETRY = 600.0

#: The theme of the day's works, worked out once a day.
_theme_rows: dict[date, list[Item]] = {}
#: When the museums were last asked for the theme of the day, and that fetch.
_day_fetch: tuple[float, threading.Thread | None] = (0.0, None)
#: (when, covers and counts by theme key)
_cards: tuple[float, dict[str, tuple[int, list[Item]]]] = (0.0, {})
#: One worker on the cards at a time.
_cards_lock = threading.Lock()


class ThemeCard(BaseModel):
    key: str
    name: str
    description: str
    group: str = ""
    #: Works in the catalogue that fit, and four of them for the cover.
    count: int = 0
    cover: list[RemoteItem] = []
    #: The owner's playlist made from this theme, if any.
    playlist_id: int | None = None
    rules: PlaylistRules | None = None


class SuggestionRow(BaseModel):
    key: str  # "for-you", "like:<theme>", "theme"
    title: str
    subtitle: str = ""
    theme: str | None = None  # the theme to browse further
    items: list[RemoteItem]


class ThemePage(BaseModel):
    items: list[RemoteItem]
    more: bool
    #: The page to ask for next: searches that found nothing are skipped.
    next_page: int | None = None


class ThemePlaylistRequest(BaseModel):
    #: Also put it on the frame now.
    play: bool = False


class ThemePlaylist(BaseModel):
    playlist: PlaylistSummary
    #: Fetching its first works from the museums, if that started.
    job_id: str | None = None


class TermInfo(BaseModel):
    key: str
    kind: str
    name: str
    words: list[str] = []
    year_from: int | None = None
    year_to: int | None = None


class TermHit(BaseModel):
    #: "artist", "style", "subject", "period", "technique" or "word".
    kind: str
    #: The term's key, the artist's name or the word.
    key: str
    name: str
    detail: str = ""
    #: Works in the catalogue (and the owner's library) that fit.
    count: int = 0


class MuseumHint(BaseModel):
    """What the museums have for words the catalogue does not know."""

    total: int
    artists: list[TermHit]
    items: list[RemoteItem]
    failed: list[str] = []


def _theme_playlist(
    svc: FrameService, found: Theme, playlists: list[Playlist] | None = None
) -> Playlist | None:
    for playlist in svc.library.playlists() if playlists is None else playlists:
        if playlist.theme == found.key or fold(playlist.name) == fold(found.name):
            return playlist
    return None


def _light(items: list[RemoteItem]) -> list[RemoteItem]:
    """Works for rows and covers: without the long texts, which only the
    work's own page shows (and loads itself)."""
    return [
        r.model_copy(
            update={"item": r.item.model_copy(update={"description": "", "artist_bio": ""})}
        )
        for r in items
    ]


def _cover(items: list[Item]) -> list[Item]:
    """Four works by different artists where there are such."""
    picked: list[Item] = []
    for item in items:
        if all(item.artist != p.artist for p in picked):
            picked.append(item)
        if len(picked) == 4:
            return picked
    return (picked + [i for i in items if i not in picked])[:4]


def work_out_cards(svc: FrameService) -> dict[str, tuple[int, list[Item]]]:
    """Every theme's count and cover: a query of the whole catalogue each,
    seconds on a NAS, so done in the background but for the first time."""
    global _cards
    with _cards_lock:
        stamp, cards = _cards
        if cards and time.monotonic() - stamp < CARDS_TTL:
            return cards  # just worked out by another request
        cards = {}
        for found in THEMES:
            total, items = svc.library.query(found.rules(), sort="suitability", limit=40)
            cards[found.key] = (total, _cover(items))
        _cards = (time.monotonic(), cards)
        return cards


def _theme_cards(svc: FrameService) -> dict[str, tuple[int, list[Item]]]:
    """The cards as last worked out; older ones are worked out again in the
    background while this request gets them as they are."""
    stamp, cards = _cards
    if not cards:
        return work_out_cards(svc)
    if time.monotonic() - stamp >= CARDS_TTL and not _cards_lock.locked():
        threading.Thread(target=work_out_cards, args=(svc,), daemon=True).start()
    return cards


def _card(
    svc: FrameService,
    found: Theme,
    cards: dict[str, tuple[int, list[Item]]],
    playlists: list[Playlist],
) -> ThemeCard:
    count, cover = cards.get(found.key, (0, []))
    playlist = _theme_playlist(svc, found, playlists)
    return ThemeCard(
        key=found.key,
        name=found.name,
        description=found.description,
        group=found.group,
        count=count,
        cover=_light(remote_items(svc, cover)),
        playlist_id=playlist.id if playlist else None,
        rules=found.rules(),
    )


def _taste_rows(svc: FrameService, day: date) -> list[SuggestionRow]:
    """Works from the catalogue by artists of the themes the owner's
    favourite artists belong to: because you like Monet, Sisley."""
    player = svc.player
    rows: list[SuggestionRow] = []
    used: set[str] = set()
    for artist in player.taste():
        found = next(
            (t for t in THEMES if t.artists and artist_matches(artist, list(t.artists))), None
        )
        if found is None or found.key in used:
            continue
        rules = found.rules()
        items = svc.library.query(rules, sort="random", seed=day.toordinal())[1]
        others = [i for i in player.fresh(items) if not artist_matches(i.artist, [artist])]
        if len(others) < 4:
            continue
        used.add(found.key)
        rows.append(
            SuggestionRow(
                key=f"like:{found.key}",
                title=f"Bo lubisz: {artist}",
                subtitle=found.name,
                theme=found.key,
                items=remote_items(svc, others[:ROW_SIZE]),
            )
        )
        if len(rows) == TASTE_ROWS:
            break
    return rows


def _fetch_day_row(svc: FrameService, found: Theme, day: date) -> None:
    try:
        items, _ = browse_theme(svc.importer, found, 1, ROW_SIZE)
    except (httpx.HTTPError, ValueError):
        return  # asked again after DAY_ROW_RETRY
    if items:
        _theme_rows.clear()
        _theme_rows[day] = items


def _day_row(svc: FrameService, found: Theme, day: date) -> list[Item]:
    """The theme of the day: from the catalogue when it has enough fresh
    works (no waiting on a museum), else the museums' first page, waited for
    a few seconds at most; a museum slower than that answers for next time."""
    global _day_fetch
    if day in _theme_rows:
        return _theme_rows[day]
    items = svc.library.query(found.rules(), sort="random", seed=day.toordinal())[1]
    picked = svc.player.fresh(items)[:ROW_SIZE]
    if len(picked) >= DAY_ROW_MIN:
        _theme_rows.clear()
        _theme_rows[day] = picked
        return picked
    asked, fetch = _day_fetch
    if fetch is None or (not fetch.is_alive() and time.monotonic() - asked >= DAY_ROW_RETRY):
        fetch = threading.Thread(target=_fetch_day_row, args=(svc, found, day), daemon=True)
        _day_fetch = (time.monotonic(), fetch)
        fetch.start()
    fetch.join(DAY_ROW_WAIT)
    return _theme_rows.get(day) or picked


def _suggestion_rows(svc: FrameService) -> list[SuggestionRow]:
    player = svc.player
    rows = []
    picked = [i for i in player.fresh(player.suggestions()) if not i.excluded]
    if picked:
        rows.append(
            SuggestionRow(
                key="for-you",
                title="Dla Ciebie",
                subtitle="Następne w rotacji Propozycje",
                items=remote_items(svc, picked[::-1][:ROW_SIZE]),
            )
        )
    today = date.today()
    rows += _taste_rows(svc, today)
    found = theme_of_the_day(today)
    day = _day_row(svc, found, today)
    if day:
        rows.append(
            SuggestionRow(
                key="theme",
                title=f"Motyw dnia: {found.name}",
                subtitle=found.description,
                theme=found.key,
                items=remote_items(svc, day),
            )
        )
    return [row.model_copy(update={"items": _light(row.items)}) for row in rows]


@router.get("/suggestions", response_model=list[SuggestionRow])
async def suggestions(svc: Svc) -> list[SuggestionRow]:
    """What Discover opens with: the works the server picked for the frame,
    works like the ones the owner likes and the theme of the day."""
    return await run_in_threadpool(_suggestion_rows, svc)


@router.post("/suggestions/play", status_code=202)
async def play_suggestions(svc: Svc) -> dict[str, bool]:
    """Puts Propozycje on the frame: the rotation without a playlist
    ("Propozycje" in Playlisty)."""
    settings = svc.player.settings
    settings.playlist_id = None
    svc.player.save_settings(settings)
    svc.player.set_hold(None)
    svc.background(svc.player.next("playlist", picks=False))  # its own first picture
    return {"accepted": True}


def _theme_list(svc: FrameService) -> list[ThemeCard]:
    cards = _theme_cards(svc)
    playlists = svc.library.playlists()
    ordered = sorted(THEMES, key=lambda t: GROUPS.index(t.group))
    return [_card(svc, t, cards, playlists) for t in ordered]


@router.get("/themes", response_model=list[ThemeCard])
async def themes(svc: Svc) -> list[ThemeCard]:
    """Every theme, in groups (``GROUPS`` order), with a cover from the
    catalogue and the playlist already made from it."""
    return await run_in_threadpool(_theme_list, svc)


def warm_up(svc: FrameService) -> None:
    """Work out what Discover opens with, so its first visit after a start
    does not wait for it."""
    work_out_cards(svc)
    _suggestion_rows(svc)


def _theme(key: str) -> Theme:
    try:
        return theme(key)
    except KeyError as err:
        raise HTTPException(404, str(err)) from err


@router.get("/themes/{key}", response_model=ThemePage)
async def theme_page(key: str, svc: Svc, page: Annotated[int, Query(ge=1)] = 1) -> ThemePage:
    """A theme, page by page, from the museums (or the catalogue)."""
    found = _theme(key)
    try:
        items, following = await run_in_threadpool(
            browse_theme, svc.importer, found, page, ROW_SIZE
        )
    except (httpx.HTTPError, ValueError) as err:
        raise HTTPException(502, f"{key}: {err}") from err
    return ThemePage(
        items=remote_items(svc, items), more=following is not None, next_page=following
    )


@router.post("/themes/{key}/playlist", response_model=ThemePlaylist)
async def theme_playlist(key: str, request: ThemePlaylistRequest, svc: Svc) -> ThemePlaylist:
    """A smart playlist with the theme's rules (the one made before, if
    any); museums fill it in the background, and ``play`` puts it on the
    frame."""
    found = _theme(key)
    playlist = _theme_playlist(svc, found)
    job_id = None
    if playlist is None:
        playlist = svc.library.save_playlist(
            Playlist(
                name=found.name,
                description=found.description,
                kind=PlaylistKind.SMART,
                rules=found.rules(),
                theme=found.key,
            )
        )
        have = len(svc.library.playlist_items(playlist))
        if have < POOL_SIZE and (found.artists or found.terms):
            rules = playlist.rules

            def fill(job: Job) -> None:
                svc.importer.fill(rules, POOL_SIZE - have, job, pooled=True)

            job_id = svc.importer.start_job(f"theme: {key}", fill).id
    assert playlist.id is not None
    if request.play:
        settings = svc.player.settings
        settings.playlist_id = playlist.id
        svc.player.save_settings(settings)
        svc.player.set_hold(None)
        svc.background(svc.player.next("playlist", picks=False))  # its own first picture
    return ThemePlaylist(playlist=svc.library.playlist_summary(playlist), job_id=job_id)


# -- words to search by ---------------------------------------------------------


@router.get("/vocabulary", response_model=list[TermInfo])
def vocabulary() -> list[TermInfo]:
    """Every style, subject, period and technique, with Polish names."""
    return [
        TermInfo(
            key=t.key,
            kind=t.kind,
            name=t.name,
            words=[w.rstrip("*") for w in t.words],
            year_from=t.year_from,
            year_to=t.year_to,
        )
        for t in TERMS
    ]


def _term_hits(svc: FrameService, text: str, limit: int) -> list[TermHit]:
    wanted = fold(text.strip())
    library = svc.library
    hits: list[TermHit] = []
    artists: Counter[str] = Counter()
    for item in library.query()[1]:
        if item.artist and wanted in fold(item.artist):
            artists[item.artist] += 1
    for name, count in artists.most_common(5):
        hits.append(TermHit(kind="artist", key=name, name=name, count=count))
    for found in suggest(text, limit=limit):
        detail = ", ".join(w.rstrip("*") for w in found.words[:3])
        count = library.query(PlaylistRules(terms=[found.key]))[0]
        kind = "period" if found.kind == "years" else found.kind
        hits.append(TermHit(kind=kind, key=found.key, name=found.name, detail=detail, count=count))
    words = text.strip()
    if words:
        count = library.query(PlaylistRules(query=words))[0]
        hits.append(TermHit(kind="word", key=words, name=words, count=count))
    return hits[: limit + 1]


@router.get("/terms", response_model=list[TermHit])
async def terms(svc: Svc, q: str, limit: Annotated[int, Query(ge=1, le=20)] = 10) -> list[TermHit]:
    """What ``q`` could mean: artists in the library, styles, subjects,
    periods and techniques, and the plain words; each with how many works
    in the catalogue fit."""
    return await run_in_threadpool(_term_hits, svc, q, limit)


@router.get("/terms/museums", response_model=MuseumHint)
async def terms_in_museums(svc: Svc, q: str) -> MuseumHint:
    """What the museums have for ``q``: how many works, the artists among
    the first results whose names fit, and a few of the works."""
    words = q.strip()
    if not words:
        return MuseumHint(total=0, artists=[], items=[])
    total, items, failed = await run_in_threadpool(svc.importer.search_all, words, 8, 1)
    items = [i for i in items if not set_aside(i)]
    wanted = fold(words)
    names: Counter[str] = Counter(i.artist for i in items if i.artist and wanted in fold(i.artist))
    artists = [TermHit(kind="artist", key=n, name=n, count=c) for n, c in names.most_common(3)]
    return MuseumHint(
        total=total, artists=artists, items=remote_items(svc, items[:8]), failed=failed
    )


# -- searching the museums --------------------------------------------------------


def _manuscripts_fit(item: Item, terms: list[str]) -> bool:
    """Pages of manuscripts only when asked for; asked for as the only
    technique, nothing else. Photographs and reproductions never."""
    if is_copy(item):
        return False
    if not wants_manuscripts(terms):
        return not is_manuscript(item)
    techniques = [t for t in terms if t.startswith("technique:")]
    return is_manuscript(item) or len(techniques) > 1


def rules_from(
    q: str = "",
    artists: list[str] | None = None,
    terms: list[str] | None = None,
    colors: list[str] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> PlaylistRules:
    return PlaylistRules(
        query=q,
        artists=artists or [],
        terms=terms or [],
        colors=colors or [],
        year_from=year_from,
        year_to=year_to,
    )


def museum_text(rules: PlaylistRules, page: int) -> str:
    """What to ask the museums: the words, an artist (one per page, in
    turns) and the styles and subjects."""
    artist = rules.artists[(page - 1) % len(rules.artists)] if rules.artists else ""
    topics = museum_queries(rules.terms)[:1]
    return " ".join(w for w in (rules.query.strip(), artist, *topics) if w)


#: With colours asked, museum pages of this many works are looked at, until
#: ``limit`` fit, this many pages are seen or this many seconds have passed.
COLOR_PAGE = 24
COLOR_PAGES = 6
COLOR_SECONDS = 15.0
#: Searches whose shown works later pages remember.
SHOWN_SEARCHES = 16

#: Works a recent search showed, by what it asked: each museum answers on
#: its own, and a work shown from one is left out of the others' answers
#: and later pages (or replaced, when a better copy comes).
_shown: OrderedDict[str, Shown] = OrderedDict()
_shown_lock = threading.Lock()


def shown_in(rules: PlaylistRules, page: int) -> Shown:
    """What the search for ``rules`` showed: nothing yet on its first page."""
    key = rules.model_dump_json()
    with _shown_lock:
        found = _shown.get(key) if page > 1 else None
        if found is None:
            found = _shown[key] = Shown()
        _shown.move_to_end(key)
        while len(_shown) > SHOWN_SEARCHES:
            _shown.popitem(last=False)
        return found


class MuseumAnswer(RemotePage):
    """One museum's part of a search, a line of ``/discover/search/stream``."""

    source: str
    #: The page to ask for more; None when the museum has no more.
    next: int | None = None


@dataclass(frozen=True)
class MuseumSearch:
    """What Discover's search asks the museums."""

    rules: PlaylistRules
    spec: Discovery
    #: The museums chosen; none means all of them.
    keys: list[str]
    limit: int

    @property
    def empty(self) -> bool:
        """Nothing asked: chosen museums show what they have, all of them
        nothing."""
        start, end = self.spec.year_from, self.spec.year_to
        return (
            not self.keys
            and not museum_text(self.rules, 1)
            and not self.rules.colors
            and start is None
            and end is None
            and self.spec.kind == "any"
        )

    def pages(
        self, svc: FrameService, keys: list[str], page: int
    ) -> Iterator[tuple[int, list[Item], list[str], int | None]]:
        """Works of ``keys`` from ``page`` on, a museum page at a time:
        (total, items, museums that failed, the page to ask next). Museums
        don't know colours, so with colours their works are judged by their
        thumbnails, pages deep, until ``limit`` fit or time runs out."""
        importer = svc.importer
        rules = self.rules
        colors = rules.colors
        asked = COLOR_PAGE if colors else self.limit
        left = COLOR_PAGES if colors else 1
        started = time.monotonic()
        total = fitting = 0
        at: int | None = page
        while at is not None and left > 0:
            text = museum_text(rules, at)
            # Several artists take turns, so each page asks for one of them.
            round_ = (at - 1) // len(rules.artists) + 1 if rules.artists else at
            if text:
                count, items, failed = importer.search_all(text, asked, round_, keys)
            else:
                count, items, failed = importer.discover_all(self.spec, asked, at, keys)
            total = total or count
            found = [
                i
                for i in importer.in_colors(items, colors)
                if self.spec.fits(i) and _manuscripts_fit(i, rules.terms)
            ]
            fitting += len(found)
            # Totals of several artists' searches don't add up page by page.
            done = not items or (not rules.artists and 0 < count <= round_ * asked)
            at = None if done else at + 1
            left -= 1
            yield total, found, failed, at
            if fitting >= self.limit or time.monotonic() - started > COLOR_SECONDS:
                return

    def ask(
        self, svc: FrameService, keys: list[str], page: int
    ) -> tuple[int, list[Item], list[str], int | None]:
        """All of :meth:`pages` at once."""
        answers = list(self.pages(svc, keys, page))
        total, _, failed, at = answers[-1]
        return total, [i for _, items, _, _ in answers for i in items], failed, at


def museum_search(
    svc: FrameService,
    q: str,
    artist: list[str] | None,
    term: list[str] | None,
    color: list[str] | None,
    year_from: int | None,
    year_to: int | None,
    source: list[str] | None,
    limit: int,
) -> MuseumSearch:
    keys = [s for s in dict.fromkeys(source or []) if s != ALL]
    offered = svc.importer.sources()
    if unknown := [s for s in keys if s not in offered]:
        raise HTTPException(404, f"unknown museum {unknown[0]!r}")
    rules = rules_from(q, artist, term, color, year_from, year_to)
    start, end = span(rules)
    spec = Discovery(year_from=start, year_to=end, kind=museum_kind(rules.terms))
    return MuseumSearch(rules=rules, spec=spec, keys=keys, limit=limit)


Artists = Annotated[list[str] | None, Query()]
Terms = Annotated[list[str] | None, Query()]
Colors = Annotated[list[str] | None, Query()]
Sources = Annotated[list[str] | None, Query()]
Year = Annotated[int | None, Query(ge=0, le=2100)]
Page = Annotated[int, Query(ge=1)]
Limit = Annotated[int, Query(ge=1, le=24)]


@router.get("/discover/search", response_model=MuseumAnswer)
async def search_museums(
    svc: Svc,
    q: str = "",
    artist: Artists = None,
    term: Terms = None,
    color: Colors = None,
    year_from: Year = None,
    year_to: Year = None,
    source: Sources = None,
    page: Page = 1,
    limit: Limit = 8,
) -> MuseumAnswer:
    """The museums' works for what Discover's search asks (``limit`` from
    each museum; every museum, or those of ``source``): their own search for
    words, artists, styles and subjects, else works of the periods and
    technique; with ``color``, those whose thumbnails have the colours."""
    search = museum_search(svc, q, artist, term, color, year_from, year_to, source, limit)
    if search.empty:
        return MuseumAnswer(source=ALL, total=0, items=[])
    keys = search.keys
    total, items, failed, next_ = await run_in_threadpool(search.ask, svc, keys, page)
    if keys and len(failed) == len(keys):
        raise HTTPException(502, f"{', '.join(failed)} did not answer")
    return MuseumAnswer(
        source=keys[0] if len(keys) == 1 else ALL,
        total=total,
        items=remote_items(svc, items, copies=len(keys) != 1),
        failed=failed,
        next=next_,
    )


@router.get("/discover/search/stream")
async def stream_museums(
    svc: Svc,
    q: str = "",
    artist: Artists = None,
    term: Terms = None,
    color: Colors = None,
    year_from: Year = None,
    year_to: Year = None,
    source: Sources = None,
    page: Page = 1,
    limit: Limit = 8,
) -> StreamingResponse:
    """Like ``/discover/search``, as the museums answer: a
    :class:`MuseumAnswer` per museum page (JSON lines), with colours several
    pages of each museum. A work comes once, from whichever museum answers
    first, unless a more reliable one brings it later (``replaces``)."""
    search = museum_search(svc, q, artist, term, color, year_from, year_to, source, limit)
    keys = [] if search.empty else search.keys or svc.importer.sources()
    copies = len(search.keys) != 1
    shown = shown_in(search.rules, page)

    loop = asyncio.get_running_loop()
    answers: asyncio.Queue[MuseumAnswer | None] = asyncio.Queue()
    #: Set when the app stops listening: no more pages are asked for.
    gone = threading.Event()

    def ask(key: str) -> None:
        """One museum's pages onto ``answers``, then None."""
        try:
            for total, items, failed, next_ in search.pages(svc, [key], page):
                if gone.is_set():
                    return
                found = {r.item.id: r for r in remote_items(svc, items, copies)}
                taken = shown.take(r.item for r in found.values())
                new = [
                    found[t.item.id].model_copy(update={"work": t.work, "replaces": t.replaces})
                    for t in taken
                ]
                answer = MuseumAnswer(source=key, total=total, items=new, failed=failed, next=next_)
                loop.call_soon_threadsafe(answers.put_nowait, answer)
        except Exception:
            log.exception("searching %s failed", key)
            failure = MuseumAnswer(source=key, total=0, items=[], failed=[key])
            loop.call_soon_threadsafe(answers.put_nowait, failure)
        finally:
            loop.call_soon_threadsafe(answers.put_nowait, None)

    async def lines() -> AsyncIterator[str]:
        asking = [asyncio.ensure_future(run_in_threadpool(ask, k)) for k in keys]
        try:
            left = len(asking)
            while left:
                answer = await answers.get()
                if answer is None:
                    left -= 1
                else:
                    yield answer.model_dump_json() + "\n"
        finally:
            gone.set()
            for task in asking:
                task.cancel()

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.get("/browse", response_model=RemotePage)
async def browse(
    svc: Svc,
    year_from: Annotated[int | None, Query(ge=0, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=0, le=2100)] = None,
    style: str = "",
    kind: Kind = "any",
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=24)] = 8,
) -> RemotePage:
    """Works of a period, style and kind from every museum that can filter
    that way, interleaved (``limit`` from each)."""
    spec = Discovery(year_from=year_from, year_to=year_to, style=style, kind=kind)
    total, items, failed = await run_in_threadpool(svc.importer.discover_all, spec, limit, page)
    items = [i for i in items if spec.fits(i) and not set_aside(i)]
    return RemotePage(total=total, items=remote_items(svc, items), failed=failed)
