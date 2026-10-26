"""How much disk the library takes and its limit, set in the app
(Ramka → trybik → Połączenie)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from ..service import FrameService
from ..storage import StorageUpdate, StorageView
from .deps import require_token, service

router = APIRouter(prefix="/api/library", dependencies=[Depends(require_token)], tags=["library"])
Svc = Annotated[FrameService, Depends(service)]


@router.get("/storage", response_model=StorageView)
async def get_storage(svc: Svc) -> StorageView:
    return await run_in_threadpool(svc.storage.view)


@router.put("/storage", response_model=StorageView)
async def put_storage(update: StorageUpdate, svc: Svc) -> StorageView:
    _after_change(svc, svc.storage.save(update))
    return await run_in_threadpool(svc.storage.view)


@router.delete("/storage", response_model=StorageView)
async def reset_storage(svc: Svc) -> StorageView:
    """Back to the limits in frame.env or the add-on options."""
    _after_change(svc, svc.storage.reset())
    return await run_in_threadpool(svc.storage.view)


def _after_change(svc: FrameService, lower: bool) -> None:
    """A lower limit trims the library now, in the background (thousands of
    files on a slow disk); a higher one lets the catalogue grow now."""
    if lower:
        svc.background(run_in_threadpool(svc.player.trim_cache))
    elif svc.settings.scheduler:  # it measures the thumbnails first: off the event loop
        svc.background(run_in_threadpool(svc.player.grow_catalogue))
