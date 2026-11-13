"""Szukaj by how a work looks (frame_server.looks, Mateusz 2026-11-13,
"G1"): the museums' works as Google's numbers, kept on the server; words,
a photograph or a work asked about them."""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.ai import AiConfigUpdate, AiUnavailable
from frame_server.ai.gemini import EMBED_MAX, EMBED_MODEL, EMBED_SIZE, Painter, embed_cost
from frame_server.library.models import Item, ItemKind
from frame_server.looks import KIND, QUERY, LookIndex, Looks
from frame_server.service import FrameService

#: Colours the fake model tells apart, each its own direction.
COLOURS = {"red": (200, 30, 30), "blue": (30, 40, 200), "green": (30, 170, 40)}


def _direction(at: int, lean: int | None = None) -> list[float]:
    vector = [0.0] * EMBED_SIZE
    vector[at] = 1.0
    if lean is not None:
        vector[lean] = 0.25
    return vector


def _colour_of(img: Image.Image) -> int:
    r, g, b = img.convert("RGB").resize((1, 1)).getpixel((0, 0))  # type: ignore[misc]
    return int(np.argmax([r, b, g]))  # red 0, blue 1, green 2


class FakePainter:
    """Google's embedding model: a picture points the way of its colour,
    words the way of the colour they name."""

    def __init__(self) -> None:
        self.asked: list[list[Image.Image | str]] = []
        self.batches: list[list[tuple[str, Image.Image]]] = []
        #: Batches Google is still at.
        self.waiting: set[str] = set()
        self.key = True

    def enabled(self) -> bool:
        return self.key

    def embed_batch(self, kind: str, pictures: Sequence[tuple[str, Image.Image]]) -> str:
        assert kind == KIND and pictures
        self.batches.append(list(pictures))
        return f"batches/{len(self.batches)}"

    def embed_batched(self, kind: str, batch: str) -> dict[str, list[float] | None] | None:
        if batch in self.waiting:
            return None
        pictures = self.batches[int(batch.split("/")[1]) - 1]
        return {name: _direction(_colour_of(img), lean=10) for name, img in pictures}

    def embed(self, kind: str, inputs: Sequence[Image.Image | str]) -> list[list[float]]:
        assert kind == KIND and 0 < len(inputs) <= EMBED_MAX
        self.asked.append(list(inputs))
        found = []
        for one in inputs:
            if isinstance(one, str):
                assert one.startswith(QUERY)
                words = one.removeprefix(QUERY)
                at = next((n for n, name in enumerate(COLOURS) if name in words), 5)
                found.append(_direction(at))
            else:
                found.append(_direction(_colour_of(one), lean=10))
        return found


def _work(service: FrameService, item_id: str, colour: str, **fields: Any) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("kind", ItemKind.ARTWORK)
    item = Item(
        id=item_id,
        source=source,
        source_id=source_id,
        title=item_id,
        thumb_url=f"https://example.org/{source_id}.jpg",
        **fields,
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), COLOURS[colour]).save(path, "JPEG")
    return service.library.upsert(item)


def _numbers(found: Looks) -> int:
    """The works sent through the Batch and their numbers read back: how
    many got them."""
    found.send()
    return found.collect()


@pytest.fixture
def looks(service: FrameService) -> tuple[Looks, FakePainter]:
    painter = FakePainter()
    service.looks.painter = painter  # type: ignore[assignment]
    return service.looks, painter


# -- the numbers kept --------------------------------------------------------------------------


def test_the_numbers_are_kept_and_the_nearest_found(tmp_path: Path) -> None:
    index = LookIndex(tmp_path)
    index.add([("a", 1, _direction(0)), ("b", 1, _direction(1)), ("c", 1, _direction(0, 1))])
    assert [i for i, _ in index.nearest(_direction(0), 2)] == ["a", "c"]
    again = LookIndex(tmp_path)  # read back from the disk
    assert len(again) == 3 and again.stamp("c") == 1
    assert [i for i, _ in again.nearest(_direction(1), 1)] == ["b"]


def test_a_new_picture_and_a_gone_work_leave_their_old_rows(tmp_path: Path) -> None:
    index = LookIndex(tmp_path)
    index.add([(f"w{n}", 1, _direction(n)) for n in range(10)])
    index.add([("w0", 2, _direction(5))])  # its picture changed
    assert index.stamp("w0") == 2
    assert [i for i, _ in index.nearest(_direction(5), 2)] == ["w5", "w0"]
    index.forget(["w1", "w2"])  # dead rows past the share: written anew
    assert len(index) == 8
    again = LookIndex(tmp_path)
    assert len(again) == 8 and "w1" not in again
    assert (tmp_path / "ids.txt").read_text().count("\n") == 8


def test_a_broken_off_write_keeps_the_whole_rows(tmp_path: Path) -> None:
    index = LookIndex(tmp_path)
    index.add([("a", 1, _direction(0)), ("b", 1, _direction(1))])
    with (tmp_path / "vectors.i8").open("ab") as out:
        out.write(b"\x01\x02\x03")
    assert len(LookIndex(tmp_path)) == 2


# -- Google's embedding model --------------------------------------------------------------------


def test_the_embedding_request_and_its_cost(service: FrameService) -> None:
    sent: list[dict[str, Any]] = []

    def google(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/models/{EMBED_MODEL}:batchEmbedContents")
        assert request.headers["x-goog-api-key"] == "k-1"
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(
            200,
            json={
                "embeddings": [{"values": [0.1] * EMBED_SIZE} for _ in body["requests"]],
                "usageMetadata": {
                    "promptTokenCount": 274,
                    "promptTokenDetails": [
                        {"modality": "IMAGE", "tokenCount": 258},
                        {"modality": "TEXT", "tokenCount": 16},
                    ],
                },
            },
        )

    service.ai_config.set_gemini_key("k-1")
    painter = Painter(
        service.ai_config,
        service.claude,
        http=lambda: httpx.Client(transport=httpx.MockTransport(google)),
    )
    found = painter.embed(KIND, [Image.new("RGB", (8, 8)), QUERY + "morze"])
    assert len(found) == 2 and len(found[0]) == EMBED_SIZE
    first, second = sent[0]["requests"]
    assert first["output_dimensionality"] == EMBED_SIZE
    assert first["content"]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"
    assert second["content"]["parts"] == [{"text": QUERY + "morze"}]
    usd = embed_cost({"promptTokenDetails": [{"modality": "IMAGE", "tokenCount": 258}]})
    assert usd == pytest.approx(0.000116, abs=1e-6)
    assert painter.spending.by_kind()[KIND] == pytest.approx(0.00012, abs=2e-6)
    with pytest.raises(ValueError):
        painter.embed(KIND, [])


# -- the background ------------------------------------------------------------------------------


def test_only_the_museums_works_with_a_thumbnail_are_sent(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _work(service, "upload:1", "red", kind=ItemKind.OWN)
    _work(service, "icloud:1", "red", kind=ItemKind.PHOTO)
    gone = Item(id="met:3", source="met", source_id="3", thumb_url="https://example.org/3.jpg")
    service.library.upsert(gone)  # no thumbnail here: not downloaded for this
    assert _numbers(found) == 2
    assert found.index.ids() == {"met:1", "met:2"}
    assert found.counts() == (2, 3)
    assert _numbers(found) == 0  # nothing new
    service.ai_config.update(AiConfigUpdate(looks=False))
    assert not found.enabled() and _numbers(found) == 0


def test_a_changed_picture_of_a_cared_work_is_sent_again(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    item = _work(service, "met:1", "red")
    found.cared = lambda: {"met:1": 0}
    assert _numbers(found) == 1
    thumb = service.images.thumb_path(item)
    Image.new("RGB", (64, 48), COLOURS["blue"]).save(thumb, "JPEG")
    stamp = int(thumb.stat().st_mtime) + 5
    import os

    os.utime(thumb, (stamp, stamp))
    assert _numbers(found) == 1
    assert found.index.stamp("met:1") == stamp


# -- the questions -------------------------------------------------------------------------------


def test_words_find_works_that_look_so(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _work(service, "met:3", "red", excluded=True)  # hidden in the app
    _numbers(found)
    asked = len(painter.asked)
    assert [f.item.id for f in found.words("czerwony red zachód")] == ["met:1"]
    assert [f.item.id for f in found.words("  Czerwony   red zachód ")] == ["met:1"]
    assert len(painter.asked) == asked + 1  # the same words are not asked again
    assert found.words("nic") == []  # far from every work


def test_a_photograph_and_a_work_find_works_that_look_alike(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    red = _work(service, "met:1", "red")
    _work(service, "aic:7", "red")
    _work(service, "met:2", "blue")
    _numbers(found)
    photo = Image.new("RGB", (300, 200), COLOURS["blue"])
    assert [f.item.id for f in found.picture(photo)] == ["met:2"]
    assert [f.item.id for f in found.similar(red)] == ["aic:7"]
    assert found.neighbours("met:1") == ["aic:7"]
    assert found.similar(Item(id="met:9", source="met", source_id="9")) == []


def test_nothing_is_asked_without_a_key_or_numbers(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, painter = looks
    painter.key = False
    with pytest.raises(AiUnavailable):
        found.words("czerwony")
    painter.key = True
    service.ai_config.set_gemini_key("k")
    with pytest.raises(AiUnavailable):  # no work has its numbers yet
        found.words("czerwony")


def test_the_api(service: FrameService, looks: tuple[Looks, FakePainter]) -> None:
    from frame_server.web import create_app

    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _numbers(found)
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        status = client.get("/api/looks").json()
        assert status == {"enabled": True, "ready": True, "done": 2, "total": 2}
        words = client.get("/api/looks/search", params={"q": "niebieski blue"}).json()
        assert [i["id"] for i in words["items"]] == ["met:2"] and words["scores"][0] > 0.9
        out = io.BytesIO()
        Image.new("RGB", (40, 30), COLOURS["red"]).save(out, "JPEG")
        files = {"file": ("photo.jpg", out.getvalue(), "image/jpeg")}
        photo = client.post("/api/looks/picture", files=files).json()
        assert [i["id"] for i in photo["items"]] == ["met:1"]
        bad = {"file": ("photo.jpg", b"not a picture", "image/jpeg")}
        assert client.post("/api/looks/picture", files=bad).status_code == 422
        like = client.get("/api/library/items/met:1/looks").json()
        assert like["items"] == []  # nothing else looks red
        service.ai_config.update(AiConfigUpdate(looks=False))
        assert client.get("/api/looks/search", params={"q": "red"}).status_code == 409
        assert client.get("/api/library/items/met:1/looks").json()["items"] == []
        view = client.get("/api/ai").json()
        assert view["looks"] is False and view["looks_done"] == 2
        assert client.post("/api/terms/sentence", json={"text": "morze"}).status_code in (404, 405)


def test_works_that_look_alike_come_first_among_the_studys_candidates(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    red = _work(service, "met:1", "red", artist="Anna A")
    _work(service, "aic:7", "red", artist="Bruno B")
    _work(service, "aic:8", "red", artist="Anna A")  # the artist's own: "Inne prace artysty"
    _numbers(found)
    assert [i.id for i in service.daily.candidates(red)] == ["aic:7"]


def test_the_works_go_through_the_batch_and_wait_for_it(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    painter.waiting.add("batches/1")
    assert found.round() == (0, 2)
    assert found.send() == 0  # out already: not sent twice
    assert found.collect() == 0 and len(found.index) == 0
    painter.waiting.clear()
    again = Looks(  # a restart keeps the batches out
        service.library,
        service.images,
        painter,
        service.ai_config,
        found.root,  # type: ignore[arg-type]
    )
    assert again.collect() == 2 and again.index.ids() == {"met:1", "met:2"}
    assert painter.asked == []  # nothing asked one by one


def test_the_embedding_batch_request_and_its_answers(service: FrameService) -> None:
    sent: list[dict[str, Any]] = []
    state = {"now": "BATCH_STATE_RUNNING"}

    def google(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path.endswith(f"/models/{EMBED_MODEL}:asyncBatchEmbedContent")
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"name": "batches/b1", "metadata": {}})
        assert request.url.path.endswith("/batches/b1")
        answers = [
            {
                "response": {"embedding": {"values": [0.5] * EMBED_SIZE}},
                "metadata": {"key": "met:1"},
            },
            {"error": {"code": 3, "message": "bad picture"}, "metadata": {"key": "met:2"}},
        ]
        return httpx.Response(
            200,
            json={
                "name": "batches/b1",
                "metadata": {"state": state["now"]},
                "response": {
                    "inlinedResponses": {"inlinedResponses": answers}
                },  # as Google answers
            },
        )

    service.ai_config.set_gemini_key("k-1")
    painter = Painter(
        service.ai_config,
        service.claude,
        http=lambda: httpx.Client(transport=httpx.MockTransport(google)),
    )
    pictures = [("met:1", Image.new("RGB", (8, 8))), ("met:2", Image.new("RGB", (8, 8)))]
    assert painter.embed_batch(KIND, pictures) == "batches/b1"
    request = sent[0]["batch"]["input_config"]["requests"]["requests"][0]
    assert request["metadata"] == {"key": "met:1"}
    assert request["request"]["output_dimensionality"] == EMBED_SIZE
    assert painter.embed_batched(KIND, "batches/b1") is None  # still at it
    state["now"] = "BATCH_STATE_SUCCEEDED"
    found = painter.embed_batched(KIND, "batches/b1")
    assert found is not None and found["met:2"] is None and len(found["met:1"] or []) == EMBED_SIZE
    assert painter.spending.by_kind()[KIND] == pytest.approx(0.000058, abs=1e-6)  # half price
