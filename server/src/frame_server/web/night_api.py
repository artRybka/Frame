"""The night's tasks started by day (Konfiguracja → Zadania nocne, Mateusz
2026-11-10): one of them or the whole night, and how each last went."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..library.models import ItemSummary
from ..night import NightQueue
from ..service import FrameService
from .deps import require_owner, service

router = APIRouter(prefix="/api/night", dependencies=[Depends(require_owner)], tags=["night"])
Svc = Annotated[FrameService, Depends(service)]


class NightStart(BaseModel):
    #: The tasks' names; none for the whole night.
    tasks: list[str] | None = None


def _queue(svc: FrameService) -> NightQueue:
    if svc.night is None:
        raise HTTPException(503, "serwer nie prowadzi nocnych zadań")
    return svc.night


@router.get("")
def night_tasks(svc: Svc) -> dict[str, Any]:
    return _queue(svc).view()


@router.post("/run")
def start_tasks(start: NightStart, svc: Svc) -> dict[str, Any]:
    queue = _queue(svc)
    try:
        run = queue.start(start.tasks)
    except ValueError as err:
        raise HTTPException(404, f"nie ma takich zadań: {err}") from err
    if run is None:
        raise HTTPException(409, "zadania już trwają")
    return queue.view()


@router.post("/stop")
def stop_tasks(svc: Svc) -> dict[str, Any]:
    queue = _queue(svc)
    queue.cancel()
    return queue.view()


# -- what the tidying of copies changed (Mateusz 2026-11-11) -----------------------------

#: What each change made of the picture, in Polish.
RELATION_NAMES = {
    "copy": "Kopia tego samego dzieła",
    "detail": "Detal dzieła",
    "scene": "Zdjęcie dzieła na ścianie",
}
#: Changes listed of each kind, the newest.
CHANGES_LISTED = 200


class Change(BaseModel):
    """One change: ``a`` made a copy, a detail or a photograph of ``b``."""

    at: str
    a: ItemSummary
    b: ItemSummary
    #: "copy", "detail" or "scene", and its Polish name.
    relation: str
    relation_name: str
    #: "pictures", "hash" or "judge" (the doubtful ones).
    by: str
    #: What the judge and its critic said (the judge's changes only).
    why: str = ""
    critic: str = ""


class Changes(BaseModel):
    #: Settled by the judge: the pictures could not tell.
    doubtful: list[Change]
    #: Settled by the pictures.
    sure: list[Change]


def _changes(svc: FrameService) -> Changes:
    doubtful: list[Change] = []
    sure: list[Change] = []
    for entry in svc.twins.log.entries():
        listed = doubtful if entry.get("by") == "judge" else sure
        if len(listed) >= CHANGES_LISTED:
            continue
        a = svc.library.get(str(entry.get("a") or ""))
        b = svc.library.get(str(entry.get("b") or ""))
        relation = str(entry.get("relation") or "")
        if a is None or b is None or relation not in RELATION_NAMES:
            continue
        listed.append(
            Change(
                at=str(entry.get("at") or ""),
                a=ItemSummary.of(a),
                b=ItemSummary.of(b),
                relation=relation,
                relation_name=RELATION_NAMES[relation],
                by=str(entry.get("by") or ""),
                why=str(entry.get("why") or ""),
                critic=str(entry.get("critic") or ""),
            )
        )
    return Changes(doubtful=doubtful, sure=sure)


class Apart(BaseModel):
    a: str
    b: str


@router.get("/changes", response_model=Changes)
async def changes(svc: Svc) -> Changes:
    """What the tidying of copies changed, newest first: the judge's (the
    doubtful ones) and the pictures'."""
    return await run_in_threadpool(_changes, svc)


@router.post("/changes/apart", response_model=Changes)
async def keep_apart(apart: Apart, svc: Svc) -> Changes:
    """ "To nie to samo": the two pictures apart again, for good."""
    if not await run_in_threadpool(svc.twins.separate, apart.a, apart.b):
        raise HTTPException(404, "nie ma takiego dzieła")
    return await run_in_threadpool(_changes, svc)
