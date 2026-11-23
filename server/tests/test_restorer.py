"""The creative restorer (frame_server.restorer): a small picture drawn again
larger by the image model, kept as the owner's pick in the work's own id
(Mateusz 2026-11-12)."""

from __future__ import annotations

import io
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_sharper import OWN, OWN_THUMB, Web, _jpeg, _own, _print, _serve

from frame_server.ai.gatekeeper import asked_by_rules
from frame_server.ai.gemini import MODEL, PRO, Ask, NotDrawn
from frame_server.config import Settings
from frame_server.library import Item, low_res
from frame_server.library.models import ItemSummary
from frame_server.library.viewer import OWNER_ID
from frame_server.restorer import (
    FIRST_TRIES,
    REFUSED_TRIES,
    NotRestored,
    fit,
    model_for,
    recoloured,
)
from frame_server.service import FrameService
from frame_server.web.app import create_app

SMALL = (900, 600)


class FakePainter:
    """The image model: the picture twice as large, or a refusal."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []
        self.models: list[str] = []
        self.refuse: set[tuple[int, int]] = set()
        #: Models that answer with no picture.
        self.blank: set[str] = set()
        self.batches: dict[str, list[Ask]] = {}
        self.batch_models: dict[str, str] = {}
        self.done: set[str] = set()

    def enabled(self) -> bool:
        return True

    @staticmethod
    def _draw(picture: Image.Image) -> Image.Image:
        w, h = picture.size
        return picture.resize((w * 2 + 3, h * 2), Image.Resampling.BICUBIC)  # a hair wider

    def paint(
        self,
        kind: str,
        prompt: str,
        pictures: Sequence[Image.Image],
        size: str = "1K",
        *,
        model: str = MODEL,
    ) -> tuple[Image.Image, float]:
        self.asked.append((kind, size))
        self.models.append(model)
        if model in self.blank:
            raise NotDrawn("Google's answer has no picture")
        if pictures[0].size in self.refuse:
            raise NotDrawn("Google answered 400", "image_recitation")
        return self._draw(pictures[0]), 0.06

    def batch(self, kind: str, asks: Sequence[Ask], model: str = MODEL) -> str:
        name = f"batches/{len(self.batches) + 1}"
        self.batches[name] = list(asks)
        self.batch_models[name] = model
        return name

    def batched(
        self, kind: str, batch: str, model: str = MODEL
    ) -> dict[str, tuple[Image.Image, float] | NotDrawn] | None:
        if batch not in self.done:
            return None
        assert model == self.batch_models[batch]
        found: dict[str, tuple[Image.Image, float] | NotDrawn] = {}
        for ask in self.batches[batch]:
            picture = ask.pictures[0]
            if model in self.blank:
                found[ask.name] = NotDrawn("Google's answer has no picture")
            elif picture.size in self.refuse:
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
    # Asked five times before it gives up (a refusal costs nothing): twice
    # of 2.1, then of Pro (Mateusz 2026-11-16).
    assert len(painter.asked) == REFUSED_TRIES == 5
    assert painter.models == [MODEL, MODEL, PRO, PRO, PRO]
    assert service.library.get(own.id).sharper is None
    assert service.restorer.candidates() == []


def test_a_refusal_now_and_then_is_asked_again(app: Any) -> None:
    """Google now and then takes the question it refused: the card asks
    again (Mateusz 2026-11-13, Delacroix's "Rzeź na Chios")."""
    client, service, _web, painter = app
    own = _small(service, favorite=True)
    refusals = iter([True, True, False])
    draw = painter.paint

    def paint(kind: str, prompt: str, pictures: Any, size: str = "1K", **kw: Any) -> Any:
        if next(refusals):
            painter.asked.append((kind, size))
            raise NotDrawn("Google answered 400", "image_recitation")
        return draw(kind, prompt, pictures, size, **kw)

    painter.paint = paint
    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    assert resp.json()["sharper"]["restored"]
    assert len(painter.asked) == 3
    assert painter.models == [PRO]  # the third try, of Pro
    assert service.library.note(own.id, "restorer").model == PRO


def test_pro_after_two_tries_of_2_1() -> None:
    assert [model_for(n) for n in range(4)] == [MODEL] * FIRST_TRIES + [PRO] * 2


def test_a_drawing_2_1_did_not_give_is_asked_of_pro(app: Any) -> None:
    """No picture from 2.1 twice: Pro draws it (Mateusz 2026-11-16: "gdy
    pierwsze 2 zawiodą odpalajmy pro"); with none from Pro either, the card
    says so."""
    client, service, _web, painter = app
    own = _small(service, favorite=True)
    painter.blank.add(MODEL)
    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    assert painter.models == [MODEL, MODEL, PRO]


def test_no_drawing_from_pro_either(app: Any) -> None:
    client, service, _web, painter = app
    own = _small(service, favorite=True)
    painter.blank |= {MODEL, PRO}
    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 422 and resp.json()["detail"].startswith("not_drawn:")
    assert painter.models == [MODEL, MODEL, PRO]


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
    assert view == {
        "enabled": True,
        "by_fal": False,
        "items": 1,
        "usd": 0.03,
        "waiting": 0,
        "restored": 0,
    }
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


def test_a_batch_refusal_is_sent_again_then_noted(app: Any) -> None:
    _client, service, _web, painter = app
    own = _small(service)
    service.library.set_favorite(OWNER_ID, own.id, True)
    painter.refuse.add(SMALL)
    assert service.restorer.order_favourites() == 1
    for n in range(1, REFUSED_TRIES + 1):
        painter.done.add(f"batches/{n}")
        assert service.restorer.poll() == 0
    # Each refusal sent again in a batch of its own, five in all: two of
    # 2.1, then of Pro.
    assert len(painter.batches) == REFUSED_TRIES
    assert list(painter.batch_models.values()) == [MODEL, MODEL, PRO, PRO, PRO]
    assert service.restorer.waiting() == set()
    assert service.library.get(own.id).sharper is None
    assert service.restorer.candidates() == []
    assert service.restorer.order_favourites() == 0


def test_a_batch_refusal_drawn_the_next_time(app: Any) -> None:
    _client, service, _web, painter = app
    own = _small(service)
    service.library.set_favorite(OWNER_ID, own.id, True)
    painter.refuse.add(SMALL)
    assert service.restorer.order_favourites() == 1
    painter.done.add("batches/1")
    assert service.restorer.poll() == 0
    assert service.restorer.waiting() == {own.id}  # sent again
    painter.refuse.clear()
    painter.done.add("batches/2")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.restored


def test_a_batch_drawing_2_1_did_not_give_goes_to_pro(app: Any) -> None:
    _client, service, _web, painter = app
    own = _small(service)
    service.library.set_favorite(OWNER_ID, own.id, True)
    painter.blank.add(MODEL)
    assert service.restorer.order_favourites() == 1
    for n in (1, 2):
        painter.done.add(f"batches/{n}")
        assert service.restorer.poll() == 0
    assert list(painter.batch_models.values()) == [MODEL, MODEL, PRO]
    painter.done.add("batches/3")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.restored
    assert service.library.note(own.id, "restorer").model == PRO


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
    assert view == {
        "enabled": True,
        "by_fal": False,
        "items": 1,
        "usd": 0.03,
        "waiting": 0,
        "restored": 0,
    }

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


def test_the_viewer_shows_the_museums_picture_beside_the_drawing(app: Any) -> None:
    """The full-screen viewer's button (Mateusz 2026-11-16): the work
    without the restorer's drawing is the museum's own photograph."""
    client, service, _web, _painter = app
    own = _small(service, favorite=True)
    assert client.post(f"/api/library/items/{own.id}/restore").status_code == 200

    def size(**query: Any) -> tuple[int, int]:
        resp = client.get(f"/api/library/items/{own.id}/treated", params=query)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "image/jpeg"
        with Image.open(io.BytesIO(resp.content)) as img:
            return img.size

    assert size() == (1803, 1200)
    assert size(restored="false") == SMALL
    assert size(restored="false", cleaned="false") == SMALL
    assert size(side=600) == (600, 399)


def test_a_work_shown_from_its_thumbnail_is_small_and_drawn_from_it(app: Any) -> None:
    """A dead link (Europeana's Delaunay "Rythmes", a Dropbox error page,
    2026-11-16): the card shows the thumbnail, so the work is marked small
    and "Restauracja dzieła" draws that thumbnail larger."""
    client, service, web, _painter = app
    web[OWN] = b"<!doctype html><title>Dropbox - Error</title>"
    own = _own(service, favorite=True)
    dead = service.library.update(own.id, width=None, height=None)
    assert dead is not None and low_res.low_side(dead) == 0  # nothing known yet

    shown = client.get(f"/api/library/items/{own.id}/image")
    assert shown.status_code == 200 and shown.headers["cache-control"] == "no-store"
    with Image.open(io.BytesIO(shown.content)) as img:
        assert img.size == (600, 400)
    assert service.images.unavailable(dead)
    assert low_res.low_side(dead) == 600

    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    copy = resp.json()["sharper"]
    assert copy["restored"] and (copy["width"], copy["height"]) == (1203, 800)
    # The full screen's button: without the drawing, the thumbnail again.
    before = client.get(f"/api/library/items/{own.id}/treated", params={"restored": "false"})
    assert before.status_code == 200, before.text
    with Image.open(io.BytesIO(before.content)) as img:
        assert img.size == (600, 400)


def test_the_drawing_takes_the_pictures_colours() -> None:
    """The model's drawing a little warmer and lighter than the museum's
    picture (Mateusz 2026-11-16): its colours come back from the picture,
    the detail it drew stays."""
    picture = _print(3, (450, 300))
    drawn = np.asarray(_print(3, (900, 600))).astype(np.float32)
    checker = (np.indices((600, 900)).sum(0) % 2 * 24 - 12).astype(np.float32)[..., None]
    shifted = np.clip(drawn * np.array([1.08, 1.0, 0.86]) + np.array([10, 4, -6]) + checker, 0, 255)
    model = Image.fromarray(shifted.astype(np.uint8), "RGB")

    def off(img: Image.Image) -> float:
        small = np.asarray(img.resize(picture.size, Image.Resampling.LANCZOS)).astype(float)
        return float(np.abs(small - np.asarray(picture).astype(float)).mean())

    out = recoloured(picture, model)
    assert out.size == model.size
    assert off(model) > 8 and off(out) < 3

    # The fine detail is the model's, as it drew it.
    def fine(img: Image.Image) -> np.ndarray:
        grey = np.asarray(img.convert("L")).astype(np.float32)
        return (grey - cv2.GaussianBlur(grey, (0, 0), 1.5)).ravel()

    assert np.corrcoef(fine(out), fine(model))[0, 1] > 0.9


def test_fit() -> None:
    assert fit((900, 600), Image.new("RGB", (1800, 1200))).size == (1800, 1200)
    assert fit((900, 600), Image.new("RGB", (1840, 1200))).size == (1840, 1227)
    with pytest.raises(NotRestored):
        fit((900, 600), Image.new("RGB", (2048, 1152)))  # 16:9 for 3:2
    with pytest.raises(NotRestored):
        fit((900, 600), Image.new("RGB", (900, 600)))


def test_a_drawing_kept_before_is_put_in_the_pictures_colours(app: Any, monkeypatch: Any) -> None:
    """The drawings kept before the colours were taken back get them once,
    nothing drawn again (Mateusz 2026-11-16: "Tak - poproszę")."""
    from frame_server import restorer as module

    client, service, _web, painter = app
    own = _small(service, favorite=True)
    draw = painter._draw
    painter._draw = lambda picture: Image.fromarray(  # a warmer, darker drawing
        np.clip(np.asarray(draw(picture), np.float32) * [1.1, 0.95, 0.8], 0, 255).astype(np.uint8)
    )
    monkeypatch.setattr(module, "recoloured", lambda picture, drawn: drawn)  # as before
    assert client.post(f"/api/library/items/{own.id}/restore").status_code == 200
    monkeypatch.undo()
    note = service.library.note(own.id, "restorer")
    old = {k: v for k, v in note.data.items() if k != "colours"}
    service.library.save_note(note.model_copy(update={"data": old}))
    before = service.library.get(own.id).sharper.url

    def tint(item: Item) -> np.ndarray:
        url = service.library.get(item.id).sharper.url
        return np.asarray(service.images.sample(url), np.float32).mean(axis=(0, 1))

    museum = np.asarray(service.images.before_drawn(own), np.float32).mean(axis=(0, 1))
    assert np.abs(tint(own) - museum).max() > 10
    assert len(painter.asked) == 1

    assert service.restorer.recolour_kept() == 1
    stored = service.library.get(own.id)
    assert stored.sharper.restored and stored.sharper.url != before
    assert np.abs(tint(own) - museum).max() < 3
    assert service.library.note(own.id, "restorer").data["colours"] == module.COLOURS
    assert len(painter.asked) == 1  # nothing drawn again
    # Once.
    assert service.restorer.recolour_kept() == 0


def test_part_of_what_the_model_drew_finer_than_the_picture_is_kept() -> None:
    rng = np.random.default_rng(3)
    y, x = np.mgrid[0:100, 0:80]
    tones = (128 + 60 * np.sin(x / 5.0) * np.cos(y / 7.0))[..., None].repeat(3, -1)
    picture = Image.fromarray(tones.astype(np.uint8))
    plain = np.asarray(picture.resize((320, 400), Image.Resampling.LANCZOS), dtype=np.float32)
    made_up = rng.normal(0, 20, plain.shape)
    drawn = np.clip(plain + made_up, 0, 255).astype(np.uint8)
    kept = np.asarray(recoloured(picture, Image.fromarray(drawn)), dtype=np.float32)
    ratio = float((kept - plain).std()) / float((drawn - plain).std())
    assert 0.55 < ratio < 0.85


def test_a_drawing_a_few_pixels_off_its_picture_is_laid_on_it_first() -> None:
    rng = np.random.default_rng(5)
    y, x = np.mgrid[0:300, 0:240]
    tones = (128 + 60 * np.sin(x / 9.0) * np.cos(y / 13.0))[..., None].repeat(3, -1)
    picture = Image.fromarray(tones.astype(np.uint8))
    big = np.asarray(picture.resize((960, 1200), Image.Resampling.LANCZOS), dtype=np.float32)
    drawn = np.roll(big, (10, -8), (0, 1)) + rng.normal(0, 4, big.shape)
    drawn = np.clip(drawn, 0, 255).astype(np.uint8)
    out = np.asarray(recoloured(picture, Image.fromarray(drawn)), dtype=np.float32)
    coarse = cv2.GaussianBlur(np.abs(out - drawn.astype(np.float32)), (0, 0), 3)
    assert float(coarse.mean()) < 3.0


def test_a_drawing_of_another_picture_is_kept_as_drawn() -> None:
    rng = np.random.default_rng(6)
    picture = Image.fromarray(rng.integers(0, 255, (120, 100, 3), dtype=np.uint8))
    other = Image.fromarray(rng.integers(0, 255, (480, 400, 3), dtype=np.uint8))
    assert np.array_equal(np.asarray(recoloured(picture, other)), np.asarray(other))
