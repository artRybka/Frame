"""The panel's address, PIN and MAC, set in the app (Ramka → Ekran), and
the frame's app it runs (panel_app.py)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..device import MdcError
from ..panel_app import AppView
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


@router.put("/app/certificates", response_model=AppView)
async def put_certificates(
    author: Annotated[UploadFile, File()],
    distributor: Annotated[UploadFile, File()],
    password: Annotated[str, Form()],
    svc: Svc,
) -> AppView:
    """The Samsung certificates the frame's app is signed with (author.p12,
    distributor.p12 and their password, ``scripts/panel-app/upload-certs.sh``):
    kept in the data directory only; the server builds the package with them."""
    try:
        return svc.app.store_certificates(
            await author.read(), await distributor.read(), password.encode()
        )
    except ValueError as err:
        raise HTTPException(400, f"certificates: {err}") from err


@router.post("/app/install", response_model=AppView)
async def install_app(svc: Svc) -> AppView:
    """Point the panel's launcher at the frame's app and start it (installs
    it when the panel has another version)."""
    if not svc.device_configured:
        raise HTTPException(409, "panel not configured")
    try:
        await svc.app.install()
    except MdcError as err:
        raise HTTPException(502, f"panel: {err}") from err
    return svc.app.view()
