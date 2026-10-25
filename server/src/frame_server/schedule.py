"""Frame settings (what to show, how, and when) and change-time arithmetic."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .imaging.grids import MAX_PHOTOS, MIN_PHOTOS
from .imaging.layout import Fit, Orientation


class Presentation(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    preset: str = "auto"  # library.style.AUTO: chosen per picture; else an imaging.PRESETS key
    fit: Fit = Fit.AUTO  # fill, passe-partout or details, by the picture's proportions
    mat: Literal["white", "cream", "grey", "black", "picture"] = "white"  # picture: its hue
    margin: float = Field(0.05, ge=0, le=0.3)
    label: bool = False
    # MULTI (photos): how many on one board, or a random number each time,
    # and the grid's letter (grids.GRIDS) or automatic by the photos' shapes.
    multi_count: int = Field(4, ge=MIN_PHOTOS, le=MAX_PHOTOS)
    multi_random: bool = False
    multi_grid: Literal["auto", "A", "B", "C"] = "auto"


MAX_CHANGE_TIMES = 12

# Photos have their own framings; pictures keep theirs (MULTI is photos only).
PHOTO_FITS = (Fit.FIT, Fit.FILL, Fit.MULTI)


class FrameSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    # The playlist the frame plays (an album playlist shows its photos);
    # None: Suggestions.
    playlist_id: int | None = None
    # When the picture changes: at these times of day (HH:MM, local), every
    # day or every second or third day. The same on the charger and on
    # battery; at least every three days protects the panel.
    change_times: list[str] = Field(default_factory=lambda: ["07:00"], min_length=1)
    change_every_days: int = Field(1, ge=1, le=3)
    # Quiet hours run from here until the next change time (the morning one):
    # the panel sleeps with the Wi-Fi off and wakes itself for that change.
    quiet_start: str | None = "22:00"
    shuffle: bool = True
    avoid_repeat_days: int = Field(14, ge=0, le=365)
    orientation: Orientation = Orientation.LANDSCAPE
    rotation: Literal[90, 270] = 90
    art: Presentation = Field(default_factory=Presentation)
    photo: Presentation = Field(default_factory=lambda: Presentation(fit=Fit.FILL, margin=0.0))
    timezone: str = "Europe/Warsaw"
    status_poll_minutes: int = Field(15, ge=0, le=1440)  # 0 = only on demand
    # The frame is only seen at home: also accept works that are free to use
    # but not public domain (e.g. CC BY-SA on Wikimedia Commons).
    private_use: bool = False
    # WikiArt as a source, only to test the panel with newer art; its works
    # leave the library when this is switched off.
    wikiart: bool = False

    @model_validator(mode="before")
    @classmethod
    def _from_intervals(cls, data: Any) -> Any:
        """Older settings: an interval from the end of quiet hours becomes
        the change times it produced."""
        if not isinstance(data, dict) or "change_times" in data or "interval_minutes" not in data:
            return data
        data = dict(data)
        minutes = int(data.pop("interval_minutes") or 1440)
        anchor = _parse(data.pop("quiet_end", None)) or time(7, 0)
        start = _parse(data.get("quiet_start"))
        data.pop("interval_minutes_battery", None)
        if minutes >= 1440:
            data["change_times"] = [anchor.strftime("%H:%M")]
            data["change_every_days"] = min(max(minutes // 1440, 1), 3)
            return data
        times = []
        slot = datetime.combine(datetime(2000, 1, 1), anchor)
        end = slot + timedelta(days=1)
        while slot < end:
            moment = slot.time()
            quiet = start is not None and start != anchor and _between(moment, start, anchor)
            if not quiet:
                times.append(moment.strftime("%H:%M"))
            slot += timedelta(minutes=max(minutes, 15))
        data["change_times"] = times[:MAX_CHANGE_TIMES]
        return data

    @field_validator("change_times")
    @classmethod
    def _sorted_times(cls, value: list[str]) -> list[str]:
        times = sorted({_hhmm(v) for v in value})
        if len(times) > MAX_CHANGE_TIMES:
            raise ValueError(f"at most {MAX_CHANGE_TIMES} change times")
        return [t.strftime("%H:%M") for t in times]

    @field_validator("quiet_start")
    @classmethod
    def _valid_start(cls, value: str | None) -> str | None:
        return _hhmm(value).strftime("%H:%M") if value else None

    @model_validator(mode="after")
    def _own_fits(self) -> FrameSettings:
        """Older settings: photos framed as pictures fill the screen."""
        if self.photo.fit not in PHOTO_FITS:
            self.photo = self.photo.model_copy(update={"fit": Fit.FILL})
        if self.art.fit == Fit.MULTI:
            self.art = self.art.model_copy(update={"fit": Fit.AUTO})
        return self

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _hhmm(text: str) -> time:
    try:
        hour, minute = text.split(":")
        return time(int(hour), int(minute))
    except ValueError as err:
        raise ValueError(f"not a time of day (HH:MM): {text!r}") from err


def _parse(hhmm: str | None) -> time | None:
    return _hhmm(hhmm) if hhmm else None


def _between(moment: time, start: time, end: time) -> bool:
    """``start <= moment < end`` on a clock face (the span may cross midnight)."""
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def change_times(settings: FrameSettings) -> list[time]:
    return [_hhmm(t) for t in settings.change_times]


def quiet_hours(settings: FrameSettings) -> tuple[time, time] | None:
    """From ``quiet_start`` until the first change time after it."""
    start = _parse(settings.quiet_start)
    if start is None:
        return None
    times = change_times(settings)
    end = next((t for t in times if t > start), times[0])
    return None if end == start else (start, end)


def in_quiet_hours(moment: datetime, settings: FrameSettings) -> bool:
    hours = quiet_hours(settings)
    if hours is None:
        return False
    return _between(moment.astimezone(settings.tz()).time(), *hours)


def morning_change(settings: FrameSettings) -> time:
    """The change the panel's own alarm wakes it for: the one ending quiet
    hours, or without them the first of the day."""
    hours = quiet_hours(settings)
    return hours[1] if hours else change_times(settings)[0]


def next_change(after: datetime, settings: FrameSettings) -> datetime:
    """Next scheduled change strictly after ``after``.

    At each change time on the days counted from ``after`` (the last
    change): that day, then every ``change_every_days`` days. Daily at
    07:00 and 19:00 after a change at 07:00 means 19:00 the same day; every
    third day at 07:00 after a change on Monday means Thursday 07:00.
    """
    tz = settings.tz()
    local = after.astimezone(tz)
    times = change_times(settings)
    day = local.date()
    for _ in range(3):
        for moment in times:
            slot = datetime.combine(day, moment, tzinfo=tz)
            if slot > local:
                return slot
        day += timedelta(days=settings.change_every_days)
    raise AssertionError("no change time found")  # pragma: no cover
