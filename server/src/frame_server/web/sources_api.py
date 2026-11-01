"""Keys of art sources (Ramka → trybik → Konfiguracja → Źródła dzieł).

The owner's only. A key is checked with its service before it is kept and
never sent back, only its last characters. See source_keys.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..service import FrameService
from ..source_keys import BY_KEY, SOURCES, KeyRejected, KeyUnchecked
from .deps import require_owner, service

router = APIRouter(
    prefix="/api/sources/keys", dependencies=[Depends(require_owner)], tags=["sources"]
)
Svc = Annotated[FrameService, Depends(service)]


class SourceKeyView(BaseModel):
    source: str
    name: str
    about: str
    signup: str
    key_set: bool
    key_tail: str | None
    key_from_app: bool  # saved in the app, not taken from frame.env


class KeyUpdate(BaseModel):
    key: str


def _views(svc: FrameService) -> list[SourceKeyView]:
    keys = svc.source_keys
    return [
        SourceKeyView(
            source=s.key,
            name=s.name,
            about=s.about,
            signup=s.signup,
            key_set=bool(keys.get(s.key)),
            key_tail=keys.tail(s.key),
            key_from_app=keys.from_app(s.key),
        )
        for s in SOURCES
    ]


def _known(source: str) -> None:
    if source not in BY_KEY:
        raise HTTPException(404, f"no keyed source {source}")


@router.get("", response_model=list[SourceKeyView])
def get_keys(svc: Svc) -> list[SourceKeyView]:
    return _views(svc)


@router.put("/{source}", response_model=list[SourceKeyView])
async def put_key(source: str, update: KeyUpdate, svc: Svc) -> list[SourceKeyView]:
    """Check the key with the source's service, then keep it."""
    _known(source)
    key = update.key.strip()
    if not key:
        raise HTTPException(400, "empty key")
    try:
        await run_in_threadpool(svc.source_keys.check, source, key)
    except KeyRejected as err:
        raise HTTPException(400, str(err)) from err
    except KeyUnchecked as err:
        raise HTTPException(502, str(err)) from err
    try:
        svc.source_keys.set(source, key)
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    return _views(svc)


@router.delete("/{source}", response_model=list[SourceKeyView])
def delete_key(source: str, svc: Svc) -> list[SourceKeyView]:
    """Forget the app's key (frame.env's applies again, if it has one)."""
    _known(source)
    svc.source_keys.set(source, None)
    return _views(svc)
