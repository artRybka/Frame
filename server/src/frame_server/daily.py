"""Discover's study of the day: one work from the catalogue a day, at the top
of Odkrywaj, with its own page written by Claude (``ai.daily``). Once written,
the page is the work's study like any other (``Study.adopt``).

Rules rank the works: museum works only, large enough, not an artist of
the last few weeks and never a work of the last year; a little ahead are
works of the season, works with a round anniversary this year, artists the
owner likes and works whose museum tells something about them; sketches by
their titles and pale sheets go last. The first ten (each by another
artist) go to the curator (``ai.study_pick``, Mateusz 2026-11-11), who
looks at their pictures, sets aside what is no finished work worth a page
and chooses one; without it the rules' first stands. Every day is kept, so
a past day opens the same work again.
"""

from __future__ import annotations

import contextlib
import logging
import random
import re
import threading
import time
import zlib
from collections.abc import Callable
from concurrent.futures import Future
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from PIL import Image

from .ai.daily import KIND, DailyJob, Detail, Essay, Seen
from .ai.jobs import text_hash
from .ai.study import KIND as STUDY
from .ai.study_pick import Choice, copy_key
from .ai.study_pick import choose as curate
from .imaging.align import align
from .imaging.layout import load_image
from .library import Item, ItemKind, PlaylistRules
from .library.artists import is_artist
from .library.colors import PALE_INK, ink_share
from .library.cultures import circle
from .library.images import display_copy
from .library.models import Note
from .library.nationality import NATIONALITIES
from .library.vocabulary import artist_matches, is_grey_copy, is_photograph, other_art
from .sharper import WEAK_SIDE, archive_own

if TYPE_CHECKING:
    from .ai import AiWorker
    from .ai.client import Claude
    from .artist_works import ArtistWorks
    from .later import LaterWorks
    from .library import Library
    from .player import Player
    from .sharper import Sharper

log = logging.getLogger(__name__)

HISTORY_KEY = "daily_history"
#: Works set aside by hand for a day ("Wylosuj inne" in Konfiguracja):
#: {"day": ISO date, "items": [ids]}; only today's are kept.
SKIPPED_KEY = "daily_skipped"
#: Days kept; a work is not picked again within a year.
KEEP_DAYS = 400
REPEAT_DAYS = 365
#: An artist comes back after this many days at the earliest.
ARTIST_DAYS = 30
#: The works of the catalogue the pick looks among, drawn for the day.
POOL = 800
#: The longer side of the original, when the museum says (pixels).
MIN_SIDE = 1000
#: Works like the work of the day the model chooses among.
CANDIDATES = 12
#: The rules' best works (each by another artist) the curator looks at.
SHORTLIST = 10
#: Shortlists the curator is asked about for one day, when it sets aside a
#: whole one.
SHORTLISTS = 2
#: Works the curator set aside ("no finished work worth a page"): never
#: shortlisted again. {id: what it saw}, the newest last.
UNFIT_KEY = "daily_unfit"
UNFIT_MAX = 5000
#: Works the curator set aside for their photograph alone: {id: the copy
#: shown then (``study_pick.copy_key``)}; back once another copy is shown.
POOR_COPY_KEY = "daily_poor_copy"
#: The curator's choice of each day: {day: {"item", "reason", "unfit"}}.
CURATED_KEY = "daily_curated"
#: A title that calls the work a sketch or studies (the rules put it last;
#: the curator may still choose one that stands as a work by itself).
SKETCH_TITLE = re.compile(
    r"\b(stud(?:y|ies)|sketch(?:es|book|ing)?|croquis|esquisses?|[ée]tudes?|studien?"
    r"|skizzen?(?:buch)?|schets(?:en|boek)?|szkic\w*|studi(?:um|a)|notebook|carnet)\b",
    re.IGNORECASE,
)
#: What a sketch's title and a pale sheet take from a work's score.
SKETCH_PENALTY = 0.3
PALE_PENALTY = 0.3
#: The copy's quality (Mateusz 2026-11-11: "bierz pod uwagę także jakość
#: kopii dzieła"): a picture as long as the frame's side (2560 px) shows
#: the work whole, one shorter than ``sharper.WEAK_SIDE`` is worth a sharper
#: copy, which may not be found.
FRAME_SIDE = 2560
SHARP_BONUS = 0.15
WEAK_PENALTY = 0.25
#: "W tym samym czasie": works made a few years either side of the work,
#: elsewhere and by others (Mateusz 2026-11-02); one row scrolled sideways
#: since 2026-11-03 ("pokazuj więcej dzieł").
SAME_TIME = 10
SAME_TIME_YEARS = 5
#: The catalogue's works of those years looked among.
SAME_TIME_POOL = 300
#: Of those, from other cultural circles than the work's (Mateusz
#: 2026-11-06: "przy twórcy europejskim także coś z Azji"); looked for
#: further either side when the catalogue has none so near.
OTHER_CIRCLES = 2
OTHER_CIRCLE_YEARS = 25
#: Where they stand in the row: the second, seen without scrolling, and
#: the fifth.
OTHER_CIRCLE_PLACES = (1, 4)
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
    value = 0.25 * of_season(item, day)
    value += 0.2 * round_anniversary(item, day)
    value += 0.15 * bool(taste and item.artist and artist_matches(item.artist, taste))
    value += 0.1 * (len(item.description) >= 200)
    value -= SKETCH_PENALTY * sketch_title(item)
    value += copy_quality(item)
    return value + rng.uniform(0, 0.35)


def copy_side(item: Item) -> int | None:
    """The long side of the picture the work is shown from (a sharper copy
    found elsewhere, else its museum's), None when not known."""
    if item.sharper is not None:
        return max(item.sharper.width, item.sharper.height)
    if item.width and item.height:
        return max(item.width, item.height)
    return None


def copy_quality(item: Item) -> float:
    """What the copy's size adds to (or takes from) a work's score."""
    side = copy_side(item)
    if side is None:
        return 0.0
    if side >= FRAME_SIDE:
        return SHARP_BONUS
    return -WEAK_PENALTY if side < WEAK_SIDE else 0.0


def sketch_title(item: Item) -> bool:
    """The museum calls the work a sketch, studies or a sketchbook page."""
    return bool(SKETCH_TITLE.search(item.title))


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
        #: Per work: the ids of its years, and of other circles (``same_time``).
        self._same_time: dict[str, tuple[list[str], list[str]]] = {}
        self._stop = threading.Event()
        self._cutting = threading.Lock()
        self.details_dir = job.images.thumbs.parent / "details"
        #: Looks up what the pages say a work led to; set by the service.
        self.later: LaterWorks | None = None
        #: Other works by the artist ("Inne prace artysty"); set by the service.
        self.artists: ArtistWorks | None = None
        #: Told of a work whose page is written (it becomes its study); set
        #: by ``frame_server.study``.
        self.on_written: Callable[[Item], object] | None = None
        #: Looks for a sharper copy of the day's work before its page is
        #: written; set by the service.
        self.sharper: Sharper | None = None
        #: Asks the curator which shortlisted work is worth a page; set by
        #: the service (None: the rules' first stands).
        self.claude: Claude | None = None

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

    def again(self, day: date) -> Item | None:
        """Another work for ``day`` instead of the one picked (the owner's
        "Wylosuj inne" in Konfiguracja): none set aside that day comes back.
        None when the catalogue has nothing else; the day keeps its work."""
        with self._lock:
            current = self.item(day)
            skipped = self.skipped(day)
            if current is not None and current.id not in skipped:
                skipped.append(current.id)
            # One shortlist: the app waits for the answer (a minute at most).
            found = self.choose(day, skipped, shortlists=1)
            if found is None:
                return None
            self.library.set_state(SKIPPED_KEY, {"day": day.isoformat(), "items": skipped})
            history = self.history()
            history[day.isoformat()] = found.id
            self.library.set_state(HISTORY_KEY, dict(sorted(history.items())))
            log.info("work of %s drawn again: %s instead of %s", day, found.id, current)
            return found

    def skipped(self, day: date) -> list[str]:
        """The works set aside for ``day`` by hand."""
        stored = self.library.get_state(SKIPPED_KEY, {})
        return list(stored.get("items") or []) if stored.get("day") == day.isoformat() else []

    def choose(
        self, day: date, skipped: list[str] | None = None, shortlists: int = SHORTLISTS
    ) -> Item | None:
        """The work for ``day``; ``skipped``: works set aside for it by hand
        (each one drawn again makes another draw)."""
        skipped = skipped if skipped is not None else self.skipped(day)
        history = self.history()
        recent = {
            i for d, i in history.items() if d >= (day - timedelta(days=REPEAT_DAYS)).isoformat()
        }
        recent |= set(skipped)
        artists_cutoff = (day - timedelta(days=ARTIST_DAYS)).isoformat()
        recent_artists = [
            item.artist
            for d, i in history.items()
            if artists_cutoff <= d < day.isoformat() and (item := self.library.get(i)) is not None
        ]
        # Drawn again: another artist too.
        recent_artists += [
            item.artist for i in skipped if (item := self.library.get(i)) is not None
        ]
        # Any work of the catalogue: no e-paper threshold (it left out
        # Rembrandt and Vermeer).
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK])
        seed = day.toordinal() + 1_000_003 * len(skipped)
        drawn = self.library.query(rules, sort="random", seed=seed, limit=POOL)[1]
        unfit = self.unfit()
        poor = self.poor_copies()
        pool = [
            i
            for i in drawn
            if i.id not in recent
            and i.id not in unfit
            and poor.get(i.id) != copy_key(i)
            and i.look is None
            and i.artist
            and not is_photograph(i)
            # A black-and-white photograph of a work in colour, an art
            # archive's old slide: no copy to look at for a quarter of an hour.
            and not is_grey_copy(i)
            and not archive_own(i)
            and not other_art(i)  # "Sztuki inne" keep to their own group
            and max(i.width or MIN_SIDE, i.height or MIN_SIDE) >= MIN_SIDE
            and not (recent_artists and artist_matches(i.artist, recent_artists))
        ]
        if not pool:
            return None
        rng = random.Random(seed)
        taste = self.player.taste()
        values = {i.id: score(i, day, taste, rng) for i in pool}
        ranked = sorted(pool, key=lambda i: values[i.id], reverse=True)
        first: Item | None = None
        for _ in range(shortlists):
            shortlist = self._shortlist(ranked)
            if not shortlist:
                break
            if first is None:
                # The rules' own choice: pale sheets go after the rest.
                first = max(
                    shortlist, key=lambda pair: values[pair[0].id] - PALE_PENALTY * _pale(pair[1])
                )[0]
            if not self._curated():
                return first
            choice = self._curate(day, shortlist)
            if choice is None:  # the curator could not answer: the rules stand
                return first
            if choice.item is not None:
                return choice.item
            # A whole shortlist set aside: the next one.
            asked = {item.id for item, _ in shortlist}
            ranked = [i for i in ranked if i.id not in asked]
        return first

    # -- the curator ---------------------------------------------------------

    def unfit(self) -> dict[str, str]:
        """The works the curator set aside, with what it saw in each."""
        return dict(self.library.get_state(UNFIT_KEY, {}))

    def poor_copies(self) -> dict[str, str]:
        """The works the curator set aside for their photograph, with the
        copy it saw."""
        return dict(self.library.get_state(POOR_COPY_KEY, {}))

    def curated(self) -> dict[str, dict[str, object]]:
        """The curator's choice by day (ISO dates)."""
        return dict(self.library.get_state(CURATED_KEY, {}))

    def _curated(self) -> bool:
        return self.claude is not None and self.job.enabled()

    def _shortlist(self, ranked: list[Item]) -> list[tuple[Item, float | None]]:
        """The rules' best works, each by another artist, with how much of a
        light sheet is marked (None when its picture is not to be had)."""
        picked: list[tuple[Item, float | None]] = []
        artists: list[str] = []
        for item in ranked:
            if len(picked) >= SHORTLIST:
                break
            if artists and artist_matches(item.artist, artists):
                continue
            artists.append(item.artist)
            picked.append((item, self._ink(item)))
        return picked

    def _ink(self, item: Item) -> float | None:
        try:
            return ink_share(load_image(self.job.images.ensure_thumb(item).read_bytes()))
        except Exception as err:  # not to be had now: judged without it
            log.info("study of the day: no picture of %s (%s)", item.id, err)
            return None

    def _curate(self, day: date, shortlist: list[tuple[Item, float | None]]) -> Choice | None:
        """The curator's answer about ``shortlist`` (its work None when it
        set every one aside); None when it could not answer."""
        assert self.claude is not None
        try:
            choice = curate(self.claude, self.job.images, shortlist)
        except Exception as err:
            log.warning("study of the day: the curator did not answer (%s)", err)
            return None
        if choice.unfit:
            unfit = self.unfit()
            unfit.update(choice.unfit)
            self.library.set_state(UNFIT_KEY, dict(list(unfit.items())[-UNFIT_MAX:]))
        if choice.poor_copy:
            poor = self.poor_copies()
            poor.update(choice.poor_copy)
            self.library.set_state(POOR_COPY_KEY, dict(list(poor.items())[-UNFIT_MAX:]))
        log.info(
            "study of the day %s: curator chose %s (%s), set aside %d of %d: %s; "
            "for the photograph: %s",
            day,
            choice.item.id if choice.item else "nothing",
            choice.reason,
            len(choice.unfit) + len(choice.poor_copy),
            len(shortlist),
            "; ".join(f"{k}: {v}" for k, v in choice.unfit.items()),
            ", ".join(choice.poor_copy) or "none",
        )
        if choice.item is None:
            return choice
        curated = self.curated()
        curated[day.isoformat()] = {
            "item": choice.item.id,
            "reason": choice.reason,
            "unfit": sorted(choice.unfit),
            "poor_copy": sorted(choice.poor_copy),
        }
        cutoff = (day - timedelta(days=KEEP_DAYS)).isoformat()
        self.library.set_state(
            CURATED_KEY, {d: c for d, c in sorted(curated.items()) if d >= cutoff}
        )
        return choice

    # -- works like it -----------------------------------------------------

    def candidates(self, item: Item) -> list[Item]:
        """Works of the catalogue like ``item``: of its styles and periods,
        close in time, by other artists ("Podobne dzieła" leaves the
        artist's own to "Inne prace artysty", Mateusz 2026-11-02)."""
        if item.id in self._candidates:
            found = (self.library.get(i) for i in self._candidates[item.id])
            return [i for i in found if i is not None]
        picked: list[Item] = []

        def add(items: list[Item], limit: int) -> None:
            for other in items:
                if len(picked) >= limit:
                    return
                twin = any(p.title == other.title and p.artist == other.artist for p in picked)
                if (
                    other.id != item.id
                    and other.look is None
                    and other not in picked
                    and not twin
                    and not same_artist(item, other)
                ):
                    picked.append(other)

        for term in [t for t in item.terms if t.startswith(("style:", "years:", "technique:"))]:
            near = PlaylistRules(kinds=[ItemKind.ARTWORK], terms=[term])
            items = self.library.query(near, sort="suitability", limit=60)[1]
            if item.year:
                items = [i for i in items if i.year and abs(i.year - item.year) <= 40]
            add(items, CANDIDATES)
        self._candidates[item.id] = [i.id for i in picked]
        return picked

    def same_time(self, item: Item, skip: set[str] | None = None) -> list[Item]:
        """Up to :data:`SAME_TIME` works of the catalogue made within
        :data:`SAME_TIME_YEARS` of ``item``, by other artists, each by
        another: from other countries than the work's and one another's
        first, the owner's favourites and the museums' highlights ahead,
        in an order kept for the work. Among them up to
        :data:`OTHER_CIRCLES` from other cultural circles than the work's
        (a European's row has something from Asia; Mateusz 2026-11-06),
        looked for up to :data:`OTHER_CIRCLE_YEARS` either side when
        nothing nearer is had, and placed where the row is seen without
        scrolling. None of ``skip`` (shown elsewhere on the page); none for
        a work without a year."""
        if not item.year:
            return []
        if item.id not in self._same_time:
            self._same_time[item.id] = self._same_time_pool(item)
        near_ids, far_ids = self._same_time[item.id]
        hidden = self.library.hidden()
        skip = skip or set()

        def fits(ids: list[str]) -> list[Item]:
            return [
                other
                for i in ids
                if (other := self.library.get(i)) is not None
                and other.id != item.id
                and other.id not in skip
                and other.look is None
                and not other.excluded
                and other not in hidden
                and not is_photograph(other)
                and is_artist(other.artist)
                and not same_artist(item, other)
            ]

        near_pool, far_pool = fits(near_ids), fits(far_ids)
        far: list[Item] = []
        circles: set[str] = set()
        for strict in (True, False):
            for other in far_pool:
                if len(far) == min(OTHER_CIRCLES, SAME_TIME):
                    break
                found = circle(other)
                if (
                    other in far
                    or any(same_artist(p, other) for p in far)
                    or (strict and found in circles)
                ):
                    continue
                far.append(other)
                circles.add(found or "")
        picked: list[Item] = []
        countries = {c} if (c := country(item)) else set()
        countries |= {c for p in far if (c := country(p))}
        wanted = SAME_TIME - len(far)
        for strict in (True, False):
            for other in near_pool:
                if len(picked) == wanted:
                    break
                where = country(other)
                if (
                    other in picked
                    or other in far
                    or any(same_artist(p, other) for p in [*picked, *far])
                    or (strict and (not where or where in countries))
                ):
                    continue
                picked.append(other)
                if where:
                    countries.add(where)
        for place, other in zip(OTHER_CIRCLE_PLACES, far, strict=False):
            picked.insert(min(place, len(picked)), other)
        return picked

    def _same_time_pool(self, item: Item) -> tuple[list[str], list[str]]:
        """The works looked among for ``item``'s "Inni w tym samym czasie":
        those of its years in an order drawn for it (favourites and
        highlights ahead), and those of other cultural circles, nearest in
        time first."""
        assert item.year is not None
        rules = PlaylistRules(
            kinds=[ItemKind.ARTWORK],
            year_from=item.year - OTHER_CIRCLE_YEARS,
            year_to=item.year + OTHER_CIRCLE_YEARS,
        )
        seed = zlib.crc32(item.id.encode())
        found = self.library.query(rules, sort="random", seed=seed)[1]
        found.sort(key=lambda i: (not i.favorite, not i.highlight))  # stable
        near = [i.id for i in found if abs((i.year or 0) - item.year) <= SAME_TIME_YEARS]
        # An unknown work's circle: the West's, as most of the catalogue.
        home = circle(item) or "west"
        far = [i for i in found if (where := circle(i)) is not None and where != home]
        far.sort(key=lambda i: _years_apart(i, item))  # stable: the order drawn stays
        return near[:SAME_TIME_POOL], [i.id for i in far[:SAME_TIME_POOL]]

    # -- its page ------------------------------------------------------------

    def ask(self, item: Item) -> Future[Note | None] | None:
        """Asks for the work's page unless it has one (or is off); a work
        with a study gets that, without a new question."""
        if not self.job.enabled() or self.job.essay(item) or self.job.failed(item):
            return None
        if self.job.take(item, self.library.note(item.id, STUDY)):
            return None  # the owner had its study written: the page is that
        future = self.ai.need_now(item.id, KIND)
        future.add_done_callback(lambda done: self._written(item.id))
        return future

    def ask_later(self, item: Item) -> bool:
        """Orders the work's page for later, for less (the Batch API: half
        price, mostly within minutes to hours); False when it needs none."""
        if not self.job.enabled() or self.job.essay(item) or self.job.failed(item):
            return False
        if self.job.take(item, self.library.note(item.id, STUDY)):
            return False  # the owner had its study written: the page is that
        return self.ai.ask_later(item.id, KIND)

    def written_later(self, item: Item) -> None:
        """A page ordered for later is made: its work's study now."""
        self._written(item.id)

    def _written(self, item_id: str) -> None:
        day = self.day_of(item_id)
        if day is not None and day > date.today():
            return  # tomorrow's page, written a day ahead: its study on its day
        item = self.library.get(item_id)
        if item is not None and self.on_written is not None and self.job.essay(item):
            try:
                self.on_written(item)
            except Exception:
                log.exception("study of the day's work %s", item_id)

    def adopt_all(self) -> None:
        """Every day's written page made its work's study (the days before
        the two were one, and any the background missed)."""
        for item_id in sorted(set(self.history().values())):
            self._written(item_id)

    # -- its fragments ("Detale") ----------------------------------------------

    def detail_path(self, item: Item, box: Detail) -> Path:
        parts = [f"{box.x:.4f}", f"{box.y:.4f}", f"{box.w:.4f}", f"{box.h:.4f}"]
        copy = _copy_of(item, box)
        if copy:  # cut from a sharper copy: another file, another address
            parts.append(copy)
        key = text_hash(*parts)[:10]
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
        seen = boxes[0].seen if boxes else None
        places = boxes
        if seen is not None and seen.url and seen.copy_id != _current(item):
            # Drawn on another copy than the one the work has now: cut from
            # the one picked (the best), the boxes carried over onto it by
            # where the two copies lie on one another; from the one drawn
            # on when the two cannot be matched (Mateusz 2026-11-03).
            places, img = self._carried(item, boxes, seen, img)
        width, height = img.size
        self.details_dir.mkdir(parents=True, exist_ok=True)
        for box, place in zip(boxes, places, strict=True):
            path = self.detail_path(item, box)
            box = place
            left, top = round(box.x * width), round(box.y * height)
            right, bottom = round((box.x + box.w) * width), round((box.y + box.h) * height)
            crop = img.crop((max(left, 0), max(top, 0), min(right, width), min(bottom, height)))
            crop.thumbnail((DETAIL_SIDE, DETAIL_SIDE), Image.Resampling.LANCZOS)
            tmp = path.with_suffix(".tmp")
            crop.convert("RGB").save(tmp, "JPEG", quality=88, optimize=True)
            tmp.replace(path)
        cutoff = time.time() - DETAIL_DAYS * 86400
        for old in self.details_dir.glob("*.jpg"):
            with contextlib.suppress(OSError):
                if old.stat().st_mtime < cutoff:
                    old.unlink()

    def _carried(
        self, item: Item, boxes: list[Detail], seen: Seen, img: Image.Image
    ) -> tuple[list[Detail], Image.Image]:
        """``boxes`` (drawn on the copy ``seen``) on ``img`` (the current
        copy), with the picture to cut them from: ``img`` when the two copies
        match, else the copy they were drawn on."""
        try:
            drawn = self.job.images.sample(seen.url)
        except (httpx.HTTPError, OSError) as err:
            log.info("copy %r of %s failed: %s; cut from the current", seen.copy_id, item.id, err)
            return boxes, img
        fit = align(drawn, img)
        if fit is None:
            log.info("copies of %s do not match: details cut from %r", item.id, seen.copy_id)
            return boxes, drawn
        log.info("details of %s carried onto its copy (fit %.2f)", item.id, fit.score)
        carried = []
        for box in boxes:
            x, y, w, h = fit.box(box.x, box.y, box.w, box.h)
            carried.append(box.model_copy(update={"x": x, "y": y, "w": w, "h": h}))
        return carried, img

    def _full_size(self, item: Item) -> Image.Image:
        """The museum's file as it is (the cached original is cut down to
        the panel's size); the cached one when the museum's cannot be had."""
        images = self.job.images
        url = display_copy(item)
        if url and (item.sharper is not None or item.source not in images.fetchers):
            try:
                return images.sample(url)
            except (httpx.HTTPError, OSError) as err:
                log.info("full size of %s failed: %s; the cached original", item.id, err)
        path, _ = images.picture(item, urgent=True)
        return load_image(path)

    def tick(self, day: date | None = None) -> None:
        """The day's page (asked now when the order of the night before is
        not in yet: what its batches answered is not asked again), then the
        next day's ordered for later, for less (Mateusz 2026-11-04)."""
        self.adopt_all()
        today = day or date.today()
        item = self.pick(today)
        if item is not None:
            item = self._sharper(item)
            self.ask(item)
            essay = self.job.essay(item)
            if self.later is not None and essay and self.later.missing(item.id, essay.legacy):
                self.later.look(item, essay.legacy)  # what it led to, with pictures
            self.warm(item, essay)
        tomorrow = self.pick(today + timedelta(days=1))
        if tomorrow is not None:
            try:
                self.ask_later(self._sharper(tomorrow))
            except Exception:  # today's page is there: tomorrow's is asked tomorrow
                log.exception("page of %s for tomorrow not ordered", tomorrow.id)

    def _sharper(self, item: Item) -> Item:
        """The work with a sharper copy looked for: its page, its details
        and the frame come from that."""
        if self.sharper is None:
            return item
        self.sharper.look(item)
        return self.library.get(item.id) or item

    def warm(self, item: Item, essay: Essay | None) -> None:
        """Looks through the catalogue for the lists under the day's page
        (works like it, the later works' copies, other works by the artist),
        so the page opens without waiting for them."""
        self.candidates(item)
        if self.later is not None and essay is not None:
            for entry in essay.legacy:
                self.later.in_catalogue(item, entry)
        if self.artists is not None:
            self.artists.works(item)

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


def _pale(ink: float | None) -> bool:
    return ink is not None and ink < PALE_INK


def _years_apart(item: Item, other: Item) -> int:
    """How far apart the two were made, in steps of :data:`SAME_TIME_YEARS`
    beyond the first (the nearer works first, drawn order kept within)."""
    apart = abs((item.year or 0) - (other.year or 0))
    return 0 if apart <= SAME_TIME_YEARS else 1 + apart // (2 * SAME_TIME_YEARS)


def same_artist(item: Item, other: Item) -> bool:
    """``other`` is by ``item``'s artist (a known one: two anonymous works
    are not)."""
    return (
        is_artist(item.artist)
        and bool(other.artist)
        and artist_matches(other.artist, [item.artist])
    )


def country(item: Item) -> str:
    """Where the work comes from, as far as the catalogue says: the artist's
    nationality from the museum's line about them ("Dutch, Delft 1632–1675"),
    else the work's culture ("Japan"); folded."""
    head = re.split(r"[,(;]", item.artist_bio, maxsplit=1)[0].strip().casefold()
    if head in NATIONALITIES:
        return NATIONALITIES[head][2]
    return item.culture.strip().casefold()


def _current(item: Item) -> str:
    """The copy the work has now: its sharper copy's id, "" for its own."""
    return item.sharper.item_id if item.sharper is not None else ""


def _copy_of(item: Item, box: Detail) -> str:
    """What ``box``'s fragment is cut from, for its file's name: the work's
    current copy, and the one the box was drawn on when that was another."""
    current = _current(item)
    if box.seen is not None and box.seen.copy_id != current:
        return f"{box.seen.copy_id or 'own'}>{current or 'own'}"
    return current
