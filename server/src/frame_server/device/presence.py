"""Is the panel on the network? Asked without waking it.

Asleep with network standby on, the panel stays on the Wi-Fi but does not
answer MDC. Its Wi-Fi radio answers ARP for it (to be confirmed on the EM32DX,
experiment E15), so the kernel's neighbour table tells it apart from a panel
that is gone: after traffic to it the entry ends REACHABLE (an ARP reply came)
or FAILED (none did). The table is read over rtnetlink, which needs no
privileges; the server runs on the host network (add-on and Synology), so this
is the LAN's own table. Behind a router the panel has no entry here (ARP is the
router's business) and nothing can be told.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import ipaddress
import logging
import socket
import struct
from dataclasses import dataclass

log = logging.getLogger(__name__)

# linux/neighbour.h
NUD_INCOMPLETE = 0x01
NUD_REACHABLE = 0x02
NUD_STALE = 0x04
NUD_DELAY = 0x08
NUD_PROBE = 0x10
NUD_FAILED = 0x20
NUD_NOARP = 0x40
NUD_PERMANENT = 0x80
NDA_DST = 1
NDA_LLADDR = 2

# linux/netlink.h, linux/rtnetlink.h
NLMSG_ERROR = 2
NLMSG_DONE = 3
RTM_NEWNEIGH = 28
RTM_GETNEIGH = 30
NLM_F_REQUEST = 0x01
NLM_F_DUMP = 0x300

NLMSG_HEADER = struct.Struct("=IHHII")  # len, type, flags, seq, pid
NDMSG = struct.Struct("=BBHiHBB")  # family, pad, pad, ifindex, state, flags, type
RTATTR = struct.Struct("=HH")  # len, type

# The discard port: an empty datagram to it makes the kernel look the panel
# up, and carries nothing a Wake-on-LAN filter would take for a magic packet.
NUDGE_PORT = 9

# A connect that fails this way found nobody on the link: the ARP went
# unanswered (macOS says "host is down").
OFF_NETWORK_ERRNOS = frozenset({errno.EHOSTUNREACH, errno.EHOSTDOWN})


@dataclass(frozen=True)
class Neighbour:
    ip: str
    mac: str | None
    state: int
    ifindex: int


def _align(n: int) -> int:
    return (n + 3) & ~3


def parse_neighbours(data: bytes) -> tuple[list[Neighbour], bool]:
    """The IPv4 entries in one rtnetlink reply, and whether the dump is done."""
    found: list[Neighbour] = []
    offset = 0
    while offset + NLMSG_HEADER.size <= len(data):
        length, kind, _, _, _ = NLMSG_HEADER.unpack_from(data, offset)
        if length < NLMSG_HEADER.size:
            break
        if kind == NLMSG_DONE:
            return found, True
        if kind == NLMSG_ERROR:
            (code,) = struct.unpack_from("=i", data, offset + NLMSG_HEADER.size)
            raise OSError(-code, "rtnetlink error")
        body = offset + NLMSG_HEADER.size
        if kind == RTM_NEWNEIGH and body + NDMSG.size <= offset + length:
            family, _, _, ifindex, state, _, _ = NDMSG.unpack_from(data, body)
            ip, mac = None, None
            attr = body + NDMSG.size
            while attr + RTATTR.size <= offset + length:
                attr_len, attr_type = RTATTR.unpack_from(data, attr)
                if attr_len < RTATTR.size:
                    break
                value = data[attr + RTATTR.size : attr + attr_len]
                if attr_type == NDA_DST and len(value) == 4:
                    ip = str(ipaddress.IPv4Address(value))
                elif attr_type == NDA_LLADDR and len(value) == 6:
                    mac = value.hex(":")
                attr += _align(attr_len)
            if family == socket.AF_INET and ip is not None:
                found.append(Neighbour(ip, mac, state, ifindex))
        offset += _align(length)
    return found, False


def neighbours() -> list[Neighbour]:
    """The kernel's IPv4 neighbour (ARP) table. Linux only; blocking, but the
    kernel answers at once."""
    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE) as sock:
        sock.settimeout(2.0)
        request = NDMSG.pack(socket.AF_INET, 0, 0, 0, 0, 0, 0)
        header = NLMSG_HEADER.pack(
            NLMSG_HEADER.size + len(request), RTM_GETNEIGH, NLM_F_REQUEST | NLM_F_DUMP, 1, 0
        )
        sock.send(header + request)
        found: list[Neighbour] = []
        while True:
            entries, done = parse_neighbours(sock.recv(65536))
            found.extend(entries)
            if done:
                return found


def verdict(states: list[int]) -> bool | None:
    """On the network (an ARP reply came), gone (no reply), or not settled yet."""
    if any(s & (NUD_REACHABLE | NUD_PERMANENT | NUD_NOARP) for s in states):
        return True
    if states and all(s & NUD_FAILED for s in states):
        return False
    return None


def connect_says_gone(err: BaseException | None) -> bool:
    """A failed connect (the cause of an MDC connection error) that already
    shows nobody answered ARP."""
    while err is not None:
        if isinstance(err, OSError) and err.errno in OFF_NETWORK_ERRNOS:
            return True
        err = err.__cause__
    return False


def _nudge(ip: str) -> None:
    # Failing means no ARP answer to an earlier lookup: the table says so too.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, contextlib.suppress(OSError):
        sock.sendto(b"", (ip, NUDGE_PORT))


async def _ipv4(host: str) -> str:
    try:
        return str(ipaddress.IPv4Address(host))
    except ValueError:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, family=socket.AF_INET)
        return str(infos[0][4][0])


async def on_network(host: str, wait: float = 9.0, interval: float = 0.25) -> bool | None:
    """True: the panel answered ARP; False: it did not; None: cannot tell
    (not Linux, behind a router, or not settled within ``wait``).

    Sends one empty datagram so the kernel looks the panel up. A known entry
    gone stale is checked only after the kernel's ~5 s grace and three
    probes: hence the default ``wait``. Right after a failed MDC connect the
    entry is usually settled already and the answer is immediate.
    """
    if not hasattr(socket, "AF_NETLINK"):
        return None
    try:
        ip = await _ipv4(host)
    except (OSError, IndexError):
        return None
    _nudge(ip)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait
    first = True
    while True:
        try:
            table = await asyncio.to_thread(neighbours)
        except OSError as err:
            log.info("cannot read the neighbour table: %s", err)
            return None
        states = [n.state for n in table if n.ip == ip]
        if not states and first:
            # Sending on the link creates the entry at once: none means the
            # panel is behind a router.
            return None
        first = False
        answer = verdict(states)
        if answer is not None:
            return answer
        if loop.time() >= deadline:
            # Still asking after all that time: nobody answers.
            if states and all(s & NUD_INCOMPLETE for s in states):
                return False
            return None
        await asyncio.sleep(interval)
