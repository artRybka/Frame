"""Studia z zapasu: what Claude's month leaves at its end goes on more
studies, the curator's runners-up first (leftover.py)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_daily import DAY, _add, _catalogue, _claude, _curator, _numbers

from frame_server import daily as daily_module
from frame_server import leftover as leftover_module
from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import SPEND_KEY, Spending, period
from frame_server.ai.study import KIND as STUDY
from frame_server.service import FrameService

#: A night in the last days of November's period (it ends on 1 December).
NIGHT = datetime(2026, 11, 28, 2, 0, tzinfo=UTC)


def _spent(svc: FrameService, usd: float, day: str = "2026-11-20") -> None:
    svc.library.set_state(SPEND_KEY, {day: {"study": usd}})


def _switched_on(svc: FrameService, when: datetime = NIGHT) -> None:
    svc.ai_config.update(
        AiConfigUpdate(leftover=True, monthly_limit_usd=200, leftover_reserve_usd=10)
    )
    svc.leftover.now = lambda: when


def test_the_period_begins_on_the_renewal_day() -> None:
    assert period(date(2026, 11, 13)) == (date(2026, 11, 1), date(2026, 12, 1))
    assert period(date(2026, 11, 13), 17) == (date(2026, 10, 17), date(2026, 11, 17))
    assert period(date(2026, 11, 17), 17) == (date(2026, 11, 17), date(2026, 12, 17))
    assert period(date(2026, 12, 20), 17) == (date(2026, 12, 17), date(2027, 1, 17))
    assert period(date(2027, 1, 3), 17) == (date(2026, 12, 17), date(2027, 1, 17))


def test_spending_counts_the_days_of_the_period(service: FrameService) -> None:
    spending = Spending(service.library, start_day=lambda: 17)
    service.library.set_state(
        SPEND_KEY,
        {
            # Kept by month before: October's second half counts in the
            # period from 17 October, November's whole.
            "2026-10": {"study": 31.0},
            "2026-11": {"study": 10.0, "keywords": 1.0},
            "2026-11-16": {"study": 2.0},
            "2026-11-17": {"study": 4.0},
        },
    )
    then = datetime(2026, 11, 14, tzinfo=UTC)
    assert spending.by_kind(then) == {"study": 15 + 10 + 2, "keywords": 1.0}
    later = datetime(2026, 11, 20, tzinfo=UTC)
    assert spending.by_kind(later) == {"study": 4.0}
    # From the 1st, as before: whole months.
    calendar = Spending(service.library)
    assert calendar.total(then) == 10 + 1 + 2 + 4


def test_the_curator_keeps_the_works_it_did_not_choose(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    _catalogue(svc)
    asked = _curator(fake, {"works": [], "choice": 0, "reason": "-"})
    svc.daily.pick(DAY)
    numbers = _numbers(asked[0])
    svc.library.set_state(daily_module.HISTORY_KEY, {})
    svc.library.set_state(daily_module.UNFIT_KEY, {})
    answer = {
        "works": [
            {"n": n, "what": "", "fit": title != "The Harvesters", "why": ""}
            for title, n in numbers.items()
        ],
        "choice": numbers["Water Lilies"],
        "reason": "Najwięcej do oglądania.",
    }
    _curator(fake, answer)
    found = svc.daily.pick(DAY)
    assert found is not None and found.id == "met:3"
    runners = svc.daily.runners_up()
    assert "met:3" not in runners and "met:4" not in runners
    assert runners and set(runners.values()) == {DAY.isoformat()}


def test_nothing_is_ordered_before_the_last_days_or_in_the_last_one(tmp_path: Path) -> None:
    _, svc, _ = _claude(tmp_path)
    _catalogue(svc)
    assert svc.leftover.at_night() == (0, "wyłączone")
    _switched_on(svc, datetime(2026, 11, 20, tzinfo=UTC))
    assert svc.leftover.at_night() == (0, "od 28.11")
    svc.leftover.now = lambda: datetime(2026, 11, 30, 3, tzinfo=UTC)
    assert svc.leftover.at_night() == (0, "ostatnia doba okresu")
    # The window is the last days of the period, wherever it begins.
    svc.ai_config.update(AiConfigUpdate(period_day=17, leftover_days=4))
    svc.leftover.now = lambda: datetime(2026, 11, 14, 3, tzinfo=UTC)
    opens, closes, ends = svc.leftover.window()
    assert (opens.date(), closes.date(), ends.date()) == (
        date(2026, 11, 13),
        date(2026, 11, 16),
        date(2026, 11, 17),
    )


def test_no_money_above_the_reserve_orders_nothing(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    _catalogue(svc)
    _switched_on(svc)
    _spent(svc, 189.5)
    asked = _curator(fake, {"works": [], "choice": 0, "reason": "-"})
    count, said = svc.leftover.at_night()
    assert count == 0 and said.startswith("brak wolnych środków")
    assert asked == []


def test_the_runners_up_first_then_the_curator(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    _catalogue(svc)
    _add(svc, "met:7", title="The Hay Wain", artist="John Constable", year=1821)
    _add(svc, "met:8", title="Another Constable", artist="John Constable", year=1822)
    _switched_on(svc)
    _spent(svc, 180.0)  # 10 USD left above the reserve: twelve studies
    svc.daily.keep_runners_up(
        [svc.library.get("met:7"), svc.library.get("met:8")],  # type: ignore[list-item]
        date(2026, 11, 20),
    )
    asked = _curator(fake, {"works": [], "choice": 0, "reason": "-"})

    def answer(**params: Any) -> Any:
        numbers = _numbers(params)
        from test_ai import _message

        asked.append(params)
        return _message(
            {
                "works": [
                    {"n": n, "what": "", "fit": t != "South Wind, Clear Sky", "why": ""}
                    for t, n in numbers.items()
                ],
                "choice": min(numbers.values()),
                "reason": "-",
            }
        )

    fake.messages.create = answer
    count, said = svc.leftover.at_night()
    orders = svc.library.get_state(leftover_module.STATE_KEY)["orders"]
    # The newest runner-up first, one per artist; then the curator's.
    assert "met:8" in orders and "met:7" not in orders
    assert orders["met:8"]["from"] == "runner"
    assert {i for i, o in orders.items() if o["from"] == "curator"} >= {"met:3", "met:4"}
    assert count == len(orders) and said.startswith("zamówione")
    assert all(svc.ai.later(STUDY, item_id) for item_id in orders)
    # The other Constable waits; nobody's study is ordered twice, and the
    # study of the day leaves them alone.
    assert "met:7" in svc.daily.runners_up() and "met:8" not in svc.daily.runners_up()
    fits = svc.daily.studyable()
    assert not any(fits(svc.library.get(i)) for i in orders)  # type: ignore[arg-type]
    view = svc.leftover.view()
    assert view["ordered"] == view["in_flight"] == len(orders)
    assert view["free_usd"] < 10.0


def test_a_study_from_the_rest_tells_nobody(tmp_path: Path) -> None:
    _, svc, _ = _claude(tmp_path)
    item = _add(svc, "met:1", title="A Work", artist="Someone")
    told: list[str] = []
    svc.notifier.study_step = lambda item_id, status, *rest: told.append(status)  # type: ignore[method-assign]
    svc.leftover.now = lambda: NIGHT
    state = svc.leftover._state()
    state["orders"]["met:1"] = {"at": NIGHT.isoformat(), "from": "runner"}
    svc.leftover._save(state)
    svc._study_step(item, "ready", "")
    assert told == []
    assert svc.leftover.view()["made"] == 1
    # A study asked for by the owner is told as before.
    other = _add(svc, "met:2", title="Another", artist="Someone Else")
    svc._study_step(other, "ready", "")
    assert told == ["ready"]


def test_what_no_study_takes_goes_on_the_catalogues_texts(tmp_path: Path) -> None:
    _, svc, fake = _claude(tmp_path)
    _switched_on(svc)
    svc.ai_config.update(AiConfigUpdate(pl_text=True))
    _spent(svc, 150.0)
    _add(svc, "met:1", title="A Work", artist="", description="A long story " * 30)
    count, said = svc.leftover.at_night()
    assert count == 0 and "opisy katalogu" in said
    assert any(r["params"]["model"] for requests in fake.batches.values() for r in requests)


def test_the_app_sees_and_sets_it(tmp_path: Path) -> None:
    app, svc, _ = _claude(tmp_path)
    token = svc.settings.api_token
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with TestClient(app) as client:
        got = client.put(
            "/api/ai",
            json={"leftover": True, "leftover_days": 4, "period_day": 17},
            headers=headers,
        ).json()
        assert got["leftover"] is True and got["leftover_days"] == 4
        assert got["period_day"] == 17 and got["period_start"].endswith("-17")
        assert got["leftover_state"]["per_study_usd"] == leftover_module.STUDY_USD
        assert client.put("/api/ai", json={"period_day": 31}, headers=headers).status_code == 422
