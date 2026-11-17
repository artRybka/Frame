"""A work's thumbnail follows its original when the original came as another
photograph (Mateusz 2026-11-17: "Po wejściu zdjęcie się podmieniło. A
miniatura została stara"): Paris Musées' Géricault in its gilt frame stayed in
every list while the card showed Commons' canvas, kept when the museum was
down."""

from __future__ import annotations

import io
from concurrent.futures import Future
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from frame_server.library.images import ImageCache, same_photograph
from frame_server.library.models import Item, ItemSummary


def _canvas(width: int = 440, height: int = 500) -> Image.Image:
    """A painting: a sky over a dark hill, a tower, a light river."""
    y, x = np.mgrid[0:height, 0:width] / np.array([height, width])[:, None, None]
    rgb = np.zeros((height, width, 3))
    rgb[..., 0] = 0.25 + 0.5 * y + 0.1 * np.sin(9 * x)
    rgb[..., 1] = 0.35 + 0.3 * np.cos(5 * y) * x
    rgb[..., 2] = 0.8 - 0.6 * y
    rgb[(x > 0.6) & (x < 0.8) & (y > 0.3)] = (0.35, 0.3, 0.2)  # the tower
    rgb[(y > 0.75) & (x < 0.5)] = (0.7, 0.75, 0.8)  # the river
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def _framed(canvas: Image.Image) -> Image.Image:
    """The same painting photographed in its gilt frame."""
    border = canvas.width // 6
    rng = np.random.default_rng(1)
    size = (canvas.height + 2 * border, canvas.width + 2 * border, 3)
    gold = np.clip(rng.normal((190, 150, 60), 25, size), 0, 255).astype(np.uint8)
    framed = Image.fromarray(gold)
    framed.paste(canvas.resize((canvas.width, canvas.height)), (border, border))
    return framed


def _jpeg(img: Image.Image, side: int | None = None) -> bytes:
    if side is not None:
        img = img.copy()
        img.thumbnail((side, side))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def _paris(n: int = 222955) -> Item:
    files = "https://www.parismuseescollections.paris.fr/sites/default/files"
    return Item(
        id=f"paris:{n}",
        source="paris",
        source_id=str(n),
        title="Paysage italien au tombeau",
        artist="Théodore Géricault",
        thumb_url=f"{files}/styles/thumbnail/pdut{n}.jpg",
        image_url=f"{files}/atoms/pdut{n}.jpg",
    )


def _museums(canvas: Image.Image, museum_up: bool, seen: list[str]) -> httpx.MockTransport:
    """Paris Musées gives the framed photograph (or is down); Commons the
    canvas alone."""
    framed = _framed(canvas)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "commons.wikimedia.org":
            return httpx.Response(200, content=_jpeg(canvas), request=request)
        if "styles/thumbnail" in request.url.path:
            return httpx.Response(200, content=_jpeg(framed, 300), request=request)
        if not museum_up:
            return httpx.Response(404, request=request)
        return httpx.Response(200, content=_jpeg(framed), request=request)

    return httpx.MockTransport(handler)


def _commons(item: Item, thumb: bool) -> list[str]:
    return [f"https://commons.wikimedia.org/{item.source_id}"]


def _cache(tmp_path: Path, museum_up: bool, canvas: Image.Image) -> tuple[ImageCache, list[str]]:
    seen: list[str] = []
    transport = _museums(canvas, museum_up, seen)
    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=transport))
    cache.mirrors["paris"] = _commons
    return cache, seen


def _thumb(cache: ImageCache, item: Item) -> Image.Image:
    with Image.open(cache.thumb_path(item)) as img:
        return img.convert("RGB")


def _original(cache: ImageCache, item: Item) -> Image.Image:
    with Image.open(cache.image_path(item)) as img:
        return img.convert("RGB")


def test_a_photograph_is_told_from_another_of_the_same_work() -> None:
    canvas = _canvas()
    small = Image.open(io.BytesIO(_jpeg(canvas, 200)))
    assert same_photograph(small, canvas)
    assert same_photograph(canvas.point(lambda v: min(255, int(v * 1.1))), canvas)  # lighter
    assert not same_photograph(_framed(canvas), canvas)
    # Of one shape, other in what is where.
    assert not same_photograph(canvas.transpose(Image.Transpose.FLIP_TOP_BOTTOM), canvas)


def test_an_original_from_a_mirror_makes_the_thumbnail_again(tmp_path: Path) -> None:
    canvas, item = _canvas(), _paris()
    cache, seen = _cache(tmp_path, museum_up=False, canvas=canvas)
    told: list[tuple[str, str]] = []
    cache.repictured = lambda work, stamp: told.append((work.id, stamp))
    cache.ensure_thumb(item)
    cache.tile(cache.thumb_path(item))  # Odkrywaj's cover tile of the old one
    assert not same_photograph(_thumb(cache, item), canvas)  # the gilt frame
    stamp_before = cache.sent_thumb(item.id)

    cache.ensure_image(item)  # the card: the museum down, Commons' canvas
    assert "commons.wikimedia.org" in seen
    assert same_photograph(_thumb(cache, item), _original(cache, item))
    assert same_photograph(_thumb(cache, item), canvas)
    assert [work for work, _ in told] == [item.id] and len(told[0][1]) == 12
    # The phone holding the old one by its stamp is sent the new one.
    assert stamp_before is not None
    sent = cache.sent_thumb(item.id, tile=True, have=[stamp_before.stamp])
    assert sent is not None and sent.data is not None
    assert same_photograph(Image.open(io.BytesIO(sent.data)), canvas)
    # Asked again: nothing more to do.
    cache.ensure_image(item)
    assert cache.thumb_follows(item) is None and len(told) == 1


def test_the_same_photograph_leaves_the_thumbnail_be(tmp_path: Path) -> None:
    item = _paris()
    cache, _ = _cache(tmp_path, museum_up=True, canvas=_canvas())
    told: list[str] = []
    cache.repictured = lambda work, stamp: told.append(stamp)
    cache.ensure_thumb(item)
    before = cache.thumb_path(item).read_bytes()
    cache.ensure_image(item)  # the museum's own original: framed as its thumbnail
    assert told == [] and cache.thumb_path(item).read_bytes() == before


def test_thumbnails_kept_before_follow_their_originals_once(tmp_path: Path) -> None:
    canvas, item, other = _canvas(), _paris(1), _paris(2)
    cache, _ = _cache(tmp_path, museum_up=False, canvas=canvas)
    for work in (item, other):
        cache.ensure_thumb(work)
    # Kept before thumbnails followed: the canvas beside the framed thumbnail.
    cache.image_path(item).write_bytes(_jpeg(canvas))
    told: list[str] = []
    cache.repictured = lambda work, stamp: told.append(work.id)
    assert cache.thumbs_follow([item, other]) == 1  # the other has no original here
    assert told == [item.id] and same_photograph(_thumb(cache, item), canvas)


def test_the_app_is_told_of_the_new_photograph(service) -> None:
    """The work's stamp changes: lists and the card's look for a sharper
    copy carry it, so the app asks for the thumbnail again; its colours and
    shape are the canvas's."""
    from fastapi.testclient import TestClient

    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    canvas = _canvas(600, 400)  # wider than its frame's photograph
    transport = _museums(canvas, False, [])
    svc.images.http = lambda: httpx.Client(transport=transport)
    svc.images.mirrors["paris"] = _commons
    looked: Future[str] = Future()
    looked.set_result("none")
    svc.sharper.soon = lambda item: looked  # no other source asked
    item = svc.importer.add(_paris().model_copy(update={"pooled": True}))
    colours = item.colors
    svc.library.update(item.id, picture_hash="abc")
    with TestClient(app) as client:
        assert client.get(f"/api/library/items/{item.id}/image").status_code == 200
        stored = svc.library.get(item.id)
        assert stored is not None and stored.picture_stamp
        assert ItemSummary.of(stored).picture_stamp == stored.picture_stamp
        assert stored.picture_hash == ""  # worked out again from the new thumbnail
        assert stored.colors != colours
        assert (stored.width, stored.height) == canvas.size  # its shape, for the tiles
        view = client.post(f"/api/library/items/{item.id}/sharpen").json()
        assert view["picture_stamp"] == stored.picture_stamp
        card = client.get(f"/api/library/items/{item.id}").json()
        assert card["picture_stamp"] == stored.picture_stamp
