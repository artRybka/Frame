"""What the frame shows and when: playlist rotation, history, holds."""

from __future__ import annotations

import asyncio
import logging
import random
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .device import MdcError
from .imaging import PRESETS, RenderSettings
from .imaging.grids import MAX_PHOTOS, MIN_PHOTOS
from .imaging.layout import Fit
from .imaging.text import TextBlock
from .library import Item, ItemKind, Job, Playlist, PlaylistKind, PlaylistRules
from .library.museums import MUSEUMS, Kind
from .library.seed import PACKS, theme_of_the_day
from .schedule import FrameSettings, Mode, in_quiet_hours, next_change

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

SETTINGS_KEY = "settings"
STATE_KEY = "player"
HISTORY_MAX = 50
#: Next pictures whose originals are downloaded ahead of their turn.
PREFETCH = 3
#: When no picture can be shown (offline, nothing cached), try again after this.
RETRY_AFTER = timedelta(minutes=15)
#: Works picked by the server for the default rotation (ids, oldest first).
SUGGESTIONS_KEY = "suggestions"
#: Set once the museum works imported before the catalogue are gone.
RESET_KEY = "library_reset"
#: A rotation with fewer pictures not shown lately asks museums for more,
#: up to ``POOL_SIZE``; Suggestions remember at most ``POOL_MAX`` works.
POOL_LOW = 8
POOL_SIZE = 24
POOL_MAX = 80
#: Suggestions: least suitability for e-paper.
SUGGESTION_SUITABILITY = 0.5
#: Artists of the owner's taste asked for when topping up Suggestions.
TASTE_ARTISTS = 6
#: The catalogue grows by this many works at a time, at most every
#: ``CATALOGUE_EVERY`` (gently for the museums' APIs).
CATALOGUE_BATCH = 300
CATALOGUE_EVERY = timedelta(hours=1)
CATALOGUE_KINDS: tuple[Kind, ...] = ("painting", "print", "drawing", "poster")
#: Works hardly visible on e-paper are not worth a place in the catalogue.
CATALOGUE_SUITABILITY = 0.25


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
    current_group: list[str] = Field(default_factory=list)  # MULTI: the other photos shown
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


def text_block_for(item: Item) -> TextBlock:
    """What the DESCRIPTION mode prints on the mat."""
    if item.kind == ItemKind.PHOTO:
        info = item.photo
        title = (info.caption if info and info.caption else "") or item.title
        when = item.date_text or (info.taken_at[:10] if info and info.taken_at else "")
        who = info.contributor if info and info.contributor else ""
        return TextBlock(title=title, meta=[m for m in (when, who) if m])
    detail = " · ".join(p for p in (item.date_text, item.medium) if p)
    body = item.description or ", ".join(p for p in (item.museum, item.credit) if p)
    return TextBlock(title=item.title, meta=[m for m in (item.artist, detail) if m], body=body)


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

    def unqueue(self, item_id: str) -> None:
        """Forget a work already queued, e.g. one taken out of the playlist."""
        state = self.state
        if item_id in state.queue:
            state.queue = [i for i in state.queue if i != item_id]
            self._save_state(state)

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
        playlist = self.playlist(settings)
        if playlist is not None:
            return self.library.playlist_items(playlist)
        # Suggestions, with the owner's own works; until the server has
        # picked any, the whole library.
        suggested = [i for i in self.suggestions() if not i.excluded]
        own = self.library.query(PlaylistRules(kinds=[ItemKind.OWN]))[1]
        if suggested:
            return suggested + own
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK, ItemKind.OWN])
        return self.library.query(rules, sort="recent")[1]

    def playlist(self, settings: FrameSettings | None = None) -> Playlist | None:
        """The playlist the frame plays; None for Suggestions."""
        settings = settings or self.settings
        if settings.playlist_id is None:
            return None
        return self.library.playlist(settings.playlist_id)

    def suggestions(self) -> list[Item]:
        ids = self.library.get_state(SUGGESTIONS_KEY, [])
        return [i for i in (self.library.get(item_id) for item_id in ids) if i is not None]

    def fresh(self, items: list[Item], settings: FrameSettings | None = None) -> list[Item]:
        """Those of ``items`` not shown within the no-repeat period."""
        settings = settings or self.settings
        cutoff = (utcnow() - timedelta(days=settings.avoid_repeat_days)).isoformat()
        return [i for i in items if not i.last_shown_at or i.last_shown_at < cutoff]

    def taste(self) -> list[str]:
        """Artists the owner likes, most liked first: favourites count most,
        then works kept in the library (not the ones the server picked)."""
        scores: Counter[str] = Counter()
        for item in self.library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]))[1]:
            if item.artist:
                scores[item.artist] += 3 * item.favorite + (not item.pooled)
        return [artist for artist, score in scores.most_common(TASTE_ARTISTS) if score > 0]

    def _refill(self, state: PlayerState, settings: FrameSettings) -> None:
        items = self.candidates(settings)
        pool = self.fresh(items, settings) or items
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

    # -- boards of several photos (MULTI) ------------------------------------

    @staticmethod
    def multi(item: Item, settings: FrameSettings) -> bool:
        return item.kind == ItemKind.PHOTO and settings.photo.fit == Fit.MULTI

    def board(
        self,
        item: Item,
        state: PlayerState,
        settings: FrameSettings,
        keep: list[str] | None = None,
    ) -> list[Item]:
        """The photos shown with ``item``: ``item`` alone unless photos are
        shown several to a board. ``keep`` (a redraw) are the ones shown with
        it before; missing photos are taken from the queue (removed from
        it), then from the rest of the playlist."""
        if not self.multi(item, settings):
            return [item]
        pres = settings.photo
        kept = [i for i in (self.library.get(x) for x in keep or []) if i and not i.excluded]
        if pres.multi_random:
            count = len(kept) + 1 if kept else random.randint(MIN_PHOTOS, MAX_PHOTOS)
        else:
            count = pres.multi_count
        board = [item, *(i for i in kept if i.id != item.id)][:count]
        taken = {i.id for i in board}
        for item_id in list(state.queue):
            if len(board) >= count:
                break
            other = self.library.get(item_id) if item_id not in taken else None
            if other is not None and other.kind == ItemKind.PHOTO and not other.excluded:
                state.queue.remove(item_id)
                board.append(other)
                taken.add(item_id)
        if len(board) < count:
            rest = [
                i
                for i in self.candidates(settings)
                if i.kind == ItemKind.PHOTO and not i.excluded and i.id not in taken
            ]
            random.shuffle(rest)
            board += rest[: count - len(board)]
        return board

    def preview_board(self, item: Item, settings: FrameSettings) -> list[Item]:
        """The board a preview of ``item`` shows: the one on the frame if
        ``item`` is current, else the photos that would join it next."""
        state = self.state
        keep = state.current_group if state.current_item_id == item.id else None
        return self.board(item, state, settings, keep)  # state is a copy: nothing is taken

    # -- showing -------------------------------------------------------------

    def render_settings(self, item: Item, settings: FrameSettings) -> RenderSettings:
        pres = settings.photo if item.kind == ItemKind.PHOTO else settings.art
        base = PRESETS.get(pres.preset, PRESETS["painting"]).model_copy(deep=True)
        base.layout.fit = pres.fit
        base.layout.mat = pres.mat
        base.layout.margin = pres.margin
        base.layout.orientation = settings.orientation
        base.layout.rotation = settings.rotation
        if not pres.multi_random:
            base.layout.grid = pres.multi_grid
        framing = item.framing.get(settings.orientation.value)
        if framing is not None:
            base.layout.crop = framing.fill
            base.layout.details = framing.details
            base.layout.detail = framing.detail
            base.layout.fit_crop = framing.fit
        if pres.fit == Fit.DESCRIPTION:
            base.text = text_block_for(item)
        base.caption = caption_for(item) if pres.label else None
        return base

    async def show(self, item: Item, reason: str, hold: Hold | None = None) -> None:
        """Render ``item``, publish it and tell the panel. Never raises."""
        async with self._lock:
            state = self.state
            settings = self.settings

            board = self.board(item, state, settings)

            async def work() -> None:
                await self._publish(board, settings)
                if state.current_item_id and state.current_item_id != item.id:
                    state.history = [*state.history, state.current_item_id][-HISTORY_MAX:]
                state.current_item_id = item.id
                state.current_group = [i.id for i in board[1:]]
                state.hold = hold
                now = utcnow()
                state.last_change_at = now.isoformat(timespec="seconds")
                state.next_change_at = next_change(
                    now, settings, self.service.status.on_battery
                ).isoformat(timespec="seconds")
                state.last_error = None
                for shown in board:
                    self.library.record_shown(shown.id, reason)
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
            board = self.board(item, state, settings, keep=state.current_group)

            async def work() -> None:
                await self._publish(board, settings)
                state.current_group = [i.id for i in board[1:]]
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

    async def _publish(self, board: list[Item], settings: FrameSettings) -> None:
        """Render the picture (or, MULTI, the board of photos) and publish it."""
        item = board[0]
        images = []
        for shown in board:
            path = await run_in_threadpool(self.service.images.ensure_image, shown)
            images.append(await run_in_threadpool(path.read_bytes))
        extra: dict[str, object] = {"item_id": item.id, "kind": item.kind.value}
        if len(board) > 1:
            extra["item_ids"] = [i.id for i in board]
        await run_in_threadpool(
            self.service.prepare,
            images if self.multi(item, settings) else images[0],
            self.render_settings(item, settings),
            title=item.title,
            description=caption_for(item),
            source=item.source,
            extra=extra,
            seed=",".join(i.id for i in board),
        )

    async def _push(self, state: PlayerState) -> None:
        if not self.service.device_configured:
            raise RuntimeError("panel not configured (FRAME_DEVICE_HOST / FRAME_DEVICE_PIN)")
        outcome = await self.service.push_current(wait=120)
        if not outcome.fetched:
            log.warning("%s (%s)", outcome.message, outcome.content_url)
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
        item = await self._pop_ready(state, settings)
        if item is None and state.last_error:
            state.next_change_at = (utcnow() + RETRY_AFTER).isoformat(timespec="seconds")
        self._save_state(state)
        if item is not None:
            await self.show(item, reason)
            await self.prefetch()
        return item

    async def _pop_ready(self, state: PlayerState, settings: FrameSettings) -> Item | None:
        """The next picture whose original is at hand. One that cannot be
        downloaded now (no internet, museum down) goes to the back of the
        queue and the first one already cached takes its turn."""
        item = self._pop_next(state, settings)
        if item is None:
            return None
        images = self.service.images
        try:
            await run_in_threadpool(images.ensure_image, item)
            return item
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.warning("original of %s unavailable: %s", item.id, err)
            state.last_error = f"{item.title or item.id}: {err}"
        for item_id in state.queue:
            cached = self.library.get(item_id)
            if cached is not None and not cached.excluded and images.has_image(cached):
                state.queue.remove(item_id)
                state.queue.append(item.id)
                return cached
        state.queue.append(item.id)
        return None

    async def prefetch(self) -> None:
        """Download the originals of the next pictures now, so that a change
        needs no internet, then trim the cache. Never raises."""
        images = self.service.images
        for item in self.upcoming(PREFETCH):
            if images.has_image(item):
                continue
            try:
                await run_in_threadpool(images.ensure_image, item)
            except (httpx.HTTPError, OSError, ValueError) as err:
                log.info("prefetch of %s failed: %s", item.id, err)
        try:
            await run_in_threadpool(self.trim_cache)
        except OSError as err:
            log.warning("trimming the image cache failed: %s", err)
        self.top_up()

    # -- pools: works the server picks from museums --------------------------

    def top_up(self) -> Job | None:
        """When the current rotation (Suggestions or a smart playlist) runs
        low on pictures not shown lately, ask museums for more in the
        background. Returns the job, if one was started."""
        settings = self.settings
        importer = self.service.importer
        if settings.mode != Mode.ART or any(
            job.description == "pool" and not job.finished for job in importer.jobs.values()
        ):
            return None
        playlist = self.playlist(settings)
        if playlist is None:
            have = len(self.fresh(self.suggestions(), settings))
            if have >= POOL_LOW:
                return None
            want = POOL_SIZE - have
            picked = self._pick_from_catalogue(want, settings)
            self._add_suggestions([i.id for i in picked])
            if len(picked) >= want:
                return None
            artists = self.taste()
            theme = theme_of_the_day(utcnow().date())
            queries = [(source, query) for source, query, _ in theme.queries]
            queries = random.sample(queries, min(4, len(queries)))

            def suggest(job: Job) -> None:
                importer.collect(
                    want - len(picked),
                    job,
                    artists=artists,
                    queries=queries,
                    min_suitability=SUGGESTION_SUITABILITY,
                )
                self._add_suggestions(job.item_ids)

            return importer.start_job("pool", suggest)
        rules = playlist.rules
        museum_works = not rules.kinds or ItemKind.ARTWORK in rules.kinds
        if playlist.kind != PlaylistKind.SMART or rules.favorites_only or not museum_works:
            return None
        have = len(self.fresh(self.library.playlist_items(playlist), settings))
        if have >= POOL_LOW:
            return None
        rules = rules.model_copy(update={"kinds": [ItemKind.ARTWORK]})
        return importer.start_job(
            "pool", lambda job: importer.fill(rules, POOL_SIZE - have, job, pooled=True)
        )

    def _pick_from_catalogue(self, count: int, settings: FrameSettings) -> list[Item]:
        """Up to ``count`` new Suggestions from the catalogue: half by the
        artists the owner likes, the rest anything good on e-paper."""
        taken = {i.id for i in self.suggestions()}
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK], min_suitability=SUGGESTION_SUITABILITY)
        pool = [i for i in self.fresh(self.library.query(rules)[1], settings) if i.id not in taken]
        taste = set(self.taste())
        liked = [i for i in pool if i.artist in taste]
        others = [i for i in pool if i.artist not in taste]
        random.shuffle(liked)
        random.shuffle(others)
        picked = liked[: count // 2] + others[: count - min(len(liked), count // 2)]
        picked += [i for i in liked[count // 2 :] if i not in picked][: count - len(picked)]
        return picked[:count]

    def _add_suggestions(self, ids: list[str]) -> None:
        """Remember new Suggestions; beyond ``POOL_MAX`` the works shown
        longest ago go first."""
        known = self.library.get_state(SUGGESTIONS_KEY, [])
        pool = self.suggestions() + [i for i in map(self.library.get, ids) if i is not None]
        pool = list({i.id: i for i in pool}.values())  # once each, in order
        if len(pool) > POOL_MAX:
            shown = sorted(
                (i for i in pool if i.last_shown_at), key=lambda i: i.last_shown_at or ""
            )
            drop = {i.id for i in shown[: len(pool) - POOL_MAX]}
            pool = [i for i in pool if i.id not in drop][-POOL_MAX:]
        log.info("suggestions: %d → %d works", len(known), len(pool))
        self.library.set_state(SUGGESTIONS_KEY, [i.id for i in pool])

    def _protected(self) -> set[str]:
        """Works the catalogue must not lose: kept by the owner, shown,
        about to be shown or picked for Suggestions."""
        state = self.state
        protected = {state.current_item_id or "", *state.current_group, *state.queue}
        protected |= {i for p in self.library.playlists() for i in p.item_ids}
        protected |= set(self.library.get_state(SUGGESTIONS_KEY, []))
        return protected

    def trim_catalogue(self) -> int:
        """Keep the catalogue's thumbnails within ``catalogue_mb``: works the
        server added that nobody kept go, the weakest on e-paper first."""
        images = self.service.images
        limit = self.service.settings.catalogue_mb * 1024 * 1024
        total = images.thumbs_size()
        if total <= limit:
            return 0
        protected = self._protected()
        spare = [
            i
            for i in self.library.query(include_excluded=True)[1]
            if i.pooled
            and not i.show_count
            and not i.favorite
            and not i.framing
            and i.id not in protected
        ]
        spare.sort(key=lambda i: (i.suitability or 0.0, i.added_at))
        removed = 0
        for item in spare:
            if total <= limit:
                break
            path = images.thumb_path(item)
            total -= path.stat().st_size if path.is_file() else 0
            self.library.delete(item.id)
            images.remove(item)
            removed += 1
        return removed

    def grow_catalogue(self) -> Job | None:
        """Add a batch of museum works to the catalogue while its thumbnails
        take less than ``catalogue_mb``; themes and random draws of every
        kind, so the app can browse widely and filter by colour."""
        importer = self.service.importer
        limit = self.service.settings.catalogue_mb * 1024 * 1024
        if not limit or any(
            job.description == "catalogue" and not job.finished for job in importer.jobs.values()
        ):
            return None
        if self.service.images.thumbs_size() >= limit:
            self.trim_catalogue()
            return None
        queries = [(source, query) for theme in PACKS for source, query, _ in theme.queries]
        queries = random.sample(queries, min(8, len(queries)))
        return importer.start_job(
            "catalogue",
            lambda job: importer.collect(
                CATALOGUE_BATCH,
                job,
                queries=queries,
                kinds=CATALOGUE_KINDS,
                min_suitability=CATALOGUE_SUITABILITY,
            ),
        )

    def reset_library(self) -> int:
        """Once, on the owner's wish for a clean start: delete the museum works
        imported before the catalogue, with their pictures, and forget them in
        playlists and the rotation. Own works and photos stay. Returns how
        many works went."""
        if self.library.get_state(RESET_KEY, False):
            return 0
        self.library.set_state(RESET_KEY, True)
        old = self.library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]), include_excluded=True)[1]
        gone = {i.id for i in old if not i.pooled}
        for item in old:
            if item.id in gone:
                self.library.delete(item.id)
                self.service.images.remove(item)
        for playlist in self.library.playlists():
            if set(playlist.item_ids) & gone:
                ids = [i for i in playlist.item_ids if i not in gone]
                self.library.save_playlist(playlist.model_copy(update={"item_ids": ids}))
        state = self.state
        state.queue = [i for i in state.queue if i not in gone]
        state.history = [i for i in state.history if i not in gone]
        if state.current_item_id in gone:
            state.current_item_id = None
            state.current_group = []
        self._save_state(state)
        self.library.set_state(SUGGESTIONS_KEY, [])
        log.info("clean start: %d museum works deleted", len(gone))
        return len(gone)

    def trim_cache(self) -> int:
        """Delete the least recently used museum originals over the size
        limit (the current picture and the next ones stay) and thumbnails
        of works browsed but not kept."""
        state = self.state
        soon = {state.current_item_id, *state.current_group, *state.queue[:PREFETCH]}
        _, items = self.library.query(include_excluded=True)
        keep = [i for i in items if i.id in soon or i.source not in MUSEUMS]
        limit = self.service.settings.image_cache_mb * 1024 * 1024
        self.trim_catalogue()
        self.service.images.prune_thumbs(self.library.query(include_excluded=True)[1])
        return self.service.images.prune(limit, keep)

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

    def postpone(self) -> None:
        """A picture that waited for the panel to wake stays until the next change."""
        state = self.state
        state.next_change_at = next_change(
            utcnow(), self.settings, self.service.status.on_battery
        ).isoformat(timespec="seconds")
        self._save_state(state)

    # -- scheduler -----------------------------------------------------------

    async def tick(self) -> None:
        if self.busy:
            return
        if self.service.power.state.pending_push:
            return  # the waiting picture goes first, when the panel wakes
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
        grown: datetime | None = None
        while True:
            try:
                await self.tick()
                if grown is None or utcnow() - grown >= CATALOGUE_EVERY:
                    grown = utcnow()
                    self.grow_catalogue()
                    self.top_up()
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(period)
