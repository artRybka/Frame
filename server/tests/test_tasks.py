"""Zadania (Mateusz 2026-11-17): each use of the month's rest set as a task,
when it runs, how many a night, for how much, and how it asks
(leftover.task, leftover.set_task)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_ai import FakeAnthropic, _add, fake  # noqa: F401  (fixture)
from test_daily import _claude
from test_leftover import NIGHT, _fake_uses, _spent, _switched_on
from test_on_demand import EACH, _ended, _limit, _works

from frame_server import leftover as leftover_module
from frame_server import on_demand as on_demand_module
from frame_server.ai import AiConfigUpdate
from frame_server.ai.config import TaskSettings, TaskUpdate
from frame_server.leftover import CROPS, KEYWORDS, POLISH, STUDIES, set_task, task
from frame_server.leftover import KEYWORDS as TEXTS
from frame_server.on_demand import OnDemandError
from frame_server.service import FrameService

#: A night early in November's period, far from its last days.
EARLY = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)


def test_a_task_is_as_it_was_until_the_owner_sets_it(tmp_path: Path) -> None:
    _, svc, _ = _claude(tmp_path)
    store = svc.ai_config
    assert task(store.config, TEXTS).when == "rest"
    # the audit's portion every night, more at the period's end only when he says
    audit = task(store.config, "audit")
    assert audit.when == "night" and audit.more_at_end is False
    set_task(store, "audit", TaskUpdate(when="night", a_night=500))
    set_task(store, TEXTS, TaskUpdate(when="off", a_night=2000, night_usd=5))
    config = store.config
    assert task(config, "audit").when == "night" and task(config, "audit").a_night == 500
    # the older switches kept in step
    assert config.leftover_off == [TEXTS, "audit"]
    assert dict(leftover_module.uses(config))[TEXTS] is False
    # 0 is "no limit of its own"
    set_task(store, TEXTS, TaskUpdate(night_usd=0))
    assert task(store.config, TEXTS).night_usd is None
    assert task(store.config, TEXTS).a_night == 2000
    with pytest.raises(ValueError, match="Batch"):
        set_task(store, STUDIES, TaskUpdate(mode="normal"))
    with pytest.raises(ValueError, match="liczby na noc"):
        set_task(store, "refresh", TaskUpdate(a_night=10))
    with pytest.raises(ValueError, match="takiego"):
        set_task(store, "nonsense", TaskUpdate(when="night"))


def test_the_catalogues_texts_become_two_tasks_as_they_were(tmp_path: Path) -> None:
    """Mateusz 2026-11-17: "Słowa kluczowe i polskie opisy - czy to nie dwa,
    odrębne procesy?" The one task they were is two; what he set for it, its
    place in his order and its switch off hold for both."""
    _, svc, _ = _claude(tmp_path)
    store = svc.ai_config
    old = TaskSettings(when="night", a_night=2000, night_usd=10, mode="normal")
    store.set_tasks(
        {"descriptions": old},
        leftover_order=["studies", "descriptions", "refresh"],
        leftover_off=["audit"],
    )
    for key in (KEYWORDS, POLISH):
        assert task(store.config, key) == old
    order = [k for k, _ in leftover_module.uses(store.config)]
    assert order[:3] == ["studies", KEYWORDS, POLISH] and "descriptions" not in order
    assert order.index("refresh") > 2
    # his first change of one keeps the other as it was
    set_task(store, POLISH, TaskUpdate(when="rest", night_usd=0))
    config = store.config
    assert "descriptions" not in config.tasks and "descriptions" not in config.leftover_order
    assert task(config, KEYWORDS) == old
    assert task(config, POLISH).when == "rest" and task(config, POLISH).night_usd is None
    assert config.leftover_order[:3] == ["studies", KEYWORDS, POLISH]
    # switched off as one, both are off
    store.set_tasks({}, leftover_off=["descriptions"])
    assert task(store.config, KEYWORDS).when == "off" == task(store.config, POLISH).when


def test_a_task_set_for_every_night_runs_outside_the_last_days(tmp_path: Path) -> None:
    _, svc, _ = _claude(tmp_path)
    svc.ai_config.update(AiConfigUpdate(monthly_limit_usd=200, leftover_reserve_usd=10))
    svc.leftover.now = lambda: EARLY
    _spent(svc, 20.0, "2026-11-05")  # 170 USD above the reserve
    calls = _fake_uses(
        svc,
        [
            ("refresh", 0.1, 30, None),
            (TEXTS, 0.01, 100000, 1000),
            ("crops", 0.01, 5000, 540),
        ],
    )
    # the rest's switch is off and its days are far: nothing
    assert svc.leftover.at_night() == (0, "wyłączone")
    store = svc.ai_config
    set_task(store, TEXTS, TaskUpdate(when="night", night_usd=5))
    set_task(store, CROPS, TaskUpdate(when="night"))
    _, said = svc.leftover.at_night()
    # the refresh waits for the period's last days; the texts take their
    # night's amount; the crops every night are their own portion (the rest
    # only adds to it in the last days)
    assert [c[0] for c in calls] == [TEXTS]
    assert dict(calls)[TEXTS] == 5.0
    assert "słowa kluczowe katalogu: 500" in said and "kadrowanie" not in said
    # not on demand only, nor off
    set_task(store, TEXTS, TaskUpdate(when="demand"))
    set_task(store, CROPS, TaskUpdate(when="off"))
    calls.clear()
    assert svc.leftover.at_night() == (0, "wyłączone")
    assert not calls


def test_a_task_stops_at_its_amount_for_the_period(tmp_path: Path) -> None:
    _, svc, _ = _claude(tmp_path)
    _switched_on(svc)  # the period's last days
    _spent(svc, 150.0)  # 40 USD above the reserve
    calls = _fake_uses(svc, [(TEXTS, 0.01, 100000, None)])
    set_task(svc.ai_config, TEXTS, TaskUpdate(period_usd=10))
    svc.leftover.at_night()
    assert calls == [(TEXTS, 10.0)]
    assert svc.leftover.period_spent(TEXTS) == pytest.approx(10.0)
    calls.clear()
    svc.leftover.at_night()  # the period's amount is spent
    assert calls == []
    set_task(svc.ai_config, TEXTS, TaskUpdate(period_usd=50))
    svc.leftover.at_night()
    assert calls == [(TEXTS, 40.0)]  # 50 less the 10 spent
    (texts,) = (u for u in svc.leftover.uses_view() if u["key"] == TEXTS)
    assert texts["period_usd"] == 50 and texts["period_spent_usd"] == pytest.approx(50.0)
    assert texts["when"] == "rest" and texts["modes"] == ["batch", "normal"]


def test_a_task_in_the_normal_mode_is_asked_now_at_night(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit(service)
    service.leftover.now = lambda: EARLY
    service.on_demand.now = lambda: EARLY
    _works(service, 6)
    monkeypatch.setitem(on_demand_module.THREADS, TEXTS, 1)
    store = service.ai_config
    store.update(AiConfigUpdate(pl_text=False))
    set_task(store, TEXTS, TaskUpdate(when="night", mode="normal", night_usd=2, a_night=250))
    # a night's number below what the app offers, to see it with a few works
    settings = task(store.config, TEXTS).model_copy(update={"a_night": 4})
    store.set_task(TEXTS, settings)
    _, said = service.leftover.at_night()
    assert "słowa kluczowe katalogu: od razu, do 2.00 USD" in said
    view = _ended(service)
    assert view["night"] is True and view["usd"] == 2.0
    assert view["done"] == 4 and view["why"] == on_demand_module.COUNT
    assert len(fake.asked) == 4 and not fake.batches
    # what it cost is the task's in the period
    assert service.leftover.period_spent(TEXTS) == pytest.approx(4 * EACH, abs=0.01)


def test_a_task_switched_off_is_not_run_on_demand(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _limit(service)
    set_task(service.ai_config, TEXTS, TaskUpdate(when="off"))
    with pytest.raises(OnDemandError, match="Zadaniach"):
        service.on_demand.start(TEXTS, 5.0)
    set_task(service.ai_config, TEXTS, TaskUpdate(when="demand"))
    _works(service, 1)
    service.on_demand.start(TEXTS, 5.0)
    assert _ended(service)["night"] is False


def test_the_app_sets_a_task(tmp_path: Path) -> None:
    app, svc, _ = _claude(tmp_path)
    svc.leftover.now = lambda: NIGHT
    token = svc.settings.api_token
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with TestClient(app) as client:
        got = client.put(
            f"/api/ai/tasks/{CROPS}",
            json={"when": "night", "a_night": 1000, "night_usd": 2, "mode": "normal"},
            headers=headers,
        )
        assert got.status_code == 200
        state = got.json()["leftover_state"]
        (crops,) = (u for u in state["uses"] if u["key"] == CROPS)
        assert crops["when"] == "night" and crops["a_night"] == 1000
        assert crops["night_usd"] == 2 and crops["period_usd"] is None
        assert crops["mode"] == "normal" and crops["on"] is True
        assert crops["a_night_choices"] == list(leftover_module.A_NIGHT_CHOICES[CROPS])
        assert state["night_usd_choices"] and state["period_usd_choices"]
        assert "planned_usd" in state
        bad = client.put(f"/api/ai/tasks/{STUDIES}", json={"mode": "normal"}, headers=headers)
        assert bad.status_code == 409
        assert (
            client.put("/api/ai/tasks/x", json={"when": "soon"}, headers=headers).status_code == 422
        )


def test_each_task_is_what_it_does_with_every_when_it_can_have(tmp_path: Path) -> None:
    """Mateusz 2026-11-17: "Dlaczego nie wszędzie pełen pakiet opcji? …
    nazwy określające nie to kiedy coś się odbywa, tylko co robi"; "„Nocny
    przegląd” chyba trzeba połączyć z „Większy nocny przegląd”"; "Przegląd
    zapisanych opisów - czy to nie powielenie…". The crops and the audit
    are one task each with their night's portion; the gatekeeper and the
    judge of copies are the catalogue's tidying; the saved texts' review is
    the Polish texts'."""
    _, svc, _ = _claude(tmp_path)
    store = svc.ai_config
    assert "text_review" not in leftover_module.USES
    assert leftover_module.whens("studies") == ["rest", "night", "off"]
    assert leftover_module.whens("audit") == ["rest", "night", "demand", "off"]
    with pytest.raises(ValueError, match="pory"):
        set_task(store, STUDIES, TaskUpdate(when="demand"))

    # the crops: in the period's last days only, its switch still on, the
    # night's own portion none but for a run he starts
    set_task(store, CROPS, TaskUpdate(when="rest"))
    assert store.config.crops is True and store.task_when(CROPS) == "rest"
    assert svc.crops.own_limit(False) == 0
    svc.crops.asked_now = True
    assert svc.crops.own_limit(False) == svc.crops.base_limit(False)
    svc.crops.asked_now = False
    # every night, and more at the end: the rest goes on it in the last days
    set_task(store, CROPS, TaskUpdate(when="night", more_at_end=True))
    assert svc.crops.own_limit(False) == svc.crops.base_limit(False)
    assert leftover_module.rest_when(store.config, CROPS) == "rest"
    set_task(store, CROPS, TaskUpdate(more_at_end=False))
    assert leftover_module.rest_when(store.config, CROPS) == "off"
    set_task(store, CROPS, TaskUpdate(when="off"))
    assert store.config.crops is False
    with pytest.raises(ValueError, match="porcji"):
        set_task(store, STUDIES, TaskUpdate(more_at_end=True))

    # the catalogue's tidying: every night, when asked, or off, its two
    # switches what it covers
    assert task(store.config, "tidy").when == "night"
    set_task(store, "tidy", TaskUpdate(when="demand"))
    assert store.config.gatekeeper and store.config.twins_judge
    assert svc.gatekeeper.own_limit(False) == 0
    assert svc.twins_judge.asked_only("tidy")
    svc.twins_judge.asked_now = True
    assert not svc.twins_judge.asked_only("tidy")
    svc.twins_judge.asked_now = False
    set_task(store, "tidy", TaskUpdate(when="off"))
    assert not store.config.gatekeeper and not store.config.twins_judge
    set_task(store, "tidy", TaskUpdate(when="night"))
    assert store.config.gatekeeper and store.config.twins_judge
    assert svc.gatekeeper.own_limit(False) == svc.gatekeeper.base_limit(False)
    with pytest.raises(ValueError, match="takiej pory"):
        set_task(store, "tidy", TaskUpdate(when="rest"))

    view = {u["key"]: u for u in svc.leftover.uses_view()}
    assert view["tidy"]["whens"] == ["night", "demand", "off"]
    assert view["tidy"]["night_tasks"] == ["gatekeeper", "twins judge"]
    assert view["audit"]["night_tasks"] == ["audit"] and view["audit"]["more_at_end"] is False
    assert view[CROPS]["modes"] == ["batch", "normal"] and view[STUDIES]["modes"] == ["batch"]
