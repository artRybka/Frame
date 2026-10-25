"""Library, museum search and import."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from ..imaging.layout import Crop, Fit, Orientation, Plan, canvas_size, load_image
from ..imaging.pipeline import encode_image, plan_for, render, render_multi
from ..library import Facets, Item, ItemKind, ItemSummary, Job, PhotoInfo, PlaylistRules
from ..library.importer import ALL
from ..library.models import Framing
from ..library.museums import MUSEUMS, Discovery, Kind
from ..library.repo import SortKey
from ..library.seed import PACKS, import_queries, pack
from ..player import hold_from
from ..schedule import FrameSettings
from ..service import FrameService
from .deps import require_token, service

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["library"])
Svc = Annotated[FrameService, Depends(service)]


class ItemPage(BaseModel):
    total: int
    items: list[ItemSummary]


class ItemPatch(BaseModel):
    favorite: bool | None = None
    excluded: bool | None = None
    title: str | None = None
    artist: str | None = None
    description: str | None = None


class ShowRequest(BaseModel):
    hold: str | int | None = None


class RemoteItem(BaseModel):
    item: Item
    in_library: bool


class RemotePage(BaseModel):
    total: int
    items: list[RemoteItem]
    #: Museums that did not answer (searching ``all``).
    failed: list[str] = []


class ImportRequest(BaseModel):
    source_id: str


class DrawRequest(BaseModel):
    count: int = Field(100, ge=1, le=500)
    year_from: int | None = Field(None, ge=0, le=2100)
    year_to: int | None = Field(None, ge=0, le=2100)
    style: str = ""
    kind: Kind = "any"
    sources: list[str] = Field(default_factory=lambda: ["aic", "cma", "met", "rijks"])
    #: 0–1; works that look worse on e-paper are drawn again.
    min_suitability: float = Field(0.0, ge=0, le=1)


class ImportSearchRequest(BaseModel):
    query: str
    limit: int = Field(24, ge=1, le=500)


def _item(svc: FrameService, item_id: str) -> Item:
    item = svc.library.get(item_id)
    if item is None:
        raise HTTPException(404, f"no item {item_id!r}")
    return item


@router.get("/library/items", response_model=ItemPage)
def list_items(
    svc: Svc,
    q: str = "",
    artist: Annotated[list[str] | None, Query()] = None,
    style: Annotated[list[str] | None, Query()] = None,
    subject: Annotated[list[str] | None, Query()] = None,
    color: Annotated[list[str] | None, Query()] = None,
    kind: Annotated[list[ItemKind] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    favorites: bool = False,
    sort: SortKey = "recent",
    offset: int = 0,
    limit: Annotated[int, Query(le=200)] = 60,
    seed: int = 0,
) -> ItemPage:
    rules = PlaylistRules(
        query=q,
        artists=artist or [],
        styles=style or [],
        subjects=subject or [],
        colors=color or [],
        kinds=kind or [],
        sources=source or [],
        favorites_only=favorites,
    )
    total, items = svc.library.query(rules, sort=sort, offset=offset, limit=limit, seed=seed)
    return ItemPage(total=total, items=[ItemSummary.of(i) for i in items])


@router.get("/library/facets", response_model=Facets)
def facets(svc: Svc) -> Facets:
    return svc.library.facets()


@router.get("/library/items/{item_id}", response_model=Item)
def get_item(item_id: str, svc: Svc) -> Item:
    return _item(svc, item_id)


@router.patch("/library/items/{item_id}", response_model=Item)
def patch_item(item_id: str, patch: ItemPatch, svc: Svc) -> Item:
    _item(svc, item_id)
    changes = patch.model_dump(exclude_none=True)
    updated = svc.library.update(item_id, **changes)
    assert updated is not None
    return updated


@router.delete("/library/items/{item_id}")
def delete_item(item_id: str, svc: Svc) -> dict[str, bool]:
    item = _item(svc, item_id)
    svc.library.delete(item_id)
    svc.images.remove(item)
    return {"deleted": True}


@router.get("/library/items/{item_id}/thumb")
async def item_thumb(item_id: str, svc: Svc) -> FileResponse:
    item = _item(svc, item_id)
    try:
        path = await run_in_threadpool(svc.images.ensure_thumb, item)
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"thumbnail unavailable: {err}") from err
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.get("/library/items/{item_id}/image")
async def item_image(item_id: str, svc: Svc) -> FileResponse:
    item = _item(svc, item_id)
    try:
        path = await run_in_threadpool(svc.images.ensure_image, item)
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"image unavailable: {err}") from err
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


_preview_locks: dict[str, asyncio.Lock] = {}
PREVIEW_CACHE_FILES = 200


def _prune(directory: Path, keep: int) -> None:
    files = sorted(directory.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


@router.get("/library/items/{item_id}/preview")
async def item_preview(item_id: str, svc: Svc, settings: str | None = None) -> FileResponse:
    """How the picture will look on the panel.

    With the saved settings, or with ``settings`` (FrameSettings JSON; only
    orientation and presentation matter) to try a framing before saving it.
    """
    item = _item(svc, item_id)
    frame_settings = svc.player.settings
    if settings:
        try:
            frame_settings = FrameSettings.model_validate_json(settings)
        except ValidationError as err:
            raise HTTPException(422, f"invalid settings: {err}") from err
    render_settings = svc.player.render_settings(item, frame_settings)
    board = svc.player.preview_board(item, frame_settings)  # MULTI: with the photos beside it
    ids = ",".join(i.id for i in board)
    key = hashlib.sha1(
        (render_settings.model_dump_json() + svc.palette.name + ids).encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]
    path = svc.images.thumbs.parent / "previews" / f"{item.file_stem}-{key}.png"
    if not path.is_file():
        async with _preview_locks.setdefault(path.name, asyncio.Lock()):
            if not path.is_file():
                sources = [
                    await run_in_threadpool(svc.images.ensure_image, shown) for shown in board
                ]

                def build() -> None:
                    if svc.player.multi(item, frame_settings):
                        result = render_multi(sources, render_settings, svc.palette, seed=ids)
                    else:
                        result = render(sources[0], render_settings, svc.palette)
                    img = result.preview_image()
                    img.thumbnail((1280, 1280))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(encode_image(img, "png"))
                    _prune(path.parent, PREVIEW_CACHE_FILES)

                await run_in_threadpool(build)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


class FramingWindow(BaseModel):
    role: str  # "fill" or "detail"
    aspect: float  # width / height of the window on the frame
    crop: Crop
    custom: bool  # set by the user (else chosen automatically)


class FramingView(BaseModel):
    orientation: Orientation
    fit: Fit  # how the picture is shown in this orientation
    width: int  # the picture, in pixels
    height: int
    windows: list[FramingWindow]  # what can be adjusted; none with a passe-partout


class FramingUpdate(BaseModel):
    orientation: Orientation
    crops: list[Crop]  # one for FILL and DESCRIPTION, two for DETAILS


def _framing_plan(
    svc: FrameService, item: Item, orientation: Orientation
) -> tuple[Plan, tuple[int, int]]:
    settings = svc.player.settings.model_copy(update={"orientation": orientation})
    render_settings = svc.player.render_settings(item, settings)
    img = load_image(svc.images.ensure_image(item))
    if svc.player.multi(item, settings):  # each photo cropped automatically to its window
        return Plan(Fit.MULTI, canvas_size(orientation), []), img.size
    return plan_for(img, render_settings.layout, caption=bool(render_settings.caption)), img.size


def _framing_view(
    item: Item, orientation: Orientation, plan: Plan, size: tuple[int, int]
) -> FramingView:
    saved = item.framing.get(orientation.value) or Framing()
    custom = {
        Fit.FILL: saved.fill is not None,
        Fit.DETAILS: saved.details is not None,
        Fit.DESCRIPTION: saved.detail is not None,
        Fit.FIT: saved.fit is not None,
    }.get(plan.fit, False)
    windows = [
        FramingWindow(role=w.role, aspect=round(w.aspect, 4), crop=w.crop, custom=custom)
        for w in plan.windows
        if w.crop is not None
    ]
    return FramingView(
        orientation=orientation, fit=plan.fit, width=size[0], height=size[1], windows=windows
    )


async def _plan_and_view(svc: FrameService, item: Item, orientation: Orientation) -> FramingView:
    try:
        plan, size = await run_in_threadpool(_framing_plan, svc, item, orientation)
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"image unavailable: {err}") from err
    return _framing_view(item, orientation, plan, size)


@router.get("/library/items/{item_id}/framing", response_model=FramingView)
async def get_framing(
    item_id: str, svc: Svc, orientation: Orientation | None = None
) -> FramingView:
    """How the picture is cropped on the frame, and what can be adjusted."""
    item = _item(svc, item_id)
    return await _plan_and_view(svc, item, orientation or svc.player.settings.orientation)


@router.put("/library/items/{item_id}/framing", response_model=FramingView)
async def put_framing(item_id: str, update: FramingUpdate, svc: Svc) -> FramingView:
    """Save a corrected crop (FILL, or FIT with its shape) or close-ups
    (DETAILS, DESCRIPTION) for this picture."""
    item = _item(svc, item_id)
    current = await _plan_and_view(svc, item, update.orientation)
    framing = item.framing.get(update.orientation.value, Framing()).model_copy()
    if current.fit == Fit.FILL and len(update.crops) == 1:
        framing.fill = update.crops[0]
    elif current.fit == Fit.DETAILS and len(update.crops) == 2:
        framing.details = list(update.crops)
    elif current.fit == Fit.DESCRIPTION and len(update.crops) == 1:
        framing.detail = update.crops[0]
    elif current.fit == Fit.FIT and len(update.crops) == 1:
        framing.fit = update.crops[0]
    else:
        raise HTTPException(422, f"{current.fit.value}: wrong number of crops")
    item = _save_framing(svc, item, update.orientation, framing)
    return await _plan_and_view(svc, item, update.orientation)


@router.delete("/library/items/{item_id}/framing", response_model=FramingView)
async def reset_framing(item_id: str, svc: Svc, orientation: Orientation) -> FramingView:
    """Back to the automatic crop of the current mode for this orientation."""
    item = _item(svc, item_id)
    current = await _plan_and_view(svc, item, orientation)
    framing = item.framing.get(orientation.value, Framing()).model_copy()
    field = {Fit.FILL: "fill", Fit.DETAILS: "details", Fit.DESCRIPTION: "detail", Fit.FIT: "fit"}
    if current.fit not in field:
        raise HTTPException(422, f"{current.fit.value}: nothing to reset")
    setattr(framing, field[current.fit], None)
    empty = framing == Framing()
    item = _save_framing(svc, item, orientation, None if empty else framing)
    return await _plan_and_view(svc, item, orientation)


def _save_framing(
    svc: FrameService, item: Item, orientation: Orientation, framing: Framing | None
) -> Item:
    stored = dict(item.framing)
    if framing is None:
        stored.pop(orientation.value, None)
    else:
        stored[orientation.value] = framing
    updated = svc.library.update(item.id, framing=stored) or item
    player = svc.player
    if player.state.current_item_id == item.id and player.settings.orientation == orientation:
        svc.background(player.restyle())  # show the new crop now
    return updated


@router.post("/library/items/{item_id}/show", status_code=202)
async def show_item(item_id: str, request: ShowRequest, svc: Svc) -> dict[str, Any]:
    item = _item(svc, item_id)
    svc.background(svc.player.show(item, "app", hold_from(request.hold)))
    return {"accepted": True, "item_id": item.id}


@router.post("/library/upload", response_model=Item)
async def upload(
    svc: Svc,
    file: Annotated[UploadFile, File()],
    kind: Annotated[ItemKind, Form()] = ItemKind.OWN,
    title: Annotated[str, Form()] = "",
    artist: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    taken_at: Annotated[str | None, Form()] = None,
    latitude: Annotated[float | None, Form()] = None,
    longitude: Annotated[float | None, Form()] = None,
) -> Item:
    """Add a picture to the library (e.g. photos from the phone's camera roll)."""
    data = await file.read()
    photo = (
        PhotoInfo(taken_at=taken_at, latitude=latitude, longitude=longitude)
        if kind == ItemKind.PHOTO
        else None
    )
    return await run_in_threadpool(
        svc.importer.add_upload,
        data,
        kind=kind,
        title=title or (file.filename or ""),
        artist=artist,
        description=description,
        photo=photo,
    )


# -- museums -------------------------------------------------------------------


@router.get("/museums")
def museums() -> list[dict[str, str]]:
    return [{"key": k, "name": m.name} for k, m in MUSEUMS.items()]


@router.get("/museums/{source}/search", response_model=RemotePage)
async def museum_search(
    source: str, svc: Svc, q: str, page: int = 1, limit: int | None = None
) -> RemotePage:
    """One museum, or ``all`` of them (``limit`` results from each)."""
    failed: list[str] = []
    if source == ALL:
        total, items, failed = await run_in_threadpool(svc.importer.search_all, q, limit or 8, page)
    elif source in MUSEUMS:
        try:
            total, items = await run_in_threadpool(
                svc.importer.search, source, q, limit or 24, page
            )
        except httpx.HTTPError as err:
            raise HTTPException(502, f"{source}: {err}") from err
    else:
        raise HTTPException(404, f"unknown museum {source!r}")
    return RemotePage(
        total=total,
        items=[RemoteItem(item=i, in_library=svc.library.has(i.id)) for i in items],
        failed=failed,
    )


@router.post("/museums/{source}/import", response_model=Item)
async def museum_import(source: str, request: ImportRequest, svc: Svc) -> Item:
    if source not in MUSEUMS:
        raise HTTPException(404, f"unknown museum {source!r}")
    try:
        item = await run_in_threadpool(svc.importer.import_one, source, request.source_id)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{source}: {err}") from err
    if item is None:
        raise HTTPException(404, "not found or not in the public domain")
    return item


@router.post("/museums/{source}/import-search")
def museum_import_search(source: str, request: ImportSearchRequest, svc: Svc) -> dict[str, Any]:
    if source != ALL and source not in MUSEUMS:
        raise HTTPException(404, f"unknown museum {source!r}")

    def work(job: Job) -> None:
        svc.importer.import_search(source, request.query, request.limit, job)

    job = svc.importer.start_job(f"{source}: {request.query}", work)
    return {"job_id": job.id}


@router.get("/library/packs")
def packs(svc: Svc) -> list[dict[str, Any]]:
    """Themed batches of museum works to add in one go."""
    running = {j.description for j in svc.importer.jobs.values() if not j.finished}
    return [
        {
            "key": p.key,
            "name": p.name,
            "description": p.description,
            "size": p.size,
            "importing": f"pack: {p.key}" in running,
        }
        for p in PACKS
    ]


@router.post("/library/packs/{key}/import")
def pack_import(key: str, svc: Svc) -> dict[str, Any]:
    try:
        found = pack(key)
    except KeyError as err:
        raise HTTPException(404, str(err)) from err
    running = next(
        (
            j
            for j in svc.importer.jobs.values()
            if j.description == f"pack: {key}" and not j.finished
        ),
        None,
    )
    if running is not None:
        return {"job_id": running.id}

    def work(job: Job) -> None:
        import_queries(svc.importer, found.queries, job)

    return {"job_id": svc.importer.start_job(f"pack: {key}", work).id}


@router.post("/library/draw")
def draw(request: DrawRequest, svc: Svc) -> dict[str, Any]:
    """Add random works by period, style and kind from several museums."""
    unknown = [s for s in request.sources if s not in MUSEUMS]
    if unknown or not request.sources:
        raise HTTPException(422, f"unknown museums {unknown}; choose from {sorted(MUSEUMS)}")
    spec = Discovery(
        year_from=request.year_from,
        year_to=request.year_to,
        style=request.style,
        kind=request.kind,
    )

    def work(job: Job) -> None:
        svc.importer.draw(
            spec, request.count, request.sources, job, min_suitability=request.min_suitability
        )

    return {"job_id": svc.importer.start_job(f"draw: {request.count}", work).id}


class FillRequest(BaseModel):
    rules: PlaylistRules
    count: int = Field(100, ge=1, le=500)


@router.post("/library/fill")
def fill(request: FillRequest, svc: Svc) -> dict[str, Any]:
    """Add museum works a smart playlist with ``rules`` would pick."""
    rules = request.rules
    if rules.favorites_only:
        raise HTTPException(422, "favourites can't be fetched from museums")
    if rules.kinds and ItemKind.ARTWORK not in rules.kinds:
        raise HTTPException(422, "only artworks come from museums")
    if rules.sources and not any(s in MUSEUMS for s in rules.sources):
        raise HTTPException(422, "the rules allow no museum")

    def work(job: Job) -> None:
        svc.importer.fill(rules, request.count, job)

    return {"job_id": svc.importer.start_job(f"fill: {request.count}", work).id}


@router.get("/album")
def album(svc: Svc) -> dict[str, Any]:
    """Last shared-album sync and how many photos the library holds."""
    photos = svc.library.query(PlaylistRules(kinds=[ItemKind.PHOTO]))[0]
    return {
        "url": svc.player.settings.album_url,
        "last_sync": svc.library.get_state("album_sync"),
        "photos": photos,
    }


@router.post("/album/sync")
def album_sync(svc: Svc) -> dict[str, Any]:
    url = svc.player.settings.album_url
    if not url:
        raise HTTPException(409, "no shared album link in settings")
    return {"job_id": svc.start_album_sync().id}


@router.get("/jobs")
def jobs(svc: Svc) -> list[dict[str, Any]]:
    return [vars(j) for j in svc.importer.jobs.values()]


@router.get("/jobs/{job_id}")
def job(job_id: str, svc: Svc) -> dict[str, Any]:
    found = svc.importer.jobs.get(job_id)
    if found is None:
        raise HTTPException(404)
    return vars(found)
