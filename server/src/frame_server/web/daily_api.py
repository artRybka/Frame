"""Discover's work of the day: the tile at the top of Propozycje and its page."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai.daily import Composition, Essay, Fact, Legacy
from ..ai.pl_text import description
from ..imaging.text import sentences
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
#: The tile's two lines when the model wrote nothing.
TEASER_MAX = 200


class SimilarWork(BaseModel):
    item: RemoteItem
    why: str = ""


class LegacyWork(Legacy):
    #: The catalogue's copy of the later work, when it has one.
    item: RemoteItem | None = None


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
    why_today: str = ""
    #: The model is writing the page now.
    writing: bool = False
    #: The model wrote the page (else only what the museum says).
    written: bool = False
    context: list[str] = []
    facts: list[Fact] = []
    composition: Composition | None = None
    colour: str = ""
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


def _teaser(text: str) -> str:
    chosen: list[str] = []
    for sentence in sentences(text):
        if chosen and sum(len(s) + 1 for s in chosen) + len(sentence) > TEASER_MAX:
            break
        chosen.append(sentence)
    teaser = " ".join(chosen)
    return teaser if len(teaser) <= TEASER_MAX + 60 else teaser[:TEASER_MAX].rsplit(" ", 1)[0] + "…"


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
        teaser=essay.teaser if essay else _teaser(museum),
        why_today=essay.why_today if essay else "",
        writing=writing and essay is None,
        written=essay is not None,
        context=essay.context
        if essay and essay.context
        else [p for p in museum.split("\n\n") if p],
        facts=essay.facts if essay else [],
        composition=essay.composition if essay and essay.composition.points else None,
        colour=essay.colour if essay else "",
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
