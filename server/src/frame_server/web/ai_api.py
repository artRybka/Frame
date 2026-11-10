"""The language model's settings and progress (Ramka → trybik → Konfiguracja)."""

from __future__ import annotations

from typing import Annotated, Any

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai import AiConfigUpdate, AiUnavailable, KeyRejected, Progress
from ..ai.audit import FIELDS as AUDIT_FIELDS
from ..ai.composition import PAGES
from ..ai.daily import CHECK_ROUND, ROUND
from ..ai.gatekeeper import SEEN_AS
from ..ai.keywords import KIND as KEYWORDS
from ..ai.pl_text import KIND as PL_TEXT
from ..ai.twins_judge import CLAIMS, Verdict, judge
from ..ai.twins_judge import MODELS as JUDGES
from ..library.models import ItemSummary
from ..service import FrameService
from .deps import require_owner, service

router = APIRouter(prefix="/api/ai", dependencies=[Depends(require_owner)], tags=["ai"])
Svc = Annotated[FrameService, Depends(service)]


class AiView(BaseModel):
    """What the app shows; the key itself is never sent back."""

    key_set: bool
    key_tail: str | None
    key_from_app: bool  # saved in the app, not taken from frame.env / add-on options
    pl_text: bool
    keywords_artworks: bool
    keywords_photos: bool
    daily: bool
    search_words: bool
    curator: bool = True
    twins_judge: bool = True
    gatekeeper: bool = True
    audit: bool = True
    sentence: bool = True
    journey: bool = True
    #: Works on the list "Do sprawdzenia": set aside by the gatekeeper, and
    #: the audit's findings.
    review_count: int = 0
    monthly_limit_usd: float
    spent_usd: float  # this month
    spent_by_kind: dict[str, float]
    keywords_progress: Progress
    pl_text_progress: Progress | None = None
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
        daily=config.daily,
        search_words=config.search_words,
        curator=config.curator,
        twins_judge=config.twins_judge,
        gatekeeper=config.gatekeeper,
        audit=config.audit,
        sentence=config.sentence,
        journey=config.journey,
        review_count=len(svc.gatekeeper.written()) + len(svc.audit.written()),
        monthly_limit_usd=config.monthly_limit_usd,
        spent_usd=round(sum(spent.values()), 4),
        spent_by_kind={k: round(v, 4) for k, v in spent.items()},
        keywords_progress=svc.ai.progress(KEYWORDS),
        pl_text_progress=svc.ai.progress(PL_TEXT),
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


@router.get("/pl-text/estimate", response_model=Estimate)
async def pl_text_estimate(svc: Svc) -> Estimate:
    """What Polish texts for the whole library would cost (Batch API)."""
    items, usd = await run_in_threadpool(svc.ai.estimate, PL_TEXT)
    return Estimate(items=items, usd=round(usd, 2))


@router.post("/pl-text/describe-library", response_model=Started)
async def pl_text_library(svc: Svc) -> Started:
    """Polish texts for the whole library through the Batch API (within 24 hours)."""
    try:
        items = await run_in_threadpool(svc.ai.describe_library, PL_TEXT)
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    return Started(items=items)


class Compose(BaseModel):
    """The works whose pages written before get their composition written
    again (``True``: all), which still wait for it and which have it."""

    rework: bool | list[str]
    waiting: list[str] = []
    #: Asked, but the answer gave no take; let them again to ask once more.
    failed: list[str] = []
    done: list[str] = []


class ComposeUpdate(BaseModel):
    rework: bool | list[str]


def _compose(svc: FrameService) -> Compose:
    job = svc.compose
    job.forget()
    done = {
        item_id
        for kind in PAGES
        for item_id, note in svc.library.notes(kind).items()
        if "teaser" in note.data and note.data.get(CHECK_ROUND, 1) >= ROUND
    }
    return Compose(
        rework=job.rework(),
        waiting=sorted(job.waiting()),
        done=sorted(done),
        failed=sorted(job.failed()),
    )


@router.get("/composition", response_model=Compose)
async def get_compose(svc: Svc) -> Compose:
    return await run_in_threadpool(_compose, svc)


@router.put("/composition", response_model=Compose)
async def put_compose(update: ComposeUpdate, svc: Svc) -> Compose:
    """Lets the analysis of the composition be written again for the pages
    of these works (or all): first a few to look at, then the rest."""
    svc.compose.let(update.rework if update.rework is True else list(update.rework or []))
    svc.ai.wake()
    return await run_in_threadpool(_compose, svc)


class JudgeAsk(BaseModel):
    """Two works of the library and the models to ask about them."""

    a: str
    b: str
    models: list[str] = list(JUDGES)
    effort: str = "low"
    #: Ask as the critic about this claim (one of ``CLAIMS``); verdicts are
    #: then "confirm" or "reject".
    claim: str = ""


class JudgeView(BaseModel):
    verdicts: list[Verdict]


@router.post("/twins-judge", response_model=JudgeView)
async def twins_judge(body: JudgeAsk, svc: Svc) -> JudgeView:
    """How each model sees a pair of pictures (``ai.twins_judge``): the
    test of the judge of copies, one pair at a time, from a script on the
    owner's Mac (Mateusz 2026-11-10). Costs go to this month's spending."""
    a, b = svc.library.get(body.a), svc.library.get(body.b)
    if a is None or b is None:
        raise HTTPException(404, "no such work")
    unknown = [m for m in body.models if m not in JUDGES]
    if unknown or body.effort not in ("low", "medium", "high", "xhigh", "max"):
        raise HTTPException(422, f"unknown model or effort: {unknown or body.effort}")
    if body.claim and body.claim not in CLAIMS:
        raise HTTPException(422, f"unknown claim: {body.claim}")
    try:
        verdicts = await run_in_threadpool(
            judge, svc.claude, svc.images, a, b, body.models, body.effort, body.claim
        )
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    return JudgeView(verdicts=verdicts)


class ReviewProblem(BaseModel):
    #: "title", "artist", "date", "polish" or "picture", and its Polish name.
    field: str
    name: str
    problem: str


class ReviewEntry(BaseModel):
    """One work on "Do sprawdzenia": set aside by the gatekeeper (``seen_as``)
    or found by the audit (``problems``)."""

    item: ItemSummary
    at: str
    #: "gatekeeper" or "audit".
    by: str
    seen_as: str = ""
    #: What the gatekeeper saw it as, in Polish.
    seen_as_name: str = ""
    why: str = ""
    problems: list[ReviewProblem] = []


class Review(BaseModel):
    set_aside: list[ReviewEntry]
    findings: list[ReviewEntry]


def _review(svc: FrameService) -> Review:
    def entries(by: str, written: list[dict[str, Any]]) -> list[ReviewEntry]:
        found = []
        for entry in written:
            item = svc.library.get(str(entry.get("id")))
            if item is None:
                continue
            problems = [
                ReviewProblem(
                    field=str(p.get("field")),
                    name=AUDIT_FIELDS.get(str(p.get("field")), ""),
                    problem=str(p.get("problem") or ""),
                )
                for p in entry.get("problems") or []
                if isinstance(p, dict)
            ]
            seen_as = str(entry.get("seen_as") or "")
            found.append(
                ReviewEntry(
                    item=ItemSummary.of(item),
                    at=str(entry.get("at") or ""),
                    by=by,
                    seen_as=seen_as,
                    seen_as_name=SEEN_AS.get(seen_as, ""),
                    why=str(entry.get("why") or ""),
                    problems=problems,
                )
            )
        return found

    return Review(
        set_aside=entries("gatekeeper", svc.gatekeeper.written()),
        findings=entries("audit", svc.audit.written()),
    )


@router.get("/review", response_model=Review)
async def get_review(svc: Svc) -> Review:
    """ "Do sprawdzenia": what the gatekeeper set aside and what the night
    audit found, newest first."""
    return await run_in_threadpool(_review, svc)


@router.post("/review/{item_id:item}/bring-back", response_model=Review)
async def bring_back(item_id: str, svc: Svc) -> Review:
    """A work the gatekeeper set aside back in the catalogue, for good."""
    if not await run_in_threadpool(svc.gatekeeper.bring_back, item_id):
        raise HTTPException(404, "no such work")
    return await run_in_threadpool(_review, svc)


@router.delete("/review/{item_id:item}", response_model=Review)
async def dismiss(item_id: str, svc: Svc) -> Review:
    """Off the list: the gatekeeper's call stands, the audit's finding is seen."""
    svc.gatekeeper.forget_written(item_id)
    svc.audit.forget_written(item_id)
    return await run_in_threadpool(_review, svc)
