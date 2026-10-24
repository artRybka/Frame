"""Wake-on-LAN for a panel sleeping with network standby enabled."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(mac.replace(":", "").replace("-", "").replace(".", ""))
    if len(raw) != 6:
        raise ValueError(f"invalid MAC address {mac!r}")
    return b"\xff" * 6 + raw * 16


def broadcast_targets(host_ip: str | None) -> list[str]:
    """Limited broadcast, the /24 directed broadcast and the panel itself.

    Wired hosts do not always forward 255.255.255.255 onto the WLAN, the
    directed broadcast usually gets through. The unicast copy is the only one
    a router forwards from another subnet (the server on Synology), and access
    points deliver it to a dozing client without waiting for a DTIM beacon.
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
        if host_ip not in targets:
            targets.append(host_ip)
    return targets


async def wake(
    mac: str, host_ip: str | None = None, repeats: int = 3, interval: float = 0.2
) -> None:
    """Send the magic packet `repeats` times, `interval` seconds apart.

    A sleeping Wi-Fi client only listens every few beacons, so a longer burst
    (e.g. 60 x 1 s) is what the battery wake experiments use.
    """
    packet = magic_packet(mac)
    loop = asyncio.get_running_loop()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        for _ in range(repeats):
            for target in broadcast_targets(host_ip):
                for port in (9, 7):
                    # No route or no ARP answer for the unicast copy.
                    with contextlib.suppress(OSError):
                        await loop.sock_sendto(sock, packet, (target, port))
            await asyncio.sleep(interval)
