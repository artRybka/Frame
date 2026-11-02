"""The night queue: heavy work at night, one task at a time, waiting while
the app is in use (night.py)."""

from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from test_pools import _wait, museums  # noqa: F401  (fixture)

from frame_server import night
from frame_server.night import DONE_KEY, Night, NightQueue, NightTask

WARSAW = ZoneInfo("Europe/Warsaw")


def _at(hour: int, minute: int = 0, day: int = 3) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=WARSAW)


def _queue(service, tasks=(), now=None) -> NightQueue:
    return NightQueue(service, list(tasks), now=now)


def test_the_night_begins_at_half_past_one_in_the_frames_time(service) -> None:
    queue = _queue(service)
    assert queue.last_night(_at(1, 0)) == date(2026, 11, 2)
    assert queue.last_night(_at(1, 30)) == date(2026, 11, 3)
    assert queue.until_next(_at(1, 0)) == 30 * 60
    assert queue.until_next(_at(2, 0)) == 23.5 * 3600
    assert queue.left(_at(2, 0)) == 4 * 3600
    assert queue.left(_at(12, 0)) == 0


def test_a_missed_night_is_made_up(service) -> None:
    queue = _queue(service)
    assert queue.missed(_at(12, 0))  # never worked
    service.library.set_state(DONE_KEY, "2026-11-03")
    assert not queue.missed(_at(12, 0))
    assert not queue.missed(_at(1, 0, day=4))  # tonight not begun yet
    assert queue.missed(_at(2, 0, day=4))


def test_tasks_run_in_order_and_the_night_is_done(service, monkeypatch) -> None:
    monkeypatch.setattr(night, "_last_used", time.monotonic() - 3600)
    done: list[str] = []
    tasks = [NightTask(n, lambda _night, n=n: done.append(n)) for n in ("a", "b")]
    tasks.insert(1, NightTask("broken", lambda _night: 1 / 0))
    queue = _queue(service, tasks)
    ran = queue.work(date(2026, 11, 3), 60)
    assert done == ["a", "b"]  # a task failing does not stop the others
    assert set(ran.took) == {"a", "broken", "b"}
    assert service.library.get_state(DONE_KEY) == "2026-11-03"


def test_the_night_waits_while_the_app_is_in_use(service, monkeypatch) -> None:
    monkeypatch.setattr(night, "QUIET_LOOK", 0.01)
    night.used()
    done: list[str] = []
    queue = _queue(service, [NightTask("a", lambda _night: done.append("a"))])
    queue.work(date(2026, 11, 3), 0.1)
    assert done == []  # used just now: left for the next night
    monkeypatch.setattr(night, "_last_used", time.monotonic() - 3600)
    service.player._changes = 1  # a picture going to the frame
    assert service.player.busy
    assert not Night(threading.Event(), time.monotonic() + 0.1, lambda: True).quiet()


def test_by_day_only_the_originals_are_trimmed(service) -> None:
    images = service.images
    images.thumbs.mkdir(parents=True, exist_ok=True)
    browsed = [images.thumbs / f"browsed-{n}.jpg" for n in range(3)]
    for n, path in enumerate(browsed):
        path.write_bytes(b"x")
        os.utime(path, (n, n))
    called: list[str] = []
    service.player.drop_spare_copies = lambda: called.append("spare") or 0
    service.player.trim_cache(whole=False)
    assert called == [] and all(p.is_file() for p in browsed)
    service.player.trim_cache()
    assert called == ["spare"]


def test_a_full_catalogue_turns_over_only_at_night(museums, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setattr(night, "_last_used", time.monotonic() - 3600)
    service = museums
    player = service.player
    player.at_night = True
    _wait(player.grow_catalogue())  # still filling up: by day too
    service.settings.catalogue_mb = 1
    service.images.thumbs_size = lambda: 2 * 1024 * 1024  # full
    assert player.grow_catalogue() is None
    stop = threading.Event()
    batches = player.grow_at_night(Night(stop, time.monotonic() + 30))
    assert batches == 1  # a day's works at once
    # Not counted again by day: the night measures it.
    service.images.thumbs_size = lambda: 0
    assert player.grow_catalogue() is None


def test_the_nga_index_is_rebuilt_at_night_before_a_search_would(tmp_path, monkeypatch) -> None:
    from frame_server.library import nga

    built: list[str] = []

    def build(path, http) -> int:
        path.write_text("index")
        built.append(path.name)
        return 1

    monkeypatch.setattr(nga, "build", build)
    path = tmp_path / "nga" / "collection.sqlite"
    assert not nga.refresh_at_night(tmp_path)  # never searched: left to a search
    path.parent.mkdir()
    path.write_text("old")
    assert not nga.refresh_at_night(tmp_path)  # fresh
    old = time.time() - nga.NIGHT_REFRESH_SECONDS - 60
    os.utime(path, (old, old))
    assert nga.refresh_at_night(tmp_path)
    assert built == ["collection.sqlite"]


def test_birthdays_are_looked_up_at_night(service, monkeypatch) -> None:
    from frame_server.notifications import BIRTHS_BATCH, births_at_night

    artists = [f"Artist {n}" for n in range(BIRTHS_BATCH + 3)]
    births = service.births
    monkeypatch.setattr(service.notifier, "wanted", lambda kind: True)
    asked: list[list[str]] = []
    monkeypatch.setattr(births, "look_up", lambda batch: asked.append(batch) or len(batch))
    monkeypatch.setattr(night, "_last_used", time.monotonic() - 3600)

    class Counts(dict):
        def most_common(self):
            return list(self.items())

    monkeypatch.setattr(births, "favourites", lambda user=None: Counts.fromkeys(artists, 1))
    kept = births_at_night(service, Night(threading.Event(), time.monotonic() + 30))
    assert kept == len(artists)
    assert [len(b) for b in asked] == [BIRTHS_BATCH, 3]


def test_a_picture_shown_leaves_the_catalogue_as_it_was(service) -> None:
    from frame_server.library import Item, ItemKind

    library = service.library
    work = library.upsert(Item(id="cma:1", source="cma", source_id="1", kind=ItemKind.ARTWORK))
    stamp = library.catalogue_stamp()
    library.update(work.id, last_shown_at="2026-11-02T10:00:00+00:00")
    assert library.catalogue_stamp() == stamp
    library.update(work.id, excluded=True)  # "Ukryj dzieło"
    assert library.catalogue_stamp() != stamp


async def test_teraz_does_not_go_through_the_playlist_at_every_look(service, monkeypatch) -> None:
    from datetime import UTC, datetime

    from test_player import _add

    from frame_server.library import Playlist, PlaylistRules

    works = [_add(service, n, (40 * n, 40, 200), "Ala") for n in range(1, 5)]
    lately = datetime.now(UTC).isoformat(timespec="seconds")
    for item in works[:3]:
        service.library.update(item.id, favorite=True, last_shown_at=lately)
    playlist = service.library.save_playlist(
        Playlist(name="Ulubione", rules=PlaylistRules(favorites_only=True))
    )
    player = service.player
    player.at_night = True
    settings = player.settings
    settings.playlist_id = playlist.id
    player.save_settings(settings)
    await player.next()
    player.upcoming(8)
    looked: list[int] = []
    real = player.candidates
    monkeypatch.setattr(player, "candidates", lambda s=None: looked.append(1) or real(s))
    player.upcoming(8)
    player.upcoming(8)
    assert looked == []  # nothing changed: the line as it is
    service.library.update(works[3].id, favorite=True)  # a heart: looked at once
    assert player.upcoming(8)[0].id == works[3].id
    assert looked


def test_discover_keeps_its_cards_and_rows_while_the_catalogue_stays(museums, monkeypatch) -> None:  # noqa: F811
    from frame_server.library import Item, ItemKind
    from frame_server.web import discover_api

    service = museums
    library = service.library
    discover_api._cards = (0.0, {})
    discover_api._rows.clear()
    discover_api._theme_rows.clear()
    cards = discover_api.work_out_cards(service)
    discover_api.suggestion_rows(service)  # the museums' row of the day comes in
    rows = discover_api.suggestion_rows(service)
    discover_api._cards = (0.0, cards)  # older than CARDS_TTL
    assert not discover_api._cards_stale(service, 0.0)
    assert discover_api.suggestion_rows(service) is rows
    work = library.upsert(Item(id="cma:9", source="cma", source_id="9", kind=ItemKind.ARTWORK))
    assert discover_api._cards_stale(service, 0.0)
    assert discover_api.suggestion_rows(service) is not rows
    assert discover_api.work_out_cards(service) is not cards
    # Hearts alone: worked out again only once the cards are old enough.
    library.update(work.id, favorite=True)
    stamp = discover_api._cards[0]
    assert not discover_api._cards_stale(service, stamp)
    assert discover_api._cards_stale(service, stamp - discover_api.CARDS_TTL)


def test_the_frames_next_pictures_get_sharper_copies_at_night(service, monkeypatch) -> None:
    from concurrent.futures import Future

    from test_player import _add

    monkeypatch.setattr(night, "_last_used", time.monotonic() - 3600)
    works = [_add(service, n, (40 * n, 40, 200), "Ala") for n in range(1, 4)]
    known = {works[0].id}
    monkeypatch.setattr(
        service.sharper, "status", lambda item: "fine" if item.id in known else None
    )
    looked: list[str] = []

    def soon(item):
        looked.append(item.id)
        done: Future[str] = Future()
        done.set_result("fine")
        return done

    monkeypatch.setattr(service.sharper, "soon", soon)
    (task,) = [t for t in night.tasks(service) if t.name == "sharper"]
    assert task.run(Night(threading.Event(), time.monotonic() + 30)) == 2
    assert set(looked) == {works[1].id, works[2].id}
