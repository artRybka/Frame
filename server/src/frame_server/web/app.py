"""HTTP API.

/panel/*  – fetched by the panel itself (no auth: it cannot send any).
/api/*    – used by the iOS app and tools; Bearer token when configured.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from .. import __version__
from ..config import Settings
from ..device import MdcError
from ..imaging import PRESETS, RenderSettings, Strategy
from ..service import FrameService, outcome_json
from ..store import PanelRequest

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    service = FrameService(settings)
    service.ensure_initial_content()

    app = FastAPI(title="Frame", version=__version__)
    app.state.service = service

    @app.middleware("http")
    async def log_panel_requests(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/panel/"):
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

    def require_token(request: Request) -> None:
        if not settings.api_token:
            return
        if request.headers.get("authorization") != f"Bearer {settings.api_token}":
            raise HTTPException(401, "invalid or missing API token")

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
    ) -> dict[str, object]:
        if settings_json:
            render_settings = RenderSettings.model_validate_json(settings_json)
        elif preset in PRESETS:
            render_settings = PRESETS[preset].model_copy(deep=True)
        else:
            raise HTTPException(400, f"unknown preset {preset!r}")
        if strategy is not None:
            render_settings.strategy = strategy
        data = await file.read()
        content = await run_in_threadpool(
            service.prepare,
            data,
            render_settings,
            raw=raw,
            title=title or (file.filename or ""),
            description=description,
            source="upload",
        )
        if not push:
            return {"content": asdict(content), "pushed": False}
        try:
            outcome = await service.push_current(wait=wait)
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err
        return outcome_json(outcome)

    @app.post("/api/device/push", dependencies=auth)
    async def push_again(wait: float = 90.0) -> dict[str, object]:
        try:
            return outcome_json(await service.push_current(wait=wait))
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err

    @app.get("/api/device/status", dependencies=auth)
    async def device_status() -> dict[str, object]:
        try:
            return await service.panel.status()
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err

    @app.post("/api/device/wake", dependencies=auth)
    async def device_wake() -> dict[str, object]:
        return {"sent": await service.panel.wake()}

    @app.post("/api/device/sleep", dependencies=auth)
    async def device_sleep() -> dict[str, object]:
        try:
            await service.panel.sleep()
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err
        return {"ok": True}

    @app.get("/api/debug/panel-requests", dependencies=auth)
    def panel_requests() -> list[dict[str, object]]:
        return [asdict(r) for r in service.store.recent_requests]

    return app
