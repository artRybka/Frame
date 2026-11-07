"""A study of any work, asked for on its card ("Przygotuj studium dzieła"):
the work of the day's page for the work, written by Claude and kept."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai.composition import KIND as COMPOSITION
from ..ai.composition import PAGES, versions
from ..ai.daily import Detail
from ..ai.details import KIND as MEND
from ..library import Item
from ..library.markup import strip_markup
from ..library.vocabulary import other_art
from ..notifications import APPLE_EPOCH, PushError
from ..service import FrameService
from ..study import PENDING, Status
from ..users import User
from .daily_api import DailyWork, page
from .deps import CurrentUser, require_owner, require_token, service
from .library_api import RemoteItem, remote_items
from .library_api import _work as find_work

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]


class StudyView(BaseModel):
    """Where the work's study is: "off" (no key), "none" (not asked for),
    "later" (ordered for later, for less), on its way ("waiting",
    "sources", "writing", "details"), "ready" (with
    the page in ``work``) or "failed" (``error`` says why)."""

    status: Status
    error: str = ""
    #: On its way, the part it is at (``frame_server.study.PARTS``, or
    #: "waiting"), and once Claude writes it, since when and until when
    #: about (seconds since 2001, as the app decodes dates).
    part: str = ""
    started_at: float | None = None
    expected_end: float | None = None
    work: DailyWork | None = None
    #: What a study costs, about (USD): now, and ordered for later (the
    #: Batch API, "Przygotuj na później").
    cost_usd: float = 0.0
    later_cost_usd: float = 0.0
    #: Studies a household member may still order today (None: no limit).
    studies_left: int | None = None


def _view(
    svc: FrameService, item: Item | None, user: User | None = None, lists: bool = True
) -> StudyView:
    status, error = svc.study.status(item)
    work = None
    if item is not None and status in ("ready", "details"):

        def detail_url(n: int, box: Detail) -> str:
            v = svc.daily.detail_path(item, box).stem.rsplit("-", 1)[-1]
            return f"/api/study/{quote(item.id, safe='')}/detail?n={n}&v={v}"

        work = page(svc, item, svc.study.job, day="", writing=False, url=detail_url, lists=lists)
        # "Why today" on the day the work is the study of the day only.
        today = svc.daily.day_of(item.id) == date.today()
        essay = svc.daily.job.essay(item) if today else None
        work = work.model_copy(update={"why_today": essay.why_today if essay else ""})
    cost = svc.study.job.estimate_usd(1, batch=False)
    later = svc.study.job.estimate_usd(1, batch=True)
    left = svc.users.studies_left(user, date.today()) if user is not None else None
    progress = svc.study.progress(item.id) if item is not None and status in PENDING else None
    return StudyView(
        status=status,
        error=error,
        part=progress.part if progress else "",
        started_at=_apple(progress.started) if progress else None,
        expected_end=_apple(progress.until) if progress else None,
        work=work,
        cost_usd=round(cost, 2),
        later_cost_usd=round(later, 2),
        studies_left=left,
    )


def _apple(moment: float | None) -> float | None:
    return round(moment - APPLE_EPOCH, 3) if moment is not None else None


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
    remote = remote_items(svc, [item for item, _, _ in written], copies=False, keep_hidden=True)
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
    work = item

    def where() -> tuple[str, str]:
        progress = svc.study.progress(work.id)
        return svc.study.status(work)[0], progress.part if progress else ""

    status = where()
    loop = asyncio.get_running_loop()
    end = loop.time() + wait
    while status[0] in PENDING and where() == status and loop.time() < end:
        await asyncio.sleep(0.5)


@router.get("/study/{item_id:item}", response_model=StudyView)
async def study(
    item_id: str,
    svc: Svc,
    user: CurrentUser,
    wait: Annotated[float, Query(ge=0, le=60)] = 0,
    lists: bool = True,
) -> StudyView:
    """The work's study, if there is one; ``wait``: seconds to wait for one
    on its way to get a step further. ``lists=false``: the page without the
    lists under its text (``DailyWork.partial``), at once; the app asks for
    them next."""
    item = svc.library.get(item_id)
    if item is None and (seen := svc.importer.known(item_id)) is not None and other_art(seen):
        item = seen  # a museum work of "Sztuki inne" only looked at: no study
    await _wait(svc, item, wait)
    return await run_in_threadpool(_view, svc, item, user, lists)


@router.post("/study/{item_id:item}", response_model=StudyView)
async def prepare_study(
    item_id: str,
    svc: Svc,
    user: CurrentUser,
    again: bool = False,
    later: bool = False,
    wait: Annotated[float, Query(ge=0, le=60)] = 0,
) -> StudyView:
    """Asks Claude for the work's study (``again``: a new one, though there
    is one; ``later``: for less, through the Batch API, "Przygotuj na
    później"); a museum work only looked at is kept in the library for it.
    One ordered for later and asked for again without ``later`` is made now,
    what its batches answered not paid for again."""
    item = await find_work(svc, item_id)
    if other_art(item):
        raise HTTPException(409, "Rękopisy, fotografie, rzeźby i rzemiosło nie mają studium.")
    if not svc.study.job.enabled():
        raise HTTPException(409, "Claude jest wyłączony: dodaj klucz API w Konfiguracji.")
    status, _ = await run_in_threadpool(svc.study.status, svc.library.get(item_id))
    new = again or status in ("none", "failed")
    today = date.today()
    if new and svc.users.studies_left(user, today) == 0:
        limit = svc.users.study_limit()
        raise HTTPException(429, f"Na dziś to już {limit} studiów. Kolejne jutro.")
    if svc.library.get(item_id) is None:  # a museum work only looked at: pooled
        item = await run_in_threadpool(svc.importer.add, item.model_copy(update={"pooled": True}))
    if later and not again:
        if status == "none" or status == "failed":
            ordered = await run_in_threadpool(svc.study.ask_later, item)
            if ordered and new:
                svc.users.ordered_study(user, today)
        return await run_in_threadpool(_view, svc, item, user)
    future = await run_in_threadpool(svc.study.ask, item, again)
    if new and future is not None:
        svc.users.ordered_study(user, today)
    if future is not None and wait:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
    return await run_in_threadpool(_view, svc, item, user)


class StudyActivityToken(BaseModel):
    """A Live Activity following a study, as iOS gave its push token."""

    token: str
    sandbox: bool = False


@router.put("/study/{item_id:item}/activity", status_code=204)
async def follow_study(item_id: str, body: StudyActivityToken, svc: Svc) -> None:
    """The Lock Screen card following the work's study: each step is pushed
    to it (without an APNs key it moves on only while the app is open).
    Where the study is now goes to it at once."""
    try:
        activity = svc.notifier.follow_study(item_id, body.token, sandbox=body.sandbox)
    except PushError as err:
        raise HTTPException(400, str(err)) from err
    status, error = await run_in_threadpool(svc.study.status, svc.library.get(item_id))
    # Not on its way here ("none"): the server lost it.
    step = "stopped" if status == "none" else status
    progress = svc.study.progress(item_id)
    await svc.notifier.push_study(item_id, step, error, only=activity.token, progress=progress)


@router.get("/study/{item_id:item}/detail")
async def study_detail(
    item_id: str, svc: Svc, n: Annotated[int, Query(ge=0, le=9)] = 0
) -> FileResponse:
    """A fragment of the work's study ("Detale"), cut from its original."""
    item = svc.library.get(item_id)
    path = await run_in_threadpool(svc.study.detail, item, n) if item is not None else None
    if path is None:
        raise HTTPException(404, "no such fragment")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=604800"})


class CompositionAgain(BaseModel):
    """Where the work's analysis of the composition asked for anew is: on
    its way, and how many analyses its page has had (the app asks for the
    page again once it is no longer on its way)."""

    pending: bool
    versions: int


class CompositionPick(BaseModel):
    #: Which of the page's analyses it shows (``DailyWork.composition_versions``).
    shown: int


def _again_state(svc: FrameService, item_id: str) -> CompositionAgain:
    pages = [svc.library.note(item_id, kind) for kind in PAGES]
    counts = [len(versions(p.data)) for p in pages if p is not None]
    return CompositionAgain(pending=svc.compose.pending(item_id), versions=max(counts, default=0))


@router.post(
    "/study/{item_id:item}/composition",
    response_model=CompositionAgain,
    dependencies=[Depends(require_owner)],
)
async def composition_again(item_id: str, svc: Svc) -> CompositionAgain:
    """The owner's "Wykonaj ponowną analizę" (held header "Analiza
    kompozycji" on the work's page): the analysis asked for anew, ahead of
    the background; the one the page shows is kept among its versions."""
    item = svc.library.get(item_id)
    if item is None:
        raise HTTPException(404, "no such work")
    if not svc.compose.enabled():
        raise HTTPException(409, "Claude jest wyłączony: dodaj klucz API w Konfiguracji.")
    if not await run_in_threadpool(svc.compose.again, item):
        raise HTTPException(409, "To dzieło nie ma jeszcze studium.")
    svc.ai.need_now(item_id, COMPOSITION)
    return await run_in_threadpool(_again_state, svc, item_id)


@router.get("/study/{item_id:item}/composition", response_model=CompositionAgain)
async def composition_state(item_id: str, svc: Svc) -> CompositionAgain:
    return await run_in_threadpool(_again_state, svc, item_id)


@router.put(
    "/study/{item_id:item}/composition",
    response_model=CompositionAgain,
    dependencies=[Depends(require_owner)],
)
async def composition_pick(item_id: str, pick: CompositionPick, svc: Svc) -> CompositionAgain:
    """The owner's pick among the page's analyses: the one it shows."""
    item = svc.library.get(item_id)
    if item is None or not await run_in_threadpool(svc.compose.choose, item, pick.shown):
        raise HTTPException(404, "no such analysis")
    return await run_in_threadpool(_again_state, svc, item_id)


class DetailsAgain(BaseModel):
    """Where the check of the work's details asked for by the owner is: on
    its way, and the titles of the details it drew anew (None when it came
    to nothing; the app asks for the page again once it is done)."""

    pending: bool
    moved: list[str] | None = None


def _mend_state(svc: FrameService, item_id: str) -> DetailsAgain:
    pending = svc.mend.pending(item_id)
    return DetailsAgain(pending=pending, moved=None if pending else svc.mend.moved(item_id))


@router.post(
    "/study/{item_id:item}/details",
    response_model=DetailsAgain,
    dependencies=[Depends(require_owner)],
)
async def details_again(item_id: str, svc: Svc) -> DetailsAgain:
    """The owner's "Popraw detale" (held header "Detale" on the work's
    page): each detail checked over its cut on the picture, a box that
    misses drawn anew (``ai.details``), ahead of the background."""
    item = svc.library.get(item_id)
    if item is None:
        raise HTTPException(404, "no such work")
    if not svc.mend.enabled():
        raise HTTPException(409, "Claude jest wyłączony: dodaj klucz API w Konfiguracji.")
    if not await run_in_threadpool(svc.mend.again, item):
        raise HTTPException(409, "To dzieło nie ma jeszcze studium z detalami.")
    svc.ai.need_now(item_id, MEND)
    return await run_in_threadpool(_mend_state, svc, item_id)


@router.get("/study/{item_id:item}/details", response_model=DetailsAgain)
async def details_state(item_id: str, svc: Svc) -> DetailsAgain:
    return await run_in_threadpool(_mend_state, svc, item_id)
