"""How a work was painted, stage by stage (frame_server.stages, Mateusz
2026-11-13, "G2"): drawn only from a published technical study the facts
from the web found, the last stage the work itself."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from PIL import Image

from frame_server import stages as stages_module
from frame_server.ai import AiConfigUpdate
from frame_server.ai.web_facts import KIND as FACTS
from frame_server.ai.web_facts import VERSION as FACTS_VERSION
from frame_server.ai.web_facts import Fact, Found, Stage, Technical
from frame_server.library import Item
from frame_server.library.models import ItemKind, Note
from frame_server.service import FrameService
from frame_server.stages import KIND, PaintingStages


class FakePainter:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def enabled(self) -> bool:
        return True

    def paint(
        self, kind: str, prompt: str, pictures: Sequence[Image.Image], size: str = "1K", **kw: Any
    ) -> tuple[Image.Image, float]:
        assert kind == KIND and len(pictures) == 1
        self.asked.append(prompt)
        return Image.new("RGB", (1024, 1024), (200, 180, 150)), 0.04


@pytest.fixture
def made(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> tuple[PaintingStages, FakePainter]:
    painter = FakePainter()
    service.stages.painter = painter  # type: ignore[assignment]
    monkeypatch.setattr(
        stages_module, "picture", lambda images, item, side: Image.new("RGB", (300, 240))
    )
    return service.stages, painter


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


def test_each_stage_but_the_last_is_drawn_from_the_study(
    service: FrameService, made: tuple[PaintingStages, FakePainter]
) -> None:
    stages, painter = made
    item = _work(service, study=True)
    assert stages.draw(item)
    assert len(painter.asked) == 2
    assert '"Rysunek"' in painter.asked[0] and "1. Rysunek: Czarny rysunek" in painter.asked[0]
    kept = stages.stages(item)
    assert kept is not None and [s.drawn for s in kept.stages] == [True, True, False]
    path = stages.part(item, 0)
    assert path is not None and Image.open(path).size == (300, 240)  # the work's own shape
    assert stages.part(item, 2) is None  # the work itself
    assert not stages.draw(item)  # drawn once


def test_nothing_is_drawn_without_a_technical_study(
    service: FrameService, made: tuple[PaintingStages, FakePainter]
) -> None:
    stages, painter = made
    item = _work(service, study=False)
    assert stages.wanted(item) is None and not stages.draw_soon(item)
    service.ai_config.update(AiConfigUpdate(stages=False))
    assert not stages.enabled()
    assert painter.asked == []


def test_the_api_serves_the_stages(
    service: FrameService, made: tuple[PaintingStages, FakePainter]
) -> None:
    from fastapi.testclient import TestClient

    from frame_server.web import create_app

    stages, _painter = made
    item = _work(service, study=True)
    assert stages.draw(item) and stages.part(item, 1) is not None
    app = create_app(service.settings)
    app.state.service = service
    client = TestClient(app)  # (no start-up: it looks the work's museum up again)
    url = "/api/stages/picture"
    got = client.get(url, params={"item": item.id, "n": 1})
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert client.get(url, params={"item": item.id, "n": 2}).status_code == 404
