"""Facts about a work from the web for its study (frame_server.ai.web_facts,
Mateusz 2026-11-13, "G8"): Claude searches, the facts go into the study's
question without the pages they came from."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from frame_server.ai import AiConfigUpdate
from frame_server.ai.daily import Context, request_text
from frame_server.ai.web_facts import KIND, SEARCHES, VERSION, parse
from frame_server.library import Item
from frame_server.library.models import ItemKind
from frame_server.service import FrameService

ANSWER = {
    "facts": [
        {
            "kind": "technika",
            "text": "Ściany były fioletowe, koszenila wyblakła (https://example.org/a) [1].",
        },
        {"kind": "losy", "text": "Obraz trafił do muzeum w 1926 roku, zob. www.example.org/b."},
        {"kind": "ciekawostka", "text": ""},
    ],
    "technical_study": {
        "found": True,
        "what": "Badanie muzeum: RTG i reflektografia",
        "stages": [
            {"stage": "Rysunek", "text": "Czarny rysunek na podkładzie."},
            {"stage": "Kolor", "text": "Płaskie plamy barwy."},
        ],
    },
}


def _message(text: str, stop: str = "end_turn", searches: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="server_tool_use"),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop,
        usage=SimpleNamespace(
            input_tokens=20_000,
            output_tokens=2_000,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=SimpleNamespace(web_search_requests=searches),
        ),
    )


class FakeClaude:
    def __init__(self) -> None:
        self.asked: list[dict[str, Any]] = []
        self.replies: list[SimpleNamespace] = []
        self.messages = self

    def create(self, **params: Any) -> SimpleNamespace:
        self.asked.append(params)
        if self.replies:
            return self.replies.pop(0)
        return _message("Znalazłem.\n```json\n" + json.dumps(ANSWER) + "\n```")


@pytest.fixture
def fake(service: FrameService) -> FakeClaude:
    client = FakeClaude()
    service.claude.factory = lambda key: client
    service.ai_config.set_key("sk-ant-test")
    return client


def _work(service: FrameService, **fields: Any) -> Item:
    fields.setdefault("kind", ItemKind.ARTWORK)
    return service.library.upsert(
        Item(
            id="aic:28560",
            source="aic",
            source_id="28560",
            title="The Bedroom",
            artist="Vincent van Gogh",
            date_text="1889",
            medium="Oil on canvas",
            **fields,
        )
    )


def test_the_answer_is_read_without_its_pages() -> None:
    found = parse("tekst\n```json\n" + json.dumps(ANSWER) + "\n```")
    assert found is not None
    assert [f.text for f in found.facts] == [
        "Ściany były fioletowe, koszenila wyblakła.",
        "Obraz trafił do muzeum w 1926 roku, zob.",
    ]
    assert found.technical.found and [s.stage for s in found.technical.stages] == [
        "Rysunek",
        "Kolor",
    ]
    one = {"found": True, "stages": [{"stage": "Rysunek", "text": "Tylko to."}]}
    alone = parse(json.dumps({"facts": [], "technical_study": one}))
    assert alone is not None and not alone.technical.found  # one stage is no way of making
    assert parse("nic tu nie ma") is None


def test_the_facts_are_asked_once_and_kept(service: FrameService, fake: FakeClaude) -> None:
    item = _work(service)
    facts = service.web_facts.for_study(item)
    assert len(facts) == 2 and "koszenila" in facts[0]
    params = fake.asked[0]
    assert params["tools"][0]["type"] == "web_search_20260209"
    assert params["tools"][0]["max_uses"] == SEARCHES
    assert "The Bedroom" in params["messages"][0]["content"]
    assert "output_config" in params and "format" not in params["output_config"]
    note = service.library.note(item.id, KIND)
    assert note is not None and note.prompt_version == VERSION
    assert "http" not in json.dumps(note.data)  # the pages are kept nowhere
    assert service.web_facts.for_study(item) == facts
    assert len(fake.asked) == 1
    spent = service.claude.spending.by_kind()[KIND]
    assert spent == pytest.approx(20_000 * 2e-6 + 2_000 * 10e-6 + 2 * 0.01)


def test_a_paused_turn_goes_on(service: FrameService, fake: FakeClaude) -> None:
    item = _work(service)
    fake.replies = [_message("Szukam…", stop="pause_turn")]
    assert len(service.web_facts.for_study(item)) == 2
    assert len(fake.asked) == 2
    assert fake.asked[1]["messages"][-1]["role"] == "assistant"


def test_nothing_is_asked_when_switched_off_or_for_a_photo(
    service: FrameService, fake: FakeClaude
) -> None:
    service.ai_config.update(AiConfigUpdate(web_facts=False))
    assert service.web_facts.for_study(_work(service)) == []
    service.ai_config.update(AiConfigUpdate(web_facts=True))
    photo = service.library.upsert(
        Item(id="upload:1", source="upload", source_id="1", kind=ItemKind.PHOTO)
    )
    assert service.web_facts.for_study(photo) == []
    assert fake.asked == []


def test_an_answer_without_facts_is_not_asked_again_at_once(
    service: FrameService, fake: FakeClaude
) -> None:
    item = _work(service)
    fake.replies = [_message("Nie umiem.")]
    assert service.web_facts.for_study(item) == []
    assert service.web_facts.for_study(item) == []
    assert len(fake.asked) == 1


def test_the_page_question_weaves_the_facts_in(service: FrameService, fake: FakeClaude) -> None:
    item = _work(service)
    text = request_text(item, Context(day=date(2026, 11, 13), web=("Ściany były fioletowe.",)))
    assert "Z SIECI" in text and "- Ściany były fioletowe." in text
    assert "Z SIECI" not in request_text(item, Context(day=date(2026, 11, 13)))
    assert service.daily.job.web_facts == service.web_facts.for_study
    assert service.study.job.web_facts == service.web_facts.for_study
