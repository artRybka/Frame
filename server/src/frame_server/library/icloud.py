"""Shared iCloud Photos album via its public website link.

Uses the (undocumented) web API behind icloud.com/sharedalbum pages:

    POST https://<host>/<token>/sharedstreams/webstream      {"streamCtag": null}
         -> 330 {"X-Apple-MMe-Host": "<partition host>"} on the wrong host
         -> {"streamName", "photos": [{photoGuid, derivatives, caption,
             dateCreated, contributorFullName, mediaAssetType, ...}]}
    POST https://<host>/<token>/sharedstreams/webasseturls   {"photoGuids": [...]}
         -> {"items": {<checksum>: {"url_location", "url_path"}}}

Asset URLs are signed and expire: a sync downloads only thumbnails, and an
original is downloaded through a fresh link when it is about to be shown.
Apple scales shared-album photos to about 2048 px on the long side.
"""

from __future__ import annotations

import contextlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from PIL import ExifTags, Image

from .importer import Importer, Job
from .models import Item, ItemKind, PhotoInfo

log = logging.getLogger(__name__)

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BATCH = 25
#: Thumbnails come from the smallest derivative with a long side this big.
THUMB_MIN = 320


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
    url: str  # full size; signed, expires
    thumb_url: str  # a small derivative for the playlist's thumbnail
    asset: str  # checksum of the full-size derivative
    width: int
    height: int
    caption: str
    taken_at: str | None
    shared_at: str | None
    contributor: str


def _long_side(derivative: dict[str, Any]) -> int:
    return max(int(derivative.get("width", 0)), int(derivative.get("height", 0)))


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

    def _urls(self, guids: list[str]) -> dict[str, str]:
        """Signed links by derivative checksum."""
        urls: dict[str, str] = {}
        for start in range(0, len(guids), BATCH):
            body = self._post("webasseturls", {"photoGuids": guids[start : start + BATCH]})
            for checksum, loc in (body.get("items") or {}).items():
                urls[checksum] = f"https://{loc['url_location']}{loc['url_path']}"
        return urls

    def photos(self) -> list[AlbumPhoto]:
        stream = self._post("webstream", {"streamCtag": None})
        self.name = stream.get("streamName", "")
        entries = [p for p in stream.get("photos", []) if p.get("mediaAssetType") != "video"]
        # Per photo: the largest derivative, and the smallest one still big
        # enough for a thumbnail.
        chosen: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for entry in entries:
            derivatives = entry.get("derivatives") or {}
            candidates = [d for key, d in derivatives.items() if key != "PosterFrame"]
            if not candidates:
                continue
            largest = max(candidates, key=_long_side)
            big_enough = [d for d in candidates if _long_side(d) >= THUMB_MIN] or [largest]
            chosen[entry["photoGuid"]] = (largest, min(big_enough, key=_long_side))

        urls = self._urls(list(chosen))
        photos = []
        for entry in entries:
            guid = entry.get("photoGuid")
            if guid not in chosen:
                continue
            largest, small = chosen[guid]
            if largest["checksum"] not in urls:
                continue
            url = urls[largest["checksum"]]
            photos.append(
                AlbumPhoto(
                    guid=guid,
                    url=url,
                    thumb_url=urls.get(small["checksum"], url),
                    asset=largest["checksum"],
                    width=int(largest.get("width", 0)),
                    height=int(largest.get("height", 0)),
                    caption=(entry.get("caption") or "").strip(),
                    taken_at=entry.get("dateCreated"),
                    shared_at=entry.get("batchDateCreated"),
                    contributor=(entry.get("contributorFullName") or "").strip(),
                )
            )
        return photos

    def asset_url(self, guid: str, checksum: str) -> str:
        """A fresh link to one derivative of one photo."""
        urls = self._urls([guid])
        if checksum not in urls:
            raise httpx.HTTPError(f"photo {guid} is no longer in the album")
        return urls[checksum]


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


@dataclass
class AlbumListing:
    name: str
    item_ids: list[str]  # in the album's order
    added: list[str]


def check_album(http: httpx.Client, url: str) -> tuple[str, int]:
    """The album's name and how many photos it has; raises on a bad link."""
    album = SharedAlbum(http, url)
    stream = album._post("webstream", {"streamCtag": None})
    photos = [p for p in stream.get("photos", []) if p.get("mediaAssetType") != "video"]
    return stream.get("streamName", ""), len(photos)


def sync_album(importer: Importer, url: str, job: Job | None = None) -> AlbumListing:
    """Bring the album's photos into the library: new ones with a thumbnail
    (originals are downloaded when they are about to be shown), known ones
    with fresh details. Photos gone from the album are left to the caller."""
    library = importer.library
    with importer.http() as http:
        album = SharedAlbum(http, url)
        photos = album.photos()
    if job is not None:
        job.total = len(photos)
    added = []
    for photo in photos:
        item_id = f"icloud:{photo.guid}"
        known = library.get(item_id)
        details = {
            "url": url,
            "museum": album.name,
            "image_url": photo.url,
            "thumb_url": photo.thumb_url,
        }
        if known is not None:
            info = (known.photo or PhotoInfo()).model_copy(
                update={"shared_at": photo.shared_at, "asset": photo.asset}
            )
            library.update(item_id, photo=info, **details)
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
            width=photo.width or None,
            height=photo.height or None,
            photo=PhotoInfo(
                taken_at=photo.taken_at,
                contributor=photo.contributor or None,
                caption=photo.caption or None,
                shared_at=photo.shared_at,
                asset=photo.asset,
            ),
            **details,
        )
        try:
            importer.add(item)
            added.append(item_id)
            if job is not None:
                job.done += 1
                job.item_ids.append(item_id)
        except (httpx.HTTPError, OSError) as err:
            log.warning("album photo %s failed: %s", photo.guid, err)
            if job is not None:
                job.failed += 1
    ids = [f"icloud:{p.guid}" for p in photos]
    return AlbumListing(album.name, [i for i in ids if library.has(i)], added)


def refetchable(item: Item) -> bool:
    """Whether the original of an album photo can be downloaded again."""
    return bool(item.source == "icloud" and item.url and item.photo and item.photo.asset)


def fetch_original(importer: Importer, item: Item) -> bytes:
    """Download an album photo's original through a fresh link, and keep the
    date and place its EXIF tells (the album's details are less exact)."""
    if not refetchable(item):
        raise httpx.HTTPError(f"no way to download {item.id} again; sync its album")
    assert item.photo is not None and item.photo.asset is not None
    with importer.http() as http:
        url = SharedAlbum(http, item.url).asset_url(item.source_id, item.photo.asset)
        resp = http.get(url)
        resp.raise_for_status()
    with contextlib.suppress(OSError, ValueError), Image.open(io.BytesIO(resp.content)) as img:
        taken, lat, lon = exif_facts(img)
        info = item.photo.model_copy(
            update={
                "taken_at": taken or item.photo.taken_at,
                "latitude": lat if lat is not None else item.photo.latitude,
                "longitude": lon if lon is not None else item.photo.longitude,
            }
        )
        importer.library.update(item.id, photo=info)
    return resp.content
