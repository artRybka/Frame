"""Tailscale built into the iOS app: the auth key its phones join with.

Away from home the app reaches the server's Tailscale address through a
Tailscale node of its own (libtailscale inside the app), not through the
Tailscale app and its VPN, so it works next to another VPN (Mateusz,
2026-11-03, decision D16). The owner gives the key once in Konfiguracja →
Dostęp spoza domu; every phone of the household takes it from here when it
reaches the server, so a household member needs no Tailscale account.

Unlike the other keys this one goes back to the phones (to any of them,
members too): that is what it is for. A reusable key with a tag
(``tag:frame-app``) is meant: tagged nodes do not expire, and the tailnet's
policy can let them reach the NAS's port only. Tailscale cannot be asked
whether a key is good without using it, so only its form is checked here;
the phone that joins with it says how that went.

Next to the key the server keeps its own address in the tailnet. Nobody
types it: the owner's phone finds it through its node (the tailnet's
machines, each asked whether it is a frame server) and hands it over here,
and every phone takes it from here like the key (Mateusz, 2026-11-07).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .library import Library

STATE_KEY = "tailnet"
ADDRESS_KEY = "tailnet_address"
MAX_ADDRESS = 200
#: Tailscale's addresses: CGNAT IPv4 and its own IPv6 range.
_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
PREFIX = "tskey-"
KEY_TAIL = 4
MIN_LENGTH = 24
MAX_LENGTH = 200


class KeyInvalid(ValueError):
    """Not a Tailscale auth key."""


class AddressInvalid(ValueError):
    """Not a server address in the tailnet."""


@dataclass(frozen=True)
class TailnetKey:
    key: str
    saved_at: str


def clean(key: str) -> str:
    """The key as pasted, without spaces around it; KeyInvalid when it does
    not look like a Tailscale auth key."""
    key = key.strip()
    if not key:
        raise KeyInvalid("pusty klucz")
    if not key.startswith(PREFIX) or len(key) > MAX_LENGTH or any(c.isspace() for c in key):
        raise KeyInvalid("to nie jest klucz Tailscale (zaczyna się od tskey-)")
    if len(key) < MIN_LENGTH:
        raise KeyInvalid("klucz jest za krótki, skopiuj go w całości")
    return key


def is_tailscale_host(host: str) -> bool:
    """A MagicDNS name (``*.ts.net``), a bare machine name or an address
    in Tailscale's ranges; as ``Tailnet.isTailscale`` in the app."""
    host = host.lower().strip("[]")
    if host.endswith(".ts.net"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return bool(host) and "." not in host and ":" not in host and host != "localhost"
    return any(ip in network for network in _NETWORKS)


def clean_address(address: str) -> str:
    """``http(s)://host[:port]`` of the server in the tailnet, without a
    path; AddressInvalid otherwise."""
    address = address.strip().rstrip("/")
    if not address or len(address) > MAX_ADDRESS or any(c.isspace() for c in address):
        raise AddressInvalid("to nie jest adres serwera")
    parts = urlsplit(address)
    try:
        _ = parts.port  # raises on a port out of range
    except ValueError as err:
        raise AddressInvalid("zły port") from err
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AddressInvalid("adres zaczyna się od http:// albo https://")
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise AddressInvalid("sam adres serwera, bez ścieżki")
    if not is_tailscale_host(parts.hostname):
        raise AddressInvalid("to nie jest adres w Tailscale")
    return address


class Tailnet:
    """The household's Tailscale auth key, kept in the library's state."""

    def __init__(self, library: Library) -> None:
        self.library = library

    def get(self) -> TailnetKey | None:
        saved = self.library.get_state(STATE_KEY)
        if not isinstance(saved, dict) or not isinstance(saved.get("key"), str):
            return None
        return TailnetKey(key=saved["key"], saved_at=str(saved.get("saved_at") or ""))

    def tail(self) -> str | None:
        found = self.get()
        return found.key[-KEY_TAIL:] if found else None

    def set(self, key: str | None) -> None:
        """Keeps ``key`` (checked with ``clean``), or forgets the saved one."""
        if key is None:
            self.library.delete_state(STATE_KEY)
            return
        self.library.set_state(
            STATE_KEY,
            {"key": clean(key), "saved_at": datetime.now(UTC).isoformat(timespec="seconds")},
        )

    def address(self) -> str | None:
        """The server's own address in the tailnet, as a phone found it."""
        saved = self.library.get_state(ADDRESS_KEY)
        if not isinstance(saved, dict) or not isinstance(saved.get("address"), str):
            return None
        return str(saved["address"])

    def set_address(self, address: str | None) -> None:
        """Keeps ``address`` (checked with ``clean_address``), or forgets it."""
        if address is None:
            self.library.delete_state(ADDRESS_KEY)
            return
        self.library.set_state(
            ADDRESS_KEY,
            {
                "address": clean_address(address),
                "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
