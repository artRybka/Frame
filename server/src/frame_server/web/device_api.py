"""The panel's address, PIN and MAC, set in the app (Ramka → Ekran), and
the Frame app it can run instead of being sent pictures (panel_app.py)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from ..device import MdcError
from ..panel_app import AppView, PackageInfo
from ..panel_config import PanelConfigUpdate, PanelConfigView
from ..service import FrameService
from .deps import require_token, service

router = APIRouter(prefix="/api/device", dependencies=[Depends(require_token)], tags=["device"])
Svc = Annotated[FrameService, Depends(service)]


@router.get("/config", response_model=PanelConfigView)
def get_config(svc: Svc) -> PanelConfigView:
    return svc.panel_config.view()


@router.put("/config", response_model=PanelConfigView)
def put_config(update: PanelConfigUpdate, svc: Svc) -> PanelConfigView:
    try:
        changed = svc.panel_config.save(update)
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    _after_change(svc, changed)
    return svc.panel_config.view()


@router.delete("/config", response_model=PanelConfigView)
def reset_config(svc: Svc) -> PanelConfigView:
    """Back to the values in frame.env or the add-on options."""
    _after_change(svc, svc.panel_config.reset())
    return svc.panel_config.view()


def _after_change(svc: FrameService, panel_changed: bool) -> None:
    if panel_changed:
        svc.status.forget()
    else:
        svc.status.status.configured = svc.device_configured


@router.get("/app", response_model=AppView)
def get_app(svc: Svc) -> AppView:
    return svc.app.view()


@router.put("/app/package", response_model=PackageInfo)
async def put_app_package(version: str, request: Request, svc: Svc) -> PackageInfo:
    """The package signed on the Mac (``scripts/panel-app/pack.sh --upload``)."""
    data = await request.body()
    if not data.startswith(b"PK"):
        raise HTTPException(400, "not a .wgt package (zip)")
    # The app reboots the panel to install it at its next question.
    return svc.app.store_package(data, version)


@router.post("/app/switch", response_model=AppView)
async def switch_app(on: bool, svc: Svc) -> AppView:
    """The panel's launcher to the Frame app (installs it at once) or back."""
    if not svc.device_configured:
        raise HTTPException(409, "panel not configured")
    try:
        await svc.app.switch(on)
    except MdcError as err:
        raise HTTPException(502, f"panel: {err}") from err
    if not on:
        svc.background(svc.push_current())  # its pictures come by MDC again
    return svc.app.view()
