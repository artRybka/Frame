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
        if url in web:  # nothing kept: the server is there, but fails
            return httpx.Response(200, content=web[url]) if web[url] else httpx.Response(502)
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
    # Foto Marburg's faded slide of the olive grove against WikiArt's copy:
    # close on average, four times as colourful (Mateusz 2026-11-09).
    slide = Tone(0.0197, (0.529, 0.005, 0.001))
    wikiart = Tone(0.0773, (0.576, -0.008, 0.030))
    assert not same_colours(slide, wikiart)
    assert same_colours(slide, wikiart, faded=True)
    assert same_colours(painting, Tone(0.07, (0.69, 0.02, 0.05)))  # a little livelier


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
        assert max(img.size) == 3600  # the copy, whole (kept up to 4000 px)
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
            assert max(img.size) == 3600
        # A photo has no other copies to look for.
        photo = service.library.upsert(
            Item(id="upload:1", kind=ItemKind.PHOTO, source="upload", source_id="1")
        )
        view = client.post(f"/api/library/items/{photo.id}/sharpen").json()
        assert view == {
            "status": "off",
            "sharper": None,
            "width": 0,
            "height": 0,
            "held_by": "",
            "held_at": "",
        }


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


# -- stand-ins: the work's own source gives no picture ---------------------------

MNK = "https://cdn-zbiory.mnk.pl/upload/multimedia/45/dd/own.jpg"
MNK_THUMB = "https://cdn-zbiory.mnk.pl/upload/cache/multimedia_big/45/dd/own.jpg"


def _mnk(service: FrameService, **kw: Any) -> Item:
    kw.setdefault("title", "Dama z gronostajem")
    kw.setdefault("artist", "Leonardo da Vinci")
    return service.library.upsert(
        Item(
            id="mnk:157417",
            kind=ItemKind.ARTWORK,
            source="mnk",
            source_id="157417",
            museum="Muzeum Narodowe w Krakowie",
            credit="Muzeum Narodowe w Krakowie, MNK XII-209",
            classification="Painting",
            image_url=MNK,
            thumb_url=MNK_THUMB,
            **kw,
        )
    )


def _leonardo(n: int, **kw: Any) -> Item:
    kw.setdefault("title", "Lady with an Ermine")
    kw.setdefault("artist", "Leonardo da Vinci")
    return _copy(n, **kw)


@pytest.fixture
def down(frame: Any) -> Any:
    """The fake web with the MNK's image server failing every original (as
    on 2026-11-08), its 1024 px thumbnail still there, and what is asked of
    Commons and of every source kept."""
    service, web, answer = frame
    service.images.sleep = lambda seconds: None
    web[MNK] = b""  # 502
    web[MNK_THUMB] = _jpeg(_print(3, (1024, 1365)))
    commons: list[Item] = []
    asked: dict[str, list[str]] = {"commons": [], "all": []}

    def search_commons(query: str, n: int) -> list[Item]:
        asked["commons"].append(query)
        return list(commons)

    def search_all(query: str, n: int) -> tuple[int, list[Item], list[str]]:
        asked["all"].append(query)
        return 0, [], []

    service.sharper.search_commons = search_commons
    service.sharper.search = search_all
    return service, web, answer, commons, asked


def test_a_copy_from_commons_stands_in_when_the_museum_gives_no_picture(down: Any) -> None:
    """Mateusz, 2026-11-08: the MNK's originals did not come; a card opened
    looks on Commons first and takes the first copy of the same picture,
    without asking the other sources."""
    service, web, _, commons, asked = down
    own = _mnk(service)
    copy = _leonardo(5, width=3000, height=4000)
    _offer(web, copy, _print(3, (3000, 4000)))
    other = _leonardo(6, title="Lady with an Ermine (detail)")
    _offer(web, other, _detail(_print(3, (3000, 4000))))
    commons[:] = [other, copy]
    assert service.sharper.soon(own).result(30) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "wmc:5"
    assert stored.sharper.stand_in
    assert asked == {"commons": ["Dama z gronostajem vinci"], "all": []}
    with Image.open(service.images.image_path(stored)) as img:
        assert max(img.size) == 4000  # the copy, as large as originals are kept


def test_a_work_known_to_be_fine_gets_a_stand_in_too(down: Any) -> None:
    """Its picture was good when the card was last opened; the original was
    pruned since, and its source fails now."""
    service, web, _, commons, _ = down
    own = _mnk(service)
    service.sharper._remember(own, "fine")
    assert service.sharper.status(own) == "fine"
    copy = _leonardo(5, width=3000, height=4000)
    _offer(web, copy, _print(3, (3000, 4000)))
    commons[:] = [copy]
    assert service.sharper.soon(own).result(30) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None and stored.sharper.stand_in


def test_other_sources_are_asked_when_commons_has_none(down: Any) -> None:
    service, web, _, _, asked = down
    own = _mnk(service)
    copy = _copy(8, title="Dama z gronostajem", artist="Leonardo da Vinci", width=2400, height=3200)
    copy = copy.model_copy(update={"id": "europeana:8", "source": "europeana"})
    _offer(web, copy, _print(3, (2400, 3200)))
    hits = [copy]
    service.sharper.search = lambda query, n: (asked["all"].append(query), (1, hits, []))[1]
    assert service.sharper.soon(own).result(30) == "found"
    assert asked["commons"] == ["Dama z gronostajem vinci"]
    assert asked["all"] == ["Dama z gronostajem vinci"]
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "europeana:8"


def test_nothing_found_is_not_looked_for_again_at_once(down: Any) -> None:
    service, _, _, _, asked = down
    own = _mnk(service)
    assert service.sharper.soon(own).result(30) == "none"
    assert service.sharper.soon(own).result(30) == "none"
    assert asked["commons"] == ["Dama z gronostajem vinci"]  # once
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is None


def test_a_source_that_works_needs_no_stand_in(down: Any) -> None:
    service, web, _, _, asked = down
    web[MNK] = _jpeg(_print(1, (3000, 2000)))
    own = _mnk(service)
    assert service.sharper.soon(own).result(30) == "fine"
    assert asked == {"commons": [], "all": []}


def test_without_a_thumbnail_only_a_certain_copy_stands_in(down: Any) -> None:
    """Nothing to compare with: the work's own Commons file (by its record)
    or a copy of the same title and artist will do, not a guess."""
    service, web, _, commons, _ = down
    web[MNK_THUMB] = b""
    own = _mnk(service)
    guess = _leonardo(5, width=3000, height=4000)  # another title: a guess
    _offer(web, guess, _print(3, (3000, 4000)))
    commons[:] = [guess]
    assert service.sharper.soon(own).result(30) == "none"
    certain = _leonardo(7, width=3000, height=4000)
    _offer(web, certain, _print(3, (3000, 4000)))
    service.sharper.commons_file = lambda item: "Lady with an Ermine.jpg"
    service.importer.commons_file = lambda name: certain  # type: ignore[method-assign]
    service.sharper._stood.clear()
    assert service.sharper.soon(own).result(30) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "wmc:7"


MARBURG = "German Documentation Center for Art History - Marburg Picture Index"
SLIDE = "http://www.bildindex.de/bilder/d/fmc652207"
SLIDE_THUMB = "https://api.europeana.eu/thumbnail/v2/url.json?uri=fmc652207&type=IMAGE"


def _faded(img: Image.Image) -> Image.Image:
    """An old colour slide of the painting: its yellow dye gone, the rest
    paler and bluer (Foto Marburg's van Goghs)."""
    r, g, b = img.split()
    r = r.point(lambda v: int(v * 0.55 + 70))
    g = g.point(lambda v: int(v * 0.6 + 80))
    b = b.point(lambda v: int(v * 0.3 + 175))
    return Image.merge("RGB", (r, g, b))


def _slide(service: FrameService, web: Web, credit: str = MARBURG) -> Item:
    """Van Gogh's olive grove in an art archive's faded slide, 1494 px."""
    web[SLIDE] = _jpeg(_faded(_print(1, (1494, 996))))
    web[SLIDE_THUMB] = _jpeg(_faded(_print(1, (600, 400))))
    return service.library.upsert(
        Item(
            id="europeana:199~item_2ZUY",
            kind=ItemKind.ARTWORK,
            source="europeana",
            source_id="199~item_2ZUY",
            museum="Europeana",
            title="Bathing Nymphs and Child",
            artist="Camille Corot",
            classification="paintings (visual works)",
            credit=credit,
            image_url=SLIDE,
            thumb_url=SLIDE_THUMB,
            width=1494,
            height=996,
        )
    )


def test_an_archive_slide_is_beaten_by_any_copy_as_large() -> None:
    slide = Quality(1494, 2.0)
    assert not Quality(1618, 2.0).better(slide)  # hardly larger
    assert Quality(1618, 2.0).better(slide, faded=True)
    assert Quality(1440, 2.0).better(slide, faded=True)  # about as large
    assert not Quality(1100, 2.0).better(slide, faded=True)
    faded = Tone(0.03, (0.75, -0.01, -0.03))
    true = Tone(0.07, (0.65, 0.01, 0.07))
    assert not same_colours(faded, true)
    assert same_colours(faded, true, faded=True)
    # A black-and-white plate stays out, faded slide or not.
    assert not same_colours(faded, Tone(0.003, (0.7, 0.0, 0.0)), faded=True)


def test_an_archive_slide_takes_a_copy_in_the_paintings_colours(frame: Any) -> None:
    """Foto Marburg's faded slide (Mateusz 2026-11-09): WikiArt's copy, as
    large and in the painting's own colours, takes its place."""
    service, web, answer = frame
    own = _slide(service, web)
    copy = _copy(5, width=1618, height=1079)
    _offer(web, copy, _print(1, (1618, 1079)))
    answer([copy])
    assert service.sharper.soon(own).result(60) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "wmc:5"


def test_another_sources_picture_keeps_its_colours(frame: Any) -> None:
    """The same pictures from a source that is no art archive: the copy in
    other colours does not take its place."""
    service, web, answer = frame
    own = _slide(service, web, credit="Nationalmuseum Sweden")
    copy = _copy(5, width=1618, height=1079)
    _offer(web, copy, _print(1, (1618, 1079)))
    answer([copy])
    assert service.sharper.soon(own).result(60) == "none"


def test_an_archive_slide_looked_at_before_is_looked_at_again(frame: Any) -> None:
    from frame_server.library.models import Note
    from frame_server.sharper import KIND, VERSION, version

    service, web, _ = frame
    own = _slide(service, web)
    when = "2026-11-08T10:00:00+00:00"
    service.library.save_note(
        Note(
            item_id=own.id,
            kind=KIND,
            model="",
            prompt_version=VERSION,
            data={"status": "none", "at": when},
        )
    )
    assert service.sharper.status(own) is None
    # The owner's own choice of the slide stands (once looked at for a
    # tile set: noted in the look's version).
    service.library.save_note(
        Note(
            item_id=own.id,
            kind=KIND,
            model="",
            prompt_version=version(own),
            data={"status": "kept", "at": when},
        )
    )
    assert service.sharper.status(own) == "fine"


def test_archive_slides_are_looked_at_once_after_the_update(frame: Any) -> None:
    """Not night by night (Mateusz 2026-11-09: "odpal już podmiany")."""
    from frame_server.sharper import ARCHIVES_KEY

    service, web, answer = frame
    service.library.set_state(ARCHIVES_KEY, 0)
    own = _slide(service, web)
    copy = _copy(5, width=1618, height=1079)
    _offer(web, copy, _print(1, (1618, 1079)))
    answer([copy])
    assert [i.id for i in service.sharper.archive_works()] == [own.id]
    assert service.sharper.archives_once() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert service.sharper.archive_works() == []
    service.sharper.search = lambda query, n: pytest.fail("looked again")
    assert service.sharper.archives_once() == 0  # once


def _archived(n: int, **kw: Any) -> Item:
    """Another art archive's photograph of the work (Foto Marburg's)."""
    kw.setdefault("width", 3600)
    kw.setdefault("height", 2400)
    return Item(
        id=f"europeana:199~slide{n}",
        kind=ItemKind.ARTWORK,
        source="europeana",
        source_id=f"199~slide{n}",
        museum="Europeana",
        title="Bathing Nymphs and Child",
        artist="Camille Corot",
        classification="paintings (visual works)",
        credit=MARBURG,
        image_url=f"http://www.bildindex.de/bilder/d/fmc{n}",
        thumb_url=f"http://www.bildindex.de/bilder/t/fmc{n}",
        **kw,
    )


def test_an_archive_photograph_is_never_a_copy(frame: Any) -> None:
    """Mateusz 2026-11-09: two van Goghs from Foto Marburg took another
    Marburg slide, as faded, larger by half."""
    service, web, answer = frame
    own = _own(service)
    slide = _archived(7)
    _offer(web, slide, _print(1, (3600, 2400)))
    answer([slide])
    assert service.sharper.soon(own).result(60) == "none"
    assert service.sharper.candidates(own) == []


def test_the_largest_copy_that_passes_is_taken(frame: Any) -> None:
    """Not the first: a slightly larger one must not shut out Commons'."""
    service, web, answer = frame
    own = _slide(service, web)
    small, large = _copy(5, width=1618, height=1079), _copy(6, width=3600, height=2400)
    _offer(web, small, _print(1, (1618, 1079)))
    _offer(web, large, _print(1, (3600, 2400)))
    answer([small, large])
    service.sharper.candidates = lambda item, commons=True: [small, large]  # as found
    assert service.sharper.soon(own).result(60) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "wmc:6"


def test_a_copy_still_too_small_is_looked_past_again(frame: Any) -> None:
    from datetime import timedelta

    from frame_server.sharper import WEAK_AGAIN

    service, web, answer = frame
    own = _slide(service, web)
    small = _copy(5, width=1618, height=1079)
    _offer(web, small, _print(1, (1618, 1079)))
    answer([small])
    assert service.sharper.soon(own).result(60) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and service.sharper.status(stored) == "found"
    # A day on, a sharper one turned up: it takes the small one's place.
    now = service.sharper.clock()
    service.sharper.clock = lambda: now + WEAK_AGAIN + timedelta(minutes=1)
    assert service.sharper.status(stored) is None
    large = _copy(6, width=3600, height=2400)
    _offer(web, large, _print(1, (3600, 2400)))
    answer([large])
    assert service.sharper.soon(stored).result(60) == "found"
    again = service.library.get(own.id)
    assert again is not None and again.sharper is not None
    assert again.sharper.item_id == "wmc:6"
    # As large as the frame wants: left alone.
    assert service.sharper.status(again) == "found"
    service.sharper.clock = lambda: now + WEAK_AGAIN * 30
    assert service.sharper.status(again) == "found"


def test_archive_copies_taken_before_are_let_go_once(frame: Any) -> None:
    from frame_server.sharper import ARCHIVES_KEY

    service, web, answer = frame
    service.library.set_state(ARCHIVES_KEY, 1)
    own = _own(service)
    taken = SharperCopy(
        url="http://www.bildindex.de/bilder/d/fmc7",
        item_id="europeana:199~slide7",
        source="europeana",
        width=2400,
        height=1600,
    )
    service.library.update(own.id, sharper=taken)
    chosen = service.library.upsert(
        _copy(9, title="Another", artist="Somebody").model_copy(
            update={"sharper": taken.model_copy(update={"chosen": True})}
        )
    )
    copy = _copy(5)
    _offer(web, copy, _print(1, (3600, 2400)))
    answer([copy])
    assert service.sharper.archives_once() == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == "wmc:5"
    # The owner's own pick stays.
    kept = service.library.get(chosen.id)
    assert kept is not None and kept.sharper is not None and kept.sharper.chosen


def test_an_archive_photograph_stands_for_a_work_last_even_when_kept() -> None:
    """Mateusz 2026-11-09: a heart or a playlist says nothing of the picture."""
    from frame_server.library.duplicates import Works

    museum = Item(
        id="aic:1",
        kind=ItemKind.ARTWORK,
        source="aic",
        source_id="1",
        title="Bathing Nymphs and Child",
        artist="Camille Corot",
        year=1870,
        pooled=True,
    )
    slide = _archived(7, year=1870, pooled=False)
    works = Works([slide, museum])
    assert works.best(slide) is not None and works.best(slide).id == "aic:1"  # type: ignore[union-attr]


def _tiled(frame: Any) -> tuple[FrameService, Web, Item, Item]:
    """A work with a good picture of its own, and Commons' file of it in a
    tile set."""
    service, web, _ = frame
    web[OWN] = _jpeg(_print(1, (2400, 1600)), 90)
    own = _own(service)
    copy = _copy(8, width=3840, height=2560)
    _offer(web, copy, _print(1, (3840, 2560)))
    service.sharper.tiled_copies = lambda item: [copy]
    service.sharper.is_tiled = lambda item_id: item_id == copy.id
    return service, web, own, copy


def test_a_tile_set_takes_the_place_of_a_good_picture(frame: Any) -> None:
    """Mateusz 2026-11-09: Bosch's and Rembrandt's tile sets on Commons,
    taken by themselves, for the full-screen viewer's deeper zoom."""
    service, _, own, copy = _tiled(frame)
    assert service.sharper.soon(own).result(60) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == copy.id
    assert service.sharper.shows_tiles(stored)


def test_a_tile_set_beats_the_owners_pick_too(frame: Any) -> None:
    """Over the museum's picture kept by hand, once (Mateusz 2026-11-09:
    "ten w ultra-rozdzielczości będzie po prostu lepszy")."""
    from frame_server.library.models import Note
    from frame_server.sharper import KIND

    service, _, own, copy = _tiled(frame)
    service.library.save_note(
        Note(
            item_id=own.id,
            kind=KIND,
            model="",
            prompt_version="sharper-1",
            data={"status": "kept", "at": "2026-11-08T10:00:00+00:00"},
        )
    )
    assert service.sharper.status(own) is None  # looked at once more
    assert service.sharper.soon(own).result(60) == "found"
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == copy.id


def test_the_owners_pick_stands_without_a_tile_set(frame: Any) -> None:
    from frame_server.library.models import Note
    from frame_server.sharper import KIND

    service, _, own, _ = _tiled(frame)
    service.sharper.tiled_copies = lambda item: []
    service.library.save_note(
        Note(
            item_id=own.id,
            kind=KIND,
            model="",
            prompt_version="sharper-1",
            data={"status": "kept", "at": "2026-11-08T10:00:00+00:00"},
        )
    )
    assert service.sharper.soon(own).result(60) == "fine"
    note = service.library.note(own.id, KIND)
    assert note is not None and note.data["status"] == "kept"
    assert service.sharper.status(own) == "fine"


def test_the_catalogues_works_of_tile_sets_take_them_once(frame: Any) -> None:
    from frame_server.sharper import TILES_KEY

    service, _, own, copy = _tiled(frame)
    service.sharper.tiled_copies = lambda item: pytest.fail("found by its file")
    service.library.set_state(TILES_KEY, 0)
    assert service.sharper.tiled_once(lambda: [copy]) == 1
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is not None
    assert stored.sharper.item_id == copy.id
    assert service.sharper.tiled_once(lambda: pytest.fail("once")) == 0
