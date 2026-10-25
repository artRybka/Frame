"""The panel's address, PIN and MAC, set in the app (Ramka → Ekran)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

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
