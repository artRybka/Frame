"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from ..library.models import Item
from ..library.viewer import VIEWER, Viewer
from ..service import FrameService
from ..users import User


def service(request: Request) -> FrameService:
    svc: FrameService = request.app.state.service
    return svc


def _token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if header.startswith("Bearer "):
        return header.removeprefix("Bearer ")
    return request.query_params.get("token")


async def current_user(request: Request) -> User:
    """Who is asking: the owner (the server's own token, or anybody when it
    has none) or a household member (a token of their phone's own). Bearer
    token, or ``?token=`` for image URLs used by widgets.

    Async on purpose: the viewer set here is seen by the endpoint and by the
    serialisation of its answer (hearts are the viewer's own)."""
    cached: User | None = getattr(request.state, "user", None)
    if cached is not None:
        return cached
    svc: FrameService = request.app.state.service
    found = svc.users.authenticate(_token(request))
    if found is None:
        raise HTTPException(401, "invalid or missing API token")
    user, device = found
    request.state.user = user
    request.state.device = device
    library = svc.library
    VIEWER.set(
        Viewer(
            user.id,
            lambda item_id: library.likes(user.id, item_id),
            lambda item_id: library.hides_work(user.id, item_id),
        )
    )
    return user


#: Every /api route but health and joining.
require_token = current_user
CurrentUser = Annotated[User, Depends(current_user)]


async def require_owner(user: CurrentUser) -> User:
    """Konfiguracja and the server itself: the owner only."""
    if not user.is_owner:
        raise HTTPException(403, "tylko właściciel ramki")
    return user


async def require_frame(user: CurrentUser) -> User:
    """What sends something to the frame or changes how it plays: everyone
    but a guest (Mateusz 2026-11-19: "nie może zmieniać ustawień ramki,
    wysyłać dzieł na ramkę")."""
    if user.is_guest:
        raise HTTPException(403, "gość nie steruje ramką")
    return user


def may_edit_own(user: User, item: Item) -> bool:
    """A work of someone's own is edited and removed by whoever added it,
    and by the owner (Mateusz 2026-11-19)."""
    if user.is_owner:
        return True
    return item.own is not None and item.own.by == user.id
