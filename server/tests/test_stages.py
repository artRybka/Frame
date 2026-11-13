"""How a work was painted, told in its study ("Jak powstawał",
frame_server.stages; Mateusz 2026-11-13, "G2", and 21:42: "rezygnujemy z
rysowania tego przez Gemini… sposób powstawania dzieła tylko opisujemy w
2,3 maks 4 zdaniach… Nie dodajemy przypisu opisującego genezę"): only from
a published technical study the facts from the web found."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from frame_server.ai import AiConfigUpdate
from frame_server.ai.web_facts import KIND as FACTS
from frame_server.ai.web_facts import VERSION as FACTS_VERSION
from frame_server.ai.web_facts import Fact, Found, Stage, Technical
from frame_server.library import Item
from frame_server.library.models import ItemKind, Note
from frame_server.service import FrameService
from frame_server.stages import KIND, MODEL, PaintingStages

TEXT = (
    "Van Gogh zaczął od czarnego rysunku na jasnym podkładzie. Potem położył płaskie plamy "
    "barwy, a na końcu obwiódł kształty konturem i dodał grubą farbę."
)


class FakeClaude:
    def __init__(self) -> None:
        self.asked: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **params: Any) -> SimpleNamespace:
        self.asked.append(params)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps({"text": TEXT}))],
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=600,
                output_tokens=200,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


@pytest.fixture
def made(service: FrameService) -> tuple[PaintingStages, FakeClaude]:
    client = FakeClaude()
    service.claude.factory = lambda key: client
    service.ai_config.set_key("sk-ant-test")
    return service.stages, client


def _work(service: FrameService, *, study: bool) -> Item:
    item = service.library.upsert(
        Item(
            id="aic:28560",
            source="aic",
            source_id="28560",
            title="The Bedroom",
            artist="Vincent van Gogh",
            date_text="1889",
            kind=ItemKind.ARTWORK,
        )
    )
    technical = Technical(
        found=study,
        what="Badanie muzeum: RTG",
        stages=[
            Stage(stage="Rysunek", text="Czarny rysunek na podkładzie."),
            Stage(stage="Podmalówka", text="Płaskie plamy barwy."),
            Stage(stage="Wykończenie", text="Kontury i impast."),
        ]
        if study
        else [],
    )
    found = Found(facts=[Fact(text="Ściany były fioletowe.")], technical=technical)
    hashed = service.web_facts.source_hash(item)
    service.library.save_note(
        Note(
            item_id=item.id,
            kind=FACTS,
            model="m",
            prompt_version=FACTS_VERSION,
            source_hash=hashed,
            data=found.model_dump(),
        )
    )
    return item


def test_the_stages_are_told_in_a_few_sentences(
    service: FrameService, made: tuple[PaintingStages, FakeClaude]
) -> None:
    stages, client = made
    item = _work(service, study=True)
    assert stages.write(item)
    params = client.asked[0]
    assert params["model"] == MODEL
    asked = params["messages"][0]["content"][0]["text"]
    assert "1. Rysunek: Czarny rysunek" in asked and "3. Wykończenie" in asked
    assert "Badanie: Badanie muzeum: RTG" in asked  # the study may be named
    system = params["system"][0]["text"]
    assert "najwyżej czterech" in system and "znaleziono w sieci" in system
    assert stages.made(item) == TEXT
    assert not stages.write(item)  # written once
    assert len(client.asked) == 1


def test_nothing_is_told_without_a_technical_study(
    service: FrameService, made: tuple[PaintingStages, FakeClaude]
) -> None:
    stages, client = made
    item = _work(service, study=False)
    assert stages.wanted(item) is None and not stages.write_soon(item)
    assert stages.made(item) is None
    with_study = _work(service, study=True)
    service.ai_config.update(AiConfigUpdate(stages=False))
    assert not stages.enabled() and not stages.write_soon(with_study)
    assert client.asked == []


def test_the_pictures_drawn_before_are_given_up(
    service: FrameService, made: tuple[PaintingStages, FakeClaude]
) -> None:
    stages, _client = made
    item = _work(service, study=True)
    service.library.save_note(
        Note(
            item_id=item.id,
            kind=KIND,
            model="gemini",
            prompt_version="stages-1",
            data={"what": "x", "stages": [{"title": "Rysunek", "text": "…", "drawn": True}]},
        )
    )
    assert stages.made(item) is None and stages.wanted(item) is not None  # told anew
