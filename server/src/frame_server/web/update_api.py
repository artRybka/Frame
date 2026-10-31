"""Updating the server from the app (Ramka → trybik → Konfiguracja → Serwer
ramki): only where the `frame updater` helper runs next to it (Synology),
see updates.py."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .. import registry
from ..service import FrameService
from ..updates import RegistryCheck, ServerUpdateView, UpdateFolder
from .deps import require_owner, require_token, service

router = APIRouter(
    prefix="/api/server/update", dependencies=[Depends(require_token)], tags=["server"]
)
log = logging.getLogger(__name__)
Svc = Annotated[FrameService, Depends(service)]

NO_HELPER = "obok serwera nie działa pomocnik aktualizacji (deploy/synology/README.md)"


def _folder(svc: FrameService) -> UpdateFolder:
    return UpdateFolder(svc.settings.data_dir / "update")


@router.get("", response_model=ServerUpdateView)
def get_update(svc: Svc) -> ServerUpdateView:
    return _folder(svc).view()


@router.post("/check", response_model=ServerUpdateView, dependencies=[Depends(require_owner)])
def check(svc: Svc) -> ServerUpdateView:
    """Asks the registry what the image's tag points at now (about a
    second); only when it cannot be reached the helper pulls the image, as
    before (a new release took minutes on the NAS)."""
    folder = _folder(svc)
    if not folder.helper_alive():
        raise HTTPException(409, NO_HELPER)
    view = folder.view()
    if view.pending == "update" or view.state in ("checking", "updating"):
        return view
    status = folder.status()
    ref = (status.image if status else None) or registry.DEFAULT_IMAGE
    try:
        latest = registry.latest_image(ref)
    except Exception as exc:
        log.warning("registry check of %s failed, the helper pulls instead: %s", ref, exc)
        folder.request("check")
        return folder.view()
    now = datetime.now(UTC).isoformat(timespec="seconds")
    folder.save_registry(RegistryCheck(checked_at=now, latest=latest))
    return folder.view()


@router.post("", response_model=ServerUpdateView, dependencies=[Depends(require_owner)])
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
