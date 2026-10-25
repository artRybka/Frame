"""How far a picture is on its way to the frame, for the app's progress bar.

The server's own stages are measured. The panel does not say when its
screen is done (the body of its /content-transfer-progress reports is still
unknown), so the refresh after the download is an estimate from experiments
E2/E3: about 12 s of preparation, then 31-36 s of flashing.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


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

# Expected seconds per stage. All but the refresh learn from the last runs.
DEFAULT_SECONDS: dict[Stage, float] = {
    Stage.RENDERING: 12.0,
    Stage.SENDING: 2.0,
    Stage.WAKING: 30.0,
    Stage.DOWNLOADING: 3.0,
    Stage.REFRESHING: 45.0,
}
LEARN_RATE = 0.5
# A stage that runs late is never "almost over": keep this share of it ahead.
OVERRUN_LEFT = 0.25
MAX_FRACTION = 0.99


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
        self._stage = Stage.IDLE
        self._planned: list[Stage] = []
        self._title = ""
        self._message: str | None = None
        self._start = 0.0
        self._stage_start = 0.0
        self._end: float | None = None
        self._shown = 0.0  # the bar never goes back

    @property
    def active(self) -> bool:
        self._settle()
        return self._stage in ACTIVE

    def begin(self, title: str, *, render: bool = True) -> None:
        now = self._clock()
        self._planned = [s for s in ORDER if s != Stage.WAKING and (render or s != Stage.RENDERING)]
        self._stage = self._planned[0]
        self._title = title
        self._message = None
        self._start = self._stage_start = now
        self._end = None
        self._shown = 0.0

    def advance(self, stage: Stage) -> None:
        """Move on to ``stage``; ignored when no picture is on its way."""
        if not self.active or stage == self._stage:
            return
        now = self._clock()
        took = now - self._stage_start
        if self._stage != Stage.REFRESHING and stage != Stage.WAKING:
            # A connect that ended in Wake-on-LAN says nothing about a normal one.
            old = self.expected[self._stage]
            self.expected[self._stage] = old + LEARN_RATE * (took - old)
        if stage not in self._planned:
            self._planned = sorted([*self._planned, stage], key=ORDER.index)
        self._shown = max(self._shown, self._fraction(now))
        self._stage = stage
        self._stage_start = now

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
        expected = self.expected[self._stage]
        left = max(expected - (now - self._stage_start), expected * OVERRUN_LEFT)
        later = self._planned[self._planned.index(self._stage) + 1 :]
        return left + sum(self.expected[s] for s in later)

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
