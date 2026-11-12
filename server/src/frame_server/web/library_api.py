"""Library, museum search and import."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from anyio import CapacityLimiter, to_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from ..ai import PolishText
from ..ai.keywords import KIND as KEYWORDS
from ..ai.keywords import polish_words
from ..ai.museum_words import leftovers, museum_labels
from ..ai.pl_text import KIND as PL_TEXT
from ..copies import CopyLine, Spot
from ..fsutil import own_files
from ..imaging.grids import GRIDS, MIN_PHOTOS, choose, plan_multi
from ..imaging.interest import InterestMap, interest_of
from ..imaging.layout import (
    WHOLE,
    Crop,
    Fit,
    Orientation,
    Plan,
    canvas_size,
    fit_area,
    load_image,
)
from ..imaging.pipeline import (
    RenderSettings,
    board_rgb,
    encode_image,
    plan_for,
    render_original,
)
from ..library import Facets, Item, ItemKind, ItemSummary, Job, Look, PhotoInfo, PlaylistRules
from ..library.duplicates import work_key
from ..library.hosts import Resting, urgent_call
from ..library.images import Gone
from ..library.importer import ALL
from ..library.models import Framing, SharperCopy
from ..library.museums import MUSEUMS
from ..library.repo import Hidden, SortKey, now_iso
from ..library.search import fill as fill_by_search
from ..library.seed import PACKS, import_queries, pack
from ..library.verdict import Place, against
from ..library.viewer import viewer_id
from ..library.zoom import zooms
from ..player import hold_from
from ..schedule import FrameSettings
from ..service import FrameService
from .deps import require_owner, require_token, service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["library"])
Svc = Annotated[FrameService, Depends(service)]


class ItemPage(BaseModel):
    total: int
    items: list[ItemSummary]


class ItemPatch(BaseModel):
    favorite: bool | None = None
    excluded: bool | None = None
    title: str | None = None
    artist: str | None = None
    description: str | None = None
    #: Only for a photo sent once ("Zdjęcie na ramkę"): over the whole frame
    #: or in a passe-partout.
    look: Look | None = None


class ShowRequest(BaseModel):
    hold: str | int | None = None


class RemoteItem(BaseModel):
    item: Item
    in_library: bool
    #: What copies of one work from several sources share
    #: (``duplicates.work_key``), to leave out copies on later pages.
    work: str = ""
    #: The library's copy of the work, when this item is a better one
    #: (the catalogue shows that copy already).
    twin: str | None = None
    #: In a search's later answers: the worse copy, shown before, that this
    #: one takes the place of.
    replaces: str | None = None
    #: Width / height, also when the museum gives no size (measured on the
    #: thumbnail, see ``Importer.measure``); None when not known yet.
    aspect: float | None = None
    #: Its picture can be looked at far closer, in tiles ("Pod lupą").
    zoom: bool = False


def remote_items(
    svc: FrameService,
    items: list[Item],
    copies: bool = True,
    keep_hidden: bool = False,
    hidden: Hidden | None = None,
) -> list[RemoteItem]:
    """Works found for the app, each once, marked whether the library holds
    them (and whether the owner likes them). With ``copies`` (results from
    several sources) a work the library holds from another source comes as
    the library's copy, unless this one is from a more reliable source than a
    copy only the server added. Works with no picture anywhere are left out
    (``ImageCache.gone``), and so are hidden works and their copies
    ("Ukryj dzieło"), unless ``keep_hidden``; without it also those whose
    thumbnail is not here while its museum turned us away
    (``ImageCache.thumb_waits``): they would be empty tiles for now.
    ``hidden``: :meth:`Library.hidden`, when worked out once for many calls.

    A work the library holds names the copy the catalogue shows of it
    (``twin``), when that is another one: a museum's answer brings Commons'
    "Het meisje met de parel" the pictures showed to be the catalogue's "Girl
    with a Pearl Earring" (``library.twins``), and Szukaj leaves it out only
    so (Mateusz 2026-11-10). One the pictures showed to be a detail, or a
    photograph of a work in its frame, is left out unless ``keep_hidden``."""
    found: dict[str, RemoteItem] = {}
    gone = svc.images.gone_ids()
    if keep_hidden:
        hidden = Hidden()
    elif hidden is None:
        hidden = svc.library.hidden()
    for item in items:
        if item.id in gone or item in hidden:
            continue
        if not keep_hidden and svc.images.thumb_waits(item):
            continue
        twin: str | None = None
        held = svc.library.get(item.id)
        if held is None:
            if copies:
                if copy := svc.importer.copy_of(item):
                    item = copy
                elif other := svc.library.twin(item):
                    twin = other.id
        elif not keep_hidden and against(held, Place.MUSEUM):
            continue  # a detail or a framed photograph (library.twins)
        elif best := svc.library.twin(held):
            twin = best.id
        own = svc.library.get(item.id)
        if own is not None:  # the museum's text, the owner's heart
            item = item.model_copy(update={"favorite": own.favorite})
        found.setdefault(
            item.id,
            RemoteItem(
                item=item,
                in_library=own is not None,
                work=work_key(item),
                twin=twin,
                aspect=svc.importer.known_aspect(item),
                zoom=zooms(item),
            ),
        )
    return list(found.values())


class RemotePage(BaseModel):
    total: int
    items: list[RemoteItem]
    #: Museums that did not answer (searching ``all``).
    failed: list[str] = []


class ImportRequest(BaseModel):
    source_id: str


class ImportSearchRequest(BaseModel):
    query: str
    limit: int = Field(24, ge=1, le=500)


#: Threads for pictures, apart from the server's own pool that the app's
#: quick requests ("Teraz", the queue, settings) and the player share: a
#: grid's burst of thumbnails, each waiting for a museum, must not hold them
#: up. What the owner looks at (a card's original, a preview) has threads of
#: its own, so it never waits for a grid either.
THUMB_THREADS = CapacityLimiter(16)
SHOWN_THREADS = CapacityLimiter(8)


def _item(svc: FrameService, item_id: str) -> Item:
    item = svc.library.get(item_id)
    if item is None:
        raise HTTPException(404, f"no item {item_id!r}")
    return item


async def _work(
    svc: FrameService, item_id: str, save: bool = False, threads: CapacityLimiter | None = None
) -> Item:
    """A library item or any museum work (``<museum>:<id>``). Museum works
    are added to the library with ``save``: when the owner shows, crops,
    likes or otherwise keeps one. ``threads``: where a museum is asked."""
    lookup = svc.importer.save if save else svc.importer.resolve
    try:
        item = await to_thread.run_sync(urgent_call(lookup), item_id, limiter=threads)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{item_id}: {err}") from err
    if item is None:
        raise HTTPException(404, f"no item {item_id!r}")
    return item


@router.get("/library/items", response_model=ItemPage)
def list_items(
    svc: Svc,
    q: str = "",
    artist: Annotated[list[str] | None, Query()] = None,
    style: Annotated[list[str] | None, Query()] = None,
    subject: Annotated[list[str] | None, Query()] = None,
    term: Annotated[list[str] | None, Query()] = None,
    color: Annotated[list[str] | None, Query()] = None,
    kind: Annotated[list[ItemKind] | None, Query()] = None,
    year_from: Annotated[int | None, Query(ge=0, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=0, le=2100)] = None,
    source: Annotated[list[str] | None, Query()] = None,
    skip: Annotated[list[str] | None, Query()] = None,
    place: Annotated[list[str] | None, Query()] = None,
    skip_place: Annotated[list[str] | None, Query()] = None,
    favorites: bool = False,
    kept: bool = False,
    sort: SortKey = "recent",
    offset: int = 0,
    limit: Annotated[int, Query(le=200)] = 60,
    seed: int = 0,
) -> ItemPage:
    rules = PlaylistRules(
        query=q,
        artists=artist or [],
        styles=style or [],
        subjects=subject or [],
        terms=term or [],
        colors=color or [],
        kinds=kind or [],
        year_from=year_from,
        year_to=year_to,
        sources=source or [],
        exclude_sources=skip or [],
        places=place or [],
        exclude_places=skip_place or [],
        favorites_only=favorites,
        kept_only=kept,
        # Works with no picture anywhere: an empty tile helps nobody.
        exclude_ids=sorted(svc.images.gone_ids()),
    )
    total, items = svc.library.query(rules, sort=sort, offset=offset, limit=limit, seed=seed)
    if rules.query.strip() or rules.artists:
        # Its artists' pictures laid over each other: copies under other
        # titles and details gone by the next look (library/twins.py).
        svc.twins.after_search(items)
    return ItemPage(total=total, items=[ItemSummary.of(i) for i in items])


@router.get("/library/hidden", response_model=ItemPage)
def hidden_items(svc: Svc) -> ItemPage:
    """The works hidden in the app ("Ukryte" at the end of Playlists), the
    last hidden first."""
    items = svc.library.hidden_items()
    return ItemPage(total=len(items), items=[ItemSummary.of(i) for i in items])


@router.get("/library/facets", response_model=Facets)
def facets(svc: Svc) -> Facets:
    return svc.library.facets()


@router.get("/library/items/{item_id:item}", response_model=Item)
async def get_item(item_id: str, svc: Svc) -> Item:
    return svc.holders.fill(await _work(svc, item_id))


class FragmentPlace(BaseModel):
    """A fragment's place on its whole work: left, top, width and height
    as fractions of the whole's."""

    id: str
    x: float
    y: float
    w: float
    h: float


class FragmentsView(BaseModel):
    """A work's fragments (library/fragments.py), for its card and its
    study: ``whole``, the work a fragment is part of (on a fragment's card,
    None on the work's own); ``fragments``, all of that work's, in order."""

    whole: RemoteItem | None = None
    fragments: list[RemoteItem] = Field(default_factory=list)
    #: Where the fragments lie on the whole, when that is known (a Commons
    #: tile set): the full-screen viewer lays them on it while zooming.
    places: list[FragmentPlace] = Field(default_factory=list)


@router.get("/library/items/{item_id:item}/fragments", response_model=FragmentsView)
async def item_fragments(item_id: str, svc: Svc) -> FragmentsView:
    item = await _work(svc, item_id)
    work = await _work(svc, item.part_of) if item.part_of else item
    found, places = await run_in_threadpool(urgent_call(svc.importer.placed_fragments), work)
    whole = remote_items(svc, [work], copies=False, keep_hidden=True) if item.part_of else []
    return FragmentsView(
        whole=whole[0] if whole else None,
        fragments=remote_items(svc, found, copies=False, keep_hidden=True),
        places=[FragmentPlace(id=f.id, x=x, y=y, w=w, h=h) for f, (x, y, w, h) in places],
    )


class DetailsView(BaseModel):
    """A work's details, for its card ("Detale"; Mateusz 2026-11-11):
    pictures of a part of it the server keeps apart from the catalogue as
    copies (``Library.details``). ``whole``: on a detail's card, the work
    it is a detail of."""

    whole: RemoteItem | None = None
    details: list[RemoteItem] = Field(default_factory=list)


@router.get("/library/items/{item_id:item}/details", response_model=DetailsView)
async def item_details(item_id: str, svc: Svc) -> DetailsView:
    item = await _work(svc, item_id)

    def find() -> tuple[list[Item], Item | None]:
        # On a detail's card, the whole work and its other details.
        whole = svc.library.whole_of(item)
        found = svc.library.details(whole or item)
        return [d for d in found if d.id != item.id], whole

    found, whole = await run_in_threadpool(urgent_call(find))
    gone = svc.images.gone_ids()
    seen = [d for d in found if d.id not in gone]
    shown = remote_items(svc, seen, copies=False, keep_hidden=True)
    wholes = remote_items(svc, [whole], copies=False) if whole is not None else []
    return DetailsView(whole=wholes[0] if wholes else None, details=shown)


class HolderView(BaseModel):
    """The museum the work is in, for its card (``Item.held_by``):
    ``status`` "found" (``name`` says which); "looking" (ask again); "none"
    (nobody says); "off" (photos, own works)."""

    status: Literal["found", "looking", "none", "off"]
    name: str = ""
    #: ``Item.held_at``: the place's key, for Szukaj with it (a hold).
    key: str = ""


@router.post("/library/items/{item_id:item}/holder", response_model=HolderView)
async def item_holder(
    item_id: str, svc: Svc, wait: Annotated[float, Query(ge=0, le=60)] = 0
) -> HolderView:
    """The card opened on a work from Commons, Openverse, WikiArt or
    Europeana: which museum it is in, looked up on Wikidata and Commons in
    the background. ``wait``: seconds to wait for the answer."""
    item = await _work(svc, item_id)
    future = svc.holders.soon(item)
    if wait:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
    status, name = svc.holders.look(item, 0)
    held = svc.holders.fill(svc.library.get(item.id) or item)
    return HolderView(status=status, name=held.held_by or name, key=held.held_at)


class PolishView(BaseModel):
    """A work's Polish texts for its card. ``status``: "ready"; "waiting"
    (being written, ask again); "none" (the model could not); "off" (no key,
    switched off, or no museum work). While "waiting", ``title`` is the
    Polish title once the model has written it, ahead of the texts."""

    status: Literal["ready", "waiting", "none", "off"]
    text: PolishText | None = None
    title: str | None = None


#: How often a wait looks for a title written ahead of the texts.
EARLY_POLL = 0.2


@router.get("/library/items/{item_id:item}/polish", response_model=PolishView)
async def item_polish(
    item_id: str,
    svc: Svc,
    wait: Annotated[float, Query(ge=0, le=60)] = 0,
    early: bool = False,
) -> PolishView:
    """The work's Polish title and texts, asked for now if it has none;
    ``wait``: seconds to wait for them. ``early``: the wait ends as soon as
    the title is written, so the card shows it before the texts."""
    job = svc.pl_text
    item = await _work(svc, item_id)
    if not job.enabled() or not job.applies(item):
        return PolishView(status="off")
    if (text := job.text(item)) is not None:
        return PolishView(status="ready", text=text)
    if svc.library.get(item_id) is None:  # a museum work only looked at: pooled
        item = await run_in_threadpool(svc.importer.add, item.model_copy(update={"pooled": True}))
    future = svc.ai.need_now(item_id, PL_TEXT)
    if wait:
        written = asyncio.wrap_future(future)
        loop = asyncio.get_running_loop()
        until = loop.time() + wait
        try:
            while (left := until - loop.time()) > 0:
                if early and job.early_title(item_id):
                    break
                try:
                    await asyncio.wait_for(
                        asyncio.shield(written), min(left, EARLY_POLL) if early else left
                    )
                    break
                except TimeoutError:
                    continue
        except Exception:  # the model is unavailable: the card stays in English
            return PolishView(status="none")
    if (text := job.text(item)) is not None:
        return PolishView(status="ready", text=text)
    done = future.done() or job.fresh(item, svc.library.note(item_id, PL_TEXT))
    if done:
        return PolishView(status="none")
    return PolishView(status="waiting", title=job.early_title(item_id))


class SeenView(BaseModel):
    """What the model saw in the picture, for the card; ``status`` as in
    PolishView. With the museum's own labels in Polish: its styles and
    subjects that the words do not already say (``tags``), the kind of
    object and where it is from ("" when the work has none)."""

    status: Literal["ready", "waiting", "none", "off"]
    words: list[str] = Field(default_factory=list)  # Polish: things, places, mood
    tags: list[str] = Field(default_factory=list)
    classification: str = ""
    culture: str = ""


@router.post("/library/items/{item_id:item}/describe", response_model=SeenView)
async def describe_item(
    item_id: str, svc: Svc, wait: Annotated[float, Query(ge=0, le=60)] = 0
) -> SeenView:
    """The card opened: the model's jobs for this work or photo (keywords,
    Polish texts) go ahead of everything else. ``wait``: seconds to wait for
    the keywords and the museum's labels in Polish; the Polish texts come
    from ``/polish``."""
    item = await _work(svc, item_id)
    labels = museum_labels(item)
    asking = svc.museum_words.ask(labels.all)
    started = time.monotonic()
    status = await _keywords(svc, item, wait)
    if asking and wait:  # asked as the keywords were: what is left of the wait
        left = max(1.0, wait - (time.monotonic() - started))
        await run_in_threadpool(svc.museum_words.polish, labels.all, left)
    polish, pending = svc.museum_words.polish(labels.all)
    words: list[str] = []
    if status == "ready":
        note = svc.library.note(item_id, KEYWORDS)
        words = polish_words(note.data) if note is not None else []
        status = "ready" if words else "none"
    if pending and status != "waiting":
        status = "waiting"
    culture = svc.museum_words.known(labels.culture) or "" if labels.culture else ""
    kind = svc.museum_words.known(labels.kind) or "" if labels.kind else ""
    return SeenView(
        status=status,
        words=words,
        # A label still being asked is left out for now: not English first.
        tags=leftovers(
            [polish[t] for t in labels.tags if not pending or svc.museum_words.known(t)],
            [*words, culture],
        ),
        classification=kind,
        culture=culture,
    )


async def _keywords(svc: FrameService, item: Item, wait: float) -> str:
    """The keywords of ``item`` asked ahead of the queue (with the Polish
    texts): "ready" (in its note), "waiting", "none" or "off"."""
    jobs = [job for job in svc.ai.jobs.values() if job.enabled() and job.in_library(item)]
    if not jobs:
        return "off"
    if svc.library.get(item.id) is None:  # a museum work only looked at: pooled
        item = await run_in_threadpool(svc.importer.add, item.model_copy(update={"pooled": True}))
    futures = {job.kind: svc.ai.need_now(item.id, job.kind) for job in jobs}
    future = futures.get(KEYWORDS)
    if future is None:
        return "off"
    if wait:
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
        except TimeoutError:
            pass
        except Exception:  # the model is unavailable
            return "none"
    note = svc.library.note(item.id, KEYWORDS)
    if note is not None and svc.ai.jobs[KEYWORDS].fresh(item, note):
        return "ready"
    return "none" if future.done() else "waiting"


class SharperView(BaseModel):
    """A sharper copy of the work's picture, for its card. ``status``:
    "found" (``sharper`` says which: the app asks for the picture again by
    its ``item_id``); "looking" (ask again); "none" (no source has a better
    one); "fine" (the work's own is good); "off" (photos, own works)."""

    status: Literal["looking", "found", "none", "fine", "off"]
    sharper: SharperCopy | None = None
    #: The picture shown now as its source gave it (0: not downloaded yet),
    #: for "Zdjęcie dzieła" on the card.
    width: int = 0
    height: int = 0
    #: The museum the work is in (``Item.held_by``): a copy from the museum
    #: itself names it.
    held_by: str = ""
    #: ``Item.held_at``: its key.
    held_at: str = ""


@router.post("/library/items/{item_id:item}/sharpen", response_model=SharperView)
async def sharpen_item(
    item_id: str, svc: Svc, wait: Annotated[float, Query(ge=0, le=60)] = 0
) -> SharperView:
    """The card opened: when the work's picture is poor, other sources are
    asked for a sharper copy of it in the background. ``wait``: seconds to
    wait for the answer."""
    item = await _work(svc, item_id)
    future = svc.sharper.soon(item)
    if wait:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), wait)
    status = future.result() if future.done() else "looking"
    stored = svc.library.get(item_id)
    copy = (stored or item).sharper
    size = svc.images.source_size(stored or item) or (0, 0, 0)
    return SharperView(
        status="found" if copy is not None else status,
        sharper=copy,
        width=size[0],
        height=size[1],
        held_by=svc.holders.fill(stored or item).held_by,
        held_at=svc.holders.fill(stored or item).held_at,
    )


@router.get("/library/items/{item_id:item}/copies")
async def item_copies(item_id: str, svc: Svc) -> StreamingResponse:
    """Every copy of the work's picture the sources have ("Szukaj lepszej
    kopii"), as they answer: :class:`CopyLine` per line (JSON lines)."""
    item = await _work(svc, item_id)
    if item.kind != ItemKind.ARTWORK or item.look is not None:
        raise HTTPException(422, "only a museum work has copies elsewhere")
    loop = asyncio.get_running_loop()
    lines: asyncio.Queue[CopyLine | None] = asyncio.Queue()
    gone = threading.Event()

    def emit(line: CopyLine) -> None:
        loop.call_soon_threadsafe(lines.put_nowait, line)

    def look() -> None:
        try:
            svc.copies.look(item, emit, gone)
        except Exception:
            log.exception("copies of %s", item.id)
            emit(CopyLine(kind="end"))
        finally:
            loop.call_soon_threadsafe(lines.put_nowait, None)

    async def answer() -> AsyncIterator[str]:
        task = asyncio.ensure_future(run_in_threadpool(urgent_call(look)))
        try:
            while (line := await lines.get()) is not None:
                yield line.model_dump_json(by_alias=True, exclude_none=True) + "\n"
        finally:
            gone.set()
            task.cancel()

    return StreamingResponse(answer(), media_type="application/x-ndjson")


class CopyPick(BaseModel):
    #: The copy's id, or the work's own to go back to its own picture.
    item_id: str


@router.put("/library/items/{item_id:item}/copy", response_model=Item)
async def choose_copy(item_id: str, pick: CopyPick, svc: Svc) -> Item:
    """The owner's pick for the work's picture: a copy from another source,
    or (its own id) the work's own. The work keeps its id, texts, hearts,
    playlists and crops; the frame shows the new picture from its next
    change."""
    item = await _work(svc, item_id)
    if item.kind != ItemKind.ARTWORK or item.look is not None:
        raise HTTPException(422, "only a museum work has copies elsewhere")
    try:
        return await run_in_threadpool(urgent_call(svc.copies.choose), item, pick.item_id)
    except LookupError as err:
        raise HTTPException(404, f"no copy {pick.item_id!r}") from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"copy unavailable: {err}") from err


@router.delete("/library/items/{item_id:item}/copy", response_model=Item)
async def keep_own_picture(item_id: str, svc: Svc) -> Item:
    """Back to the work's own picture; no copy is looked for again."""
    item = await _work(svc, item_id)
    return await run_in_threadpool(svc.sharper.keep_own, item)


@router.get("/library/items/{item_id:item}/copies/{copy_id}/spot", response_model=Spot)
async def copy_spot(
    item_id: str,
    copy_id: str,
    svc: Svc,
    x: Annotated[float | None, Query(ge=0, le=1)] = None,
    y: Annotated[float | None, Query(ge=0, le=1)] = None,
) -> Spot:
    """One spot of the picture shown now and of the copy, side by side at
    the frame's scale (``x``, ``y``: its centre; the most detailed spot when
    not given)."""
    item = await _work(svc, item_id)
    try:
        return await run_in_threadpool(urgent_call(svc.copies.compare), item, copy_id, x, y)
    except LookupError as err:
        raise HTTPException(404, f"no copy {copy_id!r}") from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    except Gone as err:
        raise HTTPException(410, str(err)) from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"picture unavailable: {err}") from err


@router.patch("/library/items/{item_id:item}", response_model=Item)
async def patch_item(item_id: str, patch: ItemPatch, svc: Svc) -> Item:
    item = await _work(svc, item_id, save=True)
    changes = patch.model_dump(exclude_none=True)
    if patch.look is not None:
        if item.look is None:
            raise HTTPException(422, "only a photo sent once has a look of its own")
        changes["look"] = patch.look
    liked = changes.pop("favorite", None)
    if liked is not None:  # the asking person's own heart
        svc.library.set_favorite(viewer_id(), item.id, liked)
        changes.setdefault("favorite", liked)  # for the player below
    stored = {k: v for k, v in changes.items() if k != "favorite"}
    if "excluded" in stored and stored["excluded"] != item.excluded:
        stored["excluded_at"] = now_iso() if stored["excluded"] else None
    updated = svc.library.update(item.id, **stored) if stored else svc.library.get(item.id)
    assert updated is not None
    if changes.keys() & {"favorite", "excluded"}:
        svc.player.item_changed(item_id)  # e.g. a new favourite joins Ulubione playing now
    if liked:
        svc.kept.soon([item_id])  # a favourite's original stays on the server
    player, state = svc.player, svc.player.state
    if "look" in changes and updated.look != item.look:
        if state.current_item_id == item_id:
            svc.background(player.restyle())  # on the frame now: shown the new way
        elif state.requested[:1] == [item_id]:
            svc.background(player.render_ahead())  # next: drawn again ahead
    return updated


@router.delete("/library/items/{item_id:item}", dependencies=[Depends(require_owner)])
def delete_item(item_id: str, svc: Svc) -> dict[str, bool]:
    item = _item(svc, item_id)
    svc.library.delete(item_id)
    svc.images.remove(item)
    return {"deleted": True}


@router.get("/library/items/{item_id:item}/thumb")
async def item_thumb(item_id: str, svc: Svc, tile: bool = False) -> FileResponse:
    """A work's thumbnail, the catalogue's or any museum work's: the app
    shows every thumbnail from here, never from the museum itself. With
    ``tile``, as the cover tiles of Odkrywaj show it: the work without the
    paper or mount around it (``ImageCache.tile``; older apps never ask)."""
    kept = svc.images.kept_thumb(item_id)
    if kept is not None:
        if tile:
            kept = await to_thread.run_sync(svc.images.tile, kept, limiter=THUMB_THREADS)
        return FileResponse(
            kept, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"}
        )
    item = await _work(svc, item_id, threads=THUMB_THREADS)
    try:
        path = await to_thread.run_sync(
            urgent_call(svc.images.ensure_thumb), item, limiter=THUMB_THREADS
        )
    except Gone as err:  # the app leaves the work out
        raise HTTPException(410, f"no picture anywhere: {err}") from err
    except Resting as err:  # the app leaves it out for now, asks again later
        wait = max(svc.images.thumb_waits(item), 60.0)
        raise HTTPException(
            503, f"thumbnail not now: {err}", headers={"Retry-After": f"{wait:.0f}"}
        ) from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"thumbnail unavailable: {err}") from err
    if tile:
        path = await to_thread.run_sync(svc.images.tile, path, limiter=THUMB_THREADS)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.get("/library/items/{item_id:item}/image")
async def item_image(item_id: str, svc: Svc) -> FileResponse:
    """The original as the card shows it: before any download in the background."""
    item = await _work(svc, item_id, threads=SHOWN_THREADS)
    try:
        path, original = await to_thread.run_sync(
            svc.images.picture, item, True, limiter=SHOWN_THREADS
        )
    except Gone as err:  # the app leaves the work out
        raise HTTPException(410, f"no picture anywhere: {err}") from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"image unavailable: {err}") from err
    # Without the original, its thumbnail: asked for again next time.
    cache = "max-age=86400" if original else "no-store"
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": cache})


_preview_locks: dict[str, asyncio.Lock] = {}
PREVIEW_CACHE_FILES = 200
#: How long a preview waits for the work's Polish texts (asked first in line).
PREVIEW_POLISH_SECONDS = 20.0
NO_STORE = {"Cache-Control": "no-store"}
PREVIEW_KIND = "fast2"  # part of the cache key: earlier previews went through the whole render,
# then Multi boards cropped by the originals rather than the thumbnails


def _prune(directory: Path, keep: int) -> None:
    files = list(own_files(directory))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def _trial_settings(
    svc: FrameService, item: Item, settings: str | None, framing: str | None
) -> tuple[Item, FrameSettings]:
    """The work and the frame settings a preview tries (see :func:`item_preview`)."""
    frame_settings = svc.player.settings
    try:
        if settings:
            frame_settings = FrameSettings.model_validate_json(settings)
        if framing:
            orientation = frame_settings.orientation.value
            saved = item.framing.get(orientation) or Framing()
            trial = Framing.model_validate_json(framing).model_dump(exclude_none=True)
            tried = Framing.model_validate(saved.model_dump() | trial)
            item = item.model_copy(update={"framing": {**item.framing, orientation: tried}})
    except ValidationError as err:
        raise HTTPException(422, f"invalid preview: {err}") from err
    return item, frame_settings


def _interest(svc: FrameService, board: list[Item]) -> list[InterestMap | None]:
    """The interest analyses of a Multi board's photos, from their
    thumbnails and kept: the previews of every grid, margin and mat crop the
    photos alike, as the app's own drawing of the board does."""
    found: list[InterestMap | None] = []
    for shown in board:
        try:
            found.append(interest_of(svc.images.ensure_thumb(shown, True)))
        except (Gone, Resting, httpx.HTTPError, OSError):
            found.append(None)
    return found


@router.get("/library/items/{item_id:item}/preview")
async def item_preview(
    item_id: str,
    svc: Svc,
    settings: str | None = None,
    framing: str | None = None,
    own_look: bool = True,
    photos: str | None = None,
) -> Response:
    """The picture framed as on the panel (crop, mat, lettering), in its own
    colours: the correction for the inks is left to the panel's image.

    With the saved settings, or with ``settings`` (FrameSettings JSON; only
    orientation and presentation matter) to try a framing before saving it.
    ``framing`` (Framing JSON) likewise tries crops before they are saved:
    the ones it gives replace the saved ones for that orientation.
    Without ``own_look`` a photo sent once is framed as the settings frame
    photos, to try them on it. ``photos`` (ids, comma-separated): a Multi
    board of these, the owner's photos for trying the grids on
    (``FrameSettings.multi_photos``), rather than those that would join
    ``item_id`` on the frame.
    """
    item = await _work(svc, item_id, threads=SHOWN_THREADS)
    if not own_look and item.look is not None:
        item = item.model_copy(update={"look": None})
    item, frame_settings = _trial_settings(svc, item, settings, framing)
    # The texts on the mat in Polish, as the frame will show them: an
    # English preview would stay in the app's cache after they come.
    await svc.player.wait_for_polish(item, frame_settings, PREVIEW_POLISH_SECONDS)

    def plan() -> tuple[RenderSettings, list[Item], Path]:
        # Off the event loop: a Multi board's photos come from the library
        # (2026-11-08: about 1 s on the NAS, every other request waiting).
        render_settings = svc.player.render_settings(item, frame_settings)
        board = _preview_board(
            svc, item, frame_settings, photos
        )  # MULTI: with the photos beside it
        ids = ",".join(i.id for i in board)
        # A sharper copy of a picture since: another preview.
        copies = ",".join(shown.sharper.item_id for shown in board if shown.sharper is not None)
        shape = render_settings.model_dump_json() + svc.palette.name
        key = hashlib.sha1(
            (PREVIEW_KIND + shape + ids + copies).encode(),
            usedforsecurity=False,
        ).hexdigest()[:12]
        return (
            render_settings,
            board,
            svc.images.thumbs.parent / "previews" / f"{item.file_stem}-{key}.jpg",
        )

    render_settings, board, path = await run_in_threadpool(plan)
    if not path.is_file():
        async with _preview_locks.setdefault(path.name, asyncio.Lock()):
            if not path.is_file():
                try:
                    pictures = [
                        await to_thread.run_sync(
                            svc.images.picture, shown, True, limiter=SHOWN_THREADS
                        )
                        for shown in board
                    ]
                except (httpx.HTTPError, OSError) as err:
                    raise HTTPException(502, f"image unavailable: {err}") from err
                sources = [p for p, _ in pictures]

                def build() -> bytes:
                    multi = svc.player.multi(item, frame_settings)
                    auto = None
                    if multi:
                        auto = [m.pick if m else None for m in _interest(svc, board)]
                    img = render_original(
                        sources,
                        render_settings,
                        svc.palette,
                        multi=multi,
                        seed=",".join(i.id for i in board),
                        auto=auto,
                    )
                    img.thumbnail((1280, 1280))
                    return encode_image(img, "jpeg", quality=90)

                data = await to_thread.run_sync(build, limiter=SHOWN_THREADS)
                if not all(original for _, original in pictures):
                    # Drawn from a thumbnail: not kept, the original may come.
                    return Response(data, media_type="image/jpeg", headers=NO_STORE)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                _prune(path.parent, PREVIEW_CACHE_FILES)
    # Without ``settings`` the address stays the same when the presentation
    # changes: the app must ask again rather than keep the old framing.
    cache = "max-age=3600" if settings else "no-cache"
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": cache})


class BoardWindow(BaseModel):
    photo: int  # which of the board's photos (index in BoardView.photos)
    rect: tuple[float, float, float, float]  # x, y, w, h as fractions of the canvas
    crop: tuple[float, float, float, float]  # x, y, w, h of the photo shown, as fractions of it


class BoardLayout(BaseModel):
    orientation: Orientation
    grid: str  # as asked: "auto" or a grid's letter
    shown: str  # the grid drawn ("auto": the one it picks for these photos)
    windows: list[BoardWindow]


class BoardView(BaseModel):
    """A Multi board for the app to draw from the thumbnails it has, at once
    and for every grid, while the preview renders (the previews of one
    board took 2–5 s each on the NAS, Mateusz 2026-11-08)."""

    photos: list[str]  # the photos on the board, ``item_id`` first
    mat: str  # "#rrggbb", about the board's colour
    layouts: list[BoardLayout]  # both orientations, "auto" and each grid; none: not a board


@router.get("/library/items/{item_id:item}/board")
async def item_board(
    item_id: str,
    svc: Svc,
    settings: str | None = None,
    own_look: bool = True,
    photos: str | None = None,
) -> BoardView:
    """Where each photo of the Multi board a preview of ``item_id`` shows
    goes, and which part of it, for every grid of its count; ``settings``
    and ``own_look`` as for :func:`item_preview` (only the photos'
    presentation matters: margin, mat and count, not the grid)."""
    item = await _work(svc, item_id, threads=SHOWN_THREADS)
    if not own_look and item.look is not None:
        item = item.model_copy(update={"look": None})
    item, frame_settings = _trial_settings(svc, item, settings, None)
    return await to_thread.run_sync(
        _board_view, svc, item, frame_settings, photos, limiter=SHOWN_THREADS
    )


def _preview_board(
    svc: FrameService, item: Item, frame_settings: FrameSettings, photos: str | None
) -> list[Item]:
    """The photos a preview's Multi board shows: ``photos`` (the owner's
    choice for trying grids on, Mateusz 2026-11-08) when given, those that
    would join ``item`` otherwise."""
    if photos and svc.player.multi(item, frame_settings):
        chosen = svc.player.chosen_board(item, [i for i in photos.split(",") if i], frame_settings)
        if chosen is not None:
            return chosen
    return svc.player.preview_board(item, frame_settings)


def _board_view(
    svc: FrameService, item: Item, frame_settings: FrameSettings, photos: str | None = None
) -> BoardView:
    render_settings = svc.player.render_settings(item, frame_settings)
    mat = render_settings.layout.mat
    board = _preview_board(svc, item, frame_settings, photos)
    ids = [i.id for i in board]
    if not svc.player.multi(item, frame_settings) or len(board) < MIN_PHOTOS:
        return BoardView(photos=ids, mat="#ffffff", layouts=[])
    thumbs: list[Image.Image] = []
    for shown in board:
        try:
            thumbs.append(load_image(svc.images.ensure_thumb(shown, True)))
        except (Gone, Resting, httpx.HTTPError, OSError):
            return BoardView(photos=ids, mat="#ffffff", layouts=[])
    maps = _interest(svc, board)
    auto = [m.pick if m else None for m in maps]
    sizes = [img.size for img in thumbs]
    seed = ",".join(ids)
    margin = render_settings.layout.margin
    layouts = []
    for orientation in Orientation:
        canvas = canvas_size(orientation)
        for grid in ["auto", *(g.id for g in GRIDS[len(board)])]:
            plan, order = plan_multi(sizes, canvas, margin, grid, seed, auto)
            shown_grid = choose([w / h for w, h in sizes], canvas, margin, grid, seed)[0].id
            windows = []
            for window, photo in zip(plan.windows, order, strict=True):
                pw, ph = sizes[photo]
                x0, y0, x1, y1 = window.box
                windows.append(
                    BoardWindow(
                        photo=photo,
                        rect=_box(window.rect, canvas),
                        crop=(
                            round(x0 / pw, 5),
                            round(y0 / ph, 5),
                            round((x1 - x0) / pw, 5),
                            round((y1 - y0) / ph, 5),
                        ),
                    )
                )
            layouts.append(
                BoardLayout(orientation=orientation, grid=grid, shown=shown_grid, windows=windows)
            )
    r, g, b = board_rgb(thumbs, mat)
    return BoardView(photos=ids, mat=f"#{r:02x}{g:02x}{b:02x}", layouts=layouts)


Box = tuple[float, float, float, float]  # x, y, w, h as fractions of the canvas


class FramingWindow(BaseModel):
    role: str  # "picture" (FIT, DESCRIPTION), "fill" or "detail"
    aspect: float  # width / height of the window on the frame
    crop: Crop
    custom: bool  # set by the user (else chosen automatically)
    rect: Box | None = None  # where the window is on the canvas
    area: Box | None = None  # FIT: where a window of another shape would be centred


class FramingView(BaseModel):
    orientation: Orientation
    fit: Fit  # how the picture is shown in this orientation
    width: int  # the picture, in pixels
    height: int
    windows: list[FramingWindow]  # what can be adjusted; none with a passe-partout


class FramingUpdate(BaseModel):
    orientation: Orientation
    # One for FILL and FIT; DESCRIPTION: the picture's and the close-up's,
    # or only the close-up's (apps from before the picture could be cropped).
    crops: list[Crop]


def _framing_plan(
    svc: FrameService, item: Item, orientation: Orientation, automatic: bool = False
) -> tuple[Plan, tuple[int, int], RenderSettings]:
    settings = svc.player.settings.model_copy(update={"orientation": orientation})
    render_settings = svc.player.render_settings(item, settings)
    if automatic:  # as if nothing had been saved
        layout = render_settings.layout.model_copy(
            update={"crop": None, "detail": None, "picture_crop": None, "fit_crop": None}
        )
        render_settings = render_settings.model_copy(update={"layout": layout})
    img = load_image(svc.images.ensure_image(item))
    if svc.player.multi(item, settings):  # each photo cropped automatically to its window
        return Plan(Fit.MULTI, canvas_size(orientation), []), img.size, render_settings
    plan = plan_for(img, render_settings.layout, caption=bool(render_settings.caption))
    return plan, img.size, render_settings


def _box(rect: tuple[int, int, int, int], canvas: tuple[int, int]) -> Box:
    x, y, w, h = rect
    cw, ch = canvas
    return round(x / cw, 5), round(y / ch, 5), round(w / cw, 5), round(h / ch, 5)


def _framing_view(
    item: Item,
    orientation: Orientation,
    plan: Plan,
    size: tuple[int, int],
    render_settings: RenderSettings,
    automatic: bool = False,
) -> FramingView:
    saved = item.framing.get(orientation.value) or Framing()
    custom = not automatic and {
        Fit.FILL: saved.fill is not None,
        Fit.DESCRIPTION: saved.detail is not None or saved.picture is not None,
        Fit.FIT: saved.fit is not None,
    }.get(plan.fit, False)
    area = None
    if plan.fit == Fit.FIT:
        margin, caption = render_settings.layout.margin, bool(render_settings.caption)
        area = _box(fit_area(plan.canvas, margin, caption), plan.canvas)
    windows = [
        FramingWindow(
            role=w.role,
            aspect=round(w.aspect, 4),
            crop=w.crop,
            custom=custom,
            rect=_box(w.rect, plan.canvas),
            area=area if w.role == "picture" else None,
        )
        for w in plan.windows
        if w.crop is not None
    ]
    return FramingView(
        orientation=orientation, fit=plan.fit, width=size[0], height=size[1], windows=windows
    )


async def _plan_and_view(
    svc: FrameService, item: Item, orientation: Orientation, automatic: bool = False
) -> FramingView:
    try:
        plan, size, render_settings = await run_in_threadpool(
            _framing_plan, svc, item, orientation, automatic
        )
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"image unavailable: {err}") from err
    return _framing_view(item, orientation, plan, size, render_settings, automatic)


@router.get("/library/items/{item_id:item}/framing", response_model=FramingView)
async def get_framing(
    item_id: str, svc: Svc, orientation: Orientation | None = None, automatic: bool = False
) -> FramingView:
    """How the picture is cropped on the frame, and what can be adjusted.
    With ``automatic`` the crops the server would choose, ignoring saved ones
    (nothing is changed: the app offers them before the user sends them)."""
    item = await _work(svc, item_id)
    orientation = orientation or svc.player.settings.orientation
    return await _plan_and_view(svc, item, orientation, automatic)


@router.put("/library/items/{item_id:item}/framing", response_model=FramingView)
async def put_framing(item_id: str, update: FramingUpdate, svc: Svc) -> FramingView:
    """Save a corrected crop (FILL, or FIT with its shape) or the picture
    and its close-up (DESCRIPTION) for this picture."""
    item = await _work(svc, item_id, save=True)
    current = await _plan_and_view(svc, item, update.orientation)
    framing = item.framing.get(update.orientation.value, Framing()).model_copy()
    if current.fit == Fit.FILL and len(update.crops) == 1:
        framing.fill = update.crops[0]
    elif current.fit == Fit.DESCRIPTION and len(update.crops) == 2:
        picture, framing.detail = update.crops
        # The whole picture, untouched, stays automatic.
        framing.picture = None if _uncropped(picture) else picture
    elif current.fit == Fit.DESCRIPTION and len(update.crops) == 1:
        framing.detail = update.crops[0]
    elif current.fit == Fit.FIT and len(update.crops) == 1:
        framing.fit = update.crops[0]
    else:
        raise HTTPException(422, f"{current.fit.value}: wrong number of crops")
    item = _save_framing(svc, item, update.orientation, framing)
    return await _plan_and_view(svc, item, update.orientation)


@router.delete("/library/items/{item_id:item}/framing", response_model=FramingView)
async def reset_framing(item_id: str, svc: Svc, orientation: Orientation) -> FramingView:
    """Back to the automatic crop of the current mode for this orientation."""
    item = await _work(svc, item_id, save=True)
    current = await _plan_and_view(svc, item, orientation)
    framing = item.framing.get(orientation.value, Framing()).model_copy()
    fields = {Fit.FILL: ["fill"], Fit.DESCRIPTION: ["detail", "picture"], Fit.FIT: ["fit"]}
    if current.fit not in fields:
        raise HTTPException(422, f"{current.fit.value}: nothing to reset")
    for field in fields[current.fit]:
        setattr(framing, field, None)
    empty = framing == Framing()
    item = _save_framing(svc, item, orientation, None if empty else framing)
    return await _plan_and_view(svc, item, orientation)


def _uncropped(crop: Crop) -> bool:
    """The picture's window as it is without a correction (layout.WHOLE)."""
    off = max(abs(crop.zoom - WHOLE.zoom), abs(crop.x - WHOLE.x), abs(crop.y - WHOLE.y))
    return crop.aspect is None and off < 1e-3


def _save_framing(
    svc: FrameService, item: Item, orientation: Orientation, framing: Framing | None
) -> Item:
    stored = dict(item.framing)
    if framing is None:
        stored.pop(orientation.value, None)
    else:
        stored[orientation.value] = framing
    updated = svc.library.update(item.id, framing=stored) or item
    player = svc.player
    if player.state.current_item_id == item.id and player.settings.orientation == orientation:
        svc.background(player.restyle())  # show the new crop now
    return updated


@router.post("/library/items/{item_id:item}/show", status_code=202)
async def show_item(item_id: str, request: ShowRequest, svc: Svc) -> dict[str, Any]:
    item = await _work(svc, item_id, save=True)
    _remember_sent(svc, item)
    svc.background(svc.player.show(item, "app", hold_from(request.hold)))
    return {"accepted": True, "item_id": item.id}


@router.post("/library/items/{item_id:item}/queue", status_code=202)
async def queue_item(item_id: str, svc: Svc) -> dict[str, Any]:
    """The owner's "Dodaj do kolejki": the work is shown at the next change."""
    item = await _work(svc, item_id, save=True)
    svc.player.queue_next(item.id)
    _remember_sent(svc, item)
    svc.background(svc.player.get_ready())
    return {"accepted": True, "item_id": item.id}


def _remember_sent(svc: FrameService, item: Item) -> None:
    """A photo sent once joins "Historia przesłanych" and gets its keywords
    ahead of the background."""
    svc.player.remember_sent(item, viewer_id())
    if item.look is not None:
        svc.ai.need_now(item.id, KEYWORDS)


@router.post("/library/upload", response_model=Item)
async def upload(
    svc: Svc,
    file: Annotated[UploadFile, File()],
    kind: Annotated[ItemKind, Form()] = ItemKind.OWN,
    title: Annotated[str, Form()] = "",
    artist: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    taken_at: Annotated[str | None, Form()] = None,
    latitude: Annotated[float | None, Form()] = None,
    longitude: Annotated[float | None, Form()] = None,
    look: Annotated[str | None, Form()] = None,
) -> Item:
    """Add a picture to the library (e.g. photos from the phone's camera roll).

    With ``look`` (Look JSON) a photo is sent once ("Zdjęcie na ramkę"): it
    is shown or queued from the app with that look and stays out of every
    list and rotation."""
    data = await file.read()
    photo = (
        PhotoInfo(taken_at=taken_at, latitude=latitude, longitude=longitude)
        if kind == ItemKind.PHOTO
        else None
    )
    try:
        single = Look.model_validate_json(look) if look else None
    except ValidationError as err:
        raise HTTPException(422, f"invalid look: {err}") from err
    if single is not None and kind != ItemKind.PHOTO:
        raise HTTPException(422, "only photos are sent once")
    return await run_in_threadpool(
        svc.importer.add_upload,
        data,
        kind=kind,
        title=title or (file.filename or ""),
        artist=artist,
        description=description,
        photo=photo,
        look=single,
    )


# -- museums -------------------------------------------------------------------


@router.get("/museums")
def museums(svc: Svc) -> list[dict[str, str]]:
    return [{"key": k, "name": MUSEUMS[k].name} for k in svc.importer.sources()]


@router.get("/museums/{source}/search", response_model=RemotePage)
async def museum_search(
    source: str, svc: Svc, q: str, page: int = 1, limit: int | None = None
) -> RemotePage:
    """One museum, or ``all`` of them (``limit`` results from each)."""
    failed: list[str] = []
    if source == ALL:
        texts = await run_in_threadpool(svc.importer.typed, q)
        total, items, failed = await run_in_threadpool(
            urgent_call(svc.importer.search_all), texts, limit or 8, page
        )
    elif source in svc.importer.sources():
        texts = await run_in_threadpool(svc.importer.typed, q, [source])
        try:
            total, items = await run_in_threadpool(
                urgent_call(svc.importer.search), source, texts[source], limit or 24, page
            )
        except httpx.HTTPError as err:
            raise HTTPException(502, f"{source}: {err}") from err
    else:
        raise HTTPException(404, f"unknown museum {source!r}")
    return RemotePage(
        total=total, items=remote_items(svc, items, copies=source == ALL), failed=failed
    )


@router.post("/museums/{source}/import", response_model=Item)
async def museum_import(source: str, request: ImportRequest, svc: Svc) -> Item:
    if source not in svc.importer.sources():
        raise HTTPException(404, f"unknown museum {source!r}")
    try:
        item = await run_in_threadpool(svc.importer.import_one, source, request.source_id)
    except httpx.HTTPError as err:
        raise HTTPException(502, f"{source}: {err}") from err
    if item is None:
        raise HTTPException(404, "not found or not in the public domain")
    return item


@router.post("/museums/{source}/import-search")
def museum_import_search(source: str, request: ImportSearchRequest, svc: Svc) -> dict[str, Any]:
    if source != ALL and source not in svc.importer.sources():
        raise HTTPException(404, f"unknown museum {source!r}")

    def work(job: Job) -> None:
        svc.importer.import_search(source, request.query, request.limit, job)

    job = svc.importer.start_job(f"{source}: {request.query}", work)
    return {"job_id": job.id}


@router.get("/library/packs")
def packs(svc: Svc) -> list[dict[str, Any]]:
    """Themed batches of museum works to add in one go."""
    running = {j.description for j in svc.importer.jobs.values() if not j.finished}
    return [
        {
            "key": p.key,
            "name": p.name,
            "description": p.description,
            "size": p.size,
            "importing": f"pack: {p.key}" in running,
        }
        for p in PACKS
    ]


@router.post("/library/packs/{key}/import")
def pack_import(key: str, svc: Svc) -> dict[str, Any]:
    try:
        found = pack(key)
    except KeyError as err:
        raise HTTPException(404, str(err)) from err
    running = next(
        (
            j
            for j in svc.importer.jobs.values()
            if j.description == f"pack: {key}" and not j.finished
        ),
        None,
    )
    if running is not None:
        return {"job_id": running.id}

    def work(job: Job) -> None:
        import_queries(svc.importer, found.queries, job)

    return {"job_id": svc.importer.start_job(f"pack: {key}", work).id}


class FillRequest(BaseModel):
    rules: PlaylistRules
    count: int = Field(100, ge=1, le=500)


@router.post("/library/fill")
def fill(request: FillRequest, svc: Svc) -> dict[str, Any]:
    """Add museum works a smart playlist with ``rules`` would pick."""
    rules = request.rules
    if rules.favorites_only:
        raise HTTPException(422, "favourites can't be fetched from museums")
    if rules.asks_mine():
        raise HTTPException(422, "the owner's own works can't be fetched from museums")
    if rules.kinds and ItemKind.ARTWORK not in rules.kinds:
        raise HTTPException(422, "only artworks come from museums")
    if rules.sources and not any(s in svc.importer.sources() for s in rules.sources):
        raise HTTPException(422, "the rules allow no museum")

    def work(job: Job) -> None:
        # Szukaj's search for the same choices (Mateusz, 2026-11-07).
        fill_by_search(svc.importer, rules, request.count, job)

    return {"job_id": svc.importer.start_job(f"fill: {request.count}", work).id}


@router.get("/jobs")
def jobs(svc: Svc) -> list[dict[str, Any]]:
    return [vars(j) for j in svc.importer.jobs.values()]


@router.get("/jobs/{job_id}")
def job(job_id: str, svc: Svc) -> dict[str, Any]:
    found = svc.importer.jobs.get(job_id)
    if found is None:
        raise HTTPException(404)
    return vars(found)
