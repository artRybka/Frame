"""Updating the server from the app (Ramka → trybik → Konfiguracja → Serwer
ramki): only where the `frame updater` helper runs next to it (Synology),
see updates.py."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..service import FrameService
from ..updates import ServerUpdateView, UpdateFolder
from .deps import require_token, service

router = APIRouter(
    prefix="/api/server/update", dependencies=[Depends(require_token)], tags=["server"]
)
Svc = Annotated[FrameService, Depends(service)]

NO_HELPER = "obok serwera nie działa pomocnik aktualizacji (deploy/synology/README.md)"


def _folder(svc: FrameService) -> UpdateFolder:
    return UpdateFolder(svc.settings.data_dir / "update")


@router.get("", response_model=ServerUpdateView)
def get_update(svc: Svc) -> ServerUpdateView:
    return _folder(svc).view()


@router.post("/check", response_model=ServerUpdateView)
def check(svc: Svc) -> ServerUpdateView:
    """The helper pulls the image now instead of in a few hours."""
    folder = _folder(svc)
    if not folder.helper_alive():
        raise HTTPException(409, NO_HELPER)
    if folder.pending() != "update":
        folder.request("check")
    return folder.view()


@router.post("", response_model=ServerUpdateView)
def update(svc: Svc) -> ServerUpdateView:
    """The helper recreates the server's container on the newest image: the
    server goes away for about a minute and comes back as the new version."""
    folder = _folder(svc)
    if not folder.helper_alive():
        raise HTTPException(409, NO_HELPER)
    if folder.view().state == "updating":
        raise HTTPException(409, "aktualizacja już trwa")
    folder.request("update")
    return folder.view()
