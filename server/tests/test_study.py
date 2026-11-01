"""A study of any work, asked for on its card: the work of the day's page
for the work, written once and kept."""

from __future__ import annotations

import io
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from test_ai import GOOD_KEY, FakeAnthropic
from test_daily import ANSWER_PX, _app, _catalogue, _today_is, written

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import OPUS
from frame_server.ai.study import KIND
from frame_server.daily import HISTORY_KEY
from frame_server.service import FrameService


def _studies(fake: FakeAnthropic) -> list[dict[str, Any]]:
    return written(fake)


def _ready(client: TestClient, item_id: str) -> dict[str, Any]:
    """The study once its fragments are cut."""
    for _ in range(40):
        view = client.get(f"/api/study/{item_id}?wait=1").json()
        if view["status"] not in ("waiting", "sources", "writing", "details"):
            return view
        time.sleep(0.05)
    raise AssertionError(f"still {view['status']}")


def test_without_a_key_there_is_no_study(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        _catalogue(app.state.service)
        assert client.get("/api/study/met:1").json()["status"] == "off"
        assert client.post("/api/study/met:1").status_code == 409


def test_claude_writes_a_study_once_and_it_is_kept(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False, daily=False))
    with TestClient(app) as client:
        _catalogue(svc)
        svc.ai.start()
        try:
            before = client.get("/api/study/met:1").json()
            assert before["status"] == "none" and before["work"] is None
            assert 0 < before["cost_usd"] < 1
            # Opening the card asks for keywords and Polish texts, never a study.
            client.post("/api/library/items/met:3/describe")
            assert client.get("/api/study/met:3").json()["status"] == "none"

            steps: list[str] = []
            svc.study.on_step = lambda item, status, error: steps.append(status)
            client.post("/api/study/met:1?wait=10")
            view = _ready(client, "met:1")
        finally:
            svc.ai.stop()
        assert view["status"] == "ready", view
        # Each step told (the Lock Screen card), "ready" once the fragments are cut.
        for _ in range(40):  # told just after the status says so
            if steps[-1:] == ["ready"]:
                break
            time.sleep(0.05)
        assert steps[-3:] == ["writing", "details", "ready"], steps
        assert set(steps) <= {"waiting", "sources", "writing", "details", "ready"}
        work = view["work"]
        assert work["written"] is True and work["model"] == OPUS
        assert work["title"] == "Wielka fala w Kanagawie"
        assert work["why_today"] == "" and work["day"] == "" and work["previous"] == []
        assert [v["title"] for v in work["composition"]["views"]] == [
            "Geometria",
            "Geometria detali",
        ]
        assert [(s["item"]["item"]["id"], s["why"]) for s in work["similar"]] == [
            ("met:2", "ta sama seria")
        ]
        details = work["details"]
        assert details[0]["image"].startswith("/api/study/met%3A1/detail?n=0&v=")
        cut = client.get(details[1]["image"])
        assert cut.status_code == 200
        assert Image.open(io.BytesIO(cut.content)).size == (270, 240)
        assert client.get("/api/study/met:1/detail?n=5").status_code == 404
        assert work["partial"] is False

        # The text first: the same page without its lists, for the app to
        # open with while it asks for the rest.
        text = client.get("/api/study/met:1?lists=false").json()
        assert text["status"] == "ready"
        first = text["work"]
        assert first["partial"] is True
        assert first["similar"] == [] and first["legacy"] == [] and first["by_artist"] == []
        assert first["legacy_pending"] is False
        for key in ("title", "context", "artist", "composition", "colour", "details", "teaser"):
            assert first[key] == work[key], key

        (asked,) = _studies(fake)
        assert "studium" in asked["system"][0]["text"]
        assert "Dziś jest" in asked["messages"][0]["content"][1]["text"]

        # Kept: asked once, and still there after the prompt changes.
        client.post("/api/study/met:1")
        note = svc.library.note("met:1", KIND)
        assert note is not None
        svc.library.save_note(note.model_copy(update={"prompt_version": "study-0"}))
        assert client.get("/api/study/met:1").json()["status"] == "ready"
        assert len(_studies(fake)) == 1


def test_a_new_study_on_request(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = {**ANSWER_PX, "teaser": ""}  # unusable
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False, daily=False))
    with TestClient(app) as client:
        _catalogue(svc)
        svc.ai.start()
        try:
            steps: list[tuple[str, str]] = []
            svc.study.on_step = lambda item, status, error: steps.append((status, error))
            client.post("/api/study/met:1?wait=10")
            failed = _ready(client, "met:1")
            assert failed["status"] == "failed" and failed["error"]
            assert steps[-1] == ("failed", failed["error"])
            client.post("/api/study/met:1?wait=10")  # not asked again by itself
            assert len(_studies(fake)) == 1

            fake.answer = ANSWER_PX
            client.post("/api/study/met:1?again=true&wait=10")
            assert _ready(client, "met:1")["status"] == "ready"
        finally:
            svc.ai.stop()
        assert len(_studies(fake)) == 2


def test_discover_lists_the_written_studies(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False, daily=False))
    with TestClient(app) as client:
        _catalogue(svc)
        assert client.get("/api/studies").json() == []
        svc.ai.start()
        try:
            client.post("/api/study/met:1?wait=10")
            _ready(client, "met:1")
        finally:
            svc.ai.stop()
        # Asked for, not written yet: not listed.
        svc.library.set_state("study_items", ["met:1", "met:3"])
        (brief,) = client.get("/api/studies").json()
        assert brief["item"]["item"]["id"] == "met:1"
        assert brief["title"] == "Wielka fala w Kanagawie"
        assert brief["item"]["item"]["description"] == ""


def test_discover_lists_the_works_of_the_day_too(tmp_path: Path) -> None:
    """ "Studia dzieł" holds every work of the day with its page, by its day,
    and the studies asked for; a work that was both is there once."""
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False))
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    with TestClient(app) as client:
        _catalogue(svc)
        svc.library.set_state(HISTORY_KEY, {yesterday: "met:2", today.isoformat(): "met:1"})
        svc.ai.start()
        try:
            assert client.get(f"/api/daily?day={yesterday}&wait=10").json()["written"] is True
            assert client.get("/api/daily?wait=10").json()["written"] is True
            client.post("/api/study/met:3?wait=10")
            assert _ready(client, "met:3")["status"] == "ready"
            client.post("/api/study/met:1?wait=10")  # the day's work: its page
            assert _ready(client, "met:1")["status"] == "ready"
        finally:
            svc.ai.stop()
        # The last written first. The days' pages are the works' studies too.
        for n, item_id in enumerate(["met:2", "met:3", "met:1"]):
            for kind in ("daily", KIND):
                note = svc.library.note(item_id, kind)
                if item_id != "met:3":
                    assert note is not None, (item_id, kind)
                if note is not None:
                    svc.library.save_note(
                        note.model_copy(update={"created_at": f"2026-10-0{n + 1}T10:00:00"})
                    )
        briefs = client.get("/api/studies").json()
        assert [(b["item"]["item"]["id"], b["day"]) for b in briefs] == [
            ("met:1", today.isoformat()),
            ("met:3", None),
            ("met:2", yesterday),
        ]


def test_a_page_is_written_once_for_the_day_and_the_study(tmp_path: Path) -> None:
    """The work of the day's page is the work's study, and the other way
    round; a new prompt keeps both: Claude is paid once per work."""
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    fake = FakeAnthropic(GOOD_KEY)
    fake.answer = ANSWER_PX
    svc.claude.factory = lambda key: fake
    svc.ai_config.set_key(GOOD_KEY)
    svc.ai_config.update(AiConfigUpdate(pl_text=False, keywords_artworks=False))
    with TestClient(app) as client:
        _catalogue(svc)
        _today_is(svc, "met:1")
        svc.ai.start()
        try:
            assert client.get("/api/daily?wait=10").json()["written"] is True
            assert len(_studies(fake)) == 1
            # The day's work studied: its page, no new question.
            client.post("/api/study/met:1?wait=10")
            view = _ready(client, "met:1")
            assert view["status"] == "ready"
            # "Why today" while it is the study of the day.
            assert view["work"]["why_today"] == "Jutro mija 266 lat od urodzin Hokusaia."
            assert len(_studies(fake)) == 1

            # A studied work picked for a day: its study, no new question.
            client.post("/api/study/met:3?wait=10")
            assert _ready(client, "met:3")["status"] == "ready"
            assert len(_studies(fake)) == 2
            _today_is(svc, "met:3")
            work = client.get("/api/daily?wait=10").json()
            assert work["item"]["item"]["id"] == "met:3" and work["written"] is True
            assert work["why_today"] == ""
            assert len(_studies(fake)) == 2

            # A new prompt: the pages written stay.
            note = svc.library.note("met:3", "daily")
            assert note is not None
            svc.library.save_note(note.model_copy(update={"prompt_version": "daily-0"}))
            assert client.get("/api/daily?wait=10").json()["written"] is True
            assert len(_studies(fake)) == 2
        finally:
            svc.ai.stop()
