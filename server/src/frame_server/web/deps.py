"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..service import FrameService


def service(request: Request) -> FrameService:
    svc: FrameService = request.app.state.service
    return svc


def require_token(request: Request) -> None:
    """Bearer token, or ``?token=`` for image URLs used by widgets."""
    token = request.app.state.service.settings.api_token
    if not token:
        return
    header = request.headers.get("authorization")
    if header == f"Bearer {token}" or request.query_params.get("token") == token:
        return
    raise HTTPException(401, "invalid or missing API token")
