"""Discover's study of the day: the tile at the top of Odkrywaj and its page,
which is also every study's page (``web.study_api``)."""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Callable
from datetime import date
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai.composition import SHOWN, versions
from ..ai.daily import (
    TEASER_CHARS,
    Composition,
    DailyJob,
    Detail,
    Essay,
    Legacy,
    Milestone,
    Pigment,
    Spot,
    View,
    short,
    vary_hedges,
)
from ..ai.journey import Journey
from ..ai.pl_text import description
from ..imaging.sheet import BLEED
from ..later import entry_key
from ..library import Item
from ..library.markup import strip_markup
from ..service import FrameService
from ..sheets import LAYERS
from ..sizes import RealSize
from .deps import require_owner, require_token, service
from .library_api import RemoteItem, remote_items

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["discover"])
Svc = Annotated[FrameService, Depends(service)]

#: The text's title when only the museum speaks.
MUSEUM_HEADLINE = "Co mówi muzeum"
#: "Podobne dzieła" at least (when the catalogue has them): two rows of
#: two in the app, and never a row with one.
MIN_SIMILAR = 4


class SimilarWork(BaseModel):
    item: RemoteItem
    why: str = ""


class LegacyWork(Legacy):
    #: A copy of the later work: the catalogue's, else a museum's.
    item: RemoteItem | None = None


class DailyDetail(Detail):
    #: The fragment cut from the original (``GET /api/daily/detail``).
    image: str


class CompositionVersion(BaseModel):
    """One of the analyses of the composition a page has had, for the
    owner's pick (held header "Analiza kompozycji")."""

    #: When it was made (ISO time).
    made: str = ""
    #: The one the page shows.
    shown: bool = False


class DrawnNumber(BaseModel):
    """Where a mark's number stands on its line (fractions of the field)."""

    x: float
    y: float


class DrawnMark(BaseModel):
    """One mark of the take as the image model drew it."""

    #: Which of the take's marks it is (its place among ``marks``).
    mark: int
    #: Its line alone, the field's size (``&part=m…``): a PNG that is
    #: nothing but as much black as there is pencil; "" when the model
    #: left the mark out (the app draws it itself).
    layer: str = ""
    #: The pencil it is drawn with ("#rrggbb"): the line's colour, its
    #: number's and its note's.
    colour: str
    #: Where its number stands: once, at each ring of an echo, at the
    #: first and the last beat of a rhythm.
    numbers: list[DrawnNumber] = []


class Drawn(BaseModel):
    """The take's study sheet as drawn by the image model (``ai.drawn``):
    one picture for the light page (the app shows it as a light card on
    its dark one), and the marks' lines to lay over it."""

    #: The study with the page's margin on each side of the field
    #: (``&part=page``), where a wash and a line run out to the screen's edge.
    sheet: str
    #: How much of the field's width the margin is, each side.
    bleed: float
    #: The field's width over its height.
    aspect: float
    marks: list[DrawnMark] = []


class DailyBrief(BaseModel):
    day: str
    item: RemoteItem
    title: str


class DailyWork(BaseModel):
    day: str
    item: RemoteItem
    #: The Polish title when there is one.
    title: str
    #: When the work was made: in Polish once its texts are, else the
    #: museum's words (the line under the title's slip).
    date: str = ""
    teaser: str = ""
    #: Where the tile's band is cropped around (fractions of the picture).
    focus: Spot | None = None
    why_today: str = ""
    #: The model is writing the page now.
    writing: bool = False
    #: The later works (or the artist's other works) are being looked up
    #: in the museums now.
    legacy_pending: bool = False
    #: The model wrote the page (else only what the museum says).
    written: bool = False
    #: The title of the text below.
    headline: str = ""
    context: list[str] = []
    #: A short note about the artist.
    artist: str = ""
    #: Left empty: read by 0.42 apps.
    facts: list[dict[str, str]] = []
    composition: Composition | None = None
    #: The study sheet the analysis is drawn on (``GET
    #: /api/composition/sheet``; the app adds ``&dark=1`` for its dark
    #: page): the picture as stains and a few strokes of a pen.
    composition_sheet: str = ""
    #: The sheet may be asked for as its two layers too (``&layer=wash``,
    #: ``&layer=pen``), which the app lays down one after the other, as if
    #: painted and drawn before the reader.
    composition_layers: bool = False
    #: The layers may be asked for with the page's margin beside the field
    #: too (``&layer=wash-bleed``, ``&layer=pen-bleed``): wider than the
    #: field by this much of its width on each side, where a stain runs out
    #: to the screen's edge and a stroke goes on past the frame. None: the
    #: page has no sheet.
    composition_bleed: float | None = None
    #: Every analysis the page has had, oldest first, once the owner asked
    #: for one anew (else empty).
    composition_versions: list[CompositionVersion] = []
    #: The sheet as the image model drew it; None while the take has
    #: none (the sheet above is shown).
    composition_drawn: Drawn | None = None
    #: The take's drawn sheet is being made now (a new page's, one the
    #: owner had made anew; a minute or two): the app asks for the page
    #: again until it has ``composition_drawn``.
    composition_drawn_pending: bool = False
    #: The owner asked for the analysis anew and it is being made.
    composition_pending: bool = False
    #: The owner asked for the details to be checked ("Popraw detale"): on its way.
    details_pending: bool = False
    colour: str = ""
    details: list[DailyDetail] = []
    on_frame: str = ""
    similar: list[SimilarWork] = []
    legacy: list[LegacyWork] = []
    #: Other works by the artist ("Inne prace artysty").
    by_artist: list[RemoteItem] = []
    #: Works made a few years either side, elsewhere ("W tym samym czasie").
    same_time: list[RemoteItem] = []
    #: The artist's years (the museum's line about them first, else the
    #: page's), moments of their life and the work's paints.
    born: int | None = None
    died: int | None = None
    milestones: list[Milestone] = []
    #: Historical events in the artist's lifetime, on their line of life.
    events: list[Milestone] = []
    pigments: list[Pigment] = []
    #: How big the work really is, in centimetres ("Prawdziwy rozmiar").
    size: RealSize | None = None
    #: How it went from its maker to where it is now ("Droga dzieła").
    journey: Journey | None = None
    sources: list[str] = []
    model: str = ""
    #: Left empty: the days before are no longer listed under the page.
    previous: list[DailyBrief] = []
    #: Without the lists under the text (similar, later and other works by
    #: the artist), which take a while: asked for the text first, the page
    #: opens with it and asks again for the rest.
    partial: bool = False


LIFE = re.compile(r"(?<!\d)(\d{3,4})\s*[-–—]\s*(\d{3,4})(?!\d)")


def life(text: str) -> tuple[int, int] | None:
    """The years of the artist's life in the museum's line about them
    ("Dutch, Delft 1632–1675 Delft") or in brackets in the name."""
    match = LIFE.search(text)
    if not match:
        return None
    born, died = int(match.group(1)), int(match.group(2))
    return (born, died) if 10 < died - born < 110 else None


def _light(svc: FrameService, item: Item, *, bio: bool = False) -> RemoteItem:
    """The work without its long texts; with ``bio`` the artist's line from
    the museum stays ("Dutch, Delft 1632–1675 Delft": the app shows the
    years under the name in "O autorze")."""
    remote = remote_items(svc, [item], copies=False, keep_hidden=True)[0]
    light = {"description": ""} if bio else {"description": "", "artist_bio": ""}
    return remote.model_copy(update={"item": remote.item.model_copy(update=light)})


def _title(svc: FrameService, item: Item, essay: Essay | None) -> str:
    if essay and essay.title:
        return essay.title
    polish = svc.pl_text.text(item)
    return polish.title if polish else strip_markup(item.title)


def _date(svc: FrameService, item: Item) -> str:
    """When the work was made, in Polish once its texts are ("ok. 1830–1832")."""
    polish = svc.pl_text.text(item)
    return polish.date if polish and polish.date else item.date_text


def _museum_text(svc: FrameService, item: Item) -> str:
    """What the museum says (in Polish once translated); "" when nothing."""
    polish = svc.pl_text.text(item)
    return polish.full if polish else description(item)


def _later(svc: FrameService, entry: Legacy, item: Item) -> RemoteItem | None:
    """The catalogue's copy of a later work, by its author and title."""
    copy = svc.later.in_catalogue(item, entry)
    return _light(svc, copy) if copy is not None else None


def _legacy(svc: FrameService, item: Item, essay: Essay) -> list[LegacyWork]:
    """What the work led to, each with a copy of it when there is one: the
    catalogue's, else the museum's found for it."""
    known = svc.later.known(item.id)
    works = []
    for entry in essay.legacy:
        found = known.get(entry_key(entry))
        copy = _later(svc, entry, item)
        if copy is None and found is not None and found.item is not None:
            copy = _light(svc, found.item)
        works.append(LegacyWork(**entry.model_dump(), item=copy))
    return works


def _work(svc: FrameService, day: date, item: Item, writing: bool, lists: bool = True) -> DailyWork:
    def detail_url(n: int, box: Detail) -> str:
        v = svc.daily.detail_path(item, box).stem.rsplit("-", 1)[-1]
        return f"/api/daily/detail?day={day.isoformat()}&n={n}&v={v}"

    return page(
        svc, item, svc.daily.job, day=day.isoformat(), writing=writing, url=detail_url, lists=lists
    )


def sheet_url(svc: FrameService, item: Item, view: View) -> str:
    """Where the app gets the sheet a take is drawn on: another address
    when the take's field or pen sketch changes, so it may be kept long."""
    return f"/api/composition/sheet?item={quote(item.id, safe='')}&v={svc.sheets.key(view)}"


def drawn(svc: FrameService, item: Item, view: View) -> tuple[Drawn | None, bool]:
    """The take's drawn sheet as the app gets it, or whether it is being
    made now (:class:`DailyWork`). One drawn before the sheets' new look
    is shown until the new one is there."""
    found = svc.drawn.kept(item, view)
    if found is None:
        return None, svc.drawn.pending(item, view)
    key, kept = found
    at = f"item={quote(item.id, safe='')}&v={key}"
    width, height = kept["size"]
    marks = [
        DrawnMark(
            mark=mark,
            layer=f"/api/composition/drawn?{at}&part=m{n}" if there else "",
            colour=colour,
            numbers=[DrawnNumber(x=x, y=y) for x, y in numbers],
        )
        for n, (mark, there, colour, numbers) in enumerate(
            zip(kept["marks"], kept["layers"], kept["colours"], kept["numbers"], strict=False),
            start=1,
        )
    ]
    sheet = Drawn(
        sheet=f"/api/composition/drawn?{at}&part=page",
        bleed=BLEED,
        aspect=width / height,
        marks=marks,
    )
    return sheet, False


def page(
    svc: FrameService,
    item: Item,
    job: DailyJob,
    *,
    day: str,
    writing: bool,
    url: Callable[[int, Detail], str],
    lists: bool = True,
) -> DailyWork:
    """The work's page as ``job`` wrote it (the work of the day, or a study
    of it), the museum's text while there is none; ``url``: where the app
    gets each fragment. Without ``lists``: the text alone, at once (each
    list looks through the whole catalogue, seconds on a NAS)."""
    essay = job.essay(item)
    museum = _museum_text(svc, item)
    candidates = svc.daily.candidates(item) if lists else []
    similar: list[SimilarWork]
    legacy: list[LegacyWork]
    if not lists:
        similar, legacy = [], []
    elif essay is not None:
        by_id = {c.id: c for c in candidates}
        chosen = [by_id[s.id] for s in essay.similar if s.id in by_id]
        why = {s.id: s.why for s in essay.similar}
        # Pages written before the artist's own works left the list have
        # fewer once they go: the other candidates fill it up, to full rows.
        wanted = max(MIN_SIMILAR, len(chosen) + len(chosen) % 2)
        chosen += [c for c in candidates if c not in chosen][: wanted - len(chosen)]
        similar = [SimilarWork(item=_light(svc, c), why=why.get(c.id, "")) for c in chosen]
        legacy = _legacy(svc, item, essay)
    else:
        similar = [SimilarWork(item=_light(svc, c), why="") for c in candidates[:MIN_SIMILAR]]
        legacy = []
    details = [
        DailyDetail(**box.model_dump(), image=url(n, box))
        for n, box in enumerate(essay.details if essay else [])
    ]
    shown = {s.item.item.id for s in similar}
    by_artist = svc.artists.works(item, shown) if lists else []
    looking = lists and svc.artists.look_soon(item, len(by_artist))
    shown |= {w.id for w in by_artist}
    # Kept with the text too (a note's read), so the drawing does not go
    # and come back while the lists are on their way.
    size = svc.sizes.size(item)
    looking = looking or (lists and size is None and svc.sizes.look_soon(item))
    journey = svc.journeys.journey(item)
    looking = looking or (lists and journey is None and svc.journeys.look_soon(item))
    same_time = svc.daily.same_time(item, shown) if lists else []
    born, died = (
        life(item.artist_bio)
        or life(item.artist)
        or ((essay.born, essay.died) if essay else (None, None))
    )
    note = svc.library.note(item.id, job.kind) if essay else None
    views = essay.composition.views if essay else []
    kept = versions(note.data) if note else []
    pick = note.data.get(SHOWN, len(kept) - 1) if note else -1
    sheet, drawing = drawn(svc, item, views[0]) if views else (None, False)
    return DailyWork(
        day=day,
        item=_light(svc, item, bio=True),
        title=_title(svc, item, essay),
        date=_date(svc, item),
        teaser=essay.teaser if essay else short(museum, TEASER_CHARS),
        focus=essay.focus if essay else None,
        why_today=essay.why_today if essay else "",
        writing=writing and essay is None,
        written=essay is not None,
        headline=essay.headline if essay and essay.headline else MUSEUM_HEADLINE,
        context=essay.context
        if essay and essay.context
        else [p for p in museum.split("\n\n") if p],
        artist=essay.artist if essay else "",
        composition=essay.composition if essay and essay.composition.views else None,
        composition_sheet=sheet_url(svc, item, essay.composition.views[0])
        if essay and essay.composition.views
        else "",
        composition_layers=bool(essay and essay.composition.views),
        composition_bleed=BLEED if essay and essay.composition.views else None,
        composition_versions=[
            CompositionVersion(made=str(v.get("made") or ""), shown=n == pick)
            for n, v in enumerate(kept)
        ],
        composition_drawn=sheet,
        composition_drawn_pending=drawing,
        composition_pending=bool(essay) and svc.compose.pending(item.id),
        details_pending=bool(essay) and svc.mend.pending(item.id),
        colour=essay.colour if essay else "",
        details=details,
        on_frame=essay.on_frame if essay else "",
        similar=similar,
        legacy=legacy,
        by_artist=[_light(svc, other) for other in by_artist],
        same_time=[_light(svc, other) for other in same_time],
        born=born,
        died=died,
        milestones=essay.milestones if essay else [],
        events=essay.events if essay else [],
        pigments=vary_hedges(essay.pigments) if essay else [],
        size=size,
        journey=journey,
        # While the study is cut it looks the later works up itself
        # (``Study._cut``): asked here too, the museums were asked twice,
        # and the study's "later" part was now and then never told.
        legacy_pending=bool(
            lists
            and essay
            and (svc.study.making(item.id) or svc.later.look_soon(item, essay.legacy))
        )
        or looking,
        sources=essay.sources if essay else [],
        model=note.model if note else "",
        partial=not lists,
    )


@router.get("/daily", response_model=DailyWork)
async def daily(
    svc: Svc,
    day: date | None = None,
    wait: Annotated[int, Query(ge=0, le=120)] = 0,
    lists: bool = True,
) -> DailyWork:
    """The work of the day (``day``: a past one), with its page as far as it
    is written; ``wait``: seconds to wait for a page being written.
    ``lists=false``: without the lists under its text
    (``DailyWork.partial``), at once: Discover's tile."""
    today = date.today()
    day = day or today
    if day > today:
        raise HTTPException(400, "that day has not come yet")
    if day == today:
        item = await run_in_threadpool(svc.daily.pick, day)
    else:
        item = await run_in_threadpool(svc.daily.item, day)
    if item is None:
        raise HTTPException(404, "no work of the day")
    future = await run_in_threadpool(svc.daily.ask, item)
    if future is not None and wait:
        # Still writing, or failed: the page shows what there is.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
    writing = future is not None and not future.done()
    return await run_in_threadpool(_work, svc, day, item, writing, lists)


@router.get("/daily/detail")
async def daily_detail(
    svc: Svc, day: date, n: Annotated[int, Query(ge=0, le=9)] = 0
) -> FileResponse:
    """A fragment of the day's work ("Detale"), cut from its original; ``v``
    in the page's address only changes it when the fragment does."""
    item = await run_in_threadpool(svc.daily.item, day)
    path = await run_in_threadpool(svc.daily.detail, item, n) if item is not None else None
    if path is None:
        raise HTTPException(404, "no such fragment")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=604800"})


@router.get("/composition/sheet")
async def composition_sheet(
    svc: Svc, item: str, v: str = "", dark: bool = False, layer: str = ""
) -> FileResponse:
    """The study sheet the work's analysis of composition is drawn on
    (``imaging.sheet``): the picture as stains and a few strokes of a pen,
    on the app's light page or its dark one; ``layer``: the stains alone
    (``wash``) or the pen alone (``pen``, a PNG with nothing around the
    lines), and either with the page's margin beside the field
    (``wash-bleed``, ``pen-bleed``: ``composition_bleed``). Made ahead
    (``Sheets.ahead``), now when asked for before its turn (seconds), then
    kept; ``v`` names the take it belongs to."""
    if layer not in LAYERS:
        raise HTTPException(422, "no such layer")
    work = svc.library.get(item)
    view = await run_in_threadpool(svc.sheets.view, work, v) if work is not None else None
    if work is None or view is None:
        raise HTTPException(404, "no such analysis")
    try:
        path = await run_in_threadpool(svc.sheets.sheet, work, view, dark, layer)
    except (httpx.HTTPError, OSError) as err:  # the picture cannot be had
        raise HTTPException(503, "the picture cannot be had now") from err
    kind = "image/png" if path.suffix == ".png" else "image/jpeg"
    return FileResponse(path, media_type=kind, headers={"Cache-Control": "max-age=604800"})


@router.get("/composition/drawn")
async def composition_drawn(svc: Svc, item: str, v: str, part: str = "page") -> FileResponse:
    """A part of the study sheet the image model drew for a take
    (``DailyWork.composition_drawn``): ``page``, the study on the light
    page with its side margins, or ``m1``…, the line of one mark alone.
    Kept for good, so the app may keep it long."""
    work = svc.library.get(item)
    path = svc.drawn.part(work, v, part) if work is not None else None
    if path is None:
        raise HTTPException(404, "no such sheet")
    kind = "image/png" if path.suffix == ".png" else "image/jpeg"
    return FileResponse(path, media_type=kind, headers={"Cache-Control": "max-age=2592000"})


@router.post("/daily/again", response_model=DailyBrief, dependencies=[Depends(require_owner)])
async def daily_again(svc: Svc) -> DailyBrief:
    """Another work of the day for today, drawn now (Konfiguracja → "Wylosuj
    inne"); its page is asked for at once. 409 when the catalogue has no
    other work fit for it."""
    today = date.today()
    item = await run_in_threadpool(svc.daily.again, today)
    if item is None:
        raise HTTPException(409, "no other work for today")
    await run_in_threadpool(svc.daily.ask, item)
    title = await run_in_threadpool(_title, svc, item, svc.daily.job.essay(item))
    return DailyBrief(day=today.isoformat(), item=_light(svc, item), title=title)
