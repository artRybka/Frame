"""A minimal fake EM32DX MDC endpoint for tests."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Callable

from frame_server.device.mdc import ACK, GREETING, HEADER, NAK, RESPONSE

Handler = Callable[[int, bytes], tuple[bool, bytes] | None]


def reply_frame(command: int, payload: bytes, ack: bool = True, length_skew: int = 0) -> bytes:
    body = bytes([RESPONSE, 0x00, len(payload) + 2 + length_skew, ACK if ack else NAK, command])
    body += payload
    return bytes([HEADER]) + body + bytes([sum(body) & 0xFF])


class FakePanel:
    def __init__(
        self,
        ssl_context: ssl.SSLContext,
        pin: str = "123456",
        handler: Handler | None = None,
        length_skew: int = 0,
    ) -> None:
        self.ssl_context = ssl_context
        self.pin = pin
        self.handler = handler or (lambda cmd, data: (True, b""))
        self.length_skew = length_skew
        self.received: list[tuple[int, bytes]] = []
        self.server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            writer.write(GREETING)
            await writer.drain()
            await writer.start_tls(self.ssl_context)
            pin = await reader.read(64)
            if pin.decode() != self.pin:
                writer.write(b"MDCAUTH<<FAIL:0x01>>")
                await writer.drain()
                return
            writer.write(b"MDCAUTH<<PASS>>")
            await writer.drain()
            buf = b""
            while True:
                chunk = await reader.read(256)
                if not chunk:
                    return
                buf += chunk
                while len(buf) >= 5 and buf[0] == HEADER:
                    size = 5 + buf[3]
                    if len(buf) < size:
                        break
                    frame, buf = buf[:size], buf[size:]
                    command, data = frame[1], frame[4:-1]
                    self.received.append((command, data))
                    result = self.handler(command, data)
                    if result is None:
                        continue
                    ack, payload = result
                    # Prepend junk to exercise resync.
                    writer.write(b"\x00" + reply_frame(command, payload, ack, self.length_skew))
                    await writer.drain()
        except (ConnectionError, ssl.SSLError):
            pass
        finally:
            writer.close()
