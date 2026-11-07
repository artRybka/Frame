"""The museum's labels on a work's card, in Polish, without repeating the
model's keywords."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_ai import GOOD_KEY, FakeAnthropic, _add

from frame_server.ai import AiConfigUpdate
from frame_server.ai.museum_words import KIND, MuseumWords, leftovers, museum_labels, repeats
from frame_server.config import Settings
from frame_server.library import Item
from frame_server.service import FrameService
from frame_server.web import create_app

LABELS = {
    "labels": [
        {"en": "18th Century", "pl": "XVIII wiek"},
        {"en": "boys", "pl": "chłopiec"},
        {"en": "youth", "pl": "młodość"},
        {"en": "portraits: male subject", "pl": "portret męski"},
        {"en": "portraits", "pl": "portret"},
        {"en": "pilgrimages", "pl": "pielgrzymka"},
        {"en": "hat", "pl": "kapelusz"},
    ]
}


@pytest.fixture
def fake(service: FrameService) -> FakeAnthropic:
    clients: dict[str, FakeAnthropic] = {}

    def factory(key: str) -> FakeAnthropic:
        return clients.setdefault(key, FakeAnthropic(key))

    service.claude.factory = factory
    service.ai_config.set_key(GOOD_KEY)
    client = factory(GOOD_KEY)
    client.answer = LABELS
    return client


def _pilgrim() -> Item:
    return Item(
        id="aic:1",
        source="aic",
        source_id="1",
        title="Portrait of Giacomo",
        classification="Painting",
        culture="Italy",
        styles=["18th Century"],
        subjects=["boys", "youth", "portraits: male subject", "portraits", "pilgrimages", "hat"],
    )


def test_a_tag_that_repeats_a_keyword_is_left_out() -> None:
    words = ["chłopiec", "pielgrzym", "szeroki kapelusz", "Włochy"]
    assert repeats("chłopiec", words)
    assert repeats("kapelusz", words)  # one word of a phrase
    assert repeats("pielgrzymka", words)  # another ending
    assert not repeats("młodość", words)
    assert not repeats("pies", ["piesek"])  # short words must be equal
    tags = ["XVIII wiek", "chłopiec", "młodość", "portret męski", "portret", "kapelusz", "młodość"]
    assert leftovers(tags, words) == ["XVIII wiek", "młodość", "portret męski"]
    # A shorter tag before a fuller one goes too.
    assert leftovers(["portret", "portret męski"], []) == ["portret męski"]


def test_common_kinds_and_places_need_no_model(service: FrameService) -> None:
    words = service.museum_words
    assert words.known("Painting") == "obraz"
    assert words.known(" italy ") == "Włochy"
    assert words.known("Dutch") == "Holandia"
    assert words.known("pilgrimages") is None
    # Without a key nothing is asked: the labels stay as the museum wrote them.
    found, pending = words.polish(["Painting", "pilgrimages"], wait=1)
    assert found == {"Painting": "obraz", "pilgrimages": "pilgrimages"}
    assert not pending


def test_the_model_translates_each_label_once(service: FrameService, fake: FakeAnthropic) -> None:
    labels = museum_labels(_pilgrim())
    assert labels.kind == "Painting" and labels.culture == "Italy"
    found, pending = service.museum_words.polish(labels.all, wait=5)
    assert not pending
    assert found["pilgrimages"] == "pielgrzymka" and found["Italy"] == "Włochy"
    assert len(fake.asked) == 1
    asked = str(fake.asked[0]["messages"])
    assert "pilgrimages" in asked and "Painting" not in asked  # the table knows it
    # Remembered, also after a restart.
    again = MuseumWords(service.library, service.claude, service.ai_config)
    assert again.known("Pilgrimages") == "pielgrzymka"
    assert again.ask(labels.all) == []
    assert len(fake.asked) == 1
    assert service.claude.spending.by_kind().get(KIND, 0) > 0


def test_the_polish_texts_switch_stops_the_questions(
    service: FrameService, fake: FakeAnthropic
) -> None:
    service.ai_config.update(AiConfigUpdate(pl_text=False))
    assert service.museum_words.ask(["pilgrimages"]) == []
    assert fake.asked == []


def test_the_card_gets_the_labels_in_polish(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        item = _pilgrim()
        _add(svc, item.id, **item.model_dump(exclude={"id", "source", "source_id"}))
        url = f"/api/library/items/{item.id}/describe"
        # No key: the table's words, the rest as the museum wrote them.
        view = client.post(url).json()
        assert view["classification"] == "obraz" and view["culture"] == "Włochy"
        assert view["tags"] == [
            "18th Century",
            "boys",
            "youth",
            "portraits: male subject",
            "pilgrimages",
            "hat",
        ]

        clients: dict[str, FakeAnthropic] = {}

        def factory(key: str) -> FakeAnthropic:
            client = clients.setdefault(key, FakeAnthropic(key))
            client.answer = LABELS
            return client

        svc.claude.factory = factory
        svc.ai_config.set_key(GOOD_KEY)
        svc.ai_config.update(AiConfigUpdate(keywords_artworks=False))
        view = client.post(f"{url}?wait=10").json()
        assert view["status"] == "off"
        assert view["tags"] == [
            "XVIII wiek",
            "chłopiec",
            "młodość",
            "portret męski",
            "pielgrzymka",
            "kapelusz",
        ]
