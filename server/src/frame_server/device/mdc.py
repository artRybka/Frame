"""Samsung MDC (Multiple Display Control) client for the EM32DX e-paper panel.

Wire protocol as observed on the EM32DX (see docs/DEVICE_PROTOCOL.md):

    TCP :1515  <- "MDCSTART<<TLS>>"
               -> TLS handshake on the same socket (self-signed cert)
               -> PIN as ASCII
               <- "MDCAUTH<<PASS>>" | "MDCAUTH<<FAIL:0xNN>>"

    command:   AA cmd id len data... chk        chk = sum(cmd..data) & 0xFF
    reply:     AA FF id len A|N rcmd data... chk chk = sum(FF..data) & 0xFF

The panel serves a single session at a time and keeps a dead one reserved for
up to a minute, so callers should open a session, do their work and close it.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass
from types import TracebackType

log = logging.getLogger(__name__)

PORT = 1515
HEADER = 0xAA
RESPONSE = 0xFF
ACK = 0x41
NAK = 0x4E

GREETING = b"MDCSTART<<TLS>>"
AUTH_PASS = b"MDCAUTH<<PASS>>"
AUTH_FAIL_PREFIX = b"MDCAUTH<<FAIL"
AUTH_FAIL_REASONS = {
    b"0x01": "incorrect PIN",
    b"0x02": "blocked after too many failed attempts",
}

# Command ids seen working on the EM32DX. Anything else: use MdcClient.command().
CMD_SERIAL = 0x0B
CMD_SW_VERSION = 0x0E
CMD_MODEL_NAME = 0x10
CMD_POWER = 0x11
CMD_STATUS = 0x1B  # sub-command 0x73 = battery
CMD_ON_TIMER = 0x25
CMD_DEVICE_NAME = 0x67
CMD_CLOCK = 0xA7
CMD_NETWORK_STANDBY = 0xB5
CMD_CONTENT_DOWNLOAD = 0xC7

SUB_BATTERY = 0x73

# The data length is a single byte and the URL is prefixed by 3 bytes.
MAX_URL_LENGTH = 255 - 3


class MdcError(Exception):
    """Protocol-level failure (NAK, malformed reply, bad argument)."""


class MdcConnectionError(MdcError):
    """Panel unreachable, asleep, busy with another session, or link dropped."""


class MdcAuthError(MdcError):
    """PIN rejected or panel locked after failed attempts."""


@dataclass(frozen=True)
class MdcReply:
    display_id: int
    ack: bool
    command: int
    payload: bytes
    raw: bytes


@dataclass(frozen=True)
class BatteryStatus:
    level: int
    raw: bytes
    # The meaning of the other bytes is not settled yet (two reference
    # implementations disagree); experiment E1 in docs/EXPERIMENTS.md.
    flags: tuple[int, ...]


def build_frame(command: int, data: bytes = b"", display_id: int = 0x00) -> bytes:
    if len(data) > 0xFF:
        raise MdcError(f"MDC payload too long ({len(data)} bytes)")
    body = bytes([command, display_id, len(data)]) + data
    return bytes([HEADER]) + body + bytes([sum(body) & 0xFF])


def _checksum_ok(frame: bytes) -> bool:
    return frame[-1] == sum(frame[1:-1]) & 0xFF


def parse_reply(buf: bytearray) -> MdcReply | None:
    """Pop one reply frame off the front of ``buf``.

    Returns None when more bytes are needed. Garbage before a header byte is
    discarded. The EM32DX is not consistent about the length byte (it is off
    by one for some replies), so each plausible frame size is accepted only
    if its checksum matches.
    """
    while True:
        try:
            start = buf.index(HEADER)
        except ValueError:
            buf.clear()
            return None
        del buf[:start]
        if len(buf) < 4:
            return None
        if buf[1] != RESPONSE:
            del buf[:1]
            continue
        length = buf[3]
        candidates = [5 + length + extra for extra in (0, 1, -1)]
        candidates = [n for n in candidates if n >= 7]
        if max(candidates) > len(buf) and not any(
            n <= len(buf) and _checksum_ok(bytes(buf[:n])) for n in candidates
        ):
            return None
        for n in candidates:
            if n <= len(buf) and _checksum_ok(bytes(buf[:n])):
                frame = bytes(buf[:n])
                del buf[:n]
                return MdcReply(
                    display_id=frame[2],
                    ack=frame[4] == ACK,
                    command=frame[5],
                    payload=frame[6:-1],
                    raw=frame,
                )
        # Header byte that does not start a valid frame: resync.
        del buf[:1]


def _insecure_tls_context() -> ssl.SSLContext:
    # The panel presents a self-signed certificate; there is nothing to verify
    # it against. The PIN is what authenticates the session.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class MdcClient:
    """One MDC session. Use as ``async with MdcClient(host, pin) as mdc: ...``."""

    def __init__(
        self,
        host: str,
        pin: str,
        port: int = PORT,
        *,
        display_id: int = 0x00,
        timeout: float = 10.0,
        command_interval: float = 0.3,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.host = host
        self.pin = pin
        self.port = port
        self.display_id = display_id
        self.timeout = timeout
        # The panel starts dropping commands after a burst; keep a gentle pace.
        self.command_interval = command_interval
        self._ssl_context = ssl_context or _insecure_tls_context()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buf = bytearray()
        self._lock = asyncio.Lock()
        self._last_command = 0.0

    async def __aenter__(self) -> MdcClient:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def connect(self, attempts: int = 1, retry_delay: float = 8.0) -> None:
        """Open and authenticate a session.

        With ``attempts > 1`` connection failures are retried, which helps
        when the panel is still holding on to a previous dead session.
        """
        last: MdcConnectionError | None = None
        for attempt in range(attempts):
            try:
                await self._connect_once()
                return
            except MdcConnectionError as err:
                last = err
                if attempt + 1 < attempts:
                    log.info("MDC connect failed (%s), retrying in %.0fs", err, retry_delay)
                    await asyncio.sleep(retry_delay)
        assert last is not None
        raise last

    async def _connect_once(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, TimeoutError) as err:
            raise MdcConnectionError(f"cannot reach {self.host}:{self.port}: {err}") from err

        try:
            greeting = await asyncio.wait_for(reader.readexactly(len(GREETING)), self.timeout)
            if greeting != GREETING:
                raise MdcConnectionError(f"unexpected greeting {greeting!r}")
            await writer.start_tls(self._ssl_context)
            writer.write(self.pin.encode("ascii"))
            await writer.drain()
            verdict = await asyncio.wait_for(self._read_auth(reader), self.timeout)
        except (OSError, ssl.SSLError, TimeoutError, asyncio.IncompleteReadError) as err:
            writer.close()
            raise MdcConnectionError(f"handshake with {self.host} failed: {err}") from err
        except MdcError:
            writer.close()
            raise

        if verdict != AUTH_PASS:
            writer.close()
            if verdict.startswith(AUTH_FAIL_PREFIX):
                code = verdict[len(AUTH_FAIL_PREFIX) + 1 : -2]
                reason = AUTH_FAIL_REASONS.get(code, code.decode(errors="replace"))
                raise MdcAuthError(f"authentication failed: {reason}")
            raise MdcConnectionError(f"unexpected auth reply {verdict!r}")

        self._reader, self._writer = reader, writer
        self._buf.clear()
        log.debug("MDC session open to %s", self.host)

    @staticmethod
    async def _read_auth(reader: asyncio.StreamReader) -> bytes:
        data = b""
        while not data.endswith(b">>"):
            chunk = await reader.read(64)
            if not chunk:
                raise MdcConnectionError("connection closed during authentication")
            data += chunk
        return data

    async def close(self) -> None:
        writer, self._reader, self._writer = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 3)
        except (OSError, ssl.SSLError, TimeoutError):
            pass

    async def command(self, command: int, data: bytes = b"") -> MdcReply:
        """Send one command and return its reply. Raises MdcError on NAK."""
        reply = await self.command_raw(command, data)
        if not reply.ack:
            raise MdcError(f"NAK for command 0x{command:02X}: {reply.payload.hex(' ')}")
        return reply

    async def command_raw(self, command: int, data: bytes = b"") -> MdcReply:
        """Like command() but returns NAK replies instead of raising."""
        if self._writer is None or self._reader is None:
            raise MdcError("not connected")
        async with self._lock:
            loop = asyncio.get_running_loop()
            wait = self._last_command + self.command_interval - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            self._writer.write(build_frame(command, data, self.display_id))
            await self._writer.drain()
            try:
                reply = await asyncio.wait_for(self._read_reply(command), self.timeout)
            except (TimeoutError, OSError, ssl.SSLError) as err:
                raise MdcConnectionError(f"no reply to 0x{command:02X}: {err}") from err
            finally:
                self._last_command = loop.time()
        return reply

    async def _read_reply(self, command: int) -> MdcReply:
        assert self._reader is not None
        while True:
            reply = parse_reply(self._buf)
            if reply is not None:
                if reply.command == command:
                    return reply
                log.debug("ignoring unsolicited reply %s", reply.raw.hex(" "))
                continue
            chunk = await self._reader.read(256)
            if not chunk:
                raise MdcConnectionError("connection closed by panel")
            self._buf += chunk

    # -- high level -------------------------------------------------------

    async def _text(self, command: int) -> str:
        reply = await self.command(command)
        return reply.payload.rstrip(b"\x00").decode(errors="replace")

    async def serial_number(self) -> str:
        return await self._text(CMD_SERIAL)

    async def software_version(self) -> str:
        return await self._text(CMD_SW_VERSION)

    async def model_name(self) -> str:
        return await self._text(CMD_MODEL_NAME)

    async def device_name(self) -> str:
        return await self._text(CMD_DEVICE_NAME)

    async def battery(self) -> BatteryStatus:
        reply = await self.command(CMD_STATUS, bytes([SUB_BATTERY]))
        p = reply.payload
        if len(p) < 5 or p[0] != SUB_BATTERY:
            raise MdcError(f"unexpected battery reply {p.hex(' ')}")
        return BatteryStatus(level=p[4], raw=p, flags=tuple(p[1:4]) + tuple(p[5:]))

    async def set_power(self, on: bool) -> None:
        await self.command(CMD_POWER, bytes([0x01 if on else 0x00]))

    async def network_standby(self) -> bool:
        reply = await self.command(CMD_NETWORK_STANDBY)
        if not reply.payload:
            raise MdcError("empty network standby reply")
        return reply.payload[0] == 0x01

    async def set_network_standby(self, enabled: bool) -> None:
        await self.command(CMD_NETWORK_STANDBY, bytes([0x01 if enabled else 0x00]))

    async def content_download(self, url: str) -> None:
        """Point the panel at a content manifest (content.json) to fetch."""
        encoded = url.encode("ascii")
        if len(encoded) > MAX_URL_LENGTH:
            raise MdcError(f"content URL longer than {MAX_URL_LENGTH} characters")
        await self.command(CMD_CONTENT_DOWNLOAD, bytes([0x53, 0x80, len(encoded)]) + encoded)
