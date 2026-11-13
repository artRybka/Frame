"""The creative restorer (frame_server.restorer): a small picture drawn again
larger by the image model, kept as the owner's pick in the work's own id
(Mateusz 2026-11-12)."""

from __future__ import annotations

import io
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_sharper import OWN, OWN_THUMB, Web, _jpeg, _own, _print, _serve

from frame_server.ai.gatekeeper import asked_by_rules
from frame_server.ai.gemini import Ask, NotDrawn
from frame_server.config import Settings
from frame_server.library import Item, low_res
from frame_server.library.models import ItemSummary
from frame_server.library.viewer import OWNER_ID
from frame_server.restorer import NotRestored, fit
from frame_server.service import FrameService
from frame_server.web.app import create_app

SMALL = (900, 600)


class FakePainter:
    """The image model: the picture twice as large, or a refusal."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []
        self.refuse: set[tuple[int, int]] = set()
        self.batches: dict[str, list[Ask]] = {}
        self.done: set[str] = set()

    def enabled(self) -> bool:
        return True

    @staticmethod
    def _draw(picture: Image.Image) -> Image.Image:
        w, h = picture.size
        return picture.resize((w * 2 + 3, h * 2), Image.Resampling.BICUBIC)  # a hair wider

    def paint(
        self, kind: str, prompt: str, pictures: Sequence[Image.Image], size: str = "1K"
    ) -> tuple[Image.Image, float]:
        self.asked.append((kind, size))
        if pictures[0].size in self.refuse:
            raise NotDrawn("Google answered 400", "image_recitation")
        return self._draw(pictures[0]), 0.06

    def batch(self, kind: str, asks: Sequence[Ask]) -> str:
        name = f"batches/{len(self.batches) + 1}"
        self.batches[name] = list(asks)
        return name

    def batched(
        self, kind: str, batch: str
    ) -> dict[str, tuple[Image.Image, float] | NotDrawn] | None:
        if batch not in self.done:
            return None
        found: dict[str, tuple[Image.Image, float] | NotDrawn] = {}
        for ask in self.batches[batch]:
            picture = ask.pictures[0]
            if picture.size in self.refuse:
                found[ask.name] = NotDrawn("no picture", "image_recitation")
            else:
                found[ask.name] = (self._draw(picture), 0.03)
        return found


def _small(service: FrameService, **kw: Any) -> Item:
    own = _own(service, **kw)
    small = service.library.update(own.id, width=SMALL[0], height=SMALL[1])
    assert small is not None
    return small


@pytest.fixture
def app(tmp_path: Path) -> Iterator[tuple[TestClient, FrameService, Web, FakePainter]]:
    created = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    service: FrameService = created.state.service
    with TestClient(created) as client:
        web: Web = {OWN: _jpeg(_print(1, SMALL), 90), OWN_THUMB: _jpeg(_print(1, (600, 400)))}
        _serve(service, web)
        service.sharper.commons_file = lambda item: ""
        painter = FakePainter()
        service.painter = painter  # type: ignore[assignment]
        service.restorer.painter = painter  # type: ignore[assignment]
        yield client, service, web, painter


def test_a_small_picture_drawn_again_stays_the_same_work(app: Any) -> None:
    client, service, _web, painter = app
    own = _small(service, favorite=True)
    assert low_res.low_side(own) == 900

    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert item["id"] == own.id and item["favorite"]
    copy = item["sharper"]
    assert copy["restored"] and copy["chosen"] and copy["source"] == "owned"
    assert copy["museum"] == "Kreatywny restaurator"
    # Twice as large, a hair off its proportions: kept so.
    assert (copy["width"], copy["height"]) == (1803, 1200)
    assert painter.asked == [("restorer", "2K")]

    stored = service.library.get(own.id)
    assert stored is not None
    summary = ItemSummary.of(stored)
    assert summary.restored and summary.low_side == 0
    # The gatekeeper leaves the owner's drawing be.
    assert not asked_by_rules(stored.model_copy(update={"source": "wikiart"}))
    # The night's look for sharper copies leaves it be too.
    view = client.post(f"/api/library/items/{own.id}/sharpen").json()
    assert view["status"] == "found" and view["sharper"]["restored"]
    assert view["low_side"] == 0
    # Back to the museum's picture.
    back = client.delete(f"/api/library/items/{own.id}/copy").json()
    assert back["sharper"] is None
    assert service.restorer.candidates()[0].id == own.id


def test_a_refusal_is_noted_and_not_sent_again(app: Any) -> None:
    client, service, _web, painter = app
    own = _small(service, favorite=True)
    painter.refuse.add(SMALL)

    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 422
    assert resp.json()["detail"].startswith("refused:")
    assert service.library.get(own.id).sharper is None
    assert service.restorer.candidates() == []


def test_a_large_picture_is_not_drawn(app: Any) -> None:
    client, service, web, _painter = app
    web[OWN] = _jpeg(_print(1, (2400, 1600)), 90)
    own = _own(service)
    own = service.library.update(own.id, width=2400, height=1600)
    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 422 and resp.json()["detail"].startswith("large:")


def test_the_favourites_through_the_batch(app: Any) -> None:
    client, service, _web, painter = app
    own = _small(service)
    service.library.set_favorite(OWNER_ID, own.id, True)

    view = client.get("/api/ai/restorer").json()
    assert view == {"enabled": True, "items": 1, "usd": 0.03, "waiting": 0, "restored": 0}
    view = client.post("/api/ai/restorer/favourites").json()
    assert view["items"] == 0 and view["waiting"] == 1
    assert list(painter.batches) == ["batches/1"]
    # Ordered once: not again while it waits.
    assert service.restorer.order_favourites() == 0

    assert service.restorer.poll() == 0  # not done yet
    painter.done.add("batches/1")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.restored
    view = client.get("/api/ai/restorer").json()
    assert view["waiting"] == 0 and view["restored"] == 1 and view["items"] == 0


def test_a_batch_refusal_is_noted(app: Any) -> None:
    _client, service, _web, painter = app
    own = _small(service)
    service.library.set_favorite(OWNER_ID, own.id, True)
    painter.refuse.add(SMALL)
    assert service.restorer.order_favourites() == 1
    painter.done.add("batches/1")
    assert service.restorer.poll() == 0
    assert service.library.get(own.id).sharper is None
    assert service.restorer.candidates() == []
    assert service.restorer.order_favourites() == 0


def test_a_playlists_works_through_the_batch(app: Any) -> None:
    """The playlist's "…" → "Kreatywny restaurator" (Mateusz 2026-11-13):
    its works under the threshold, not only the favourites."""
    client, service, _web, painter = app
    own = _small(service)
    made = client.post(
        "/api/playlists", json={"name": "Małe", "kind": "manual", "item_ids": [own.id]}
    )
    assert made.status_code == 200, made.text
    playlist_id = made.json()["playlist"]["id"]
    # Not a favourite: Konfiguracja's line leaves it out, the playlist's has it.
    assert client.get("/api/ai/restorer").json()["items"] == 0
    view = client.get(f"/api/ai/restorer/playlists/{playlist_id}").json()
    assert view == {"enabled": True, "items": 1, "usd": 0.03, "waiting": 0, "restored": 0}

    view = client.post(f"/api/ai/restorer/playlists/{playlist_id}").json()
    assert view["items"] == 0 and view["waiting"] == 1
    assert [a.name for a in painter.batches["batches/1"]] == [own.id]
    # Ordered once: not again while it waits.
    assert client.post(f"/api/ai/restorer/playlists/{playlist_id}").json()["waiting"] == 1
    assert list(painter.batches) == ["batches/1"]
    painter.done.add("batches/1")
    assert service.restorer.poll() == 1
    view = client.get(f"/api/ai/restorer/playlists/{playlist_id}").json()
    assert view["items"] == 0 and view["restored"] == 1
    assert client.get("/api/ai/restorer/playlists/999").status_code == 404


def test_the_drawing_has_a_thumbnail(app: Any) -> None:
    """The "Szukaj lepszej kopii" sheet shows the picture in the work's place by the
    copy's own id: the restorer's drawing had no thumbnail (Mateusz
    2026-11-13)."""
    client, service, _web, _painter = app
    own = _small(service, favorite=True)
    copy_id = client.post(f"/api/library/items/{own.id}/restore").json()["sharper"]["item_id"]
    assert copy_id.startswith("owned:")
    stored = service.library.get(own.id)
    assert service.copies.current(stored).item_id == copy_id
    thumb = client.get(f"/api/library/items/{copy_id}/thumb")
    assert thumb.status_code == 200, thumb.text
    assert thumb.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(thumb.content)) as img:
        assert max(img.size) <= 640 and img.size[0] > img.size[1]
    assert client.get("/api/library/items/owned:nothing.jpg/thumb").status_code == 404


def test_fit() -> None:
    assert fit((900, 600), Image.new("RGB", (1800, 1200))).size == (1800, 1200)
    assert fit((900, 600), Image.new("RGB", (1840, 1200))).size == (1840, 1227)
    with pytest.raises(NotRestored):
        fit((900, 600), Image.new("RGB", (2048, 1152)))  # 16:9 for 3:2
    with pytest.raises(NotRestored):
        fit((900, 600), Image.new("RGB", (900, 600)))
