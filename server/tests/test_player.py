from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta

import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from pydantic import ValidationError

from frame_server.library import ItemKind, Playlist, PlaylistRules
from frame_server.player import Hold, hold_from
from frame_server.schedule import (
    FrameSettings,
    in_quiet_hours,
    morning_change,
    next_change,
    quiet_hours,
)


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=FrameSettings().tz())


def test_daily_change_at_seven() -> None:
    s = FrameSettings()  # 07:00 daily, quiet from 22:00, Europe/Warsaw
    assert next_change(_at("2026-10-24T15:00"), s) == _at("2026-10-25T07:00")
    assert next_change(_at("2026-10-24T06:00"), s) == _at("2026-10-24T07:00")
    assert next_change(_at("2026-10-24T07:00"), s) == _at("2026-10-25T07:00")


def test_several_change_times_a_day() -> None:
    s = FrameSettings(change_times=["19:00", "7:00", "13:30", "07:00"])
    assert s.change_times == ["07:00", "13:30", "19:00"]
    assert next_change(_at("2026-10-24T08:00"), s) == _at("2026-10-24T13:30")
    assert next_change(_at("2026-10-24T19:30"), s) == _at("2026-10-25T07:00")
    # Quiet hours run from 22:00 to the morning change.
    assert quiet_hours(s) == (time(22, 0), time(7, 0))
    assert in_quiet_hours(_at("2026-10-24T23:00"), s)
    assert not in_quiet_hours(_at("2026-10-24T12:00"), s)
    assert morning_change(s) == time(7, 0)


def test_every_few_days() -> None:
    s = FrameSettings(change_times=["08:00"], change_every_days=3)
    # Shown on Saturday 08:00 (or by hand at noon): the next one on Tuesday.
    assert next_change(_at("2026-10-24T08:00"), s) == _at("2026-10-27T08:00")
    assert next_change(_at("2026-10-24T12:00"), s) == _at("2026-10-27T08:00")
    assert next_change(_at("2026-10-24T06:00"), s) == _at("2026-10-24T08:00")


def test_quiet_hours_end_with_a_change() -> None:
    assert quiet_hours(FrameSettings(quiet_start=None)) is None
    early = FrameSettings(change_times=["06:30", "21:00"], quiet_start="23:15")
    assert quiet_hours(early) == (time(23, 15), time(6, 30))
    # Starting before the morning change: a short night.
    assert quiet_hours(FrameSettings(quiet_start="05:00")) == (time(5, 0), time(7, 0))
    # Starting at the only change: no quiet hours at all.
    assert quiet_hours(FrameSettings(quiet_start="07:00")) is None
    assert morning_change(FrameSettings(change_times=["12:00", "09:00"], quiet_start=None)) == time(
        9, 0
    )
    with pytest.raises(ValidationError):
        FrameSettings(change_times=[])
    with pytest.raises(ValidationError):
        FrameSettings(change_times=["7 rano"])


def test_older_interval_settings_become_change_times() -> None:
    daily = FrameSettings.model_validate(
        {"interval_minutes": 1440, "interval_minutes_battery": 2880, "quiet_end": "07:30"}
    )
    assert daily.change_times == ["07:30"] and daily.change_every_days == 1
    every3 = FrameSettings.model_validate({"interval_minutes": 4320, "quiet_end": "07:00"})
    assert every3.change_every_days == 3
    hours = FrameSettings.model_validate(
        {"interval_minutes": 180, "quiet_start": "22:00", "quiet_end": "07:00"}
    )
    assert hours.change_times == ["07:00", "10:00", "13:00", "16:00", "19:00"]
    assert hours.quiet_start == "22:00"


def test_hold_specs() -> None:
    assert hold_from("next") is None
    assert hold_from("forever") == Hold(forever=True)
    hold = hold_from(60)
    assert hold is not None and hold.active(datetime.now(UTC))
    assert not hold.active(datetime.now(UTC) + timedelta(hours=2))


def _add(service, n: int, color: tuple[int, int, int], artist: str):
    return service.importer.add_upload(
        jpeg_bytes(color), kind=ItemKind.OWN, title=f"Work {n}", artist=artist
    )


async def test_rotation_next_previous_and_history(service) -> None:
    a = _add(service, 1, (200, 40, 40), "Ala")
    b = _add(service, 2, (40, 40, 200), "Ola")
    c = _add(service, 3, (40, 160, 40), "Ala")
    playlist = service.library.save_playlist(
        Playlist(name="Ala", rules=PlaylistRules(artists=["Ala"]))
    )
    settings = service.player.settings
    settings.playlist_id = playlist.id
    settings.shuffle = False
    service.player.save_settings(settings)

    first = await service.player.next()
    second = await service.player.next()
    assert {first.id, second.id} == {a.id, c.id}  # b is not in the playlist
    assert service.player.state.current_item_id == second.id
    assert service.store.current().extra["item_id"] == second.id

    back = await service.player.previous()
    assert back.id == first.id
    assert service.player.state.queue[0] == second.id
    assert b.id not in service.player.state.queue


async def test_tick_respects_hold_and_schedule(service) -> None:
    _add(service, 1, (200, 40, 40), "Ala")
    player = service.player
    player.reschedule()
    state = player.state
    state.next_change_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    state.hold = Hold(forever=True)
    player._save_state(state)
    settings = player.settings
    settings.quiet_start = None
    player.save_settings(settings)
    state = player.state
    state.next_change_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    player._save_state(state)

    await player.tick()
    assert player.state.current_item_id is None  # held

    player.set_hold(None)
    await player.tick()
    assert player.state.current_item_id is not None


def test_api_library_playlists_player(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    for n, colour in enumerate([(200, 40, 40), (40, 40, 200), (230, 200, 40)]):
        _add(svc, n, colour, "Ala" if n else "Ola")

    with TestClient(app) as client:
        page = client.get("/api/library/items", params={"artist": "Ala"}).json()
        assert page["total"] == 2
        item_id = page["items"][0]["id"]
        assert (
            client.get(f"/api/library/items/{item_id}/thumb").headers["content-type"]
            == "image/jpeg"
        )
        assert client.patch(f"/api/library/items/{item_id}", json={"favorite": True}).json()[
            "favorite"
        ]
        assert client.get("/api/library/facets").json()["artists"][0] == {
            "value": "Ala",
            "count": 2,
        }

        preview = client.post("/api/playlists/preview", json={"colors": ["blue"]}).json()
        assert preview["count"] >= 1
        created = client.post(
            "/api/playlists", json={"name": "Niebieskie", "rules": {"colors": ["blue"]}}
        )
        playlist_id = created.json()["playlist"]["id"]
        assert any(p["name"] == "Niebieskie" for p in client.get("/api/playlists").json())

        # Framing tried before saving it: a different render of the same item.
        saved = client.get(f"/api/library/items/{item_id}/preview")
        trial = client.get(
            f"/api/library/items/{item_id}/preview",
            params={"settings": json.dumps({"art": {"fit": "fill", "margin": 0}})},
        )
        assert trial.headers["content-type"] == "image/png"
        assert trial.content != saved.content
        bad = client.get(f"/api/library/items/{item_id}/preview", params={"settings": "{"})
        assert bad.status_code == 422

        settings = client.get("/api/settings").json()
        settings["change_times"] = ["19:00", "07:00"]
        settings["art"]["label"] = True
        assert client.put("/api/settings", json=settings).json()["change_times"] == [
            "07:00",
            "19:00",
        ]

        assert client.post(f"/api/playlists/{playlist_id}/play").status_code == 202
        view = client.get("/api/player").json()
        assert view["playlist"]["id"] == playlist_id and view["mode"] == "art"

        status = client.get("/api/status").json()
        assert status["device"]["configured"] is False
        assert status["server"]["library_count"] == 3


async def test_presentation_change_redraws_the_current_picture(service) -> None:
    item = _add(service, 1, (200, 40, 40), "Ala")
    player = service.player
    await player.show(item, "test")
    before, state = service.store.current(), player.state

    old = player.settings
    new = old.model_copy(deep=True)
    new.photo.margin = 0.2  # the current picture is art: no redraw
    assert not player.needs_restyle(old, new)
    new.art.margin = 0.12
    assert player.needs_restyle(old, new)

    player.save_settings(new)
    await player.restyle()
    after = service.store.current()
    assert after.file_id != before.file_id
    assert after.render["layout"]["margin"] == 0.12
    # Same picture, framed differently: the schedule and counts stay put.
    assert player.state.last_change_at == state.last_change_at
    assert player.state.next_change_at == state.next_change_at
    assert service.library.get(item.id).show_count == 1


async def test_timed_hold_ends_with_the_next_picture(service) -> None:
    a = _add(service, 1, (200, 40, 40), "Ala")
    _add(service, 2, (40, 40, 200), "Ola")
    player = service.player
    settings = player.settings
    settings.quiet_start = None
    player.save_settings(settings)
    # "For an hour", and the hour is over: the rotation takes over now, not
    # at tomorrow's scheduled change.
    expired = Hold(until=(datetime.now(UTC) - timedelta(minutes=1)).isoformat())
    await player.show(a, "app", expired)
    await player.tick()
    assert player.state.hold is None
    assert player.state.current_item_id not in (None, a.id)


async def test_push_without_panel_reports_an_error(service) -> None:
    _add(service, 1, (200, 40, 40), "Ala")
    await service.player.next()
    assert "panel not configured" in (service.player.state.last_error or "")


def test_public_host_accepts_a_url() -> None:
    from frame_server.config import Settings

    for value in ("192.100.3.185", "http://192.100.3.185", "http://192.100.3.185:8099/"):
        assert Settings(public_host=value).base_url() == "http://192.100.3.185:8099"


def test_panel_progress_report_is_accepted(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    with TestClient(app) as client:
        response = client.post("/content-transfer-progress", json={"progress": 100})
        assert response.status_code == 200
    paths = [r.path for r in app.state.service.store.recent_requests]
    assert "/content-transfer-progress" in paths
