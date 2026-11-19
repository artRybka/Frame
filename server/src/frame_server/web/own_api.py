"""The owner's own works ("Dodaj własne dzieło", Mateusz 2026-11-15): the
photograph sent first, the work found in it, hints read off it, then the
work added with what he wrote (:mod:`frame_server.own_works`)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from ..ai import AiUnavailable
from ..imaging.cut import valid
from ..library.models import Item
from ..own_works import (
    MERGED_BYTES,
    PHONE_BYTES,
    SIDES,
    Description,
    Hints,
    Incoming,
    Merged,
)
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
async def send_side(
    token: str,
    svc: Svc,
    file: Annotated[UploadFile, File()],
    angle: Annotated[float | None, Query(ge=-90, le=90)] = None,
) -> dict[str, int]:
    """A photograph of the same work from a little to the side (the scan
    of three): ``{"sides": how many it has now}``. ``angle``: from how far
    to the side the phone says it was taken (degrees; negative: from the
    work's left). Of several from one side the scan is made of the one
    nearest 30°, and the others are kept with it."""
    data = await file.read()
    if not data:
        raise HTTPException(422, "empty file")
    try:
        return {"sides": await run_in_threadpool(svc.own_works.side, token, data, angle)}
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
    #: The phone shows the scan and the photograph from the front to
    #: choose between whatever the scan came to (from 1.145.229): the scan
    #: is made also of photographs that show no one flat work, in doubt.
    #: An app before it showed the scan alone, chosen, where anything was
    #: taken off, and gets a relief untouched as it did.
    choice: bool = False
    #: What the phone noted of the scan as it was taken (seconds after the
    #: first photograph its marks came, how fast it turned at each side
    #: one…): kept beside the scan's photographs, for the camera's tuning.
    trace: dict[str, float] | None = Field(default=None, max_length=64)


@router.post("/own/photos/{token}/merge", response_model=Merged)
async def merge(token: str, svc: Svc, ask: MergeAsk | None = None) -> Merged:
    """The reflections taken out by the side photographs, within the
    work's corners (the phone's, else Opus is asked for them, about two
    cents); up to a minute of the server's own work."""
    try:
        corners = _corners(ask.corners) if ask is not None else None
        outline = ask.outline if ask is not None else None
        choice = ask.choice if ask is not None else False
        trace = ask.trace if ask is not None else None
        return await run_in_threadpool(svc.own_works.merge, token, corners, outline, choice, trace)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err


class PhoneScan(BaseModel):
    """What the phone made of a scan itself: the work's corners it merged
    within, how many side photographs it laid over the first, how much of
    the work's light it took off (0: nothing, and no picture comes), and
    whether the photographs show no one flat work."""

    corners: list[tuple[float, float]]
    used: int = Field(ge=0, le=SIDES)
    replaced: float = Field(ge=0, le=1)
    doubt: bool = False
    #: As :class:`MergeAsk` has it.
    trace: dict[str, float] | None = Field(default=None, max_length=64)
    #: What the phone noted of making it: how long each part took, on
    #: what phone, with which app and core.
    phone: dict[str, Any] | None = Field(default=None, max_length=32)


@router.post("/own/photos/{token}/merged", response_model=Merged)
async def merged(
    token: str,
    svc: Svc,
    note: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File()] = None,
) -> Merged:
    """The scan the phone made of its own photographs (the same merging,
    in a few seconds there), kept in the first photograph's place as
    :func:`merge` keeps the server's: ``file`` the first photograph
    without its reflections (a JPEG of its size), ``note`` a
    :class:`PhoneScan` as JSON. 422 for what is no scan of this
    photograph (its colours were set by a chart here, no side photographs
    are with the server…): the phone then asks :func:`merge`."""
    try:
        told = PhoneScan.model_validate_json(note)
    except ValidationError as err:
        raise HTTPException(422, "the note is no scan's") from err
    data = await file.read() if file is not None else None
    if data is not None and len(data) > MERGED_BYTES:
        raise HTTPException(413, "too large")
    corners = _corners(told.corners)
    assert corners is not None
    try:
        return await run_in_threadpool(
            svc.own_works.merged_by_phone,
            token,
            data,
            corners,
            told.used,
            told.replaced,
            told.doubt,
            told.trace,
            told.phone,
        )
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err


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


#: What a scan's kept files are served as.
_KEPT = {".jpg": "image/jpeg", ".json": "application/json", ".npy": "application/octet-stream"}


@router.get("/debug/own-scans/{token}/{name}")
async def scan_file(token: str, name: str, svc: Svc) -> FileResponse:
    try:
        path = svc.own_works.scan_file(token, name)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    return FileResponse(path, media_type=_KEPT[path.suffix])


@router.get("/debug/own-scans/{token}/{name}/pixels")
async def scan_pixels(token: str, name: str, svc: Svc) -> StreamingResponse:
    """A kept scan's photograph as the server's merge reads it, a ``.npy``
    file (rows × columns × RGB, a side one small): the phone merges the
    same numbers in its trial (Mateusz 2026-11-19: "Najpierw próba na
    iPhonie")."""
    try:
        head, pixels = await run_in_threadpool(svc.own_works.scan_pixels, token, name)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err

    def parts(step: int = 1 << 22) -> Iterator[bytes]:
        yield head
        for start in range(0, len(pixels), step):
            yield bytes(pixels[start : start + step])

    return StreamingResponse(
        parts(),
        media_type="application/octet-stream",
        headers={"Content-Length": str(len(head) + len(pixels))},
    )


@router.put("/debug/own-scans/{token}/{name}")
async def phone_file(token: str, name: str, request: Request, svc: Svc) -> dict[str, int]:
    """What the phone made of a kept scan's photographs itself
    (``phone.npy``, as :func:`scan_pixels` gave them) and what it noted of
    that (``phone.json``), the request's body as it is: kept beside the
    photographs to be compared with the server's. Nothing of his
    collection changes."""
    try:
        part = svc.own_works.phone_part(token, name)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    size = 0
    with part.open("wb") as out:
        async for chunk in request.stream():
            size += len(chunk)
            if size > PHONE_BYTES:
                break
            await run_in_threadpool(out.write, chunk)
    if size > PHONE_BYTES:
        part.unlink(missing_ok=True)
        raise HTTPException(413, "too large")
    try:
        return {"bytes": await run_in_threadpool(svc.own_works.phone_took, token, name)}
    except ValueError as err:
        raise HTTPException(422, str(err)) from err


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
