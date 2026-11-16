"""The owner's own works ("Dodaj własne dzieło", Mateusz 2026-11-15): the
photograph sent first, the work found in it, hints read off it, then the
work added with what he wrote (:mod:`frame_server.own_works`)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai import AiUnavailable
from ..imaging.cut import valid
from ..library.models import Item
from ..own_works import Description, Hints, Incoming, Merged
from ..service import FrameService
from .deps import require_owner, service

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)], tags=["own"])
Svc = Annotated[FrameService, Depends(service)]


class PhotoCut(BaseModel):
    """The photograph sent and the corners of the work on it (0–1 across
    and down; None: the photograph whole). ``by``: "auto" when they are the
    server's (or the phone's) unchanged, "owner" when he moved them."""

    token: str
    corners: list[tuple[float, float]] | None = None
    by: str = "auto"
    shape: str = ""


class NewOwnWork(PhotoCut):
    text: Description


class HintsAsk(BaseModel):
    token: str
    corners: list[tuple[float, float]] | None = None


def _corners(raw: list[tuple[float, float]] | None) -> list[tuple[float, float]] | None:
    if raw is None:
        return None
    quad = valid(raw)
    if quad is None:
        raise HTTPException(422, "the corners make no picture")
    return quad


async def _own(svc: FrameService, item_id: str) -> Item:
    item = svc.library.get(item_id)
    if item is None:
        raise HTTPException(404, f"no work {item_id!r}")
    return item


@router.post("/own/photos", response_model=Incoming)
async def send_photo(svc: Svc, file: Annotated[UploadFile, File()]) -> Incoming:
    """The photograph of a work of his, kept a day while he adds it."""
    data = await file.read()
    if not data:
        raise HTTPException(422, "empty file")
    try:
        return await run_in_threadpool(svc.own_works.take, data)
    except ValueError as err:
        raise HTTPException(422, str(err)) from err


@router.post("/own/photos/{token}/sides")
async def send_side(token: str, svc: Svc, file: Annotated[UploadFile, File()]) -> dict[str, int]:
    """A photograph of the same work from a little to the side (the scan
    of three): ``{"sides": how many it has now}``."""
    data = await file.read()
    if not data:
        raise HTTPException(422, "empty file")
    try:
        return {"sides": await run_in_threadpool(svc.own_works.side, token, data)}
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err


@router.post("/own/photos/{token}/merge", response_model=Merged)
async def merge(token: str, svc: Svc) -> Merged:
    """The reflections taken out by the side photographs (no model, a
    few seconds of the server's own work)."""
    try:
        return await run_in_threadpool(svc.own_works.merge, token)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err


@router.post("/own/photos/{token}/find", response_model=Incoming)
async def find_work(token: str, svc: Svc) -> Incoming:
    """The work found in the photograph (Opus, a few seconds, about two
    cents): its corners, or none (no key, nothing found, not a rectangle)."""
    try:
        return await run_in_threadpool(svc.own_works.find, token)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    except AiUnavailable as err:
        raise HTTPException(503, str(err)) from err


@router.post("/own/hints", response_model=Hints)
async def hints(ask: HintsAsk, svc: Svc) -> Hints:
    """Signature, date, technique and a plain title read off the work."""
    try:
        return await run_in_threadpool(svc.own_works.hints, ask.token, _corners(ask.corners))
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    except AiUnavailable as err:
        raise HTTPException(503, str(err)) from err


@router.post("/own/works", response_model=Item)
async def add_work(new: NewOwnWork, svc: Svc) -> Item:
    """The work added to the catalogue, cut and described."""
    try:
        return await run_in_threadpool(
            svc.own_works.add, new.token, _corners(new.corners), new.by, new.shape, new.text
        )
    except LookupError as err:
        raise HTTPException(404, str(err)) from err


@router.put("/own/works/{item_id:item}", response_model=Item)
async def describe(item_id: str, text: Description, svc: Svc) -> Item:
    """ "Edytuj opis"."""
    item = await _own(svc, item_id)
    try:
        return await run_in_threadpool(svc.own_works.describe, item, text)
    except ValueError as err:
        raise HTTPException(422, str(err)) from err


@router.put("/own/works/{item_id:item}/photo", response_model=Item)
async def retake(item_id: str, photo: PhotoCut, svc: Svc) -> Item:
    """ "Zrób zdjęcie ponownie": the new photograph, cut; the text stays."""
    item = await _own(svc, item_id)
    try:
        return await run_in_threadpool(
            svc.own_works.retake, item, photo.token, _corners(photo.corners), photo.by, photo.shape
        )
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
