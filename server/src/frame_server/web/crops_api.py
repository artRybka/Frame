"""Museum photographs cut by the phone's own model (``phone_crops``; Mateusz
2026-11-20): what the app is to look at, what it found, and the owner's list
"Kadrowane" with what his corrections teach the model."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..imaging.crop_model import MODEL, PHOTO_SIDE
from ..library.images import Gone
from ..library.models import Item, ItemSummary
from ..service import FrameService
from .deps import require_owner, service
from .library_api import _work

router = APIRouter(prefix="/api/crops", dependencies=[Depends(require_owner)], tags=["crops"])
Svc = Annotated[FrameService, Depends(service)]


class PhoneLook(BaseModel):
    """Whether the app is to look at a work's photograph now (its card
    opened), the work's kind as the model is told it, the model the server
    knows, the photograph's key and side."""

    look: bool
    kind: int
    model: str
    picture: str
    side: int = PHOTO_SIDE


class Waiting(BaseModel):
    """ "Kadruj partię": works to look at (``id``, ``kind``, ``picture``),
    how many wait in all."""

    model: str
    side: int = PHOTO_SIDE
    works: list[dict[str, Any]]
    left: int


class PhoneFound(BaseModel):
    """What the phone's model found (``imaging/crop_model.find``): corners
    as fractions of the photograph of ``width`` × ``height`` it looked at."""

    model: str
    picture: str
    verdict: Literal["cut", "whole", "unsure"]
    sure: float = Field(ge=0, le=1)
    work: list[tuple[float, float]] | None = None
    surround: list[tuple[float, float]] | None = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Found(BaseModel):
    """What came of it: ``verdict`` as kept ("" when nothing was done: the
    photograph shown changed meanwhile, or the owner cut it himself)."""

    cut: bool
    verdict: str
    item: Item


class Review(BaseModel):
    """ "Kadrowane": what the model cut, and what it left to him."""

    cut: list[ItemSummary]
    unsure: list[ItemSummary]


@router.get("/phone/waiting", response_model=Waiting)
async def phone_waiting(svc: Svc, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> Waiting:
    works, left = await run_in_threadpool(svc.phone_crops.waiting, limit)
    return Waiting(
        model=MODEL,
        works=[{"id": i.id, **svc.phone_crops.ask(i)} for i in works],
        left=left,
    )


@router.get("/phone/{item_id:item}", response_model=PhoneLook)
async def phone_ask(item_id: str, svc: Svc) -> PhoneLook:
    item = await _work(svc, item_id)
    stored = svc.library.get(item.id) or item
    return PhoneLook(**svc.phone_crops.ask(stored))


@router.post("/phone/{item_id:item}", response_model=Found)
async def phone_found(item_id: str, found: PhoneFound, svc: Svc) -> Found:
    item = await _work(svc, item_id)
    stored = svc.library.get(item.id)
    if stored is None:
        raise HTTPException(404, "only a work in the library is cut")
    try:
        verdict = await run_in_threadpool(
            lambda: svc.phone_crops.found(
                stored,
                verdict=found.verdict,
                sure=found.sure,
                work=found.work,
                surround=found.surround,
                size=(found.width, found.height),
                picture=found.picture,
                model=found.model,
            )
        )
    except Gone as err:
        raise HTTPException(410, f"no picture anywhere: {err}") from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"image unavailable: {err}") from err
    return Found(cut=verdict == "cut", verdict=verdict, item=svc.library.get(item.id) or stored)


@router.get("/review", response_model=Review)
async def review(svc: Svc) -> Review:
    cut, unsure = await run_in_threadpool(svc.phone_crops.review)
    return Review(cut=[ItemSummary.of(i) for i in cut], unsure=[ItemSummary.of(i) for i in unsure])


@router.post("/review/{item_id:item}/fine", response_model=Review)
async def review_fine(item_id: str, svc: Svc) -> Review:
    """ "Dobrze": the model's cut is right; off the list."""
    item = await _work(svc, item_id)
    stored = svc.library.get(item.id) or item
    if not await run_in_threadpool(svc.phone_crops.fine, stored):
        raise HTTPException(409, "no cut of the model's to keep")
    return await review(svc)


@router.get("/lessons")
async def lessons(svc: Svc) -> list[dict[str, Any]]:
    """What the model is taught again from (on the Mac): his corrections and
    the cuts he kept, with what the model proposed; the photographs from
    ``/api/library/items/{id}/full?side=``."""
    return await run_in_threadpool(svc.phone_crops.lessons)
