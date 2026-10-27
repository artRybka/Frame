"""The language model's settings and progress (Ramka → trybik → Konfiguracja)."""

from __future__ import annotations

from typing import Annotated

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai import AiConfigUpdate, AiUnavailable, KeyRejected, Progress
from ..ai.keywords import KIND as KEYWORDS
from ..service import FrameService
from .deps import require_token, service

router = APIRouter(prefix="/api/ai", dependencies=[Depends(require_token)], tags=["ai"])
Svc = Annotated[FrameService, Depends(service)]


class AiView(BaseModel):
    """What the app shows; the key itself is never sent back."""

    key_set: bool
    key_tail: str | None
    key_from_app: bool  # saved in the app, not taken from frame.env / add-on options
    pl_text: bool
    keywords_artworks: bool
    keywords_photos: bool
    monthly_limit_usd: float
    spent_usd: float  # this month
    spent_by_kind: dict[str, float]
    keywords_progress: Progress
    pl_text_progress: Progress | None = None  # filled once the Polish texts job is there
    error: str | None  # why the model is paused, if it is


class KeyUpdate(BaseModel):
    key: str


class Estimate(BaseModel):
    items: int
    usd: float


class Started(BaseModel):
    items: int


def _view(svc: FrameService) -> AiView:
    store, config = svc.ai_config, svc.ai_config.config
    spent = svc.claude.spending.by_kind()
    return AiView(
        key_set=bool(store.api_key),
        key_tail=store.key_tail,
        key_from_app=store.key_from_app,
        pl_text=config.pl_text,
        keywords_artworks=config.keywords_artworks,
        keywords_photos=config.keywords_photos,
        monthly_limit_usd=config.monthly_limit_usd,
        spent_usd=round(sum(spent.values()), 4),
        spent_by_kind={k: round(v, 4) for k, v in spent.items()},
        keywords_progress=svc.ai.progress(KEYWORDS),
        error=svc.ai.error,
    )


@router.get("", response_model=AiView)
async def get_ai(svc: Svc) -> AiView:
    return await run_in_threadpool(_view, svc)


@router.put("", response_model=AiView)
async def put_ai(update: AiConfigUpdate, svc: Svc) -> AiView:
    svc.ai_config.update(update)
    svc.ai.wake()
    return await run_in_threadpool(_view, svc)


@router.put("/key", response_model=AiView)
async def put_key(update: KeyUpdate, svc: Svc) -> AiView:
    """Check the key with Anthropic (free), then keep it."""
    key = update.key.strip()
    if not key:
        raise HTTPException(400, "empty API key")
    try:
        await run_in_threadpool(svc.claude.check_key, key)
    except KeyRejected as err:
        raise HTTPException(400, str(err)) from err
    except anthropic.APIError as err:
        raise HTTPException(502, f"Anthropic did not answer: {err}") from err
    try:
        svc.ai_config.set_key(key)
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    svc.ai.wake()
    return await run_in_threadpool(_view, svc)


@router.delete("/key", response_model=AiView)
async def delete_key(svc: Svc) -> AiView:
    """Forget the app's key (frame.env's applies again, if it has one)."""
    svc.ai_config.set_key(None)
    svc.ai.wake()
    return await run_in_threadpool(_view, svc)


@router.get("/keywords/estimate", response_model=Estimate)
async def keywords_estimate(svc: Svc) -> Estimate:
    """What "Opisz bibliotekę" would ask about, and about what it costs."""
    items, usd = await run_in_threadpool(svc.ai.estimate, KEYWORDS)
    return Estimate(items=items, usd=round(usd, 2))


@router.post("/keywords/describe-library", response_model=Started)
async def describe_library(svc: Svc) -> Started:
    """Keywords for the whole library through the Batch API (within 24 hours)."""
    try:
        items = await run_in_threadpool(svc.ai.describe_library, KEYWORDS)
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    return Started(items=items)
