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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .library import Library

STATE_KEY = "tailnet"
PREFIX = "tskey-"
KEY_TAIL = 4
MIN_LENGTH = 24
MAX_LENGTH = 200


class KeyInvalid(ValueError):
    """Not a Tailscale auth key."""


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
