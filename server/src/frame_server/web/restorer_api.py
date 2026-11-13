"""The creative restorer (``frame_server.restorer``): one work from its card,
the owner's favourites under the threshold from Konfiguracja."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai import AiUnavailable
from ..library.hosts import urgent_call
from ..library.models import Item
from ..restorer import NotRestored
from ..service import FrameService
from .deps import require_owner, service
from .library_api import _work

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)], tags=["restorer"])
Svc = Annotated[FrameService, Depends(service)]


class RestorerView(BaseModel):
    """Konfiguracja's line: the favourites the batch would draw (``items``,
    about ``usd``), those waiting in batches, and the works drawn so far."""

    enabled: bool
    items: int
    usd: float
    waiting: int
    restored: int


def _view(svc: FrameService) -> RestorerView:
    items, usd = svc.restorer.estimate()
    waiting, restored = svc.restorer.counts()
    return RestorerView(
        enabled=svc.painter.enabled(),
        items=items,
        usd=usd,
        waiting=waiting,
        restored=restored,
    )


@router.get("/ai/restorer", response_model=RestorerView)
async def restorer_view(svc: Svc) -> RestorerView:
    return await run_in_threadpool(_view, svc)


@router.post("/ai/restorer/favourites", response_model=RestorerView)
async def restore_favourites(svc: Svc) -> RestorerView:
    """The favourites whose picture is small for the frame drawn again
    through the Batch API (within 24 hours, half the price)."""
    try:
        await run_in_threadpool(svc.restorer.order_favourites)
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except httpx.HTTPError as err:
        raise HTTPException(502, f"Google did not answer: {err}") from err
    return await run_in_threadpool(_view, svc)


@router.post("/library/items/{item_id:item}/restore", response_model=Item)
async def restore_item(item_id: str, svc: Svc) -> Item:
    """The work's picture drawn again larger by the image model and kept in
    its place ("Kreatywny restaurator"; some 25 s). 422 for a work that is
    not drawn, its detail led by the reason's code ("refused: …": the
    model would not draw it)."""
    item = await _work(svc, item_id)
    try:
        return await run_in_threadpool(urgent_call(svc.restorer.restore), item)
    except NotRestored as err:
        raise HTTPException(422, f"{err.code}: {err}") from err
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"picture unavailable: {err}") from err
