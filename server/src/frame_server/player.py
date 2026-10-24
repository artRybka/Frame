"""What the frame shows and when: playlist rotation, history, holds."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .device import MdcError
from .imaging import PRESETS, RenderSettings
from .library import Item, ItemKind, PlaylistRules
from .schedule import FrameSettings, Mode, in_quiet_hours, next_change

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

SETTINGS_KEY = "settings"
STATE_KEY = "player"
HISTORY_MAX = 50


def utcnow() -> datetime:
    return datetime.now(UTC)


class Hold(BaseModel):
    """Keep the current picture: until a moment, or until unpinned."""

    until: str | None = None
    forever: bool = False

    def active(self, now: datetime) -> bool:
        return self.forever or (self.until is not None and datetime.fromisoformat(self.until) > now)


class PlayerState(BaseModel):
    current_item_id: str | None = None
    queue: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    hold: Hold | None = None
    last_change_at: str | None = None
    next_change_at: str | None = None
    last_error: str | None = None


def hold_from(spec: str | int | None) -> Hold | None:
    """``"next"``/None: until the next scheduled change; ``"forever"``;
    or a number of minutes."""
    if spec in (None, "", "next"):
        return None
    if spec == "forever":
        return Hold(forever=True)
    minutes = int(spec)
    return Hold(until=(utcnow() + timedelta(minutes=minutes)).isoformat(timespec="seconds"))


def caption_for(item: Item) -> str:
    if item.kind == ItemKind.PHOTO:
        parts = [item.date_text, item.photo.caption if item.photo else ""]
        return " · ".join(p for p in parts if p)
    parts = [item.artist, item.title]
    text = " — ".join(p for p in parts if p)
    return f"{text}, {item.date_text}" if item.date_text else text


class Player:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self.library = service.library
        self._lock = asyncio.Lock()
        self.busy = False

    # -- persisted settings and state --------------------------------------

    @property
    def settings(self) -> FrameSettings:
        return FrameSettings.model_validate(self.library.get_state(SETTINGS_KEY, {}))

    def save_settings(self, settings: FrameSettings) -> FrameSettings:
        old = self.settings
        self.library.set_state(SETTINGS_KEY, settings.model_dump(mode="json"))
        if (old.mode, old.playlist_id, old.shuffle) != (
            settings.mode,
            settings.playlist_id,
            settings.shuffle,
        ):
            state = self.state
            state.queue = []
            self._save_state(state)
        self.reschedule()
        return settings

    @property
    def state(self) -> PlayerState:
        return PlayerState.model_validate(self.library.get_state(STATE_KEY, {}))

    def _save_state(self, state: PlayerState) -> None:
        self.library.set_state(STATE_KEY, state.model_dump(mode="json"))

    def reschedule(self) -> None:
        state = self.state
        base = datetime.fromisoformat(state.last_change_at) if state.last_change_at else utcnow()
        state.next_change_at = next_change(
            base, self.settings, self.service.status.on_battery
        ).isoformat(timespec="seconds")
        self._save_state(state)

    # -- choosing pictures ---------------------------------------------------

    def candidates(self, settings: FrameSettings | None = None) -> list[Item]:
        settings = settings or self.settings
        if settings.mode == Mode.ALBUM:
            return self.library.query(PlaylistRules(kinds=[ItemKind.PHOTO]), sort="recent")[1]
        if settings.playlist_id is not None:
            playlist = self.library.playlist(settings.playlist_id)
            if playlist is not None:
                return self.library.playlist_items(playlist)
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK, ItemKind.OWN])
        return self.library.query(rules, sort="recent")[1]

    def _refill(self, state: PlayerState, settings: FrameSettings) -> None:
        items = self.candidates(settings)
        cutoff = (utcnow() - timedelta(days=settings.avoid_repeat_days)).isoformat()
        fresh = [i for i in items if not i.last_shown_at or i.last_shown_at < cutoff]
        pool = fresh or items
        ids = [i.id for i in pool if i.id != state.current_item_id] or [i.id for i in pool]
        if settings.shuffle:
            random.shuffle(ids)
        state.queue = ids

    def _pop_next(self, state: PlayerState, settings: FrameSettings) -> Item | None:
        for _ in range(2):
            while state.queue:
                item = self.library.get(state.queue.pop(0))
                if item is not None and not item.excluded:
                    return item
            self._refill(state, settings)
        return None

    def upcoming(self, limit: int = 8) -> list[Item]:
        state, settings = self.state, self.settings
        if not state.queue:
            self._refill(state, settings)
            self._save_state(state)
        items = (self.library.get(i) for i in state.queue[:limit])
        return [i for i in items if i is not None]

    # -- showing -------------------------------------------------------------

    def render_settings(self, item: Item, settings: FrameSettings) -> RenderSettings:
        pres = settings.photo if item.kind == ItemKind.PHOTO else settings.art
        base = PRESETS.get(pres.preset, PRESETS["painting"]).model_copy(deep=True)
        base.layout.fit = pres.fit
        base.layout.margin = pres.margin
        base.layout.orientation = settings.orientation
        base.layout.rotation = settings.rotation
        base.caption = caption_for(item) if pres.label else None
        return base

    async def show(self, item: Item, reason: str, hold: Hold | None = None) -> None:
        """Render ``item``, publish it and tell the panel. Never raises."""
        async with self._lock:
            state = self.state
            settings = self.settings

            async def work() -> None:
                await self._publish(item, settings)
                if state.current_item_id and state.current_item_id != item.id:
                    state.history = [*state.history, state.current_item_id][-HISTORY_MAX:]
                state.current_item_id = item.id
                state.hold = hold
                now = utcnow()
                state.last_change_at = now.isoformat(timespec="seconds")
                state.next_change_at = next_change(
                    now, settings, self.service.status.on_battery
                ).isoformat(timespec="seconds")
                state.last_error = None
                self.library.record_shown(item.id, reason)
                self._save_state(state)
                await self._push(state)

            await self._guarded(item.id, state, work)

    def needs_restyle(self, old: FrameSettings, new: FrameSettings) -> bool:
        """Whether a settings change alters how the current picture is drawn."""
        state = self.state
        item = self.library.get(state.current_item_id) if state.current_item_id else None
        if item is None:
            return False
        kind = "photo" if item.kind == ItemKind.PHOTO else "art"
        return (old.orientation, old.rotation, getattr(old, kind)) != (
            new.orientation,
            new.rotation,
            getattr(new, kind),
        )

    async def restyle(self) -> None:
        """Redraw the current picture with the current presentation settings.

        The same picture, framed differently: schedule, hold, history and
        show counts stay as they are. Never raises.
        """
        async with self._lock:
            state = self.state
            item = self.library.get(state.current_item_id) if state.current_item_id else None
            if item is None:
                return
            settings = self.settings

            async def work() -> None:
                await self._publish(item, settings)
                state.last_error = None
                self._save_state(state)
                await self._push(state)

            await self._guarded(item.id, state, work)

    async def show_still(
        self, png: bytes, *, preview_png: bytes, title: str, description: str, hold: Hold
    ) -> None:
        """Put a ready-made panel image (e.g. the calibration chart) on the frame
        and hold it. The current item stays current, so ``resume`` returns to it.
        """
        async with self._lock:
            state = self.state

            async def work() -> None:
                await run_in_threadpool(
                    self.service.store.publish,
                    png,
                    "png",
                    preview_png=preview_png,
                    title=title,
                    description=description,
                    source="frame",
                    render={"raw": True},
                )
                state.hold = hold
                state.last_error = None
                self._save_state(state)
                await self._push(state)

            await self._guarded(title, state, work)

    async def resume(self) -> None:
        """Back to the rotation after ``show_still``: the current picture again
        (redrawn, e.g. with a new palette), or the next one if there is none."""
        self.set_hold(None)
        if self.state.current_item_id and self.library.get(self.state.current_item_id):
            await self.restyle()
        else:
            await self.next("resume")

    async def _publish(self, item: Item, settings: FrameSettings) -> None:
        path = await run_in_threadpool(self.service.images.ensure_image, item)
        data = await run_in_threadpool(path.read_bytes)
        await run_in_threadpool(
            self.service.prepare,
            data,
            self.render_settings(item, settings),
            title=item.title,
            description=caption_for(item),
            source=item.source,
            extra={"item_id": item.id, "kind": item.kind.value},
        )

    async def _push(self, state: PlayerState) -> None:
        if not self.service.device_configured:
            return
        outcome = await self.service.push_current(wait=120)
        if not outcome.fetched:
            state.last_error = outcome.message
            self._save_state(state)

    async def _guarded(
        self, label: str, state: PlayerState, work: Callable[[], Awaitable[None]]
    ) -> None:
        self.busy = True
        try:
            await work()
        except (MdcError, OSError, ValueError, RuntimeError) as err:
            log.warning("showing %s failed: %s", label, err)
            state.last_error = str(err)
            self._save_state(state)
        except Exception as err:  # keep the scheduler alive whatever happens
            log.exception("showing %s failed", label)
            state.last_error = str(err)
            self._save_state(state)
        finally:
            self.busy = False

    async def next(self, reason: str = "manual") -> Item | None:
        state, settings = self.state, self.settings
        item = self._pop_next(state, settings)
        self._save_state(state)
        if item is not None:
            await self.show(item, reason)
        return item

    async def previous(self) -> Item | None:
        state = self.state
        while state.history:
            item = self.library.get(state.history.pop())
            if item is None:
                continue
            if state.current_item_id:
                state.queue.insert(0, state.current_item_id)
            state.current_item_id = None  # show() must not push it to history
            self._save_state(state)
            await self.show(item, "previous")
            return item
        return None

    def set_hold(self, hold: Hold | None) -> PlayerState:
        state = self.state
        state.hold = hold
        self._save_state(state)
        return state

    def note_external(self, hold: Hold | None) -> None:
        """An upload from the app replaced the picture outside the playlist."""
        state = self.state
        if state.current_item_id:
            state.history = [*state.history, state.current_item_id][-HISTORY_MAX:]
        state.current_item_id = None
        state.hold = hold
        now = utcnow()
        state.last_change_at = now.isoformat(timespec="seconds")
        state.next_change_at = next_change(
            now, self.settings, self.service.status.on_battery
        ).isoformat(timespec="seconds")
        self._save_state(state)

    # -- scheduler -----------------------------------------------------------

    async def tick(self) -> None:
        if self.busy:
            return
        state, settings = self.state, self.settings
        now = utcnow()
        if state.hold is not None:
            if state.hold.active(now):
                return
            # A timed hold is over: the rotation takes over now (outside quiet
            # hours), not at the change that was scheduled before the hold.
            state.hold = None
            state.next_change_at = now.isoformat(timespec="seconds")
            self._save_state(state)
        if state.next_change_at is None:
            self.reschedule()
            return
        if now < datetime.fromisoformat(state.next_change_at) or in_quiet_hours(now, settings):
            return
        await self.next("schedule")

    async def run(self, period: float = 30.0) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(period)
