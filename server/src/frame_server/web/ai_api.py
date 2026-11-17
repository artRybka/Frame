"""The language model's settings and progress (Ramka → trybik → Konfiguracja)."""

from __future__ import annotations

from typing import Annotated, Any

import anthropic
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai import AiConfigUpdate, AiUnavailable, KeyRejected, Progress, costs
from ..ai.audit import FIELDS as AUDIT_FIELDS
from ..ai.composition import PAGES
from ..ai.config import TaskUpdate
from ..ai.daily import CHECK_ROUND, ROUND
from ..ai.drawn import TYPICAL_USD as SHEET_USD
from ..ai.gatekeeper import SEEN_AS
from ..ai.gemini import GeminiRejected
from ..ai.keywords import KIND as KEYWORDS
from ..ai.pl_text import KIND as PL_TEXT
from ..ai.review_fix import ReviewError
from ..ai.twins_judge import CLAIMS, Verdict, judge
from ..ai.twins_judge import MODELS as JUDGES
from ..leftover import NIGHT_USD_CHOICES, PERIOD_USD_CHOICES, set_task
from ..library.models import ItemSummary
from ..on_demand import USES as ON_DEMAND
from ..on_demand import OnDemandError
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
    journey: bool = True
    #: Facts from the web woven into new studies ("G8").
    web_facts: bool = True
    #: The study's "Jak powstawał", told from a technical study ("G2").
    stages: bool = True
    #: Museum photographs cut down to the work ("Kadrowanie zdjęć dzieł").
    crops: bool = True
    #: Haiku asked whether a green under yellowed varnish is a blue
    #: ("Błękit pod werniksem").
    varnish_blue: bool = True
    #: Works on the list "Do sprawdzenia": set aside by the gatekeeper, and
    #: the audit's findings.
    review_count: int = 0
    monthly_limit_usd: float
    spent_usd: float  # this month
    spent_by_kind: dict[str, float]
    keywords_progress: Progress
    pl_text_progress: Progress | None = None
    error: str | None  # why the model is paused, if it is
    #: Google's key for the image model that draws the study sheets
    #: (``ai.drawn``): whether there is one, its last letters.
    gemini_key_set: bool = False
    gemini_key_tail: str | None = None
    #: The owner's switch "Arkusze rysowane przez model graficzny".
    drawn: bool = True
    #: About what one drawn sheet costs.
    drawn_usd: float = SHEET_USD
    #: Why no sheet is drawn now: "no_credit" (the key's prepaid credit is
    #: used up), "key_rejected", "limit" (the image model's month's).
    gemini_error: str | None = None
    #: The image model's own month: its limit, what its answers cost so
    #: far, by what asked for them ("sheet", "restorer").
    gemini_monthly_limit_usd: float = 5.0
    gemini_spent_usd: float = 0.0
    gemini_spent_by_kind: dict[str, float] = {}
    #: The sheets of the pages saved before go through Google's Batch (half
    #: the price, within a day): how many still wait for it, how many are
    #: in it now, and about what one costs there.
    drawn_waiting: int = 0
    drawn_in_batch: int = 0
    drawn_batch_usd: float = SHEET_USD / 2
    #: Szukanie wyglądem ("G1"): the switch, the museums' works with their
    #: numbers so far and all that would have them, and why none are made
    #: now (Google's trouble, the limit).
    looks: bool = True
    looks_done: int = 0
    looks_total: int = 0
    looks_error: str | None = None
    study_refresh: StudyRefreshView | None = None
    text_review: TextReviewView | None = None
    #: The day of the month Claude's period begins on, and the period now
    #: (ISO dates, its first and last day).
    period_day: int = 1
    period_start: str | None = None
    period_end: str | None = None
    #: "Resztka miesiąca na studia": the switch, its days and reserve, and
    #: how it is getting on (:class:`LeftoverView`).
    leftover: bool = False
    leftover_days: int = 3
    leftover_reserve_usd: float = 10.0
    leftover_state: LeftoverView | None = None
    #: What each thing cost over the last ``cost_days`` days and the period
    #: so far, Claude's and Google's apart (``ai.costs``).
    cost_days: int = costs.DAYS
    claude_costs: list[CostView] = []
    gemini_costs: list[CostView] = []


class CostView(BaseModel):
    """One row of "Koszty" (``ai.costs``)."""

    #: The switch's key where it has one, else the row's own.
    key: str
    label: str
    days_usd: float
    period_usd: float


class LeftoverView(BaseModel):
    """What the month's rest does (``frame_server.leftover``)."""

    #: When studies may be ordered this period (ISO dates), and whether now.
    opens: str
    closes: str
    open: bool
    #: What the limit leaves above the reserve, less the studies on their way.
    free_usd: float
    #: What a study is reckoned to cost; measured here or not yet.
    per_study_usd: float
    measured: bool
    #: This period: studies ordered, on their way, made, failed.
    ordered: int
    in_flight: int
    made: int
    failed: int
    #: Works the curator found fit and did not choose, waiting.
    candidates: int
    #: What the rest goes on, in the owner's order (Mateusz 2026-11-15).
    uses: list[LeftoverUseView] = []
    #: What a run on demand may be given now.
    now_free_usd: float = 0.0
    #: Ordered and held by the runs going, not spent yet (USD).
    planned_usd: float = 0.0
    #: What a task's amounts a night and a period may be set to (USD).
    night_usd_choices: list[float] = list(NIGHT_USD_CHOICES)
    period_usd_choices: list[float] = list(PERIOD_USD_CHOICES)


class LeftoverUseView(BaseModel):
    """One thing the month's rest may go on (``leftover.USES``)."""

    key: str
    label: str
    about: str
    #: The owner's switch for it here, and whether its own switch (and what
    #: it needs) lets it run.
    on: bool
    able: bool
    #: How many wait for it (None: more than tell), about what one costs and
    #: what all of them would; how many it may take a night.
    waiting: int | None
    each_usd: float
    waiting_usd: float | None
    a_night: int | None
    #: What the owner may set ``a_night`` to (None: fixed), and what a night
    #: takes of what waits and about for how much (Mateusz 2026-11-15: the
    #: whole catalogue's "824,84 USD" is no night's).
    a_night_options: list[int] | None = None
    tonight: int | None = None
    tonight_usd: float | None = None
    #: What it ordered this period, and about what it cost.
    done: int
    done_usd: float
    #: Run now for an amount, at the full price (Mateusz 2026-11-17, "na
    #: żądanie, w trybie zwykłym"): about what a work costs so (None: it
    #: cannot be run now), and the run going or the last one.
    now_each_usd: float | None = None
    run: OnDemandRunView | None = None
    #: The owner's settings of it as a task (Mateusz 2026-11-17, "Zadania"):
    #: when it runs ("rest", "night", "demand", "off"), the works a night he
    #: may choose (``a_night`` is the one chosen), what a night and the
    #: period may spend on it (None: no amount of its own), how it asks
    #: ("batch", "normal") and how it may, and what it cost this period.
    when: str = "rest"
    a_night_choices: list[int] | None = None
    night_usd: float | None = None
    period_usd: float | None = None
    mode: str = "batch"
    modes: list[str] = ["batch"]
    period_spent_usd: float = 0.0


class OnDemandRunView(BaseModel):
    """A run on demand (``frame_server.on_demand``)."""

    label: str
    #: The amount given, what it cost so far.
    usd: float
    spent_usd: float
    #: Works done, of them changed (described, cut), failed.
    done: int
    changed: int = 0
    failed: int = 0
    #: Works waiting when it began, and still to go (while it runs).
    waiting: int | None = None
    left: int | None = None
    running: bool
    stopping: bool = False
    #: When it began and ended (ISO), and why it ended, in Polish.
    started: str | None = None
    ended: str | None = None
    why: str | None = None
    #: The night started it (the task's mode "Zwykły").
    night: bool = False


class OnDemandStart(BaseModel):
    key: str
    usd: float


class StudyRefreshView(BaseModel):
    """The studies written before the facts from the web, filled in at the
    owner's tap (``ai.refresh``)."""

    #: Studies with no facts from the web yet, and those whose facts add
    #: much and wait for their text to be rewritten.
    waiting: int = 0
    rewrite_waiting: int = 0
    #: An order is under way: the studies asked about, being rewritten.
    running: bool = False
    asked: int = 0
    rewriting: int = 0
    #: So far: studies that got facts, rewritten, what it cost.
    found: int = 0
    rewritten: int = 0
    spent_usd: float = 0.0
    #: About what the facts of those waiting cost, and their rewrites.
    facts_usd: float = 0.0
    rewrite_usd: float = 0.0


class TextReviewView(BaseModel):
    """The Polish texts kept, looked over at the owner's tap
    (``ai.text_review``)."""

    #: Translations kept; of them not yet checked by Haiku, and found not to
    #: be about the work with their note still to come; notes written
    #: before the five styles.
    translations: int = 0
    unchecked: int = 0
    general: int = 0
    unstyled: int = 0
    #: An order is under way: the checks and the notes in it.
    running: bool = False
    checking: int = 0
    writing: int = 0
    #: So far: translations checked, found not about the work, notes
    #: written, what it cost.
    checked: int = 0
    found: int = 0
    written: int = 0
    spent_usd: float = 0.0
    #: About what each step costs now, and one note.
    check_usd: float = 0.0
    note_usd: float = 0.0
    general_usd: float = 0.0
    restyle_usd: float = 0.0


class TextReviewStart(BaseModel):
    #: "Sprawdź tłumaczenia" and "Przepisz notki w nowych stylach".
    check: bool = True
    restyle: bool = False


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
    painted = svc.painter.spending.by_kind()
    waiting, in_batch = svc.drawn.counts()
    looks_done, looks_total = svc.looks.counts()
    leftover = svc.leftover.view()
    for use in leftover["uses"]:
        if use["key"] in ON_DEMAND:
            use["now_each_usd"] = svc.on_demand.each_usd(use["key"])
            use["run"] = svc.on_demand.view(use["key"])
    leftover["now_free_usd"] = round(svc.on_demand.free_usd(), 2)
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
        journey=config.journey,
        web_facts=config.web_facts,
        stages=config.stages,
        crops=config.crops,
        varnish_blue=config.varnish_blue,
        review_count=_review_count(svc),
        monthly_limit_usd=config.monthly_limit_usd,
        spent_usd=round(sum(spent.values()), 4),
        spent_by_kind={k: round(v, 4) for k, v in spent.items()},
        keywords_progress=svc.ai.progress(KEYWORDS),
        pl_text_progress=svc.ai.progress(PL_TEXT),
        error=svc.ai.error,
        gemini_key_set=bool(store.gemini_key),
        gemini_key_tail=store.gemini_tail,
        drawn=config.drawn,
        gemini_error=svc.drawn.error if store.drawn else None,
        drawn_waiting=waiting,
        drawn_in_batch=in_batch,
        gemini_monthly_limit_usd=config.gemini_monthly_limit_usd,
        gemini_spent_usd=round(sum(painted.values()), 4),
        gemini_spent_by_kind={k: round(v, 4) for k, v in painted.items()},
        looks=config.looks,
        looks_done=looks_done,
        looks_total=looks_total,
        looks_error=svc.looks.trouble if config.looks else None,
        study_refresh=StudyRefreshView(**svc.study_refresh.view()),
        text_review=TextReviewView(**svc.text_review.view()),
        period_day=config.period_day,
        period_start=leftover.pop("period_start"),
        period_end=leftover.pop("period_end"),
        leftover=config.leftover,
        leftover_days=config.leftover_days,
        leftover_reserve_usd=config.leftover_reserve_usd,
        leftover_state=LeftoverView(**leftover),
        claude_costs=[CostView(**row) for row in costs.rows(svc.claude.spending, costs.CLAUDE)],
        gemini_costs=[CostView(**row) for row in costs.rows(svc.painter.spending, costs.GEMINI)],
    )


@router.get("", response_model=AiView)
async def get_ai(svc: Svc) -> AiView:
    return await run_in_threadpool(_view, svc)


@router.put("", response_model=AiView)
async def put_ai(update: AiConfigUpdate, svc: Svc) -> AiView:
    svc.ai_config.update(update)
    svc.ai.wake()
    svc.drawn.again()  # the limit raised, the sheets switched on
    svc.looks.nudge()
    return await run_in_threadpool(_view, svc)


@router.post("/study-refresh", response_model=AiView)
async def start_study_refresh(svc: Svc) -> AiView:
    """The studies written before the facts from the web asked about now,
    through the Batch API (the owner's tap in Konfiguracja)."""
    if not svc.ai_config.api_key:
        raise HTTPException(409, "Brak klucza API Anthropic.")
    try:
        svc.claude.check_budget()
    except AiUnavailable as err:
        raise HTTPException(409, "Osiągnięty miesięczny limit Claude.") from err
    asked = await run_in_threadpool(svc.study_refresh.start)
    if not asked and not svc.study_refresh.view()["running"]:
        raise HTTPException(409, "Nie udało się zamówić (szczegóły w dzienniku serwera).")
    return await run_in_threadpool(_view, svc)


@router.post("/on-demand", response_model=AiView)
async def start_on_demand(start: OnDemandStart, svc: Svc) -> AiView:
    """One of the month's rest's uses run now, for the owner's amount, at
    the full price (Konfiguracja → Claude → "Uruchom teraz")."""
    try:
        await run_in_threadpool(svc.on_demand.start, start.key, start.usd)
    except OnDemandError as err:
        raise HTTPException(409, str(err)) from err
    return await run_in_threadpool(_view, svc)


@router.put("/tasks/{key}", response_model=AiView)
async def put_task(key: str, update: TaskUpdate, svc: Svc) -> AiView:
    """One task's when, number a night, amounts and mode (Konfiguracja →
    Zadania)."""
    try:
        set_task(svc.ai_config, key, update)
    except ValueError as err:
        raise HTTPException(409, str(err)) from err
    return await run_in_threadpool(_view, svc)


@router.post("/on-demand/{key}/stop", response_model=AiView)
async def stop_on_demand(key: str, svc: Svc) -> AiView:
    """The run stops after the works it is asking about."""
    if not svc.on_demand.stop(key):
        raise HTTPException(404, "To zadanie teraz nie działa.")
    return await run_in_threadpool(_view, svc)


@router.post("/text-review", response_model=AiView)
async def start_text_review(start: TextReviewStart, svc: Svc) -> AiView:
    """The Polish texts kept looked over through the Batch API (the owner's
    tap in Konfiguracja): the translations checked, notes written anew."""
    if not svc.ai_config.api_key:
        raise HTTPException(409, "Brak klucza API Anthropic.")
    try:
        svc.claude.check_budget()
    except AiUnavailable as err:
        raise HTTPException(409, "Osiągnięty miesięczny limit Claude.") from err
    asked = await run_in_threadpool(svc.text_review.start, start.check, start.restyle)
    if not asked and not svc.text_review.view()["running"]:
        raise HTTPException(409, "Nie ma czego przejrzeć.")
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


@router.put("/gemini-key", response_model=AiView)
async def put_gemini_key(update: KeyUpdate, svc: Svc) -> AiView:
    """Check Google's key (free), then keep it: the study sheets are drawn
    by its image model from now on."""
    key = update.key.strip()
    if not key:
        raise HTTPException(400, "empty API key")
    try:
        await run_in_threadpool(svc.painter.check_key, key)
    except GeminiRejected as err:
        raise HTTPException(400, str(err)) from err
    except httpx.HTTPError as err:
        raise HTTPException(502, f"Google did not answer: {err}") from err
    try:
        svc.ai_config.set_gemini_key(key)
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    svc.drawn.again()
    svc.looks.nudge()
    return await run_in_threadpool(_view, svc)


@router.delete("/gemini-key", response_model=AiView)
async def delete_gemini_key(svc: Svc) -> AiView:
    """Forget Google's key: the sheets are made by the server again."""
    svc.ai_config.set_gemini_key(None)
    svc.drawn.again()
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
    #: For a title, a maker or a date: the corrected value ("Popraw"), ""
    #: until the audit or ``/suggest`` gave one.
    fix: str = ""
    #: For a title: the corrected Polish title.
    fix_pl: str = ""


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
                    fix=str(p.get("fix") or ""),
                    fix_pl=str(p.get("fix_pl") or ""),
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
                    # In Polish once written so (``ai.review_fix``).
                    why=str(entry.get("why_pl") or entry.get("why") or ""),
                    problems=problems,
                )
            )
        return found

    return Review(
        set_aside=entries("gatekeeper", svc.gatekeeper.written()),
        findings=entries("audit", svc.audit.written()),
    )


def _review_count(svc: FrameService) -> int:
    """What "Do sprawdzenia" lists: an entry whose work is no longer in the
    library (merged into another copy, removed) is not shown there, so it is
    not counted either (Mateusz 2026-11-17: 21 by the row, 5 inside)."""
    written = [*svc.gatekeeper.written(), *svc.audit.written()]
    return sum(1 for e in written if svc.library.has(str(e.get("id"))))


@router.get("/review", response_model=Review)
async def get_review(svc: Svc) -> Review:
    """ "Do sprawdzenia": what the gatekeeper set aside and what the night
    audit found, newest first. The gatekeeper's English notes written before
    it wrote them in Polish are translated meanwhile, for the next look."""
    svc.review_fixes.translate_soon()
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


class ReviewFix(BaseModel):
    #: "title", "artist" or "date".
    field: str
    value: str
    #: For a title: the Polish title the app shows.
    value_pl: str | None = None


def _review_call(svc: FrameService, call: Any, *args: Any) -> Review:
    """One of "Do sprawdzenia"'s remedies, then the list as it is now."""
    try:
        call(*args)
    except LookupError as err:
        raise HTTPException(404, "no such work on the list") from err
    except ReviewError as err:
        raise HTTPException(422, str(err)) from err
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"Zdjęcie dzieła niedostępne: {err}") from err
    return _review(svc)


@router.post("/review/{item_id:item}/suggest", response_model=Review)
async def suggest_fixes(item_id: str, svc: Svc) -> Review:
    """The corrected title, maker or date of a finding written before the
    audit gave them, asked of Haiku now (a fraction of a cent)."""
    return await run_in_threadpool(_review_call, svc, svc.review_fixes.suggest, item_id)


@router.post("/review/{item_id:item}/fix", response_model=Review)
async def apply_fix(item_id: str, fix: ReviewFix, svc: Svc) -> Review:
    """ "Popraw": the owner's value on the work; that problem off the list."""
    return await run_in_threadpool(
        _review_call, svc, svc.review_fixes.apply, item_id, fix.field, fix.value, fix.value_pl
    )


class PolishDraft(BaseModel):
    #: The text on the frame (whole sentences that fit) and the card's.
    frame: str
    full: str


@router.post("/review/{item_id:item}/polish", response_model=PolishDraft)
async def propose_polish(item_id: str, svc: Svc) -> PolishDraft:
    """ "Popraw opis": the Polish texts mended where the audit's remark
    says (Sonnet, about a cent), not kept until ``PUT``."""
    drafts: list[dict[str, str]] = []
    await run_in_threadpool(
        _review_call, svc, lambda: drafts.append(svc.review_fixes.propose_polish(item_id))
    )
    return PolishDraft(**drafts[0])


@router.put("/review/{item_id:item}/polish", response_model=Review)
async def save_polish(item_id: str, draft: PolishDraft, svc: Svc) -> Review:
    """The owner's Polish texts kept; that problem off the list."""
    return await run_in_threadpool(
        _review_call, svc, svc.review_fixes.save_polish, item_id, draft.frame, draft.full
    )


@router.post("/review/{item_id:item}/cut", response_model=Review)
async def cut_finding(item_id: str, svc: Svc) -> Review:
    """ "Przytnij": Opus finds the work in its photograph now (about 2
    cents), told what the audit saw; the cut is the owner's."""
    return await run_in_threadpool(_review_call, svc, svc.review_fixes.cut, item_id)


@router.delete("/review/{item_id:item}/problems/{field}", response_model=Review)
async def drop_problem(item_id: str, field: str, svc: Svc) -> Review:
    """One problem done elsewhere (a better copy picked): off the list."""
    return await run_in_threadpool(_review_call, svc, svc.review_fixes.drop, item_id, field)


@router.post("/review/{item_id:item}/hide", response_model=Review)
async def hide_finding(item_id: str, svc: Svc) -> Review:
    """ "Ukryj": the work out of the catalogue, and off the list."""
    review = await run_in_threadpool(_review_call, svc, svc.review_fixes.hide, item_id)
    svc.player.item_changed(item_id)
    return review
