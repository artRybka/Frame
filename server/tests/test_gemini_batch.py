"""Google's Batch through the one client of the image model (ai.gemini):
questions in the request, answers by their names, the Batch's price."""

from __future__ import annotations

import base64
import io
import json
from typing import Any

import httpx
import pytest
from PIL import Image

from frame_server.ai.client import AiUnavailable
from frame_server.ai.gemini import (
    BATCH_URL,
    BATCHES_URL,
    Ask,
    GeminiRejected,
    NotDrawn,
    Painter,
    _request,
    batch_cost,
)
from frame_server.service import FrameService

KEY = "AIza-test-key-wxyz"
KIND = "restorer"
NAME = "batches/abc123"


def _png(colour: tuple[int, int, int]) -> str:
    out = io.BytesIO()
    Image.new("RGB", (64, 48), colour).save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode()


USAGE = {
    "promptTokenCount": 2000,
    "candidatesTokenCount": 1320,
    "thoughtsTokenCount": 100,
    "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}],
}


class Google:
    """Google's Batch: takes a batch, then says how it goes."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.headers: list[str] = []
        self.state = "BATCH_STATE_PENDING"
        self.status = 200
        self.busy = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.headers.append(request.headers.get("x-goog-api-key", ""))
        if self.busy:
            self.busy -= 1
            return httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}})
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"code": 404, "status": "NOT_FOUND"}})
        if request.method == "POST":
            assert str(request.url) == BATCH_URL
            self.sent.append(json.loads(request.content))
            meta = {"state": "BATCH_STATE_PENDING", "name": NAME}
            return httpx.Response(200, json={"name": NAME, "metadata": meta})
        assert str(request.url) == f"{BATCHES_URL}/{NAME}"
        body: dict[str, Any] = {"name": NAME, "metadata": {"state": self.state}}
        if self.state == "BATCH_STATE_SUCCEEDED":
            answers = [
                {
                    "metadata": {"key": "a/lines"},
                    "response": {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "image/png",
                                                "data": _png((10, 200, 30)),
                                            }
                                        }
                                    ]
                                },
                                "finishReason": "STOP",
                            }
                        ],
                        "usageMetadata": USAGE,
                    },
                },
                {
                    "metadata": {"key": "b/lines"},
                    "response": {"candidates": [{"finishReason": "IMAGE_RECITATION"}]},
                },
                {
                    "metadata": {"key": "c/lines"},
                    "error": {"code": 400, "message": "bad picture", "status": "INVALID_ARGUMENT"},
                },
            ]
            body["done"] = True
            body["response"] = {"inlinedResponses": {"inlinedResponses": answers}}
        return httpx.Response(200, json=body)


@pytest.fixture
def google() -> Google:
    return Google()


@pytest.fixture
def painter(service: FrameService, google: Google, monkeypatch: pytest.MonkeyPatch) -> Painter:
    monkeypatch.setattr("frame_server.ai.gemini.time.sleep", lambda s: None)
    return Painter(
        service.ai_config,
        service.claude,
        http=lambda: httpx.Client(transport=httpx.MockTransport(google)),
    )


def _asks() -> list[Ask]:
    picture = Image.new("RGB", (90, 60), (200, 120, 60))
    return [Ask(f"{n}/lines", "draw", [picture], size="2K") for n in "abc"]


def test_a_batch_is_sent_and_read_once_by_its_names(
    service: FrameService, painter: Painter, google: Google
) -> None:
    with pytest.raises(AiUnavailable):  # no key
        painter.batch(KIND, _asks())
    service.ai_config.set_gemini_key(KEY)

    assert painter.batch(KIND, _asks()) == NAME
    [sent] = google.sent
    requests = sent["batch"]["input_config"]["requests"]["requests"]
    assert [r["metadata"]["key"] for r in requests] == ["a/lines", "b/lines", "c/lines"]
    first = requests[0]["request"]
    assert first["generation_config"]["imageConfig"] == {"imageSize": "2K"}
    assert first["generation_config"]["responseModalities"] == ["IMAGE"]
    parts = first["contents"][0]["parts"]
    assert parts[0] == {"text": "draw"} and parts[1]["inline_data"]["mime_type"] == "image/jpeg"
    assert "thinkingConfig" not in first["generation_config"]  # the model's own default
    assert set(google.headers) == {KEY}
    # Asked not to think first (the sheets, 2026-11-13): checked live on generateContent.
    thought = Ask("x", "draw", [Image.new("RGB", (8, 8))], think="minimal")
    assert _request(thought)["generation_config"]["thinkingConfig"] == {"thinkingLevel": "minimal"}

    assert painter.batched(KIND, NAME) is None  # pending
    google.state = "BATCH_STATE_RUNNING"
    assert painter.batched(KIND, NAME) is None
    google.busy = 3  # Google busy through every try: later
    assert painter.batched(KIND, NAME) is None
    assert service.painter.spending.by_kind() == {}

    google.state = "BATCH_STATE_SUCCEEDED"
    found = painter.batched(KIND, NAME)
    assert found is not None and set(found) == {"a/lines", "b/lines", "c/lines"}
    drawn = found["a/lines"]
    assert not isinstance(drawn, NotDrawn)
    img, usd = drawn
    assert img.size == (64, 48) and img.getpixel((3, 3)) == (10, 200, 30)
    # Half of what the same answer costs at once.
    assert usd == round((2000 * 1.5 + 300 * 7.5 + 1120 * 30) / 2 / 1e6, 4) == batch_cost(USAGE)
    refused, bad = found["b/lines"], found["c/lines"]
    assert isinstance(refused, NotDrawn) and refused.code == "image_recitation"
    assert isinstance(bad, NotDrawn) and bad.code == "INVALID_ARGUMENT"
    assert service.painter.spending.by_kind() == {KIND: usd}


def test_a_lost_batch_and_refusals(service: FrameService, painter: Painter, google: Google) -> None:
    service.ai_config.set_gemini_key(KEY)
    for state in ("BATCH_STATE_EXPIRED", "BATCH_STATE_CANCELLED", "JOB_STATE_FAILED"):
        google.state = state
        with pytest.raises(NotDrawn):
            painter.batched(KIND, NAME)
    google.status = 404
    with pytest.raises(NotDrawn):
        painter.batched(KIND, NAME)
    google.status = 403
    with pytest.raises(GeminiRejected):
        painter.batch(KIND, _asks())
    google.status = 200
    with pytest.raises(ValueError):  # a name twice
        painter.batch(KIND, [*_asks(), _asks()[0]])
    huge = Image.effect_noise((4000, 4000), 120).convert("RGB")
    with pytest.raises(ValueError, match="send fewer"):
        painter.batch(KIND, [Ask(f"{n}", "draw", [huge]) for n in range(4)])
    assert google.sent == []
