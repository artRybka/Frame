from __future__ import annotations

import ssl

import pytest
import trustme
from fake_panel import FakePanel, reply_frame

from frame_server.device.mdc import (
    CMD_CONTENT_DOWNLOAD,
    CMD_ON_TIMER,
    CMD_SERIAL,
    CMD_STATUS,
    MAX_URL_LENGTH,
    ON_TIMER_REPEAT,
    BatteryStatus,
    MdcAuthError,
    MdcClient,
    MdcError,
    build_frame,
    parse_reply,
)


@pytest.fixture(scope="module")
def server_ssl() -> ssl.SSLContext:
    ca = trustme.CA()
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ca.issue_cert("panel.local").configure_cert(ctx)
    return ctx


def test_build_frame_checksum() -> None:
    # Battery query as sent by the reference implementations.
    assert build_frame(0x1B, b"\x73") == bytes([0xAA, 0x1B, 0x00, 0x01, 0x73, 0x8F])


def test_parse_reply_resyncs_and_waits_for_more() -> None:
    frame = reply_frame(0x0B, b"SERIAL")
    buf = bytearray(b"\x12\xaa\x00" + frame[:5])
    assert parse_reply(buf) is None
    buf += frame[5:]
    reply = parse_reply(buf)
    assert reply is not None
    assert reply.ack and reply.command == 0x0B and reply.payload == b"SERIAL"
    assert buf == bytearray()


@pytest.mark.parametrize("skew", [-1, 0, 1])
def test_parse_reply_tolerates_length_skew(skew: int) -> None:
    buf = bytearray(reply_frame(0x0E, b"S-RSEDWWC-1050.1", length_skew=skew))
    reply = parse_reply(buf)
    assert reply is not None and reply.payload == b"S-RSEDWWC-1050.1"


async def test_session_commands(server_ssl: ssl.SSLContext) -> None:
    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_SERIAL:
            return True, b"0K1X3ABC00001\x00"
        if command == CMD_STATUS and data == b"\x73":
            return True, bytes([0x73, 0x00, 0x01, 0x01, 87, 0x00, 0x02])
        if command == CMD_CONTENT_DOWNLOAD:
            return True, b""
        return False, b"\x00"

    panel = FakePanel(server_ssl, handler=handler, length_skew=1)
    await panel.start()
    try:
        async with MdcClient("127.0.0.1", "123456", panel.port, command_interval=0) as mdc:
            assert await mdc.serial_number() == "0K1X3ABC00001"
            battery = await mdc.battery()
            assert battery.level == 87
            url = "http://192.168.1.10:8099/device/content.json"
            await mdc.content_download(url)
            with pytest.raises(MdcError, match="NAK"):
                await mdc.command(0x99)
    finally:
        await panel.stop()

    command, data = panel.received[2]
    assert command == CMD_CONTENT_DOWNLOAD
    assert data[:3] == bytes([0x53, 0x80, len(url)]) and data[3:] == url.encode()


async def test_wrong_pin(server_ssl: ssl.SSLContext) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        with pytest.raises(MdcAuthError, match="incorrect PIN"):
            async with MdcClient("127.0.0.1", "000000", panel.port):
                pass
    finally:
        await panel.stop()


async def test_url_too_long(server_ssl: ssl.SSLContext) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        async with MdcClient("127.0.0.1", "123456", panel.port) as mdc:
            with pytest.raises(MdcError, match="longer"):
                await mdc.content_download("http://x/" + "a" * MAX_URL_LENGTH)
    finally:
        await panel.stop()


async def test_on_timer(server_ssl: ssl.SSLContext) -> None:
    state = {"timer": b"\x00"}

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_ON_TIMER:
            if data:
                state["timer"] = data[:4]
            return True, state["timer"]
        return False, b"\x00"

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    try:
        async with MdcClient("127.0.0.1", "123456", panel.port, command_interval=0) as mdc:
            disabled = await mdc.on_timer()
            assert not disabled.enabled and disabled.hour is None
            await mdc.set_on_timer(7, 5, ON_TIMER_REPEAT["daily"])
            timer = await mdc.on_timer()
            assert timer.enabled and (timer.hour, timer.minute, timer.repeat) == (7, 5, 0x02)
            with pytest.raises(MdcError, match="invalid"):
                await mdc.set_on_timer(24, 0)
    finally:
        await panel.stop()

    assert (CMD_ON_TIMER, bytes([0x01, 0x02, 7, 5, 0x01])) in panel.received


def test_battery_external_power() -> None:
    # Raw replies read from an EM32DX (firmware S-RSEDWWC-1130.7), experiment E1.
    plugged = BatteryStatus(level=100, raw=bytes.fromhex("73000101640202"), flags=())
    unplugged = BatteryStatus(level=100, raw=bytes.fromhex("73000101640200"), flags=())
    assert plugged.external_power is True
    assert unplugged.external_power is False
    assert BatteryStatus(level=50, raw=bytes.fromhex("7300010132"), flags=()).external_power is None
