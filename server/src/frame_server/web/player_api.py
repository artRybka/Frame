"""Now playing, rotation control, frame settings and device status."""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import __version__
from ..library import Item, ItemSummary, PlaylistRules, PlaylistSummary
from ..player import Hold, hold_from
from ..progress import DisplayProgress
from ..schedule import FrameSettings
from ..service import FrameService
from ..status import DeviceStatus
from .deps import require_token, service

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)], tags=["player"])
Svc = Annotated[FrameService, Depends(service)]
STARTED = time.monotonic()


class NowShowing(BaseModel):
    title: str
    description: str
    source: str
    created: str
    preview_url: str
    item: Item | None


class PlayerView(BaseModel):
    playlist: PlaylistSummary | None
    current: NowShowing | None
    upcoming: list[ItemSummary]
    history: list[ItemSummary]
    hold: Hold | None
    last_change_at: str | None
    next_change_at: str | None
    busy: bool
    last_error: str | None
    progress: DisplayProgress


class HoldRequest(BaseModel):
    hold: str | int | None = "forever"


class ServerStatus(BaseModel):
    version: str
    uptime_s: int
    library_count: int
    playlists: int
    jobs_running: int
    palette: str


class StatusView(BaseModel):
    device: DeviceStatus
    server: ServerStatus


def _player_view(svc: FrameService) -> PlayerView:
    player = svc.player
    state, settings = player.state, player.settings
    content = svc.store.current()
    current = None
    if content is not None:
        item_id = content.extra.get("item_id") if content.extra else None
        current = NowShowing(
            title=content.title,
            description=content.description,
            source=content.source,
            created=content.created,
            preview_url=f"/api/previews/{content.file_id}.png",
            item=svc.library.get(str(item_id)) if item_id else None,
        )
    playlist = None
    if settings.playlist_id is not None:
        found = svc.library.playlist(settings.playlist_id)
        playlist = svc.library.playlist_summary(found) if found else None
    history = [svc.library.get(i) for i in reversed(state.history[-12:])]
    return PlayerView(
        playlist=playlist,
        current=current,
        upcoming=[ItemSummary.of(i) for i in player.upcoming(8)],
        history=[ItemSummary.of(i) for i in history if i is not None],
        hold=state.hold,
        last_change_at=state.last_change_at,
        next_change_at=state.next_change_at,
        busy=player.busy,
        last_error=state.last_error,
        progress=svc.progress.view(),
    )


@router.get("/player", response_model=PlayerView)
def player(svc: Svc) -> PlayerView:
    return _player_view(svc)


@router.post("/player/next", status_code=202)
def next_picture(svc: Svc) -> dict[str, Any]:
    svc.player.set_hold(None)
    svc.background(svc.player.next("manual"))
    return {"accepted": True}


@router.post("/player/previous", status_code=202)
def previous_picture(svc: Svc) -> dict[str, Any]:
    svc.player.set_hold(None)
    svc.background(svc.player.previous())
    return {"accepted": True}


@router.post("/player/hold", response_model=PlayerView)
def hold(request: HoldRequest, svc: Svc) -> PlayerView:
    svc.player.set_hold(hold_from(request.hold))
    return _player_view(svc)


@router.delete("/player/hold", response_model=PlayerView)
def release(svc: Svc) -> PlayerView:
    svc.player.set_hold(None)
    return _player_view(svc)


@router.get("/settings", response_model=FrameSettings)
def get_settings(svc: Svc) -> FrameSettings:
    return svc.player.settings


@router.put("/settings", response_model=FrameSettings)
async def put_settings(settings: FrameSettings, svc: Svc) -> FrameSettings:
    player = svc.player
    old = player.settings
    saved = player.save_settings(settings)
    if old.wikiart and not saved.wikiart:
        # WikiArt was only for tests: its copies go with the switch.
        _, tests = svc.library.query(PlaylistRules(sources=["wikiart"]), include_excluded=True)
        for item in tests:
            svc.library.delete(item.id)
            svc.images.remove(item)
    if player.needs_restyle(old, saved):
        # New framing should show up now, not at the next scheduled change.
        svc.background(player.restyle())
    return saved


@router.get("/status", response_model=StatusView)
async def status(svc: Svc, refresh: bool = False) -> StatusView:
    device = await svc.status.refresh() if refresh else svc.status.status
    return StatusView(
        device=device,
        server=ServerStatus(
            version=__version__,
            uptime_s=int(time.monotonic() - STARTED),
            library_count=svc.library.count(),
            playlists=len(svc.library.playlists()),
            jobs_running=sum(not j.finished for j in svc.importer.jobs.values()),
            palette=svc.palette.name,
        ),
    )
