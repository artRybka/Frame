"""Discover: Suggestions, themes and museum browsing, all live from museums."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..library import Item, ItemKind, PlaylistRules
from ..library.museums import Discovery, Kind
from ..library.seed import PACKS, browse_theme, pack, theme_of_the_day
from ..service import FrameService
from .deps import require_token, service
from .library_api import RemoteItem, RemotePage

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]

ROW_SIZE = 24
#: The best on e-paper row: suitability from this up.
BEST_SUITABILITY = 0.72

#: The theme of the day's first page, fetched once a day.
_theme_rows: dict[date, list[Item]] = {}


class Theme(BaseModel):
    key: str
    name: str
    description: str


class SuggestionRow(BaseModel):
    key: str  # "for-you", "theme", "best"
    title: str
    subtitle: str = ""
    theme: str | None = None  # the theme to browse further
    items: list[RemoteItem]


class ThemePage(BaseModel):
    items: list[RemoteItem]
    more: bool


def _remote(svc: FrameService, items: list[Item]) -> list[RemoteItem]:
    return [RemoteItem(item=i, in_library=svc.library.has(i.id)) for i in items]


@router.get("/suggestions", response_model=list[SuggestionRow])
async def suggestions(svc: Svc) -> list[SuggestionRow]:
    """What Discover opens with: the works the server picked for the frame,
    the theme of the day and what looks best on e-paper."""
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
    theme = theme_of_the_day(today)
    if today not in _theme_rows:
        try:
            items, _ = await run_in_threadpool(browse_theme, svc.importer, theme, 1, ROW_SIZE)
            _theme_rows.clear()
            _theme_rows[today] = items
        except (httpx.HTTPError, ValueError):
            pass  # the row comes back once the museum answers
    if _theme_rows.get(today):
        rows.append(
            SuggestionRow(
                key="theme",
                title=f"Motyw dnia: {theme.name}",
                subtitle=theme.description,
                theme=theme.key,
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
                items=_remote(svc, best[:ROW_SIZE]),
            )
        )
    return rows


@router.get("/themes", response_model=list[Theme])
def themes() -> list[Theme]:
    return [Theme(key=p.key, name=p.name, description=p.description) for p in PACKS]


@router.get("/themes/{key}", response_model=ThemePage)
async def theme_page(key: str, svc: Svc, page: Annotated[int, Query(ge=1)] = 1) -> ThemePage:
    """A theme, page by page, straight from the museums."""
    try:
        theme = pack(key)
    except KeyError as err:
        raise HTTPException(404, str(err)) from err
    try:
        items, more = await run_in_threadpool(browse_theme, svc.importer, theme, page, ROW_SIZE)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{key}: {err}") from err
    return ThemePage(items=_remote(svc, items), more=more)


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
    items = [i for i in items if spec.fits(i)]
    return RemotePage(total=total, items=_remote(svc, items), failed=failed)
