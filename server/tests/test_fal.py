"""The creative restorer drawn by SeedVR2 on fal.ai (``frame_server.ai.fal``,
Mateusz 2026-11-22): from a work's card at once, the favourites through
fal's queue, the works Google refused drawn too, Google's model the spare;
fal's queue spoken to as fal speaks."""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_restorer import SMALL, FakePainter, _small
from test_sharper import OWN, OWN_THUMB, Web, _jpeg, _print, _serve

from frame_server.ai import fal
from frame_server.ai.client import Spending
from frame_server.config import Settings
from frame_server.library.viewer import OWNER_ID
from frame_server.service import FrameService
from frame_server.web.app import create_app

FAL_KEY = "fal-id:fal-secret-abcd"


class FakeUpscaler:
    """fal's SeedVR2: the picture as large as asked, after one look."""

    def __init__(self) -> None:
        self.key = True
        self.sent: list[tuple[tuple[int, int], int]] = []
        self.pictures: dict[str, Image.Image] = {}
        self.ready: set[str] = set()
        self.fail = False

    def enabled(self) -> bool:
        return self.key

    def submit(self, picture: Image.Image, longest: int) -> fal.Asked:
        self.sent.append((picture.size, longest))
        name = f"req-{len(self.sent)}"
        times = fal.factor(picture.size, longest)
        w, h = picture.size
        self.pictures[name] = picture.resize((round(w * times), round(h * times)))
        return fal.Asked(name, times)

    def state(self, request_id: str) -> str:
        return "COMPLETED" if request_id in self.ready else "IN_PROGRESS"

    def result(self, kind: str, request_id: str) -> tuple[Image.Image, float]:
        if self.fail:
            raise fal.NotUpscaled("no picture")
        img = self.pictures[request_id]
        return img, fal.cost(img.size)

    def upscale(self, kind: str, picture: Image.Image, longest: int) -> tuple[Image.Image, float]:
        asked = self.submit(picture, longest)
        self.ready.add(asked.request_id)
        return self.result(kind, asked.request_id)


@pytest.fixture
def app(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, FrameService, FakePainter, FakeUpscaler]]:
    created = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    service: FrameService = created.state.service
    with TestClient(created) as client:
        web: Web = {OWN: _jpeg(_print(1, SMALL), 90), OWN_THUMB: _jpeg(_print(1, (600, 400)))}
        _serve(service, web)
        service.sharper.commons_file = lambda item: ""
        painter = FakePainter()
        upscaler = FakeUpscaler()
        service.restorer.painter = painter  # type: ignore[assignment]
        service.restorer.upscaler = upscaler  # type: ignore[assignment]
        yield client, service, painter, upscaler


def test_a_work_from_its_card_is_drawn_by_seedvr2(app: Any) -> None:
    client, service, painter, upscaler = app
    own = _small(service, favorite=True)
    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    copy = resp.json()["sharper"]
    assert copy["restored"] and copy["museum"] == "Kreatywny restaurator"
    # 900 px drawn to some 2048: no Google asked.
    assert upscaler.sent == [(SMALL, 2048)] and painter.asked == []
    assert max(copy["width"], copy["height"]) == 2048
    note = service.library.note(own.id, "restorer")
    assert note is not None and note.model == fal.MODEL and note.data["status"] == "done"


def test_google_is_the_spare_when_fal_gives_nothing(app: Any) -> None:
    client, service, painter, upscaler = app
    own = _small(service)
    upscaler.fail = True
    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    assert painter.asked == [("restorer", "2K")]


def test_the_favourites_through_fals_queue(app: Any) -> None:
    client, service, painter, upscaler = app
    own = _small(service)
    service.library.set_favorite(OWNER_ID, own.id, True)
    view = client.get("/api/ai/restorer").json()
    assert view["by_fal"] and view["items"] == 1 and view["usd"] == fal.TYPICAL_USD
    view = client.post("/api/ai/restorer/favourites").json()
    assert view["waiting"] == 1 and view["items"] == 0 and painter.batches == {}
    assert service.restorer.poll() == 0  # still drawn
    upscaler.ready.add("req-1")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.restored
    assert client.get("/api/ai/restorer").json()["waiting"] == 0


def test_works_google_refused_are_drawn_by_seedvr2(app: Any) -> None:
    client, service, painter, upscaler = app
    own = _small(service, favorite=True)
    upscaler.key = False
    painter.refuse.add(SMALL)
    assert client.post(f"/api/library/items/{own.id}/restore").status_code == 422
    assert service.restorer.candidates() == []
    upscaler.key = True
    assert [i.id for i in service.restorer.candidates()] == [own.id]


def test_the_key_is_kept_from_konfiguracja_and_never_sent_back(app: Any) -> None:
    client, service, _painter, _upscaler = app
    service.upscaler.check_key = lambda key: None  # type: ignore[method-assign]
    view = client.put("/api/ai/fal-key", json={"key": f" {FAL_KEY} "}).json()
    assert view["fal_key_set"] and view["fal_key_tail"] == "abcd"
    assert FAL_KEY not in json.dumps(view)
    assert service.ai_config.fal_key == FAL_KEY

    def rejects(key: str) -> None:
        raise fal.FalRejected("fal.ai did not accept the key")

    service.upscaler.check_key = rejects  # type: ignore[method-assign]
    assert client.put("/api/ai/fal-key", json={"key": "bad"}).status_code == 400
    assert client.put("/api/ai/fal-key", json={"key": " "}).status_code == 400
    assert client.delete("/api/ai/fal-key").json()["fal_key_set"] is False


class Store:
    def __init__(self, key: str | None) -> None:
        self.fal_key = key


def _png(size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 90, 60)).save(buf, "PNG")
    return buf.getvalue()


def test_fals_queue_is_spoken_to_as_fal_speaks(tmp_path: Path) -> None:
    seen: list[tuple[str, str, Any]] = []
    looks = {"n": 0}

    def answer(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization")
        url = str(request.url)
        seen.append((request.method, url, auth))
        if url.endswith("/fal-ai/seedvr/upscale/image"):
            body = json.loads(request.content)
            assert body["upscale_mode"] == "factor" and body["upscale_factor"] == 2.048
            assert body["enable_safety_checker"] is False
            assert body["image_url"].startswith("data:image/png;base64,")
            return httpx.Response(200, json={"request_id": "r1"})
        if url.endswith("/fal-ai/seedvr/requests/r1/status"):
            looks["n"] += 1
            status = "COMPLETED" if looks["n"] > 1 else "IN_QUEUE"
            return httpx.Response(200, json={"status": status})
        if url.endswith("/fal-ai/seedvr/requests/r1"):
            data = "data:image/png;base64," + base64.b64encode(_png((2048, 1365))).decode()
            return httpx.Response(200, json={"image": {"url": data}, "seed": 1})
        if "/requests/" in url:  # the key's check
            if auth != f"Key {FAL_KEY}":
                return httpx.Response(401)
            return httpx.Response(404)
        raise AssertionError(url)

    added: list[tuple[str, float]] = []

    class Spent(Spending):
        def __init__(self) -> None:
            pass

        def add(self, kind: str, usd: float) -> None:  # type: ignore[override]
            added.append((kind, usd))

    up = fal.Upscaler(
        Store(FAL_KEY),  # type: ignore[arg-type]
        Spent(),
        lambda: 5.0,
        http=lambda: httpx.Client(transport=httpx.MockTransport(answer)),
        sleep=lambda s: None,
    )
    img, usd = up.upscale("restorer", Image.new("RGB", (1000, 667)), 2048)
    assert img.size == (2048, 1365) and usd == pytest.approx(2048 * 1365 / 1e6 * 0.001)
    assert added == [("restorer", usd)]
    assert all(auth == f"Key {FAL_KEY}" for _m, _u, auth in seen)
    up.check_key(FAL_KEY)
    with pytest.raises(fal.FalRejected):
        up.check_key("wrong")
    # No money left this month: nothing sent.
    up.budget_left = lambda: 0.0
    with pytest.raises(fal.AiUnavailable):
        up.submit(Image.new("RGB", (100, 100)), 2048)


def test_factor() -> None:
    assert fal.factor((900, 600), 2048) == 2.276
    assert fal.factor((300, 200), 2048) == fal.MOST
    assert fal.factor((1900, 1000), 2048) == fal.LEAST
