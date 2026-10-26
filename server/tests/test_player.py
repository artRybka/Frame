from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, time, timedelta

import httpx
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from pydantic import ValidationError

from frame_server.imaging.layout import Orientation
from frame_server.library import Item, ItemKind, Playlist, PlaylistRules
from frame_server.player import RETRY_AFTER, Hold, hold_from
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


def _count_renders(service, monkeypatch) -> list[int]:
    """Renders this service makes (not reused ones). Counted on its own
    cache, so a render still running in a thread from an earlier test does
    not count."""
    renders: list[int] = []
    get = service.rendered.get
    monkeypatch.setattr(
        service.rendered, "get", lambda key, make: get(key, lambda: renders.append(1) or make())
    )
    return renders


async def test_next_picture_is_rendered_ahead(service, monkeypatch) -> None:
    for n in range(3):
        _add(service, n, (200, 40 * n, 40), "Ala")
    settings = service.player.settings
    settings.shuffle = False
    service.player.save_settings(settings)
    renders = _count_renders(service, monkeypatch)

    await service.player.next()
    upcoming = service.player.state.queue[0]
    assert len(renders) == 2  # the picture shown and the one after it

    shown = await service.player.next()
    assert shown.id == upcoming
    assert service.store.current().extra["item_id"] == upcoming
    assert len(renders) == 3  # it was ready; only the one after it is new


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
        assert trial.headers["content-type"] == "image/jpeg"
        assert trial.content != saved.content
        # Named settings keep their address; the saved ones change under it.
        assert trial.headers["cache-control"] == "max-age=3600"
        assert saved.headers["cache-control"] == "no-cache"
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
        assert view["playlist"]["id"] == playlist_id

        status = client.get("/api/status").json()
        assert status["device"]["configured"] is False
        assert status["server"]["library_count"] == 3


def test_api_removes_single_works_from_playlists(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    a, b, c = (_add(svc, n, (40 * n, 40, 200), "Ala") for n in range(1, 4))

    with TestClient(app) as client:
        smart = client.post("/api/playlists", json={"name": "Ala", "rules": {"artists": ["Ala"]}})
        smart_id = smart.json()["playlist"]["id"]
        assert client.post(f"/api/playlists/{smart_id}/play").status_code == 202
        state = svc.player.state
        state.queue = [a.id, b.id]
        svc.player._save_state(state)

        # A smart playlist keeps the work out as an exception to its rules.
        detail = client.delete(f"/api/playlists/{smart_id}/items/{b.id}").json()
        assert {i["id"] for i in detail["items"]} == {a.id, c.id}
        assert detail["playlist"]["rules"]["exclude_ids"] == [b.id]
        assert detail["playlist"]["item_count"] == 2
        assert b.id not in svc.player.state.queue  # not shown next either
        assert {i.id for i in svc.player.candidates()} == {a.id, c.id}
        preview = client.post("/api/playlists/preview", json=detail["playlist"]["rules"]).json()
        assert preview["count"] == 2

        # Saving the playlist back without exceptions restores the work.
        rules = {**detail["playlist"]["rules"], "exclude_ids": []}
        restored = client.put(f"/api/playlists/{smart_id}", json={"name": "Ala", "rules": rules})
        assert restored.json()["playlist"]["item_count"] == 3

        manual = client.post(
            "/api/playlists",
            json={"name": "Wybór", "kind": "manual", "item_ids": [a.id, b.id]},
        ).json()["playlist"]["id"]
        detail = client.delete(f"/api/playlists/{manual}/items/{a.id}").json()
        assert detail["item_ids"] == [b.id]
        assert detail["playlist"]["rules"]["exclude_ids"] == []


async def test_presentation_change_waits_for_the_next_picture(service) -> None:
    item = _add(service, 1, (200, 40, 40), "Ala")
    player = service.player
    await player.show(item, "test")
    before, state = service.store.current(), player.state

    old = player.settings
    new = old.model_copy(deep=True)
    new.art.margin = 0.12
    # A new framing is only for the pictures still to come.
    assert player.presentation_changed(old, new)
    assert not player.needs_restyle(old, new)
    # Turning the screen redraws the picture on it.
    new.orientation = Orientation.PORTRAIT
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


def test_saving_presentation_keeps_the_picture_on_the_frame(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    item = _add(svc, 1, (200, 40, 40), "Ala")
    asyncio.run(svc.player.show(item, "test"))
    before = svc.store.current()
    with TestClient(app) as client:
        settings = client.get("/api/settings").json()
        settings["art"]["margin"] = 0.15
        settings["art"]["mat"] = "black"
        assert client.put("/api/settings", json=settings).status_code == 200
        assert svc.store.current().file_id == before.file_id
        assert svc.player.settings.art.margin == 0.15


def test_frame_name_is_trimmed(service) -> None:
    settings = service.player.settings
    assert settings.name is None
    settings.name = "  Salon \n przy oknie "
    assert settings.name == "Salon przy oknie"
    settings.name = "   "
    assert settings.name is None
    service.player.save_settings(settings.model_copy(update={"name": "Salon"}))
    assert service.player.settings.name == "Salon"


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


async def test_work_added_to_the_queue_is_shown_next(service, monkeypatch) -> None:
    a, _, c, d = (_add(service, n, (200, 40 * n, 40), "Ala") for n in range(4))
    playlist = service.library.save_playlist(
        Playlist(name="Ala", rules=PlaylistRules(artists=["Ala"]))
    )
    settings = service.player.settings
    settings.playlist_id = playlist.id
    settings.shuffle = False
    service.player.save_settings(settings)
    player = service.player
    await player.next()
    outsider = _add(service, 9, (40, 40, 200), "Ola")  # not in the playlist

    player.queue_next(c.id)
    player.queue_next(outsider.id)  # the latest pick goes first
    assert [i.id for i in player.upcoming(3)][:2] == [outsider.id, c.id]
    assert player.state.queue.count(c.id) == 0  # not shown twice

    renders = _count_renders(service, monkeypatch)
    await player.render_ahead()
    assert len(renders) == 1
    shown = await player.next()
    assert shown.id == outsider.id
    assert len(renders) == 2  # drawn ahead; only the one after it is new
    assert (await player.next()).id == c.id
    assert player.state.requested == []
    assert c.id not in [i.id for i in player.upcoming(8)]  # back in its own turn

    # A pick survives a new playlist and can be taken back.
    player.queue_next(a.id)
    player.queue_next(d.id)
    settings.playlist_id = None
    player.save_settings(settings)
    assert player.state.requested == [d.id, a.id]
    player.dequeue(d.id)
    assert player.upcoming(1)[0].id == a.id


async def test_queued_work_waits_while_its_original_is_unavailable(service) -> None:
    cached = _artwork(service, 1, cached=True)
    missing = _artwork(service, 2, cached=False)
    _offline(service)
    player = service.player
    player.queue_next(missing.id)

    shown = await player.next()
    assert shown is not None and shown.id == cached.id  # took its turn
    assert player.state.requested == [missing.id]  # still first in line


def test_api_adds_a_work_to_the_queue(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    _, b = (_add(svc, n, (40 * n, 40, 200), "Ala") for n in range(1, 3))

    with TestClient(app) as client:
        assert client.post(f"/api/library/items/{b.id}/queue").status_code == 202
        view = client.get("/api/player").json()
        assert view["upcoming"][0]["id"] == b.id
        assert view["queued"] == [b.id]
        assert client.post("/api/library/items/nope:1/queue").status_code == 404

        view = client.delete(f"/api/player/queue/{b.id}").json()
        assert view["queued"] == []
        assert client.post("/api/player/next").status_code == 202


async def test_liked_works_join_the_favourites_playing_now(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    a, b, c, d, e = (_add(svc, n, (40 * n, 40, 200), "Ala") for n in range(1, 6))
    for item in (a, b, c):
        svc.library.update(item.id, favorite=True)
    playlist = svc.library.save_playlist(
        Playlist(name="Ulubione", rules=PlaylistRules(favorites_only=True))
    )
    player = svc.player
    settings = player.settings
    settings.playlist_id = playlist.id
    player.save_settings(settings)
    await player.next()
    upcoming = [i.id for i in player.upcoming(8)]
    assert len(upcoming) == 2 and d.id not in upcoming

    with TestClient(app) as client:
        assert client.post(f"/api/library/items/{e.id}/queue").status_code == 202
        client.patch(f"/api/library/items/{d.id}", json={"favorite": True})
        view = client.get("/api/player").json()
        # The owner's pick first, then the picture drawn ahead, then the new favourite.
        assert [i["id"] for i in view["upcoming"]] == [e.id, upcoming[0], d.id, upcoming[1]]
        assert view["queued"] == [e.id]

        client.patch(f"/api/library/items/{upcoming[1]}", json={"favorite": False})
        client.patch(f"/api/library/items/{e.id}", json={"favorite": False})  # a pick stays
        view = client.get("/api/player").json()
        assert [i["id"] for i in view["upcoming"]] == [e.id, upcoming[0], d.id]
        favourites = next(p for p in client.get("/api/playlists").json() if p["id"] == playlist.id)
        assert favourites["item_count"] == 3


async def test_favourites_shown_lately_stay_in_the_queue(service) -> None:
    works = [_add(service, n, (40 * n, 40, 200), "Ala") for n in range(1, 7)]
    lately = datetime.now(UTC).isoformat(timespec="seconds")
    for item in works[:4]:
        service.library.update(item.id, favorite=True, last_shown_at=lately)
    playlist = service.library.save_playlist(
        Playlist(name="Ulubione", rules=PlaylistRules(favorites_only=True))
    )
    player = service.player
    settings = player.settings
    settings.playlist_id = playlist.id
    player.save_settings(settings)
    shown = await player.next()
    assert shown is not None
    others = {i.id for i in works[:4]} - {shown.id}

    new = works[4]
    service.library.update(new.id, favorite=True)
    player.playlist_changed(playlist.id)  # drawn again
    upcoming = [i.id for i in player.upcoming(8)]
    assert upcoming[0] == new.id  # not shown lately: first
    assert set(upcoming[1:]) == others  # the rest of the playlist still follows

    assert (await player.next()).id == new.id
    found = works[5]  # e.g. a top-up: in the playlist, not in the queue
    service.library.update(found.id, favorite=True)
    assert player.upcoming(8)[0].id == found.id  # before the ones shown lately
    assert (await player.next()).id == found.id


def test_library_is_scored_again_once(service) -> None:
    from frame_server.library.colors import SCORE_VERSION
    from frame_server.player import SCORE_KEY

    library = service.library
    work = service.importer.add_upload(
        jpeg_bytes((150, 150, 150)), kind=ItemKind.OWN, title="Grey", artist="Ala"
    )
    fresh = work.suitability
    assert fresh is not None and fresh <= 0.5  # no colour of its own
    library.update(work.id, suitability=0.95)  # the score of an older version
    library.set_state(SCORE_KEY, SCORE_VERSION - 1)
    assert service.player.rescore() >= 1
    assert library.get(work.id).suitability == fresh
    assert library.get_state(SCORE_KEY) == SCORE_VERSION
    library.update(work.id, suitability=0.95)
    assert service.player.rescore() == 0  # only once
