"""The panel's address, MDC PIN and MAC, editable in the app.

frame.env (or the add-on options) gives the starting values. What the app
saves wins over them and survives restarts; resetting goes back to them.
The values live on the shared ``Settings``, so the panel client, Wake-on-LAN
and status checks pick a change up with their next session.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .config import Settings
    from .library import Library

log = logging.getLogger(__name__)

STATE_KEY = "panel_config"
# The MAC the frame's app read on the panel, used while none is set.
LEARNT_MAC_KEY = "panel_mac_learnt"
_HOST = re.compile(r"^[A-Za-z0-9.\-]+$")  # an IPv4 address or a name
_HEX = re.compile(r"^[0-9A-Fa-f]{12}$")


class PanelConfig(BaseModel):
    host: str | None = None
    pin: str | None = None
    mac: str | None = None
    port: int = 1515


class PanelConfigView(BaseModel):
    """What the app shows; the PIN itself is never sent back."""

    host: str | None
    mac: str | None
    port: int
    pin_set: bool
    from_app: bool  # saved in the app, not taken from frame.env / add-on options
    mac_from_panel: str | None = None  # what the frame's app read on the panel


class PanelConfigUpdate(BaseModel):
    host: str | None = None
    pin: str | None = None  # left out (None) keeps the PIN, "" removes it
    mac: str | None = None
    port: int = Field(1515, ge=1, le=65535)


def clean_host(value: str | None) -> str | None:
    """A bare address: "http://203.0.113.152/" is taken as 203.0.113.152."""
    host = (value or "").strip().split("://", 1)[-1].split("/", 1)[0]
    if not host:
        return None
    if not _HOST.match(host):
        raise ValueError(f"invalid panel address {value!r}")
    return host


def clean_mac(value: str | None) -> str | None:
    """Any common spelling as AA:BB:CC:DD:EE:FF."""
    raw = re.sub(r"[\s:.\-]", "", value or "")
    if not raw:
        return None
    if not _HEX.match(raw):
        raise ValueError(f"invalid MAC address {value!r}")
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2)).upper()


def clean_pin(value: str) -> str | None:
    pin = value.strip()
    if any(c.isspace() for c in pin) or len(pin) > 32:
        raise ValueError("invalid PIN")
    return pin or None


class PanelConfigStore:
    def __init__(self, settings: Settings, library: Library) -> None:
        self.settings = settings
        self.library = library
        self.defaults = self.current
        saved = library.get_state(STATE_KEY)
        if saved:
            self._apply(PanelConfig.model_validate(saved))
        self._fill_mac()

    @property
    def current(self) -> PanelConfig:
        s = self.settings
        return PanelConfig(
            host=s.device_host, pin=s.device_pin, mac=s.device_mac, port=s.device_port
        )

    @property
    def from_app(self) -> bool:
        return self.library.get_state(STATE_KEY) is not None

    def view(self) -> PanelConfigView:
        config = self.current
        return PanelConfigView(
            host=config.host,
            mac=config.mac,
            port=config.port,
            pin_set=bool(config.pin),
            from_app=self.from_app,
            mac_from_panel=self.learnt_mac,
        )

    @property
    def learnt_mac(self) -> str | None:
        learnt = self.library.get_state(LEARNT_MAC_KEY)
        return learnt if isinstance(learnt, str) else None

    def save(self, update: PanelConfigUpdate) -> bool:
        """Keep the app's values; True when the panel itself may have changed.

        An empty MAC means the one the panel reports (once its app has run).
        Raises ValueError on an address, MAC or PIN that cannot be right."""
        old = self.current
        config = PanelConfig(
            host=clean_host(update.host),
            pin=old.pin if update.pin is None else clean_pin(update.pin),
            mac=clean_mac(update.mac),
            port=update.port,
        )
        self.library.set_state(STATE_KEY, config.model_dump())
        self._apply(config)
        self._fill_mac()
        return (old.host, old.port) != (config.host, config.port)

    def reset(self) -> bool:
        """Back to frame.env / add-on options; True when the panel may have changed."""
        old = self.current
        self.library.delete_state(STATE_KEY)
        self._apply(self.defaults)
        self._fill_mac()
        return (old.host, old.port) != (self.defaults.host, self.defaults.port)

    def learn_mac(self, mac: str) -> None:
        """The panel's own MAC (its app read it): Wake-on-LAN uses it while
        none is set; one set that differs is only logged, it may be right
        for another way in (Ethernet)."""
        learnt = self.library.get_state(LEARNT_MAC_KEY)
        if learnt != mac:
            self.library.set_state(LEARNT_MAC_KEY, mac)
            current = self.settings.device_mac
            if current and current != mac:
                log.warning("the panel says its MAC is %s, Wake-on-LAN goes to %s", mac, current)
        if not self.settings.device_mac:
            log.info("the panel's MAC %s is used for Wake-on-LAN", mac)
            self.settings.device_mac = mac

    def _fill_mac(self) -> None:
        if not self.settings.device_mac:
            self.settings.device_mac = self.learnt_mac

    def _apply(self, config: PanelConfig) -> None:
        s = self.settings
        s.device_host, s.device_pin, s.device_mac = config.host, config.pin, config.mac
        s.device_port = config.port
