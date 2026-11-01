"""Sharper copies of works whose own picture is poor (frame_server.sharper)."""

from __future__ import annotations

import io
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageOps

from frame_server.config import Settings
from frame_server.library import Item, ItemKind
from frame_server.library.images import ImageCache
from frame_server.library.models import SharperCopy
from frame_server.service import FrameService
from frame_server.sharper import Quality, Tone, same_colours
from frame_server.web.app import create_app


def _print(seed: int, size: tuple[int, int] = (900, 600)) -> Image.Image:
    """A made-up painting: shapes in many tones, different for each seed."""
    rng = random.Random(seed)
    img = Image.new("RGB", (900, 600), (235, 225, 200))
    draw = ImageDraw.Draw(img)
    for _ in range(160):
        x, y = rng.randrange(900), rng.randrange(600)
        w, h = rng.randrange(10, 120), rng.randrange(10, 120)
        tone = tuple(rng.randrange(256) for _ in range(3))
        shape = draw.ellipse if rng.random() < 0.5 else draw.rectangle
        shape((x, y, x + w, y + h), fill=tone, outline=(20, 20, 20))
    return img.resize(size, Image.Resampling.LANCZOS)


def _jpeg(img: Image.Image, quality: int = 92) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality)
    return out.getvalue()


def _detail(img: Image.Image) -> Image.Image:
    """A close-up of the painting, as museums publish them too."""
    w, h = img.size
    return img.crop((w // 5, h // 5, w * 4 // 5, h * 4 // 5)).resize(img.size)


def _album_page(img: Image.Image) -> Image.Image:
    """The painting printed on a page with a wide margin and a caption."""
    w, h = img.size
    page = ImageOps.expand(img, border=(w // 3, h // 4, w // 3, h // 2), fill=(245, 242, 235))
    draw = ImageDraw.Draw(page)
    draw.rectangle((w // 3, h * 5 // 4 + h // 10, w, h * 5 // 4 + h // 7), fill=(30, 30, 30))
    return page


#: What the fake web serves, by address.
Web = dict[str, bytes]


def _serve(service: FrameService, web: Web) -> list[str]:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        asked.append(url)
        if url in web:
            return httpx.Response(200, content=web[url])
        return httpx.Response(404)

    service.images.http = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    return asked


OWN = "https://www.artic.edu/iiif/2/abc/full/1686,/0/default.jpg"
OWN_THUMB = "https://www.artic.edu/iiif/2/abc/full/600,/0/default.jpg"


def _own(service: FrameService, **kw: Any) -> Item:
    kw.setdefault("title", "Bathing Nymphs and Child")
    kw.setdefault("artist", "Camille Corot")
    return service.library.upsert(
        Item(
            id="aic:4760",
            kind=ItemKind.ARTWORK,
            source="aic",
            source_id="4760",
            museum="Art Institute of Chicago",
            classification="Painting",
            image_url=OWN,
            thumb_url=OWN_THUMB,
            width=1686,
            height=1124,
            **kw,
        )
    )


def _copy(n: int, **kw: Any) -> Item:
    kw.setdefault("title", "Bathing Nymphs and Child")
    kw.setdefault("artist", "Jean-Baptiste-Camille Corot")
    kw.setdefault("width", 3600)
    kw.setdefault("height", 2400)
    return Item(
        id=f"wmc:{n}",
        kind=ItemKind.ARTWORK,
        source="wmc",
        source_id=str(n),
        museum="Wikimedia Commons",
        classification="Painting",
        image_url=f"https://upload.wikimedia.org/copy{n}.jpg",
        thumb_url=f"https://upload.wikimedia.org/thumb{n}.jpg",
        **kw,
    )


def _offer(web: Web, copy: Item, picture: Image.Image) -> None:
    web[copy.image_url] = _jpeg(picture)
    web[copy.thumb_url] = _jpeg(picture.resize((600, 600 * picture.height // picture.width)))


@pytest.fixture
def frame(service: FrameService) -> tuple[FrameService, Web, Callable[[list[Item]], None]]:
    """The service with a fake web, a museum work with a small picture on
    it, and the sources' answers to be set."""
    web: Web = {
        OWN: _jpeg(_print(1, (1686, 1124)), 85),
        OWN_THUMB: _jpeg(_print(1, (600, 400))),
    }
    _serve(service, web)
    hits: list[Item] = []
    service.sharper.search = lambda query, n: (len(hits), list(hits), [])
    service.sharper.commons_file = lambda item: ""

    def answer(found: list[Item]) -> None:
        hits[:] = found

    return service, web, answer


def test_poor_and_better_pictures() -> None:
    aic = Quality(1686, 2.1)
    assert aic.weak
    assert not Quality(2560, 1.8).weak
    assert Quality(2560, 0.3).weak  # squeezed
    assert Quality(3600, 1.5).better(aic)
    assert not Quality(1900, 1.5).better(aic)  # hardly larger
    assert not Quality(3600, 0.1).better(aic)  # large, but mush
    assert Quality(1200).better(Quality(0))  # anything over the thumbnail
    assert not Quality(800).better(Quality(0))
    # As large, but far less squeezed.
    assert Quality(1686, 1.6).better(Quality(1686, 0.4))
    assert not Quality(1686, 1.6).better(Quality(1686, 1.2))


def test_colours_tell_a_black_and_white_plate() -> None:
    painting = Tone(0.06, (0.7, 0.02, 0.05))
    assert same_colours(painting, Tone(0.05, (0.68, 0.025, 0.045)))
    assert not same_colours(painting, Tone(0.004, (0.7, 0.0, 0.01)))  # B&W plate
    assert not same_colours(painting, Tone(0.06, (0.45, 0.02, 0.05)))  # far darker
    etching = Tone(0.003, (0.8, 0.01, 0.03))
    assert not same_colours(etching, Tone(0.05, (0.8, 0.02, 0.05)))  # coloured in


def test_a_poor_picture_is_swapped_for_a_sharper_copy(frame: Any) -> None:
    service, web, answer = frame
    own = _own(service)
    copy = _copy(9)
    _offer(web, copy, _print(1, (3600, 2400)))
    answer([copy])
    assert service.sharper.soon(own).result(30) == "found"

    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "wmc:9"
    assert stored.sharper.url == copy.image_url
    assert stored.title == "Bathing Nymphs and Child"  # the work's own texts stay
    with Image.open(service.images.image_path(stored)) as img:
        assert max(img.size) == 2560  # the copy, cut down to the frame
    assert service.images.source_size(stored) is not None
    # Known from now on: asked again, nothing is looked up.
    answer([])
    assert service.sharper.soon(stored).result(1) == "found"


def test_a_good_picture_is_left_alone(frame: Any) -> None:
    service, web, _ = frame
    web[OWN] = _jpeg(_print(1, (3000, 2000)))
    own = _own(service)
    asked: list[str] = []
    service.sharper.search = lambda query, n: (asked.append(query), (0, [], []))[1]
    assert service.sharper.soon(own).result(30) == "fine"
    assert asked == []
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is None


def test_only_the_same_picture_whole_stands_in(frame: Any) -> None:
    """A detail, an album page, a black-and-white plate, another work by
    the artist, a smaller copy: none takes the work's place."""
    service, web, answer = frame
    own = _own(service)
    painting = _print(1, (3600, 2400))
    copies = [
        (_copy(1), _detail(painting)),
        (_copy(2, title="Album reprodukcji: Corot"), painting),
        (_copy(3), ImageOps.grayscale(painting).convert("RGB")),
        (_copy(4, title="Ville-d'Avray"), _print(7, (3600, 2400))),
        (_copy(5, width=1700, height=1133), _print(1, (1700, 1133))),
        (_copy(6, width=4800, height=4000), _album_page(painting)),
    ]
    for copy, picture in copies:
        _offer(web, copy, picture)
    answer([c for c, _ in copies])
    assert service.sharper.soon(own).result(60) == "none"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is None
    # Remembered: not looked for again on the next visit.
    answer([])
    service.sharper.search = lambda query, n: pytest.fail("looked again")
    assert service.sharper.soon(stored).result(1) == "none"


def test_the_works_commons_file_comes_first(frame: Any) -> None:
    service, web, answer = frame
    own = _own(service)
    commons = _copy(77, title="Kąpiące się nimfy i dziecko")  # its Polish title
    _offer(web, commons, _print(1, (3600, 2400)))
    names: list[str] = []

    def file(name: str) -> Item | None:
        names.append(name)
        return commons

    service.sharper.commons_file = lambda item: "Corot - Bathing Nymphs.jpg"
    service.importer.commons_file = file  # type: ignore[method-assign]
    answer([])
    assert service.sharper.soon(own).result(30) == "found"
    assert names == ["Corot - Bathing Nymphs.jpg"]
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "wmc:77"


def test_the_sharper_copy_is_downloaded_first_and_the_own_after(tmp_path: Path) -> None:
    asked: list[str] = []
    web = {"https://museum.example/own.jpg": _jpeg(_print(1, (800, 533)))}

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        data = web.get(str(request.url))
        return httpx.Response(200, content=data) if data else httpx.Response(404)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    item = Item(
        id="aic:1",
        source="aic",
        source_id="1",
        image_url="https://museum.example/own.jpg",
        sharper=SharperCopy(
            url="https://upload.wikimedia.org/gone.jpg",
            item_id="wmc:1",
            source="wmc",
            width=3000,
            height=2000,
        ),
    )
    cache.ensure_image(item)
    assert asked == ["https://upload.wikimedia.org/gone.jpg", "https://museum.example/own.jpg"]


def test_the_card_asks_and_the_frame_gets_the_copy(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    service: FrameService = app.state.service
    with TestClient(app) as client:
        web: Web = {
            OWN: _jpeg(_print(1, (1686, 1124)), 85),
            OWN_THUMB: _jpeg(_print(1, (600, 400))),
        }
        _serve(service, web)
        own = _own(service)
        copy = _copy(9)
        _offer(web, copy, _print(1, (3600, 2400)))
        service.sharper.search = lambda query, n: (1, [copy], [])
        service.sharper.commons_file = lambda item: ""
        view = client.post(f"/api/library/items/{own.id}/sharpen", params={"wait": 30}).json()
        assert view["status"] == "found"
        assert view["sharper"]["item_id"] == "wmc:9"
        assert view["sharper"]["museum"] == "Wikimedia Commons"
        item = client.get(f"/api/library/items/{own.id}").json()
        assert item["sharper"]["item_id"] == "wmc:9"
        picture = client.get(f"/api/library/items/{own.id}/image", params={"v": "wmc:9"})
        with Image.open(io.BytesIO(picture.content)) as img:
            assert max(img.size) == 2560
        # A photo has no other copies to look for.
        photo = service.library.upsert(
            Item(id="upload:1", kind=ItemKind.PHOTO, source="upload", source_id="1")
        )
        view = client.post(f"/api/library/items/{photo.id}/sharpen").json()
        assert view == {"status": "off", "sharper": None}


def test_the_work_of_the_day_gets_its_sharper_copy_before_its_page(frame: Any) -> None:
    from datetime import date

    from frame_server.daily import HISTORY_KEY

    service, web, answer = frame
    own = _own(service)
    copy = _copy(9)
    _offer(web, copy, _print(1, (3600, 2400)))
    answer([copy])
    asked: list[str | None] = []
    service.daily.ask = lambda item: asked.append(item.sharper and item.sharper.item_id)  # type: ignore[method-assign]
    service.library.set_state(HISTORY_KEY, {date.today().isoformat(): own.id})
    service.daily.tick()
    assert asked == ["wmc:9"]  # the page is written from the sharper copy
