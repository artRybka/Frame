"""The restorer (frame_server.restorer): a small picture drawn again larger
by our own model, or by Google's as "Restaurator Pro", kept as the owner's
pick in the work's own id (Mateusz 2026-11-12, 2026-11-26)."""

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

from frame_server import restorer
from frame_server.ai.gatekeeper import asked_by_rules
from frame_server.ai.gemini import MODEL, PRO, Ask, NotDrawn
from frame_server.config import Settings
from frame_server.imaging import artsr
from frame_server.library import Item, low_res
from frame_server.library.models import Cut, ItemSummary
from frame_server.library.viewer import OWNER_ID
from frame_server.restorer import (
    CUT_KEY,
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


class FakeModel:
    """Our model: the picture four times as large, noting what it was given."""

    def __init__(self) -> None:
        self.asked: list[tuple[tuple[int, int], str]] = []
        self.tint = (1.0, 1.0, 1.0)

    def here(self) -> bool:
        return True

    def larger(self, picture: Image.Image, look: np.ndarray, kind: str) -> Image.Image:
        assert look.shape == (768,)
        self.asked.append((picture.size, kind))
        w, h = picture.size
        big = np.asarray(picture.resize((w * 4, h * 4), Image.Resampling.BICUBIC), np.float32)
        return Image.fromarray(np.clip(big * self.tint, 0, 255).astype(np.uint8))


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
        # The background left out: each test drains and polls itself.
        service.restorer.stop()
        if service.restorer._thread is not None:
            service.restorer._thread.join(10)
        service.restorer._stop.clear()
        service.restorer.model = FakeModel()  # type: ignore[assignment]
        service.restorer.look_of = lambda picture: np.ones(768, np.float32)
        yield client, service, web, painter


def test_a_small_picture_drawn_again_stays_the_same_work(app: Any) -> None:
    """Our own model draws it, on the server, for nothing (Mateusz
    2026-11-26), led by how it looks and by its kind; it goes into the
    asker's "Restaurator"."""
    client, service, _web, painter = app
    own = _small(service, favorite=True)
    assert low_res.low_side(own) == 900

    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    item = resp.json()
    assert item["id"] == own.id and item["favorite"]
    copy = item["sharper"]
    assert copy["restored"] and copy["chosen"] and copy["source"] == "owned"
    assert not copy["pro"]
    assert copy["museum"] == "Kreatywny restaurator"
    # Four times larger, brought to 2K.
    assert (copy["width"], copy["height"]) == (2048, 1365)
    assert painter.asked == [] and painter.batches == {}
    model = service.restorer.model
    assert model.asked == [((900, 600), "painting")]
    note = service.library.note(own.id, "restorer")
    assert note.model == "artsr-g3" and note.data["usd"] == 0.0

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
    # In "Restaurator", made for it.
    playlist = service.restorer.playlist(OWNER_ID)
    assert playlist is not None and playlist.name == "Restaurator"
    assert playlist.item_ids == [own.id] and playlist.owner == OWNER_ID
    # Drawn once.
    again = client.post(f"/api/library/items/{own.id}/restore")
    assert again.status_code == 422 and again.json()["detail"].startswith("restored:")
    # Back to the museum's picture.
    back = client.delete(f"/api/library/items/{own.id}/copy").json()
    assert back["sharper"] is None
    assert service.restorer.candidates()[0].id == own.id


def test_the_kind_the_model_is_led_by() -> None:
    def kind(medium: str, classification: str = "") -> str:
        return artsr.kind_of(
            Item(
                id="x:1",
                source="x",
                source_id="1",
                title="t",
                medium=medium,
                classification=classification,
            )
        )

    assert kind("Oil on canvas") == "painting"
    assert kind("Etching and drypoint") == "print"
    assert kind("Litografia barwna") == "print"
    assert kind("Pen and brown ink over graphite") == "drawing"
    assert kind("Watercolor on paper") == "drawing"
    assert kind("", "Prints") == "print"
    assert kind("") == "painting"


def test_a_large_picture_is_not_drawn(app: Any) -> None:
    client, service, web, _painter = app
    web[OWN] = _jpeg(_print(1, (2400, 1600)), 90)
    own = _own(service)
    own = service.library.update(own.id, width=2400, height=1600)
    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 422 and resp.json()["detail"].startswith("large:")
    resp = client.post(f"/api/library/items/{own.id}/restore/pro")
    assert resp.status_code == 422 and resp.json()["detail"].startswith("large:")


def test_the_favourites_drawn_in_the_background(app: Any) -> None:
    client, service, _web, painter = app
    own = _small(service)
    service.library.set_favorite(OWNER_ID, own.id, True)

    view = client.get("/api/ai/restorer").json()
    assert view == {
        "enabled": True,
        "pro": True,
        "items": 1,
        "usd": 0.0,
        "waiting": 0,
        "restored": 0,
    }
    view = client.post("/api/ai/restorer/favourites").json()
    assert view["items"] == 0 and view["waiting"] == 1
    # Ordered once: not again while it waits.
    assert service.restorer.order_favourites() == 0
    assert service.restorer.drain() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.restored
    assert painter.batches == {}
    view = client.get("/api/ai/restorer").json()
    assert view["waiting"] == 0 and view["restored"] == 1 and view["items"] == 0


def test_a_playlists_works_drawn_in_the_background(app: Any) -> None:
    """The playlist's "…" → "Restauracja dzieł" (Mateusz 2026-11-13): its
    works under the threshold, not only the favourites."""
    client, service, _web, _painter = app
    own = _small(service)
    made = client.post(
        "/api/playlists", json={"name": "Małe", "kind": "manual", "item_ids": [own.id]}
    )
    assert made.status_code == 200, made.text
    playlist_id = made.json()["playlist"]["id"]
    # Not a favourite: Konfiguracja's line leaves it out, the playlist's has it.
    assert client.get("/api/ai/restorer").json()["items"] == 0
    view = client.get(f"/api/ai/restorer/playlists/{playlist_id}").json()
    assert view["items"] == 1 and view["usd"] == 0.0

    view = client.post(f"/api/ai/restorer/playlists/{playlist_id}").json()
    assert view["items"] == 0 and view["waiting"] == 1
    assert client.post(f"/api/ai/restorer/playlists/{playlist_id}").json()["waiting"] == 1
    assert service.restorer.drain() == 1
    view = client.get(f"/api/ai/restorer/playlists/{playlist_id}").json()
    assert view["items"] == 0 and view["restored"] == 1 and view["waiting"] == 0
    assert client.get("/api/ai/restorer/playlists/999").status_code == 404


def test_restaurator_pro_through_the_batch(app: Any) -> None:
    """Google's 2.1 through the Batch API, one work ordered from its card
    (Mateusz 2026-11-26: "2.1 dla Restauratora PRO"); whoever ordered it
    is told."""
    client, service, _web, painter = app
    own = _small(service)
    told: list[tuple[str, str, bool]] = []
    service.restorer.on_pro = lambda item, by, ok: told.append((item.id, by, ok))

    resp = client.post(f"/api/library/items/{own.id}/restore/pro")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"sent": True, "left": None}  # the owner has no limit
    assert list(painter.batch_models.values()) == [MODEL]
    # Ordered once: not again while it waits.
    assert client.post(f"/api/library/items/{own.id}/restore/pro").json()["sent"] is False
    assert service.restorer.waiting() == {own.id}
    # The card knows it waits (its PRO entry spins, the plain one goes).
    assert client.get(f"/api/library/items/{own.id}").json()["restoring_pro"] is True
    stored = service.library.get(own.id)
    assert stored is not None and not stored.restoring_pro  # never kept

    assert service.restorer.poll() == 0  # not done yet
    painter.done.add("batches/1")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.restored and stored.sharper.pro
    assert stored.sharper.museum == "Restauracja PRO"
    assert told == [(own.id, OWNER_ID, True)]
    assert client.get(f"/api/library/items/{own.id}").json()["restoring_pro"] is False
    assert service.restorer.playlist(OWNER_ID).item_ids == [own.id]
    # Drawn by Pro: not again.
    again = client.post(f"/api/library/items/{own.id}/restore/pro")
    assert again.status_code == 422 and again.json()["detail"].startswith("restored:")


def test_pro_draws_a_work_ours_drew_from_the_museums_picture(app: Any) -> None:
    client, service, _web, painter = app
    own = _small(service)
    assert client.post(f"/api/library/items/{own.id}/restore").status_code == 200
    assert client.post(f"/api/library/items/{own.id}/restore/pro").json()["sent"]
    asked = painter.batches["batches/1"]
    assert asked[0].pictures[0].size == SMALL  # not our drawing
    painter.done.add("batches/1")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored.sharper.pro and (stored.sharper.width, stored.sharper.height) == (1803, 1200)
    assert service.restorer.playlist(OWNER_ID).item_ids == [own.id]


QUAD = [(0.1, 0.15), (0.9, 0.15), (0.9, 0.85), (0.1, 0.85)]


def _cut(service: FrameService, item: Item) -> Item:
    """``item`` cut on its museum's photograph (SMALL, 3:2) to a work of
    another shape, its original made again so."""
    cut = service.library.update(item.id, cut=Cut(work=QUAD, aspect=1.5))
    assert cut is not None
    service.images.recut(cut)
    return cut


def test_pro_after_ours_draws_the_work_as_cut(app: Any) -> None:
    """Restaurator Pro after our model draws the museum's photograph cut as
    the work is shown, not whole with its frame and board (Mateusz
    2026-11-26: „Restaurator PRO nie powinien ignorować wcześniejszego
    kadrowania”)."""
    client, service, _web, painter = app
    own = _cut(service, _small(service))
    assert client.post(f"/api/library/items/{own.id}/restore").status_code == 200
    ours = service.library.get(own.id)
    assert ours is not None and ours.sharper is not None
    shape = ours.sharper.width / ours.sharper.height
    assert abs(shape - 720 / 420) < 0.05  # ours drew the work as cut
    assert client.post(f"/api/library/items/{own.id}/restore/pro").json()["sent"]
    asked = painter.batches["batches/1"][0].pictures[0]
    assert abs(asked.width / asked.height - shape) < 0.05 and asked.width < SMALL[0]
    painter.done.add("batches/1")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.pro
    assert abs(stored.sharper.width / stored.sharper.height - shape) < 0.05


def test_a_drawing_of_the_whole_photograph_is_cut_to_the_work_once(app: Any) -> None:
    """Drawn whole before (Pro after ours, before 1.145.392): cut down to the
    work once, still Pro's, nothing drawn again."""
    _client, service, _web, painter = app
    own = _small(service)
    restorer = service.restorer
    drawn = painter._draw(_print(1, SMALL))
    picture = _print(1, SMALL)
    kept = restorer._keep(own, picture, drawn, 0.03, PRO, pro=True)
    assert kept.sharper is not None
    assert abs(kept.sharper.width / kept.sharper.height - 1.5) < 0.01
    _cut(service, service.library.get(own.id))

    assert restorer.cut_kept() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.restored and stored.sharper.pro
    assert abs(stored.sharper.width / stored.sharper.height - 720 / 420) < 0.05
    assert service.library.get_state(CUT_KEY, False)
    assert restorer.cut_kept() == 0  # once
    service.library.set_state(CUT_KEY, False)
    assert restorer.cut_kept() == 0  # cut already


def test_a_drawing_of_a_photograph_little_wider_than_its_work_is_cut_too(app: Any) -> None:
    """Van Gogh's "Der Bauer" (Leipzig): the card cut to the painting is
    0.78 wide to the photograph's 0.81, and its Pro drawing 0.81."""
    _client, service, _web, painter = app
    own = _small(service)
    picture = _print(1, SMALL)
    service.restorer._keep(own, picture, painter._draw(picture), 0.03, PRO, pro=True)
    narrow = [(0.03, 0.02), (0.95, 0.02), (0.95, 0.98), (0.03, 0.98)]  # 1.44 of 1.5
    cut = service.library.update(own.id, cut=Cut(work=narrow, aspect=1.5))
    assert cut is not None
    assert service.restorer.cut_kept() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.width / stored.sharper.height < 1.47


def test_a_printed_screens_grain_is_not_laid_under_the_drawing() -> None:
    """A scan of a postcard: its screen, too fine to be found, is not
    brought back over the drawing by the plain enlargement under it
    (Mateusz 2026-11-26: „usuwać raster wynikający ze skanu reprodukcji”)."""
    y, x = np.mgrid[0:300, 0:240]
    tones = 128 + 50 * np.sin(x / 11.0) * np.cos(y / 17.0)
    screen = (
        14
        * np.cos(2 * np.pi * (x + y) / (2.36 * 2**0.5))
        * np.cos(2 * np.pi * (x - y) / (2.36 * 2**0.5))
    )
    picture = Image.fromarray(
        np.clip(tones + screen, 0, 255)[..., None].repeat(3, -1).astype(np.uint8)
    )
    clean = Image.fromarray(tones[..., None].repeat(3, -1).astype(np.uint8))
    drawn = clean.resize((960, 1200), Image.Resampling.LANCZOS)  # the model drew it clean
    out = np.asarray(recoloured(picture, drawn).convert("L"), dtype=np.float32)
    plain = np.asarray(drawn.convert("L"), dtype=np.float32)
    left = out - cv2.GaussianBlur(out, (0, 0), 3) - (plain - cv2.GaussianBlur(plain, (0, 0), 3))
    assert float(np.abs(left).mean()) < 0.6


def test_without_googles_key_pro_is_not_ordered(app: Any) -> None:
    client, service, _web, painter = app
    own = _small(service)
    painter.enabled = lambda: False
    resp = client.post(f"/api/library/items/{own.id}/restore/pro")
    assert resp.status_code == 409
    assert client.get("/api/ai/restorer").json()["pro"] is False


def test_pro_after_two_tries_of_2_1() -> None:
    assert [model_for(n) for n in range(4)] == [MODEL] * FIRST_TRIES + [PRO] * 2


def test_a_batch_refusal_is_sent_again_then_noted(app: Any) -> None:
    _client, service, _web, painter = app
    own = _small(service)
    told: list[tuple[str, str, bool]] = []
    service.restorer.on_pro = lambda item, by, ok: told.append((item.id, by, ok))
    painter.refuse.add(SMALL)
    assert service.restorer.order_pro(own, "someone")
    for n in range(1, REFUSED_TRIES + 1):
        painter.done.add(f"batches/{n}")
        assert service.restorer.poll() == 0
    # Each refusal sent again in a batch of its own, five in all: two of
    # 2.1, then of Pro.
    assert len(painter.batches) == REFUSED_TRIES
    assert list(painter.batch_models.values()) == [MODEL, MODEL, PRO, PRO, PRO]
    assert service.restorer.waiting() == set()
    assert service.library.get(own.id).sharper is None
    assert told == [(own.id, "someone", False)]
    with pytest.raises(NotRestored):
        service.restorer.order_pro(own)
    # Our own model draws it still.
    assert service.restorer.candidates([own])[0].id == own.id


def test_a_batch_refusal_drawn_the_next_time(app: Any) -> None:
    _client, service, _web, painter = app
    own = _small(service)
    painter.refuse.add(SMALL)
    assert service.restorer.order_pro(own)
    painter.done.add("batches/1")
    assert service.restorer.poll() == 0
    assert service.restorer.waiting() == {own.id}  # sent again
    painter.refuse.clear()
    painter.done.add("batches/2")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.pro


def test_a_batch_drawing_2_1_did_not_give_goes_to_pro(app: Any) -> None:
    _client, service, _web, painter = app
    own = _small(service)
    painter.blank.add(MODEL)
    assert service.restorer.order_pro(own)
    for n in (1, 2):
        painter.done.add(f"batches/{n}")
        assert service.restorer.poll() == 0
    assert list(painter.batch_models.values()) == [MODEL, MODEL, PRO]
    painter.done.add("batches/3")
    assert service.restorer.poll() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.pro
    assert service.library.note(own.id, "restorer").model == PRO


def test_a_batch_from_before_goes_to_our_model(app: Any) -> None:
    """fal's and the favourites' batches waiting at the update: their works
    are drawn by our model instead."""
    _client, service, _web, _painter = app
    own = _small(service)
    service.library.set_state(
        "restorer.batches", [{"name": "fal:x", "model": "fal-ai/seedvr", "ids": [own.id]}]
    )
    assert service.restorer.poll() == 0
    assert service.restorer.waiting() == {own.id}
    assert service.restorer.drain() == 1
    assert service.library.get(own.id).sharper.restored


def test_the_works_restored_before_go_into_restaurator(app: Any) -> None:
    client, service, _web, _painter = app
    own = _small(service)
    assert client.post(f"/api/library/items/{own.id}/restore").status_code == 200
    service.library.save_playlist(
        service.restorer.playlist(OWNER_ID).model_copy(update={"item_ids": []})
    )
    service.library.set_state("restorer_playlist_filled", False)
    assert service.restorer.file_kept() == 1
    assert service.restorer.playlist(OWNER_ID).item_ids == [own.id]
    assert service.restorer.file_kept() == 0  # once


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

    assert size() == (2048, 1365)
    assert size(restored="false") == SMALL
    assert size(restored="false", cleaned="false") == SMALL
    assert size(side=600) == (600, 400)


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
    assert copy["restored"] and (copy["width"], copy["height"]) == (2048, 1365)
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
    # Not quite 0: the picture's finest grain is not laid under the drawing
    # (``GRAIN_SIGMA``), and this one's edges are a pixel sharp.
    assert off(model) > 8 and off(out) < 3.5

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

    client, service, _web, _painter = app
    own = _small(service, favorite=True)
    model = service.restorer.model
    model.tint = (1.1, 0.95, 0.8)  # a warmer, darker drawing
    monkeypatch.setattr(module, "recoloured", lambda picture, drawn, *_: drawn)  # as before
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
    assert len(model.asked) == 1

    assert service.restorer.recolour_kept() == 1
    stored = service.library.get(own.id)
    assert stored.sharper.restored and stored.sharper.url != before
    assert np.abs(tint(own) - museum).max() < 3
    assert service.library.note(own.id, "restorer").data["colours"] == module.COLOURS
    assert len(model.asked) == 1  # nothing drawn again
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


def test_pros_drawing_keeps_all_its_detail_and_takes_only_the_colours(
    app: Any, monkeypatch: Any
) -> None:
    """Restaurator Pro: no plain enlargement under Google's drawing, only
    the picture's colours (Mateusz 2026-11-26 16:09 UTC)."""
    from frame_server import restorer as module

    _client, service, _web, painter = app
    own = _small(service)
    picture = _print(1, SMALL)
    seen: list[float] = []

    def spy(p: Image.Image, d: Image.Image, share: float = module.DRAWN) -> Image.Image:
        seen.append(share)
        return recoloured(p, d, share)

    monkeypatch.setattr(module, "recoloured", spy)
    service.restorer._keep(own, picture, painter._draw(picture), 0.03, PRO, pro=True)
    assert seen == [1.0]


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


def test_pros_notification_opens_the_works_card(app: Any) -> None:
    """Tapped, "Restauracja gotowa" opens the work's own card (Mateusz
    2026-11-26: "kliknięcie na powiadomienie powinno przenieść na kartę tego
    dzieła"), and so does the one saying it was not drawn."""
    _client, service, _web, _painter = app
    own = _small(service)
    routes: list[str | None] = []
    service.notifier.notify = lambda *a, **kw: routes.append(kw.get("route"))
    service._restored_pro(own, OWNER_ID, True)
    service._restored_pro(own, OWNER_ID, False)
    assert routes == [f"work/{own.id}", f"work/{own.id}"]


def test_a_restored_works_tile_takes_its_drawings_shape(app: Any) -> None:
    """A drawing of the work cut out of the museum's photograph is not that
    photograph's shape: the tile (and the whole screen growing out of it)
    takes the drawing's, not bars beside it (Mateusz 2026-11-26)."""
    from frame_server.library.models import SharperCopy

    _client, service, _web, _painter = app
    own = _small(service)
    drawn = SharperCopy(
        url="", item_id=f"owned:{own.id}", source="owned", width=1560, height=2000, restored=True
    )
    restored = service.library.update(own.id, sharper=drawn)
    assert restored is not None
    summary = ItemSummary.of(restored)
    assert (summary.width, summary.height) == (1560, 2000)


def test_the_owner_cuts_a_restored_work_on_its_drawing(app: Any) -> None:
    """ "Popraw kadr" on a restored work (Mateusz 2026-11-26: "W przypadku
    dzieł po restauracji nadal chciałbym mieć opcję kadrowania"): the
    corners are the drawing's, and the work is shown cut so."""
    client, service, _web, _painter = app
    own = _small(service)
    drawn = client.post(f"/api/library/items/{own.id}/restore").json()
    corners = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    resp = client.put(f"/api/library/items/{own.id}/cut", json={"corners": corners})
    assert resp.status_code == 200, resp.text
    cut = resp.json()["cut"]
    assert cut["picture"] == drawn["sharper"]["item_id"] and cut["by"] == "owner"
    stored = service.library.get(own.id)
    assert stored is not None and stored.cut_shown() is not None
    with Image.open(service.images.image_path(stored)) as img:
        assert img.width < drawn["sharper"]["width"]  # cut down to the corners


def test_a_picture_up_to_1800_px_is_drawn_whole(app: Any) -> None:
    """Pictures shorter than 1800 px are offered (the mark of a small one
    stays at 1600), and the model is given the picture whole, not made
    smaller first (Mateusz 2026-11-26: "materiał wejściowy podajemy pełny.
    Rozszerzmy zdjęcia kwalifikujące się do 1800px"); the drawing is 2K."""
    client, service, web, _painter = app
    own = _small(service, favorite=True)
    web[OWN] = _jpeg(_print(1, (1700, 1133)), 90)
    larger = service.library.update(own.id, width=1700, height=1133)
    assert larger is not None
    assert low_res.low_side(larger) == 0 and low_res.restore_side(larger) == 1700
    assert [i.id for i in service.restorer.candidates()] == [own.id]

    resp = client.post(f"/api/library/items/{own.id}/restore")
    assert resp.status_code == 200, resp.text
    copy = resp.json()["sharper"]
    assert service.restorer.model.asked[0][0] == (1700, 1133)
    assert max(copy["width"], copy["height"]) == 2048


def test_our_model_draws_a_large_picture_in_tiles_into_bytes() -> None:
    """A picture of 1800 px is drawn tile by tile into a picture of bytes
    four times as large (7200 px of floats would be half a gigabyte)."""

    class Session:
        def run(self, _out: Any, feed: dict[str, np.ndarray]) -> list[np.ndarray]:
            part = feed["image"]
            return [part.repeat(artsr.SCALE, axis=2).repeat(artsr.SCALE, axis=3)]

    model = artsr.ArtSR()
    model._session = Session()  # type: ignore[assignment]
    picture = Image.fromarray(
        np.random.default_rng(1).integers(0, 256, (300, 520, 3), dtype=np.uint8)
    )
    drawn = model.larger(picture, np.zeros(768, np.float32), "painting")
    assert drawn.size == (2080, 1200)
    small = np.asarray(drawn.resize(picture.size, Image.Resampling.BOX), np.int16)
    assert np.abs(small - np.asarray(picture, np.int16)).max() <= 1


def test_the_phone_draws_a_work_and_the_server_keeps_it(app: Any) -> None:
    """Mateusz 2026-11-27: „Wszystko.” and „telefon wykonuje poprawę. Od
    razu ja pokazuje a w tle wysyła na serwer”. The phone asks how to draw
    the work (its kind, its looks) and the picture the server would draw
    it from, does it all itself, and sends the drawing: kept as the
    server's is, in the asker's "Restaurator", noted as the phone's."""
    client, service, _web, _painter = app
    own = _small(service, favorite=True)

    plan = client.get(f"/api/library/items/{own.id}/restore/plan")
    assert plan.status_code == 200, plan.text
    assert plan.json()["kind"] == 0 and len(plan.json()["look"]) == 768
    # Its kept numbers lead when there are some.
    service.restorer.look_kept = lambda item_id: np.full(768, 2.0, np.float32)
    assert client.get(f"/api/library/items/{own.id}/restore/plan").json()["look"][0] == 2.0

    source = client.get(f"/api/library/items/{own.id}/restore/source")
    assert source.status_code == 200 and source.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(source.content)) as img:
        assert img.size == (900, 600)

    drawn = _jpeg(_print(1, (2048, 1365)), 92)
    resp = client.post(
        f"/api/library/items/{own.id}/restore/drawn?width=900&height=600",
        content=drawn,
        headers={"Content-Type": "image/jpeg"},
    )
    assert resp.status_code == 200, resp.text
    copy = resp.json()["sharper"]
    assert copy["restored"] and not copy["pro"] and copy["museum"] == "Kreatywny restaurator"
    assert (copy["width"], copy["height"]) == (2048, 1365)
    assert service.restorer.model.asked == []  # not drawn here
    note = service.library.note(own.id, "restorer")
    assert note is not None and note.model == "artsr-g3-phone"
    assert note.data["own"] == [900, 600] and note.data["colours"] == restorer.COLOURS
    playlist = service.restorer.playlist(OWNER_ID)
    assert playlist is not None and playlist.item_ids == [own.id]
    # Drawn once: another phone's is not taken, nor a plan given.
    again = client.post(
        f"/api/library/items/{own.id}/restore/drawn?width=900&height=600", content=drawn
    )
    assert again.status_code == 200 and again.json()["sharper"] == copy
    assert client.get(f"/api/library/items/{own.id}/restore/plan").status_code == 422


def test_a_phones_drawing_no_larger_than_its_picture_is_not_kept(app: Any) -> None:
    client, service, _web, _painter = app
    own = _small(service)
    resp = client.post(
        f"/api/library/items/{own.id}/restore/drawn?width=900&height=600",
        content=_jpeg(_print(1, (900, 600))),
    )
    assert resp.status_code == 422 and resp.json()["detail"].startswith("small:")
    junk = client.post(
        f"/api/library/items/{own.id}/restore/drawn?width=900&height=600", content=b"no picture"
    )
    assert junk.status_code == 422
    assert service.library.get(own.id).sharper is None  # type: ignore[union-attr]
