"""HTTP API.

/panel/*  – fetched by the panel itself (no auth: it cannot send any).
/api/*    – used by the iOS app and tools; Bearer token when configured.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from .. import __version__
from ..config import Settings
from ..device import MdcError
from ..imaging import PRESETS, RenderSettings, Strategy
from ..imaging.layout import load_image
from ..library.seed import seed_playlists
from ..library.style import AUTO, preset_for_photo
from ..player import hold_from
from ..power import WakeResult
from ..progress import DisplayProgress, Stage
from ..service import FrameService, outcome_json
from ..status import DeviceStatus
from ..store import PanelRequest
from . import (
    ai_api,
    calibration_api,
    device_api,
    discover_api,
    library_api,
    player_api,
    playlists_api,
    storage_api,
)
from .deps import require_token

log = logging.getLogger(__name__)

# The panel reports download progress (and failures) here, at the root of the
# content server, whatever path the manifest came from.
PROGRESS_PATH = "/content-transfer-progress"


def _photo_preset(data: bytes) -> str:
    try:
        return preset_for_photo(load_image(data))
    except OSError:
        return "photo"  # not an image: prepare() says so


async def poll_status(service: FrameService) -> None:
    """Refresh the panel status now and then. On battery only rarely: every
    MDC session may keep the panel awake (to be measured in E8)."""
    await asyncio.sleep(5)
    while True:
        minutes = service.player.settings.status_poll_minutes
        if minutes and service.device_configured:
            last = service.status.status.checked_at
            stale = last is None or datetime.fromisoformat(last) < datetime.now(UTC) - timedelta(
                hours=6
            )
            asleep = service.power.deep_asleep(datetime.now(UTC))
            if not asleep and (not service.status.on_battery or stale):
                await service.status.refresh()
        await asyncio.sleep(max(minutes, 1) * 60)


async def sync_albums_periodically(service: FrameService, minutes: int = 30) -> None:
    await asyncio.sleep(20)
    while True:
        service.albums.sync_all()
        await asyncio.sleep(minutes * 60)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    service = FrameService(settings)
    service.ensure_initial_content()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks = []
        if settings.scheduler:
            tasks = [
                asyncio.create_task(service.player.run()),
                asyncio.create_task(service.power.run()),
                asyncio.create_task(poll_status(service)),
                asyncio.create_task(sync_albums_periodically(service)),
            ]
            service.ai.start()
        seed_playlists(service.importer)
        service.albums.migrate()  # once: the album of older settings becomes a playlist
        service.player.reset_library()  # once: a clean start for the catalogue
        service.player.drop_set_aside()  # once: the catalogue leaves them out now
        service.player.drop_spare_copies()  # a work once, from the most reliable source
        if settings.seed_library:
            service.player.top_up()  # Suggestions come from museums, as needed
        if settings.scheduler:
            # Discover's first visit then finds its themes worked out.
            threading.Thread(target=discover_api.warm_up, args=(service,), daemon=True).start()
        yield
        for task in tasks:
            task.cancel()
        service.ai.stop()
        service.library.close()

    app = FastAPI(title="Frame", version=__version__, lifespan=lifespan)
    app.state.service = service
    routers = (
        library_api.router,
        discover_api.router,
        playlists_api.router,
        player_api.router,
        calibration_api.router,
        device_api.router,
        storage_api.router,
        ai_api.router,
    )
    for router in routers:
        app.include_router(router)

    @app.middleware("http")
    async def log_panel_requests(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/panel/") or request.url.path == PROGRESS_PATH:
            entry = PanelRequest(
                time=datetime.now(UTC).isoformat(timespec="milliseconds"),
                client=request.client.host if request.client else "",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                user_agent=request.headers.get("user-agent", ""),
                headers=dict(request.headers),
            )
            service.store.log_request(entry)
            log.info("panel %s %s -> %s", entry.method, request.url, entry.status)
        return response

    auth = [Depends(require_token)]

    # -- panel ---------------------------------------------------------------

    @app.get("/panel/content.json")
    def panel_manifest() -> Response:
        manifest = service.store.manifest(settings.base_url())
        if manifest is None:
            raise HTTPException(404)
        return Response(manifest.encode(), media_type="application/json")

    @app.get("/panel/images/{name}")
    def panel_image(name: str) -> FileResponse:
        path = service.store.image_path(name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path)

    @app.post(PROGRESS_PATH)
    async def panel_progress(request: Request) -> dict[str, object]:
        body = (await request.body())[:2000].decode("utf-8", "replace")
        log.info("panel progress report: %s", body)
        return {}

    # -- API -----------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"ok": True, "version": __version__, "palette": service.palette.name}

    @app.get("/api/now", dependencies=auth)
    def now() -> dict[str, object]:
        content = service.store.current()
        if content is None:
            raise HTTPException(404)
        return asdict(content) | {"preview_url": f"/api/previews/{content.file_id}.png"}

    @app.get("/api/previews/{file_id}.png", dependencies=auth)
    def preview(file_id: str) -> FileResponse:
        path = service.store.preview_path(file_id)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type="image/png")

    @app.get("/api/presets", dependencies=auth)
    def presets() -> dict[str, object]:
        return {name: p.model_dump(mode="json") for name, p in PRESETS.items()}

    @app.post("/api/display", dependencies=auth)
    async def display(
        file: Annotated[UploadFile, File()],
        preset: Annotated[str, Form()] = "photo",
        strategy: Annotated[Strategy | None, Form()] = None,
        settings_json: Annotated[str | None, Form()] = None,
        raw: Annotated[bool, Form()] = False,
        title: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
        push: Annotated[bool, Form()] = True,
        wait: Annotated[float, Form()] = 90.0,
        hold: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        data = await file.read()
        if preset == AUTO and not settings_json:
            preset = await run_in_threadpool(_photo_preset, data)
        if settings_json:
            render_settings = RenderSettings.model_validate_json(settings_json)
        elif preset in PRESETS:
            render_settings = PRESETS[preset].model_copy(deep=True)
        else:
            raise HTTPException(400, f"unknown preset {preset!r}")
        if strategy is not None:
            render_settings.strategy = strategy
        title = title or (file.filename or "")
        if push:
            service.progress.begin(title)
        try:
            content = await run_in_threadpool(
                service.prepare,
                data,
                render_settings,
                raw=raw,
                title=title,
                description=description,
                source="upload",
            )
        except Exception as err:
            if push:
                service.progress.finish(Stage.FAILED, str(err))
            raise
        service.player.note_external(hold_from(hold))
        if not push or not service.device_configured:
            message = "" if not push else "panel not configured"
            if push:
                service.progress.finish(Stage.FAILED, message)
            return {"content": asdict(content), "pushed": False, "message": message}
        try:
            outcome = await service.push_current(wait=wait)
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err
        return outcome_json(outcome)

    @app.post("/api/device/push", dependencies=auth)
    async def push_again(wait: float = 90.0) -> dict[str, object]:
        if not service.device_configured:
            raise HTTPException(409, "panel not configured")
        try:
            return outcome_json(await service.push_current(wait=wait))
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err

    @app.get("/api/progress", dependencies=auth)
    def progress() -> DisplayProgress:
        """The picture on its way to the frame (the app polls this every second)."""
        return service.progress.view()

    @app.get("/api/device/status", dependencies=auth)
    async def device_status() -> DeviceStatus:
        return await service.status.refresh()

    @app.post("/api/device/wake", dependencies=auth)
    async def device_wake(sleep_after: bool = False) -> WakeResult:
        """``sleep_after``: the app's "Sprawdź stan" found the panel asleep
        and wakes it only to look at it."""
        if not service.device_configured:
            raise HTTPException(409, "panel not configured")
        return await service.power.wake_now(sleep_after=sleep_after)

    @app.post("/api/device/sleep", dependencies=auth)
    async def device_sleep() -> dict[str, object]:
        if not service.device_configured:
            raise HTTPException(409, "panel not configured")
        try:
            await service.power.sleep_now()
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err
        return {"ok": True}

    @app.get("/api/debug/panel-requests", dependencies=auth)
    def panel_requests() -> list[dict[str, object]]:
        return [asdict(r) for r in service.store.recent_requests]

    return app
