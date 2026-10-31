"""What the frame shows and when: playlist rotation, history, holds."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import threading
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Iterator
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from PIL import Image
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .device import MdcError
from .imaging import PRESETS, RenderSettings
from .imaging.grids import MAX_PHOTOS, MIN_PHOTOS
from .imaging.layout import Fit
from .imaging.text import TextBlock
from .library import AlbumOrder, Item, ItemKind, Job, Note, Playlist, PlaylistKind, PlaylistRules
from .library.artists import is_artist
from .library.colors import SCORE_VERSION, analyse, tint_spread
from .library.icloud import only_copy
from .library.images import Unavailable
from .library.museums import Kind
from .library.nationality import life_years, note_years
from .library.repo import SENT_KEY
from .library.style import AUTO, auto_preset
from .library.themes import SEARCHABLE, theme_of_the_day
from .library.vocabulary import HIGHLIGHT, set_aside
from .progress import Stage
from .schedule import FrameSettings, Presentation, in_quiet_hours, next_change

if TYPE_CHECKING:
    from .ai import PolishText
    from .service import FrameService

log = logging.getLogger(__name__)

SETTINGS_KEY = "settings"
STATE_KEY = "player"
HISTORY_MAX = 50
#: Next pictures whose originals are downloaded ahead of their turn.
PREFETCH = 8  # as many as "Następne" shows in the app
#: When no picture can be shown (offline, nothing cached), try again after this.
RETRY_AFTER = timedelta(minutes=15)
#: How long a change waits for a work's Polish texts (a translation takes a
#: few seconds, a note from the picture up to half a minute) before it shows
#: the English ones; the next picture's are asked for while it waits its turn.
POLISH_SHOW_SECONDS = 25.0
POLISH_AHEAD_SECONDS = 180.0
#: Works picked by the server for the default rotation (ids, oldest first).
SUGGESTIONS_KEY = "suggestions"
#: Set once the museum works imported before the catalogue are gone.
RESET_KEY = "library_reset"
#: Set once the catalogue's manuscripts are gone.
#: Set once the catalogue has been cleared of what it leaves out now.
SET_ASIDE_KEY = "set_aside_dropped"
#: Bump when ``set_aside`` leaves out more, so the catalogue is cleaned again
#: (1: photographs and manuscripts, 2: reproductions and B&W copies,
#: 3: Girona's photo archive).
SET_ASIDE_VERSION = 3
#: Version of the colour analysis and score the library's pictures carry.
SCORE_KEY = "suitability_version"
#: The playlist the photos sent once gather in, newest first.
SENT_NAME = "Historia przesłanych"
#: A rotation with fewer pictures not shown lately asks museums for more,
#: up to ``POOL_SIZE``; Suggestions remember at most ``POOL_MAX`` works.
POOL_LOW = 8
POOL_SIZE = 24
POOL_MAX = 80
#: Artists of the owner's taste asked for when topping up Suggestions.
TASTE_ARTISTS = 6
#: Artists asked for in Szukaj, the latest this many: each search counts as
#: a work kept, at most this much for one artist.
SEARCHED_ARTISTS_KEY = "searched_artists"
SEARCHED_ARTISTS_KEPT = 30
SEARCHED_ARTIST_MAX = 3
#: The catalogue grows by this many works at a time, at most every
#: ``CATALOGUE_EVERY`` (gently for the museums' APIs).
CATALOGUE_BATCH = 300
CATALOGUE_EVERY = timedelta(hours=1)
CATALOGUE_KINDS: tuple[Kind, ...] = ("painting", "print", "drawing", "poster")
#: Kinds of the museums' most important works it takes in too.
CATALOGUE_HIGHLIGHTS: tuple[Kind, ...] = ("painting", "print")
#: Highlights the catalogue keeps at least (for "Arcydzieła muzeów"),
#: topped up at most every ``CATALOGUE_HIGHLIGHT_EVERY``.
CATALOGUE_HIGHLIGHT_MIN = 40
CATALOGUE_HIGHLIGHT_EVERY = timedelta(days=1)
#: When the catalogue's highlights were last topped up.
HIGHLIGHTS_KEY = "catalogue_highlights"
#: A full catalogue still takes in this many works at a time, at most every
#: ``CATALOGUE_TURNOVER_EVERY``, and lets as many go: new works keep coming.
CATALOGUE_TURNOVER = 60
CATALOGUE_TURNOVER_EVERY = timedelta(hours=6)
#: When a full catalogue last took works in.
TURNOVER_KEY = "catalogue_turnover"
# How long a due change may keep the panel from its night sleep.
CHANGE_GRACE = timedelta(minutes=3)


def _log_failure(task: asyncio.Task[object]) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("background task failed", exc_info=task.exception())


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
    #: Added from the app ("Dodaj do kolejki"): shown before ``queue``.
    requested: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    hold: Hold | None = None
    last_change_at: str | None = None
    #: Who made that change: ``schedule`` or ``app`` (see ``origin_of``).
    last_change_origin: str | None = None
    next_change_at: str | None = None
    last_error: str | None = None


def origin_of(reason: str) -> str:
    """Who changed the picture, for the app: the schedule (a timed change,
    also the end of a timed hold) or the owner from the app (everything else:
    "Pokaż na ramce", a playlist presented, back, next)."""
    return "schedule" if reason == "schedule" else "app"


def hold_from(spec: str | int | None) -> Hold | None:
    """``"next"``/None: until the next scheduled change; ``"forever"``;
    or a number of minutes."""
    if spec in (None, "", "next"):
        return None
    if spec == "forever":
        return Hold(forever=True)
    minutes = int(spec)
    return Hold(until=(utcnow() + timedelta(minutes=minutes)).isoformat(timespec="seconds"))


def caption_for(item: Item, polish: PolishText | None = None) -> str:
    if item.kind == ItemKind.PHOTO:
        parts = [item.date_text, item.photo.caption if item.photo else ""]
        return " · ".join(p for p in parts if p)
    parts = [item.artist, polish.title if polish else item.title]
    text = " — ".join(p for p in parts if p)
    date = (polish.date if polish else "") or item.date_text
    return f"{text}, {date}" if date else text


def text_block_for(item: Item, polish: PolishText | None = None) -> TextBlock:
    """What the DESCRIPTION mode prints on the mat; with ``polish``, in Polish."""
    if item.kind == ItemKind.PHOTO:
        info = item.photo
        title = (info.caption if info and info.caption else "") or item.title
        when = item.date_text or (info.taken_at[:10] if info and info.taken_at else "")
        who = info.contributor if info and info.contributor else ""
        return TextBlock(title=title, meta=[m for m in (when, who) if m])
    # The author alone, then date · medium; a work the museum gives no date
    # for (not even "ca. 1660") shows its author's life years instead.
    life = life_years(item.artist_bio) if item.artist_bio else ""
    if polish is not None:
        when = polish.date or item.date_text or note_years(polish.artist_note) or life
        detail = " · ".join(p for p in (when, polish.medium or item.medium) if p)
        return TextBlock(
            title=polish.title, meta=[m for m in (item.artist, detail) if m], body=polish.frame
        )
    detail = " · ".join(p for p in (item.date_text or life, item.medium) if p)
    body = item.description or ", ".join(p for p in (item.museum, item.credit) if p)
    return TextBlock(title=item.title, meta=[m for m in (item.artist, detail) if m], body=body)


async def _settled(future: Future[Note | None], seconds: float, item_id: str) -> bool:
    """Whether the Polish texts asked for came within ``seconds``."""
    try:
        await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), seconds)
    except TimeoutError:
        log.info("Polish texts of %s not ready after %.0f s", item_id, seconds)
        return False
    except Exception as err:  # the model is unavailable: English it is
        log.info("Polish texts of %s failed: %s", item_id, err)
        return False
    return True


def _when_taken(item: Item) -> str:
    return (item.photo.taken_at if item.photo else None) or item.date_text or item.added_at


def _when_shared(item: Item) -> str:
    return (item.photo.shared_at if item.photo else None) or item.added_at


def album_order(items: list[Item], order: AlbumOrder) -> list[Item]:
    """An album's photos in the order its playlist shows them."""
    if order == AlbumOrder.RANDOM:
        return random.sample(items, len(items))
    if order == AlbumOrder.ADDED:
        return sorted(items, key=_when_shared, reverse=True)
    return sorted(items, key=_when_taken, reverse=order == AlbumOrder.NEWEST)


class Player:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self.library = service.library
        self._lock = asyncio.Lock()
        self._trimming = threading.Lock()  # after a change and after a new limit at once
        self._changes = 0  # under way: from the download of the original to the push

    @property
    def busy(self) -> bool:
        """A change is under way, the original's download included: the app
        follows it from the start, "Teraz" catches up once it is done."""
        return self._changes > 0

    @contextlib.contextmanager
    def _working(self) -> Iterator[None]:
        self._changes += 1
        try:
            yield
        finally:
            self._changes -= 1

    # -- persisted settings and state --------------------------------------

    @property
    def settings(self) -> FrameSettings:
        return FrameSettings.model_validate(self.library.get_state(SETTINGS_KEY, {}))

    def save_settings(self, settings: FrameSettings) -> FrameSettings:
        old = self.settings
        self.library.set_state(SETTINGS_KEY, settings.model_dump(mode="json"))
        if (old.playlist_id, old.shuffle) != (settings.playlist_id, settings.shuffle):
            self.reset_queue()
        self.reschedule()
        return settings

    @property
    def state(self) -> PlayerState:
        return PlayerState.model_validate(self.library.get_state(STATE_KEY, {}))

    def _save_state(self, state: PlayerState) -> None:
        self.library.set_state(STATE_KEY, state.model_dump(mode="json"))

    def reset_queue(self) -> None:
        """Forget the order of the next pictures; it is drawn again."""
        state = self.state
        state.queue = []
        self._save_state(state)

    def playlist_changed(self, playlist_id: int) -> None:
        """The playlist's pictures or their order changed (e.g. new photos in
        an album): if the frame plays it, the next ones are drawn again."""
        if self.settings.playlist_id == playlist_id:
            self.reset_queue()

    def item_changed(self, item_id: str) -> None:
        """A work was liked, unliked, left out or brought back: the queue of
        the playlist the frame plays follows, without a redraw. A work that
        joined the playlist comes right after the next picture (already
        drawn ahead), or at the end if shown lately or the playlist keeps an
        album's order; one that left it is dropped. The owner's picks
        (``queue_next``) stay either way."""
        playlist = self.playlist()
        state = self.state
        if playlist is None or not state.queue:
            return  # Suggestions, or drawn from the playlist at the next change
        member = any(i.id == item_id for i in self.library.playlist_items(playlist))
        if not member:
            self.unqueue(item_id)
            return
        shown = {state.current_item_id, *state.current_group, *state.requested}
        item = self.library.get(item_id)
        if item is None or item_id in state.queue or item_id in shown:
            return
        if playlist.album is not None or not self.fresh([item]):
            state.queue.append(item_id)
        else:
            state.queue.insert(1, item_id)
        self._save_state(state)

    def unqueue(self, item_id: str) -> None:
        """Forget a work already queued, e.g. one taken out of the playlist."""
        state = self.state
        if item_id in state.queue:
            state.queue = [i for i in state.queue if i != item_id]
            self._save_state(state)

    def queue_next(self, item_id: str) -> None:
        """The owner's pick: shown at the next change, before the rest of
        the queue (and before earlier picks), whatever the frame plays."""
        state = self.state
        state.requested = [item_id, *(i for i in state.requested if i != item_id)]
        state.queue = [i for i in state.queue if i != item_id]
        self._save_state(state)

    def remember_sent(self, item: Item) -> None:
        """A photo sent once, shown or queued, goes first in "Historia
        przesłanych"; the playlist is made when first needed, and again if
        the owner deleted it."""
        if item.look is None:
            return
        playlist_id = self.library.get_state(SENT_KEY, None)
        playlist = self.library.playlist(playlist_id) if playlist_id is not None else None
        if playlist is None:
            playlist = Playlist(name=SENT_NAME, kind=PlaylistKind.MANUAL)
        ids = [item.id, *(i for i in playlist.item_ids if i != item.id)]
        saved = self.library.save_playlist(playlist.model_copy(update={"item_ids": ids}))
        self.library.set_state(SENT_KEY, saved.id)

    def dequeue(self, item_id: str) -> None:
        """Take back a pick added with ``queue_next``."""
        state = self.state
        if item_id in state.requested:
            state.requested = [i for i in state.requested if i != item_id]
            self._save_state(state)

    def skip(self, item_id: str) -> None:
        """The owner skips ("Pomiń") a picture waiting its turn: a pick
        added with ``queue_next`` is taken back, one of the rotation goes to
        the end of it, so it comes back only after the rest of the round."""
        state = self.state
        if item_id in state.requested:
            state.requested = [i for i in state.requested if i != item_id]
        elif item_id in state.queue:
            state.queue = [*(i for i in state.queue if i != item_id), item_id]
        else:
            return
        self._save_state(state)

    def reschedule(self) -> None:
        state = self.state
        base = datetime.fromisoformat(state.last_change_at) if state.last_change_at else utcnow()
        state.next_change_at = next_change(base, self.settings).isoformat(timespec="seconds")
        self._save_state(state)

    # -- choosing pictures ---------------------------------------------------

    def candidates(self, settings: FrameSettings | None = None) -> list[Item]:
        settings = settings or self.settings
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
        spare = self.library.spare_copies()
        found = (self.library.get(item_id) for item_id in ids if item_id not in spare)
        return [i for i in found if i is not None]

    def fresh(self, items: list[Item], settings: FrameSettings | None = None) -> list[Item]:
        """Those of ``items`` not shown within the no-repeat period."""
        settings = settings or self.settings
        cutoff = (utcnow() - timedelta(days=settings.avoid_repeat_days)).isoformat()
        return [i for i in items if not i.last_shown_at or i.last_shown_at < cutoff]

    def taste(self) -> list[str]:
        """Artists the owner likes, most liked first: favourites count most,
        then works kept in the library (not the ones the server picked) and
        artists lately searched for."""
        scores: Counter[str] = Counter()
        for item in self.library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]))[1]:
            if is_artist(item.artist):
                scores[item.artist] += 3 * item.favorite + (not item.pooled)
        searched = Counter(self.library.get_state(SEARCHED_ARTISTS_KEY, []))
        for artist, times in searched.items():
            scores[artist] += min(times, SEARCHED_ARTIST_MAX)
        return [artist for artist, score in scores.most_common(TASTE_ARTISTS) if score > 0]

    def _refill(self, state: PlayerState, settings: FrameSettings) -> None:
        """The whole rotation: pictures not shown lately first, then those
        shown lately. (Only the first part would leave out most of a
        playlist once a few new works join it.)"""
        items = [i for i in self.candidates(settings) if i.id not in state.requested]
        items = [i for i in items if i.id != state.current_item_id] or items
        fresh = {i.id for i in self.fresh(items, settings)}
        parts = [[i for i in items if i.id in fresh], [i for i in items if i.id not in fresh]]
        playlist = self.playlist(settings)
        for part in parts:
            if playlist is not None and playlist.album is not None:
                part[:] = album_order(part, playlist.album.order)
            elif settings.shuffle:
                random.shuffle(part)
        state.queue = [i.id for part in parts for i in part]

    def _catch_up(self, state: PlayerState, settings: FrameSettings) -> bool:
        """Once the queue goes on to pictures shown lately, works found since
        (e.g. by a top-up from museums) come first: the queue is drawn
        again. Returns whether it was."""
        head = self.library.get(state.queue[0]) if state.queue else None
        if head is None or self.fresh([head], settings):
            return False
        queued = {*state.queue, *state.requested, state.current_item_id}
        if all(i.id in queued for i in self.fresh(self.candidates(settings), settings)):
            return False
        self._refill(state, settings)
        return True

    def _pop_next(
        self, state: PlayerState, settings: FrameSettings, picks: bool = True
    ) -> Item | None:
        while picks and state.requested:
            item = self.library.get(state.requested.pop(0))
            if item is not None:  # asked for: shown even if left out of the rotation
                return item
        spare = self.library.spare_copies()
        unavailable = self.service.images.unavailable
        self._catch_up(state, settings)
        for _ in range(2):
            while state.queue:
                item = self.library.get(state.queue.pop(0))
                if item is None or item.excluded or item.id in spare or unavailable(item):
                    continue
                return item
            self._refill(state, settings)
        return None

    def _drop(self, item_id: str) -> None:
        """Out of the line: its original cannot be had."""
        state = self.state
        if item_id in state.queue or item_id in state.requested:
            state.queue = [i for i in state.queue if i != item_id]
            state.requested = [i for i in state.requested if i != item_id]
            self._save_state(state)

    def upcoming(self, limit: int = 8) -> list[Item]:
        state, settings = self.state, self.settings
        if not state.queue:
            self._refill(state, settings)
            self._save_state(state)
        elif self._catch_up(state, settings):
            self._save_state(state)
        items = (self.library.get(i) for i in [*state.requested, *state.queue][:limit])
        return [i for i in items if i is not None]

    # -- boards of several photos (MULTI) ------------------------------------

    @staticmethod
    def presentation(item: Item, settings: FrameSettings) -> Presentation:
        """How ``item`` is framed: the settings' for photos or for art, or
        the look a photo sent once from the camera roll was given."""
        if item.look is not None:
            look = item.look
            update = {"fit": look.fit, "mat": look.mat, "margin": look.margin}
            return settings.photo.model_copy(update=update | {"preset": AUTO, "label": False})
        return settings.photo if item.kind == ItemKind.PHOTO else settings.art

    @classmethod
    def multi(cls, item: Item, settings: FrameSettings) -> bool:
        return item.kind == ItemKind.PHOTO and cls.presentation(item, settings).fit == Fit.MULTI

    def board(
        self,
        item: Item,
        state: PlayerState,
        settings: FrameSettings,
        keep: list[str] | None = None,
        spare: list[Item] | None = None,
    ) -> list[Item]:
        """The photos shown with ``item``: ``item`` alone unless photos are
        shown several to a board. ``keep`` (a redraw) are the ones shown with
        it before; missing photos are taken from the queue (removed from
        it), then from the rest of the playlist, then from ``spare``."""
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
            taken |= {i.id for i in board}
        if len(board) < count and spare:
            more = [i for i in spare if i.id not in taken and not i.excluded]
            board += more[: count - len(board)]
        return board

    def preview_board(self, item: Item, settings: FrameSettings) -> list[Item]:
        """The board a preview of ``item`` shows: the one on the frame if
        ``item`` is current, else the photos that would join it next."""
        state = self.state
        keep = state.current_group if state.current_item_id == item.id else None
        spare = None
        if self.multi(item, settings):
            # A playlist of art has no photos to join it: the library's
            # photos and those sent once fill the board, the same ones each
            # time for one photo.
            listed = self.library.query(PlaylistRules(kinds=[ItemKind.PHOTO]))[1]
            sent = (self.library.get(i) for i in sorted(self.library.sent_photo_ids()))
            spare = sorted([*listed, *(i for i in sent if i is not None)], key=lambda i: i.id)
            random.Random(item.id).shuffle(spare)
        return self.board(item, state, settings, keep, spare)  # state is a copy: nothing is taken

    # -- showing -------------------------------------------------------------

    def preset_for(self, item: Item, settings: FrameSettings) -> str:
        """The rendering preset ``item`` gets: always chosen by the picture."""
        if item.tint_spread is None:
            # Pictures added before automatic styles: measure the thumbnail once.
            thumb = self.service.images.thumb_path(item)
            if thumb.is_file():
                with Image.open(thumb) as img:
                    spread = tint_spread(img)
                item = self.library.update(item.id, tint_spread=spread) or item
        return auto_preset(item)

    def render_settings(self, item: Item, settings: FrameSettings) -> RenderSettings:
        pres = self.presentation(item, settings)
        preset = self.preset_for(item, settings)
        base = PRESETS.get(preset, PRESETS["painting"]).model_copy(deep=True)
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
            base.layout.detail = framing.detail
            base.layout.picture_crop = framing.picture
            base.layout.fit_crop = framing.fit
        polish = self.polish(item, settings)
        if pres.fit == Fit.DESCRIPTION:
            base.text = text_block_for(item, polish)
        base.caption = caption_for(item, polish) if pres.label else None
        return base

    # -- Polish texts --------------------------------------------------------

    def _wants_text(self, item: Item, settings: FrameSettings) -> bool:
        pres = self.presentation(item, settings)
        return pres.fit == Fit.DESCRIPTION or pres.label

    def polish(self, item: Item, settings: FrameSettings) -> PolishText | None:
        """The work's Polish texts when they are on and written already."""
        if not self._wants_text(item, settings):
            return None
        return self.service.pl_text.text(item)

    def _ask_polish(self, item: Item, settings: FrameSettings) -> Future[Note | None] | None:
        """Ask for the work's Polish texts first in line, if it has none yet."""
        job = self.service.pl_text
        if not job.enabled() or not job.applies(item) or not self._wants_text(item, settings):
            return None
        future = self.service.ai.need_now(item.id, job.kind)
        return None if future.done() else future

    async def wait_for_polish(self, item: Item, settings: FrameSettings, seconds: float) -> None:
        """Wait up to ``seconds`` for the work's Polish texts; the English ones
        are shown when they take longer (or fail). Never raises."""
        future = self._ask_polish(item, settings)
        if future is not None:
            await _settled(future, seconds, item.id)

    async def show(self, item: Item, reason: str, hold: Hold | None = None) -> None:
        """Render ``item``, publish it and tell the panel. Never raises."""
        async with self._lock:
            state = self.state
            settings = self.settings

            board = self.board(item, state, settings)

            async def work() -> None:
                # Begun at the download.
                self.service.progress.begin(item.title, keep=True, origin=origin_of(reason))
                await self.wait_for_polish(item, settings, POLISH_SHOW_SECONDS)
                await self._publish(board, settings)
                if state.current_item_id and state.current_item_id != item.id:
                    state.history = [*state.history, state.current_item_id][-HISTORY_MAX:]
                state.current_item_id = item.id
                state.current_group = [i.id for i in board[1:]]
                state.hold = hold
                now = utcnow()
                state.last_change_at = now.isoformat(timespec="seconds")
                state.last_change_origin = origin_of(reason)
                state.next_change_at = next_change(now, settings).isoformat(timespec="seconds")
                state.last_error = None
                for shown in board:
                    self.library.record_shown(shown.id, reason)
                self._save_state(state)
                await self._push(state)

            await self._guarded(item.id, state, work)

    def needs_restyle(self, old: FrameSettings, new: FrameSettings) -> bool:
        """Whether a settings change must redraw the current picture now.

        Only turning the screen does: the picture would hang sideways.
        A new presentation (framing, mat, style) waits for the next picture
        sent to the frame, so saving it does not wake the panel."""
        if not self.state.current_item_id:
            return False
        return (old.orientation, old.rotation) != (new.orientation, new.rotation)

    def presentation_changed(self, old: FrameSettings, new: FrameSettings) -> bool:
        """Whether pictures are framed differently from now on."""
        return (old.art, old.photo) != (new.art, new.photo)

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
                self.service.progress.begin(item.title, origin="app")  # new settings
                await self.wait_for_polish(item, settings, POLISH_SHOW_SECONDS)
                await self._publish(board, settings)
                state.current_group = [i.id for i in board[1:]]
                state.last_error = None
                self._save_state(state)
                await self._push(state)

            await self._guarded(item.id, state, work)
        await self.render_ahead()  # new settings may draw the next one differently too

    async def show_still(
        self, png: bytes, *, preview_png: bytes, title: str, description: str, hold: Hold
    ) -> None:
        """Put a ready-made panel image (e.g. the calibration chart) on the frame
        and hold it. The current item stays current, so ``resume`` returns to it.
        """
        async with self._lock:
            state = self.state

            async def work() -> None:
                self.service.progress.begin(title, render=False, origin="app")
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

    async def _originals(
        self, board: list[Item], settings: FrameSettings, urgent: bool = True
    ) -> bytes | list[bytes]:
        """The picture's original (MULTI: the board's), downloaded if need be;
        ``urgent`` (a change): before the downloads of the background."""
        images = []
        for shown in board:
            path = await run_in_threadpool(self.service.images.ensure_image, shown, urgent)
            images.append(await run_in_threadpool(path.read_bytes))
        return images if self.multi(board[0], settings) else images[0]

    async def _publish(self, board: list[Item], settings: FrameSettings) -> None:
        """Render the picture (or, MULTI, the board of photos) and publish it."""
        item = board[0]
        extra: dict[str, object] = {"item_id": item.id, "kind": item.kind.value}
        if len(board) > 1:
            extra["item_ids"] = [i.id for i in board]
        await run_in_threadpool(
            self.service.prepare,
            await self._originals(board, settings),
            self.render_settings(item, settings),
            title=item.title,
            description=caption_for(item),
            source=item.source,
            extra=extra,
            seed=",".join(i.id for i in board),
        )

    async def render_ahead(self) -> None:
        """Draw the next picture while the current one is on the frame, so
        its change only publishes it. Never raises.

        Not for boards of photos: which photos join one is decided when it
        is shown."""
        settings = self.settings
        upcoming = self.upcoming(1)
        if not upcoming or self.multi(upcoming[0], settings):
            return
        item = upcoming[0]
        if (future := self._ask_polish(item, settings)) is not None:
            # Drawn again once its Polish texts are there.
            self.service.background(self._render_when_ready(future, item.id))
        try:
            image = await self._originals([item], settings, urgent=False)
            render_settings = self.render_settings(item, settings)
            await run_in_threadpool(self.service.render_content, image, render_settings)
        except Exception as err:  # it is drawn again at its turn
            log.info("rendering %s ahead failed: %s", item.id, err)

    async def _render_when_ready(self, future: Future[Note | None], item_id: str) -> None:
        if await _settled(future, POLISH_AHEAD_SECONDS, item_id):
            await self.render_ahead()

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
        with self._working():
            await self._work_logged(label, state, work)

    async def _work_logged(
        self, label: str, state: PlayerState, work: Callable[[], Awaitable[None]]
    ) -> None:
        try:
            await work()
        except (MdcError, OSError, ValueError, RuntimeError) as err:
            log.warning("showing %s failed: %s", label, err)
            state.last_error = str(err)
            self._save_state(state)
            self.service.progress.finish(Stage.FAILED, str(err))
        except Exception as err:  # keep the scheduler alive whatever happens
            log.exception("showing %s failed", label)
            state.last_error = str(err)
            self._save_state(state)
            self.service.progress.finish(Stage.FAILED, str(err))

    async def next(self, reason: str = "manual", *, picks: bool = True) -> Item | None:
        """The next picture on the frame. ``picks=False`` ("Prezentuj na
        ramce" on a playlist): the rotation's own next one, the owner's
        picks wait for the change after it."""
        with self._working():  # busy from the start: the original may take a while
            state, settings = self.state, self.settings
            item = await self._pop_ready(state, settings, picks, origin_of(reason))
            if item is None and state.last_error:
                state.next_change_at = (utcnow() + RETRY_AFTER).isoformat(timespec="seconds")
            self._save_state(state)
            if item is not None:
                await self.show(item, reason)
        if item is not None:
            await self.get_ready()
        return item

    async def _pop_ready(
        self,
        state: PlayerState,
        settings: FrameSettings,
        picks: bool = True,
        origin: str | None = None,
    ) -> Item | None:
        """The next picture whose original is at hand. One that cannot be
        downloaded now (no internet, museum down) goes to the back of the
        queue and the first one already cached takes its turn; the owner's
        pick stays first in line."""
        asked = set(state.requested) if picks else set()
        item = self._pop_next(state, settings, picks)
        if item is None:
            return None
        images = self.service.images
        progress = self.service.progress
        downloading = not images.has_image(item)
        if downloading:
            progress.begin(item.title, origin=origin)  # the app's bar from the download on
        try:
            await run_in_threadpool(images.ensure_image, item, True)
            return item
        except Unavailable as err:  # never coming: out of the line
            log.warning("%s; dropped from the queue", err)
            state.last_error = f"{item.title or item.id}: oryginał niedostępny"
            if downloading:
                progress.finish(Stage.IDLE)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.warning("original of %s unavailable: %s", item.id, err)
            state.last_error = f"{item.title or item.id}: {err}"
            if downloading:
                progress.finish(Stage.IDLE)
            if item.id in asked:
                state.requested.insert(0, item.id)
            else:
                state.queue.append(item.id)
        if not state.queue:
            self._refill(state, settings)
        for line in (state.requested, state.queue) if picks else (state.queue,):
            for item_id in line:
                cached = self.library.get(item_id)
                if cached is not None and images.has_image(cached):
                    if line is state.queue and cached.excluded:
                        continue
                    line.remove(item_id)
                    return cached
        return None

    async def get_ready(self) -> None:
        """After the next pictures changed: download them, draw the first."""
        await self.prefetch()
        await self.render_ahead()

    async def prefetch(self) -> None:
        """Download the originals of the next pictures now, so that a change
        needs no internet, then trim the cache. Never raises."""
        images = self.service.images
        for item in self.upcoming(PREFETCH):
            if images.has_image(item):
                continue
            try:
                await run_in_threadpool(images.ensure_image, item)
            except Unavailable as err:
                log.warning("%s; dropped from the queue", err)
                self._drop(item.id)
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
        if any(job.description == "pool" and not job.finished for job in importer.jobs.values()):
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
            theme = theme_of_the_day(utcnow().date(), self.library)
            queries = theme.searches()
            queries = random.sample(queries, min(4, len(queries)))

            def suggest(job: Job) -> None:
                importer.collect(
                    want - len(picked),
                    job,
                    artists=artists,
                    queries=queries,
                )
                self._add_suggestions(job.item_ids)

            return importer.start_job("pool", suggest)
        rules = playlist.rules
        museum_works = not rules.kinds or ItemKind.ARTWORK in rules.kinds
        if (
            playlist.kind != PlaylistKind.SMART
            or rules.favorites_only
            or rules.asks_mine()
            or not museum_works
        ):
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
        artists the owner likes, the rest anything. (No e-paper threshold:
        Mateusz, 2026-10-31, it left out Rembrandt and Vermeer.)"""
        taken = {i.id for i in self.suggestions()}
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK])
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
        protected |= set(state.requested)
        protected |= {i for p in self.library.playlists() for i in p.item_ids}
        protected |= set(self.library.get_state(SUGGESTIONS_KEY, []))
        return protected

    def keep_searched(self, items: Iterable[Item]) -> None:
        """Works a search showed join the catalogue in the background (as
        the catalogue's own draws do, so not while tests run the server)."""
        settings = self.service.settings
        if settings.scheduler and settings.catalogue_mb:
            self.service.importer.keep_searched(items)

    def searched_for(self, artists: list[str]) -> None:
        """Artists asked for in Szukaj count towards :meth:`taste`; the
        same search again (e.g. coming back to it) once."""
        if not artists:
            return
        recent: list[str] = self.library.get_state(SEARCHED_ARTISTS_KEY, [])
        if recent[-len(artists) :] == artists:
            return
        self.library.set_state(SEARCHED_ARTISTS_KEY, (recent + artists)[-SEARCHED_ARTISTS_KEPT:])

    def trim_catalogue(self) -> int:
        """Keep the catalogue's thumbnails within ``catalogue_mb``: works the
        server added that nobody kept go, the longest there first."""
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
        spare.sort(key=lambda i: i.added_at)
        gone: list[Item] = []
        for item in spare:
            if total <= limit:
                break
            path = images.thumb_path(item)
            total -= path.stat().st_size if path.is_file() else 0
            gone.append(item)
        # A lowered limit can drop thousands at once: one transaction.
        self._forget(gone)
        return len(gone)

    def _add_highlights(self, job: Job) -> None:
        """Top the catalogue's museum highlights up to ``CATALOGUE_HIGHLIGHT_MIN``."""
        have = self.library.query(PlaylistRules(terms=[HIGHLIGHT]))[0]
        if have >= CATALOGUE_HIGHLIGHT_MIN:
            return
        self.service.importer.collect(
            CATALOGUE_HIGHLIGHT_MIN - have,
            Job(id=job.id, description="highlights"),  # its own count
            kinds=(),
            highlights=CATALOGUE_HIGHLIGHTS,
        )

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
        full = self.service.images.thumbs_size() >= limit
        # "Arcydzieła muzeów" needs the museums' highlights in the catalogue,
        # which works taken in before 0.42 never say they are: asked for on
        # their own, once a day, while the catalogue has too few.
        tried = self.library.get_state(HIGHLIGHTS_KEY, "")
        highlights = (
            not tried or utcnow() - datetime.fromisoformat(tried) >= CATALOGUE_HIGHLIGHT_EVERY
        )
        turnover = True
        if full:
            self.trim_catalogue()
            turned = self.library.get_state(TURNOVER_KEY, "")
            turnover = (
                not turned or utcnow() - datetime.fromisoformat(turned) >= CATALOGUE_TURNOVER_EVERY
            )
            if not turnover and not highlights:
                return None
            if turnover:
                self.library.set_state(TURNOVER_KEY, utcnow().isoformat())
        if highlights:
            self.library.set_state(HIGHLIGHTS_KEY, utcnow().isoformat())
        queries = [search for theme in SEARCHABLE for search in theme.searches()]
        queries = random.sample(queries, min(8, len(queries)))

        def grow(job: Job) -> None:
            if highlights:
                self._add_highlights(job)
            if turnover:
                importer.collect(
                    CATALOGUE_TURNOVER if full else CATALOGUE_BATCH,
                    job,
                    queries=queries,
                    kinds=CATALOGUE_KINDS,
                    highlights=CATALOGUE_HIGHLIGHTS,
                )
            if full:
                self.trim_catalogue()

        return importer.start_job("catalogue", grow)

    def rescore(self) -> int:
        """Once per ``SCORE_VERSION``: analyse the library's pictures again
        from their thumbnails (add-on 0.12: colourful works first; 0.21:
        colour accents). Measured before writing, written in one
        transaction; returns how many."""
        if self.library.get_state(SCORE_KEY, 1) >= SCORE_VERSION:
            return 0
        images = self.service.images
        analysed: dict[str, dict[str, Any]] = {}
        for item in self.library.query(include_excluded=True)[1]:
            path = images.thumb_path(item)
            if (item.suitability is None and not item.colors) or not path.is_file():
                continue
            try:
                with Image.open(path) as img:
                    spread = item.tint_spread
                    if spread is None:
                        spread = tint_spread(img)
                    colors, tags, value = analyse(img, self.service.palette, spread)
            except OSError:
                log.warning("rescore: cannot read %s", path)
                continue
            changes: dict[str, Any] = {"colors": colors, "color_tags": tags, "tint_spread": spread}
            if item.suitability is not None:
                changes["suitability"] = value
            analysed[item.id] = changes
        with self.library.batch():
            for item_id, changes in analysed.items():
                self.library.update(item_id, **changes)
            self.library.set_state(SCORE_KEY, SCORE_VERSION)
        log.info("rescore: %d pictures analysed again", len(analysed))
        return len(analysed)

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
        with self.library.batch():
            for item in old:
                if item.id in gone:
                    self.library.delete(item.id)
            for playlist in self.library.playlists():
                if set(playlist.item_ids) & gone:
                    ids = [i for i in playlist.item_ids if i not in gone]
                    self.library.save_playlist(playlist.model_copy(update={"item_ids": ids}))
        for item in old:
            if item.id in gone:
                self.service.images.remove(item)
        state = self.state
        state.queue = [i for i in state.queue if i not in gone]
        state.requested = [i for i in state.requested if i not in gone]
        state.history = [i for i in state.history if i not in gone]
        if state.current_item_id in gone:
            state.current_item_id = None
            state.current_group = []
        self._save_state(state)
        self.library.set_state(SUGGESTIONS_KEY, [])
        log.info("clean start: %d museum works deleted", len(gone))
        return len(gone)

    def drop_set_aside(self) -> int:
        """Once per :data:`SET_ASIDE_VERSION`: delete the photographs, copies
        and pages of manuscripts the server put in the catalogue before it
        learnt to leave them out. Works the owner kept, liked, framed or put
        in a playlist stay. Returns how many went."""
        # Version 1 was stored as ``True``.
        if int(self.library.get_state(SET_ASIDE_KEY, 0)) >= SET_ASIDE_VERSION:
            return 0
        self.library.set_state(SET_ASIDE_KEY, SET_ASIDE_VERSION)
        state = self.state
        kept = {i for p in self.library.playlists() for i in p.item_ids}
        kept |= {state.current_item_id or "", *state.current_group, *state.requested}
        gone = [
            i
            for i in self.library.query(include_excluded=True)[1]
            if i.pooled and set_aside(i) and not i.favorite and not i.framing and i.id not in kept
        ]
        self._forget(gone)
        log.info("catalogue: %d photographs, copies and manuscript pages deleted", len(gone))
        return len(gone)

    def drop_spare_copies(self) -> int:
        """Delete the works the server added again from another source
        (``Library.spare_copies``): the copy the owner kept, or the one from
        the most reliable source, stays. Copies the owner liked, framed or
        put in a playlist, and the one on the frame, stay too. Returns how
        many went."""
        spare = self.library.spare_copies()
        if not spare:
            return 0
        state = self.state
        kept = {i for p in self.library.playlists() for i in p.item_ids}
        kept |= {state.current_item_id or "", *state.current_group, *state.requested}
        gone = [
            i
            for i in map(self.library.get, spare - kept)
            if i is not None and not i.favorite and not i.framing
        ]
        self._forget(gone)
        if gone:
            log.info("catalogue: %d copies of works held from another source deleted", len(gone))
        return len(gone)

    def _forget(self, gone: list[Item]) -> None:
        """Delete ``gone`` with their pictures, from the queue and Suggestions."""
        ids = {i.id for i in gone}
        if not ids:
            return
        with self.library.batch():
            for item in gone:
                self.library.delete(item.id)
        for item in gone:
            self.service.images.remove(item)
        state = self.state
        state.queue = [i for i in state.queue if i not in ids]
        state.requested = [i for i in state.requested if i not in ids]
        self._save_state(state)
        suggestions = self.library.get_state(SUGGESTIONS_KEY, [])
        self.library.set_state(SUGGESTIONS_KEY, [i for i in suggestions if i not in ids])

    def trim_cache(self) -> int:
        """Delete the least recently used museum originals over the size
        limit (the current picture and the next ones stay) and thumbnails
        of works browsed but not kept."""
        with self._trimming:
            return self._trim_cache()

    def _trim_cache(self) -> int:
        state = self.state
        soon = {state.current_item_id, *state.current_group, *state.requested}
        soon |= set(state.queue[:PREFETCH])
        _, items = self.library.query(include_excluded=True)
        keep = [i for i in items if i.id in soon]
        own = [i for i in items if only_copy(i)]
        kept = {i for p in self.library.playlists() for i in p.item_ids}
        last = [i for i in items if i.favorite or i.id in kept]
        limit = self.service.settings.image_cache_mb * 1024 * 1024
        gone = self.drop_spare_copies() + self.trim_catalogue()
        gone += self.service.images.prune_thumbs(self.library.query(include_excluded=True)[1])
        pruned = self.service.images.prune(limit, keep, own=own, last=last)
        if gone or pruned:
            self.service.storage.forget()
        return pruned

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
        state.last_change_origin = "app"
        state.next_change_at = next_change(now, self.settings).isoformat(timespec="seconds")
        self._save_state(state)

    def postpone(self) -> None:
        """A picture that waited for the panel to wake stays until the next change."""
        state = self.state
        state.next_change_at = next_change(utcnow(), self.settings).isoformat(timespec="seconds")
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
            # A timed hold is over: the rotation takes over now, not at the
            # change that was scheduled before the hold (in quiet hours: at
            # the next change, the panel is asleep).
            state.hold = None
            state.next_change_at = (
                next_change(now, settings) if in_quiet_hours(now, settings) else now
            ).isoformat(timespec="seconds")
            self._save_state(state)
        if state.next_change_at is None:
            self.reschedule()
            return
        if now >= datetime.fromisoformat(state.next_change_at):
            await self.next("schedule")

    def change_starting(self, now: datetime) -> bool:
        """A picture is being shown, or a change was due just now: the panel
        should stay awake for it."""
        if self.busy:
            return True
        due = self.state.next_change_at
        return due is not None and timedelta(0) <= now - datetime.fromisoformat(due) < CHANGE_GRACE

    async def run(self, period: float = 30.0) -> None:
        grown: datetime | None = None
        ahead = False
        # A minute or so on a NAS for a large library: alongside, not first.
        rescoring = asyncio.create_task(run_in_threadpool(self.rescore))
        rescoring.add_done_callback(_log_failure)
        while True:
            try:
                await self.tick()
                if not ahead:  # after a restart; also loads the ditherer's code
                    ahead = True
                    await self.render_ahead()
                if grown is None or utcnow() - grown >= CATALOGUE_EVERY:
                    grown = utcnow()
                    self.grow_catalogue()
                    self.top_up()
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(period)
