"""Suggestions, smart-playlist pools and the catalogue of museum works."""

from __future__ import annotations

import random
import time
from collections.abc import Iterator

import httpx
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.library import Item, ItemKind, Playlist, PlaylistKind, PlaylistRules
from frame_server.library.museums import MUSEUMS, Discovery, Museum
from frame_server.player import MIGRATED_PLAYLIST, POOL_SIZE

COLOURS = [(200, 30, 30), (30, 60, 180), (240, 200, 30), (30, 140, 60)]


def _picture(n: int) -> bytes:
    """Bold stripes on paper: good on e-paper, with ``n`` choosing the order."""
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (320, 240), (245, 240, 230))
    draw = ImageDraw.Draw(img)
    for i, colour in enumerate([*COLOURS[n:], *COLOURS[:n], (20, 20, 20)]):
        draw.rectangle((i * 64, 40, i * 64 + 50, 200), fill=colour)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _fake(key: str) -> type[Museum]:
    class Fake(Museum):
        name = key.upper()

        def _work(self, n: int, artist: str) -> Item:
            url = f"https://{key}.invalid/{n % len(COLOURS)}.jpg"
            return self._item(
                f"{artist}-{n}",
                artist=artist,
                title=f"{artist} {n}",
                image_url=url,
                thumb_url=url,
                classification="Painting",
            )

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            start = (page - 1) * limit
            return 40, [self._work(n, query) for n in range(start, min(start + limit, 40))]

        def fetch(self, source_id: str) -> Item | None:
            artist, _, n = source_id.rpartition("-")
            return self._work(int(n), artist)

        def random_draw(self, spec: Discovery, rng: random.Random) -> Iterator[Item]:
            return iter([self._work(n, f"Random {spec.kind}") for n in range(60)])

    Fake.key = key
    return Fake


@pytest.fixture
def museums(service, monkeypatch):
    for key in ("aic", "cma", "met", "rijks", "wmc"):
        monkeypatch.setitem(MUSEUMS, key, _fake(key))
    pictures = [_picture(n) for n in range(len(COLOURS))]

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pictures[int(request.url.path[1])])

    service.images.http = lambda: httpx.Client(transport=httpx.MockTransport(answer))
    return service


def _wait(job) -> None:
    deadline = time.monotonic() + 30
    while not job.finished and time.monotonic() < deadline:
        time.sleep(0.05)
    assert job.finished and not job.error, job.error


def _liked(service, artist: str) -> Item:
    item = service.library.upsert(
        Item(
            id=f"aic:{artist}-0",
            source="aic",
            source_id=f"{artist}-0",
            artist=artist,
            favorite=True,
            image_url="https://aic.invalid/0.jpg",
            thumb_url="https://aic.invalid/0.jpg",
        )
    )
    return service.importer.add(item)


def test_suggestions_follow_the_owners_taste(museums) -> None:
    service = museums
    player = service.player
    liked = _liked(service, "Ala")
    assert player.taste() == ["Ala"]

    job = player.top_up()  # the catalogue has one work: museums are asked
    assert job is not None
    _wait(job)
    picked = player.suggestions()
    assert len(picked) == POOL_SIZE and picked[0].id == liked.id
    assert all(i.pooled for i in picked[1:])
    assert sum(i.artist == "Ala" for i in picked) > 1
    # The rotation plays Suggestions now, with the owner's own works.
    own = service.importer.add_upload(jpeg_bytes((200, 40, 40)), kind=ItemKind.OWN)
    assert {i.id for i in player.candidates()} == {i.id for i in picked} | {own.id}
    assert player.top_up() is None  # enough for now

    # Keeping a picked work takes it out of the server's hands.
    assert not service.importer.save(picked[1].id).pooled


def test_suggestions_come_from_the_catalogue_first(museums) -> None:
    service = museums
    player = service.player
    job = player.grow_catalogue()
    assert job is not None
    _wait(job)
    assert service.library.count() >= POOL_SIZE

    assert player.top_up() is None  # picked locally, no museum asked
    assert len(player.suggestions()) == POOL_SIZE


def test_smart_playlist_pool_is_topped_up(museums) -> None:
    service = museums
    playlist = service.library.save_playlist(
        Playlist(name="Ola", rules=PlaylistRules(artists=["Ola"]))
    )
    settings = service.player.settings
    settings.playlist_id = playlist.id
    service.player.save_settings(settings)

    job = service.player.top_up()
    assert job is not None
    _wait(job)
    items = service.library.playlist_items(playlist)
    assert len(items) == POOL_SIZE and all(i.artist == "Ola" and i.pooled for i in items)

    favourites = service.library.save_playlist(
        Playlist(name="Serca", rules=PlaylistRules(favorites_only=True))
    )
    settings.playlist_id = favourites.id
    service.player.save_settings(settings)
    assert service.player.top_up() is None  # museums cannot add hearts


def test_catalogue_stays_within_its_size(museums) -> None:
    service = museums
    player = service.player
    _wait(player.grow_catalogue())
    kept = _liked(service, "Ala")
    shown = service.library.query(PlaylistRules(kept_only=False))[1][-1]
    service.library.record_shown(shown.id)
    size = service.images.thumbs_size()

    service.settings.catalogue_mb = 0  # nothing spare may stay
    assert player.trim_catalogue() > 0
    left = {i.id for i in service.library.query()[1]}
    assert left == {kept.id, shown.id}
    assert service.images.thumbs_size() < size
    assert player.grow_catalogue() is None  # disabled


def test_old_library_is_kept_as_a_playlist(service) -> None:
    own = service.importer.add_upload(jpeg_bytes((200, 40, 40)), kind=ItemKind.OWN)
    service.library.upsert(Item(id="aic:9", source="aic", source_id="9", pooled=True))
    playlist = service.player.migrate_library()
    assert playlist is not None and playlist.name == MIGRATED_PLAYLIST
    assert playlist.kind == PlaylistKind.MANUAL and playlist.item_ids == [own.id]
    assert service.player.migrate_library() is None  # once


def test_discover_endpoints(museums) -> None:
    from frame_server.web import create_app, discover_api

    service = museums
    app = create_app(service.settings)
    app.state.service = service
    discover_api._theme_rows.clear()
    with TestClient(app) as client:
        themes = client.get("/api/themes").json()
        assert themes and {"key", "name", "description"} <= themes[0].keys()
        page = client.get(f"/api/themes/{themes[0]['key']}", params={"page": 1}).json()
        assert page["items"] and page["more"]
        assert client.get("/api/themes/nope").status_code == 404

        rows = client.get("/api/suggestions").json()
        assert [r["key"] for r in rows] == ["theme"]  # nothing picked yet

        browse = client.get("/api/browse", params={"kind": "print"}).json()
        assert browse["total"] == 0  # the fakes cannot filter

        catalogue = client.get("/api/library/items", params={"kept": True}).json()
        assert catalogue["total"] == 0


def test_kept_filter() -> None:
    from frame_server.library.repo import matches

    picked = Item(id="a:1", source="a", source_id="1", pooled=True)
    assert not matches(picked, PlaylistRules(kept_only=True))
    assert matches(picked.model_copy(update={"favorite": True}), PlaylistRules(kept_only=True))
    assert matches(picked, PlaylistRules())
