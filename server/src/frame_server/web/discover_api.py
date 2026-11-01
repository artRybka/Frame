"""Discover: Suggestions and themes, the words to search by, and one search
over the catalogue and the museums."""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..library import (
    Item,
    ItemKind,
    Job,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    PlaylistSummary,
)
from ..library.artists import is_artist
from ..library.duplicates import Shown
from ..library.importer import ALL, span
from ..library.museums import Discovery, Kind
from ..library.themes import (
    GROUPS,
    THEMES,
    Theme,
    batch_of,
    browse_theme,
    day_reason,
    liked,
    make_liked,
    new_artist_of_the_week,
    page_after,
    search_page,
    theme,
    theme_of_the_day,
    weekly_themes,
)
from ..library.viewer import viewer_id
from ..library.vocabulary import (
    TECHNIQUE_KINDS,
    TERMS,
    category_fits,
    fold,
    museum_kind,
    museum_queries,
    set_aside,
    suggest,
)
from ..player import POOL_SIZE
from ..service import FrameService
from .deps import require_owner, require_token, service
from .library_api import RemoteItem, RemotePage, remote_items
from .playlists_api import summary

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]

ROW_SIZE = 24
#: A theme's stream asks this many of its searches at once, each one's
#: works sent as it answers.
THEME_BATCH = 4
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
#: The owner's works not shown for this many days come back in a row.
BACK_DAYS = 180
#: Rows of works shown only with at least this many.
ROW_MIN = 4
#: A theme's cover: four works drawn each day from its best ones.
COVER_POOL = 40

#: The theme of the day's works, worked out once a day.
_theme_rows: dict[date, list[Item]] = {}
#: When the museums were last asked for the theme of the day, and that fetch.
_day_fetch: tuple[float, threading.Thread | None] = (0.0, None)
#: (when, the count, new works and cover by theme key)
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
    key: str  # "for-you", "theme", "back" ("like:<theme>" before "Bo lubisz" cards)
    title: str
    subtitle: str = ""
    theme: str | None = None  # the theme to browse further
    items: list[RemoteItem]


class ThemePage(BaseModel):
    items: list[RemoteItem]
    more: bool
    #: The page to ask for next: searches that found nothing are skipped.
    next_page: int | None = None


class ThemeLine(BaseModel):
    """A line of ``/themes/{key}/stream``: one search's works as it
    answers; the last line (``end``) says whether there is more."""

    items: list[RemoteItem] = []
    end: bool = False
    more: bool = False
    next_page: int | None = None
    #: Every search asked failed (on the last line).
    failed: bool = False


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
    #: Named periods: their group in Epoka ("europe", "poland", "east-asia").
    region: str | None = None


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
    """The playlist made from ``found``: the asking person's or a shared one."""
    for playlist in svc.library.playlists(viewer_id()) if playlists is None else playlists:
        if playlist.theme == found.key or fold(playlist.name) == fold(found.playlist or found.name):
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


def _cover(items: list[Item], seed: str = "") -> list[Item]:
    """Four works by different artists where there are such, drawn from the
    best ``COVER_POOL`` by ``seed`` (a day's covers differ from the next's)."""
    items = items[:COVER_POOL]
    if seed:
        random.Random(seed).shuffle(items)
    picked: list[Item] = []
    for item in items:
        if all(item.artist != p.artist for p in picked):
            picked.append(item)
        if len(picked) == 4:
            return picked
    return (picked + [i for i in items if i not in picked])[:4]


def _since(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


def work_out_cards(svc: FrameService) -> dict[str, tuple[int, list[Item]]]:
    """Every theme's count and cover: a query of the whole
    catalogue each, seconds on a NAS, so done in the background but for the
    first time (as are the week's themes, once a week, and the cards of
    "Bo lubisz", from the owner's taste then)."""
    global _cards
    with _cards_lock:
        stamp, cards = _cards
        if cards and time.monotonic() - stamp < CARDS_TTL:
            return cards  # just worked out by another request
        cards = {}
        today = date.today().isoformat()
        mine: dict[str, Theme] = {}
        for user in svc.users.users():  # everyone's "Bo lubisz"
            for found in make_liked(svc.library, svc.player.taste(user.id), user.id):
                mine.setdefault(found.key, found)
        for found in [*weekly_themes(svc.library, date.today()), *mine.values(), *THEMES]:
            total, items = svc.library.query(found.rules(), sort="suitability")
            cards[found.key] = (total, _cover(items, f"{today}:{found.key}"))
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


def _back_row(svc: FrameService, day: date) -> SuggestionRow | None:
    """The owner's works (kept or liked) the frame has not shown for half
    a year or more."""
    since = _since(BACK_DAYS)
    hearts = svc.library.favorites()  # the asking person's
    rules = PlaylistRules(kinds=[ItemKind.ARTWORK])
    back = [
        i
        for i in svc.library.query(rules)[1]
        if (i.id in hearts or not i.pooled) and (i.last_shown_at or i.added_at or since) < since
    ]
    if len(back) < ROW_MIN:
        return None
    random.Random(day.toordinal()).shuffle(back)
    return SuggestionRow(
        key="back",
        title="Dawno ich nie było",
        subtitle="Twoje dzieła, których ramka nie pokazała od pół roku",
        items=remote_items(svc, back[:ROW_SIZE]),
    )


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
    found = theme_of_the_day(today, svc.library)
    day = _day_row(svc, found, today)
    if day:
        reason = day_reason(today)
        rows.append(
            SuggestionRow(
                key="theme",
                title=f"Motyw dnia: {found.name}",
                subtitle=f"{reason}. {found.description}" if reason else found.description,
                theme=found.key,
                items=remote_items(svc, day),
            )
        )
    if back := _back_row(svc, today):
        rows.append(back)
    return [row.model_copy(update={"items": _light(row.items)}) for row in rows]


@router.get("/suggestions", response_model=list[SuggestionRow])
async def suggestions(svc: Svc) -> list[SuggestionRow]:
    """What Discover opens with: the works the server picked for the frame,
    the theme of the day (a card of "Dziś dla Ciebie" in the app) and the
    owner's works not shown for long. Works like the ones the owner likes
    are the cards of "Bo lubisz" in ``/themes``."""
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
    playlists = svc.library.playlists(viewer_id())
    # The week's themes and "Bo lubisz" once the cards have them (worked
    # out with them).
    weekly = [t for t in weekly_themes(svc.library, date.today()) if t.key in cards]
    mine = [t for t in liked(svc.library) if t.key in cards]
    ordered = sorted([*weekly, *mine, *THEMES], key=lambda t: GROUPS.index(t.group))
    return [_card(svc, t, cards, playlists) for t in ordered]


@router.get("/themes", response_model=list[ThemeCard])
async def themes(svc: Svc) -> list[ThemeCard]:
    """Every theme, in groups (``GROUPS`` order), with a cover from the
    catalogue and the playlist already made from it."""
    return await run_in_threadpool(_theme_list, svc)


def warm_up(svc: FrameService) -> None:
    """Work out what Discover opens with, so its first visit after a start
    does not wait for it; the suggestions while typing first."""
    svc.library.term_index()
    work_out_cards(svc)
    _suggestion_rows(svc)


def _theme(key: str, svc: FrameService) -> Theme:
    try:
        return theme(key, svc.library)
    except KeyError as err:
        raise HTTPException(404, str(err)) from err


def _new_artist(svc: FrameService) -> ThemeCard | None:
    """Another artist of the week, with its card worked out at once (the
    other cards stay as they are)."""
    global _cards
    found = new_artist_of_the_week(svc.library, date.today())
    if found is None:
        return None
    total, items = svc.library.query(found.rules(), sort="suitability")
    cover = _cover(items, f"{date.today().isoformat()}:{found.key}")
    with _cards_lock:
        stamp, cards = _cards
        _cards = (stamp, {**cards, found.key: (total, cover)})
    playlists = svc.library.playlists(viewer_id())
    return _card(svc, found, {found.key: (total, cover)}, playlists)


@router.post(
    "/themes/week-artist/again",
    response_model=ThemeCard,
    dependencies=[Depends(require_owner)],
)
async def week_artist_again(svc: Svc) -> ThemeCard:
    """Another artist of the week, drawn now (Konfiguracja → "Wylosuj
    innego"); 409 when the catalogue has no other artist fit for it."""
    card = await run_in_threadpool(_new_artist, svc)
    if card is None:
        raise HTTPException(409, "no other artist for this week")
    return card


@router.get("/themes/{key}", response_model=ThemePage)
async def theme_page(key: str, svc: Svc, page: Annotated[int, Query(ge=1)] = 1) -> ThemePage:
    """A theme, page by page, from the museums (or the catalogue)."""
    found = await run_in_threadpool(_theme, key, svc)
    try:
        items, following = await run_in_threadpool(
            browse_theme, svc.importer, found, page, ROW_SIZE
        )
    except (httpx.HTTPError, ValueError) as err:
        raise HTTPException(502, f"{key}: {err}") from err
    return ThemePage(
        items=remote_items(svc, items), more=following is not None, next_page=following
    )


@router.get("/themes/{key}/stream")
async def stream_theme(
    key: str, svc: Svc, page: Annotated[int, Query(ge=1)] = 1
) -> StreamingResponse:
    """Like ``/themes/{key}``, as the museums answer: several of the
    theme's searches asked at once (:data:`THEME_BATCH`), a
    :class:`ThemeLine` with each one's works as it comes, then a last line
    with the page to ask for next."""
    found = await run_in_threadpool(_theme, key, svc)
    if not found.searches():  # the catalogue: one page at once
        items, following = await run_in_threadpool(
            browse_theme, svc.importer, found, page, ROW_SIZE
        )

        async def once() -> AsyncIterator[str]:
            yield ThemeLine(items=remote_items(svc, items)).model_dump_json() + "\n"
            last = ThemeLine(end=True, more=following is not None, next_page=following)
            yield last.model_dump_json() + "\n"

        return StreamingResponse(once(), media_type="application/x-ndjson")

    pages = batch_of(found, page, THEME_BATCH)
    loop = asyncio.get_running_loop()
    #: Works as they come; True or False when a search is over (answered or not).
    lines_: asyncio.Queue[ThemeLine | bool] = asyncio.Queue()
    #: How many works the last page's search has (whether a round follows).
    last_total = [0]
    #: Set when the app stops listening.
    gone = threading.Event()

    def ask(at: int) -> None:
        ok = False
        try:
            items, total = search_page(svc.importer, found, at, ROW_SIZE)
            ok = True
            if at == pages[-1]:
                last_total[0] = total
            if items and not gone.is_set():
                line = ThemeLine(items=remote_items(svc, items))
                loop.call_soon_threadsafe(lines_.put_nowait, line)
        except (httpx.HTTPError, ValueError) as err:
            log.warning("theme %s: page %d failed: %s", key, at, err)
        except Exception:
            log.exception("theme %s: page %d failed", key, at)
        finally:
            loop.call_soon_threadsafe(lines_.put_nowait, ok)

    async def lines() -> AsyncIterator[str]:
        asking = [asyncio.ensure_future(run_in_threadpool(ask, at)) for at in pages]
        answered = False
        try:
            left = len(asking)
            while left:
                line = await lines_.get()
                if isinstance(line, bool):
                    left -= 1
                    answered |= line
                else:
                    yield line.model_dump_json() + "\n"
            following = page_after(found, pages[-1], last_total[0], ROW_SIZE)
            last = ThemeLine(
                end=True,
                more=following is not None,
                next_page=following,
                failed=not answered,
            )
            yield last.model_dump_json() + "\n"
        finally:
            gone.set()
            for task in asking:
                task.cancel()

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.post("/themes/{key}/playlist", response_model=ThemePlaylist)
async def theme_playlist(key: str, request: ThemePlaylistRequest, svc: Svc) -> ThemePlaylist:
    """A smart playlist with the theme's rules (the one made before, if
    any); museums fill it in the background, and ``play`` puts it on the
    frame."""
    found = await run_in_threadpool(_theme, key, svc)
    playlist = _theme_playlist(svc, found)
    job_id = None
    if playlist is None:
        playlist = svc.library.save_playlist(
            Playlist(
                name=found.playlist or found.name,
                description=found.description,
                kind=PlaylistKind.SMART,
                rules=found.rules(),
                theme=found.key,
                owner=viewer_id(),
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
    return ThemePlaylist(playlist=summary(svc, playlist), job_id=job_id)


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
            region=t.region,
        )
        for t in TERMS
    ]


def _term_hits(svc: FrameService, text: str, limit: int) -> list[TermHit]:
    """Artists, the works' keywords ("wielka fala"), the vocabulary's terms
    and the typed words last (always there: the app's Return puts them in)."""
    index = svc.library.term_index()
    words = text.strip()
    hits = [
        TermHit(kind="artist", key=name, name=name, count=count)
        for name, count in index.artists(text, limit=4)
    ]
    hits += [
        TermHit(kind="word", key=phrase, name=phrase, count=index.word_count(phrase))
        for phrase in index.phrases(text, limit=3)
        if fold(phrase) != fold(words)
    ]
    for found in suggest(text, limit=max(limit - len(hits), 3)):
        detail = ", ".join(w.rstrip("*") for w in found.words[:3])
        kind = "period" if found.kind == "years" else found.kind
        count = index.term_count(found.key)
        hits.append(TermHit(kind=kind, key=found.key, name=found.name, detail=detail, count=count))
    hits = hits[:limit]
    if words:
        hits.append(TermHit(kind="word", key=words, name=words, count=index.word_count(words)))
    return hits


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
    names: Counter[str] = Counter(
        i.artist for i in items if wanted in fold(i.artist) and is_artist(i.artist)
    )
    artists = [TermHit(kind="artist", key=n, name=n, count=c) for n, c in names.most_common(3)]
    return MuseumHint(
        total=total, artists=artists, items=remote_items(svc, items[:8]), failed=failed
    )


# -- searching the museums --------------------------------------------------------


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
                if self.spec.fits(i) and category_fits(i, rules.terms)
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
    if page == 1:
        svc.player.searched_for(search.rules.artists, viewer_id())

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
                # What the owner looks for, into the catalogue.
                svc.player.keep_searched(r.item for r in new if not r.in_library)
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
    asked = [key for key, value in TECHNIQUE_KINDS.items() if value == kind]
    items = [i for i in items if spec.fits(i) and not set_aside(i, asked)]
    return RemotePage(total=total, items=remote_items(svc, items), failed=failed)
