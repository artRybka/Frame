"""Tailscale built into the app (Konfiguracja → Dostęp spoza domu).

Every phone reads the key, members too, to join the tailnet with it, and
the server's own address there; only the owner sets or forgets them. See
tailnet.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..service import FrameService
from ..tailnet import AddressInvalid, KeyInvalid
from .deps import require_owner, require_token, service

router = APIRouter(prefix="/api/tailnet", dependencies=[Depends(require_token)], tags=["tailnet"])
Svc = Annotated[FrameService, Depends(service)]


class TailnetView(BaseModel):
    key_set: bool
    key_tail: str | None
    #: The whole key, for the phone to join with.
    key: str | None
    saved_at: str | None
    #: The server's address in the tailnet (``http://nas.tail….ts.net:8099``),
    #: found by the owner's phone; None until then.
    address: str | None = None


class KeyUpdate(BaseModel):
    key: str


class AddressUpdate(BaseModel):
    address: str


def _view(svc: FrameService) -> TailnetView:
    found = svc.tailnet.get()
    return TailnetView(
        key_set=found is not None,
        key_tail=svc.tailnet.tail(),
        key=found.key if found else None,
        saved_at=found.saved_at if found else None,
        address=svc.tailnet.address(),
    )


@router.get("", response_model=TailnetView)
def get_tailnet(svc: Svc) -> TailnetView:
    return _view(svc)


@router.put("/key", response_model=TailnetView, dependencies=[Depends(require_owner)])
def put_key(update: KeyUpdate, svc: Svc) -> TailnetView:
    try:
        svc.tailnet.set(update.key)
    except KeyInvalid as err:
        raise HTTPException(400, str(err)) from err
    return _view(svc)


@router.delete("/key", response_model=TailnetView, dependencies=[Depends(require_owner)])
def delete_key(svc: Svc) -> TailnetView:
    svc.tailnet.set(None)
    return _view(svc)


@router.put("/address", response_model=TailnetView, dependencies=[Depends(require_owner)])
def put_address(update: AddressUpdate, svc: Svc) -> TailnetView:
    try:
        svc.tailnet.set_address(update.address)
    except AddressInvalid as err:
        raise HTTPException(400, str(err)) from err
    return _view(svc)


@router.delete("/address", response_model=TailnetView, dependencies=[Depends(require_owner)])
def delete_address(svc: Svc) -> TailnetView:
    svc.tailnet.set_address(None)
    return _view(svc)
