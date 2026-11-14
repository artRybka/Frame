"""Discover: Suggestions and themes, the words to search by, and one search
over the catalogue and the museums."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import AsyncIterator, Callable
from datetime import date
from typing import Annotated
from weakref import WeakKeyDictionary

import httpx
from anyio import CapacityLimiter, to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..library import (
    Item,
    Job,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    PlaylistSummary,
    day_picks,
    zoom,
)
from ..library.artists import is_artist, known_names
from ..library.duplicates import Shown, work_key
from ..library.hosts import urgent_call
from ..library.importer import ALL
from ..library.mix import mixed
from ..library.museums import places_in
from ..library.phrases import quote
from ..library.places import NAME as NAME_KEY
from ..library.places import OWN, QID, known_places, migrate_sources
from ..library.repo import Abandoned, Hidden, Library, asked_by, says
from ..library.search import MuseumSearch, fill_card
from ..library.themes import (
    CARD_MIN,
    GROUPS,
    MIX_PREFIX,
    OTHER_ART_THEMES,
    SECTION_YEARS,
    THEMES,
    WEEKLY,
    Theme,
    batch_of,
    browse_theme,
    colour_themes,
    curated,
    curated_seen,
    day_reason,
    for_you,
    kept_close,
    liked,
    make_liked,
    new_artist_of_the_week,
    page_after,
    search_page,
    theme,
    theme_of_the_day,
)
from ..library.verdict import Place, against
from ..library.viewer import viewer_id
from ..library.vocabulary import (
    TERMS,
    fold,
    is_painting,
    suggest,
)
from ..library.zoom import zooms
from ..museum_places import PlaceHit, commons_picture
from ..player import POOL_SIZE, SUGGESTIONS_KEY, TILE_WORKS_KEY
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
#: How long a set's museums wait for its catalogue's works (shown first).
CATALOGUE_HEAD_START = 0.5
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
#: A theme's cover: four works drawn each day from its best ones.
COVER_POOL = 40

#: The theme of the day's works, worked out once a day.
_theme_rows: dict[date, list[Item]] = {}
#: When the museums were last asked for the theme of the day, and that fetch.
_day_fetch: tuple[float, threading.Thread | None] = (0.0, None)
#: (when, the count, new works and cover by theme key)
_cards: tuple[float, dict[str, tuple[int, list[Item]]]] = (0.0, {})
#: What the cards were worked out from (:func:`_cards_key`).
_cards_from: tuple[object, ...] = ()
#: Discover's rows as last worked out, by viewer: (what from, the rows).
_rows: dict[str, tuple[tuple[object, ...], list[SuggestionRow]]] = {}
#: One worker on the cards at a time.
_cards_lock = threading.Lock()
#: Pages of themes kept at most (every card's first page, a few more).
PAGES_KEPT = 400

#: A theme's page of the catalogue for one person (:func:`_page_key`).
PageKey = tuple[str, str, int, str]
#: What a page was worked out from (:func:`_page_stamp`).
PageStamp = tuple[int, ...]


class _ThemePages:
    """One library's pages of themes as last worked out
    (:func:`catalogue_page`): (what it was worked out from,
    :func:`_page_stamp`; how many works fit; the page's works) by
    :func:`_page_key`."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.kept: OrderedDict[PageKey, tuple[PageStamp, int, list[Item]]] = OrderedDict()
        #: Pages being worked out again in the background.
        self.working: set[PageKey] = set()

    def keep(self, key: PageKey, stamp: PageStamp, total: int, items: list[Item]) -> None:
        with self.lock:
            self.kept[key] = (stamp, total, items)
            self.kept.move_to_end(key)
            while len(self.kept) > PAGES_KEPT:
                self.kept.popitem(last=False)


#: By library (a test's own, the server's one).
_theme_pages: WeakKeyDictionary[Library, _ThemePages] = WeakKeyDictionary()
_theme_pages_lock = threading.Lock()


def _pages_of(library: Library) -> _ThemePages:
    with _theme_pages_lock:
        pages = _theme_pages.get(library)
        if pages is None:
            pages = _theme_pages[library] = _ThemePages()
        return pages


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
    #: The part of its group's page it stands in ("Starożytność i Bizancjum"),
    #: and that part's years.
    section: str = ""
    section_years: str = ""


class SuggestionRow(BaseModel):
    key: str  # "for-you", "theme" (also "back" and "like:<theme>" before)
    title: str
    subtitle: str = ""
    theme: str | None = None  # the theme to browse further
    items: list[RemoteItem]
    #: Of ``items``, the ids of the works for its card's cover (the theme
    #: of the day as a card in "Dziś dla Ciebie"), picked as a theme's
    #: cover is (:func:`_cover`: paintings first); [] for rows without one.
    cover: list[str] = []


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
    #: A title: the work that has it, for its thumbnail (kind "title").
    item: str = ""
    #: A title the words typed are (not only part of): Return picks it.
    exact: bool = False


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


#: What rows and covers leave out of a work: the long texts, which only the
#: work's own page shows (and loads itself), and what only the server uses
#: (the app reads none of it). /api/themes was 692 KB on the NAS.
_HEAVY: dict[str, object] = {
    "description": "",
    "artist_bio": "",
    "keywords": [],
    "terms": [],
    "color_shares": {},
    "framing": {},
}


def _light(items: list[RemoteItem]) -> list[RemoteItem]:
    """Works for rows and covers, without :data:`_HEAVY`."""
    return [r.model_copy(update={"item": r.item.model_copy(update=_HEAVY)}) for r in items]


def _draw(seed: str, item: Item) -> bytes:
    """Where ``item`` stands in the day's draw for a cover: its own, so a
    work coming into or leaving the pool does not move the others."""
    return hashlib.sha256(f"{seed}:{item.id}".encode()).digest()


def _cover(items: list[Item], seed: str = "", found: Theme | None = None) -> list[Item]:
    """Four works by different artists where there are such, drawn from the
    best ``COVER_POOL`` by ``seed`` (a day's covers differ from the next's).

    Each work draws on its own (:func:`_draw`), not a shuffle of the pool:
    the cards are worked out again whenever the catalogue changes, and a
    shuffle gave a card four other works after one new work came in, so
    the covers kept changing while Odkrywaj was browsed (Mateusz
    2026-11-07).

    Paintings come first, the best ``COVER_POOL`` of them wherever they
    stand in ``items``, unless ``found`` is a theme of prints or drawings
    (:meth:`Theme.on_paper`): drawings and prints stay inside the set, the
    cover is painting (Mateusz 2026-11-12). A theme with fewer paintings
    than four fills its cover with the rest as before."""
    paintings = found is None or not found.on_paper()
    pool = items[:COVER_POOL]
    if paintings:
        painted = [i for i in items if is_painting(i)][:COVER_POOL]
        pool = painted + [i for i in pool if not is_painting(i)]
    if seed:
        pool = sorted(pool, key=lambda i: (paintings and not is_painting(i), _draw(seed, i)))
    picked: list[Item] = []
    for item in pool:
        if all(item.artist != p.artist for p in picked):
            picked.append(item)
        if len(picked) == 4:
            return picked
    return (picked + [i for i in pool if i not in picked])[:4]


def _cards_key(svc: FrameService) -> tuple[object, ...]:
    """The cards stay as worked out while this stays: the day (covers and
    the week's themes), the catalogue's works, everyone's hearts ("Bo
    lubisz"). A picture shown or a work described does not change it; the
    curator's new cards do (with the day, so at once)."""
    made = tuple(t.key for t in curated(svc.library))
    return ((date.today(), made), *svc.library.catalogue_stamp())


def _cards_stale(svc: FrameService, stamp: float) -> bool:
    """Worked out on another day or before the curator's new cards: at
    once. After works came in or went, or hearts: at most every
    ``CARDS_TTL`` (the whole round is a query of the catalogue for every
    card, and while Szukaj is open the museums' works come in without a
    pause: round after round, the audit of 2026-11-14), unless a cover
    lost a work (hidden, or gone: it would show a hole)."""
    key = _cards_key(svc)
    if key == _cards_from:
        return False
    if key[:1] != _cards_from[:1] or time.monotonic() - stamp >= CARDS_TTL:
        return True
    return key[1] != _cards_from[1] and _cover_lost(svc)


def _cover_lost(svc: FrameService) -> bool:
    """A work of some card's cover is hidden now, or no longer here."""
    hidden = svc.library.hidden()
    return any(
        item in hidden or not svc.library.has(item.id)
        for _count, cover in _cards[1].values()
        for item in cover
    )


def work_out_cards(svc: FrameService, force: bool = False) -> dict[str, tuple[int, list[Item]]]:
    """Every theme's count and cover: a query of the whole
    catalogue each, seconds on a NAS, so done at night (``force``) and in
    the background after the catalogue changed, but for the first time (as
    are the week's themes, once a week, and the cards of "Bo lubisz", from
    the owner's taste then)."""
    global _cards, _cards_from
    with _cards_lock:
        _, cards = _cards
        key = _cards_key(svc)
        if cards and not force and key == _cards_from:
            return cards  # just worked out by another request
        cards = {}
        day = date.today()
        today = day.isoformat()
        mine: dict[str, Theme] = {}
        for user in svc.users.users():  # everyone's "Bo lubisz"
            for found in make_liked(svc.library, svc.player.hearted(user.id), user.id):
                mine.setdefault(found.key, found)
        weekly = for_you(svc.library, day)
        others = [*mine.values(), *THEMES, *OTHER_ART_THEMES, *colour_themes(svc.library, day)]
        pages = _pages_of(svc.library)
        for found in [*weekly, *others]:
            stamp = _page_stamp(svc, day)
            total, items = svc.library.query(
                found.rules(), sort="good", seed=day.toordinal(), proposing=True
            )
            cards[found.key] = (total, _cover(items, f"{today}:{found.key}", found))
            # The same query is the theme's first page: its set opens at once.
            pages.keep(_page_key(found, 1, viewer_id()), stamp, total, items[:ROW_SIZE])
        _cards = (time.monotonic(), cards)
        _cards_from = key
        return cards


def shown_ids(svc: FrameService) -> set[str]:
    """The works Discover shows as last worked out: the cards' covers, the
    themes' pages kept (every card's first page and those opened since) and
    everyone's Propozycje dnia (the night's tidying looks at them first,
    Mateusz 2026-11-11)."""
    ids = {i.id for _count, cover in _cards[1].values() for i in cover}
    pages = _pages_of(svc.library)
    with pages.lock:
        kept = list(pages.kept.values())
    ids.update(i.id for _stamp, _total, items in kept for i in items)
    users = [svc.player.suggestions_user, *(u.id for u in svc.users.users())]
    for user in dict.fromkeys(users):
        picks = day_picks.kept(svc.library, user)
        if picks is not None:
            ids.update(picks.ids)
    return ids


def _theme_cards(svc: FrameService) -> dict[str, tuple[int, list[Item]]]:
    """The cards as last worked out; older ones are worked out again in the
    background while this request gets them as they are."""
    stamp, cards = _cards
    if not cards:
        return work_out_cards(svc)
    if _cards_stale(svc, stamp) and not _cards_lock.locked():
        threading.Thread(target=work_out_cards, args=(svc,), daemon=True).start()
    return cards


def _card(
    svc: FrameService,
    found: Theme,
    cards: dict[str, tuple[int, list[Item]]],
    playlists: list[Playlist],
    hidden: Hidden | None = None,
) -> ThemeCard:
    """``hidden``: the hidden works, when worked out once for many cards."""
    count, cover = cards.get(found.key, (0, []))
    playlist = _theme_playlist(svc, found, playlists)
    return ThemeCard(
        key=found.key,
        name=found.name,
        description=found.description,
        group=found.group,
        count=count,
        cover=_light(remote_items(svc, cover, hidden=hidden)),
        playlist_id=playlist.id if playlist else None,
        rules=found.rules(),
        section=found.section,
        section_years=SECTION_YEARS.get(found.section, ""),
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
    items = svc.library.query(found.rules(), sort="random", seed=day.toordinal(), proposing=True)[1]
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
                items=remote_items(svc, mixed(day)),
                cover=[i.id for i in _cover(day, f"{today.isoformat()}:{found.key}", found)],
            )
        )
    if zoom := _zoom_row(svc):
        rows.append(zoom)
    return [row.model_copy(update={"items": _light(row.items)}) for row in rows]


#: Discover's row of the works to look at far closer, in tiles ("Pod
#: lupą", before "Studia dzieł"; Mateusz 2026-11-09).
ZOOM_ROW = "zoom"
#: The files with a tile set are read once in the background when none are
#: kept yet (after that, at night once a month).
_zoom_asked = threading.Event()


def _zoom_row(svc: FrameService) -> SuggestionRow | None:
    """The works whose picture shown is a Commons file with a tile set:
    the library's (hearts first), then Commons' other such files."""
    player = svc.player
    files = player.tile_set_works()
    if not files and not _zoom_asked.is_set():
        _zoom_asked.set()
        threading.Thread(target=player.tile_set_files, name="tile sets", daemon=True).start()
    if not zoom.pages():
        return None
    hidden = svc.library.hidden()
    works = svc.library.works()
    # The catalogue's works that zoom, as its whole list has them: looked
    # for among the copies of the works one copy of which zooms (the best
    # copy stands for a work), not in the whole catalogue (a few seconds on
    # the NAS after every change of a work, the audit of 2026-11-14).
    may: set[str] = set()
    for item in zoom.zooming(svc.library.all_items()):
        at = works.group_index(item.id)
        may.update([item.id] if at is None else [c.id for c in works.groups[at]])
    found = svc.library.query(limit=None, proposing=True, among=may)[1] if may else []
    own = [i for i in found if zooms(i) and i not in hidden]
    own.sort(key=lambda i: (not i.favorite, i.title.casefold()))
    fragments = svc.importer.fragments

    def work(item: Item) -> str:
        """One work's key: Commons keeps some as several files with a tile
        set (Whistler's "Princess" three times, Mateusz 2026-11-10)."""
        shown = item.sharper.item_id if item.sharper is not None else item.id
        source, _, page = shown.partition(":")
        if fragments is not None and source == "wmc" and (qid := fragments.work_of_page(page)):
            return qid
        return work_key(item) or item.id

    shown = {g for i in own if (g := works.group_index(i.id)) is not None}
    seen: set[str] = set()
    kept: list[Item] = []
    for item in own:
        if (key := work(item)) not in seen:
            seen.add(key)
            kept.append(item)
    # A file shown already in its work's place is that work.
    taken = {i.id for i in own} | {i.sharper.item_id for i in own if i.sharper is not None}
    svc.importer.remember(files)
    # Of several files of one work, the largest.
    for item in sorted(files, key=lambda i: -(i.width or 0) * (i.height or 0)):
        at = works.group_index(item.id)
        if item.id in taken or (at is not None and at in shown) or item in hidden:
            continue
        if (key := work(item)) in seen:
            continue
        seen.add(key)
        kept.append(item)
        taken.add(item.id)
    own = kept
    if not own:
        return None
    return SuggestionRow(
        key=ZOOM_ROW,
        title="Pod lupą",
        subtitle="Dzieła w ogromnej rozdzielczości",
        items=remote_items(svc, own, copies=False),
    )


def suggestion_rows(svc: FrameService) -> list[SuggestionRow]:
    """The rows as last worked out while the library, Propozycje and the
    day stay as they were (worked out at night, and again after a change)."""
    viewer = viewer_id()
    today = date.today()
    key = (
        today,
        today in _theme_rows,  # the museums' row of the day came in since
        svc.library.stamp(),
        tuple(svc.library.get_state(SUGGESTIONS_KEY, [])),
        # "Pod lupą": the files with a tile set listed and read since.
        len(zoom.pages()),
        (svc.library.get_state(TILE_WORKS_KEY) or {}).get("at"),
    )
    kept = _rows.get(viewer)
    if kept is not None and kept[0] == key:
        return kept[1]
    rows = _suggestion_rows(svc)
    _rows[viewer] = (key, rows)
    return rows


@router.get("/suggestions", response_model=list[SuggestionRow])
async def suggestions(svc: Svc) -> list[SuggestionRow]:
    """What Discover opens with: the works the server picked for the frame
    and the theme of the day (a card of "Dziś dla Ciebie" in the app). The
    row of the owner's works not shown for long is gone (Mateusz
    2026-11-07); works like the ones the owner likes are the cards
    "Ponieważ lubisz" in ``/themes``."""
    return await run_in_threadpool(suggestion_rows, svc)


class DayCard(BaseModel):
    """A card of "Dziś dla Ciebie" that Propozycje dnia take works from (as
    the app's ``ArtTheme``: it opens the card)."""

    key: str
    name: str
    description: str = ""
    group: str = WEEKLY


class DayPicksView(BaseModel):
    """``GET /api/suggestions/day``: the asking person's Propozycje dnia."""

    day: str
    cards: list[DayCard]
    #: The works in the order the frame shows them: fours from each card.
    items: list[RemoteItem]


@router.get("/suggestions/day", response_model=DayPicksView)
async def day_suggestions(svc: Svc) -> DayPicksView:
    """Propozycje dnia: twelve works of each card of "Dziś dla Ciebie", in
    fours (Mateusz 2026-11-09), made once a day for each person."""
    user = viewer_id()

    def view() -> DayPicksView:
        picks = svc.player.day_picks(user)
        found = (svc.library.get(i) for i in picks.ids)
        items = [i for i in found if i is not None]
        return DayPicksView(
            day=picks.day,
            cards=[DayCard(key=k, name=n, description=d) for k, n, d in picks.cards],
            items=_light(remote_items(svc, items, copies=False)),
        )

    return await run_in_threadpool(view)


@router.post("/suggestions/play", status_code=202)
async def play_suggestions(svc: Svc) -> dict[str, bool]:
    """Puts Propozycje dnia on the frame: the rotation without a playlist,
    the asking person's ("Propozycje dnia" in Playlisty)."""
    svc.player.play_suggestions(viewer_id())
    settings = svc.player.settings
    settings.playlist_id = None
    svc.player.save_settings(settings)
    svc.player.set_hold(None)
    svc.background(svc.player.next("playlist", picks=False))  # its own first picture
    return {"accepted": True}


def _theme_list(svc: FrameService) -> list[ThemeCard]:
    cards = _theme_cards(svc)
    playlists = svc.library.playlists(viewer_id())
    # The week's themes and "Ponieważ lubisz" once the cards have them
    # (worked out with them), the latter before the week's pairs.
    weekly = [t for t in for_you(svc.library, date.today()) if t.key in cards]
    mine = [t for t in liked(svc.library) if t.key in cards]
    pairs = [t for t in weekly if t.key.startswith(MIX_PREFIX)]
    weekly = [t for t in weekly if t not in pairs]
    colours = [t for t in colour_themes(svc.library, date.today()) if t.key in cards]
    every = [*weekly, *mine, *pairs, *THEMES, *OTHER_ART_THEMES, *colours]
    private = svc.player.settings.private_use
    every = [t for t in every if private or not t.private]
    # A card with too few works for a cover is not shown (it comes back
    # once the catalogue has them; the night looks for those of "Sztuki
    # inne" first, Player._add_other_art).
    every = [t for t in every if cards.get(t.key, (0, []))[0] >= CARD_MIN]
    ordered = sorted(every, key=lambda t: GROUPS.index(t.group))
    hidden = svc.library.hidden()  # once, not for each card
    return [_card(svc, t, cards, playlists, hidden) for t in ordered]


def _page_key(found: Theme, page: int, user: str) -> PageKey:
    """A theme's page of the catalogue for ``user``: by the theme's rules too
    (the curator's and "Bo lubisz" cards keep their key with new rules)."""
    return (found.key, found.rules().model_dump_json(), page, user)


def _page_stamp(svc: FrameService, day: date) -> PageStamp:
    """What a theme's page was worked out from: the catalogue and the day
    (the good works come in another order each day, ``library.good``)."""
    return (*svc.library.catalogue_stamp(), day.toordinal())


def _work_out_page(svc: FrameService, found: Theme, page: int, user: str) -> tuple[int, list[Item]]:
    pages = _pages_of(svc.library)
    key = _page_key(found, page, user)
    try:
        day = date.today()
        stamp = _page_stamp(svc, day)
        total, items = svc.library.query(
            found.rules(),
            sort="good",
            seed=day.toordinal(),
            offset=(page - 1) * ROW_SIZE,
            limit=ROW_SIZE,
            user=user,
            proposing=True,
        )
        pages.keep(key, stamp, total, items)
        return total, items
    finally:
        with pages.lock:
            pages.working.discard(key)


def catalogue_page(svc: FrameService, found: Theme, page: int = 1) -> tuple[list[Item], bool]:
    """A page of the catalogue's works that fit ``found``, best first, and
    whether more follow. A query of the whole catalogue takes seconds on the
    NAS (Mateusz 2026-11-06: a set took ~10 s to show its first works), so
    the page as last worked out comes at once, also after the catalogue
    changed (works the server adds in the background) and on another day
    (the night works out every theme's first page of the day); it is worked
    out again in the background then, for the next visit. The cards
    (:func:`work_out_cards`) work out every theme's first page."""
    pages = _pages_of(svc.library)
    user = viewer_id()
    key = _page_key(found, page, user)
    with pages.lock:
        kept = pages.kept.get(key)
        stale = kept is not None and kept[0] != _page_stamp(svc, date.today())
        again = stale and key not in pages.working
        if again:
            pages.working.add(key)
    if kept is None:
        total, items = _work_out_page(svc, found, page, user)
    else:
        _, total, items = kept
        if again:
            threading.Thread(
                target=_work_out_page, args=(svc, found, page, user), daemon=True
            ).start()
    return items, page * ROW_SIZE < total


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
    suggestion_rows(svc)


def _theme(key: str, svc: FrameService, page: int = 0) -> Theme:
    """The theme ``key``; its first ``page`` opened marks the curator's
    card as seen (made again the next night)."""
    try:
        found = theme(key, svc.library)
    except KeyError as err:
        raise HTTPException(404, str(err)) from err
    if found.private and not svc.player.settings.private_use:
        raise HTTPException(404, f"{key}: only with private use")
    if page == 1:
        curated_seen(svc.library, key)
    return found


def _new_artist(svc: FrameService) -> ThemeCard | None:
    """Another artist of the week, with its card worked out at once (the
    other cards stay as they are)."""
    global _cards
    found = new_artist_of_the_week(svc.library, date.today())
    if found is None:
        return None
    day = date.today()
    total, items = svc.library.query(
        found.rules(), sort="good", seed=day.toordinal(), proposing=True
    )
    cover = _cover(items, f"{day.isoformat()}:{found.key}", found)
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
    found = await run_in_threadpool(_theme, key, svc, page)
    if not found.searches():
        items, more = await run_in_threadpool(catalogue_page, svc, found, page)
        return ThemePage(
            items=remote_items(svc, items), more=more, next_page=page + 1 if more else None
        )
    try:
        items, following = await run_in_threadpool(
            urgent_call(browse_theme), svc.importer, found, page, ROW_SIZE
        )
    except (httpx.HTTPError, ValueError) as err:
        raise HTTPException(502, f"{key}: {err}") from err
    await run_in_threadpool(svc.importer.measure, items)
    if kept_close(found):
        svc.player.keep_searched(items)
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
    asked = time.monotonic()
    found = await run_in_threadpool(_theme, key, svc, page)
    if not found.searches():  # the catalogue: one page at once
        items, more = await run_in_threadpool(catalogue_page, svc, found, page)
        line = await run_in_threadpool(lambda: ThemeLine(items=remote_items(svc, items)))
        log.info(
            "theme %s, catalogue page %d: %d works in %.1f s",
            key,
            page,
            len(line.items),
            time.monotonic() - asked,
        )

        async def once() -> AsyncIterator[str]:
            yield line.model_dump_json() + "\n"
            last = ThemeLine(end=True, more=more, next_page=page + 1 if more else None)
            yield last.model_dump_json() + "\n"

        return StreamingResponse(once(), media_type="application/x-ndjson")

    pages = batch_of(found, page, THEME_BATCH)
    close = kept_close(found)
    loop = asyncio.get_running_loop()
    #: Works as they come; True or False when a search is over (answered or not).
    lines_: asyncio.Queue[ThemeLine | bool] = asyncio.Queue()
    #: How many works the last page's search has (whether a round follows).
    last_total = [0]
    #: Set when the app stops listening.
    gone = threading.Event()

    #: Works sent, by page, and when the first search began (for the log).
    sent: dict[int, int] = {}
    started: dict[str, float] = {}

    def ask(at: int) -> None:
        ok = False
        try:
            if gone.is_set():
                return  # the app left before this search's turn
            started.setdefault("at", time.monotonic())
            items, total = search_page(svc.importer, found, at, ROW_SIZE)
            ok = True
            if close:  # antiquity, Sztuki inne: what was found stays for next time
                svc.player.keep_searched(items)
            if at == pages[-1]:
                last_total[0] = total
            if items and not gone.is_set():
                svc.importer.measure(items)
                line = ThemeLine(items=remote_items(svc, items))
                sent[at] = len(line.items)
                loop.call_soon_threadsafe(lines_.put_nowait, line)
        except (httpx.HTTPError, ValueError) as err:
            log.warning("theme %s: page %d failed: %s", key, at, err)
        except Exception:
            log.exception("theme %s: page %d failed", key, at)
        finally:
            loop.call_soon_threadsafe(lines_.put_nowait, ok)

    def stocked() -> None:
        """The works of the set the catalogue holds, shown before the
        museums answer (its page as last worked out comes at once, and a
        slow one does not hold the museums' lines up); the museums' copies
        of them are left out by the app. Every set opens with them: the
        museums take 1–4 s, more while the server is busy (Mateusz
        2026-11-06: ~10 s to the first works)."""
        held: list[Item] = []
        try:
            if not gone.is_set():
                held = catalogue_page(svc, found, 1)[0]
            if held and not gone.is_set():
                line = ThemeLine(items=remote_items(svc, held))
                sent[0] = len(line.items)
                loop.call_soon_threadsafe(lines_.put_nowait, line)
        except Exception:
            log.exception("theme %s: the catalogue's works failed", key)
        finally:
            loop.call_soon_threadsafe(lines_.put_nowait, bool(held))

    async def lines() -> AsyncIterator[str]:
        asking = []
        if page == 1:
            # A head start, so that its line comes first (at once when it
            # was worked out before); a slow one does not hold the museums.
            asking.append(asyncio.ensure_future(run_in_threadpool(stocked)))
            await asyncio.wait(asking, timeout=CATALOGUE_HEAD_START)
        asking += [asyncio.ensure_future(run_in_threadpool(urgent_call(ask), at)) for at in pages]
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
            log.info(
                "theme %s, pages %d-%d: %s works in %.1f s (searches from %.1f s)%s",
                key,
                pages[0],
                pages[-1],
                "+".join(str(sent.get(at, 0)) for at in [*([0] if 0 in sent else []), *pages]),
                time.monotonic() - asked,
                started.get("at", asked) - asked,
                "" if answered else ", no museum answered",
            )
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
                fill_card(svc.importer, rules, POOL_SIZE - have, job, pooled=True)

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


#: "vermeer's" is Vermeer.
_POSSESSIVE = re.compile(r"['’]s?$")


def _term_hits(
    svc: FrameService, text: str, limit: int, gone: Callable[[], bool] = lambda: False
) -> list[TermHit]:
    """Artists, the works' keywords ("wielka fala"), the vocabulary's terms
    and the typed words last (always there: the app's Return puts them in).
    ``gone``: the asker typed on meanwhile, nothing more is counted."""
    index = svc.library.term_index()
    words = text.strip()
    hits = [
        TermHit(kind="artist", key=name, name=name, count=count)
        for name, count in index.artists(text, limit=4)
    ]
    # A keyword that is an artist's name ("Johannes Vermeer", "johannes
    # vermeer's") is their row already (Mateusz 2026-11-09).
    named = {
        fold(spelling)
        for hit in hits
        for spelling in index.names.spellings.get(hit.name, [hit.name])
    }
    # Works whose title has the words, as typed or as the museums were
    # asked them ("gwiaździsta noc", "starry night"): no count, a title
    # is mostly one work (Mateusz 2026-11-13). A title the words are comes
    # right after the artists, one they are only in after the keywords.
    titled = (
        [
            TermHit(
                kind="title",
                key=t.title,
                name=t.title,
                detail=index.names.shown(t.artist) if t.artist else "",
                item=t.item_id,
                exact=t.exact,
            )
            for t in index.titles([words, *_title_forms(svc, words)])
        ]
        if words
        else []
    )
    hits += [t for t in titled if t.exact]
    hits += [
        TermHit(kind="word", key=phrase, name=phrase, count=index.word_count(phrase))
        for phrase in index.phrases(text, limit=4)
        if fold(phrase) != fold(words) and _POSSESSIVE.sub("", fold(phrase)) not in named
    ][:3]
    hits += [t for t in titled if not t.exact]
    for found in suggest(text, limit=max(limit - len(hits), 3)):
        if gone():
            return []
        detail = ", ".join(w.rstrip("*") for w in found.words[:3])
        kind = "period" if found.kind == "years" else found.kind
        count = index.term_count(found.key)
        hits.append(TermHit(kind=kind, key=found.key, name=found.name, detail=detail, count=count))
    hits = hits[:limit]
    if words and not gone():
        hits.append(TermHit(kind="word", key=words, name=words, count=index.word_count(words)))
    return hits


#: Threads counting the suggestions while typing, apart from the server's
#: own pool. A count goes through the whole catalogue until its search
#: index is made (after a start, after the night's import): dozens of them
#: at once, one a letter, took every thread and stood the server still for
#: minutes, the frame's preview and the panel too (2026-11-13).
TERM_THREADS = CapacityLimiter(2)

#: The last question of each asker (by their token): one asked before it
#: was given up by the app when the next letter came.
_TERMS_ASKED: dict[str, int] = {}
_TERMS_LOCK = threading.Lock()
#: How long the suggestions wait for the English and French of two words
#: or more, for the titles ("gwiaździsta noc": "The Starry Night").
TITLE_TRANSLATE_SECONDS = 0.6


def _title_forms(svc: FrameService, words: str) -> tuple[str, ...]:
    """The words as the museums are asked them: known already, or for two
    words or more a moment's wait for the translation."""
    if " " in words and len(words) >= 5:
        said = svc.importer.wording(words, TITLE_TRANSLATE_SECONDS)
        return tuple(w for w in (said.en, said.fr) if w)
    return svc.library.wording(words) if svc.library.wording else ()


@router.get("/terms", response_model=list[TermHit])
async def terms(
    request: Request, svc: Svc, q: str, limit: Annotated[int, Query(ge=1, le=20)] = 10
) -> list[TermHit]:
    """What ``q`` could mean: artists in the library, styles, subjects,
    periods and techniques, and the plain words; each with how many works
    in the catalogue fit. A question the same asker followed with another
    before its turn came is answered with nothing (the app has let it go)."""
    who = hashlib.sha256(request.headers.get("authorization", "").encode()).hexdigest()
    with _TERMS_LOCK:
        turn = _TERMS_ASKED[who] = _TERMS_ASKED.get(who, 0) + 1

    def gone() -> bool:
        return _TERMS_ASKED.get(who) != turn

    def answer() -> list[TermHit]:
        if gone():
            return []
        try:
            with asked_by(gone):  # a count under way stops with the next letter
                return _term_hits(svc, q, limit, gone)
        except Abandoned:
            return []

    return await to_thread.run_sync(answer, limiter=TERM_THREADS)


#: Threads for asking the museums, apart from the server's own pool: a
#: search's stream asks some 19 sources at once, and two quick searches took
#: the shared pool's 40 threads, so the catalogue's answer, the quickest of
#: all, waited behind them (2026-11-09: 21 s).
MUSEUM_THREADS = CapacityLimiter(24)


#: How long the museums' hint, asked while typing, waits for the words'
#: translation (a later answer serves the next one).
HINT_TRANSLATE_SECONDS = 2.5


@router.get("/terms/museums", response_model=MuseumHint)
async def terms_in_museums(svc: Svc, q: str) -> MuseumHint:
    """What the museums have for ``q``: how many works, the artists among
    the first results whose names fit, and a few of the works."""
    words = q.strip()
    if not words:
        return MuseumHint(total=0, artists=[], items=[])
    # What is typed becomes one token: a phrase when it has several words.
    asked = await to_thread.run_sync(
        svc.importer.asked, quote([words]), None, HINT_TRANSLATE_SECONDS, limiter=MUSEUM_THREADS
    )
    # Only what is kept at home (the museums' dumps and lists): asking every
    # museum at each letter typed took 40-90 s and the museums' patience
    # (Mateusz 2026-11-09: the hint from local dumps only).
    total, items, _ = await to_thread.run_sync(
        svc.importer.at_home, asked.texts, 8, limiter=MUSEUM_THREADS
    )
    failed: list[str] = []
    items = [i for i in items if not against(i, Place.SOUGHT) and says(i, asked.said)]
    wanted = fold(words)
    known = known_names()  # one row for Rembrandt, however a museum spells him
    names: Counter[str] = Counter(
        known.shown(i.artist) for i in items if wanted in fold(i.artist) and is_artist(i.artist)
    )
    artists = [TermHit(kind="artist", key=n, name=n, count=c) for n, c in names.most_common(3)]
    return MuseumHint(
        total=total, artists=artists, items=remote_items(svc, items[:8]), failed=failed
    )


# -- places ------------------------------------------------------------------------

#: Letters typed before Wikidata is asked for museums no work is in yet.
PLACE_SEARCH_LETTERS = 3


@router.get("/places", response_model=list[PlaceHit])
async def places(
    svc: Svc, q: str = "", limit: Annotated[int, Query(ge=1, le=500)] = 200
) -> list[PlaceHit]:
    """Szukaj's "Muzeum": the places of the catalogue's works, the one with
    most first, then the museums of our sources with none yet; with ``q``,
    those whose name or town has it, and museums Wikidata knows by it."""
    rows = await run_in_threadpool(svc.library.places)
    offered = set(svc.importer.sources())
    hits = [PlaceHit(**row.model_dump()) for row in rows]
    have = {h.key for h in hits}
    hits += [
        PlaceHit(key=p.key, name=p.name, city=p.city, source=p.source)
        for p in OWN.values()
        if p.key not in have and p.source in offered
    ]
    known = known_places()
    # Museums the playlists choose or leave out, with no work here yet:
    # the app names their chips by this list.
    have = {h.key for h in hits}
    chosen = [
        key
        for playlist in await run_in_threadpool(svc.library.playlists)
        for key in (*playlist.rules.places, *playlist.rules.exclude_places)
    ]
    for key in dict.fromkeys(chosen):
        if key not in have and (name := known.name(key)):
            place = known.place(key)
            hits.append(PlaceHit(key=key, name=name, city=place.city if place else ""))
    hits = [
        h.model_copy(update={"picture": commons_picture(file)})
        if not h.item_id and (file := known.picture(h.key))
        else h
        for h in hits
    ]
    words = fold(q)
    if words:
        hits = [h for h in hits if words in fold(f"{h.name} {h.city}")]
    if len(words) >= PLACE_SEARCH_LETTERS:
        try:
            extra = await run_in_threadpool(urgent_call(svc.museum_places.hits), q)
        except (httpx.HTTPError, ValueError) as err:
            log.info("museums named %r: %s", q, err)
            extra = []
        have = {h.key for h in hits}
        hits += [h for h in extra if h.key not in have]
    merged, learnt = _one_each(hits)
    if learnt:
        await run_in_threadpool(svc.library.save_places)
    return merged[:limit]


def _one_each(hits: list[PlaceHit]) -> tuple[list[PlaceHit], bool]:
    """One row for each museum: the catalogue's "Prado" whose works only
    named it (``name:prado``, the night not having asked Wikidata yet) and
    Wikidata's Prado typed are one, with Wikidata's key (learnt from then
    on) and the catalogue's work (Mateusz 2026-11-08: "Nawet 2x?"). Also
    whether a name was learnt so."""
    known = known_places()
    learnt = False
    out: list[PlaceHit] = []
    by_name: dict[str, int] = {}
    for hit in hits:
        name = fold(hit.name)
        at = by_name.get(name)
        if at is None:
            by_name[name] = len(out)
            out.append(hit)
            continue
        first = out[at]
        if first.key.startswith(NAME_KEY) and QID.match(hit.key):
            # The night would learn it so: the name is that museum.
            known.alias(first.name, hit.key)
            learnt = True
            out[at] = first.model_copy(
                update={"key": hit.key, "city": first.city or hit.city, "source": hit.source}
            )
        elif first.city and hit.city and fold(first.city) != fold(hit.city):
            out.append(hit)  # two museums of one name, in two towns
    return out, learnt


class PlacePicture(BaseModel):
    #: The address of a picture of a work in the place, "" when none is known.
    picture: str = ""


@router.get("/places/{key}/picture", response_model=PlacePicture)
async def place_picture(svc: Svc, key: str) -> PlacePicture:
    """A picture of a work in a place with none in the catalogue (Prado
    typed in Szukaj): Wikidata's, looked for once and kept."""
    try:
        file = await run_in_threadpool(urgent_call(svc.museum_places.picture), key)
    except (httpx.HTTPError, ValueError, KeyError) as err:
        log.info("picture of %s: %s", key, err)
        return PlacePicture()
    return PlacePicture(picture=commons_picture(file) if file else "")


# -- searching the museums --------------------------------------------------------


def rules_from(
    q: str = "",
    artists: list[str] | None = None,
    terms: list[str] | None = None,
    colors: list[str] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    title: str = "",
    look: str = "",
) -> PlaylistRules:
    return PlaylistRules(
        query=q,
        title=" ".join(title.split()),
        look=" ".join(look.split()),
        artists=artists or [],
        terms=terms or [],
        colors=colors or [],
        year_from=year_from,
        year_to=year_to,
    )


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
    skip: list[str] | None = None,
    place: list[str] | None = None,
    skip_place: list[str] | None = None,
    title: str = "",
    look: str = "",
) -> MuseumSearch:
    # The sources to ask: a page further of one the search's answers named
    # ("rijks", "wd:Q160112|Q1"), or an older app's museums.
    keys = [s for s in dict.fromkeys(source or []) if s != ALL]
    # An older app's museums left out: a museum's own collection is its
    # places now (PlaylistRules), the others stay sources.
    left_out, skip = migrate_sources(dict.fromkeys(skip or []))
    offered = {*svc.importer.sources(), *svc.importer.reachable()}
    if unknown := [s for s in keys if s not in offered and not places_in(s)]:
        raise HTTPException(404, f"unknown museum {unknown[0]!r}")
    rules = rules_from(q, artist, term, color, year_from, year_to, title, look)
    # Museums left out need not be on offer (any more): they just stay out.
    return MuseumSearch.of(
        rules,
        keys=keys,
        limit=limit,
        skip=skip,
        places=place or [],
        skip_places=[*(skip_place or []), *left_out],
    )


def keep_found(svc: FrameService, search: MuseumSearch, found: list[RemoteItem]) -> None:
    """What the owner looks for, into the catalogue, remembering the search:
    the library then counts it in for the same choices (a smart playlist of
    them too), and so do Szukaj's next searches."""
    key = search.key
    for remote in found:
        if remote.in_library:
            svc.library.found(remote.item.id, key)
        if remote.twin is not None:
            svc.library.found(remote.twin, key)
    svc.player.keep_searched((r.item for r in found if not r.in_library), found=key)


def keeper(svc: FrameService) -> Callable[[list[Item]], None]:
    """Where a search's works that don't fit go (:meth:`MuseumSearch.pages`):
    into the catalogue after the shown ones, but not those the owner hid
    or that have no picture (Mateusz 2026-11-07: "szkoda byłoby tracić te
    odpytania")."""

    def keep(items: list[Item]) -> None:
        gone = svc.images.gone_ids()
        hidden = svc.library.hidden()
        svc.player.keep_spare(i for i in items if i.id not in gone and i not in hidden)

    return keep


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
    skip: Sources = None,
    place: Sources = None,
    skip_place: Sources = None,
    page: Page = 1,
    limit: Limit = 8,
    title: str = "",
    look: str = "",
) -> MuseumAnswer:
    """The museums' works for what Discover's search asks (``limit`` from
    each museum; every museum, or those of ``source``, without those of
    ``skip``): their own search for words, artists, styles and subjects,
    else works of the periods and technique; with ``color``, those whose
    thumbnails have the colours."""
    search = museum_search(
        svc,
        q,
        artist,
        term,
        color,
        year_from,
        year_to,
        source,
        limit,
        skip,
        place,
        skip_place,
        title,
        look,
    )
    # With none left out, no keys still means every museum.
    # Sources of one kind only (the Library of Congress's photographs) just
    # when that kind is asked for.
    offered = svc.importer.asked_sources(search.spec.kind)
    narrowed = search.skip or search.places or search.skip_places
    keys = search.asked(offered, svc.importer.reachable()) if narrowed else search.keys
    if search.empty or (narrowed and not keys):
        return MuseumAnswer(source=ALL, total=0, items=[])
    total, items, failed, next_ = await to_thread.run_sync(
        urgent_call(search.ask), svc.importer, keys, page, keeper(svc), limiter=MUSEUM_THREADS
    )
    if keys and len(failed) == len(keys):
        raise HTTPException(502, f"{', '.join(failed)} did not answer")
    found = remote_items(svc, items, copies=len(keys) != 1)
    keep_found(svc, search, found)
    return MuseumAnswer(
        source=keys[0] if len(keys) == 1 else ALL,
        total=total,
        items=found,
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
    skip: Sources = None,
    place: Sources = None,
    skip_place: Sources = None,
    page: Page = 1,
    limit: Limit = 8,
    title: str = "",
    look: str = "",
) -> StreamingResponse:
    """Like ``/discover/search``, as the museums answer: a
    :class:`MuseumAnswer` per museum page (JSON lines), with colours several
    pages of each museum. A work comes once, from whichever museum answers
    first, unless a more reliable one brings it later (``replaces``)."""
    search = museum_search(
        svc,
        q,
        artist,
        term,
        color,
        year_from,
        year_to,
        source,
        limit,
        skip,
        place,
        skip_place,
        title,
        look,
    )
    keys = search.asked(svc.importer.asked_sources(search.spec.kind), svc.importer.reachable())
    copies = len(keys) != 1
    shown = shown_in(search.rules, page)
    if page == 1:
        svc.player.searched_for(search.rules.artists, viewer_id())

    loop = asyncio.get_running_loop()
    answers: asyncio.Queue[MuseumAnswer | None] = asyncio.Queue()
    #: Set when the app stops listening: no more pages are asked for.
    gone = threading.Event()

    spare = keeper(svc)

    def ask(key: str) -> None:
        """One museum's pages onto ``answers``, then None."""
        try:
            for total, items, failed, next_ in search.pages(svc.importer, [key], page, spare):
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
                keep_found(svc, search, new)
        except Exception:
            log.exception("searching %s failed", key)
            failure = MuseumAnswer(source=key, total=0, items=[], failed=[key])
            loop.call_soon_threadsafe(answers.put_nowait, failure)
        finally:
            loop.call_soon_threadsafe(answers.put_nowait, None)

    async def lines() -> AsyncIterator[str]:
        asking = [
            asyncio.ensure_future(to_thread.run_sync(urgent_call(ask), k, limiter=MUSEUM_THREADS))
            for k in keys
        ]
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
