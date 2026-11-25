"""Museum photographs cut by the phone's own model (``phone_crops``; Mateusz
2026-11-20): what the app is to look at, what it found, and the owner's list
"Kadrowane" with what his corrections teach the model."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..imaging.crop_model import PHOTO_SIDE
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
    #: Of a print whose sheet the phone cut down round its impression
    #: (``crop_model.plate``): the sheet the model found and the impression
    #: alone; ``plates``: how it did it (``crop_model.PLATE``; none from an
    #: older app, the server does it then).
    sheet: list[tuple[float, float]] | None = None
    plate: list[tuple[float, float]] | None = None
    plates: int | None = None


class Found(BaseModel):
    """What came of it: ``verdict`` as kept ("" when nothing was done: the
    photograph shown changed meanwhile, or the owner cut it himself)."""

    cut: bool
    verdict: str
    item: Item


class Sure(BaseModel):
    id: str
    sure: float


class Review(BaseModel):
    """ "Kadrowane": what the model cut, and what it left to him."""

    cut: list[ItemSummary]
    unsure: list[ItemSummary]
    #: How sure the model was a cut is wanted, of each work.
    sure: list[Sure] = []


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
                sheet=found.sheet,
                plate_alone=found.plate,
                plates=found.plates,
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
    sure = svc.phone_crops.sure([i.id for i in cut + unsure])
    return Review(
        cut=[ItemSummary.of(i) for i in cut],
        unsure=[ItemSummary.of(i) for i in unsure],
        sure=[Sure(id=k, sure=v) for k, v in sure.items()],
    )


@router.post("/review/{item_id:item}/fine", response_model=Review)
async def review_fine(item_id: str, svc: Svc) -> Review:
    """ "Zatwierdź": the model's cut is right, or a work it left whole is
    right whole ("Bez kadru"); off the list."""
    item = await _work(svc, item_id)
    stored = svc.library.get(item.id) or item
    if not await run_in_threadpool(svc.phone_crops.fine, stored):
        raise HTTPException(409, "nothing of the model's to keep")
    return await review(svc)


@router.delete("/review/{item_id:item}/fine", response_model=Review)
async def review_unfine(item_id: str, svc: Svc) -> Review:
    """ "Cofnij": the last approval taken back; the work is on the list again."""
    if not await run_in_threadpool(svc.phone_crops.unfine, item_id):
        raise HTTPException(404, "not approved")
    return await review(svc)


@router.get("/lessons")
async def lessons(svc: Svc) -> list[dict[str, Any]]:
    """What the model is taught again from (on the Mac): his corrections and
    the cuts he kept, with what the model proposed; the photographs from
    ``/api/library/items/{id}/full?side=``."""
    return await run_in_threadpool(svc.phone_crops.lessons)


class Teach(BaseModel):
    """ "Ucz kadrowania": photographs for his word, and how many he gave."""

    works: list[ItemSummary]
    told: int


class Told(BaseModel):
    answer: Literal["whole", "cut", "framed"]


@router.get("/teach", response_model=Teach)
async def teach(
    svc: Svc,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    kind: Annotated[int, Query(ge=0, le=2)] = 0,
) -> Teach:
    """Photographs of one kind (0 painting, 1 drawing, 2 print) for his word."""
    works, told = await run_in_threadpool(svc.phone_crops.to_teach, limit, kind)
    return Teach(works=[ItemSummary.of(i) for i in works], told=told)


@router.post("/teach/{item_id:item}", response_model=Teach)
async def teach_tell(item_id: str, told: Told, svc: Svc) -> Teach:
    """His word on a photograph: "whole" (no cut), "cut" (no frame), "framed"."""
    item = await _work(svc, item_id)
    stored = svc.library.get(item.id) or item
    count = await run_in_threadpool(svc.phone_crops.tell, stored, told.answer)
    return Teach(works=[], told=count)


@router.delete("/teach/{item_id:item}", response_model=Teach)
async def teach_untell(item_id: str, svc: Svc) -> Teach:
    """ "Cofnij": his word taken back."""
    item = await _work(svc, item_id)
    stored = svc.library.get(item.id) or item
    count = await run_in_threadpool(svc.phone_crops.tell, stored, None)
    return Teach(works=[], told=count)


@router.get("/told")
async def told(svc: Svc) -> list[dict[str, Any]]:
    """What he said at a glance (``/teach``), for teaching on the Mac."""
    return await run_in_threadpool(svc.phone_crops.told)
