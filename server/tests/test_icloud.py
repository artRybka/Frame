from __future__ import annotations

import io
import json

import httpx
import pytest
from PIL import Image

from frame_server.library.icloud import album_token, partition_host, sync_album
from frame_server.library.models import ItemKind


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (400, 300), (40, 90, 160))
    exif = Image.Exif()
    exif[0x0132] = "2025:08:14 18:32:00"  # DateTime
    gps = {1: "N", 2: (54.0, 36.0, 0.0), 3: "E", 4: (18.0, 48.0, 0.0)}
    exif[0x8825] = gps
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_token_and_partition() -> None:
    token = album_token("https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC")
    assert token == "B0aGWZuqDGKPOC"
    assert partition_host(token).endswith("-sharedstreams.icloud.com")
    assert partition_host("A1abcdefghij") == "p01-sharedstreams.icloud.com"
    with pytest.raises(ValueError):
        album_token("https://example.com/not-an-album")


def test_sync_album(service) -> None:
    jpeg = _jpeg_with_exif()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.host}{request.url.path}")
        path = request.url.path
        if request.url.host != "p99-sharedstreams.icloud.com" and path.endswith("webstream"):
            return httpx.Response(330, json={"X-Apple-MMe-Host": "p99-sharedstreams.icloud.com"})
        if path.endswith("webstream"):
            return httpx.Response(
                200,
                json={
                    "streamName": "Rodzina",
                    "photos": [
                        {
                            "photoGuid": "G1",
                            "caption": "Hel",
                            "dateCreated": "2025-08-14T16:32:00Z",
                            "contributorFullName": "Ala Kowalska",
                            "mediaAssetType": "image",
                            "derivatives": {
                                "342": {"checksum": "small", "width": "342", "height": "256"},
                                "2049": {"checksum": "big", "width": "2048", "height": "1536"},
                            },
                        },
                        {"photoGuid": "V1", "mediaAssetType": "video", "derivatives": {}},
                    ],
                },
            )
        if path.endswith("webasseturls"):
            body = json.loads(request.content)
            assert body["photoGuids"] == ["G1"]
            return httpx.Response(
                200,
                json={
                    "items": {
                        "big": {"url_location": "cvws.icloud-content.com", "url_path": "/big.jpg"}
                    }
                },
            )
        if request.url.host == "cvws.icloud-content.com":
            return httpx.Response(200, content=jpeg)
        return httpx.Response(404)

    service.importer.http = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    service.images.http = service.importer.http
    added = sync_album(service.importer, "https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC")

    assert added == 1
    item = service.library.get("icloud:G1")
    assert item is not None and item.kind == ItemKind.PHOTO
    assert item.artist == "Ala Kowalska" and item.title == "Hel" and item.museum == "Rodzina"
    assert item.photo is not None
    assert item.photo.latitude == pytest.approx(54.6) and item.photo.longitude == pytest.approx(
        18.8
    )
    assert item.photo.taken_at == "2025-08-14T18:32:00"
    assert service.library.get_state("album_sync")["count"] == 1
    assert any(c.startswith("GET cvws") for c in calls)

    # A second sync with the photo gone removes it from the library.
    def empty(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("webstream"):
            return httpx.Response(200, json={"streamName": "Rodzina", "photos": []})
        return httpx.Response(200, json={"items": {}})

    service.importer.http = lambda: httpx.Client(transport=httpx.MockTransport(empty))
    assert sync_album(service.importer, "https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC") == 0
    assert service.library.get("icloud:G1") is None
