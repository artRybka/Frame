"""How far a picture is on its way to the frame, for the app's progress bar.

The server's own stages are measured. The panel does not say when its
screen is done (the body of its /content-transfer-progress reports is still
unknown), so the refresh after the download is an estimate from experiments
E2/E3: about 12 s of preparation, then 31-36 s of flashing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

log = logging.getLogger(__name__)


class Stage(StrEnum):
    IDLE = "idle"
    RENDERING = "rendering"  # fetch the original, tone map, dither, publish
    SENDING = "sending"  # MDC session, content download command
    WAKING = "waking"  # the panel did not answer: Wake-on-LAN, then again
    DOWNLOADING = "downloading"  # the panel fetches content.json and the image
    REFRESHING = "refreshing"  # the panel prepares and redraws the e-paper (estimated)
    DONE = "done"
    WAITING = "waiting"  # panel asleep or unreachable: the picture goes out when it wakes
    FAILED = "failed"


ORDER = (Stage.RENDERING, Stage.SENDING, Stage.WAKING, Stage.DOWNLOADING, Stage.REFRESHING)
ACTIVE = frozenset(ORDER)

Phase = Literal["processing", "loading", "displaying"]
PHASES: dict[Stage, Phase] = {
    Stage.RENDERING: "processing",
    Stage.SENDING: "loading",
    Stage.WAKING: "loading",
    Stage.DOWNLOADING: "loading",
    Stage.REFRESHING: "displaying",
}

# Expected seconds per stage. All but the refresh learn from the last runs
# (kept across restarts by the service). Rendering: about 2 s on 2-4 cores
# since the render was sped up, a NAS is slower and may fetch the original
# first. Waking: the 15 s Wake-on-LAN burst, then a connect. Downloading:
# the panel asks for content.json 0.25 s after the command, the image right
# after (E2). Refreshing: 11-12 s of preparation, then 31-36 s of flashing.
DEFAULT_SECONDS: dict[Stage, float] = {
    Stage.RENDERING: 5.0,
    Stage.SENDING: 2.0,
    Stage.WAKING: 20.0,
    Stage.DOWNLOADING: 1.5,
    Stage.REFRESHING: 45.0,
}
# Connecting to a sleeping panel: two attempts (10 s timeout, 5 s apart)
# fail before Wake-on-LAN. Expected instead of SENDING when a wake is.
DEFAULT_FAILED_CONNECT = 15.0
LEARN_RATE = 0.5
# A picture drawn ahead (``RenderCache``) is only published: so quick a
# "render" says nothing about drawing one.
MIN_RENDER = 1.0
MAX_FRACTION = 0.99
# The download's pace is trusted from this share on.
MIN_DOWNLOADED = 0.05


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


class DisplayProgress(BaseModel):
    stage: Stage = Stage.IDLE
    phase: Phase | None = None
    active: bool = False
    title: str = ""
    fraction: float = 0.0  # of the whole way, estimated
    seconds_left: int | None = None  # estimated
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None


class ProgressTracker:
    """One picture at a time; a new one replaces whatever was in progress."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.expected = dict(DEFAULT_SECONDS)
        self.failed_connect = DEFAULT_FAILED_CONNECT
        # Whether the panel will need waking, asked when a picture sets off.
        self.likely_asleep: Callable[[], bool] = lambda: False
        self.on_learn: Callable[[dict[str, float]], None] | None = None  # e.g. to save it
        self._took: dict[Stage, float] = {}
        self._stage = Stage.IDLE
        self._planned: list[Stage] = []
        self._title = ""
        self._message: str | None = None
        self._start = 0.0
        self._stage_start = 0.0
        self._end: float | None = None
        self._shown = 0.0  # the bar never goes back
        self._downloaded = 0.0  # the share the panel app said it has

    @property
    def active(self) -> bool:
        self._settle()
        return self._stage in ACTIVE

    def learned(self) -> dict[str, float]:
        """The expectations that are learned, by stage name."""
        values = {s.value: round(v, 2) for s, v in self.expected.items() if s != Stage.REFRESHING}
        return values | {"failed_connect": round(self.failed_connect, 2)}

    def restore(self, learned: dict[str, float]) -> None:
        """Take back what ``learned`` gave, e.g. after a restart."""
        for key, value in learned.items():
            if key == "failed_connect":
                self.failed_connect = float(value)
            elif key in ORDER and key != Stage.REFRESHING:
                self.expected[Stage(key)] = float(value)

    def begin(self, title: str, *, render: bool = True) -> None:
        now = self._clock()
        wake = self.likely_asleep()
        self._planned = [
            s for s in ORDER if (wake or s != Stage.WAKING) and (render or s != Stage.RENDERING)
        ]
        self._took = {}
        self._stage = self._planned[0]
        self._title = title
        self._message = None
        self._start = self._stage_start = now
        self._end = None
        self._shown = 0.0
        self._downloaded = 0.0

    def note_download(self, fraction: float) -> None:
        """The panel app's word on its download (the Mobile source says
        nothing): the time left is reckoned from its pace."""
        if self._stage == Stage.DOWNLOADING:
            self._downloaded = min(max(fraction, self._downloaded), 1.0)

    def advance(self, stage: Stage) -> None:
        """Move on to ``stage``; ignored when no picture is on its way."""
        if not self.active or stage == self._stage:
            return
        now = self._clock()
        took = now - self._stage_start
        self._took[self._stage] = took
        self._learn(self._stage, took, woke=stage == Stage.WAKING)
        if stage not in self._planned:
            self._planned = sorted([*self._planned, stage], key=ORDER.index)
        self._shown = max(self._shown, self._fraction(now))
        self._stage = stage
        self._stage_start = now
        if stage == Stage.REFRESHING:
            log.info(
                "progress of %r: %s; the refresh is estimated at %.0f s",
                self._title,
                ", ".join(f"{s.value} {t:.1f} s" for s, t in self._took.items()),
                self.expected[Stage.REFRESHING],
            )

    def _learn(self, stage: Stage, took: float, *, woke: bool) -> None:
        if stage == Stage.REFRESHING or (stage == Stage.RENDERING and took < MIN_RENDER):
            return
        if stage == Stage.SENDING and woke:
            # A connect that ended in Wake-on-LAN, learned apart from a normal one.
            self.failed_connect += LEARN_RATE * (took - self.failed_connect)
        else:
            old = self.expected[stage]
            self.expected[stage] = old + LEARN_RATE * (took - old)
        if self.on_learn:
            self.on_learn(self.learned())

    def _expected(self, stage: Stage) -> float:
        if stage == Stage.SENDING and Stage.WAKING in self._planned:
            return self.failed_connect
        return self.expected[stage]

    def finish(self, stage: Stage, message: str | None = None) -> None:
        """End the run: DONE, WAITING or FAILED (IDLE: forget it)."""
        if stage == Stage.IDLE:
            self._stage = Stage.IDLE
            return
        if self._stage not in ACTIVE and self._end is not None:
            return  # already ended; keep the first reason
        now = self._clock()
        self._shown = 1.0 if stage == Stage.DONE else max(self._shown, self._fraction(now))
        self._stage = stage
        self._message = message
        self._end = now

    def _settle(self) -> None:
        """The refresh has no end signal: it is over when its time is up."""
        if self._stage == Stage.REFRESHING:
            end = self._stage_start + self.expected[Stage.REFRESHING]
            if self._clock() >= end:
                self._stage = Stage.DONE
                self._shown = 1.0
                self._end = end

    def _remaining(self, now: float) -> float:
        # A stage that runs late has nothing left, not less than nothing: the
        # bar slows down (the refresh is still ahead) without stopping, and
        # one that ends on time hands over to the next without a jump.
        spent = now - self._stage_start
        left = max(self._expected(self._stage) - spent, 0.0)
        if self._stage == Stage.DOWNLOADING and self._downloaded >= MIN_DOWNLOADED:
            left = spent * (1 - self._downloaded) / self._downloaded
        later = self._planned[self._planned.index(self._stage) + 1 :]
        return left + sum(self._expected(s) for s in later)

    def _fraction(self, now: float) -> float:
        if self._stage not in ACTIVE:
            return self._shown
        elapsed = now - self._start
        total = elapsed + self._remaining(now)
        return min(elapsed / total if total > 0 else 0.0, MAX_FRACTION)

    def view(self) -> DisplayProgress:
        self._settle()
        if self._stage == Stage.IDLE:
            return DisplayProgress()
        now = self._clock()
        wall = datetime.now(UTC)
        active = self._stage in ACTIVE
        self._shown = max(self._shown, self._fraction(now))
        return DisplayProgress(
            stage=self._stage,
            phase=PHASES.get(self._stage),
            active=active,
            title=self._title,
            fraction=round(self._shown, 3),
            seconds_left=round(self._remaining(now)) if active else None,
            started_at=_stamp(wall - timedelta(seconds=now - self._start)),
            finished_at=(
                _stamp(wall - timedelta(seconds=now - self._end)) if self._end is not None else None
            ),
            message=self._message,
        )
