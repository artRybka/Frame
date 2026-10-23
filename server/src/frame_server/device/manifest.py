"""The content.json manifest the panel downloads after an MDC content-download.

The layout mirrors what the Samsung E-Paper iOS app publishes
(deploy_type MOBILE). Several fields are not understood yet (``duration``
units, whether ``version``/``id`` drive caching, how several ``contents`` or
``schedule`` entries are played) — see experiments E6/E7.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime

# Where the Samsung app tells the player to store downloads. Kept verbatim.
PLAYER_CONTENT_DIR = "/home/owner/content/Downloads/vxtplayer/epaper/mobile/contents"

# Value used by the Samsung app for a single still image.
DEFAULT_DURATION = 91326


def new_file_id() -> str:
    return secrets.token_hex(8).upper()


@dataclass(frozen=True)
class ManifestItem:
    image_url: str
    file_id: str
    file_name: str
    file_size: int
    duration: int = DEFAULT_DURATION

    def to_json(self) -> dict[str, object]:
        return {
            "image_url": self.image_url,
            "file_id": self.file_id,
            "file_path": f"{PLAYER_CONTENT_DIR}/{self.file_id}/{self.file_name}",
            "duration": self.duration,
            "file_size": str(self.file_size),
            "file_name": self.file_name,
        }


@dataclass(frozen=True)
class ScheduleEntry:
    items: tuple[ManifestItem, ...]
    start_date: str = "1970-01-01"
    stop_date: str = "2999-12-31"
    start_time: str = "00:00:00"

    def to_json(self) -> dict[str, object]:
        return {
            "start_date": self.start_date,
            "stop_date": self.stop_date,
            "start_time": self.start_time,
            "contents": [item.to_json() for item in self.items],
        }


@dataclass(frozen=True)
class Manifest:
    schedule: tuple[ScheduleEntry, ...]
    name: str = "frame"
    version: int = 1
    manifest_id: str = field(default_factory=new_file_id)
    create_time: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))

    @classmethod
    def single(cls, item: ManifestItem, **kwargs: object) -> Manifest:
        return cls(schedule=(ScheduleEntry(items=(item,)),), **kwargs)  # type: ignore[arg-type]

    def to_json(self) -> dict[str, object]:
        return {
            "schedule": [entry.to_json() for entry in self.schedule],
            "name": self.name,
            "version": self.version,
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "id": self.manifest_id,
            "program_id": "com.samsung.ios.ePaper",
            "content_type": "ImageContent",
            "deploy_type": "MOBILE",
        }

    def encode(self) -> bytes:
        # The Samsung app escapes forward slashes; mimic it byte for byte in
        # case the player's JSON reader is picky.
        return json.dumps(self.to_json()).replace("/", "\\/").encode()
