"""What the frame shows and when: playlist rotation, history, holds."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import threading
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Iterator
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from functools import partial
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
from .kept import kept_ids
from .library import AlbumOrder, Item, ItemKind, Job, Note, Playlist, PlaylistKind, PlaylistRules
from .library.artists import is_artist
from .library.colors import SCORE_VERSION, analyse, tint_spread, tint_strength
from .library.icloud import only_copy
from .library.images import Unavailable
from .library.museums import Kind
from .library.nationality import life_years, note_years
from .library.photo_text import photo_line, photo_title
from .library.repo import matches, sent_key
from .library.search import fill as fill_by_search
from .library.style import AUTO, auto_preset, toned_only
from .library.themes import (
    COVER_MIN,
    SEARCHABLE,
    other_art_searches,
    theme_of_the_day,
    thin_other_art,
    thin_searches,
)
from .library.viewer import OWNER_ID
from .library.vocabulary import (
    DECORATIVE,
    HIGHLIGHT,
    MANUSCRIPTS,
    OBJECT_CATEGORIES,
    PHOTOGRAPHY,
    SCULPTURE,
    object_category,
    other_art,
    set_aside,
)
from .progress import Stage
from .schedule import FrameSettings, Presentation, in_quiet_hours, next_change

if TYPE_CHECKING:
    from .ai import PolishText
    from .night import Night
    from .service import FrameService

log = logging.getLogger(__name__)

SETTINGS_KEY = "settings"
STATE_KEY = "player"
HISTORY_MAX = 50
PREVIEW_BOARD_SECONDS = 300.0  # a previewed Multi board keeps its photos this long
PREVIEW_BOARDS_KEPT = 64
#: Said in the app (the send bar, a card) when no panel is set up yet.
PANEL_NOT_SET = "Ramka nie jest jeszcze ustawiona: podaj jej adres w Połączeniu z ekranem."
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
#: The works with a study and the works of the day (``study.STATE_KEY``,
#: ``daily.HISTORY_KEY``): the catalogue never deletes them.
STUDY_KEY = "study_items"
DAILY_KEY = "daily_history"
#: Set once the museum works imported before the catalogue are gone.
RESET_KEY = "library_reset"
#: Set once the catalogue's manuscripts are gone.
#: Set once the catalogue has been cleared of what it leaves out now.
SET_ASIDE_KEY = "set_aside_dropped"
#: Bump when ``set_aside`` leaves out more, so the catalogue is cleaned again
#: (1: photographs and manuscripts, 2: reproductions and B&W copies,
#: 3: Girona's photo archive, 4: stamps and Athens' Philatelic Postal Museum,
#: 5: black-and-white photographs from Foto Marburg and KIK-IRPA).
SET_ASIDE_VERSION = 5
#: Version of the colour analysis and score the library's pictures carry.
SCORE_KEY = "suitability_version"
#: Set once the pictures kept from before lost their blank margins
#: (``ImageCache.trim_kept``).
MARGINS_KEY = "margins_trimmed"
#: Set once the elongated works' kept originals were had again in the size
#: they are kept in now (``ImageCache.wide_again``, 2026-11-09).
WIDE_KEY = "wide_originals"
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
#: "Sztuki inne": the share of the catalogue's works each technique keeps,
#: so that Szukaj has some at once (Mateusz 2026-11-06: 6 % in all, 5:4:3:3).
OTHER_ART_SHARES = {PHOTOGRAPHY: 0.02, MANUSCRIPTS: 0.016, SCULPTURE: 0.012, DECORATIVE: 0.012}
#: Works of one technique taken in at a time.
OTHER_ART_BATCH = 40
#: Thin cards of "Sztuki inne" filled a night, the thinnest first; each
#: looks at :data:`THIN_DRAWS` museum works at most. A round for all of them
#: by day, with every turnover, brought the Library of Congress's and the
#: Met's bot walls down on the home address (2026-11-07). A full catalogue
#: takes nothing in any more (Mateusz 2026-11-07).
THIN_CARDS_A_NIGHT = 2
THIN_DRAWS = 60
#: How long the room each technique has is trusted (seconds), for searches.
OTHER_ART_ROOM_FOR = 600.0
#: At night a catalogue still filling up takes in at most this many batches.
NIGHT_BATCHES = 6
# How long a due change may keep the panel from its night sleep.
CHANGE_GRACE = timedelta(minutes=3)


def _log_failure(task: asyncio.Task[object]) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("background task failed", exc_info=task.exception())


def utcnow() -> datetime:
    return datetime.now(UTC)


def searched_key(user: str) -> str:
    """Each person's searches (the owner's under the key from before)."""
    return SEARCHED_ARTISTS_KEY if user == OWNER_ID else f"{SEARCHED_ARTISTS_KEY}:{user}"


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


# Pictures the owner sends from the app (not the schedule, the end of a
# timed hold, nor the button on the frame, which is up already): each is one
# more wake for the battery.
SENT_FROM_APP = frozenset({"app", "manual", "playlist", "previous"})


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


def caption_for(item: Item, polish: PolishText | None = None, dated: bool = True) -> str:
    """ "Artist — Title, date"; the label on the frame goes without the date
    (``dated=False``, Mateusz 2026-11-08)."""
    if item.kind == ItemKind.PHOTO:
        return " · ".join(p for p in (photo_title(item), photo_line(item)) if p)
    parts = [item.artist, polish.title if polish else item.title]
    text = " — ".join(p for p in parts if p)
    date = ((polish.date if polish else "") or item.date_text) if dated else ""
    return f"{text}, {date}" if date else text


def text_block_for(item: Item, polish: PolishText | None = None) -> TextBlock:
    """What the DESCRIPTION mode prints on the mat; with ``polish``, in Polish."""
    if item.kind == ItemKind.PHOTO:
        info = item.photo
        who = info.contributor if info and info.contributor else ""
        return TextBlock(title=photo_title(item), meta=[m for m in (photo_line(item), who) if m])
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
        #: The catalogue turns over and the cache is tidied at night
        #: (:mod:`frame_server.night`); set when the server runs its background.
        self.at_night = False
        #: The catalogue was full when last measured: by day (with the
        #: night queue) the files are not counted again until the night.
        self._full = False
        #: When the room of "Sztuki inne" was counted (monotonic), and it.
        self._other_art_room: tuple[float, dict[str, int]] = (0.0, {})
        #: What the line was last checked for new works with (by day).
        self._caught_up_from: tuple[object, ...] = ()
        self._changes = 0  # under way: from the download of the original to the push
        #: A change made early (:meth:`next_early`): the one after it counts
        #: from the time this one was due, not from now.
        self._due_at: datetime | None = None
        #: The photos of lately previewed Multi boards (:meth:`preview_board`).
        self._preview_boards: dict[tuple[object, ...], tuple[float, list[str]]] = {}

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

    def remember_sent(self, item: Item, user: str = OWNER_ID) -> None:
        """A photo ``user`` sent once, shown or queued, goes first in their
        own "Historia przesłanych" (Mateusz, 2026-10-31: one for each
        person); the playlist is made when first needed, and again if they
        deleted it."""
        if item.look is None:
            return
        key = sent_key(user)
        playlist_id = self.library.get_state(key, None)
        playlist = self.library.playlist(playlist_id) if playlist_id is not None else None
        if playlist is None or playlist.owner != user:
            playlist = Playlist(name=SENT_NAME, kind=PlaylistKind.MANUAL, owner=user)
        ids = [item.id, *(i for i in playlist.item_ids if i != item.id)]
        saved = self.library.save_playlist(playlist.model_copy(update={"item_ids": ids}))
        self.library.set_state(key, saved.id)

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

    def taste(self, user: str | None = None) -> list[str]:
        """Artists ``user`` likes (None: the household together), most liked
        first: favourites count most, then works kept in the library (not
        the ones the server picked) and artists lately searched for."""
        scores: Counter[str] = Counter()
        hearts = None if user is None else self.library.favorites(user)
        for item in self.library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]))[1]:
            if is_artist(item.artist) and not other_art(item):
                liked = item.favorite if hearts is None else item.id in hearts
                scores[item.artist] += 3 * liked + (not item.pooled)
        searched: Counter[str] = Counter()
        for key in [searched_key(user)] if user is not None else self._searched_keys():
            searched.update(self.library.get_state(key, []))
        for artist, times in searched.items():
            scores[artist] += min(times, SEARCHED_ARTIST_MAX)
        return [artist for artist, score in scores.most_common(TASTE_ARTISTS) if score > 0]

    def hearted(self, user: str) -> list[str]:
        """Artists of the works ``user`` gave a heart, the most hearts
        first (the cards "Ponieważ lubisz" in Discover, Mateusz 2026-11-07:
        "bazuj tylko na serduszkach")."""
        hearts = self.library.favorites(user)
        scores: Counter[str] = Counter()
        for item in self.library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]))[1]:
            if item.id in hearts and is_artist(item.artist) and not other_art(item):
                scores[item.artist] += 1
        return [artist for artist, _ in scores.most_common()]

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

    def _may_catch_up(self, settings: FrameSettings) -> bool:
        if not self.at_night:
            return True
        key = (self.library.catalogue_stamp(), self.library.stamp()[1], settings.playlist_id)
        if key == self._caught_up_from:
            return False
        self._caught_up_from = key
        return True

    def catch_up(self) -> bool:
        """The night's task: works new to the rotation (the catalogue
        turned over) come before pictures shown lately."""
        state, settings = self.state, self.settings
        if not self._catch_up(state, settings):
            return False
        self._save_state(state)
        return True

    def _pop_next(
        self, state: PlayerState, settings: FrameSettings, picks: bool = True
    ) -> Item | None:
        while picks and state.requested:
            item = self.library.get(state.requested.pop(0))
            if item is not None:  # asked for: shown even if left out of the rotation
                return item
        spare = self.library.spare_copies() | self.library.hidden().ids
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
        """The next pictures. Works new to the rotation are let in when
        they can have come: with the night queue, after works joined the
        catalogue, someone's hearts or a playlist changed, not at every
        look at Teraz (which went through the whole playlist each time
        once it went round)."""
        state, settings = self.state, self.settings
        if not state.queue:
            self._refill(state, settings)
            self._save_state(state)
        elif self._may_catch_up(settings) and self._catch_up(state, settings):
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
        ``item`` is current, else the photos that would join it next.

        Kept for :data:`PREVIEW_BOARD_SECONDS`: the app asks for one preview
        per grid, margin and mat, and finding the photos went through the
        whole catalogue each time (about 1 s on the NAS, on the server's
        event loop; Mateusz 2026-11-08: "buduje się ekstremalnie długo")."""
        state = self.state
        keep = state.current_group if state.current_item_id == item.id else None
        if not self.multi(item, settings):
            return [item]
        pres = settings.photo
        if pres.multi_random and not keep:
            # A random count, the same each time for one photo: the board the
            # app draws and the preview it then gets must hold the same photos.
            count = random.Random(item.id).randint(MIN_PHOTOS, MAX_PHOTOS)
            photo = pres.model_copy(update={"multi_random": False, "multi_count": count})
            settings = settings.model_copy(update={"photo": photo})
            pres = photo
        key = (
            item.id,
            pres.multi_random,
            pres.multi_count,
            settings.playlist_id,
            state.current_item_id,
            tuple(keep or ()),
            tuple(state.queue[:MAX_PHOTOS]),
        )
        now = time.monotonic()
        kept = self._preview_boards.get(key)
        if kept is not None and now - kept[0] < PREVIEW_BOARD_SECONDS:
            found = [self.library.get(i) for i in kept[1]]
            if all(i is not None for i in found):
                return [i for i in found if i is not None]
        # A playlist of art has no photos to join it: the library's photos
        # and those sent once fill the board, the same ones each time for
        # one photo. Photos are never copies of one another, so a plain look
        # through the items does what a library query did, many times faster.
        listed = [
            i
            for i in self.library.all_items()
            if i.kind == ItemKind.PHOTO and i.look is None and not i.excluded
        ]
        sent = (self.library.get(i) for i in sorted(self.library.sent_photo_ids()))
        spare = sorted([*listed, *(i for i in sent if i is not None)], key=lambda i: i.id)
        random.Random(item.id).shuffle(spare)
        board = self.board(item, state, settings, keep, spare)  # state is a copy: nothing is taken
        if len(self._preview_boards) > PREVIEW_BOARDS_KEPT:
            self._preview_boards.clear()
        self._preview_boards[key] = (now, [i.id for i in board])
        return board

    def chosen_board(
        self, item: Item, ids: list[str], settings: FrameSettings
    ) -> list[Item] | None:
        """A preview's Multi board of the owner's chosen photos (``ids``,
        ``FrameSettings.multi_photos``) as many as the board holds, ``item``
        first; more than chosen: the photos that would join ``item`` fill
        the rest. None when fewer than two of them are left."""
        chosen = [i for i in (self.library.get(x) for x in ids) if i and not i.excluded]
        chosen = [i for i in chosen if i.kind == ItemKind.PHOTO][:MAX_PHOTOS]
        if item.id in {i.id for i in chosen}:
            chosen = [item, *(i for i in chosen if i.id != item.id)]
        if len(chosen) < MIN_PHOTOS:
            return None
        pres = settings.photo
        if pres.multi_random:  # the same count each time for this choice
            count = random.Random(",".join(i.id for i in chosen)).randint(MIN_PHOTOS, MAX_PHOTOS)
        else:
            count = pres.multi_count
        board = chosen[:count]
        if len(board) < count:
            taken = {i.id for i in board}
            more = (i for i in self.preview_board(item, settings) if i.id not in taken)
            board += list(more)[: count - len(board)]
        return board

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
        tint = None
        if toned_only(item):
            # Black and white or sepia: how strong the tint is tells them apart.
            thumb = self.service.images.thumb_path(item)
            if thumb.is_file():
                with Image.open(thumb) as img:
                    tint = tint_strength(img)
        return auto_preset(item, tint)

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
        base.caption = caption_for(item, polish, dated=False) if pres.label else None
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
                self.service.progress.begin(
                    item.title, keep=True, origin=origin_of(reason), item_id=item.id
                )
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
                base = max(now, self._due_at) if self._due_at is not None else now
                state.next_change_at = next_change(base, settings).isoformat(timespec="seconds")
                state.last_error = None
                for shown in board:
                    self.library.record_shown(shown.id, reason)
                # Shown now (e.g. sent from the app) while waiting its turn in
                # the rotation: to the back, or the schedule shows it again
                # the same day.
                ids = {shown.id for shown in board}
                if again := [i for i in state.queue if i in ids]:
                    state.queue = [i for i in state.queue if i not in ids] + again
                self._save_state(state)
                if reason in SENT_FROM_APP:
                    self.service.status.note_sent(now)  # a wake on top of the schedule
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
                # New settings.
                self.service.progress.begin(item.title, origin="app", item_id=item.id)
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
            title=photo_title(item) if item.kind == ItemKind.PHOTO else item.title,
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
            raise RuntimeError(PANEL_NOT_SET)
        outcome = await self.service.push_current(wait=120)
        if not outcome.fetched:
            # Waiting for the frame to wake (economy, asleep, away) is no
            # error: the app says when it shows, the failures raise instead.
            log.info("waiting for the frame: %s (%s)", outcome.message, outcome.content_url)

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
            # The app's bar from the download on.
            progress.begin(item.title, origin=origin, item_id=item.id)
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
            await run_in_threadpool(self.trim_cache, not self.at_night)
        except OSError as err:
            log.warning("trimming the image cache failed: %s", err)
        await run_in_threadpool(self.top_up)

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
        items = self.library.playlist_items(playlist)
        have = len(self.fresh(items, settings))
        if have >= POOL_LOW:
            return None
        want = POOL_SIZE - have
        if playlist.limit is not None:
            # A full playlist goes round its own works again.
            want = min(want, playlist.limit - len(items))
            if want <= 0:
                return None
        rules = rules.model_copy(update={"kinds": [ItemKind.ARTWORK]})
        if playlist.theme is None:
            # The owner's own playlist: what Szukaj finds for its choices.
            return importer.start_job(
                "pool", lambda job: fill_by_search(importer, rules, want, job, pooled=True)
            )
        return importer.start_job("pool", lambda job: importer.fill(rules, want, job, pooled=True))

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
        about to be shown or picked for Suggestions, and those with a page
        Claude wrote."""
        state = self.state
        protected = {state.current_item_id or "", *state.current_group, *state.queue}
        protected |= set(state.requested)
        protected |= {i for p in self.library.playlists() for i in p.item_ids}
        protected |= set(self.library.get_state(SUGGESTIONS_KEY, []))
        return protected | self._written_about()

    def _written_about(self) -> set[str]:
        """Works with a study or a work of the day's page: deleting one would
        delete its text too, and Claude would be paid to write it again."""
        ids = set(self.library.get_state(STUDY_KEY, []))
        return ids | set(self.library.get_state(DAILY_KEY, {}).values())

    def keep_searched(self, items: Iterable[Item], found: str = "") -> None:
        """Works a search showed join the catalogue in the background (as
        the catalogue's own draws do, so not while tests run the server);
        those of "Sztuki inne" while their technique has room. ``found``:
        the museum search that found them, which they fit from then on."""
        settings = self.service.settings
        if settings.scheduler and settings.catalogue_mb and not self._full:
            self.service.importer.keep_searched(items, room=self.other_art_room(), found=found)

    def keep_spare(self, items: Iterable[Item]) -> None:
        """Works a search brought but did not show join the catalogue too,
        after the shown ones (:meth:`Importer.keep_spare`)."""
        settings = self.service.settings
        if settings.scheduler and settings.catalogue_mb and not self._full:
            self.service.importer.keep_spare(items, room=self.other_art_room())

    def _catalogue_works(self) -> list[Item]:
        """The works the server picked (``pooled``), excluded ones too."""
        return [i for i in self.library.query(include_excluded=True)[1] if i.pooled]

    def other_art_room(self, fresh: bool = False) -> dict[str, int]:
        """How many more works each technique of "Sztuki inne" may have in
        the catalogue (only those with room), as last counted within
        :data:`OTHER_ART_ROOM_FOR` unless ``fresh``."""
        counted, room = self._other_art_room
        if fresh or time.monotonic() - counted >= OTHER_ART_ROOM_FOR or counted == 0.0:
            works = self._catalogue_works()
            have = Counter(c for i in works if (c := object_category(i)) is not None)
            room = {
                key: wanted - have[key]
                for key, share in OTHER_ART_SHARES.items()
                if (wanted := int(share * len(works))) > have[key]
            }
            self._other_art_room = (time.monotonic(), room)
        return room

    def _add_other_art(self, job: Job, thin: bool = False) -> None:
        """Top up each technique of "Sztuki inne" towards its share of the
        catalogue, :data:`OTHER_ART_BATCH` works at a time; at night
        (``thin``) first the works of the themes whose cards have too few for
        a cover (:data:`THIN_CARDS_A_NIGHT`), whatever room (their technique
        keeps to its share by :meth:`trim_other_art` the next night, the
        works seen least going first)."""
        thinnest = sorted(thin_other_art(self.library), key=lambda pair: pair[1]) if thin else []
        for found, count in thinnest[:THIN_CARDS_A_NIGHT]:
            category = next(k for k in found.terms if k in OBJECT_CATEGORIES)
            rules = found.rules()
            part = Job(id=job.id, description=f"other arts: {found.key}")
            self.service.importer.collect_searched(
                category,
                found.searches(),
                COVER_MIN - count,
                part,
                fits=partial(matches, rules=rules),
                most=THIN_DRAWS,
            )
            job.item_ids += part.item_ids
            log.info("catalogue: %d works for %s taken in", len(part.item_ids), found.key)
        searches = other_art_searches()
        for category, missing in self.other_art_room(fresh=True).items():
            part = Job(id=job.id, description="other arts")  # its own count
            self.service.importer.collect_other_art(
                category, min(missing, OTHER_ART_BATCH), part, queries=searches.get(category, ())
            )
            job.item_ids += part.item_ids
            log.info("catalogue: %d works of %s taken in", len(part.item_ids), category)
        self.other_art_room(fresh=True)

    def trim_other_art(self) -> int:
        """Keep each technique of "Sztuki inne" within its share of the
        catalogue (after the limit was lowered, or searches kept many):
        the ones seen least lately go first, never those the owner kept,
        liked, framed or put in a playlist. Returns how many went."""
        works = self._catalogue_works()
        protected = self._protected()
        images = self.service.images
        gone: list[Item] = []
        for category, share in OTHER_ART_SHARES.items():
            own = [i for i in works if object_category(i) == category]
            over = len(own) - int(share * len(works))
            if over <= 0:
                continue
            spare = [
                i
                for i in own
                if not i.show_count and not i.favorite and not i.framing and i.id not in protected
            ]

            def order(item: Item) -> tuple[bool, float, str]:
                seen = images.used_at(item)
                return seen is not None, seen or 0.0, item.added_at

            spare.sort(key=order)
            gone += spare[:over]
        if gone:
            self._forget(gone)
            self._other_art_room = (0.0, {})
            log.info("catalogue: %d works of Sztuki inne over their share deleted", len(gone))
        return len(gone)

    def searched_for(self, artists: list[str], user: str = OWNER_ID) -> None:
        """Artists ``user`` asked for in Szukaj count towards their
        :meth:`taste`; the same search again (e.g. coming back to it) once."""
        if not artists:
            return
        key = searched_key(user)
        recent: list[str] = self.library.get_state(key, [])
        if recent[-len(artists) :] == artists:
            return
        self.library.set_state(key, (recent + artists)[-SEARCHED_ARTISTS_KEPT:])

    def _searched_keys(self) -> list[str]:
        users = getattr(self.service, "users", None)
        people = [u.id for u in users.users()] if users is not None else [OWNER_ID]
        return [searched_key(u) for u in people]

    def trim_catalogue(self) -> int:
        """Keep the catalogue's thumbnails within ``catalogue_mb``: works the
        server added that nobody kept go, the longest there first. Works the
        owner looked at (their original is here: a card, the whole screen, a
        study) go last, the least recently seen first: their originals have
        a limit of their own, and looking at one again is quick."""
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

        def order(item: Item) -> tuple[bool, float, str]:
            seen = images.used_at(item)
            return seen is not None, seen or 0.0, item.added_at

        spare.sort(key=order)
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

    def grow_catalogue(self, night: bool = False) -> Job | None:
        """Add a batch of museum works to the catalogue while its thumbnails
        take less than ``catalogue_mb``; themes and random draws of every
        kind, so the app can browse widely and filter by colour. A full
        catalogue takes nothing in: no works are drawn to replace others
        (Mateusz 2026-11-07, "gdy katalog jest pełny, nie odciągajmy więcej
        dzieł"); Konfiguracja says so (``StorageView.catalogue_full``). It is
        only trimmed back to the limit. With the night queue
        (:attr:`at_night`) a full catalogue is measured again only at night
        or when the limit changes (:meth:`limit_changed`)."""
        importer = self.service.importer
        limit = self.service.settings.catalogue_mb * 1024 * 1024
        if not limit or any(
            job.description == "catalogue" and not job.finished for job in importer.jobs.values()
        ):
            return None
        if self._full and self.at_night and not night:
            return None
        full = self._full = self.service.images.thumbs_size() >= limit
        if full:
            self.trim_catalogue()  # a lower limit, or a batch past it
            return None
        # "Arcydzieła muzeów" needs the museums' highlights in the catalogue,
        # which works taken in before 0.42 never say they are: asked for on
        # their own, once a day, while the catalogue has too few.
        tried = self.library.get_state(HIGHLIGHTS_KEY, "")
        highlights = (
            night
            or not tried
            or utcnow() - datetime.fromisoformat(tried) >= CATALOGUE_HIGHLIGHT_EVERY
        )
        if highlights:
            self.library.set_state(HIGHLIGHTS_KEY, utcnow().isoformat())
        queries = [search for theme in SEARCHABLE for search in theme.searches()]
        queries = random.sample(queries, min(8, len(queries)))
        if night:  # antiquity's cards need works of their own for a cover
            queries = [*thin_searches(self.library), *queries]

        def grow(job: Job) -> None:
            if highlights:
                self._add_highlights(job)
            importer.collect(
                CATALOGUE_BATCH,
                job,
                queries=queries,
                kinds=CATALOGUE_KINDS,
                highlights=CATALOGUE_HIGHLIGHTS,
            )
            self.trim_other_art()
            self._add_other_art(job, thin=night)

        return importer.start_job("catalogue", grow)

    def limit_changed(self) -> None:
        """The catalogue's limit changed: measured again before it is
        trusted to be full."""
        self._full = False

    @property
    def catalogue_full(self) -> bool:
        """The catalogue reached its limit when last measured: works the
        server would add itself (draws, what Szukaj showed) stay out."""
        return self._full

    def grow_at_night(self, night: Night) -> int:
        """The night's task: a catalogue still filling up takes in batches
        while the night lasts; a full one nothing. How many batches."""
        batches = 0
        while batches < NIGHT_BATCHES and night.quiet():
            job = self.grow_catalogue(night=True)
            if job is None:
                break
            batches += 1
            while not job.finished:  # in its own thread, gently for the museums
                if not night.sleep(5.0):
                    return batches
            log.info("night: catalogue took in %d works", len(job.item_ids))
        return batches

    def _fix_up(self) -> None:
        """Once after an update: the kept pictures without their blank
        margins, the pictures analysed again, the thumbnails of works shown
        from another source's copy made from it, then the elongated works'
        originals had again larger."""
        if not self.library.get_state(MARGINS_KEY, False):
            trimmed = self.service.images.trim_kept()
            self.library.set_state(MARGINS_KEY, True)
            log.info("margins: %d kept pictures trimmed", trimmed)
        self.rescore()
        self.service.sharper.thumbs_again()
        if not self.library.get_state(WIDE_KEY, False):
            items = self.library.query(include_excluded=True)[1]
            grown = self.service.images.wide_again(items)
            self.library.set_state(WIDE_KEY, True)
            log.info("elongated works: %d kept originals larger", grown)

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
                    colors, tags, value, shares = analyse(img, self.service.palette, spread)
            except OSError:
                log.warning("rescore: cannot read %s", path)
                continue
            changes: dict[str, Any] = {
                "colors": colors,
                "color_tags": tags,
                "color_shares": shares,
                "tint_spread": spread,
            }
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
        kept |= self._written_about()
        gone = [
            i
            for i in self.library.query(include_excluded=True)[1]
            if i.pooled
            and set_aside(i, OBJECT_CATEGORIES)  # "Sztuki inne" stay (2026-11-06)
            and not i.favorite
            and not i.framing
            and i.id not in kept
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
        kept |= self._written_about()
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

    def trim_cache(self, whole: bool = True) -> int:
        """Delete the least recently used museum originals over the size
        limit (the current picture and the next ones stay); ``whole``: also
        spare copies of works, the catalogue over its limit and thumbnails
        of works browsed but not kept (at night, and when a limit is
        lowered; after each change only without the night queue)."""
        with self._trimming:
            return self._trim_cache(whole)

    def _trim_cache(self, whole: bool) -> int:
        state = self.state
        soon = {state.current_item_id, *state.current_group, *state.requested}
        soon |= set(state.queue[:PREFETCH])
        _, items = self.library.query(include_excluded=True)
        keep = [i for i in items if i.id in soon]
        own = [i for i in items if only_copy(i)]
        kept = kept_ids(self.service)
        last = [i for i in items if i.favorite or i.id in kept]
        limit = self.service.settings.image_cache_mb * 1024 * 1024
        gone = 0
        if whole:
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

    async def next_early(self) -> Item | None:
        """The scheduled change now, a little before its time: the panel woke
        for it (its alarm rings early, its clock may run fast). The change
        after it is counted from this one's time."""
        due = self.state.next_change_at
        self._due_at = datetime.fromisoformat(due) if due is not None else None
        try:
            return await self.next("schedule")
        finally:
            self._due_at = None

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
        rescoring = asyncio.create_task(run_in_threadpool(self._fix_up))
        rescoring.add_done_callback(_log_failure)
        while True:
            try:
                await self.tick()
                if not ahead:  # after a restart; also loads the ditherer's code
                    ahead = True
                    await self.render_ahead()
                if grown is None or utcnow() - grown >= CATALOGUE_EVERY:
                    grown = utcnow()
                    # Off the event loop: the size of the thumbnails is a
                    # walk over the disk, a top-up queries the whole
                    # catalogue; the frame's questions do not wait for them
                    # (104 s after a start, 2026-11-04).
                    await run_in_threadpool(self.grow_catalogue)
                    await run_in_threadpool(self.top_up)
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(period)
