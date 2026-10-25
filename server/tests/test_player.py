from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.library import ItemKind, Playlist, PlaylistRules
from frame_server.player import Hold, hold_from
from frame_server.schedule import FrameSettings, in_quiet_hours, next_change


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=FrameSettings().tz())


def test_daily_changes_happen_at_end_of_quiet_hours() -> None:
    s = FrameSettings()  # daily, quiet 22:00-07:00, Europe/Warsaw
    assert next_change(_at("2026-10-24T15:00"), s) == _at("2026-10-25T07:00")
    assert next_change(_at("2026-10-24T06:00"), s) == _at("2026-10-24T07:00")


def test_interval_skips_quiet_hours() -> None:
    s = FrameSettings(interval_minutes=180)
    assert next_change(_at("2026-10-24T08:00"), s) == _at("2026-10-24T10:00")
    # 22:00 and later slots fall into quiet hours -> next morning.
    assert next_change(_at("2026-10-24T19:30"), s) == _at("2026-10-25T07:00")
    assert in_quiet_hours(_at("2026-10-24T23:00"), s)
    assert not in_quiet_hours(_at("2026-10-24T12:00"), s)


def test_battery_interval() -> None:
    s = FrameSettings(interval_minutes=60, interval_minutes_battery=720)
    assert next_change(_at("2026-10-24T08:30"), s, on_battery=True) == _at("2026-10-24T19:00")


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
    settings.quiet_start = settings.quiet_end = None
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
        settings["interval_minutes"] = 180
        settings["art"]["label"] = True
        assert client.put("/api/settings", json=settings).json()["interval_minutes"] == 180

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
    settings.quiet_start = settings.quiet_end = None
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


def test_auto_style_follows_the_picture(service) -> None:
    from frame_server.imaging import PRESETS

    player = service.player
    settings = player.settings
    assert settings.art.preset == "auto" and settings.photo.preset == "auto"
    colour = service.importer.add_upload(
        jpeg_bytes((200, 40, 40)), kind=ItemKind.OWN, title="Red", artist="Ala"
    )
    colour = service.library.update(colour.id, medium="Colour woodcut") or colour
    grey = service.importer.add_upload(jpeg_bytes((150, 150, 150)), kind=ItemKind.PHOTO)
    assert colour.tint_spread is not None and grey.tint_spread is not None
    assert player.preset_for(colour, settings) == "graphic"
    assert player.preset_for(grey, settings) == "bw"
    assert player.render_settings(grey, settings).inks == PRESETS["bw"].inks
    # Picked by hand: kept.
    settings.art.preset = "painting"
    assert player.preset_for(colour, settings) == "painting"
    # Pictures from before automatic styles are measured on first use.
    old = service.library.update(grey.id, tint_spread=None)
    assert old is not None and old.tint_spread is None
    assert player.preset_for(old, settings) == "bw"
    assert service.library.get(grey.id).tint_spread is not None


def test_old_default_styles_become_automatic(service) -> None:
    from frame_server.player import AUTO_STYLE_KEY, SETTINGS_KEY, Player

    library = service.library
    raw = FrameSettings().model_dump(mode="json")
    raw["art"]["preset"] = "painting"  # the old default
    raw["photo"]["preset"] = "bw"  # picked by hand
    library.set_state(SETTINGS_KEY, raw)
    library.set_state(AUTO_STYLE_KEY, None)
    player = Player(service)
    assert player.settings.art.preset == "auto"
    assert player.settings.photo.preset == "bw"
    # Only once: choosing "painting" by hand later sticks.
    settings = player.settings
    settings.art.preset = "painting"
    player.save_settings(settings)
    assert Player(service).settings.art.preset == "painting"
