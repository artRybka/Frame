"""The restorer (``frame_server.restorer``): one work from its card by our
own model, the owner's favourites under the threshold from Konfiguracja and
a playlist's from its "…" by it in the background (Mateusz 2026-11-13), and
"Restaurator Pro" from the card, through Google's Batch, within each
person's day (2026-11-26)."""

from __future__ import annotations

import io
from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..ai import AiUnavailable
from ..imaging import artsr
from ..library.hosts import urgent_call
from ..library.models import Item
from ..restorer import LONGEST, NotRestored
from ..service import FrameService
from ..users import User
from .deps import CurrentUser, require_owner, require_token, service
from .library_api import _work
from .playlists_api import _playlist

#: The batches are the owner's; one work from its card is everyone's
#: (Mateusz 2026-11-19).
router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["restorer"])
Owner = [Depends(require_owner)]
Svc = Annotated[FrameService, Depends(service)]


class RestorerView(BaseModel):
    """Konfiguracja's line: the favourites our model would draw (``items``,
    for nothing: ``usd`` 0), those waiting, and the works drawn so far."""

    enabled: bool
    #: Restaurator Pro can draw (Google's key in Konfiguracja).
    pro: bool = False
    items: int
    usd: float
    waiting: int
    restored: int


class ProOrder(BaseModel):
    """A work ordered of Restaurator Pro: whether it was sent now (False:
    it waits already), and how many more its orderer may order today
    (None: no limit)."""

    sent: bool
    left: int | None = None


def _view(svc: FrameService, works: list[Item] | None = None) -> RestorerView:
    """With ``works``, a playlist's line: its works the batch would draw."""
    items, usd = svc.restorer.estimate(works)
    waiting, restored = svc.restorer.counts()
    return RestorerView(
        enabled=svc.restorer.enabled(),
        pro=svc.restorer.pro_enabled(),
        items=items,
        usd=usd,
        waiting=waiting,
        restored=restored,
    )


@router.get("/ai/restorer", response_model=RestorerView, dependencies=Owner)
async def restorer_view(svc: Svc) -> RestorerView:
    return await run_in_threadpool(_view, svc)


@router.post("/ai/restorer/favourites", response_model=RestorerView, dependencies=Owner)
async def restore_favourites(svc: Svc, user: CurrentUser) -> RestorerView:
    """The favourites whose picture is small for the frame drawn again by
    our model in the background."""
    await run_in_threadpool(svc.restorer.order_favourites, user.id)
    return await run_in_threadpool(_view, svc)


def _playlist_works(svc: FrameService, playlist_id: int, user: User) -> list[Item]:
    return svc.library.playlist_items(_playlist(svc, playlist_id, user))


@router.get("/ai/restorer/playlists/{playlist_id}", response_model=RestorerView, dependencies=Owner)
async def restorer_playlist(playlist_id: int, svc: Svc, user: CurrentUser) -> RestorerView:
    """The playlist's line: its works whose picture is small for the frame
    (under ``low_res.LOW_SIDE``) and that our model would draw."""
    works = await run_in_threadpool(_playlist_works, svc, playlist_id, user)
    return await run_in_threadpool(_view, svc, works)


@router.post(
    "/ai/restorer/playlists/{playlist_id}", response_model=RestorerView, dependencies=Owner
)
async def restore_playlist(playlist_id: int, svc: Svc, user: CurrentUser) -> RestorerView:
    """The playlist's works whose picture is small for the frame drawn
    again by our model, one after another in the background (the
    playlist's "…" → "Restauracja dzieł")."""
    works = await run_in_threadpool(_playlist_works, svc, playlist_id, user)
    await run_in_threadpool(svc.restorer.order, works, user.id)
    return await run_in_threadpool(_view, svc, works)


@router.post("/library/items/{item_id:item}/restore", response_model=Item)
async def restore_item(item_id: str, svc: Svc, user: CurrentUser) -> Item:
    """The work's picture drawn again larger by our model and kept in its
    place, in the asker's "Restaurator" (a minute or two on the NAS). 422
    for a work that is not drawn, its detail led by the reason's code."""
    item = await _work(svc, item_id)
    try:
        return await run_in_threadpool(urgent_call(svc.restorer.restore), item, user.id)
    except NotRestored as err:
        raise HTTPException(422, f"{err.code}: {err}") from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"picture unavailable: {err}") from err


class RestorePlan(BaseModel):
    """What the phone draws a work with (Mateusz 2026-11-27: „Wszystko.”,
    the restorer on the iPhone when a card opens): the kind that leads our
    model (0 painting, 1 print, 2 drawing: ``artsr.KINDS``) and how the work
    looks (SigLIP 2's numbers); its picture is ``/restore/source``."""

    kind: int
    look: list[float]


#: The most a phone's drawing may weigh.
DRAWN_BYTES = 12_000_000


@router.get("/library/items/{item_id:item}/restore/plan", response_model=RestorePlan)
async def restore_plan(item_id: str, svc: Svc) -> RestorePlan:
    """How the phone is to draw the work (422 for one that is not drawn)."""
    item = await _work(svc, item_id)
    try:
        await run_in_threadpool(svc.restorer.check, item)
        if svc.restorer.restored(item):
            raise NotRestored("restored", "drawn again already")
        look = await run_in_threadpool(urgent_call(svc.restorer.look), item)
    except NotRestored as err:
        raise HTTPException(422, f"{err.code}: {err}") from err
    except AiUnavailable as err:
        raise HTTPException(503, f"how the work looks is not known: {err}") from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"picture unavailable: {err}") from err
    kind = artsr.KINDS.get(artsr.kind_of(item), 0)
    return RestorePlan(kind=kind, look=[float(v) for v in look])


@router.get("/library/items/{item_id:item}/restore/source")
async def restore_source(item_id: str, svc: Svc) -> Response:
    """The picture our model draws the work from, as the server would
    (``Restorer.source``), losslessly: the phone takes its printed screen
    out, draws it and puts it in its colours itself."""
    item = await _work(svc, item_id)

    def png() -> bytes:
        out = io.BytesIO()
        svc.restorer.source(item).save(out, "PNG", compress_level=1)
        return out.getvalue()

    try:
        data = await run_in_threadpool(urgent_call(png))
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"picture unavailable: {err}") from err
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/library/items/{item_id:item}/restore/drawn", response_model=Item)
async def restore_drawn(
    item_id: str,
    request: Request,
    svc: Svc,
    user: CurrentUser,
    width: Annotated[int, Query(ge=1, le=LONGEST)],
    height: Annotated[int, Query(ge=1, le=LONGEST)],
) -> Item:
    """The phone's drawing of the work (a JPEG, its body), of its source
    ``width`` × ``height``: kept in place of its picture and put in the
    asker's "Restaurator", as ``/restore`` keeps the server's. 422 for a
    work that is not drawn (drawn already: the work as kept)."""
    data = await request.body()
    if len(data) > DRAWN_BYTES:
        raise HTTPException(413, "too large")
    item = await _work(svc, item_id)
    try:
        return await run_in_threadpool(
            svc.restorer.keep_drawn, item, data, (width, height), user.id
        )
    except NotRestored as err:
        raise HTTPException(422, f"{err.code}: {err}") from err
    except ValueError as err:
        raise HTTPException(422, f"not_drawn: {err}") from err


@router.post("/library/items/{item_id:item}/restore/pro", response_model=ProOrder)
async def restore_item_pro(item_id: str, svc: Svc, user: CurrentUser) -> ProOrder:
    """The work sent to Restaurator Pro (Google's model through the Batch
    API, within a day); its orderer is told when it is drawn. 429 past
    their day's limit, 409 without Google's key, 422 for a work that is
    not drawn ("refused: …": the model would not draw it)."""
    item = await _work(svc, item_id)
    today = date.today()
    if svc.users.pro_left(user, today) == 0:
        stored = svc.users.user(user.id) or user
        limit = stored.pro_a_day()
        raise HTTPException(
            429, f"Na dziś to już {limit} {_works(limit)} w Restauracji PRO. Kolejne jutro."
        )
    if not svc.restorer.pro_enabled():
        raise HTTPException(409, "Restauracja PRO potrzebuje klucza Google w Konfiguracji.")
    if svc.library.get(item_id) is None:  # a museum work only looked at: pooled
        item = await run_in_threadpool(svc.importer.add, item.model_copy(update={"pooled": True}))
    try:
        sent = await run_in_threadpool(urgent_call(svc.restorer.order_pro), item, user.id)
    except NotRestored as err:
        raise HTTPException(422, f"{err.code}: {err}") from err
    except AiUnavailable as err:
        raise HTTPException(409, str(err)) from err
    except (httpx.HTTPError, OSError) as err:
        raise HTTPException(502, f"picture unavailable: {err}") from err
    if sent:
        svc.users.ordered_pro(user, today)
    return ProOrder(sent=sent, left=svc.users.pro_left(user, today))


def _works(n: int) -> str:
    """ "dzieło", "dzieła", "dzieł" after ``n``."""
    if n == 1:
        return "dzieło"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "dzieła"
    return "dzieł"
