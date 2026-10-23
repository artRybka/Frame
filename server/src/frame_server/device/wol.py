"""Wake-on-LAN for a panel sleeping with network standby enabled."""

from __future__ import annotations

import asyncio
import ipaddress
import socket


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(mac.replace(":", "").replace("-", "").replace(".", ""))
    if len(raw) != 6:
        raise ValueError(f"invalid MAC address {mac!r}")
    return b"\xff" * 6 + raw * 16


def broadcast_targets(host_ip: str | None) -> list[str]:
    """Limited broadcast plus the /24 directed broadcast of the panel's subnet.

    Wired hosts do not always forward 255.255.255.255 onto the WLAN, the
    directed broadcast usually gets through.
    """
    targets = ["255.255.255.255"]
    if host_ip:
        try:
            net = ipaddress.ip_network(f"{host_ip}/24", strict=False)
        except ValueError:
            return targets
        directed = str(net.broadcast_address)
        if directed not in targets:
            targets.append(directed)
    return targets


async def wake(mac: str, host_ip: str | None = None, repeats: int = 3) -> None:
    packet = magic_packet(mac)
    loop = asyncio.get_running_loop()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        for _ in range(repeats):
            for target in broadcast_targets(host_ip):
                await loop.sock_sendto(sock, packet, (target, 9))
            await asyncio.sleep(0.2)
