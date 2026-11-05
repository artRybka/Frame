"""The event loop's watcher: a loop held up by work done on it is logged,
with where it stood."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from frame_server.loopwatch import LoopWatch


def held_up(seconds: float) -> None:
    time.sleep(seconds)  # work that belongs in a thread


async def test_a_loop_held_up_is_logged_with_its_stack(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="frame_server.loopwatch")
    watch = LoopWatch(stall=0.3, every=10.0, beat=0.05)
    task = asyncio.create_task(watch.run())
    await asyncio.sleep(0.2)
    held_up(0.8)
    await asyncio.sleep(0.2)
    task.cancel()
    texts = [r.getMessage() for r in caplog.records]
    stuck = [t for t in texts if "has stood still" in t]
    assert len(stuck) == 1  # once per stall, not every look
    assert "held_up" in stuck[0]  # where the loop was
    assert any(t.startswith("the event loop stood still for") for t in texts)


async def test_a_loop_that_moves_is_quiet(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="frame_server.loopwatch")
    watch = LoopWatch(stall=0.3, every=10.0, beat=0.05)
    task = asyncio.create_task(watch.run())
    for _ in range(10):
        held_up(0.05)
        await asyncio.sleep(0.05)
    task.cancel()
    assert not caplog.records


async def test_a_long_stall_is_shown_again(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="frame_server.loopwatch")
    watch = LoopWatch(stall=0.2, every=0.4, beat=0.05)
    task = asyncio.create_task(watch.run())
    await asyncio.sleep(0.1)
    held_up(1.2)
    await asyncio.sleep(0.1)
    task.cancel()
    stuck = [r for r in caplog.records if "has stood still" in r.getMessage()]
    assert 2 <= len(stuck) <= 3
