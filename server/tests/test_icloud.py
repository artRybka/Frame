from __future__ import annotations

import io
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.library import AlbumOrder, AlbumSource, Playlist, PlaylistKind
from frame_server.library.icloud import album_token, partition_host, sync_album
from frame_server.library.models import ItemKind
from frame_server.player import SETTINGS_KEY, album_order

URL = "https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC"
OTHER = "https://www.icloud.com/sharedalbum/#B1bbbbbbbbbbbb"
CONTENT_HOST = "cvws.icloud-content.com"


def _jpeg(size: tuple[int, int] = (400, 300), exif: bool = False) -> bytes:
    img = Image.new("RGB", size, (40, 90, 160))
    data = Image.Exif()
    if exif:
        data[0x0132] = "2025:08:14 18:32:00"  # DateTime
        data[0x8825] = {1: "N", 2: (54.0, 36.0, 0.0), 3: "E", 4: (18.0, 48.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=data)
    return buf.getvalue()


def _photo(guid: str, taken: str, shared: str, caption: str = "") -> dict:
    return {
        "photoGuid": guid,
        "caption": caption,
        "dateCreated": taken,
        "batchDateCreated": shared,
        "contributorFullName": "Ala Kowalska",
        "mediaAssetType": "image",
        "derivatives": {
            "342": {"checksum": f"{guid}-small", "width": "342", "height": "256"},
            "2049": {"checksum": f"{guid}-big", "width": "2048", "height": "1536"},
        },
    }


class FakeICloud:
    """Shared albums by token, with the web API's redirect and signed links."""

    def __init__(self) -> None:
        self.albums: dict[str, tuple[str, list[dict]]] = {}
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.host}{request.url.path}")
        path = request.url.path
        token = path.strip("/").split("/")[0]
        if path.endswith("webstream") and request.url.host != "p99-sharedstreams.icloud.com":
            return httpx.Response(330, json={"X-Apple-MMe-Host": "p99-sharedstreams.icloud.com"})
        if token not in self.albums and "sharedstreams" in path:
            return httpx.Response(404)
        if path.endswith("webstream"):
            name, photos = self.albums[token]
            video = {"photoGuid": "V1", "mediaAssetType": "video", "derivatives": {}}
            return httpx.Response(200, json={"streamName": name, "photos": [*photos, video]})
        if path.endswith("webasseturls"):
            guids = json.loads(request.content)["photoGuids"]
            items = {
                f"{g}-{size}": {
                    "url_location": "cvws.icloud-content.com",
                    "url_path": f"/{g}-{size}",
                }
                for g in guids
                for size in ("small", "big")
            }
            return httpx.Response(200, json={"items": items})
        if request.url.host == "cvws.icloud-content.com":
            big = path.endswith("-big")
            return httpx.Response(200, content=_jpeg((2048, 1536) if big else (342, 256), big))
        return httpx.Response(404)

    def downloads(self, kind: str) -> list[str]:
        return [c for c in self.calls if c.startswith("GET cvws") and c.endswith(kind)]


@pytest.fixture
def icloud(service) -> FakeICloud:
    fake = FakeICloud()
    service.importer.http = lambda: httpx.Client(transport=httpx.MockTransport(fake))
    service.images.http = service.importer.http
    return fake


def _album_playlist(service, url: str = URL, order: AlbumOrder = AlbumOrder.RANDOM) -> int:
    playlist = service.library.save_playlist(
        Playlist(name="Rodzina", kind=PlaylistKind.ALBUM, album=AlbumSource(url=url, order=order))
    )
    assert playlist.id is not None
    return playlist.id


def test_token_and_partition() -> None:
    token = album_token(URL)
    assert token == "B0aGWZuqDGKPOC"
    assert partition_host(token).endswith("-sharedstreams.icloud.com")
    assert partition_host("A1abcdefghij") == "p01-sharedstreams.icloud.com"
    with pytest.raises(ValueError):
        album_token("https://example.com/not-an-album")


def test_sync_brings_thumbnails_and_originals_come_when_needed(service, icloud) -> None:
    icloud.albums["B0aGWZuqDGKPOC"] = (
        "Rodzina",
        [_photo("G1", "2025-08-14T16:32:00Z", "2025-08-20T10:00:00Z", "Hel")],
    )
    listing = sync_album(service.importer, URL)

    assert listing.name == "Rodzina" and listing.item_ids == ["icloud:G1"]
    item = service.library.get("icloud:G1")
    assert item is not None and item.kind == ItemKind.PHOTO
    assert item.artist == "Ala Kowalska" and item.title == "Hel" and item.museum == "Rodzina"
    assert item.url == URL and item.photo is not None and item.photo.asset == "G1-big"
    assert item.photo.shared_at == "2025-08-20T10:00:00Z"
    assert icloud.downloads("-small") and not icloud.downloads("-big")
    assert not service.images.has_image(item)

    # Shown later: a fresh link to the original, whose EXIF tells date and place.
    service.images.ensure_image(item)
    assert icloud.downloads("-big")
    item = service.library.get("icloud:G1")
    assert item is not None and item.photo is not None
    assert item.photo.latitude == pytest.approx(54.6)
    assert item.photo.longitude == pytest.approx(18.8)
    assert item.photo.taken_at == "2025-08-14T18:32:00"


def test_album_playlists_follow_their_albums(service, icloud) -> None:
    icloud.albums["B0aGWZuqDGKPOC"] = (
        "Rodzina",
        [
            _photo("G1", "2025-08-14T16:32:00Z", "2025-08-20T10:00:00Z"),
            _photo("G2", "2024-01-02T10:00:00Z", "2025-09-01T10:00:00Z"),
        ],
    )
    icloud.albums["B1bbbbbbbbbbbb"] = ("Góry", [_photo("M1", "2023-07-01T08:00:00Z", "")])
    family, mountains = _album_playlist(service), _album_playlist(service, OTHER)

    sync = service.albums.sync(family)
    assert sync is not None and (sync.name, sync.count, sync.added) == ("Rodzina", 2, 2)
    service.albums.sync(mountains)
    assert service.library.playlist(family).item_ids == ["icloud:G1", "icloud:G2"]
    assert service.library.playlist(mountains).item_ids == ["icloud:M1"]
    summary = service.library.playlist_summary(service.library.playlist(family))
    assert summary.item_count == 2 and summary.album_sync is not None

    # A photo gone from the album leaves the playlist and the library.
    name, photos = icloud.albums["B0aGWZuqDGKPOC"]
    icloud.albums["B0aGWZuqDGKPOC"] = (name, photos[1:])
    assert service.albums.sync(family).added == 0
    assert service.library.playlist(family).item_ids == ["icloud:G2"]
    assert service.library.get("icloud:G1") is None

    # A broken link keeps the photos and says what went wrong.
    service.library.save_playlist(
        service.library.playlist(family).model_copy(
            update={"album": AlbumSource(url="https://www.icloud.com/sharedalbum/#B9zzzzzzzzzz")}
        )
    )
    assert service.albums.sync(family).error
    assert service.library.playlist(family).item_ids == ["icloud:G2"]

    # Deleting an album playlist deletes its photos; the other album's stay.
    service.library.delete_playlist(family)
    service.albums.deleted(family)
    assert service.library.get("icloud:G2") is None
    assert service.library.get("icloud:M1") is not None


def test_album_order(service, icloud) -> None:
    icloud.albums["B0aGWZuqDGKPOC"] = (
        "Rodzina",
        [
            _photo("OLD", "2020-01-01T10:00:00Z", "2025-09-03T10:00:00Z"),
            _photo("NEW", "2025-06-01T10:00:00Z", "2025-09-01T10:00:00Z"),
            _photo("MID", "2023-01-01T10:00:00Z", "2025-09-02T10:00:00Z"),
        ],
    )
    playlist_id = _album_playlist(service, order=AlbumOrder.NEWEST)
    service.albums.sync(playlist_id)
    items = service.library.playlist_items(service.library.playlist(playlist_id))

    def ids(order: AlbumOrder) -> list[str]:
        return [i.source_id for i in album_order(items, order)]

    assert ids(AlbumOrder.NEWEST) == ["NEW", "MID", "OLD"]
    assert ids(AlbumOrder.OLDEST) == ["OLD", "MID", "NEW"]
    assert ids(AlbumOrder.ADDED) == ["OLD", "MID", "NEW"]
    assert sorted(ids(AlbumOrder.RANDOM)) == ["MID", "NEW", "OLD"]

    # Played: the album's order wins over the frame's shuffle.
    settings = service.player.settings
    settings.playlist_id, settings.shuffle = playlist_id, True
    service.player.save_settings(settings)
    assert [i.source_id for i in service.player.upcoming()] == ["NEW", "MID", "OLD"]

    # A new photo in the album comes first at the next change.
    icloud.albums["B0aGWZuqDGKPOC"][1].append(
        _photo("NEWEST", "2026-10-01T10:00:00Z", "2026-10-02T10:00:00Z")
    )
    service.albums.sync(playlist_id)
    assert service.player.upcoming()[0].source_id == "NEWEST"


def test_older_album_setting_becomes_a_playlist(service) -> None:
    from frame_server.library import Item

    service.library.upsert(
        Item(id="icloud:G1", kind=ItemKind.PHOTO, source="icloud", source_id="G1")
    )
    service.library.set_state("album_sync", {"at": "2026-10-01T10:00:00+00:00", "name": "Rodzina"})
    service.library.set_state(
        SETTINGS_KEY, {"mode": "album", "album_url": URL, "shuffle": False, "playlist_id": None}
    )

    playlist = service.albums.migrate()

    assert playlist is not None and playlist.kind == PlaylistKind.ALBUM
    assert playlist.name == "Rodzina" and playlist.item_ids == ["icloud:G1"]
    assert playlist.album == AlbumSource(url=URL, order=AlbumOrder.NEWEST)
    assert service.player.settings.playlist_id == playlist.id
    raw = service.library.get_state(SETTINGS_KEY)
    assert "album_url" not in raw and "mode" not in raw
    assert service.albums.migrate() is None  # once
    assert len(service.albums.playlists()) == 1


def test_api_album_playlists(service, icloud) -> None:
    from frame_server.web import create_app

    icloud.albums["B0aGWZuqDGKPOC"] = (
        "Rodzina",
        [_photo("G1", "2025-08-14T16:32:00Z", "2025-08-20T10:00:00Z")],
    )
    app = create_app(service.settings)
    svc = app.state.service
    svc.importer.http = service.importer.http
    svc.images.http = service.importer.http

    with TestClient(app) as client:
        assert client.post("/api/albums/check", json={"url": URL}).json() == {
            "name": "Rodzina",
            "count": 1,
        }
        bad = client.post("/api/albums/check", json={"url": "https://example.com/x"})
        assert bad.status_code == 422
        missing = client.post("/api/playlists", json={"name": "Album", "kind": "album"})
        assert missing.status_code == 422

        created = client.post(
            "/api/playlists",
            json={"name": "Rodzina", "kind": "album", "album": {"url": URL, "order": "newest"}},
        ).json()
        playlist_id = created["playlist"]["id"]
        assert created["playlist"]["album"] == {"url": URL, "order": "newest"}
        job_id = client.post(f"/api/playlists/{playlist_id}/sync").json()["job_id"]
        for _ in range(200):
            if client.get(f"/api/jobs/{job_id}").json()["finished"]:
                break
            time.sleep(0.05)
        detail = client.get(f"/api/playlists/{playlist_id}").json()
        assert detail["item_ids"] == ["icloud:G1"]
        assert client.get(f"/api/playlists/{playlist_id}/sync").json()["count"] == 1

        # Taken out of the album playlist: stays out after the next sync.
        client.delete(f"/api/playlists/{playlist_id}/items/icloud:G1")
        svc.albums.sync(playlist_id)
        assert client.get(f"/api/playlists/{playlist_id}").json()["items"] == []

        settings = client.get("/api/settings").json()
        assert "mode" not in settings and "album_url" not in settings
        assert client.post(f"/api/playlists/{playlist_id}/play").status_code == 202
        assert client.get("/api/player").json()["playlist"]["kind"] == "album"
