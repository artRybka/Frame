from __future__ import annotations

import asyncio
import socket

import pytest
import uvloop

from frame_server.device.wol import broadcast_targets, magic_packet, wake


def test_magic_packet() -> None:
    packet = magic_packet("aa:bb:cc:dd:ee:ff")
    assert packet[:6] == b"\xff" * 6 and packet[6:12] == bytes.fromhex("aabbccddeeff")
    assert len(packet) == 102


def test_targets_include_the_panel_itself() -> None:
    # The unicast copy is the one a router forwards from another subnet.
    assert broadcast_targets("192.168.1.152") == [
        "255.255.255.255",
        "192.168.1.255",
        "192.168.1.152",
    ]
    assert broadcast_targets(None) == ["255.255.255.255"]


@pytest.mark.parametrize("use_uvloop", [False, True])
def test_wake_sends_under_uvicorns_event_loop(use_uvloop: bool) -> None:
    """uvicorn runs on uvloop when it is installed, and uvloop has no
    loop.sock_sendto: the packets must still go out."""
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(1.0)
    port = rx.getsockname()[1]
    try:
        coro = wake("aa:bb:cc:dd:ee:ff", "127.0.0.1", repeats=2, interval=0.01, ports=(port,))
        sent = uvloop.run(coro) if use_uvloop else asyncio.run(coro)
        assert sent >= 2
        data, _ = rx.recvfrom(200)
        assert data == magic_packet("aa:bb:cc:dd:ee:ff")
    finally:
        rx.close()
