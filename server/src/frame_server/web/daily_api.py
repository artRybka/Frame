"""Discover's work of the day: the tile at the top of Propozycje and its page."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai.daily import TEASER_CHARS, Composition, Detail, Essay, Legacy, Spot, short
from ..ai.pl_text import description
from ..library import Item, PlaylistRules
from ..library.markup import strip_markup
from ..library.vocabulary import artist_matches
from ..service import FrameService
from .deps import require_token, service
from .library_api import RemoteItem, remote_items

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]

#: Past days listed under the page.
PREVIOUS = 7
#: The text's title when only the museum speaks.
MUSEUM_HEADLINE = "Co mówi muzeum"


class SimilarWork(BaseModel):
    item: RemoteItem
    why: str = ""


class LegacyWork(Legacy):
    #: The catalogue's copy of the later work, when it has one.
    item: RemoteItem | None = None


class DailyDetail(Detail):
    #: The fragment cut from the original (``GET /api/daily/detail``).
    image: str


class DailyBrief(BaseModel):
    day: str
    item: RemoteItem
    title: str


class DailyWork(BaseModel):
    day: str
    item: RemoteItem
    #: The Polish title when there is one.
    title: str
    teaser: str = ""
    #: Where the tile's band is cropped around (fractions of the picture).
    focus: Spot | None = None
    why_today: str = ""
    #: The model is writing the page now.
    writing: bool = False
    #: The model wrote the page (else only what the museum says).
    written: bool = False
    #: The title of the text below.
    headline: str = ""
    context: list[str] = []
    #: A short note about the artist.
    artist: str = ""
    #: Left empty: read by 0.42 apps.
    facts: list[dict[str, str]] = []
    composition: Composition | None = None
    colour: str = ""
    details: list[DailyDetail] = []
    on_frame: str = ""
    similar: list[SimilarWork] = []
    legacy: list[LegacyWork] = []
    sources: list[str] = []
    model: str = ""
    previous: list[DailyBrief] = []


def _light(svc: FrameService, item: Item) -> RemoteItem:
    remote = remote_items(svc, [item], copies=False)[0]
    return remote.model_copy(
        update={"item": remote.item.model_copy(update={"description": "", "artist_bio": ""})}
    )


def _title(svc: FrameService, item: Item, essay: Essay | None) -> str:
    if essay and essay.title:
        return essay.title
    polish = svc.pl_text.text(item)
    return polish.title if polish else strip_markup(item.title)


def _museum_text(svc: FrameService, item: Item) -> str:
    """What the museum says (in Polish once translated); "" when nothing."""
    polish = svc.pl_text.text(item)
    return polish.full if polish else description(item)


def _later(svc: FrameService, entry: Legacy, item: Item) -> RemoteItem | None:
    """The catalogue's copy of a later work, by its author and title."""
    if not entry.search:
        return None
    hits = svc.library.query(PlaylistRules(query=entry.search), sort="suitability", limit=5)[1]
    for hit in hits:
        if hit.id != item.id and hit.artist and artist_matches(hit.artist, [entry.who]):
            return _light(svc, hit)
    return None


def _brief(svc: FrameService, day: str, item: Item) -> DailyBrief:
    return DailyBrief(
        day=day, item=_light(svc, item), title=_title(svc, item, svc.daily.job.essay(item))
    )


def _work(svc: FrameService, day: date, item: Item, writing: bool) -> DailyWork:
    job = svc.daily.job
    essay = job.essay(item)
    museum = _museum_text(svc, item)
    candidates = svc.daily.candidates(item)
    if essay is not None:
        by_id = {c.id: c for c in candidates}
        similar = [
            SimilarWork(item=_light(svc, by_id[s.id]), why=s.why)
            for s in essay.similar
            if s.id in by_id
        ]
        legacy = [
            LegacyWork(**entry.model_dump(), item=_later(svc, entry, item))
            for entry in essay.legacy
        ]
    else:
        similar = [
            SimilarWork(
                item=_light(svc, c),
                why="ten sam autor" if c.artist == item.artist else "",
            )
            for c in candidates[:4]
        ]
        legacy = []
    details = [
        DailyDetail(
            **box.model_dump(),
            image=f"/api/daily/detail?day={day.isoformat()}&n={n}"
            f"&v={svc.daily.detail_path(item, box).stem.rsplit('-', 1)[-1]}",
        )
        for n, box in enumerate(essay.details if essay else [])
    ]
    note = svc.library.note(item.id, job.kind) if essay else None
    history = svc.daily.history()
    previous = []
    for past in sorted((d for d in history if d < day.isoformat()), reverse=True):
        found = svc.library.get(history[past])
        if found is not None:
            previous.append(_brief(svc, past, found))
        if len(previous) == PREVIOUS:
            break
    return DailyWork(
        day=day.isoformat(),
        item=_light(svc, item),
        title=_title(svc, item, essay),
        teaser=essay.teaser if essay else short(museum, TEASER_CHARS),
        focus=essay.focus if essay else None,
        why_today=essay.why_today if essay else "",
        writing=writing and essay is None,
        written=essay is not None,
        headline=essay.headline if essay and essay.headline else MUSEUM_HEADLINE,
        context=essay.context
        if essay and essay.context
        else [p for p in museum.split("\n\n") if p],
        artist=essay.artist if essay else "",
        composition=essay.composition if essay and essay.composition.views else None,
        colour=essay.colour if essay else "",
        details=details,
        on_frame=essay.on_frame if essay else "",
        similar=similar,
        legacy=legacy,
        sources=essay.sources if essay else [],
        model=note.model if note else "",
        previous=previous,
    )


@router.get("/daily", response_model=DailyWork)
async def daily(
    svc: Svc,
    day: date | None = None,
    wait: Annotated[int, Query(ge=0, le=120)] = 0,
) -> DailyWork:
    """The work of the day (``day``: a past one), with its page as far as it
    is written; ``wait``: seconds to wait for a page being written."""
    today = date.today()
    day = day or today
    if day > today:
        raise HTTPException(400, "that day has not come yet")
    if day == today:
        item = await run_in_threadpool(svc.daily.pick, day)
    else:
        item = await run_in_threadpool(svc.daily.item, day)
    if item is None:
        raise HTTPException(404, "no work of the day")
    future = await run_in_threadpool(svc.daily.ask, item)
    if future is not None and wait:
        # Still writing, or failed: the page shows what there is.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
    writing = future is not None and not future.done()
    return await run_in_threadpool(_work, svc, day, item, writing)


@router.get("/daily/detail")
async def daily_detail(
    svc: Svc, day: date, n: Annotated[int, Query(ge=0, le=9)] = 0
) -> FileResponse:
    """A fragment of the day's work ("Detale"), cut from its original; ``v``
    in the page's address only changes it when the fragment does."""
    item = await run_in_threadpool(svc.daily.item, day)
    path = await run_in_threadpool(svc.daily.detail, item, n) if item is not None else None
    if path is None:
        raise HTTPException(404, "no such fragment")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=604800"})
