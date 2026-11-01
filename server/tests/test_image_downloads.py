"""Thumbnail downloads: throttled answers are tried again, a few per host."""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

from frame_server.library.images import GONE_FOR, Gone, HostGate, ImageCache
from frame_server.library.models import Item


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 80, 40)).save(out, "JPEG")
    return out.getvalue()


def _item(n: int, host: str = "upload.wikimedia.org") -> Item:
    return Item(
        id=f"commons:{n}",
        source="commons",
        source_id=str(n),
        title=f"Work {n}",
        thumb_url=f"https://{host}/thumb/{n}.jpg",
    )


def test_throttled_thumbnail_is_tried_again(tmp_path: Path) -> None:
    answers = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, content=_jpeg()),
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return answers.pop(0)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    waits: list[float] = []
    cache.sleep = waits.append
    path = cache.ensure_thumb(_item(1))
    assert path.is_file()
    assert len(seen) == 2
    assert waits == [1.0]


def test_gives_up_after_a_few_tries(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    cache.sleep = lambda _: None
    with pytest.raises(httpx.HTTPStatusError):
        cache.ensure_thumb(_item(2))
    assert calls == 3
    assert not cache.thumb_path(_item(2)).exists()


def test_missing_thumbnail_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(Gone):
        cache.ensure_thumb(_item(3))
    assert calls == 1


@pytest.mark.parametrize(("host", "limit"), [("upload.wikimedia.org", 2), ("www.artic.edu", 4)])
def test_parallel_downloads_per_host_are_limited(tmp_path: Path, host: str, limit: int) -> None:
    running = 0
    peak = 0
    lock = threading.Lock()
    picture = _jpeg()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return httpx.Response(200, content=picture)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    threads = [
        threading.Thread(target=cache.ensure_thumb, args=(_item(n, host),)) for n in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == limit
    assert len(list(cache.thumbs.glob("*.jpg"))) == 10


def test_what_the_owner_looks_at_goes_first() -> None:
    gate = HostGate(limit=1)
    order: list[str] = []

    def download(name: str, urgent: bool) -> None:
        with gate.turn(urgent):
            order.append(name)

    with gate.turn():  # a thumbnail on its way
        waiting = [
            threading.Thread(target=download, args=("thumbnail", False)),
            threading.Thread(target=download, args=("card", True)),
        ]
        for t in waiting:
            t.start()
            time.sleep(0.05)  # in line in this order
    for t in waiting:
        t.join()
    assert order == ["card", "thumbnail"]


def test_what_the_owner_looks_at_has_places_of_its_own() -> None:
    gate = HostGate(limit=1, extra=1)
    with gate.turn():
        done = threading.Event()

        def card() -> None:
            with gate.turn(urgent=True):
                done.set()

        threading.Thread(target=card).start()
        assert done.wait(1)  # without waiting for the thumbnail


def _europeana(n: int) -> Item:
    return Item(
        id=f"europeana:2021672~work_{n}",
        source="europeana",
        source_id=f"2021672~work_{n}",
        title=f"Work {n}",
        image_url=f"https://www.mauritshuis.nl/media/{n}_repro.jpg",
        thumb_url=f"https://api.europeana.eu/thumbnail/v2/url.json?uri=x{n}&size=w400",
    )


def test_refused_original_comes_through_the_mirror(tmp_path: Path) -> None:
    from frame_server.library.museums import europeana_mirrors

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "www.mauritshuis.nl":  # Cloudflare's "verify you are human"
            return httpx.Response(403, html="<title>Attention Required!</title>")
        return httpx.Response(200, content=_jpeg())

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    cache.mirrors["europeana"] = europeana_mirrors
    assert cache.ensure_image(_europeana(1)).is_file()
    assert seen == ["www.mauritshuis.nl", "proxy.europeana.eu"]


def test_original_refused_everywhere_is_unavailable_for_a_while(tmp_path: Path) -> None:
    from frame_server.library.images import FAILED_FOR, Unavailable

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if "thumbnail" in str(request.url):
            return httpx.Response(200, content=_jpeg())
        return httpx.Response(200, html="<p>Verify that you are a human</p>")  # not a picture

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    now = [1000.0]
    cache.clock = lambda: now[0]
    item = _europeana(2)
    with pytest.raises(Unavailable):
        cache.ensure_image(item)
    assert cache.unavailable(item)
    calls.clear()
    with pytest.raises(Unavailable):
        cache.ensure_image(item)  # not asked again
    assert calls == []
    # The app still gets something to show: the thumbnail.
    path, original = cache.picture(item)
    assert path == cache.thumb_path(item) and not original
    now[0] += FAILED_FOR + 1
    assert not cache.unavailable(item)


COMMONS_ORIGINAL = (
    "https://upload.wikimedia.org/wikipedia/commons/4/4c/"
    "Le_Gar%C3%A7on_au_gilet_rouge%2C_par_Paul_C%C3%A9zanne%2C_National_Gallery_of_Art.jpg"
)


def _commons_scan(width: int) -> Item:
    return Item(
        id="wmc:149057",
        source="wmc",
        source_id="149057",
        title="Le Garçon au gilet rouge",
        image_url=COMMONS_ORIGINAL,
        thumb_url=COMMONS_ORIGINAL.replace("/4/4c/", "/thumb/4/4c/") + "/500px-x.jpg",
        width=width,
        height=width * 5 // 4,
    )


def test_a_huge_commons_scan_comes_as_commons_rendition(tmp_path: Path) -> None:
    """A 100 MB, 200-megapixel museum scan: Commons' 3840 px copy is
    downloaded instead, for the card, the preview and the frame alike."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_jpeg())

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    # As the Commons API gives its links now.
    linked = COMMONS_ORIGINAL + "?utm_source=commons.wikimedia.org&utm_content=original"
    huge = _commons_scan(12560).model_copy(update={"image_url": linked})
    assert cache.ensure_image(huge).is_file()
    assert len(seen) == 1
    assert "/thumb/4/4c/" in seen[0] and "/3840px-" in seen[0]
    # A file the frame's size is downloaded as it is.
    seen.clear()
    small = _commons_scan(2536).model_copy(update={"id": "wmc:149054", "source_id": "149054"})
    cache.ensure_image(small)
    assert seen == [COMMONS_ORIGINAL]


def test_a_picture_too_large_to_open_falls_back_to_the_thumbnail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pillow refuses to open it (a decompression bomb to it): the preview
    and the full screen get the thumbnail instead of an error."""
    from frame_server.library.images import Unavailable

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)  # every picture "too large"
    big = _jpeg()
    out = io.BytesIO()
    Image.new("RGB", (8, 6), (200, 80, 40)).save(out, "JPEG")
    small = out.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=small if "500px" in str(request.url) else big)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    item = _commons_scan(3000)
    path, original = cache.picture(item, urgent=True)
    assert path == cache.thumb_path(item) and not original
    with pytest.raises(Unavailable):  # not downloaded again for a while
        cache.ensure_image(item)


def test_host_down_is_not_remembered(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    cache.sleep = lambda _: None
    with pytest.raises(httpx.HTTPStatusError):
        cache.ensure_image(_item(5))
    assert not cache.unavailable(_item(5))


def _aic(n: int) -> Item:
    iiif = f"https://www.artic.edu/iiif/2/id{n}"
    return Item(
        id=f"aic:{n}",
        source="aic",
        source_id=str(n),
        title=f"Work {n}",
        image_url=f"{iiif}/full/1686,/0/default.jpg",
        thumb_url=f"{iiif}/full/600,/0/default.jpg",
    )


def _challenge(request: httpx.Request) -> httpx.Response:
    """Cloudflare's "Just a moment..." page, as the AIC's image server gives it."""
    return httpx.Response(
        403,
        headers={"server": "cloudflare", "cf-mitigated": "challenge", "content-type": "text/html"},
        text="<title>Just a moment...</title>",
        request=request,
    )


def test_a_thumbnail_refused_by_the_museum_comes_from_a_copy(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "www.artic.edu":
            return _challenge(request)
        return httpx.Response(200, content=_jpeg())

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    cache.mirrors["aic"] = lambda item, thumb: [
        f"https://commons.wikimedia.org/{item.source_id}?thumb={thumb}"
    ]
    assert cache.ensure_thumb(_aic(1)).is_file()
    assert seen == ["www.artic.edu", "www.artic.edu", "commons.wikimedia.org"]
    assert not cache.gone("aic:1")


def test_a_bot_wall_does_not_make_a_work_gone(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _challenge(request)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        cache.ensure_thumb(_aic(2))
    assert not isinstance(caught.value, Gone)
    assert not cache.gone("aic:2")


def test_a_work_with_no_picture_anywhere_is_gone_for_a_while(tmp_path: Path) -> None:
    answer = [httpx.Response(404)]

    def handler(request: httpx.Request) -> httpx.Response:
        return answer[0]

    def make() -> ImageCache:
        cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
        cache.wall = lambda: now[0]
        return cache

    now = [1_000_000.0]
    cache = make()
    item = _aic(3)
    with pytest.raises(Gone):
        cache.ensure_thumb(item)
    assert cache.gone(item.id) and cache.unavailable(item)
    # Remembered across a restart, and left out of the frame's queue.
    again = make()
    assert again.gone(item.id)
    with pytest.raises(Gone):
        again.picture(item)
    # Asked again after a while; a picture found ends it.
    now[0] += GONE_FOR + 1
    assert not again.gone(item.id)
    answer[0] = httpx.Response(200, content=_jpeg())
    assert again.ensure_thumb(item).is_file()
    assert not again.gone(item.id)


def test_the_commons_copy_is_found_through_wikidata() -> None:
    from frame_server.library.wikidata import CommonsCopies

    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        asked.append(params.get("action", ""))
        if params.get("action") == "query":
            hits = [{"title": "Q1"}] if "P4610=3" in params["srsearch"] else []
            return httpx.Response(200, json={"query": {"search": hits}})
        file = {"mainsnak": {"datavalue": {"value": "Corot - Bathing Nymphs.jpg"}}}
        return httpx.Response(200, json={"entities": {"Q1": {"claims": {"P18": [file]}}}})

    copies = CommonsCopies(lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    assert copies(_aic(3), True) == [
        "https://commons.wikimedia.org/wiki/Special:FilePath/Corot%20-%20Bathing%20Nymphs.jpg?width=960"
    ]
    assert copies(_aic(3))[0].endswith("?width=2560")  # remembered: not asked again
    assert asked == ["query", "wbgetentities"]
    assert copies(_aic(4)) == []  # Wikidata has no copy
    assert copies(_aic(4)) == []
    assert asked == ["query", "wbgetentities", "query"]


def test_works_with_no_picture_are_left_out_of_lists(service) -> None:
    from fastapi.testclient import TestClient

    from frame_server.web import create_app
    from frame_server.web.library_api import remote_items

    app = create_app(service.settings)
    svc = app.state.service
    gone, kept = _aic(5), _aic(6)
    svc.images._mark_gone(gone)
    assert [r.item.id for r in remote_items(svc, [gone, kept])] == [kept.id]
    with TestClient(app) as client:
        svc.library.upsert(gone)
        svc.library.upsert(kept)
        page = client.get("/api/library/items", params={"source": "aic"}).json()
        assert [i["id"] for i in page["items"]] == [kept.id] and page["total"] == 1
        # The app is told, and leaves the tile out at once.
        assert client.get(f"/api/library/items/{gone.id}/thumb").status_code == 410
