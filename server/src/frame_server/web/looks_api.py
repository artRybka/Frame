"""Szukaj by how a work looks (``frame_server.looks``, "G1"): words for how
it looks, a photograph of one, and the works that look like a work."""

from __future__ import annotations

import io
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai import AiUnavailable
from ..ai.gemini import NotDrawn
from ..library.models import ItemSummary
from ..looks import Found
from ..service import FrameService
from .deps import require_token, service
from .library_api import _work

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["looks"])
Svc = Annotated[FrameService, Depends(service)]

#: A photograph sent to be searched by may weigh this much at most.
PICTURE_BYTES = 15_000_000


class LooksStatus(BaseModel):
    """Whether Szukaj may offer it: Google's key and the switch (``enabled``),
    and works with their numbers already (``ready``)."""

    enabled: bool
    ready: bool
    done: int
    total: int


class LooksAnswer(BaseModel):
    """The works found, nearest first, and how near each is (0-1)."""

    items: list[ItemSummary]
    scores: list[float]


def _answer(found: list[Found]) -> LooksAnswer:
    return LooksAnswer(
        items=[ItemSummary.of(f.item) for f in found],
        scores=[f.score for f in found],
    )


@router.get("/looks", response_model=LooksStatus)
async def looks_status(svc: Svc) -> LooksStatus:
    done, total = await run_in_threadpool(svc.looks.counts)
    return LooksStatus(enabled=svc.looks.enabled(), ready=svc.looks.ready(), done=done, total=total)


@router.get("/looks/search", response_model=LooksAnswer)
async def looks_by_words(
    svc: Svc,
    q: str,
    limit: Annotated[int, Query(ge=1, le=120)] = 60,
) -> LooksAnswer:
    """Works that look as ``q`` says ("mglisty poranek nad wodą"). 409 when
    it cannot be asked (no key, the switch off, no numbers yet, the
    month's limit), 502 when Google does not answer."""
    if not q.strip():
        raise HTTPException(422, "empty words")
    try:
        found = await run_in_threadpool(svc.looks.words, q, limit)
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except (NotDrawn, httpx.HTTPError) as err:
        raise HTTPException(502, f"Google did not answer: {err}") from err
    return _answer(found)


@router.post("/looks/picture", response_model=LooksAnswer)
async def looks_by_picture(
    svc: Svc,
    file: Annotated[UploadFile, File()],
    limit: Annotated[int, Query(ge=1, le=120)] = 60,
) -> LooksAnswer:
    """Works that look like a photograph (of a work in a museum, a postcard,
    a page of a book). The photograph is not kept."""
    data = await file.read(PICTURE_BYTES + 1)
    if not data:
        raise HTTPException(422, "empty file")
    if len(data) > PICTURE_BYTES:
        raise HTTPException(413, "the photograph is too large")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as err:
        raise HTTPException(422, f"not a picture: {err}") from err
    try:
        found = await run_in_threadpool(svc.looks.picture, img, limit)
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except (NotDrawn, httpx.HTTPError) as err:
        raise HTTPException(502, f"Google did not answer: {err}") from err
    return _answer(found)


@router.get("/library/items/{item_id:item}/looks", response_model=LooksAnswer)
async def looks_like(
    item_id: str,
    svc: Svc,
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
) -> LooksAnswer:
    """Works that look like this one ("Podobne wyglądem"): none while it
    has no numbers (or Szukanie wyglądem is off). Asks Google nothing."""
    item = await _work(svc, item_id)
    if not svc.looks.enabled():
        return LooksAnswer(items=[], scores=[])
    return _answer(await run_in_threadpool(svc.looks.similar, item, limit))
