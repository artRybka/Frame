"""Frame settings (what to show, how, and when) and change-time arithmetic."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from .imaging.layout import Fit, Orientation


class Mode(StrEnum):
    ART = "art"  # pictures from a playlist
    ALBUM = "album"  # the shared iCloud album


class Presentation(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    preset: str = "painting"
    fit: Fit = Fit.AUTO  # fill, passe-partout or details, by the picture's proportions
    mat: Literal["white", "cream", "grey", "black", "picture"] = "white"  # picture: its hue
    margin: float = Field(0.05, ge=0, le=0.3)
    label: bool = False


class FrameSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    mode: Mode = Mode.ART
    playlist_id: int | None = None
    # How often the picture changes, in minutes; on battery the slower value
    # applies. 1440 = once a day.
    interval_minutes: int = Field(1440, ge=15, le=10080)
    interval_minutes_battery: int = Field(1440, ge=60, le=10080)
    quiet_start: str | None = "22:00"
    quiet_end: str | None = "07:00"
    shuffle: bool = True
    avoid_repeat_days: int = Field(14, ge=0, le=365)
    orientation: Orientation = Orientation.LANDSCAPE
    rotation: Literal[90, 270] = 90
    art: Presentation = Field(default_factory=Presentation)
    photo: Presentation = Field(
        default_factory=lambda: Presentation(preset="photo", fit=Fit.AUTO, margin=0.0)
    )
    album_url: str = ""
    timezone: str = "Europe/Warsaw"
    status_poll_minutes: int = Field(15, ge=0, le=1440)  # 0 = only on demand
    # The frame is only seen at home: also accept works that are free to use
    # but not public domain (e.g. CC BY-SA on Wikimedia Commons).
    private_use: bool = False

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _parse(hhmm: str | None) -> time | None:
    if not hhmm:
        return None
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def in_quiet_hours(moment: datetime, settings: FrameSettings) -> bool:
    start, end = _parse(settings.quiet_start), _parse(settings.quiet_end)
    if start is None or end is None or start == end:
        return False
    local = moment.astimezone(settings.tz()).time()
    if start < end:
        return start <= local < end
    return local >= start or local < end


def next_change(after: datetime, settings: FrameSettings, on_battery: bool = False) -> datetime:
    """Next scheduled change strictly after ``after``.

    Changes are aligned to the end of quiet hours (07:00 by default), so a
    daily interval means every morning at 07:00 and a 3-hour interval means
    07:00, 10:00, 13:00, ... Slots inside quiet hours are skipped.
    """
    tz = settings.tz()
    minutes = settings.interval_minutes_battery if on_battery else settings.interval_minutes
    step = timedelta(minutes=minutes)
    anchor_time = _parse(settings.quiet_end) or time(0, 0)
    local = after.astimezone(tz)
    slot = datetime.combine(local.date() - timedelta(days=1), anchor_time, tzinfo=tz)
    # Bounded walk: at most a week of slots past the anchor.
    for _ in range(int(timedelta(days=9) / step) + 2):
        if slot > local and not in_quiet_hours(slot, settings):
            return slot
        slot += step
    return local + step
