"""Konfiguracja's "Koszty": what each thing cost over the last days."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from frame_server.ai import costs
from frame_server.ai.client import SPEND_KEY, Spending
from frame_server.ai.gemini import SPEND_KEY as GEMINI_KEY
from frame_server.config import Settings
from frame_server.service import FrameService
from frame_server.web.app import create_app

NOW = datetime(2026, 11, 16, 7, tzinfo=UTC)


def test_the_last_days_are_today_and_the_six_before(service: FrameService) -> None:
    service.library.set_state(
        SPEND_KEY,
        {
            "2026-11": {"study": 50.0},  # by month, from before the days
            "2026-11-09": {"study": 9.0},  # eight days ago
            "2026-11-10": {"study": 1.0, "keywords": 0.25},
            "2026-11-16": {"keywords": 0.5},
        },
    )
    spending = Spending(service.library)
    assert spending.last_days(7, NOW) == {"study": 1.0, "keywords": 0.75}


def test_the_rows_put_the_kinds_together_and_count_the_rest_as_other(
    service: FrameService,
) -> None:
    service.library.set_state(
        SPEND_KEY,
        {
            "2026-11-02": {"daily": 2.0},
            "2026-11-15": {
                "composition": 0.3,
                "composition_text": 0.1,
                "study": 1.0,
                "pl_text": 0.2,
                "museum_words": 0.01,
                "twins.judge": 0.02,
                "something_new": 0.05,
            },
        },
    )
    rows = {row["key"]: row for row in costs.rows(Spending(service.library), costs.CLAUDE, NOW)}
    assert rows["studies"]["days_usd"] == 1.4
    assert rows["pl_text"]["days_usd"] == 0.21
    assert rows["twins_judge"]["label"] == "Sędzia powtórek"
    # Before the last seven days, still in the period.
    assert rows["daily"] == {
        "key": "daily",
        "label": "Studium dnia (wybór i tekst)",
        "days_usd": 0.0,
        "period_usd": 2.0,
    }
    assert rows["other"]["days_usd"] == 0.05
    # What cost nothing is left out.
    assert "crops" not in rows
    # In the page's order, "Inne" last.
    keys = [row["key"] for row in costs.rows(Spending(service.library), costs.CLAUDE, NOW)]
    assert keys == ["pl_text", "daily", "studies", "twins_judge", "other"]


def test_konfiguracja_gets_claudes_and_geminis_apart(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    today = datetime.now(UTC).date().isoformat()
    svc.library.set_state(SPEND_KEY, {today: {"crops": 0.12}})
    svc.library.set_state(GEMINI_KEY, {today: {"sheet": 0.3, "looks": 0.001}})
    with TestClient(app) as client:
        view = client.get("/api/ai").json()
    assert view["cost_days"] == 7
    assert view["claude_costs"] == [
        {"key": "crops", "label": "Kadrowanie zdjęć dzieł", "days_usd": 0.12, "period_usd": 0.12}
    ]
    assert [row["key"] for row in view["gemini_costs"]] == ["drawn", "looks"]
