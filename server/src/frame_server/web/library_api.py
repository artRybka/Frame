"""Library, museum search and import."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from anyio import CapacityLimiter, to_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from ..ai import PolishText
from ..ai.keywords import KIND as KEYWORDS
from ..ai.keywords import polish_words
from ..ai.pl_text import KIND as PL_TEXT
from ..fsutil import own_files
from ..imaging.layout import (
    WHOLE,
    Crop,
    Fit,
    Orientation,
    Plan,
    canvas_size,
    fit_area,
    load_image,
)
from ..imaging.pipeline import RenderSettings, encode_image, plan_for, render_original
from ..library import Facets, Item, ItemKind, ItemSummary, Job, Look, PhotoInfo, PlaylistRules
from ..library.duplicates import work_key
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
    #: Only for a photo sent once ("Zdjęcie na ramkę"): over the whole frame
    #: or in a passe-partout.
    look: Look | None = None


class ShowRequest(BaseModel):
    hold: str | int | None = None


class RemoteItem(BaseModel):
    item: Item
    in_library: bool
    #: What copies of one work from several sources share
    #: (``duplicates.work_key``), to leave out copies on later pages.
    work: str = ""
    #: The library's copy of the work, when this item is a better one
    #: (the catalogue shows that copy already).
    twin: str | None = None
    #: In a search's later answers: the worse copy, shown before, that this
    #: one takes the place of.
    replaces: str | None = None


def remote_items(svc: FrameService, items: list[Item], copies: bool = True) -> list[RemoteItem]:
    """Works found for the app, each once, marked whether the library holds
    them. With ``copies`` (results from several sources) a work the library
    holds from another source comes as the library's copy, unless this one
    is from a more reliable source than a copy only the server added."""
    found: dict[str, RemoteItem] = {}
    for item in items:
        twin: str | None = None
        if copies and not svc.library.has(item.id):
            if copy := svc.importer.copy_of(item):
                item = copy
            elif other := svc.library.twin(item):
                twin = other.id
        held = svc.library.has(item.id)
        found.setdefault(
            item.id, RemoteItem(item=item, in_library=held, work=work_key(item), twin=twin)
        )
    return list(found.values())


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


#: Threads for pictures, apart from the server's own pool that the app's
#: quick requests ("Teraz", the queue, settings) and the player share: a
#: grid's burst of thumbnails, each waiting for a museum, must not hold them
#: up. What the owner looks at (a card's original, a preview) has threads of
#: its own, so it never waits for a grid either.
THUMB_THREADS = CapacityLimiter(16)
SHOWN_THREADS = CapacityLimiter(8)


def _item(svc: FrameService, item_id: str) -> Item:
    item = svc.library.get(item_id)
    if item is None:
        raise HTTPException(404, f"no item {item_id!r}")
    return item


async def _work(
    svc: FrameService, item_id: str, save: bool = False, threads: CapacityLimiter | None = None
) -> Item:
    """A library item or any museum work (``<museum>:<id>``). Museum works
    are added to the library with ``save``: when the owner shows, crops,
    likes or otherwise keeps one. ``threads``: where a museum is asked."""
    lookup = svc.importer.save if save else svc.importer.resolve
    try:
        item = await to_thread.run_sync(lookup, item_id, limiter=threads)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{item_id}: {err}") from err
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
    term: Annotated[list[str] | None, Query()] = None,
    color: Annotated[list[str] | None, Query()] = None,
    kind: Annotated[list[ItemKind] | None, Query()] = None,
    year_from: Annotated[int | None, Query(ge=0, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=0, le=2100)] = None,
    source: Annotated[list[str] | None, Query()] = None,
    favorites: bool = False,
    kept: bool = False,
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
        terms=term or [],
        colors=color or [],
        kinds=kind or [],
        year_from=year_from,
        year_to=year_to,
        sources=source or [],
        favorites_only=favorites,
        kept_only=kept,
    )
    total, items = svc.library.query(rules, sort=sort, offset=offset, limit=limit, seed=seed)
    return ItemPage(total=total, items=[ItemSummary.of(i) for i in items])


@router.get("/library/facets", response_model=Facets)
def facets(svc: Svc) -> Facets:
    return svc.library.facets()


@router.get("/library/items/{item_id}", response_model=Item)
async def get_item(item_id: str, svc: Svc) -> Item:
    return await _work(svc, item_id)


class PolishView(BaseModel):
    """A work's Polish texts for its card. ``status``: "ready"; "waiting"
    (being written, ask again); "none" (the model could not); "off" (no key,
    switched off, or no museum work)."""

    status: Literal["ready", "waiting", "none", "off"]
    text: PolishText | None = None


@router.get("/library/items/{item_id}/polish", response_model=PolishView)
async def item_polish(
    item_id: str, svc: Svc, wait: Annotated[float, Query(ge=0, le=60)] = 0
) -> PolishView:
    """The work's Polish title and texts, asked for now if it has none;
    ``wait``: seconds to wait for them."""
    job = svc.pl_text
    item = await _work(svc, item_id)
    if not job.enabled() or not job.applies(item):
        return PolishView(status="off")
    if (text := job.text(item)) is not None:
        return PolishView(status="ready", text=text)
    if svc.library.get(item_id) is None:  # a museum work only looked at: pooled
        item = await run_in_threadpool(svc.importer.add, item.model_copy(update={"pooled": True}))
    future = svc.ai.need_now(item_id, PL_TEXT)
    if wait:
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
        except TimeoutError:
            pass
        except Exception:  # the model is unavailable: the card stays in English
            return PolishView(status="none")
    if (text := job.text(item)) is not None:
        return PolishView(status="ready", text=text)
    done = future.done() or job.fresh(item, svc.library.note(item_id, PL_TEXT))
    return PolishView(status="none" if done else "waiting")


class SeenView(BaseModel):
    """What the model saw in the picture, for the card; ``status`` as in
    PolishView."""

    status: Literal["ready", "waiting", "none", "off"]
    words: list[str] = Field(default_factory=list)  # Polish: things, places, mood


@router.post("/library/items/{item_id}/describe", response_model=SeenView)
async def describe_item(
    item_id: str, svc: Svc, wait: Annotated[float, Query(ge=0, le=60)] = 0
) -> SeenView:
    """The card opened: the model's jobs for this work or photo (keywords,
    Polish texts) go ahead of everything else. ``wait``: seconds to wait for
    the keywords; the Polish texts come from ``/polish``."""
    item = await _work(svc, item_id)
    jobs = [job for job in svc.ai.jobs.values() if job.enabled() and job.in_library(item)]
    if not jobs:
        return SeenView(status="off")
    if svc.library.get(item_id) is None:  # a museum work only looked at: pooled
        item = await run_in_threadpool(svc.importer.add, item.model_copy(update={"pooled": True}))
    futures = {job.kind: svc.ai.need_now(item_id, job.kind) for job in jobs}
    future = futures.get(KEYWORDS)
    if future is None:
        return SeenView(status="off")
    if wait:
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
        except TimeoutError:
            pass
        except Exception:  # the model is unavailable
            return SeenView(status="none")
    note = svc.library.note(item_id, KEYWORDS)
    if note is not None and svc.ai.jobs[KEYWORDS].fresh(item, note):
        words = polish_words(note.data)
        return SeenView(status="ready" if words else "none", words=words)
    return SeenView(status="none" if future.done() else "waiting")


@router.patch("/library/items/{item_id}", response_model=Item)
async def patch_item(item_id: str, patch: ItemPatch, svc: Svc) -> Item:
    item = await _work(svc, item_id, save=True)
    changes = patch.model_dump(exclude_none=True)
    if patch.look is not None:
        if item.look is None:
            raise HTTPException(422, "only a photo sent once has a look of its own")
        changes["look"] = patch.look
    updated = svc.library.update(item_id, **changes)
    assert updated is not None
    if changes.keys() & {"favorite", "excluded"}:
        svc.player.item_changed(item_id)  # e.g. a new favourite joins Ulubione playing now
    player, state = svc.player, svc.player.state
    if "look" in changes and updated.look != item.look:
        if state.current_item_id == item_id:
            svc.background(player.restyle())  # on the frame now: shown the new way
        elif state.requested[:1] == [item_id]:
            svc.background(player.render_ahead())  # next: drawn again ahead
    return updated


@router.delete("/library/items/{item_id}")
def delete_item(item_id: str, svc: Svc) -> dict[str, bool]:
    item = _item(svc, item_id)
    svc.library.delete(item_id)
    svc.images.remove(item)
    return {"deleted": True}


@router.get("/library/items/{item_id}/thumb")
async def item_thumb(item_id: str, svc: Svc) -> FileResponse:
    item = await _work(svc, item_id, threads=THUMB_THREADS)
    try:
        path = await to_thread.run_sync(svc.images.ensure_thumb, item, limiter=THUMB_THREADS)
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"thumbnail unavailable: {err}") from err
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.get("/library/items/{item_id}/image")
async def item_image(item_id: str, svc: Svc) -> FileResponse:
    """The original as the card shows it: before any download in the background."""
    item = await _work(svc, item_id, threads=SHOWN_THREADS)
    try:
        path, original = await to_thread.run_sync(
            svc.images.picture, item, True, limiter=SHOWN_THREADS
        )
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"image unavailable: {err}") from err
    # Without the original, its thumbnail: asked for again next time.
    cache = "max-age=86400" if original else "no-store"
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": cache})


_preview_locks: dict[str, asyncio.Lock] = {}
PREVIEW_CACHE_FILES = 200
#: How long a preview waits for the work's Polish texts (asked first in line).
PREVIEW_POLISH_SECONDS = 20.0
NO_STORE = {"Cache-Control": "no-store"}
PREVIEW_KIND = "fast"  # part of the cache key: earlier previews went through the whole render


def _prune(directory: Path, keep: int) -> None:
    files = list(own_files(directory))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


@router.get("/library/items/{item_id}/preview")
async def item_preview(
    item_id: str, svc: Svc, settings: str | None = None, framing: str | None = None
) -> Response:
    """The picture framed as on the panel (crop, mat, lettering), in its own
    colours: the correction for the inks is left to the panel's image.

    With the saved settings, or with ``settings`` (FrameSettings JSON; only
    orientation and presentation matter) to try a framing before saving it.
    ``framing`` (Framing JSON) likewise tries crops before they are saved:
    the ones it gives replace the saved ones for that orientation.
    """
    item = await _work(svc, item_id, threads=SHOWN_THREADS)
    frame_settings = svc.player.settings
    try:
        if settings:
            frame_settings = FrameSettings.model_validate_json(settings)
        if framing:
            orientation = frame_settings.orientation.value
            saved = item.framing.get(orientation) or Framing()
            trial = Framing.model_validate_json(framing).model_dump(exclude_none=True)
            tried = Framing.model_validate(saved.model_dump() | trial)
            item = item.model_copy(update={"framing": {**item.framing, orientation: tried}})
    except ValidationError as err:
        raise HTTPException(422, f"invalid preview: {err}") from err
    # The texts on the mat in Polish, as the frame will show them: an
    # English preview would stay in the app's cache after they come.
    await svc.player.wait_for_polish(item, frame_settings, PREVIEW_POLISH_SECONDS)
    render_settings = svc.player.render_settings(item, frame_settings)
    board = svc.player.preview_board(item, frame_settings)  # MULTI: with the photos beside it
    ids = ",".join(i.id for i in board)
    key = hashlib.sha1(
        (PREVIEW_KIND + render_settings.model_dump_json() + svc.palette.name + ids).encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]
    path = svc.images.thumbs.parent / "previews" / f"{item.file_stem}-{key}.jpg"
    if not path.is_file():
        async with _preview_locks.setdefault(path.name, asyncio.Lock()):
            if not path.is_file():
                try:
                    pictures = [
                        await to_thread.run_sync(
                            svc.images.picture, shown, True, limiter=SHOWN_THREADS
                        )
                        for shown in board
                    ]
                except (httpx.HTTPError, OSError) as err:
                    raise HTTPException(502, f"image unavailable: {err}") from err
                sources = [p for p, _ in pictures]

                def build() -> bytes:
                    multi = svc.player.multi(item, frame_settings)
                    img = render_original(
                        sources, render_settings, svc.palette, multi=multi, seed=ids
                    )
                    img.thumbnail((1280, 1280))
                    return encode_image(img, "jpeg", quality=90)

                data = await to_thread.run_sync(build, limiter=SHOWN_THREADS)
                if not all(original for _, original in pictures):
                    # Drawn from a thumbnail: not kept, the original may come.
                    return Response(data, media_type="image/jpeg", headers=NO_STORE)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                _prune(path.parent, PREVIEW_CACHE_FILES)
    # Without ``settings`` the address stays the same when the presentation
    # changes: the app must ask again rather than keep the old framing.
    cache = "max-age=3600" if settings else "no-cache"
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": cache})


Box = tuple[float, float, float, float]  # x, y, w, h as fractions of the canvas


class FramingWindow(BaseModel):
    role: str  # "picture" (FIT, DESCRIPTION), "fill" or "detail"
    aspect: float  # width / height of the window on the frame
    crop: Crop
    custom: bool  # set by the user (else chosen automatically)
    rect: Box | None = None  # where the window is on the canvas
    area: Box | None = None  # FIT: where a window of another shape would be centred


class FramingView(BaseModel):
    orientation: Orientation
    fit: Fit  # how the picture is shown in this orientation
    width: int  # the picture, in pixels
    height: int
    windows: list[FramingWindow]  # what can be adjusted; none with a passe-partout


class FramingUpdate(BaseModel):
    orientation: Orientation
    # One for FILL and FIT; DESCRIPTION: the picture's and the close-up's,
    # or only the close-up's (apps from before the picture could be cropped).
    crops: list[Crop]


def _framing_plan(
    svc: FrameService, item: Item, orientation: Orientation, automatic: bool = False
) -> tuple[Plan, tuple[int, int], RenderSettings]:
    settings = svc.player.settings.model_copy(update={"orientation": orientation})
    render_settings = svc.player.render_settings(item, settings)
    if automatic:  # as if nothing had been saved
        layout = render_settings.layout.model_copy(
            update={"crop": None, "detail": None, "picture_crop": None, "fit_crop": None}
        )
        render_settings = render_settings.model_copy(update={"layout": layout})
    img = load_image(svc.images.ensure_image(item))
    if svc.player.multi(item, settings):  # each photo cropped automatically to its window
        return Plan(Fit.MULTI, canvas_size(orientation), []), img.size, render_settings
    plan = plan_for(img, render_settings.layout, caption=bool(render_settings.caption))
    return plan, img.size, render_settings


def _box(rect: tuple[int, int, int, int], canvas: tuple[int, int]) -> Box:
    x, y, w, h = rect
    cw, ch = canvas
    return round(x / cw, 5), round(y / ch, 5), round(w / cw, 5), round(h / ch, 5)


def _framing_view(
    item: Item,
    orientation: Orientation,
    plan: Plan,
    size: tuple[int, int],
    render_settings: RenderSettings,
    automatic: bool = False,
) -> FramingView:
    saved = item.framing.get(orientation.value) or Framing()
    custom = not automatic and {
        Fit.FILL: saved.fill is not None,
        Fit.DESCRIPTION: saved.detail is not None or saved.picture is not None,
        Fit.FIT: saved.fit is not None,
    }.get(plan.fit, False)
    area = None
    if plan.fit == Fit.FIT:
        margin, caption = render_settings.layout.margin, bool(render_settings.caption)
        area = _box(fit_area(plan.canvas, margin, caption), plan.canvas)
    windows = [
        FramingWindow(
            role=w.role,
            aspect=round(w.aspect, 4),
            crop=w.crop,
            custom=custom,
            rect=_box(w.rect, plan.canvas),
            area=area if w.role == "picture" else None,
        )
        for w in plan.windows
        if w.crop is not None
    ]
    return FramingView(
        orientation=orientation, fit=plan.fit, width=size[0], height=size[1], windows=windows
    )


async def _plan_and_view(
    svc: FrameService, item: Item, orientation: Orientation, automatic: bool = False
) -> FramingView:
    try:
        plan, size, render_settings = await run_in_threadpool(
            _framing_plan, svc, item, orientation, automatic
        )
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"image unavailable: {err}") from err
    return _framing_view(item, orientation, plan, size, render_settings, automatic)


@router.get("/library/items/{item_id}/framing", response_model=FramingView)
async def get_framing(
    item_id: str, svc: Svc, orientation: Orientation | None = None, automatic: bool = False
) -> FramingView:
    """How the picture is cropped on the frame, and what can be adjusted.
    With ``automatic`` the crops the server would choose, ignoring saved ones
    (nothing is changed: the app offers them before the user sends them)."""
    item = await _work(svc, item_id)
    orientation = orientation or svc.player.settings.orientation
    return await _plan_and_view(svc, item, orientation, automatic)


@router.put("/library/items/{item_id}/framing", response_model=FramingView)
async def put_framing(item_id: str, update: FramingUpdate, svc: Svc) -> FramingView:
    """Save a corrected crop (FILL, or FIT with its shape) or the picture
    and its close-up (DESCRIPTION) for this picture."""
    item = await _work(svc, item_id, save=True)
    current = await _plan_and_view(svc, item, update.orientation)
    framing = item.framing.get(update.orientation.value, Framing()).model_copy()
    if current.fit == Fit.FILL and len(update.crops) == 1:
        framing.fill = update.crops[0]
    elif current.fit == Fit.DESCRIPTION and len(update.crops) == 2:
        picture, framing.detail = update.crops
        # The whole picture, untouched, stays automatic.
        framing.picture = None if _uncropped(picture) else picture
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
    item = await _work(svc, item_id, save=True)
    current = await _plan_and_view(svc, item, orientation)
    framing = item.framing.get(orientation.value, Framing()).model_copy()
    fields = {Fit.FILL: ["fill"], Fit.DESCRIPTION: ["detail", "picture"], Fit.FIT: ["fit"]}
    if current.fit not in fields:
        raise HTTPException(422, f"{current.fit.value}: nothing to reset")
    for field in fields[current.fit]:
        setattr(framing, field, None)
    empty = framing == Framing()
    item = _save_framing(svc, item, orientation, None if empty else framing)
    return await _plan_and_view(svc, item, orientation)


def _uncropped(crop: Crop) -> bool:
    """The picture's window as it is without a correction (layout.WHOLE)."""
    off = max(abs(crop.zoom - WHOLE.zoom), abs(crop.x - WHOLE.x), abs(crop.y - WHOLE.y))
    return crop.aspect is None and off < 1e-3


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
    item = await _work(svc, item_id, save=True)
    _remember_sent(svc, item)
    svc.background(svc.player.show(item, "app", hold_from(request.hold)))
    return {"accepted": True, "item_id": item.id}


@router.post("/library/items/{item_id}/queue", status_code=202)
async def queue_item(item_id: str, svc: Svc) -> dict[str, Any]:
    """The owner's "Dodaj do kolejki": the work is shown at the next change."""
    item = await _work(svc, item_id, save=True)
    svc.player.queue_next(item.id)
    _remember_sent(svc, item)
    svc.background(svc.player.get_ready())
    return {"accepted": True, "item_id": item.id}


def _remember_sent(svc: FrameService, item: Item) -> None:
    """A photo sent once joins "Historia przesłanych" and gets its keywords
    ahead of the background."""
    svc.player.remember_sent(item)
    if item.look is not None:
        svc.ai.need_now(item.id, KEYWORDS)


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
    look: Annotated[str | None, Form()] = None,
) -> Item:
    """Add a picture to the library (e.g. photos from the phone's camera roll).

    With ``look`` (Look JSON) a photo is sent once ("Zdjęcie na ramkę"): it
    is shown or queued from the app with that look and stays out of every
    list and rotation."""
    data = await file.read()
    photo = (
        PhotoInfo(taken_at=taken_at, latitude=latitude, longitude=longitude)
        if kind == ItemKind.PHOTO
        else None
    )
    try:
        single = Look.model_validate_json(look) if look else None
    except ValidationError as err:
        raise HTTPException(422, f"invalid look: {err}") from err
    if single is not None and kind != ItemKind.PHOTO:
        raise HTTPException(422, "only photos are sent once")
    return await run_in_threadpool(
        svc.importer.add_upload,
        data,
        kind=kind,
        title=title or (file.filename or ""),
        artist=artist,
        description=description,
        photo=photo,
        look=single,
    )


# -- museums -------------------------------------------------------------------


@router.get("/museums")
def museums(svc: Svc) -> list[dict[str, str]]:
    return [{"key": k, "name": MUSEUMS[k].name} for k in svc.importer.sources()]


@router.get("/museums/{source}/search", response_model=RemotePage)
async def museum_search(
    source: str, svc: Svc, q: str, page: int = 1, limit: int | None = None
) -> RemotePage:
    """One museum, or ``all`` of them (``limit`` results from each)."""
    failed: list[str] = []
    if source == ALL:
        total, items, failed = await run_in_threadpool(svc.importer.search_all, q, limit or 8, page)
    elif source in svc.importer.sources():
        try:
            total, items = await run_in_threadpool(
                svc.importer.search, source, q, limit or 24, page
            )
        except httpx.HTTPError as err:
            raise HTTPException(502, f"{source}: {err}") from err
    else:
        raise HTTPException(404, f"unknown museum {source!r}")
    return RemotePage(
        total=total, items=remote_items(svc, items, copies=source == ALL), failed=failed
    )


@router.post("/museums/{source}/import", response_model=Item)
async def museum_import(source: str, request: ImportRequest, svc: Svc) -> Item:
    if source not in svc.importer.sources():
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
    if source != ALL and source not in svc.importer.sources():
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
    offered = svc.importer.sources()
    unknown = [s for s in request.sources if s not in offered]
    if unknown or not request.sources:
        raise HTTPException(422, f"unknown museums {unknown}; choose from {sorted(offered)}")
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
    if rules.asks_mine():
        raise HTTPException(422, "the owner's own works can't be fetched from museums")
    if rules.kinds and ItemKind.ARTWORK not in rules.kinds:
        raise HTTPException(422, "only artworks come from museums")
    if rules.sources and not any(s in svc.importer.sources() for s in rules.sources):
        raise HTTPException(422, "the rules allow no museum")

    def work(job: Job) -> None:
        svc.importer.fill(rules, request.count, job)

    return {"job_id": svc.importer.start_job(f"fill: {request.count}", work).id}


@router.get("/jobs")
def jobs(svc: Svc) -> list[dict[str, Any]]:
    return [vars(j) for j in svc.importer.jobs.values()]


@router.get("/jobs/{job_id}")
def job(job_id: str, svc: Svc) -> dict[str, Any]:
    found = svc.importer.jobs.get(job_id)
    if found is None:
        raise HTTPException(404)
    return vars(found)
