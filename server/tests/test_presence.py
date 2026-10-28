"""Is the panel on the network: rtnetlink parsing and the verdict."""

from __future__ import annotations

import errno
import socket
import struct
import sys

import pytest

from frame_server.device import presence
from frame_server.device.mdc import MdcConnectionError
from frame_server.device.presence import (
    NUD_DELAY,
    NUD_FAILED,
    NUD_INCOMPLETE,
    NUD_REACHABLE,
    NUD_STALE,
    Neighbour,
    connect_says_gone,
    parse_neighbours,
    verdict,
)


def _attr(kind: int, value: bytes) -> bytes:
    raw = struct.pack("=HH", 4 + len(value), kind) + value
    return raw + b"\0" * (-len(raw) % 4)


def _neigh(ip: str, mac: str | None, state: int, family: int = socket.AF_INET) -> bytes:
    body = struct.pack("=BBHiHBB", family, 0, 0, 3, state, 0, 1)
    dst = socket.inet_aton(ip) if family == socket.AF_INET else b"\0" * 16
    body += _attr(presence.NDA_DST, dst)
    if mac:
        body += _attr(presence.NDA_LLADDR, bytes.fromhex(mac.replace(":", "")))
    return struct.pack("=IHHII", 16 + len(body), presence.RTM_NEWNEIGH, 2, 1, 0) + body


def _done() -> bytes:
    return struct.pack("=IHHII", 20, presence.NLMSG_DONE, 2, 1, 0) + b"\0" * 4


def test_parse_a_dump() -> None:
    data = (
        _neigh("192.0.2.20", "00:00:5e:00:53:01", NUD_REACHABLE)
        + _neigh("192.0.2.9", None, NUD_FAILED)
        + _neigh("::", None, NUD_STALE, family=socket.AF_INET6)
    )
    entries, done = parse_neighbours(data)
    assert not done
    assert entries == [
        Neighbour("192.0.2.20", "00:00:5e:00:53:01", NUD_REACHABLE, 3),
        Neighbour("192.0.2.9", None, NUD_FAILED, 3),
    ]
    assert parse_neighbours(_done()) == ([], True)


def test_parse_an_error() -> None:
    data = struct.pack("=IHHII", 36, presence.NLMSG_ERROR, 0, 1, 0) + struct.pack("=i", -1)
    with pytest.raises(OSError):
        parse_neighbours(data + b"\0" * 16)


def test_verdict() -> None:
    assert verdict([NUD_REACHABLE]) is True
    assert verdict([NUD_FAILED]) is False
    assert verdict([NUD_FAILED, NUD_REACHABLE]) is True  # two interfaces
    assert verdict([NUD_INCOMPLETE]) is None  # still asking
    assert verdict([NUD_STALE]) is None
    assert verdict([]) is None


def test_connect_errors() -> None:
    def failed(code: int) -> MdcConnectionError:
        try:
            try:
                raise OSError(code, "nope")
            except OSError as err:
                raise MdcConnectionError("cannot reach") from err
        except MdcConnectionError as err:
            return err

    assert connect_says_gone(failed(errno.EHOSTUNREACH).__cause__)
    assert connect_says_gone(failed(errno.EHOSTDOWN))
    assert not connect_says_gone(failed(errno.ECONNREFUSED))
    assert not connect_says_gone(MdcConnectionError("timed out"))


@pytest.mark.skipif(not hasattr(socket, "AF_NETLINK"), reason="rtnetlink is Linux only")
def test_read_the_real_table() -> None:
    entries = presence.neighbours()
    assert all(isinstance(n, Neighbour) for n in entries)


@pytest.mark.skipif(sys.platform != "linux", reason="rtnetlink is Linux only")
@pytest.mark.parametrize(
    ("tables", "expected"),
    [
        ([[NUD_STALE], [NUD_DELAY], [NUD_REACHABLE]], True),
        ([[NUD_INCOMPLETE], [NUD_FAILED]], False),
        ([[NUD_INCOMPLETE]] * 50, False),  # nobody answers before the deadline
        ([[NUD_STALE]] * 50, None),
        ([[]], None),  # no entry at all: behind a router
    ],
)
async def test_on_network(
    monkeypatch: pytest.MonkeyPatch, tables: list[list[int]], expected: bool | None
) -> None:
    reads = iter(tables)
    nudged: list[str] = []

    def table() -> list[Neighbour]:
        states = next(reads, tables[-1])
        return [Neighbour("10.0.0.7", None, s, 2) for s in states]

    monkeypatch.setattr(presence, "neighbours", table)
    monkeypatch.setattr(presence, "_nudge", nudged.append)
    assert await presence.on_network("10.0.0.7", wait=0.2, interval=0.01) is expected
    assert nudged == ["10.0.0.7"]
