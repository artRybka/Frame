"""Discover: Suggestions and themes, the words to search by, and one search
over the catalogue and the museums."""

from __future__ import annotations

import time
from collections import Counter
from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..library import Item, ItemKind, Job, Playlist, PlaylistKind, PlaylistRules, PlaylistSummary
from ..library.importer import ALL, span
from ..library.museums import MUSEUMS, Discovery, Kind, museum
from ..library.themes import GROUPS, THEMES, Theme, browse_theme, theme, theme_of_the_day
from ..library.vocabulary import (
    TERMS,
    artist_matches,
    fold,
    is_manuscript,
    museum_kind,
    museum_queries,
    suggest,
    wants_manuscripts,
)
from ..player import POOL_SIZE
from ..service import FrameService
from .deps import require_token, service
from .library_api import RemoteItem, RemotePage

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]

ROW_SIZE = 24
#: The best on e-paper row: suitability from this up.
BEST_SUITABILITY = 0.72
#: Rows of works by artists like the ones the owner likes.
TASTE_ROWS = 2
#: Theme covers and counts are worked out again after this many seconds.
CARDS_TTL = 600.0

#: The theme of the day's first page, fetched once a day.
_theme_rows: dict[date, list[Item]] = {}
#: (when, covers and counts by theme key)
_cards: tuple[float, dict[str, tuple[int, list[Item]]]] = (0.0, {})


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
    key: str  # "for-you", "like:<theme>", "theme", "best"
    title: str
    subtitle: str = ""
    theme: str | None = None  # the theme to browse further
    items: list[RemoteItem]


class ThemePage(BaseModel):
    items: list[RemoteItem]
    more: bool


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


def _remote(svc: FrameService, items: list[Item]) -> list[RemoteItem]:
    return [RemoteItem(item=i, in_library=svc.library.has(i.id)) for i in items]


def _theme_playlist(svc: FrameService, found: Theme) -> Playlist | None:
    for playlist in svc.library.playlists():
        if playlist.theme == found.key or fold(playlist.name) == fold(found.name):
            return playlist
    return None


def _cover(items: list[Item]) -> list[Item]:
    """Four works by different artists where there are such."""
    picked: list[Item] = []
    for item in items:
        if all(item.artist != p.artist for p in picked):
            picked.append(item)
        if len(picked) == 4:
            return picked
    return (picked + [i for i in items if i not in picked])[:4]


def _theme_cards(svc: FrameService) -> dict[str, tuple[int, list[Item]]]:
    global _cards
    stamp, cards = _cards
    if cards and time.monotonic() - stamp < CARDS_TTL:
        return cards
    cards = {}
    for found in THEMES:
        total, items = svc.library.query(found.rules(), sort="suitability", limit=40)
        cards[found.key] = (total, _cover(items))
    _cards = (time.monotonic(), cards)
    return cards


def _card(svc: FrameService, found: Theme, cards: dict[str, tuple[int, list[Item]]]) -> ThemeCard:
    count, cover = cards.get(found.key, (0, []))
    playlist = _theme_playlist(svc, found)
    return ThemeCard(
        key=found.key,
        name=found.name,
        description=found.description,
        group=found.group,
        count=count,
        cover=_remote(svc, cover),
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
                items=_remote(svc, others[:ROW_SIZE]),
            )
        )
        if len(rows) == TASTE_ROWS:
            break
    return rows


@router.get("/suggestions", response_model=list[SuggestionRow])
async def suggestions(svc: Svc) -> list[SuggestionRow]:
    """What Discover opens with: the works the server picked for the frame,
    works like the ones the owner likes, the theme of the day and what looks
    best on e-paper."""
    player = svc.player
    rows = []
    picked = [i for i in player.fresh(player.suggestions()) if not i.excluded]
    if picked:
        rows.append(
            SuggestionRow(
                key="for-you",
                title="Dla Ciebie",
                subtitle="Następne w rotacji Propozycje",
                items=_remote(svc, picked[::-1][:ROW_SIZE]),
            )
        )
    today = date.today()
    rows += await run_in_threadpool(_taste_rows, svc, today)
    found = theme_of_the_day(today)
    if today not in _theme_rows:
        try:
            items, _ = await run_in_threadpool(browse_theme, svc.importer, found, 1, ROW_SIZE)
            _theme_rows.clear()
            _theme_rows[today] = items
        except (httpx.HTTPError, ValueError):
            pass  # the row comes back once the museum answers
    if _theme_rows.get(today):
        rows.append(
            SuggestionRow(
                key="theme",
                title=f"Motyw dnia: {found.name}",
                subtitle=found.description,
                theme=found.key,
                items=_remote(svc, _theme_rows[today]),
            )
        )
    rules = PlaylistRules(kinds=[ItemKind.ARTWORK], min_suitability=BEST_SUITABILITY)
    best = player.fresh(svc.library.query(rules, sort="suitability")[1])
    if best:
        rows.append(
            SuggestionRow(
                key="best",
                title="Najlepiej na e-papierze",
                subtitle="Wyraziste barwy i kontrast, które ten ekran oddaje najlepiej",
                theme="best",
                items=_remote(svc, best[:ROW_SIZE]),
            )
        )
    return rows


@router.get("/themes", response_model=list[ThemeCard])
async def themes(svc: Svc) -> list[ThemeCard]:
    """Every theme, in groups (``GROUPS`` order), with a cover from the
    catalogue and the playlist already made from it."""
    cards = await run_in_threadpool(_theme_cards, svc)
    ordered = sorted(THEMES, key=lambda t: GROUPS.index(t.group))
    return [_card(svc, t, cards) for t in ordered]


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
        items, more = await run_in_threadpool(browse_theme, svc.importer, found, page, ROW_SIZE)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{key}: {err}") from err
    return ThemePage(items=_remote(svc, items), more=more)


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
        svc.background(svc.player.next("playlist"))
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
    items = [i for i in items if not is_manuscript(i)]
    wanted = fold(words)
    names: Counter[str] = Counter(i.artist for i in items if i.artist and wanted in fold(i.artist))
    artists = [TermHit(kind="artist", key=n, name=n, count=c) for n, c in names.most_common(3)]
    return MuseumHint(total=total, artists=artists, items=_remote(svc, items[:8]), failed=failed)


# -- searching the museums --------------------------------------------------------


def _manuscripts_fit(item: Item, terms: list[str]) -> bool:
    """Pages of manuscripts only when asked for; asked for as the only
    technique, nothing else."""
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
    topics = museum_queries(rules.terms, limit=1)
    return " ".join(w for w in (rules.query.strip(), artist, *topics) if w)


@router.get("/discover/search", response_model=RemotePage)
async def search_museums(
    svc: Svc,
    q: str = "",
    artist: Annotated[list[str] | None, Query()] = None,
    term: Annotated[list[str] | None, Query()] = None,
    year_from: Annotated[int | None, Query(ge=0, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=0, le=2100)] = None,
    source: str = ALL,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=24)] = 8,
) -> RemotePage:
    """The museums' works for what Discover's search asks (``limit`` from
    each museum): their own search for words, artists, styles and subjects,
    else works of the periods and technique. Colours are only known in the
    catalogue."""
    if source != ALL and source not in MUSEUMS:
        raise HTTPException(404, f"unknown museum {source!r}")
    rules = rules_from(q, artist, term, None, year_from, year_to)
    start, end = span(rules)
    spec = Discovery(year_from=start, year_to=end, kind=museum_kind(rules.terms))
    text = museum_text(rules, page)
    # Several artists take turns, so each page asks for one of them.
    round_ = (page - 1) // len(rules.artists) + 1 if rules.artists else page
    failed: list[str] = []
    if not text and start is None and end is None and spec.kind == "any":
        return RemotePage(total=0, items=[])

    def ask() -> tuple[int, list[Item], list[str]]:
        importer = svc.importer
        if text:
            if source == ALL:
                return importer.search_all(text, limit, round_)
            return (*importer.search(source, text, limit, round_), [])
        if source == ALL:
            return importer.discover_all(spec, limit, page)
        with importer.http() as http:
            found = museum(source, http, importer.private_use()).discover(spec, limit, page)
        importer.remember(found[1])
        return (*found, [])

    try:
        total, items, failed = await run_in_threadpool(ask)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{source}: {err}") from err
    items = [i for i in items if spec.fits(i) and _manuscripts_fit(i, rules.terms)]
    return RemotePage(total=total, items=_remote(svc, items), failed=failed)


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
    items = [i for i in items if spec.fits(i) and not is_manuscript(i)]
    return RemotePage(total=total, items=_remote(svc, items), failed=failed)
