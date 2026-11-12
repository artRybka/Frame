"""Notes ordered for later, for less: a study's "Przygotuj na później" and
every day's page a day ahead. Their long (Opus) questions go through the
Batch API one by one; the short ones are asked at once."""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic, _message
from test_daily import ANSWER_PX, _app, _catalogue, _like, composing, written

from frame_server.ai import AiConfigUpdate, study_pick
from frame_server.ai.client import FABLE, OPUS
from frame_server.ai.daily import KIND as DAILY
from frame_server.ai.jobs import BATCHES_KEY, LATER_KEY, Ask, Deferred
from frame_server.ai.study import KIND
from frame_server.service import FrameService


def _setup(tmp_path: Path, *, daily: bool = False) -> tuple[Any, FrameService, FakeAnthropic]:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False, daily=daily))
    svc.daily.sharper = None  # no museum asked for a sharper copy
    return app, svc, fake


def _batched(fake: FakeAnthropic) -> list[dict[str, Any]]:
    """Batches answer as the fake does; the questions they got, in turn."""
    got: list[dict[str, Any]] = []

    def results(batch_id: str) -> list[SimpleNamespace]:
        out = []
        for r in fake.batches[batch_id]:
            got.append(r["params"])
            ok = SimpleNamespace(type="succeeded", message=_message(fake.answer))
            out.append(SimpleNamespace(custom_id=r["custom_id"], result=ok))
        return out

    fake.messages.batches.results = results
    return got


def test_questions_that_do_not_wait_for_one_another_are_asked_together(tmp_path: Path) -> None:
    """The pen's close-ups: at once at the same time, or (an order for
    later) in one batch; what is answered is kept in its order."""
    app, svc, fake = _setup(tmp_path)
    with TestClient(app):
        _catalogue(svc)

        def question(model: str, n: int) -> dict[str, Any]:
            return {"model": model, "max_tokens": 100, "messages": [{"role": "user", "content": n}]}

        # No order: asked now, each answer in its question's place.
        ask = Ask(svc.ai, KIND, "met:1", defer=False)
        assert ask.many([]) == []
        answers = ask.many([question(OPUS, n) for n in range(3)])
        assert len(answers) == 3 and len(fake.asked) == 3
        assert svc.library.get_state(LATER_KEY, {}) == {}
        # An order for later: the long ones go into one batch, the first
        # named "q" and those with it "q1", "q2"…
        svc.library.set_state(LATER_KEY, {f"{KIND}|met:1": {"answers": [], "batch": ""}})
        ask = Ask(svc.ai, KIND, "met:1", defer=True)
        first = ask(question("claude-haiku", 0))  # a short one: at once, and kept
        assert first.data is not None and len(fake.asked) == 4
        several = [question(FABLE, n) for n in (1, 2, 3)]
        try:
            ask.many(several)
            raise AssertionError("asked at full price")
        except Deferred as put_off:
            assert put_off.seq == 1 and put_off.params == several[0]
            assert put_off.also == several[1:]
            svc.ai._defer(KIND, "met:1", put_off)
        assert [r["custom_id"] for r in fake.batches["batch_1"]] == ["q", "q1", "q2"]
        (record,) = svc.library.get_state(BATCHES_KEY, [])
        assert record["later"] == 1 and set(record["ids"].values()) == {"met:1"}
        assert len(fake.asked) == 4
        # Finished now instead: the ones not answered are asked together,
        # and kept after the one that was.
        ask = Ask(svc.ai, KIND, "met:1", defer=False)
        assert ask(question("claude-haiku", 0)).model == first.model and len(fake.asked) == 4
        assert len(ask.many(several)) == 3 and len(fake.asked) == 7
        kept = svc.library.get_state(LATER_KEY, {})[f"{KIND}|met:1"]["answers"]
        assert len(kept) == 4
        # Made from its start again: nothing is asked twice.
        ask = Ask(svc.ai, KIND, "met:1", defer=True)
        ask(question("claude-haiku", 0))
        assert len(ask.many(several)) == 3 and len(fake.asked) == 7


def _ready(client: TestClient, item_id: str) -> dict[str, Any]:
    for _ in range(60):
        view = client.get(f"/api/study/{item_id}").json()
        if view["status"] == "ready":
            return view
        time.sleep(0.05)
    raise AssertionError(f"still {view['status']}")


def test_a_study_ordered_for_later_goes_through_batches(tmp_path: Path) -> None:
    app, svc, fake = _setup(tmp_path)
    got = _batched(fake)
    with TestClient(app) as client:
        _catalogue(svc)
        _like(svc)
        before = client.get("/api/study/met:1").json()
        assert 0 < before["later_cost_usd"] < before["cost_usd"]

        steps: list[str] = []
        svc.study.on_step = lambda item, status, error: steps.append(status)
        view = client.post("/api/study/met:1?later=true").json()
        assert view["status"] == "later"
        # Ordered once: asked again, it stays the same order.
        assert client.post("/api/study/met:1?later=true").json()["status"] == "later"

        svc.ai._advance_all()  # the worker's next look
        assert list(fake.batches) == ["batch_1"]
        assert fake.asked == []  # nothing asked at full price
        (page,) = [r["params"] for r in fake.batches["batch_1"]]
        assert page["model"] == OPUS and not composing(page)
        assert "timeout" not in page  # the client's own, no part of a request
        svc.ai._advance_all()  # waiting for its batch: not sent again
        assert list(fake.batches) == ["batch_1"]
        assert client.get("/api/study/met:1").json()["status"] == "later"

        fake.ended = True
        svc.ai.poll_batches()  # the page in; its composition's analysis next
        assert list(fake.batches) == ["batch_1", "batch_2"]
        (analysis,) = [r["params"] for r in fake.batches["batch_2"]]
        assert analysis["model"] == OPUS and composing(analysis)
        assert [b["id"] for b in svc.library.get_state(BATCHES_KEY, [])] == ["batch_2"]
        assert client.get("/api/study/met:1").json()["status"] == "later"

        svc.ai.poll_batches()  # the analysis in: the short steps asked at once
        assert list(fake.batches) == ["batch_1", "batch_2", "batch_3"]
        (sketch,) = [r["params"] for r in fake.batches["batch_3"]]
        assert sketch["model"] == FABLE and composing(sketch)  # the pen's drawing
        assert client.get("/api/study/met:1").json()["status"] == "later"

        svc.ai.poll_batches()  # the drawing in (it asked for no close-ups)
        assert list(fake.batches) == ["batch_1", "batch_2", "batch_3", "batch_4"]
        (text,) = [r["params"] for r in fake.batches["batch_4"]]
        assert text["model"] == OPUS and composing(text)  # its text, written last
        assert client.get("/api/study/met:1").json()["status"] == "later"

        svc.ai.poll_batches()  # the text in: the page made
        view = _ready(client, "met:1")
        assert len(got) == 4
        models = [p["model"] for p in fake.asked]
        assert all(m not in (OPUS, FABLE) for m in models), models
        assert fake.asked and all(composing(p) for p in fake.asked)
        assert svc.library.get_state(LATER_KEY, {}) == {}
        assert svc.library.get_state(BATCHES_KEY, []) == []
        work = view["work"]
        assert work["title"] == "Wielka fala w Kanagawie"
        assert [v["title"] for v in work["composition"]["views"]] == ["Analiza kompozycji"]
        for _ in range(40):  # "Studium gotowe": told once the fragments are cut
            if steps[-1:] == ["ready"]:
                break
            time.sleep(0.05)
        assert steps[-1:] == ["ready"], steps


def test_a_study_ordered_for_later_can_be_made_now(tmp_path: Path) -> None:
    """Made now ("Przygotuj na już") after "na później": what the batches answered is
    not paid for again."""
    app, svc, fake = _setup(tmp_path)
    _batched(fake)
    with TestClient(app) as client:
        _catalogue(svc)
        assert client.post("/api/study/met:1?later=true").json()["status"] == "later"
        svc.ai._advance_all()
        fake.ended = True
        svc.ai.poll_batches()  # the page in; the analysis in batch_2, not ended
        fake.ended = False
        assert list(fake.batches) == ["batch_1", "batch_2"]

        svc.ai.start()
        try:
            client.post("/api/study/met:1?wait=10")
            view = _ready(client, "met:1")
        finally:
            svc.ai.stop()
        assert view["work"]["title"] == "Wielka fala w Kanagawie"
        assert written(fake) == []  # the page from its batch
        analyses = [p for p in fake.asked if p["model"] == OPUS]
        assert len(analyses) == 2 and all(composing(p) for p in analyses)  # analysis, text
        assert svc.library.get_state(LATER_KEY, {}) == {}
        note = svc.library.note("met:1", KIND)

        fake.ended = True
        svc.ai.poll_batches()  # the order's batch ends after all: nothing changes
        assert svc.library.note("met:1", KIND) == note
        assert svc.library.get_state(BATCHES_KEY, []) == []


def test_tomorrows_page_is_ordered_for_later_and_kept_for_its_day(tmp_path: Path) -> None:
    app, svc, fake = _setup(tmp_path, daily=True)
    _batched(fake)
    with TestClient(app):
        _catalogue(svc)
        today = date.today()
        svc.daily.tick(today)
        tomorrow = svc.daily.item(today + timedelta(days=1))
        work = svc.daily.item(today)
        assert tomorrow is not None and work is not None and tomorrow.id != work.id
        assert svc.ai.later(DAILY, tomorrow.id)
        assert not svc.ai.later(DAILY, work.id)  # today's asked now

        svc.ai._advance_all()
        fake.ended = True
        for _ in range(4):  # the page, its analysis, its drawing, its text
            svc.ai.poll_batches()
        assert svc.daily.job.essay(tomorrow) is not None
        assert not svc.ai.later(DAILY, tomorrow.id)
        # Not a study before its day.
        svc.daily.adopt_all()
        assert svc.study.job.essay(tomorrow) is None
        assert tomorrow.id not in [item.id for item, _, _ in svc.study.written()]
        assert all(p["model"] != OPUS for p in fake.asked)  # all of it in batches

        # Its day: the page is there, nothing asked again (but the curator,
        # about the day after).
        asked = len(fake.asked)
        svc.daily.tick(today + timedelta(days=1))
        assert svc.daily.ask(tomorrow) is None
        assert all(p["model"] == study_pick.MODEL for p in fake.asked[asked:])
