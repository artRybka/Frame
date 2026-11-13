"""The studies written before the facts from the web, filled in at the
owner's tap (frame_server.ai.refresh, Mateusz 2026-11-13 12:49): the facts
through one batch, the rewrites of those they add much to through another;
the composition and everything else on the page stays."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic, fake  # noqa: F401  (fixture)

from frame_server.ai import web_facts
from frame_server.ai.client import OPUS, SONNET
from frame_server.ai.refresh import REFRESHED, VERSION, WORTH, StudyRefresh
from frame_server.config import Settings
from frame_server.library import Item, ItemKind
from frame_server.library.models import Note
from frame_server.service import FrameService
from frame_server.web import create_app

COMPOSITION = {"views": [{"name": "Trójkąt", "marks": []}]}


def _page(context: list[str], **more: Any) -> dict[str, Any]:
    return {
        "teaser": "Sypialnia w Arles.",
        "headline": "Pokój w żółtym domu",
        "context": context,
        "artist": "Holenderski malarz.",
        "colour": "Fiolet ścian i żółć łóżka.",
        "composition": COMPOSITION,
        "details": [{"title": "Krzesło"}],
        **more,
    }


def _study(service: FrameService, item_id: str, kind: str = "study", **page: Any) -> Item:
    item = service.library.get(item_id) or service.library.upsert(
        Item(
            id=item_id,
            source=item_id.split(":")[0],
            source_id=item_id.split(":")[1],
            title=f"Work {item_id}",
            artist="Vincent van Gogh",
            date_text="1889",
            kind=ItemKind.ARTWORK,
        )
    )
    service.library.save_note(
        Note(
            item_id=item_id,
            kind=kind,
            model=OPUS,
            prompt_version="x",
            source_hash="h",
            data=_page(["Pierwszy akapit.", "Drugi akapit."], **page),
            created_at="2026-11-01T10:00:00Z",
        )
    )
    return item


def _searched(data: dict[str, Any]) -> SimpleNamespace:
    text = "Szukałem.\n```json\n" + json.dumps(data, ensure_ascii=False) + "\n```"
    return SimpleNamespace(
        content=[SimpleNamespace(type="server_tool_use"), SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=40_000,
            output_tokens=2_000,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=SimpleNamespace(web_search_requests=5),
        ),
    )


def _answers(client: FakeAnthropic, by_custom_id: dict[str, SimpleNamespace | None]) -> None:
    def results(batch_id: str) -> list[SimpleNamespace]:
        out = []
        for r in client.batches[batch_id]:
            message = by_custom_id.get(r["custom_id"])
            kind = "succeeded" if message is not None else "errored"
            out.append(
                SimpleNamespace(
                    custom_id=r["custom_id"], result=SimpleNamespace(type=kind, message=message)
                )
            )
        return out

    client.messages.batches.results = results


def _rewritten(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(data, ensure_ascii=False))],
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=5_000,
            output_tokens=3_000,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


def test_the_studies_get_their_facts_and_those_worth_it_a_new_text(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    refresh: StudyRefresh = service.study_refresh
    rich = _study(service, "aic:1")
    _study(service, "aic:1", kind="daily", why_today="Dziś rocznica.")
    _study(service, "aic:2")
    told = _study(service, "aic:3")  # written with its facts already
    service.library.save_note(
        Note(
            item_id=told.id,
            kind=web_facts.KIND,
            model=SONNET,
            prompt_version=web_facts.VERSION,
            source_hash=service.web_facts.source_hash(told),
            data={"facts": [{"kind": "losy", "text": "x"}]},
        )
    )
    view = refresh.view()
    assert view["waiting"] == 2 and view["running"] is False
    assert view["facts_usd"] > 0

    assert refresh.start() == 2
    assert refresh.start() == 0  # one order at a time
    (requests,) = fake.batches.values()
    params = requests[0]["params"]
    assert params["model"] == SONNET
    assert params["tools"][0]["type"].startswith("web_search")
    text = params["messages"][0]["content"]
    assert "STUDIUM JUŻ NAPISANE" in text and "Pierwszy akapit." in text and '"worth"' in text
    assert "timeout" not in params  # the client's own, no part of a batch
    assert refresh.view()["running"] and refresh.view()["asked"] == 2

    assert refresh.collect() is False  # still running
    fake.ended = True
    _answers(
        fake,
        {
            "f0": _searched(
                {
                    "facts": [
                        {"kind": "technika", "text": "Ściany były fioletowe, koszenila wyblakła."}
                    ],
                    "technical_study": {"found": False},
                    "worth": 3,
                }
            ),
            "f1": _searched({"facts": [{"kind": "losy", "text": "Drobiazg."}], "worth": 1}),
        },
    )
    fake.ended = True
    assert refresh.collect() is True
    found = service.web_facts.found(rich)
    assert found is not None and found.facts[0].text.startswith("Ściany")
    assert service.library.note("aic:1", web_facts.KIND).data["worth"] == 3  # type: ignore[union-attr]
    assert refresh.view()["found"] == 2 and refresh.view()["waiting"] == 0

    # Only the study the facts add much to is rewritten, by Opus.
    assert refresh.to_rewrite() == ["aic:1"]
    assert len(fake.batches) == 2
    rewrite = fake.batches["batch_2"]
    assert [r["custom_id"] for r in rewrite] == ["r0"]
    sent = rewrite[0]["params"]
    assert sent["model"] == OPUS
    words = sent["messages"][0]["content"][0]["text"]
    assert "NOWE FAKTY" in words and "koszenila" in words and "Drugi akapit." in words

    _answers(
        fake,
        {
            "r0": _rewritten(
                {
                    "headline": "Fioletowe ściany.",
                    "context": ["Nowy pierwszy.", "Nowy drugi."],
                    "colour": "Fiolet, który wyblakł.",
                }
            )
        },
    )
    assert refresh.collect() is True
    for kind in ("study", "daily"):
        page = service.library.note("aic:1", kind)
        assert page is not None
        assert page.data["context"] == ["Nowy pierwszy.", "Nowy drugi."]
        assert page.data["headline"] == "Fioletowe ściany"
        assert page.data["composition"] == COMPOSITION  # the analysis stays
        assert page.data["details"] == [{"title": "Krzesło"}]
        assert page.data["teaser"] == "Sypialnia w Arles."
        assert page.data[REFRESHED]["version"] == VERSION
        assert page.data[REFRESHED]["before"]["context"] == ["Pierwszy akapit.", "Drugi akapit."]
        assert page.created_at == "2026-11-01T10:00:00Z"
    assert service.library.note("aic:1", "daily").data["why_today"] == "Dziś rocznica."  # type: ignore[union-attr]
    other = service.library.note("aic:2", "study")
    assert other is not None and REFRESHED not in other.data  # worth 1: left as it was
    view = refresh.view()
    assert view["rewritten"] == 1 and view["rewrite_waiting"] == 0 and not view["running"]
    assert view["spent_usd"] > 0
    assert service.claude.spending.by_kind()["study_refresh"] > 0
    assert WORTH == 2


def test_a_failed_answer_is_tried_again_once(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    refresh: StudyRefresh = service.study_refresh
    _study(service, "aic:1")
    for _ in range(2):
        assert refresh.start() == 1
        fake.ended = True
        _answers(fake, {"f0": None})
        assert refresh.collect() is True
    assert refresh.waiting() == [] and refresh.start() == 0


def test_the_app_starts_it(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    client = TestClient(app)
    _study(svc, "aic:1")
    assert client.post("/api/ai/study-refresh").status_code == 409  # no key
    svc.claude.factory = FakeAnthropic
    svc.ai_config.set_key(GOOD_KEY)
    view = client.get("/api/ai").json()["study_refresh"]
    assert view["waiting"] == 1 and view["facts_usd"] > 0
    view = client.post("/api/ai/study-refresh").json()["study_refresh"]
    assert view["running"] and view["asked"] == 1
