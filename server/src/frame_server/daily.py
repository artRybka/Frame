"""Discover's work of the day: one work from the catalogue a day, at the top
of Propozycje, with its own page written by Claude (``ai.daily``).

The work is picked without the model: museum works only, well suited to
the e-paper, large enough, not an artist of the last few weeks and never a
work of the last year; a little ahead are works of the season, works with
a round anniversary this year, artists the owner likes and works whose
museum tells something about them. Every day is kept, so a past day opens
the same work again ("Poprzednie dzieła dnia").
"""

from __future__ import annotations

import contextlib
import logging
import random
import re
import threading
import time
from concurrent.futures import Future
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from PIL import Image

from .ai.daily import KIND, DailyJob, Detail, Essay
from .ai.jobs import text_hash
from .imaging.layout import load_image
from .library import Item, ItemKind, PlaylistRules
from .library.models import Note
from .library.vocabulary import artist_matches, is_photograph

if TYPE_CHECKING:
    from .ai import AiWorker
    from .later import LaterWorks
    from .library import Library
    from .player import Player

log = logging.getLogger(__name__)

HISTORY_KEY = "daily_history"
#: Days kept; a work is not picked again within a year.
KEEP_DAYS = 400
REPEAT_DAYS = 365
#: An artist comes back after this many days at the earliest.
ARTIST_DAYS = 30
#: The best suited works the pick looks among.
POOL = 800
MIN_SUITABILITY = 0.4
#: The longer side of the original, when the museum says (pixels).
MIN_SIDE = 1000
#: Works like the work of the day the model chooses among.
CANDIDATES = 12
SAME_ARTIST = 4
#: How often the background picks the day's work and asks for its page.
TICK_SECONDS = 1800.0
#: The fragments' pictures ("Detale"): their longer side, and how long kept.
DETAIL_SIDE = 1600
DETAIL_DAYS = 30

SEASON_WORDS = {
    "winter": ("winter", "snow", "ice", "skating", "zima", "śnieg", "subject:winter"),
    "spring": ("spring", "blossom", "wiosna", "kwitn"),
    "summer": ("summer", "lato", "beach", "plaża", "bathing"),
    "autumn": ("autumn", "jesień", "harvest", "żniwa", "fallen leaves"),
}
_YEARS = re.compile(r"\b(1[0-9]{3})\b")


def season(day: date) -> str:
    return ("winter", "spring", "summer", "autumn")[day.month % 12 // 3]


def of_season(item: Item, day: date) -> bool:
    words = SEASON_WORDS[season(day)]
    text = " ".join([item.title, *item.keywords, *item.terms, *item.subjects]).lower()
    return any(w in text for w in words)


def round_anniversary(item: Item, day: date) -> bool:
    """The work, or its author's birth or death, is a multiple of 25 years
    (at least 50) old this year."""
    years = {item.year} if item.year else set()
    years |= {int(y) for y in _YEARS.findall(item.artist_bio)}
    return any((age := day.year - y) >= 50 and age % 25 == 0 for y in years if y)


def score(item: Item, day: date, taste: list[str], rng: random.Random) -> float:
    value = item.suitability or 0.0
    value += 0.25 * of_season(item, day)
    value += 0.2 * round_anniversary(item, day)
    value += 0.15 * bool(taste and item.artist and artist_matches(item.artist, taste))
    value += 0.1 * (len(item.description) >= 200)
    return value + rng.uniform(0, 0.35)


class Daily:
    def __init__(self, library: Library, player: Player, ai: AiWorker, job: DailyJob) -> None:
        self.library = library
        self.player = player
        self.ai = ai
        self.job = job
        job.day_of = self.day_of
        job.candidates = self.candidates
        self._lock = threading.Lock()
        self._candidates: dict[str, list[str]] = {}
        self._stop = threading.Event()
        self._cutting = threading.Lock()
        self.details_dir = job.images.thumbs.parent / "details"
        #: Looks up what the pages say a work led to; set by the service.
        self.later: LaterWorks | None = None

    # -- the days ----------------------------------------------------------

    def history(self) -> dict[str, str]:
        """Item ids by day (ISO dates)."""
        return dict(self.library.get_state(HISTORY_KEY, {}))

    def day_of(self, item_id: str) -> date | None:
        """The last day ``item_id`` was the work of."""
        days = [d for d, i in self.history().items() if i == item_id]
        return date.fromisoformat(max(days)) if days else None

    def item(self, day: date) -> Item | None:
        """The work of ``day`` as picked; None for a day not picked."""
        item_id = self.history().get(day.isoformat())
        return self.library.get(item_id) if item_id else None

    def pick(self, day: date) -> Item | None:
        """The work of ``day``, picked now if it has none (or its work is gone)."""
        with self._lock:
            found = self.item(day)
            if found is not None and not found.excluded:
                return found
            found = self.choose(day)
            if found is not None:
                history = self.history()
                history[day.isoformat()] = found.id
                cutoff = (day - timedelta(days=KEEP_DAYS)).isoformat()
                self.library.set_state(
                    HISTORY_KEY, {d: i for d, i in sorted(history.items()) if d >= cutoff}
                )
            return found

    def choose(self, day: date) -> Item | None:
        history = self.history()
        recent = {
            i for d, i in history.items() if d >= (day - timedelta(days=REPEAT_DAYS)).isoformat()
        }
        artists_cutoff = (day - timedelta(days=ARTIST_DAYS)).isoformat()
        recent_artists = [
            item.artist
            for d, i in history.items()
            if artists_cutoff <= d < day.isoformat() and (item := self.library.get(i)) is not None
        ]
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK], min_suitability=MIN_SUITABILITY)
        pool = [
            i
            for i in self.library.query(rules, sort="suitability", limit=POOL)[1]
            if i.id not in recent
            and i.look is None
            and i.artist
            and not is_photograph(i)
            and max(i.width or MIN_SIDE, i.height or MIN_SIDE) >= MIN_SIDE
            and not (recent_artists and artist_matches(i.artist, recent_artists))
        ]
        if not pool:
            return None
        rng = random.Random(day.toordinal())
        taste = self.player.taste()
        return max(pool, key=lambda i: score(i, day, taste, rng))

    # -- works like it -----------------------------------------------------

    def candidates(self, item: Item) -> list[Item]:
        """Works of the catalogue like ``item``: by its artist first, then of
        its styles and periods, close in time."""
        if item.id in self._candidates:
            found = (self.library.get(i) for i in self._candidates[item.id])
            return [i for i in found if i is not None]
        picked: list[Item] = []

        def add(items: list[Item], limit: int) -> None:
            for other in items:
                if len(picked) >= limit:
                    return
                twin = any(p.title == other.title and p.artist == other.artist for p in picked)
                if other.id != item.id and other.look is None and other not in picked and not twin:
                    picked.append(other)

        if item.artist:
            same = PlaylistRules(kinds=[ItemKind.ARTWORK], artists=[item.artist])
            add(self.library.query(same, sort="suitability", limit=40)[1], SAME_ARTIST)
        for term in [t for t in item.terms if t.startswith(("style:", "years:", "technique:"))]:
            near = PlaylistRules(kinds=[ItemKind.ARTWORK], terms=[term])
            items = self.library.query(near, sort="suitability", limit=60)[1]
            if item.year:
                items = [i for i in items if i.year and abs(i.year - item.year) <= 40]
            add(items, CANDIDATES)
        self._candidates[item.id] = [i.id for i in picked]
        return picked

    # -- its page ------------------------------------------------------------

    def ask(self, item: Item) -> Future[Note | None] | None:
        """Asks for the work's page unless it has one (or is off)."""
        if not self.job.enabled() or self.job.essay(item) or self.job.failed(item):
            return None
        return self.ai.need_now(item.id, KIND)

    # -- its fragments ("Detale") ----------------------------------------------

    def detail_path(self, item: Item, box: Detail) -> Path:
        key = text_hash(f"{box.x:.4f}", f"{box.y:.4f}", f"{box.w:.4f}", f"{box.h:.4f}")[:10]
        return self.details_dir / f"{item.file_stem}-{key}.jpg"

    def detail(self, item: Item, index: int, essay: Essay | None = None) -> Path | None:
        """The page's ``index``th fragment cut from the work's original; None
        when the page has no such fragment. All of them are cut at once,
        from the museum's full size when it can be had. ``essay``: another
        write-up than the day's (a study of the work)."""
        essay = essay or self.job.essay(item)
        if essay is None or not 0 <= index < len(essay.details):
            return None
        path = self.detail_path(item, essay.details[index])
        if path.is_file():
            return path
        with self._cutting:
            if not path.is_file():
                self._cut(item, essay.details)
        return path

    def _cut(self, item: Item, boxes: list[Detail]) -> None:
        img = self._full_size(item)
        width, height = img.size
        self.details_dir.mkdir(parents=True, exist_ok=True)
        for box in boxes:
            left, top = round(box.x * width), round(box.y * height)
            right, bottom = round((box.x + box.w) * width), round((box.y + box.h) * height)
            crop = img.crop((left, top, right, bottom))
            crop.thumbnail((DETAIL_SIDE, DETAIL_SIDE), Image.Resampling.LANCZOS)
            path = self.detail_path(item, box)
            tmp = path.with_suffix(".tmp")
            crop.convert("RGB").save(tmp, "JPEG", quality=88, optimize=True)
            tmp.replace(path)
        cutoff = time.time() - DETAIL_DAYS * 86400
        for old in self.details_dir.glob("*.jpg"):
            with contextlib.suppress(OSError):
                if old.stat().st_mtime < cutoff:
                    old.unlink()

    def _full_size(self, item: Item) -> Image.Image:
        """The museum's file as it is (the cached original is cut down to
        the panel's size); the cached one when the museum's cannot be had."""
        images = self.job.images
        if item.image_url and item.source not in images.fetchers:
            try:
                return images.sample(item.image_url)
            except (httpx.HTTPError, OSError) as err:
                log.info("full size of %s failed: %s; the cached original", item.id, err)
        path, _ = images.picture(item, urgent=True)
        return load_image(path)

    def tick(self, day: date | None = None) -> None:
        item = self.pick(day or date.today())
        if item is not None:
            self.ask(item)
            essay = self.job.essay(item)
            if self.later is not None and essay and self.later.missing(item.id, essay.legacy):
                self.later.look(item, essay.legacy)  # what it led to, with pictures

    def run(self) -> None:
        """Picks the day's work and asks for its page, so they are ready when
        Discover opens; the first tick waits for the server to settle."""
        wait = 60.0
        while not self._stop.wait(wait):
            wait = TICK_SECONDS
            try:
                self.tick()
            except Exception:
                log.exception("work of the day")

    def stop(self) -> None:
        self._stop.set()
