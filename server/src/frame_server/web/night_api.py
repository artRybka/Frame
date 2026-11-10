"""The night's tasks started by day (Konfiguracja → Zadania nocne, Mateusz
2026-11-10): one of them or the whole night, and how each last went."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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
