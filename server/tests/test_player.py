from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.library import Item, ItemKind, Playlist, PlaylistRules
from frame_server.player import RETRY_AFTER, Hold, hold_from
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


def _artwork(service, n: int, cached: bool) -> Item:
    item = service.library.upsert(
        Item(
            id=f"aic:{n}",
            source="aic",
            source_id=str(n),
            title=f"Painting {n}",
            image_url=f"https://museum.invalid/{n}.jpg",
            thumb_url=f"https://museum.invalid/{n}-small.jpg",
        )
    )
    if cached:
        service.images.store(item, jpeg_bytes((30 * n, 90, 120)))
    return item


def _offline(service) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    service.images.http = lambda: httpx.Client(transport=httpx.MockTransport(refuse))


async def test_offline_change_takes_a_cached_picture(service) -> None:
    missing = _artwork(service, 1, cached=False)
    ready = _artwork(service, 2, cached=True)
    _offline(service)
    state = service.player.state
    state.queue = [missing.id, ready.id]
    service.player._save_state(state)

    shown = await service.player.next()

    assert shown is not None and shown.id == ready.id
    assert service.player.state.current_item_id == ready.id
    assert missing.id in service.player.state.queue  # tried again later


async def test_offline_with_nothing_cached_keeps_the_picture_and_retries(service) -> None:
    missing = _artwork(service, 1, cached=False)
    _offline(service)
    state = service.player.state
    state.queue = [missing.id]
    service.player._save_state(state)

    assert await service.player.next() is None
    state = service.player.state
    assert state.current_item_id is None
    assert "Painting 1" in (state.last_error or "")
    retry = datetime.fromisoformat(state.next_change_at or "")
    assert retry > datetime.now(UTC) + RETRY_AFTER - timedelta(minutes=1)


def test_cache_drops_least_recently_used_museum_originals(service) -> None:
    import os

    old, recent, current = (_artwork(service, n, cached=True) for n in (1, 2, 3))
    own = _add(service, 4, (200, 40, 40), "Ala")
    images = service.images
    for age, item in ((3000, old), (2000, recent), (1000, current)):
        stamp = datetime.now(UTC).timestamp() - age
        os.utime(images.image_path(item), (stamp, stamp))
    images.ensure_image(recent)  # used just now
    state = service.player.state
    state.current_item_id = current.id
    service.player._save_state(state)

    # Room for about two originals: the oldest unused one goes first.
    sizes = sorted(p.stat().st_size for p in images.images.glob("*.jpg"))
    assert images.prune(sum(sizes) - 1, [current, own]) == 1
    assert not images.has_image(old) and images.has_image(recent)

    service.settings.image_cache_mb = 0
    service.player.trim_cache()
    assert not images.has_image(recent)
    assert images.has_image(current)  # on the frame now
    assert images.has_image(own)  # an upload cannot be downloaded again


def test_museum_works_join_the_library_only_when_kept(service, monkeypatch) -> None:
    from frame_server.library.museums import MUSEUMS, Museum
    from frame_server.web import create_app

    fetched: list[str] = []

    class Fake(Museum):
        key = "fake"
        name = "Fake Museum"

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            return 0, []

        def fetch(self, source_id: str) -> Item | None:
            fetched.append(source_id)
            url = f"https://museum.invalid/{source_id}.jpg"
            return self._item(source_id, title=f"Work {source_id}", image_url=url, thumb_url=url)

    monkeypatch.setitem(MUSEUMS, "fake", Fake)
    app = create_app(service.settings)
    svc = app.state.service
    picture = jpeg_bytes((40, 40, 200))
    svc.images.http = lambda: httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=picture))
    )
    playlist = svc.library.save_playlist(Playlist(name="Mine", kind="manual"))

    with TestClient(app) as client:
        # Browsing: details and pictures, nothing kept.
        assert client.get("/api/library/items/fake:1").json()["title"] == "Work 1"
        assert client.get("/api/library/items/fake:1/thumb").status_code == 200
        assert client.get("/api/library/items/fake:1/preview").status_code == 200
        assert not svc.library.has("fake:1")
        assert fetched == ["1"]  # remembered after the first request
        assert client.get("/api/library/items/nope:1").status_code == 404

        # A heart or a playlist keeps the work, with its colours.
        liked = client.patch("/api/library/items/fake:1", json={"favorite": True}).json()
        assert liked["favorite"] and liked["colors"]
        assert svc.library.get("fake:1").favorite
        client.post(f"/api/playlists/{playlist.id}/items", json={"item_ids": ["fake:2"]})
        assert svc.library.has("fake:2")
        assert client.get("/api/library/items/fake:3/thumb").status_code == 200

    # Browsed thumbnails beyond the spare ones go with the next trim.
    svc.images.prune_thumbs(svc.library.query()[1], spare=0)
    assert svc.images.thumb_path(svc.library.get("fake:1")).is_file()
    assert not svc.images.thumb_path(svc.importer.remote("fake:3")).is_file()
