"""The progress bar: stages, estimates, and the way pushes report them."""

from __future__ import annotations

from conftest import jpeg_bytes

from frame_server.device import MdcConnectionError
from frame_server.library import ItemKind
from frame_server.progress import DEFAULT_SECONDS, ProgressTracker, Stage


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_picture_goes_through_the_three_phases() -> None:
    clock = Clock()
    tracker = ProgressTracker(clock)
    assert tracker.view().stage == Stage.IDLE and not tracker.view().active

    tracker.begin("Zachód słońca")
    view = tracker.view()
    assert (view.stage, view.phase, view.active) == (Stage.RENDERING, "processing", True)
    assert view.fraction == 0.0
    assert view.seconds_left == round(sum(DEFAULT_SECONDS.values()) - DEFAULT_SECONDS[Stage.WAKING])

    seen = [view.fraction]
    for stage, seconds in (
        (Stage.SENDING, 10),
        (Stage.DOWNLOADING, 2),
        (Stage.REFRESHING, 3),
    ):
        clock.now += seconds
        tracker.advance(stage)
        seen.append(tracker.view().fraction)
    assert tracker.view().phase == "displaying"
    clock.now += 20
    seen.append(tracker.view().fraction)
    assert seen == sorted(seen) and seen[-1] < 1

    clock.now += DEFAULT_SECONDS[Stage.REFRESHING]
    view = tracker.view()
    assert (view.stage, view.active, view.fraction) == (Stage.DONE, False, 1.0)
    assert view.finished_at is not None and view.title == "Zachód słońca"


def test_the_bar_never_goes_back_and_never_ends_early() -> None:
    clock = Clock()
    tracker = ProgressTracker(clock)
    tracker.begin("x")
    clock.now += 600  # a very slow render
    late = tracker.view().fraction
    assert late < 0.99
    tracker.advance(Stage.SENDING)
    clock.now += 1
    tracker.advance(Stage.WAKING)  # waking adds time ahead
    assert tracker.view().fraction >= late
    assert tracker.view().phase == "loading"


def test_durations_are_learned_but_not_from_a_wake() -> None:
    clock = Clock()
    tracker = ProgressTracker(clock)
    tracker.begin("x")
    clock.now += 4
    tracker.advance(Stage.SENDING)
    assert tracker.expected[Stage.RENDERING] == (DEFAULT_SECONDS[Stage.RENDERING] + 4) / 2
    clock.now += 20
    tracker.advance(Stage.WAKING)
    assert tracker.expected[Stage.SENDING] == DEFAULT_SECONDS[Stage.SENDING]


def test_waiting_and_failing_keep_their_reason() -> None:
    tracker = ProgressTracker(Clock())
    tracker.begin("x", render=False)
    assert tracker.view().stage == Stage.SENDING
    tracker.finish(Stage.WAITING, "panel asleep")
    tracker.finish(Stage.FAILED, "later error")
    view = tracker.view()
    assert (view.stage, view.message, view.active) == (Stage.WAITING, "panel asleep", False)
    tracker.advance(Stage.DOWNLOADING)  # nothing on its way: ignored
    assert tracker.view().stage == Stage.WAITING


async def test_unreachable_panel_leaves_the_picture_waiting(service) -> None:
    service.settings.device_host, service.settings.device_pin = "127.0.0.1", "1"

    async def unreachable(url: str) -> None:
        raise MdcConnectionError("no route")

    service.panel.set_content_url = unreachable  # type: ignore[method-assign]
    outcome = await service.push_current(wait=1)
    assert not outcome.pushed
    view = service.progress.view()
    assert view.stage == Stage.WAITING and "unreachable" in (view.message or "")


async def test_fetched_picture_is_refreshing(service) -> None:
    service.settings.device_host, service.settings.device_pin = "127.0.0.1", "1"
    stages: list[Stage] = []

    async def panel_fetches(url: str) -> None:
        stages.append(service.progress.view().stage)
        content = service.store.current()
        service.store._fetch_waiters[content.file_id].set()

    service.panel.set_content_url = panel_fetches  # type: ignore[method-assign]
    outcome = await service.push_current(wait=5)
    assert outcome.fetched
    assert stages == [Stage.SENDING]
    assert service.progress.view().stage == Stage.REFRESHING


async def test_player_failure_ends_the_run(service) -> None:
    service.importer.add_upload(jpeg_bytes((200, 40, 40)), kind=ItemKind.OWN, title="A")
    await service.player.next()  # no panel configured
    view = service.progress.view()
    assert view.stage == Stage.FAILED and "not configured" in (view.message or "")
