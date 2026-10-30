"""Battery: costs learnt from readings on battery, a day at the schedule set."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from frame_server.battery import BatteryLog, day_plan
from frame_server.schedule import FrameSettings

START = datetime(2026, 10, 28, 6, 0, tzinfo=UTC)


def test_a_day_at_the_schedule() -> None:
    awake = 0.05
    online = day_plan(FrameSettings(), START, awake)
    # 07:00 change, 22:00 quiet hours: the Wi-Fi off until the morning.
    assert online[3] == pytest.approx(2.0, abs=0.2) and online[4] == pytest.approx(1.0, abs=0.2)
    assert online[0] == pytest.approx(15, abs=0.2) and online[1] == pytest.approx(9, abs=0.2)
    economy = day_plan(FrameSettings(power_mode="economy", check_every_hours=2), START, awake)
    assert economy[0] == 0 and economy[1] > 23
    assert economy[3] == pytest.approx(8.0, abs=0.2) and economy[4] == pytest.approx(1.0, abs=0.2)
    assert sum(day_plan(FrameSettings(), START, awake, off=True)[2:]) == 0
    rest = day_plan(FrameSettings(), START, awake, rest_until=START + timedelta(days=2))
    assert rest[1] > online[1] and rest[3] < online[3]


def test_wakes_and_pictures_are_counted() -> None:
    log = BatteryLog(None)
    log.track(START, "awake")
    log.track(START + timedelta(minutes=2), "deep")
    log.track(START + timedelta(hours=4), "awake", silent_wakes=1)
    log.drew()
    totals = log.activity.at(START + timedelta(hours=4, minutes=3))
    assert totals[1] == pytest.approx(4 - 2 / 60)
    assert totals[2] == pytest.approx(5 / 60)
    assert totals[3:] == [2, 1]


def test_readings_keep_the_first_and_last_of_a_level_and_restart_after_charging() -> None:
    log = BatteryLog(None)
    log.track(START, "standby")
    for minutes, level in [(0, 90), (20, 90), (40, 90), (80, 90), (120, 89)]:
        log.note(START + timedelta(minutes=minutes), level, True)
    assert [r[1] for r in log.runs[-1]] == [90, 90, 89]
    assert log.runs[-1][1][0] == (START + timedelta(minutes=80)).timestamp()
    log.note(START + timedelta(hours=3), 95, True)  # charged in between
    assert len(log.runs) == 2
    log.note(START + timedelta(hours=4), 100, False)
    log.note(START + timedelta(hours=5), 100, True)
    assert len(log.runs) == 3


def test_costs_are_learnt_and_the_range_narrows() -> None:
    """Online days and economy days apart: standby and a picture each get
    their own cost, close to what the battery really spends."""
    true = {"standby": 0.8, "deep": 0.004, "awake": 5.0, "wake": 0.05, "change": 0.4}
    log = BatteryLog(None)
    t, used = START, 0.0
    settings = FrameSettings()
    log.track(t, "awake")
    log.note(t, 100, True)
    plan = day_plan(settings, t, log.activity.awake_per_wake())
    first = log.estimate(100, True, plan)
    for day in range(10):
        mode = "standby" if day % 2 else "deep"
        for _ in range(4):
            log.track(t, mode)
            t += timedelta(hours=5, minutes=57)
            used += true[mode] * (5 + 57 / 60)
            log.track(t, "awake")
            t += timedelta(minutes=3)
            used += true["wake"] + true["awake"] * 3 / 60
            log.drew()
            used += true["change"]
            log.note(t, math.floor(100 - used), True)
        if used > 80:
            break
    later = log.estimate(math.floor(100 - used), True, plan)
    assert later.costs.standby_per_day == pytest.approx(24 * true["standby"], rel=0.2)
    assert later.costs.learnt[0] > 0.8
    assert first.full_days_high - first.full_days_low > 3 * (
        later.full_days_high - later.full_days_low
    )
