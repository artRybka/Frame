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
from ..looks import By, Found
from ..service import FrameService
from .deps import require_owner, require_token, service
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
    #: Of these, how many Szukaj's "Podobne do" shows (``Looks.enough``):
    #: what the card's "Szukaj podobnych" counts. Only on a work's looks.
    alike: int | None = None


def _answer(found: list[Found], alike: int | None = None) -> LooksAnswer:
    return LooksAnswer(
        items=[ItemSummary.of(f.item) for f in found],
        scores=[f.score for f in found],
        alike=alike,
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
    _, img = await _photograph(file)
    try:
        found = await run_in_threadpool(svc.looks.picture, img, limit)
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except (NotDrawn, httpx.HTTPError) as err:
        raise HTTPException(502, f"Google did not answer: {err}") from err
    return _answer(found)


class LooksPhoto(BaseModel):
    """A photograph searched in Szukaj: the key Szukaj asks as ``like``."""

    key: str


@router.post("/looks/photo", response_model=LooksPhoto)
async def looks_photo(svc: Svc, file: Annotated[UploadFile, File()]) -> LooksPhoto:
    """ "Szukaj zdjęciem" in Szukaj's own list (Mateusz 2026-11-15): the
    photograph's numbers kept under a key that ``/api/library/items?like=``
    and a smart playlist's ``like`` take, as a work's id. The photograph is
    not kept. 409 / 502 as ``/looks/picture``."""
    data, img = await _photograph(file)
    try:
        key = await run_in_threadpool(svc.looks.photo, data, img)
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except (NotDrawn, httpx.HTTPError) as err:
        raise HTTPException(502, f"Google did not answer: {err}") from err
    return LooksPhoto(key=key)


async def _photograph(file: UploadFile) -> tuple[bytes, Image.Image]:
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
    return data, img


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
    found = await run_in_threadpool(svc.looks.similar, item, limit)
    return _answer(found, alike=len(svc.looks.enough(found)))


@router.get(
    "/debug/looks/{item_id:item}", response_model=LooksAnswer, dependencies=[Depends(require_owner)]
)
async def looks_near(
    item_id: str,
    svc: Svc,
    by: By = "",
    count: Annotated[int, Query(ge=1, le=2000)] = 1000,
) -> LooksAnswer:
    """The ``count`` works nearest this one by ``by`` (both, "subject",
    "style"), with their nearness, however near (above the works' mean):
    for setting where "Podobne do" stops (Mateusz 2026-11-18: "limitem
    ilości nie powinien być stopień podobieństwa?"). The owner's only."""
    item = await _work(svc, item_id)
    return _answer(await run_in_threadpool(svc.looks.similar, item, count, by=by))
