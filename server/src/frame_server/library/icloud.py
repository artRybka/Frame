"""Shared iCloud Photos album via its public website link.

Uses the (undocumented) web API behind icloud.com/sharedalbum pages:

    POST https://<host>/<token>/sharedstreams/webstream      {"streamCtag": null}
         -> 330 {"X-Apple-MMe-Host": "<partition host>"} on the wrong host
         -> {"streamName", "photos": [{photoGuid, derivatives, caption,
             dateCreated, contributorFullName, mediaAssetType, ...}]}
    POST https://<host>/<token>/sharedstreams/webasseturls   {"photoGuids": [...]}
         -> {"items": {<checksum>: {"url_location", "url_path"}}}

Asset URLs are signed and expire, so pictures are downloaded during sync.
Apple scales shared-album photos to about 2048 px on the long side.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from PIL import ExifTags, Image

from .importer import Importer, Job
from .models import Item, ItemKind, PhotoInfo

log = logging.getLogger(__name__)

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BATCH = 25


def album_token(url: str) -> str:
    """``https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC`` -> ``B0aGWZuqDGKPOC``."""
    token = url.split("#", 1)[-1].strip().split(";")[0].strip("/")
    if not re.fullmatch(r"[A-Za-z0-9]{10,}", token):
        raise ValueError(f"not a shared album link: {url!r}")
    return token


def partition_host(token: str) -> str:
    if token[0] == "A":
        partition = BASE62.index(token[1])
    else:
        partition = BASE62.index(token[1]) * 62 + BASE62.index(token[2])
    return f"p{partition:02d}-sharedstreams.icloud.com"


@dataclass
class AlbumPhoto:
    guid: str
    url: str
    width: int
    height: int
    caption: str
    taken_at: str | None
    contributor: str


class SharedAlbum:
    def __init__(self, http: httpx.Client, url: str) -> None:
        self.http = http
        self.token = album_token(url)
        self.host = partition_host(self.token)
        self.name = ""

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        for _ in range(3):
            resp = self.http.post(
                f"https://{self.host}/{self.token}/sharedstreams/{endpoint}",
                json=body,
                headers={"Content-Type": "text/plain"},
            )
            if resp.status_code == 330:
                self.host = resp.json()["X-Apple-MMe-Host"]
                continue
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data
        raise httpx.HTTPError("too many iCloud host redirects")

    def photos(self) -> list[AlbumPhoto]:
        stream = self._post("webstream", {"streamCtag": None})
        self.name = stream.get("streamName", "")
        entries = [p for p in stream.get("photos", []) if p.get("mediaAssetType") != "video"]
        best: dict[str, tuple[str, dict[str, Any]]] = {}
        for entry in entries:
            derivatives = entry.get("derivatives") or {}
            candidates = [d for key, d in derivatives.items() if key != "PosterFrame"]
            if not candidates:
                continue
            largest = max(
                candidates, key=lambda d: int(d.get("width", 0)) * int(d.get("height", 0))
            )
            best[entry["photoGuid"]] = (largest["checksum"], largest)

        urls: dict[str, str] = {}
        guids = list(best)
        for start in range(0, len(guids), BATCH):
            body = self._post("webasseturls", {"photoGuids": guids[start : start + BATCH]})
            for checksum, loc in (body.get("items") or {}).items():
                urls[checksum] = f"https://{loc['url_location']}{loc['url_path']}"

        photos = []
        for entry in entries:
            guid = entry.get("photoGuid")
            if guid not in best:
                continue
            checksum, derivative = best[guid]
            if checksum not in urls:
                continue
            photos.append(
                AlbumPhoto(
                    guid=guid,
                    url=urls[checksum],
                    width=int(derivative.get("width", 0)),
                    height=int(derivative.get("height", 0)),
                    caption=(entry.get("caption") or "").strip(),
                    taken_at=entry.get("dateCreated"),
                    contributor=(entry.get("contributorFullName") or "").strip(),
                )
            )
        return photos


def _gps_degrees(values: Any, ref: str) -> float | None:
    try:
        d, m, s = (float(v) for v in values)
    except (TypeError, ValueError):
        return None
    result = d + m / 60 + s / 3600
    return -result if ref in ("S", "W") else result


def exif_facts(img: Image.Image) -> tuple[str | None, float | None, float | None]:
    """(DateTimeOriginal as ISO, latitude, longitude) when the file keeps them."""
    exif = img.getexif()
    taken = None
    sub = exif.get_ifd(ExifTags.IFD.Exif)
    raw = sub.get(ExifTags.Base.DateTimeOriginal) or exif.get(ExifTags.Base.DateTime)
    if raw:
        try:
            taken = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            taken = None
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    lat = lon = None
    if gps:
        lat = _gps_degrees(gps.get(2), str(gps.get(1, "N")))
        lon = _gps_degrees(gps.get(4), str(gps.get(3, "E")))
    return taken, lat, lon


def sync_album(importer: Importer, url: str, job: Job | None = None) -> int:
    """Mirror the album into the library; returns the number of new photos."""
    library, cache = importer.library, importer.cache
    with importer.http() as http:
        album = SharedAlbum(http, url)
        photos = album.photos()
        if job is not None:
            job.total = len(photos)
        added = 0
        for photo in photos:
            item_id = f"icloud:{photo.guid}"
            if library.has(item_id):
                if job is not None:
                    job.done += 1
                continue
            item = Item(
                id=item_id,
                kind=ItemKind.PHOTO,
                source="icloud",
                source_id=photo.guid,
                title=photo.caption,
                artist=photo.contributor,
                date_text=(photo.taken_at or "")[:10],
                museum=album.name,
                image_url=photo.url,
                thumb_url=photo.url,
                width=photo.width or None,
                height=photo.height or None,
                photo=PhotoInfo(
                    taken_at=photo.taken_at,
                    contributor=photo.contributor or None,
                    caption=photo.caption or None,
                ),
            )
            try:
                resp = http.get(photo.url)
                resp.raise_for_status()
                # Read EXIF from the original bytes; the cached copy is re-encoded.
                with Image.open(io.BytesIO(resp.content)) as img:
                    taken, lat, lon = exif_facts(img)
                cache.store(item, resp.content)
                if item.photo is not None:
                    item.photo.taken_at = taken or item.photo.taken_at
                    item.photo.latitude, item.photo.longitude = lat, lon
                importer.add(item)
                added += 1
                if job is not None:
                    job.done += 1
                    job.item_ids.append(item_id)
            except (httpx.HTTPError, OSError) as err:
                log.warning("album photo %s failed: %s", photo.guid, err)
                if job is not None:
                    job.failed += 1

    current = {f"icloud:{p.guid}" for p in photos}
    for item in library.query(include_excluded=True)[1]:
        if item.source == "icloud" and item.id not in current:
            library.delete(item.id)
            cache.remove(item)
    library.set_state(
        "album_sync",
        {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "count": len(photos),
            "name": album.name,
        },
    )
    return added
