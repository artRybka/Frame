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
from PIL import Image

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


def _cut(service, item: Item, size: tuple[int, int] = (2560, 1920)) -> None:
    """``item``'s original as it was kept until 1.145.32: cut to 2560 px."""
    path = service.images.image_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg_bytes((30, 30, 200), size))


def test_originals_cut_to_the_old_limit_are_had_again_larger(museum) -> None:
    """Mateusz 2026-11-11: originals up to 4000 px, not 2560. Those here
    were cut: the kept works' first, then the ones he looked at, a night at
    a time; a source that has no more is not asked a third time."""
    service = museum
    large, same = jpeg_bytes((200, 30, 30), (4800, 3600)), jpeg_bytes((200, 30, 30), (2560, 1920))

    def answer(request: httpx.Request) -> httpx.Response:
        service.asked.append(request.url.path)
        return httpx.Response(200, content=same if "small" in request.url.path else large)

    service.images.http = lambda: httpx.Client(transport=httpx.MockTransport(answer))
    liked, small = _work(service, "liked"), _work(service, "small")
    seen, whole = _work(service, "seen"), _work(service, "whole")
    for item in (liked, small):
        service.library.set_favorite("owner", item.id, True)
    for item in (liked, small, seen):
        _cut(service, item)
    _cut(service, whole, (1800, 1350))  # all its source had: not cut
    images = service.images

    assert service.kept.at_night(_night()) == 2
    assert service.asked == ["/liked.jpg", "/small.jpg", "/seen.jpg"]  # the kept first
    for item, side in ((liked, 4000), (small, 2560), (seen, 4000), (whole, 1800)):
        with Image.open(images.image_path(item)) as kept_here:
            assert max(kept_here.size) == side
    assert images.known_size(liked) == (4800, 3600)
    # The next night nothing is left, and the originals are not looked through again.
    assert service.kept.at_night(_night()) == 0 and len(service.asked) == 3
    _cut(service, seen)
    assert service.kept.at_night(_night()) == 0 and len(service.asked) == 3


def test_larger_originals_stop_at_the_originals_limit(museum, monkeypatch) -> None:
    """The kept works' originals grow into the room of the others (pruned
    first), never into one another's: a full cache would lose Favourites."""
    service = museum
    large = jpeg_bytes((200, 30, 30), (4800, 3600))
    service.images.http = lambda: httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=large))
    )
    liked, seen = _work(service, "liked"), _work(service, "seen")
    service.library.set_favorite("owner", liked.id, True)
    for item in (liked, seen):
        _cut(service, item)
    keeper: KeptOriginals = service.kept
    monkeypatch.setattr(keeper, "room", lambda: 0)  # full, of others' originals
    assert keeper.at_night(_night()) == 1
    sides = []
    for item in (liked, seen):
        with Image.open(service.images.image_path(item)) as kept_here:
            sides.append(max(kept_here.size))
    assert sides == [4000, 2560]
    _cut(service, liked)
    monkeypatch.setattr(keeper, "kept_room", lambda kept: 0)  # full of kept ones
    assert keeper.at_night(_night()) == 0


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


def test_a_work_that_fails_oddly_does_not_end_the_downloads(museum, monkeypatch) -> None:
    """2026-11-06: an unexpected error ended the thread with its flag still
    set, and no kept work was downloaded again until a restart."""
    service = museum
    odd, fine = _work(service, "odd"), _work(service, "fine")
    ensure = service.images.ensure_image

    def failing(item: Item, *args, **kwargs):
        if item.id == odd.id:
            raise RuntimeError("odd")
        return ensure(item, *args, **kwargs)

    monkeypatch.setattr(service.images, "ensure_image", failing)
    service.kept.soon([odd.id, fine.id])
    deadline = time.monotonic() + 10
    while not service.images.has_image(fine) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert service.images.has_image(fine)


def test_kept_originals_come_after_the_tidying_before_the_rijks_index(service) -> None:
    names = [t.name for t in tasks(service)]
    assert names.index("kept originals") > names.index("audit")
    assert names[-1] == "rijks"  # whatever time the night has left


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
