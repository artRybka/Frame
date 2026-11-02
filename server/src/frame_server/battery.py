"""How long the battery lasts: what each thing the panel does costs, learnt
from its readings on battery, and the days that leaves at the schedule set.

The panel's day is a few kinds of activity: asleep with network standby on
(the online mode), asleep with the Wi-Fi off (economy, quiet hours), awake,
the wakes themselves and the pictures it draws. The server follows them as
they happen (``Activity``) and notes the level next to their totals now and
then while on battery. Each reading says how much was used since the first
one of that stretch on battery, so a least-squares fit gives the cost of
each. It starts from the costs others measured (``PRIOR_MEAN``), wide enough
for a few days of readings to move them, so there is an estimate from the
first minute and its range narrows as the readings come in.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

import numpy as np
from pydantic import BaseModel

from .schedule import in_quiet_hours, next_change, next_check, quiet_hours

if TYPE_CHECKING:
    from .library import Library
    from .schedule import FrameSettings

# What is counted, in this order everywhere: hours asleep in the network,
# hours asleep without the Wi-Fi, hours awake, wakes, pictures drawn.
FEATURES = ("standby_h", "deep_h", "awake_h", "wakes", "changes")
# Their cost in percent, until the frame's own readings say otherwise:
# network standby 1.5-2 %/h and awake ~4 %/h as samsung-epaper-calendar
# measured on an EM32DX; Samsung's ~200 days at a change a day in deep sleep
# leaves little for the sleep itself (docs/WAKE.md). Wide on purpose.
PRIOR_MEAN = np.array([1.5, 0.005, 4.0, 0.05, 0.3])
PRIOR_SD = np.array([1.0, 0.02, 3.0, 0.1, 0.3])
# One reading: whole percent, and the level sags while the panel is awake.
NOISE = 0.6
# Until there are wakes enough to tell, a wake keeps the panel up this long.
AWAKE_PER_WAKE = timedelta(minutes=3)
MIN_WAKES_SEEN = 5

ACTIVITY_KEY = "battery_activity"
RUNS_KEY = "battery_runs"
OLD_LOG_KEY = "battery_log"  # before 0.41: levels only, three days
# A reading at most every half hour, kept when the level changed or every
# few hours (the first and the last of each level matter most).
SAMPLE_EVERY = timedelta(minutes=30)
KEEP_EVERY = timedelta(hours=2)
KEEP_RUNS_FOR = timedelta(days=120)
MAX_RUNS = 20
CHARGED = 2  # the level rose by more than this: charged in between

# How far ahead the schedule is followed to count a typical day.
PLAN_DAYS = 7
Mode = Literal["awake", "standby", "deep"]


class BatteryCosts(BaseModel):
    """What each thing costs, in percent of a full battery."""

    standby_per_day: float  # a day asleep in the network
    deep_per_day: float  # a day asleep without the Wi-Fi
    per_wake: float  # a wake, with the time it keeps the panel up
    per_change: float  # drawing a picture
    # 0 (still the assumption) to 1 (measured), in the order above.
    learnt: list[float]


class BatteryDay(BaseModel):
    """A day at the schedule set, and what it costs."""

    standby_hours: float
    deep_hours: float
    wakes: float
    changes: float
    standby_cost: float
    deep_cost: float
    wakes_cost: float
    changes_cost: float


class BatteryEstimate(BaseModel):
    per_day: float  # percent a day at the schedule set
    # Days left on battery (None on the charger), and on a full battery;
    # the low and high ends of the likely range of each.
    days: float | None = None
    days_low: float | None = None
    days_high: float | None = None
    full_days: float
    full_days_low: float
    full_days_high: float
    hours_measured: float  # on battery, behind the costs
    readings: int
    costs: BatteryCosts
    day: BatteryDay
    # Asleep, the panel reads nothing and its level stands still: the level
    # now, by what it has done since the last reading on battery
    # (``read_level`` at ``read_at``) at the costs learnt. None while that
    # reading still holds (the panel awake, or too little time since).
    level: int | None = None
    read_level: int | None = None
    read_at: str | None = None


def _hours(delta: timedelta) -> float:
    return max(delta / timedelta(hours=1), 0.0)


class Activity(BaseModel):
    """What the panel does now, since when, and the totals so far."""

    mode: Mode | None = None
    since: str | None = None
    totals: list[float] = [0.0] * len(FEATURES)

    def at(self, now: datetime) -> list[float]:
        """The totals with the time in the current mode up to ``now``."""
        totals = list(self.totals)
        if self.mode is not None and self.since is not None:
            index = {"standby": 0, "deep": 1, "awake": 2}[self.mode]
            totals[index] += _hours(now - datetime.fromisoformat(self.since))
        return totals

    def change(self, now: datetime, mode: Mode, silent_wakes: int = 0) -> bool:
        """The panel is now ``mode``; whether that is news. A sleep ending
        in waking up is a wake; ``silent_wakes``: alarms that woke it in
        the meantime and let it sleep on without asking (economy checks)."""
        if mode == self.mode:
            return False
        self.totals = self.at(now)
        if mode == "awake" and self.mode in ("standby", "deep"):
            self.totals[3] += 1
        self.totals[3] += silent_wakes
        self.mode = mode
        self.since = now.isoformat(timespec="seconds")
        return True

    def drew(self) -> None:
        self.totals[4] += 1

    def awake_per_wake(self) -> float:
        """Hours a wake keeps the panel up, as seen so far."""
        wakes = self.totals[3]
        if wakes < MIN_WAKES_SEEN:
            return _hours(AWAKE_PER_WAKE)
        return min(self.totals[2] / wakes, 1.0)


class Fit(BaseModel):
    mean: list[float]
    cov: list[list[float]]
    hours: float
    readings: int


def fit(runs: list[list[list[float]]]) -> Fit:
    """The costs from the readings, starting from ``PRIOR_MEAN``.

    In a run (a stretch on battery) reading ``i`` gives ``y_i = L_0 - L_i``
    for the totals ``x_i = F_i - F_0``. All share the first reading's
    error, so the noise is ``NOISE**2 * (I + 11')``, whose inverse is
    ``(I - 11'/(n+1)) / NOISE**2``.
    """
    precision = np.diag(1 / PRIOR_SD**2)
    target = PRIOR_MEAN / PRIOR_SD**2
    hours, readings = 0.0, 0
    for run in runs:
        if len(run) < 2:
            continue
        first = np.array(run[0][1:], dtype=float)
        rest = np.array([r[1:] for r in run[1:]], dtype=float)
        y = first[0] - rest[:, 0]
        x = rest[:, 1:] - first[1:]
        n = len(y)
        weight = (np.eye(n) - np.ones((n, n)) / (n + 1)) / NOISE**2
        precision += x.T @ weight @ x
        target += x.T @ weight @ y
        hours += float(x[-1, :3].sum())
        readings += n + 1
    cov = np.linalg.inv(precision)
    mean = np.clip(cov @ target, 0.0, None)
    return Fit(mean=mean.tolist(), cov=cov.tolist(), hours=hours, readings=readings)


class BatteryLog:
    """The panel's activity and its battery readings, kept in the library."""

    def __init__(self, library: Library | None) -> None:
        self.library = library
        saved = library.get_state(ACTIVITY_KEY) if library else None
        self.activity = Activity.model_validate(saved or {})
        # Each stretch on battery: ``[seconds, level, *totals]`` readings;
        # ``open``: the last one goes on.
        runs = library.get_state(RUNS_KEY, {}) if library else {}
        self.runs: list[list[list[float]]] = runs.get("runs", [])
        self._open = bool(runs.get("open", False))
        # The last reading on battery (a row as in a run); kept between the
        # rows of a run, which are half an hour apart at most.
        self._last: list[float] | None = None
        if self._open and self.runs:
            self._last = list(self.runs[-1][-1])
        self._fit: Fit | None = None
        if library is not None and library.get_state(OLD_LOG_KEY) is not None:
            library.delete_state(OLD_LOG_KEY)

    def _save_runs(self) -> None:
        self._fit = None
        if self.library is not None:
            self.library.set_state(RUNS_KEY, {"runs": self.runs, "open": self._open})

    def _save_activity(self) -> None:
        if self.library is not None:
            self.library.set_state(ACTIVITY_KEY, self.activity.model_dump())

    def track(self, now: datetime, mode: Mode | None, silent_wakes: int = 0) -> None:
        if mode is None:
            return
        since = self.activity.since
        if since is not None and now < datetime.fromisoformat(since):
            now = datetime.fromisoformat(since)  # a clock gone back: no time passed
        if self.activity.change(now, mode, silent_wakes):
            self._save_activity()

    def drew(self) -> None:
        self.activity.drew()
        self._save_activity()

    def note(self, now: datetime, level: int, on_battery: bool) -> None:
        """A reading of the level; on the charger the run on battery ends."""
        runs = self.runs
        if not on_battery:
            self._last = None
            if self._open:
                self._open = False
                self._save_runs()
            return
        row = [now.timestamp(), float(level), *self.activity.at(now)]
        self._last = row
        run = runs[-1] if self._open and runs else None
        if run is not None and level > run[-1][1] + CHARGED:
            run = None
        if run is None:
            runs.append([row])
            self._open = True
        else:
            last = run[-1]
            if now.timestamp() - last[0] < SAMPLE_EVERY.total_seconds():
                return
            plateau = len(run) >= 2 and run[-2][1] == last[1] == level
            if plateau and now.timestamp() - run[-2][0] < KEEP_EVERY.total_seconds():
                run[-1] = row  # the same level still: keep its first and last reading
            else:
                run.append(row)
        oldest = (now - KEEP_RUNS_FOR).timestamp()
        self.runs = [r for r in runs if r[-1][0] >= oldest][-MAX_RUNS:]
        self._save_runs()

    def fit(self) -> Fit:
        if self._fit is None:
            self._fit = fit(self.runs)
        return self._fit

    def since_reading(self, now: datetime, mean: np.ndarray) -> tuple[list[float], float] | None:
        """The last reading on battery and the percent used since, by what
        the panel has done meanwhile at the costs ``mean``."""
        last = self._last
        if last is None or now.timestamp() < last[0]:
            return None
        done = np.array(self.activity.at(now)) - np.array(last[2:])
        return last, float(np.clip(done, 0.0, None) @ mean)

    def estimate(
        self,
        level: int | None,
        on_battery: bool,
        plan: list[float],
        now: datetime | None = None,
    ) -> BatteryEstimate:
        """The days ``level`` lasts at ``plan`` (a day's totals). With
        ``now``, a level that stood still since the last reading on battery
        (the panel asleep) gives way to the level estimated for ``now``."""
        model = self.fit()
        mean, cov = np.array(model.mean), np.array(model.cov)
        guess: int | None = None
        reading = self.since_reading(now, mean) if now is not None and on_battery else None
        if reading is not None:
            last, used = reading
            estimated = max(math.floor(last[1] - used + 0.5), 0)
            if estimated < last[1]:
                guess = estimated
        day = np.array(plan)
        per_day = max(float(day @ mean), 0.01)
        spread = 1.28 * float(np.sqrt(max(day @ cov @ day, 0.0)))  # 80 % of the likely range
        low_rate, high_rate = max(per_day - spread, per_day / 4), per_day + spread

        def days(percent: float) -> tuple[float, float, float]:
            return (
                round(percent / per_day, 1),
                round(percent / high_rate, 1),
                round(percent / low_rate, 1),
            )

        full, full_low, full_high = days(100)
        now_level = guess if guess is not None else level
        left = days(now_level) if on_battery and now_level is not None else (None, None, None)
        per_wake = mean[3] + mean[2] * self.activity.awake_per_wake()
        learnt = 1 - np.sqrt(np.diag(cov)) / PRIOR_SD
        costs = BatteryCosts(
            standby_per_day=round(mean[0] * 24, 2),
            deep_per_day=round(mean[1] * 24, 2),
            per_wake=round(per_wake, 3),
            per_change=round(mean[4], 3),
            learnt=[
                round(float(v), 2)
                for v in (learnt[0], learnt[1], max(learnt[2], learnt[3]), learnt[4])
            ],
        )
        awake = day[2] * mean[2]
        return BatteryEstimate(
            per_day=round(per_day, 2),
            days=left[0],
            days_low=left[1],
            days_high=left[2],
            full_days=full,
            full_days_low=full_low,
            full_days_high=full_high,
            hours_measured=round(model.hours, 1),
            readings=model.readings,
            costs=costs,
            day=BatteryDay(
                standby_hours=round(day[0], 1),
                deep_hours=round(day[1], 1),
                wakes=round(day[3], 1),
                changes=round(day[4], 1),
                standby_cost=round(day[0] * mean[0], 2),
                deep_cost=round(day[1] * mean[1], 2),
                wakes_cost=round(day[3] * mean[3] + awake, 2),
                changes_cost=round(day[4] * mean[4], 2),
            ),
            level=guess,
            read_level=int(reading[0][1]) if guess is not None and reading else None,
            read_at=(
                datetime.fromtimestamp(reading[0][0], UTC).isoformat(timespec="seconds")
                if guess is not None and reading
                else None
            ),
        )


def day_plan(
    settings: FrameSettings,
    now: datetime,
    awake_per_wake: float,
    rest_until: datetime | None = None,
    off: bool = False,
) -> list[float]:
    """A day's totals on battery at ``settings``, averaged over the next
    ``PLAN_DAYS``: the wakes the app sets (changes, economy checks, the
    start of quiet hours in the online mode) and the sleep between them,
    with the Wi-Fi off in the economy mode and in quiet hours. A rest
    ("Głęboki sen") sleeps without the Wi-Fi until it ends; off, for good."""
    end = now + timedelta(days=PLAN_DAYS)
    totals = [0.0] * len(FEATURES)
    if off:
        return [0.0, 24.0, 0.0, 0.0, 0.0]
    t = now
    if rest_until is not None and rest_until > now:
        t = min(rest_until, end)
        totals[1] += _hours(t - now)
    change = next_change(t, settings)
    hours = quiet_hours(settings)
    tz = settings.tz()
    while t < end:
        wakes = [change]
        check = next_check(t, settings)
        if check is not None:
            wakes.append(check)
        if hours is not None and not in_quiet_hours(t, settings):
            local = t.astimezone(tz)
            start = datetime.combine(local.date(), hours[0], tzinfo=tz)
            wakes.append(start if start > local else start + timedelta(days=1))
        wake = min(wakes)
        deep = settings.power_mode == "economy" or in_quiet_hours(t, settings)
        totals[1 if deep else 0] += _hours(min(wake, end) - t)
        if wake >= end:
            break
        totals[2] += awake_per_wake
        totals[3] += 1
        if wake == change:
            totals[4] += 1
            change = next_change(change, settings)
        t = wake + timedelta(hours=awake_per_wake)
    days = _hours(end - now) / 24
    return [v / days for v in totals]


def awake_mode(power_state: str | None) -> Mode | None:
    """The battery's view of what the status says the panel does."""
    modes: dict[str, Mode] = {"online": "awake", "standby": "standby", "deep_sleep": "deep"}
    return modes.get(power_state or "")
