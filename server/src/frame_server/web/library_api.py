"""Library, museum search and import."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from ..imaging.pipeline import encode_image, render
from ..library import Facets, Item, ItemKind, ItemSummary, Job, PhotoInfo, PlaylistRules
from ..library.museums import MUSEUMS
from ..library.repo import SortKey
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


class ImportRequest(BaseModel):
    source_id: str


class ImportSearchRequest(BaseModel):
    query: str
    limit: int = 24


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
    key = hashlib.sha1(
        (render_settings.model_dump_json() + svc.palette.name).encode(), usedforsecurity=False
    ).hexdigest()[:12]
    path = svc.images.thumbs.parent / "previews" / f"{item.file_stem}-{key}.png"
    if not path.is_file():
        async with _preview_locks.setdefault(path.name, asyncio.Lock()):
            if not path.is_file():
                source = await run_in_threadpool(svc.images.ensure_image, item)

                def build() -> None:
                    result = render(source, render_settings, svc.palette)
                    img = result.preview_image()
                    img.thumbnail((1280, 1280))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(encode_image(img, "png"))
                    _prune(path.parent, PREVIEW_CACHE_FILES)

                await run_in_threadpool(build)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


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
) -> Item:
    data = await file.read()
    photo = PhotoInfo(taken_at=taken_at) if kind == ItemKind.PHOTO else None
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
    source: str, svc: Svc, q: str, page: int = 1, limit: int = 24
) -> RemotePage:
    if source not in MUSEUMS:
        raise HTTPException(404, f"unknown museum {source!r}")
    try:
        total, items = await run_in_threadpool(svc.importer.search, source, q, limit, page)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{source}: {err}") from err
    return RemotePage(
        total=total,
        items=[RemoteItem(item=i, in_library=svc.library.has(i.id)) for i in items],
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
    if source not in MUSEUMS:
        raise HTTPException(404, f"unknown museum {source!r}")

    def work(job: Job) -> None:
        svc.importer.import_search(source, request.query, request.limit, job)

    job = svc.importer.start_job(f"{source}: {request.query}", work)
    return {"job_id": job.id}


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
