"""Originals of Favourites and manual/album playlists kept on the server
(kept.py): downloaded just after a work is kept, and at night what is still
missing, gently for the museums."""

from __future__ import annotations

import threading
import time
from datetime import timedelta

import httpx
import pytest
from conftest import jpeg_bytes

from frame_server import kept, night
from frame_server.kept import REFUSED_FOR, KeptOriginals
from frame_server.library import Item, Playlist, PlaylistKind
from frame_server.night import Night, tasks


@pytest.fixture
def museum(service, monkeypatch):
    """Museums at ``ok.invalid`` (answers), ``busy.invalid`` (429) and
    ``gone.invalid`` (404); the hosts asked, in order."""
    monkeypatch.setattr(kept, "PAUSE", 0.0)
    monkeypatch.setattr(night, "_last_used", time.monotonic() - 3600)
    service.images.mirrors.clear()
    service.images.sleep = lambda _s: None
    picture = jpeg_bytes((200, 30, 30))
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        asked.append(f"{host}{request.url.path}")
        if host == "busy.invalid":
            return httpx.Response(429)
        if host == "gone.invalid":
            return httpx.Response(404)
        return httpx.Response(200, content=picture)

    service.images.http = lambda: httpx.Client(transport=httpx.MockTransport(answer))
    service.asked = asked
    return service


def _work(service, name: str, host: str = "ok.invalid", **fields) -> Item:
    url = f"https://{host}/{name}.jpg"
    return service.library.upsert(
        Item(
            id=f"met:{name}",
            source="met",
            source_id=name,
            title=name,
            image_url=url,
            thumb_url=url,
            **fields,
        )
    )


def _night(seconds: float = 30.0) -> Night:
    return Night(threading.Event(), time.monotonic() + seconds)


def _playlist(service, *ids: str) -> Playlist:
    return service.library.save_playlist(
        Playlist(name="Moje", kind=PlaylistKind.MANUAL, item_ids=list(ids))
    )


def test_the_night_downloads_what_is_kept_and_nothing_else(museum) -> None:
    service = museum
    liked = _work(service, "liked")
    service.library.set_favorite("owner", liked.id, True)
    listed = _work(service, "listed")
    _playlist(service, listed.id)
    browsed = _work(service, "browsed")  # in the catalogue, kept by nobody
    hidden = _work(service, "hidden", excluded=True)
    service.library.set_favorite("owner", hidden.id, True)

    assert service.kept.at_night(_night()) == 2
    images = service.images
    assert images.has_image(liked) and images.has_image(listed)
    assert not images.has_image(browsed) and not images.has_image(hidden)
    assert service.asked == ["ok.invalid/liked.jpg", "ok.invalid/listed.jpg"]  # hearts first
    assert service.kept.at_night(_night()) == 0  # all here: nothing asked again
    assert len(service.asked) == 2


def test_a_host_that_turns_us_away_is_left_for_the_night(museum) -> None:
    service = museum
    for name, host in (("a", "busy.invalid"), ("b", "busy.invalid"), ("c", "ok.invalid")):
        service.library.set_favorite("owner", _work(service, name, host).id, True)

    assert service.kept.at_night(_night()) == 1
    busy = [a for a in service.asked if a.startswith("busy.invalid")]
    assert set(busy) == {"busy.invalid/a.jpg"}  # tried (with retries), b not asked
    assert service.images.has_image(service.library.get("met:c"))


def test_a_refused_original_is_not_asked_for_a_month(museum) -> None:
    service = museum
    work = _work(service, "lost", "gone.invalid")
    service.library.set_favorite("owner", work.id, True)
    keeper = service.kept
    assert keeper.at_night(_night()) == 0
    assert keeper.refused(work.id)
    asked = len(service.asked)
    service.images._failed.clear()  # the next night: the 30 min memo long gone
    assert keeper.at_night(_night()) == 0
    assert len(service.asked) == asked
    later = keeper.now() + REFUSED_FOR + timedelta(days=1)
    keeper.now = lambda: later
    assert not keeper.refused(work.id)
    assert work.id in [i.id for i in keeper.missing()]


def test_downloading_stops_short_of_the_originals_limit(museum, monkeypatch) -> None:
    service = museum
    for name in "abc":
        service.library.set_favorite("owner", _work(service, name).id, True)
    keeper: KeptOriginals = service.kept
    monkeypatch.setattr(keeper, "room", lambda: 1)  # room for one more
    assert keeper.at_night(_night()) == 1


def test_a_new_favourite_is_downloaded_at_once(museum) -> None:
    service = museum
    work = _work(service, "new")
    _playlist(service)  # an empty one: nothing to do
    service.library.set_favorite("owner", work.id, True)
    service.kept.soon([work.id, "met:unknown"])
    deadline = time.monotonic() + 10
    while not service.images.has_image(work) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert service.images.has_image(work)


def test_kept_originals_are_the_nights_last_task(service) -> None:
    assert tasks(service)[-1].name == "kept originals"


def _until(check, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while not check() and time.monotonic() < deadline:
        time.sleep(0.02)
    return check()


def test_a_heart_or_a_playlist_in_the_app_downloads_the_original(service, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    picture = jpeg_bytes((40, 40, 200))
    svc.images.mirrors.clear()
    svc.images.http = lambda: httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=picture))
    )
    with TestClient(app) as client:  # works added once the app has started
        liked, listed = _work(svc, "liked"), _work(svc, "listed")
        playlist = _playlist(svc)
        client.patch(f"/api/library/items/{liked.id}", json={"favorite": True})
        client.post(f"/api/playlists/{playlist.id}/items", json={"item_ids": [listed.id]})
        assert _until(lambda: svc.images.has_image(liked) and svc.images.has_image(listed))
