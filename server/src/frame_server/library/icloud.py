"""Shared iCloud Photos album via its public website link.

Two kinds of links, each with its own (undocumented) web API.

Older shared albums, ``https://www.icloud.com/sharedalbum/#<token>``:

    POST https://<host>/<token>/sharedstreams/webstream      {"streamCtag": null}
         -> 330 {"X-Apple-MMe-Host": "<partition host>"} on the wrong host
         -> {"streamName", "photos": [{photoGuid, derivatives, caption,
             dateCreated, contributorFullName, mediaAssetType, ...}]}
    POST https://<host>/<token>/sharedstreams/webasseturls   {"photoGuids": [...]}
         -> {"items": {<checksum>: {"url_location", "url_path"}}}

Apple scales these photos to about 2048 px on the long side.

Newer shared albums (iOS 26), ``https://photos.icloud.com/shared/album/<token>``,
are CloudKit shared zones ("shared collections") with the full originals:

    POST ckdatabasews.icloud.com/database/1/com.apple.photos.cloud/production/
         public/records/resolve?sharing_url_key=<token>  {"shortGUIDs": [...]}
         -> {"results": [{zoneID, share: {fields: {cloudkit.title}},
             anonymousPublicAccess: {token, databasePartition}}]}
    POST <databasePartition>/database/1/com.apple.photos.cloud/production/
         shared/records/query?sharing_url_key=..&publicAccessAuthToken=..
         CPLAssetAndMasterByAssetDateWithoutHiddenOrDeleted, by startRank
         -> CPLMaster records (resOriginalRes, resJPEGMedRes, ... with signed
            download URLs) followed by their CPLAsset records (assetDate,
            addedDate, masterRef, locationEnc, resJPEGFullRes when edited)

Asset URLs are signed and expire: a sync downloads only thumbnails, and an
original is downloaded through a fresh link when it is about to be shown.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import logging
import plistlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from PIL import ExifTags, Image

from .importer import Importer, Job
from .models import Item, ItemKind, PhotoInfo

log = logging.getLogger(__name__)

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BATCH = 25
#: Thumbnails come from the smallest derivative with a long side this big.
THUMB_MIN = 320


#: The path of a newer shared album's link, before its token.
COLLECTION_PATH = "/shared/album/"


def is_collection(url: str) -> bool:
    """Whether the link is to a newer shared album (a CloudKit shared collection)."""
    return COLLECTION_PATH in urlsplit(url.strip()).path


def album_token(url: str) -> str:
    """``https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC`` -> ``B0aGWZuqDGKPOC``,
    ``https://photos.icloud.com/shared/album/0e6scjSSOolg7`` -> ``0e6scjSSOolg7``."""
    url = url.strip()
    if is_collection(url):
        token = urlsplit(url).path.split(COLLECTION_PATH, 1)[1].split("/")[0]
    else:
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
    latitude: float | None = None
    longitude: float | None = None


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

    def summary(self) -> tuple[str, int]:
        stream = self._post("webstream", {"streamCtag": None})
        photos = [p for p in stream.get("photos", []) if p.get("mediaAssetType") != "video"]
        return stream.get("streamName", ""), len(photos)

    def asset_url(self, guid: str, checksum: str) -> str:
        """A fresh link to one derivative of one photo."""
        urls = self._urls([guid])
        if checksum not in urls:
            raise httpx.HTTPError(f"photo {guid} is no longer in the album")
        return urls[checksum]


CK_DATABASE = "https://ckdatabasews.icloud.com"
CK_PATH = "/database/1/com.apple.photos.cloud/production"
#: Records per query: a CPLMaster and a CPLAsset for each photo.
CK_PAGE = 200
#: Originals Pillow reads (HEIC through pillow-heif); others (RAW) fall back
#: to Apple's JPEG renders.
READABLE = {"public.jpeg", "public.heic", "public.heif", "public.png", "public.tiff"}
#: Edited photos have their render on the CPLAsset; originals on the CPLMaster.
FULL_SIZE = ("resJPEGFullRes", "resOriginalRes", "resJPEGMedRes")
THUMB_SIZE = ("resJPEGThumbRes", "resJPEGMedRes", "resJPEGFullRes")
#: EXIF orientations that swap width and height.
ROTATED = {5, 6, 7, 8}


def _iso(millis: Any) -> str | None:
    if not isinstance(millis, int | float):
        return None
    return datetime.fromtimestamp(millis / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decoded(field: dict[str, Any] | None) -> Any:
    """An ``...Enc`` field: base64 of a plist or of UTF-8 text."""
    if not field or not isinstance(field.get("value"), str):
        return None
    try:
        raw = base64.b64decode(field["value"])
        return plistlib.loads(raw) if raw.startswith(b"bplist") else raw.decode()
    except (ValueError, plistlib.InvalidFileException):
        return None


def master_name(asset_fields: dict[str, Any]) -> str:
    return str(asset_fields.get("masterRef", {}).get("value", {}).get("recordName", ""))


def _is_video(master: dict[str, Any]) -> bool:
    kind = str(master.get("itemType", {}).get("value", "")).lower()
    return any(word in kind for word in ("movie", "mpeg", "video", "avi"))


class SharedCollection:
    """A newer shared album, read through CloudKit with the public link's
    anonymous access."""

    def __init__(self, http: httpx.Client, url: str) -> None:
        self.http = http
        self.token = album_token(url)
        self.name = ""
        self._zone: dict[str, Any] | None = None
        self._base = ""
        self._params: dict[str, str] = {}

    def _request(self, url: str, body: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
        resp = self.http.post(
            url, params=params, content=json.dumps(body), headers={"Content-Type": "text/plain"}
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    def _resolve(self) -> None:
        if self._zone is not None:
            return
        data = self._request(
            f"{CK_DATABASE}{CK_PATH}/public/records/resolve",
            {"shortGUIDs": [{"value": self.token}]},
            {"sharing_url_key": self.token},
        )
        result = (data.get("results") or [{}])[0]
        if result.get("serverErrorCode"):
            raise httpx.HTTPError(
                f"iCloud does not know this album ({result['serverErrorCode']}); "
                "is the link complete and the public website on?"
            )
        access = result.get("anonymousPublicAccess") or {}
        if not access.get("token") or not result.get("zoneID"):
            raise httpx.HTTPError("the album's public website is off")
        fields = (result.get("share") or {}).get("fields") or {}
        self.name = str((fields.get("cloudkit.title") or {}).get("value") or "")
        self._zone = result["zoneID"]
        self._base = f"{access.get('databasePartition') or CK_DATABASE}{CK_PATH}/shared"
        self._params = {
            "remapEnums": "true",
            "sharing_url_key": self.token,
            "publicAccessAuthToken": access["token"],
        }

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        self._resolve()
        return self._request(
            f"{self._base}/records/{endpoint}", {**body, "zoneID": self._zone}, self._params
        )

    def _pairs(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """(CPLAsset, its CPLMaster) records of every photo, videos left out."""
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        rank = 0
        while True:
            filters = [("direction", "STRING", "ASCENDING"), ("startRank", "INT64", rank)]
            data = self._post(
                "query",
                {
                    "query": {
                        "recordType": "CPLAssetAndMasterByAssetDateWithoutHiddenOrDeleted",
                        "filterBy": [
                            {
                                "fieldName": name,
                                "comparator": "EQUALS",
                                "fieldValue": {"value": value, "type": kind},
                            }
                            for name, kind, value in filters
                        ],
                    },
                    "resultsLimit": CK_PAGE,
                },
            )
            records = data.get("records") or []
            masters = {
                r["recordName"]: r["fields"] for r in records if r.get("recordType") == "CPLMaster"
            }
            assets = [r for r in records if r.get("recordType") == "CPLAsset"]
            if not assets:
                return pairs
            for asset in assets:
                master = masters.get(master_name(asset["fields"]))
                if master is not None and not _is_video(master):
                    pairs.append((asset, master))
            rank += len(assets)

    @staticmethod
    def _pick(
        asset: dict[str, Any], master: dict[str, Any], keys: tuple[str, ...]
    ) -> tuple[str, dict[str, Any]] | None:
        """The first derivative there is: (its field name, its fields' record)."""
        for key in keys:
            for fields in (asset, master):
                if key not in fields:
                    continue
                if key == "resOriginalRes":
                    kind = fields.get("resOriginalFileType", {}).get("value")
                    if kind not in READABLE:
                        continue
                return key, fields
        return None

    @staticmethod
    def _url(fields: dict[str, Any], key: str) -> str:
        value = fields[key]["value"]
        return str(value["downloadURL"]).replace("${f}", "photo")

    def photos(self) -> list[AlbumPhoto]:
        photos = []
        for asset, master in self._pairs():
            fields = asset["fields"]
            full = self._pick(fields, master, FULL_SIZE)
            if full is None:
                continue
            key, record = full
            thumb = self._pick(fields, master, THUMB_SIZE) or full
            stem = key.removesuffix("Res")
            width = int(record.get(f"{stem}Width", {}).get("value", 0))
            height = int(record.get(f"{stem}Height", {}).get("value", 0))
            turned = master.get("originalOrientation", {}).get("value", 1) in ROTATED
            if key == "resOriginalRes" and turned:  # renders are upright, originals not
                width, height = height, width
            place = _decoded(fields.get("locationEnc"))
            place = place if isinstance(place, dict) else {}
            caption = _decoded(fields.get("captionEnc"))
            photos.append(
                AlbumPhoto(
                    guid=asset["recordName"],
                    url=self._url(record, key),
                    thumb_url=self._url(thumb[1], thumb[0]),
                    asset=master_name(fields),
                    width=width,
                    height=height,
                    caption=caption.strip() if isinstance(caption, str) else "",
                    taken_at=_iso(fields.get("assetDate", {}).get("value")),
                    shared_at=_iso(fields.get("addedDate", {}).get("value")),
                    contributor="",
                    latitude=place.get("lat"),
                    longitude=place.get("lon"),
                )
            )
        # In the order photos were added, like an older album's stream.
        photos.sort(key=lambda p: p.shared_at or "")
        return photos

    def summary(self) -> tuple[str, int]:
        count = len(self._pairs())  # resolves the share, which names the album
        return self.name, count

    def asset_url(self, guid: str, master: str) -> str:
        """A fresh link to the full-size picture of one photo."""
        data = self._post("lookup", {"records": [{"recordName": guid}, {"recordName": master}]})
        found = {r["recordName"]: r for r in data.get("records") or [] if "fields" in r}
        if guid not in found or master not in found:
            raise httpx.HTTPError(f"photo {guid} is no longer in the album")
        full = self._pick(found[guid]["fields"], found[master]["fields"], FULL_SIZE)
        if full is None:
            raise httpx.HTTPError(f"photo {guid} has no picture to download")
        return self._url(full[1], full[0])


class Album(Protocol):
    name: str

    def photos(self) -> list[AlbumPhoto]: ...

    def summary(self) -> tuple[str, int]: ...

    def asset_url(self, guid: str, asset: str) -> str: ...


def open_album(http: httpx.Client, url: str) -> Album:
    """The web API client for a shared album's link; raises ValueError on a bad link."""
    if is_collection(url):
        return SharedCollection(http, url)
    return SharedAlbum(http, url)


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
    try:
        return open_album(http, url).summary()
    except (KeyError, TypeError) as err:
        raise httpx.HTTPError(f"unexpected answer from iCloud: {err!r}") from err


def sync_album(importer: Importer, url: str, job: Job | None = None) -> AlbumListing:
    """Bring the album's photos into the library: new ones with a thumbnail
    (originals are downloaded when they are about to be shown), known ones
    with fresh details. Photos gone from the album are left to the caller."""
    library = importer.library
    with importer.http() as http:
        album = open_album(http, url)
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
                latitude=photo.latitude,
                longitude=photo.longitude,
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
        url = open_album(http, item.url).asset_url(item.source_id, item.photo.asset)
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
