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
# Their cost in percent, until the frame's own readings say otherwise,
# from our frame's tests (2026-11-05, docs/EXPERIMENTS.md): network standby
# ~41 %/day (1.5-2 %/h on another EM32DX too); held awake ~6 %/h (E17,
# 97 -> 58 % in ~6.5 h); a wake with its picture ~0.6 % (a night of eight,
# 100 -> 95 %); an empty check ~0.8 % (cold boot, ~5 min on the Wi-Fi);
# Samsung's ~200 days at a change a day leaves ~0.5 %/day for deep sleep.
# Wide on purpose.
PRIOR_MEAN = np.array([1.7, 0.02, 5.0, 0.3, 0.15])
PRIOR_SD = np.array([1.0, 0.03, 3.0, 0.3, 0.3])
# One reading: whole percent, and the level sags while the panel is awake.
NOISE = 0.6
# A wake that runs the app keeps the panel up from its first question to its
# "sleep" report: as measured on battery (the median of the last few), this
# long until there are enough. Longer than ``LONGEST_WAKE``: someone kept it
# up ("Obudź ramkę", a test), not the wake's own time.
APP_AWAKE = timedelta(minutes=3)
MIN_WAKES_SEEN = 3
WAKES_KEPT = 30
LONGEST_WAKE = timedelta(minutes=30)
# An economy check with nothing new: the app does not run, the panel stays up
# on the Wi-Fi until Samsung's own sleep (app.js ``AUTO_SLEEP``) and sleeps on.
# The server sees only the alarm that rang (``silent_wakes``).
CHECK_UP = timedelta(minutes=5)
# Pictures sent from the app: so many a day, as in the last two weeks (a
# burst within ``SEND_BURST`` is one wake), on top of the schedule.
SENDS_FOR = timedelta(days=14)
SENDS_MIN_DAYS = 3
SEND_BURST = timedelta(minutes=10)
# The last stretch on battery against what the costs say it should have used.
CHECK_SPAN = timedelta(hours=24)
CHECK_MIN = timedelta(hours=12)
RECENT_FOR = timedelta(days=7)

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


LineKind = Literal["standby", "deep", "checks", "changes", "sends", "wakes"]


class BatteryCosts(BaseModel):
    """What each thing costs, in percent of a full battery."""

    standby_per_day: float  # a day asleep in the network
    deep_per_day: float  # a day asleep without the Wi-Fi
    per_wake: float  # a wake that runs the app, with the time it keeps the panel up
    per_change: float  # drawing a picture, on top of its wake
    # 0 (still the assumption) to 1 (measured), in the order above.
    learnt: list[float]
    # A scheduled change whole (its wake, the app up, the drawing), an
    # economy check with nothing new, and the minutes behind them.
    per_change_wake: float = 0.0
    per_check: float = 0.0
    app_awake_minutes: float = 0.0
    check_minutes: float = 0.0


class BatteryLine(BaseModel):
    """One thing in a day at the schedule set: how many (or hours), each
    costs, and in all."""

    kind: LineKind
    count: float  # hours for standby and deep
    each: float  # percent, per hour for standby and deep
    cost: float  # percent a day


class BatteryDay(BaseModel):
    """A day at the schedule set, and what it costs."""

    standby_hours: float
    deep_hours: float
    wakes: float
    changes: float
    standby_cost: float
    deep_cost: float
    wakes_cost: float  # every wake and its time up, drawing aside
    changes_cost: float  # the drawing alone
    checks: float = 0.0
    sends: float = 0.0  # pictures sent from the app, as usual lately
    # What makes the day, most costly first (the battery sheet).
    lines: list[BatteryLine] = []


class BatteryCheck(BaseModel):
    """The last stretch on battery: the percent used, and what the costs
    learnt say it should have been."""

    hours: float
    used: float
    expected: float


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
    # The readings on battery of the last week, ``[time, level]``, and how
    # the costs fit the last day of them.
    recent: list[tuple[str, int]] = []
    check: BatteryCheck | None = None


def _hours(delta: timedelta) -> float:
    return max(delta / timedelta(hours=1), 0.0)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


class Activity(BaseModel):
    """What the panel does now, since when, and the totals so far."""

    mode: Mode | None = None
    since: str | None = None
    totals: list[float] = [0.0] * len(FEATURES)
    # Awake after a wake on battery (not the charger, not a look): its
    # minutes up count for the wakes that run the app.
    woke: bool = False
    wake_minutes: list[float] = []
    # Pictures sent from the app (ISO times), and since when they are noted.
    sent: list[str] = []
    sent_since: str | None = None

    def at(self, now: datetime, silent_wakes: int = 0) -> list[float]:
        """The totals with the time in the current mode up to ``now``, and
        the economy checks that rang meanwhile (``silent_wakes``)."""
        totals = list(self.totals)
        if self.mode is not None and self.since is not None:
            index = {"standby": 0, "deep": 1, "awake": 2}[self.mode]
            spent = _hours(now - datetime.fromisoformat(self.since))
            totals[index] += spent
            if silent_wakes and self.mode == "deep":
                # Each check kept it up on the Wi-Fi for a while, unseen.
                up = min(silent_wakes * _hours(CHECK_UP), spent)
                totals[1] -= up
                totals[2] += up
        totals[3] += silent_wakes
        return totals

    def change(
        self, now: datetime, mode: Mode, silent_wakes: int = 0, on_battery: bool = True
    ) -> bool:
        """The panel is now ``mode``; whether that is news. A sleep ending
        in waking up is a wake; ``silent_wakes``: alarms that woke it in
        the meantime and let it sleep on without asking (economy checks).
        A wake on battery that ends in a sleep tells how long a wake lasts."""
        if mode == self.mode:
            return False
        if self.mode == "awake" and self.woke and on_battery and self.since is not None:
            up = now - datetime.fromisoformat(self.since)
            if timedelta(0) < up <= LONGEST_WAKE:
                self.wake_minutes = [*self.wake_minutes, round(up / timedelta(minutes=1), 2)]
                self.wake_minutes = self.wake_minutes[-WAKES_KEPT:]
        self.totals = self.at(now, silent_wakes)
        woke = mode == "awake" and self.mode in ("standby", "deep")
        if woke:
            self.totals[3] += 1
        self.woke = woke and on_battery
        self.mode = mode
        self.since = now.isoformat(timespec="seconds")
        return True

    def drew(self) -> None:
        self.totals[4] += 1

    def awake_per_wake(self) -> float:
        """Hours a wake that runs the app keeps the panel up, on battery."""
        if len(self.wake_minutes) < MIN_WAKES_SEEN:
            return _hours(APP_AWAKE)
        return _median(self.wake_minutes) / 60

    def note_sent(self, now: datetime) -> None:
        if self.sent_since is None:
            self.sent_since = now.isoformat(timespec="seconds")
        last = datetime.fromisoformat(self.sent[-1]) if self.sent else None
        if last is not None and timedelta(0) <= now - last < SEND_BURST:
            return  # the same burst: one wake takes them all
        oldest = now - SENDS_FOR
        kept = [s for s in self.sent if datetime.fromisoformat(s) >= oldest]
        self.sent = [*kept, now.isoformat(timespec="seconds")]

    def sends_per_day(self, now: datetime) -> float:
        """Pictures sent from the app a day, as in the last two weeks."""
        if self.sent_since is None:
            return 0.0
        noted = now - datetime.fromisoformat(self.sent_since)
        days = min(max(_hours(noted) / 24, SENDS_MIN_DAYS), SENDS_FOR / timedelta(days=1))
        oldest = now - SENDS_FOR
        return sum(datetime.fromisoformat(s) >= oldest for s in self.sent) / days


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

    def track(
        self, now: datetime, mode: Mode | None, silent_wakes: int = 0, on_battery: bool = True
    ) -> None:
        if mode is None:
            return
        since = self.activity.since
        if since is not None and now < datetime.fromisoformat(since):
            now = datetime.fromisoformat(since)  # a clock gone back: no time passed
        if self.activity.change(now, mode, silent_wakes, on_battery):
            self._save_activity()

    def drew(self) -> None:
        self.activity.drew()
        self._save_activity()

    def sent(self, now: datetime) -> None:
        """A picture sent from the app (not the schedule's)."""
        self.activity.note_sent(now)
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

    def since_reading(
        self, now: datetime, mean: np.ndarray, silent_wakes: int = 0
    ) -> tuple[list[float], float] | None:
        """The last reading on battery and the percent used since, by what
        the panel has done meanwhile at the costs ``mean``; only while it
        sleeps, when nothing new is read."""
        last = self._last
        if last is None or now.timestamp() < last[0]:
            return None
        if self.activity.mode not in ("standby", "deep"):
            return None  # awake, the panel reads its battery itself
        done = np.array(self.activity.at(now, silent_wakes)) - np.array(last[2:])
        return last, float(np.clip(done, 0.0, None) @ mean)

    def recent(self, now: datetime) -> list[tuple[str, int]]:
        """The readings on battery of the last week, oldest first."""
        oldest = (now - RECENT_FOR).timestamp()
        return [
            (datetime.fromtimestamp(row[0], UTC).isoformat(timespec="seconds"), int(row[1]))
            for run in self.runs
            for row in run
            if row[0] >= oldest
        ]

    def check(self, mean: np.ndarray) -> BatteryCheck | None:
        """The last day of the latest run on battery: the percent it used
        against what the costs ``mean`` make of what the panel did."""
        if not self.runs:
            return None
        run = self.runs[-1]
        last = run[-1]
        start = next((r for r in run if last[0] - r[0] <= CHECK_SPAN.total_seconds()), None)
        if start is None or last[0] - start[0] < CHECK_MIN.total_seconds():
            return None
        done = np.clip(np.array(last[2:]) - np.array(start[2:]), 0.0, None)
        return BatteryCheck(
            hours=round((last[0] - start[0]) / 3600, 1),
            used=round(start[1] - last[1], 1),
            expected=round(float(done @ mean), 1),
        )

    def estimate(
        self,
        level: int | None,
        on_battery: bool,
        plan: DayPlan,
        now: datetime | None = None,
        silent_wakes: int = 0,
    ) -> BatteryEstimate:
        """The days ``level`` lasts at ``plan`` (a day at the schedule).
        With ``now``, a level that stood still since the last reading on
        battery (the panel asleep, ``silent_wakes`` checks since) gives way
        to the level estimated for ``now``."""
        model = self.fit()
        mean, cov = np.array(model.mean), np.array(model.cov)
        guess: int | None = None
        reading = (
            self.since_reading(now, mean, silent_wakes) if now is not None and on_battery else None
        )
        if reading is not None:
            last, used = reading
            estimated = max(math.floor(last[1] - used + 0.5), 0)
            if estimated < last[1]:
                guess = estimated
        day = np.array(plan.totals())
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
        app_awake = self.activity.awake_per_wake()
        per_wake = mean[3] + mean[2] * app_awake
        per_check = mean[3] + mean[2] * _hours(CHECK_UP)
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
            per_change_wake=round(per_wake + mean[4], 3),
            per_check=round(per_check, 3),
            app_awake_minutes=round(app_awake * 60, 1),
            check_minutes=round(_hours(CHECK_UP) * 60, 1),
        )
        draws = day[4] * mean[4]
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
                wakes_cost=round(day[3] * mean[3] + day[2] * mean[2], 2),
                changes_cost=round(draws, 2),
                checks=round(plan.checks, 1),
                sends=round(plan.sends, 2),
                lines=plan.lines(mean),
            ),
            level=guess,
            read_level=int(reading[0][1]) if guess is not None and reading else None,
            read_at=(
                datetime.fromtimestamp(reading[0][0], UTC).isoformat(timespec="seconds")
                if guess is not None and reading
                else None
            ),
            recent=self.recent(now) if now is not None else [],
            check=self.check(mean),
        )


class DayPlan(BaseModel):
    """A day on battery at the schedule set, by what makes it: each a day's
    totals of ``FEATURES`` and how many."""

    standby_hours: float = 0.0
    deep_hours: float = 0.0
    checks: float = 0.0
    check: list[float] = [0.0] * len(FEATURES)
    changes: float = 0.0
    change: list[float] = [0.0] * len(FEATURES)
    # Wakes that run the app with nothing to draw (the online mode's quiet
    # hours begin).
    wakes: float = 0.0
    wake: list[float] = [0.0] * len(FEATURES)
    sends: float = 0.0
    send: list[float] = [0.0] * len(FEATURES)

    def totals(self) -> list[float]:
        totals = np.array([self.standby_hours, self.deep_hours, 0.0, 0.0, 0.0])
        for part in (self.check, self.change, self.wake, self.send):
            totals += np.array(part)
        return [float(v) for v in totals]

    def lines(self, mean: np.ndarray) -> list[BatteryLine]:
        def line(kind: LineKind, count: float, part: list[float] | float) -> BatteryLine:
            cost = float(np.array(part) @ mean) if isinstance(part, list) else part
            each = cost / count if count else 0.0
            return BatteryLine(
                kind=kind, count=round(count, 2), each=round(each, 3), cost=round(cost, 2)
            )

        lines = [
            line("standby", self.standby_hours, self.standby_hours * float(mean[0])),
            line("deep", self.deep_hours, self.deep_hours * float(mean[1])),
            line("checks", self.checks, self.check),
            line("changes", self.changes, self.change),
            line("wakes", self.wakes, self.wake),
            line("sends", self.sends, self.send),
        ]
        return sorted((x for x in lines if x.count > 0), key=lambda x: -x.cost)


def day_plan(
    settings: FrameSettings,
    now: datetime,
    awake_per_wake: float,
    rest_until: datetime | None = None,
    off: bool = False,
    sends_per_day: float = 0.0,
) -> DayPlan:
    """A day on battery at ``settings``, averaged over the next
    ``PLAN_DAYS``: the wakes the app sets (changes, economy checks, the
    start of quiet hours in the online mode) and the sleep between them,
    with the Wi-Fi off in the economy mode and in quiet hours. A change
    runs the app (``awake_per_wake`` hours) and draws; an economy check
    with nothing new keeps the panel up ``CHECK_UP`` without the app.
    Pictures sent from the app (``sends_per_day``): out of the online
    mode's network standby each wakes it, runs the app and draws; in the
    economy mode a check takes it (the app runs there instead of the empty
    check), and without checks it waits for the next change. A rest
    ("Głęboki sen") sleeps without the Wi-Fi until it ends; off, for good."""
    plan = DayPlan()
    if off:
        plan.deep_hours = 24.0
        return plan
    end = now + timedelta(days=PLAN_DAYS)
    t = now
    if rest_until is not None and rest_until > now:
        t = min(rest_until, end)
        plan.deep_hours += _hours(t - now)
    change = next_change(t, settings)
    hours = quiet_hours(settings)
    tz = settings.tz()
    check_up = _hours(CHECK_UP)
    standby_hours = 0.0
    check = np.zeros(len(FEATURES))
    changing = np.zeros(len(FEATURES))
    waking = np.zeros(len(FEATURES))
    checks = changes = wakes = 0
    while t < end:
        moments = [change]
        next_one = next_check(t, settings)
        if next_one is not None:
            moments.append(next_one)
        if hours is not None and not in_quiet_hours(t, settings):
            local = t.astimezone(tz)
            start = datetime.combine(local.date(), hours[0], tzinfo=tz)
            moments.append(start if start > local else start + timedelta(days=1))
        wake = min(moments)
        deep = settings.power_mode == "economy" or in_quiet_hours(t, settings)
        asleep = _hours(min(wake, end) - t)
        if deep:
            plan.deep_hours += asleep
        else:
            standby_hours += asleep
        if wake >= end:
            break
        if wake == change:
            changes += 1
            changing += [0, 0, awake_per_wake, 1, 1]
            change = next_change(change, settings)
            up = awake_per_wake
        elif wake == next_one:
            checks += 1
            check += [0, 0, check_up, 1, 0]
            up = check_up
        else:
            wakes += 1
            waking += [0, 0, awake_per_wake, 1, 0]
            up = awake_per_wake
        t = wake + timedelta(hours=up)
    days = _hours(end - now) / 24
    plan.standby_hours = standby_hours / days
    plan.deep_hours /= days
    plan.checks, plan.check = checks / days, list(check / days)
    plan.changes, plan.change = changes / days, list(changing / days)
    plan.wakes, plan.wake = wakes / days, list(waking / days)
    if sends_per_day > 0:
        if settings.power_mode == "economy":
            # A check runs the app and draws instead of sleeping on; none
            # left (or no checks): the picture waits for the next change.
            plan.sends = min(sends_per_day, plan.checks)
            extra = [0.0, 0.0, max(awake_per_wake - check_up, 0.0), 0.0, 1.0]
        else:
            # Woken out of network standby; in quiet hours it waits.
            awake_share = 1 - plan.deep_hours / 24 if plan.deep_hours < 24 else 0.0
            plan.sends = sends_per_day * awake_share
            # Up instead of asleep in the network.
            extra = [-awake_per_wake, 0.0, awake_per_wake, 1.0, 1.0]
        plan.send = [plan.sends * v for v in extra]
    return plan


def awake_mode(power_state: str | None) -> Mode | None:
    """The battery's view of what the status says the panel does."""
    modes: dict[str, Mode] = {"online": "awake", "standby": "standby", "deep_sleep": "deep"}
    return modes.get(power_state or "")
