"""Na żądanie, w trybie zwykłym: a use of the month's rest run now for the
owner's amount, at the full price (on_demand.py)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_ai import ANSWER, GOOD_KEY, FakeAnthropic, _add, _message, fake  # noqa: F401  (fixture)
from test_daily import _app

from frame_server import on_demand as on_demand_module
from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU, cost
from frame_server.ai.keywords import KIND as KEYWORDS
from frame_server.leftover import KEYWORDS as TEXTS
from frame_server.on_demand import OnDemand, OnDemandError, Plan
from frame_server.service import FrameService

#: What one keywords answer of the fake costs at the full price.
EACH = cost(HAIKU, _message(ANSWER).usage)


def _limit(service: FrameService, usd: float = 200.0, reserve: float = 10.0) -> None:
    service.ai_config.update(
        AiConfigUpdate(monthly_limit_usd=usd, leftover_reserve_usd=reserve, keywords_artworks=True)
    )


def _works(service: FrameService, n: int) -> None:
    for k in range(1, n + 1):
        _add(service, f"met:{k}", title=f"Work {k}", artist=f"Painter {k}")


def _ended(service: FrameService, key: str = TEXTS) -> dict[str, Any]:
    for _ in range(400):
        view = service.on_demand.view(key)
        if view is not None and not view["running"]:
            return view
        time.sleep(0.02)
    raise AssertionError("the run did not end")


def test_a_run_asks_now_until_nothing_waits(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _limit(service)
    _works(service, 6)
    service.on_demand.start(TEXTS, 50.0)
    view = _ended(service)
    assert view["done"] == 6 and view["changed"] == 6 and view["failed"] == 0
    assert view["why"] == on_demand_module.EMPTY and view["waiting"] == 6
    # asked now, one question a work, at the full price; no batch
    assert len(fake.asked) == 6 and not fake.batches
    assert view["spent_usd"] == round(6 * EACH, 2)
    assert all(service.library.note(f"met:{k}", KEYWORDS) is not None for k in range(1, 7))


def test_a_run_stops_when_its_amount_is_spent(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit(service)
    _works(service, 10)
    monkeypatch.setitem(on_demand_module.THREADS, TEXTS, 1)
    run = service.on_demand
    plans = run._plans()
    plans[TEXTS].each = lambda: EACH  # reckoned as it is
    run._plans = lambda: plans  # type: ignore[method-assign]
    usd = 3.5 * EACH
    monkeypatch.setattr(on_demand_module, "MIN_USD", 0.0)
    run.start(TEXTS, usd)
    view = _ended(service)
    assert view["why"] == on_demand_module.SPENT
    assert view["done"] == 3 and len(fake.asked) == 3
    record = run._state()[TEXTS]
    assert record["spent_usd"] <= usd


def test_a_run_never_takes_the_reserve(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _limit(service, usd=30.0, reserve=10.0)
    service.claude.spending.add("study", 15.0)
    _works(service, 2)
    with pytest.raises(OnDemandError, match=r"zostało ok\. 5,00 USD"):
        service.on_demand.start(TEXTS, 6.0)
    with pytest.raises(OnDemandError, match="Kwota"):
        service.on_demand.start(TEXTS, 0.5)
    with pytest.raises(OnDemandError, match="nie da się"):
        service.on_demand.start("studies", 5.0)
    service.ai_config.update(
        AiConfigUpdate(keywords_artworks=False, keywords_photos=False, pl_text=False)
    )
    with pytest.raises(OnDemandError, match="wyłączone"):
        service.on_demand.start(TEXTS, 5.0)
    assert not fake.asked


def test_the_meter_counts_only_its_own_thread(service: FrameService) -> None:
    spending = service.claude.spending
    with spending.meter() as counted:
        spending.add("keywords", 0.25)
        other = threading.Thread(target=spending.add, args=("keywords", 1.0))
        other.start()
        other.join()
        with spending.meter() as inner:
            spending.add("pl_text", 0.5)
    assert counted == [0.75] and inner == [0.5]
    assert spending.total() == pytest.approx(1.75)


def test_the_night_leaves_a_running_use_and_its_money(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit(service)
    held = threading.Event()
    seen: list[str] = []

    def one(item_id: str) -> bool:
        seen.append(item_id)
        held.wait(5)
        return True

    monkeypatch.setitem(on_demand_module.THREADS, TEXTS, 1)
    plan = Plan(each=lambda: 0.01, waiting=lambda: ["a", "b"], one=one, able=lambda: True)
    run = service.on_demand
    run._plans = lambda: {TEXTS: plan}  # type: ignore[method-assign]
    free = service.leftover.free_usd()
    run.start(TEXTS, 40.0)
    for _ in range(100):
        if seen:
            break
        time.sleep(0.02)
    assert run.running(TEXTS)
    assert service.leftover.free_usd() == pytest.approx(free - 40.0)
    assert run.free_usd() == pytest.approx(free - 40.0)
    with pytest.raises(OnDemandError, match="już działa"):
        run.start(TEXTS, 5.0)
    assert run.stop(TEXTS)
    held.set()
    view = _ended(service)
    assert view["why"] == on_demand_module.STOPPED and view["done"] == 1
    assert service.leftover.free_usd() == pytest.approx(free)
    assert not run.stop(TEXTS)


def test_a_run_cut_short_by_a_restart_says_so(service: FrameService) -> None:
    service.library.set_state(
        on_demand_module.STATE_KEY,
        {TEXTS: {"key": TEXTS, "usd": 50.0, "spent_usd": 12.5, "done": 900, "started": "x"}},
    )
    again = OnDemand(
        service.library, service.claude, service.ai_config, service.ai, service.leftover
    )
    view = again.view(TEXTS)
    assert view is not None and not view["running"]
    assert view["why"] == on_demand_module.RESTART and view["spent_usd"] == 12.5


def test_the_app_starts_and_stops_a_run(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    answers = FakeAnthropic(GOOD_KEY)
    svc.claude.factory = lambda key: answers
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False))
    _limit(svc)
    _works(svc, 3)
    token = svc.settings.api_token
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with TestClient(app) as client:
        got = client.get("/api/ai", headers=headers).json()
        (texts,) = (u for u in got["leftover_state"]["uses"] if u["key"] == TEXTS)
        assert texts["now_each_usd"] > 0 and texts["run"] is None
        assert got["leftover_state"]["now_free_usd"] == pytest.approx(190.0)
        (crops,) = (u for u in got["leftover_state"]["uses"] if u["key"] == "crops")
        assert crops["now_each_usd"] > 0
        (studies,) = (u for u in got["leftover_state"]["uses"] if u["key"] == "studies")
        assert studies["now_each_usd"] is None
        bad = client.post("/api/ai/on-demand", json={"key": TEXTS, "usd": 900}, headers=headers)
        assert bad.status_code == 409 and "Kwota" in bad.json()["detail"]
        ok = client.post("/api/ai/on-demand", json={"key": TEXTS, "usd": 20}, headers=headers)
        assert ok.status_code == 200
        _ended(svc)
        got = client.get("/api/ai", headers=headers).json()
        (texts,) = (u for u in got["leftover_state"]["uses"] if u["key"] == TEXTS)
        # (the background may have asked about some meanwhile)
        assert texts["run"]["waiting"] is not None and texts["run"]["usd"] == 20
        assert client.post(f"/api/ai/on-demand/{TEXTS}/stop", headers=headers).status_code == 404
