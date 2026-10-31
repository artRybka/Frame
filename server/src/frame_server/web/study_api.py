"""A study of any work, asked for on its card ("Przygotuj studium dzieła"):
the work of the day's page for the work, written by Claude and kept."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai.daily import Detail
from ..library import Item
from ..library.markup import strip_markup
from ..service import FrameService
from ..study import PENDING, Status
from .daily_api import DailyWork, page
from .deps import require_token, service
from .library_api import RemoteItem, remote_items
from .library_api import _work as find_work

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]


class StudyView(BaseModel):
    """Where the work's study is: "off" (no key), "none" (not asked for),
    on its way ("waiting", "sources", "writing", "details"), "ready" (with
    the page in ``work``) or "failed" (``error`` says why)."""

    status: Status
    error: str = ""
    work: DailyWork | None = None
    #: What a study costs, about (USD).
    cost_usd: float = 0.0


def _view(svc: FrameService, item: Item | None) -> StudyView:
    status, error = svc.study.status(item)
    work = None
    if item is not None and status in ("ready", "details"):

        def detail_url(n: int, box: Detail) -> str:
            v = svc.daily.detail_path(item, box).stem.rsplit("-", 1)[-1]
            return f"/api/study/{quote(item.id, safe='')}/detail?n={n}&v={v}"

        work = page(svc, item, svc.study.job, day="", writing=False, url=detail_url)
        work = work.model_copy(update={"why_today": ""})
    cost = svc.study.job.estimate_usd(1, batch=False)
    return StudyView(status=status, error=error, work=work, cost_usd=round(cost, 2))


class StudyBrief(BaseModel):
    """A work with a study or a work of the day's page, for Discover's row
    "Studia dzieł"."""

    item: RemoteItem
    #: The Polish title the study gives it.
    title: str
    #: A work of the day: its (last) day, whose page opens; else its study.
    day: str | None = None


def _briefs(svc: FrameService) -> list[StudyBrief]:
    written = svc.study.written()
    remote = remote_items(svc, [item for item, _, _ in written], copies=False)
    return [
        StudyBrief(
            item=r.model_copy(update={"item": _plain(r.item)}),
            title=essay.title or strip_markup(r.item.title),
            day=day.isoformat() if day else None,
        )
        for r, (_, essay, day) in zip(remote, written, strict=True)
    ]


def _plain(item: Item) -> Item:
    return item.model_copy(update={"description": "", "artist_bio": ""})


@router.get("/studies", response_model=list[StudyBrief])
async def studies(svc: Svc) -> list[StudyBrief]:
    """Every work with a study or a work of the day's page, the last
    written first."""
    return await run_in_threadpool(_briefs, svc)


async def _wait(svc: FrameService, item: Item | None, wait: float) -> None:
    """Up to ``wait`` seconds for the study on its way to move on."""
    if item is None or not wait:
        return
    status = svc.study.status(item)[0]
    loop = asyncio.get_running_loop()
    end = loop.time() + wait
    while status in PENDING and svc.study.status(item)[0] == status and loop.time() < end:
        await asyncio.sleep(0.5)


@router.get("/study/{item_id}", response_model=StudyView)
async def study(
    item_id: str, svc: Svc, wait: Annotated[float, Query(ge=0, le=60)] = 0
) -> StudyView:
    """The work's study, if there is one; ``wait``: seconds to wait for one
    on its way to get a step further."""
    item = svc.library.get(item_id)
    await _wait(svc, item, wait)
    return await run_in_threadpool(_view, svc, item)


@router.post("/study/{item_id}", response_model=StudyView)
async def prepare_study(
    item_id: str,
    svc: Svc,
    again: bool = False,
    wait: Annotated[float, Query(ge=0, le=60)] = 0,
) -> StudyView:
    """Asks Claude for the work's study (``again``: a new one, though there
    is one); a museum work only looked at is kept in the library for it."""
    item = await find_work(svc, item_id)
    if not svc.study.job.enabled():
        raise HTTPException(409, "Claude jest wyłączony: dodaj klucz API w Konfiguracji.")
    if svc.library.get(item_id) is None:  # a museum work only looked at: pooled
        item = await run_in_threadpool(svc.importer.add, item.model_copy(update={"pooled": True}))
    future = await run_in_threadpool(svc.study.ask, item, again)
    if future is not None and wait:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
    return await run_in_threadpool(_view, svc, item)


@router.get("/study/{item_id}/detail")
async def study_detail(
    item_id: str, svc: Svc, n: Annotated[int, Query(ge=0, le=9)] = 0
) -> FileResponse:
    """A fragment of the work's study ("Detale"), cut from its original."""
    item = svc.library.get(item_id)
    path = await run_in_threadpool(svc.study.detail, item, n) if item is not None else None
    if path is None:
        raise HTTPException(404, "no such fragment")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=604800"})
