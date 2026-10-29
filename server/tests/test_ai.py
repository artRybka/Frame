"""The language model's jobs: keywords from thumbnails, costs, batches, the API."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.ai import AiConfigUpdate, AiUnavailable
from frame_server.ai.client import BATCH_DISCOUNT, HAIKU, cost
from frame_server.ai.keywords import KIND, words_and_terms
from frame_server.config import Settings
from frame_server.library import Item, ItemKind, PhotoInfo, PlaylistRules
from frame_server.service import FrameService
from frame_server.web import create_app

GOOD_KEY = "sk-ant-test-0000abcd"
ANSWER = {
    "subjects": ["subject:sea", "subject:ships", "not-a-subject"],
    "tags_en": ["Sailing boat", "harbour", "fishermen", "harbour"],
    "tags_pl": ["żaglowiec", "port", "rybacy"],
    "season": "winter",
    "time_of_day": "unknown",
    "people": "few",
    "mood_pl": ["spokój"],
}


def _message(data: dict[str, Any] | None, stop: str = "end_turn") -> SimpleNamespace:
    text = "" if data is None else json.dumps(data, ensure_ascii=False)
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        usage=SimpleNamespace(
            input_tokens=600,
            output_tokens=400,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=2000,
        ),
    )


def _auth_error() -> anthropic.AuthenticationError:
    request = httpx2.Request("GET", "https://api.anthropic.com/v1/models")
    response = httpx2.Response(401, request=request)
    return anthropic.AuthenticationError("invalid x-api-key", response=response, body=None)


class FakeAnthropic:
    """What the server uses of anthropic.Anthropic, answering ANSWER."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.asked: list[dict[str, Any]] = []
        self.answer: dict[str, Any] | None = ANSWER
        self.stop = "end_turn"
        self.batches: dict[str, list[dict[str, Any]]] = {}
        self.ended = False
        self.messages = SimpleNamespace(
            create=self._create,
            batches=SimpleNamespace(
                create=self._create_batch, retrieve=self._retrieve, results=self._results
            ),
        )
        self.models = SimpleNamespace(retrieve=self._model)

    def _model(self, model: str) -> SimpleNamespace:
        if self.key != GOOD_KEY:
            raise _auth_error()
        return SimpleNamespace(id=model)

    def _create(self, **params: Any) -> SimpleNamespace:
        self.asked.append(params)
        return _message(self.answer, self.stop)

    def _create_batch(self, requests: list[dict[str, Any]]) -> SimpleNamespace:
        batch_id = f"batch_{len(self.batches) + 1}"
        self.batches[batch_id] = requests
        return SimpleNamespace(id=batch_id)

    def _retrieve(self, batch_id: str) -> SimpleNamespace:
        n = len(self.batches[batch_id])
        counts = SimpleNamespace(
            succeeded=n if self.ended else 0, errored=0, canceled=0, expired=0, processing=0
        )
        return SimpleNamespace(
            processing_status="ended" if self.ended else "in_progress", request_counts=counts
        )

    def _results(self, batch_id: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(type="succeeded", message=_message(ANSWER)),
            )
            for r in self.batches[batch_id]
        ]


@pytest.fixture
def fake(service: FrameService) -> FakeAnthropic:
    """The service talks to a fake Anthropic with a key saved in the app."""
    clients: dict[str, FakeAnthropic] = {}

    def factory(key: str) -> FakeAnthropic:
        return clients.setdefault(key, FakeAnthropic(key))

    service.claude.factory = factory
    service.ai_config.set_key(GOOD_KEY)
    service.ai_config.update(AiConfigUpdate(pl_text=False))  # tested in test_polish.py
    return factory(GOOD_KEY)


def _add(service: FrameService, item_id: str, **kw: Any) -> Item:
    kw.setdefault("kind", ItemKind.ARTWORK)
    item = service.library.upsert(
        Item(id=item_id, source=item_id.split(":")[0], source_id=item_id, **kw)
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg_bytes((90, 120, 200), (640, 480)))
    return item


def test_keywords_from_the_thumbnail_go_onto_the_item(
    service: FrameService, fake: FakeAnthropic
) -> None:
    _add(service, "met:1", title="Fishing boats", description="Boats in a harbour.")
    note = service.ai.run_one(KIND, "met:1")

    assert note is not None and note.model == HAIKU
    params = fake.asked[0]
    assert params["model"] == HAIKU
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["output_config"]["format"]["type"] == "json_schema"
    content = params["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert "Title: Fishing boats" in content[1]["text"]

    item = service.library.get("met:1")
    assert item is not None
    assert item.keywords[:3] == ["sailing boat", "harbour", "fishermen"]
    assert {"żaglowiec", "spokój", "zima", "morze"} <= set(item.keywords)
    assert item.terms == ["subject:sea", "subject:ships", "subject:winter"]
    # Found by smart playlists' terms and by a Polish search.
    lib = service.library
    assert [i.id for i in lib.query(PlaylistRules(terms=["subject:winter"]))[1]] == ["met:1"]
    assert [i.id for i in lib.query(PlaylistRules(query="żaglowiec"))[1]] == ["met:1"]
    assert service.claude.spending.by_kind()[KIND] > 0


def test_a_note_is_asked_again_only_when_the_text_changes(
    service: FrameService, fake: FakeAnthropic
) -> None:
    _add(service, "met:1", title="Boats")
    service.ai.run_one(KIND, "met:1")
    service.ai.run_one(KIND, "met:1")
    assert len(fake.asked) == 1
    service.library.update("met:1", title="Boats at Étretat")
    service.ai.run_one(KIND, "met:1")
    assert len(fake.asked) == 2


def test_a_refusal_is_kept_and_not_asked_again(service: FrameService, fake: FakeAnthropic) -> None:
    _add(service, "met:1")
    fake.answer, fake.stop = None, "refusal"
    note = service.ai.run_one(KIND, "met:1")
    assert note is not None and note.data == {"refused": True}
    assert service.library.get("met:1").keywords == []  # type: ignore[union-attr]
    service.ai.run_one(KIND, "met:1")
    assert len(fake.asked) == 1
    assert service.ai.progress(KIND).refused == 1


def test_nothing_is_asked_without_a_key_or_over_the_limit(
    service: FrameService, fake: FakeAnthropic
) -> None:
    _add(service, "met:1")
    service.ai_config.set_key(None)
    assert service.ai.need_now("met:1", KIND).result(timeout=1) is None
    assert service.ai.run_one(KIND, "met:1") is None

    service.ai_config.set_key(GOOD_KEY)
    service.ai_config.update(AiConfigUpdate(monthly_limit_usd=0))
    with pytest.raises(AiUnavailable):
        service.ai.run_one(KIND, "met:1")
    assert fake.asked == []


def test_the_background_asks_about_the_owners_items(
    service: FrameService, fake: FakeAnthropic
) -> None:
    _add(service, "met:kept")
    _add(service, "met:pooled", pooled=True)
    _add(service, "met:shown", pooled=True, show_count=1)
    _add(service, "icloud:1", kind=ItemKind.PHOTO, photo=PhotoInfo(caption="Zakopane"))
    assert service.ai.progress(KIND).waiting == 3
    assert service.ai.sweep() == 3
    while not service.ai._queue.empty():
        service.ai._do(service.ai._queue.get())
    asked = {p["messages"][0]["content"][1]["text"].splitlines()[0] for p in fake.asked}
    assert asked == {"Kind: artwork", "Kind: photo"}
    assert len(fake.asked) == 3
    assert service.ai.progress(KIND).waiting == 0

    service.ai_config.update(AiConfigUpdate(keywords_photos=False))
    _add(service, "icloud:2", kind=ItemKind.PHOTO)
    assert service.ai.sweep() == 0


def test_the_whole_library_through_a_batch(service: FrameService, fake: FakeAnthropic) -> None:
    _add(service, "met:1")
    _add(service, "met:2", pooled=True)  # in the library, but not in the background
    items, usd = service.ai.estimate(KIND)
    assert items == 2 and 0 < usd < 0.01
    assert service.ai.describe_library(KIND) == 2
    service.ai.tick()
    (requests,) = fake.batches.values()
    assert len(requests) == 2 and service.ai.progress(KIND).batch_items == 2
    assert service.ai.sweep() == 0  # already in a batch

    fake.ended = True
    assert service.ai.poll_batches() == 2
    assert service.library.get("met:2").terms  # type: ignore[union-attr]
    assert service.ai.progress(KIND).batch_items == 0
    one = (600 * 0.10 + 2000 * 0.01 + 400 * 0.50) / 1_000_000
    assert service.claude.spending.total() == pytest.approx(2 * one * BATCH_DISCOUNT, rel=1e-3)


def test_a_reimported_item_keeps_its_keywords(service: FrameService) -> None:
    item = _add(service, "met:1")
    service.library.update("met:1", keywords=["boat"], terms=["subject:ships"])
    service.library.upsert(item.model_copy(update={"title": "New title"}))
    kept = service.library.get("met:1")
    assert kept is not None and kept.keywords == ["boat"] and kept.terms == ["subject:ships"]


def test_answers_become_words_and_terms() -> None:
    words, terms = words_and_terms({"subjects": ["subject:sea"], "time_of_day": "night"})
    assert terms == ["subject:sea", "subject:night"]
    assert {"night", "noc"} <= set(words)
    assert len(words) == len(set(words))


def test_the_app_sets_the_key_and_never_gets_it_back(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    svc.claude.factory = FakeAnthropic
    with TestClient(app) as client:
        view = client.get("/api/ai").json()
        assert view["key_set"] is False and view["keywords_progress"]["done"] == 0

        assert client.put("/api/ai/key", json={"key": "sk-ant-wrong"}).status_code == 400
        assert client.get("/api/ai").json()["key_set"] is False

        resp = client.put("/api/ai/key", json={"key": f" {GOOD_KEY} "})
        assert resp.status_code == 200
        assert GOOD_KEY not in resp.text
        assert resp.json()["key_tail"] == "abcd" and resp.json()["key_from_app"] is True

        resp = client.put("/api/ai", json={"keywords_photos": False, "monthly_limit_usd": 2})
        assert resp.json()["keywords_photos"] is False
        assert resp.json()["keywords_artworks"] is True
        assert resp.json()["monthly_limit_usd"] == 2

        assert client.get("/api/ai/keywords/estimate").json() == {"items": 0, "usd": 0.0}
        assert client.delete("/api/ai/key").json()["key_set"] is False
        assert client.post("/api/ai/keywords/describe-library").status_code == 409


def test_frame_env_key_is_the_fallback(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            seed_library=False,
            scheduler=False,
            public_host="127.0.0.1",
            anthropic_api_key="sk-ant-env-key-wxyz",
        )
    )
    with TestClient(app) as client:
        view = client.get("/api/ai").json()
        assert view["key_set"] is True and view["key_from_app"] is False
        assert view["key_tail"] == "wxyz"


def test_a_dated_model_id_costs_as_its_model() -> None:
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0)
    assert cost(f"{HAIKU}-20261015", usage) == pytest.approx(0.10)
    assert cost("claude-unknown", usage) == pytest.approx(2.00)


def test_opening_a_card_asks_out_of_turn(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    svc.claude.factory = FakeAnthropic
    with TestClient(app) as client:
        _add(svc, "icloud:1", kind=ItemKind.PHOTO, photo=PhotoInfo(caption="Port"))
        url = "/api/library/items/icloud:1/describe"
        assert client.post(url).json() == {"status": "off", "words": []}

        svc.ai_config.set_key(GOOD_KEY)
        svc.ai.start()
        try:
            view = client.post(f"{url}?wait=10").json()
        finally:
            svc.ai.stop()
        assert view == {"status": "ready", "words": ["żaglowiec", "port", "rybacy", "spokój"]}
        item = svc.library.get("icloud:1")
        assert item is not None and "subject:sea" in item.terms


def test_what_the_app_needs_now_never_waits_for_the_background(
    service: FrameService, fake: FakeAnthropic
) -> None:
    _add(service, "met:1", title="Fishing boats")
    _add(service, "met:2", title="Harbour")
    release = threading.Event()
    calls = 0
    create = fake.messages.create

    def slow_first(**params: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 1:  # the background's question takes its time
            release.wait(10)
        return create(**params)

    fake.messages.create = slow_first
    assert service.ai.sweep() == 2
    service.ai.start()
    try:
        while calls == 0:
            time.sleep(0.01)
        note = service.ai.need_now("met:2", KIND).result(timeout=5)
        assert note is not None and note.item_id == "met:2"
    finally:
        release.set()
        service.ai.stop()
