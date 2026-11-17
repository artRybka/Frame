"""The owner's own works ("Dodaj własne dzieło", Mateusz 2026-11-15): the
photograph sent first, the work found in it, hints read off it, then the
work added with what he wrote (:mod:`frame_server.own_works`)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
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
    #: The white balance he set (-1 cooler … 1 warmer; 0, as taken).
    balance: float = Field(default=0.0, ge=-1, le=1)


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


class MergeAsk(BaseModel):
    #: The work's corners on the first photograph, when the phone knows them.
    corners: list[tuple[float, float]] | None = None
    #: The rectangle the phone's camera followed at the first photograph:
    #: where the work is when nothing else says.
    outline: list[tuple[float, float]] | None = None


@router.post("/own/photos/{token}/merge", response_model=Merged)
async def merge(token: str, svc: Svc, ask: MergeAsk | None = None) -> Merged:
    """The reflections taken out by the side photographs, within the
    work's corners (the phone's, else Opus is asked for them, about two
    cents); up to a minute of the server's own work."""
    try:
        corners = _corners(ask.corners) if ask is not None else None
        outline = ask.outline if ask is not None else None
        return await run_in_threadpool(svc.own_works.merge, token, corners, outline)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err


@router.post("/own/photos/{token}/single")
async def single(token: str, svc: Svc) -> dict[str, bool]:
    """The first photograph as it came, in the scan's place: he chose the
    one photograph on the page that shows the two."""
    try:
        await run_in_threadpool(svc.own_works.single, token)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    return {"single": True}


@router.get("/own/photos/{token}")
async def photo(token: str, svc: Svc, side: int | None = None) -> Response:
    """The photograph as it waits (after :func:`merge`, without the glare):
    the phone shows it in "Kadr", no longer than ``side`` (whole, it is
    48 MP and twenty megabytes)."""
    if side is not None and not 200 <= side <= 9000:
        raise HTTPException(422, "side: 200–9000")
    try:
        found = await run_in_threadpool(svc.own_works.shown, token, side)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    if isinstance(found, bytes):
        return Response(found, media_type="image/jpeg")
    return FileResponse(found, media_type="image/jpeg")


@router.get("/debug/own-scans")
async def scans(svc: Svc) -> list[dict[str, object]]:
    """The scans' photographs kept two weeks for the merging to be tuned
    on (Mateusz 2026-11-16): each scan's files and what the merge noted."""
    return await run_in_threadpool(svc.own_works.kept_scans)


@router.get("/debug/own-scans/{token}/{name}")
async def scan_file(token: str, name: str, svc: Svc) -> FileResponse:
    try:
        return FileResponse(svc.own_works.scan_file(token, name), media_type="image/jpeg")
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
            svc.own_works.add,
            new.token,
            _corners(new.corners),
            new.by,
            new.shape,
            new.text,
            new.balance,
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
            svc.own_works.retake,
            item,
            photo.token,
            _corners(photo.corners),
            photo.by,
            photo.shape,
            photo.balance,
        )
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
