"""Now playing, rotation control, frame settings and device status."""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import build_version
from ..ai import PolishText
from ..library import Item, ItemSummary, PlaylistRules, PlaylistSummary
from ..library.museums import TEST_LICENCE
from ..player import Hold, hold_from, origin_of
from ..progress import DisplayProgress
from ..schedule import FrameSettings
from ..service import FrameService
from ..status import DeviceStatus
from ..store import ContentInfo
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
    #: The work's Polish title and texts, when they are on and written.
    polish: PolishText | None = None


class Delivery(BaseModel):
    """Whether ``current`` is on the panel. ``shown``: it downloaded it;
    ``sending``: on its way; ``waiting``: the panel is asleep or did not
    answer, the picture goes out when it wakes; ``failed``: sent, but never
    downloaded; ``unknown``: no panel, or no download seen yet."""

    state: Literal["shown", "sending", "waiting", "failed", "unknown"]
    #: What the panel shows instead, when not ``current``.
    on_frame: NowShowing | None = None
    shown_at: str | None = None
    failed_at: str | None = None
    failure: str | None = None  # "timeout" or "error"
    message: str = ""
    #: ``waiting`` in deep sleep (Wi-Fi off): HH:MM of the panel's alarm,
    #: and the moment (ISO) it rings.
    asleep_until: str | None = None
    asleep_until_at: str | None = None
    #: Economy mode: a wake (ISO) the panel did not show up for.
    missed_wake_at: str | None = None
    #: ``waiting`` with the Wi-Fi off (economy, quiet hours): only the alarm
    #: or the button wakes it. False: asleep with the Wi-Fi on (online).
    deep_sleep: bool = False
    #: ``waiting`` with the Wi-Fi gone off by itself (unplugged, the panel
    #: sleeps at once without it): the button wakes it.
    wifi_lost: bool = False
    #: ``waiting`` for good: the panel does not run the app and the server
    #: cannot build it (no Samsung certificates).
    no_app: bool = False


class ShownMark(BaseModel):
    """When a picture in the history went on the frame, and who put it there."""

    at: str
    origin: str  # schedule | app


class PlayerView(BaseModel):
    playlist: PlaylistSummary | None
    current: NowShowing | None
    upcoming: list[ItemSummary]
    #: Those of ``upcoming`` added from the app ("Dodaj do kolejki").
    queued: list[str]
    history: list[ItemSummary]
    #: By item id, for those of ``history`` the server has a record of.
    history_marks: dict[str, ShownMark] = {}
    hold: Hold | None
    last_change_at: str | None
    last_change_origin: str | None = None
    next_change_at: str | None
    busy: bool
    last_error: str | None
    progress: DisplayProgress
    delivery: Delivery


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


def _now_showing(svc: FrameService, content: ContentInfo) -> NowShowing:
    item_id = content.extra.get("item_id") if content.extra else None
    item = svc.library.get(str(item_id)) if item_id else None
    return NowShowing(
        title=content.title,
        description=content.description,
        source=content.source,
        created=content.created,
        preview_url=f"/api/previews/{content.file_id}.png",
        item=item,
        polish=svc.pl_text.text(item) if item else None,
    )


def _summary(svc: FrameService, item: Item) -> ItemSummary:
    """For "Teraz": with the work's Polish title, once it has one."""
    summary = ItemSummary.of(item)
    if (text := svc.pl_text.text(item)) is not None:
        summary.title_pl = text.title
    return summary


def _delivery(svc: FrameService, content: ContentInfo | None) -> Delivery:
    record = svc.store.delivery()
    shown = record.shown
    if content is None or not svc.device_configured:
        return Delivery(state="unknown")
    if shown is not None and shown.file_id == content.file_id:
        return Delivery(state="shown", shown_at=record.shown_at)
    if not svc.app.active and svc.app.package() is None:
        # No app to start: nothing reaches the frame until the certificates do.
        on_frame = _now_showing(svc, shown) if shown is not None else None
        return Delivery(state="waiting", on_frame=on_frame, no_app=True)
    if shown is None:
        return Delivery(state="unknown")
    on_frame = _now_showing(svc, shown)
    common: dict[str, Any] = {"on_frame": on_frame, "shown_at": record.shown_at}
    if svc.player.busy or svc.progress.active:
        return Delivery(state="sending", **common)
    if svc.power.state.pending_push:
        until = svc.app.wakes_at()
        tz = svc.player.settings.tz()
        return Delivery(
            state="waiting",
            asleep_until=until.astimezone(tz).strftime("%H:%M") if until else None,
            asleep_until_at=until.isoformat(timespec="seconds") if until else None,
            missed_wake_at=svc.app.state.missed_wake,
            deep_sleep=svc.app.deep_asleep(),
            wifi_lost=svc.app.deep_asleep() and svc.app.state.wifi_lost,
            **common,
        )
    failed = record.failed_file_id == content.file_id
    return Delivery(
        state="failed",
        failed_at=record.failed_at if failed else None,
        failure=record.failure if failed else None,
        message=record.message if failed else "",
        **common,
    )


def _player_view(svc: FrameService) -> PlayerView:
    player = svc.player
    state, settings = player.state, player.settings
    content = svc.store.current()
    current = _now_showing(svc, content) if content is not None else None
    playlist = None
    if settings.playlist_id is not None:
        found = svc.library.playlist(settings.playlist_id)
        playlist = svc.library.playlist_summary(found) if found else None
    history = [i for i in (svc.library.get(i) for i in reversed(state.history[-12:])) if i]
    shown = svc.library.last_shown([i.id for i in history])
    return PlayerView(
        playlist=playlist,
        current=current,
        upcoming=[_summary(svc, i) for i in player.upcoming(8)],
        queued=state.requested,
        history=[_summary(svc, i) for i in history],
        history_marks={
            i: ShownMark(at=at, origin=origin_of(reason))
            for i, (at, reason) in shown.items()
            if reason
        },
        hold=state.hold,
        last_change_at=state.last_change_at,
        last_change_origin=state.last_change_origin,
        next_change_at=state.next_change_at,
        busy=player.busy,
        last_error=state.last_error,
        progress=svc.progress.view(),
        delivery=_delivery(svc, content),
    )


@router.get("/player", response_model=PlayerView)
def player(svc: Svc) -> PlayerView:
    return _player_view(svc)


@router.post("/player/next", status_code=202)
async def next_picture(svc: Svc) -> dict[str, Any]:
    svc.player.set_hold(None)
    svc.background(svc.player.next("manual"))
    return {"accepted": True}


@router.post("/player/previous", status_code=202)
async def previous_picture(svc: Svc) -> dict[str, Any]:
    svc.player.set_hold(None)
    svc.background(svc.player.previous())
    return {"accepted": True}


@router.delete("/player/queue/{item_id}", response_model=PlayerView)
async def dequeue(item_id: str, svc: Svc) -> PlayerView:
    """Take back a work added with "Dodaj do kolejki"."""
    svc.player.dequeue(item_id)
    svc.background(svc.player.render_ahead())
    return _player_view(svc)


@router.post("/player/skip/{item_id}", response_model=PlayerView)
async def skip(item_id: str, svc: Svc) -> PlayerView:
    """The picture waiting in the queue ("Pomiń") is not shown this round."""
    svc.player.skip(item_id)
    svc.background(svc.player.render_ahead())
    return _player_view(svc)


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
    svc.power.publish_status()  # a mode the sleeping frame takes on later
    if old.wikiart and not saved.wikiart:
        # WikiArt was only for tests: its copies go with the switch.
        _, tests = svc.library.query(PlaylistRules(sources=["wikiart"]), include_excluded=True)
        for item in tests:
            svc.library.delete(item.id)
            svc.images.remove(item)
    if old.ignore_term and not saved.ignore_term:
        # So were the works still protected in the EU.
        _, found = svc.library.query(PlaylistRules(sources=["europeana"]), include_excluded=True)
        for item in found:
            if item.license.startswith(TEST_LICENCE):
                svc.library.delete(item.id)
                svc.images.remove(item)
    if player.needs_restyle(old, saved):
        # The screen was turned: the picture on it is redrawn to match.
        svc.background(player.restyle())
    elif player.presentation_changed(old, saved):
        # The picture on the frame stays; the next one is drawn the new way.
        svc.background(player.render_ahead())
    return saved


@router.get("/status", response_model=StatusView)
async def status(svc: Svc, refresh: bool = False) -> StatusView:
    if refresh:
        await svc.status.refresh()
    svc.power.publish_status()  # whether the app is silent changes with the clock
    device = svc.status.status
    return StatusView(
        device=device,
        server=ServerStatus(
            version=build_version(),
            uptime_s=int(time.monotonic() - STARTED),
            library_count=svc.library.count(),
            playlists=len(svc.library.playlists()),
            jobs_running=sum(not j.finished for j in svc.importer.jobs.values()),
            palette=svc.palette.name,
        ),
    )
