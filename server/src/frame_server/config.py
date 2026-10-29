"""Runtime configuration.

Sources, highest priority first: environment variables (``FRAME_*``), a
``.env`` file in the working directory, and the Home Assistant add-on
options file (``/data/options.json``) when running as an add-on.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ADDON_OPTIONS = Path(os.environ.get("FRAME_OPTIONS_FILE", "/data/options.json"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FRAME_", env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    # Panel
    device_host: str | None = None
    device_pin: str | None = None
    device_mac: str | None = None
    device_port: int = 1515

    # HTTP server the panel downloads content from. ``public_host`` is the
    # address the panel can reach this machine at; autodetected if unset.
    bind: str = "0.0.0.0"
    port: int = 8099
    public_host: str | None = None
    api_token: str | None = None

    data_dir: Path = Path("data")
    # Originals the server can download again (museums, shared albums) are a
    # cache: least recently used ones go beyond this size, those in Favourites
    # and playlists last. Uploads are always kept and not counted.
    image_cache_mb: int = 3000
    # The catalogue browsed in the app: museum works with thumbnails and
    # colours, grown in the background up to this many MB of thumbnails
    # (0: only what Suggestions and playlists need).
    catalogue_mb: int = 1000
    # Ask museums for Suggestions on start (the default rotation) as needed.
    seed_library: bool = True
    # Background rotation and status polling (off in some tests).
    scheduler: bool = True
    palette: str | None = None  # built-in palette name or path to a calibrated JSON
    # Europeana's shared demo key works; a free key of one's own has higher limits.
    europeana_key: str = "api2demo"
    # Openverse app credentials; without them 200 anonymous requests a day.
    openverse_client_id: str | None = None
    openverse_client_secret: str | None = None
    # Claude (Anthropic API) for keywords and Polish texts; a key saved in
    # the app wins over this one.
    anthropic_api_key: str | None = None

    @field_validator("public_host")
    @classmethod
    def _bare_host(cls, value: str | None) -> str | None:
        # Accept "http://host:port/" too: base_url() adds scheme and port itself,
        # and a doubled scheme silently breaks the panel's image download.
        if not value:
            return value
        host = value.strip().split("://", 1)[-1].split("/", 1)[0]
        if host.count(":") == 1:  # host:port, but leave IPv6 literals alone
            host = host.split(":", 1)[0]
        return host or None

    @classmethod
    def load(cls) -> Settings:
        defaults: dict[str, object] = {}
        if ADDON_OPTIONS.is_file():
            options = json.loads(ADDON_OPTIONS.read_text())
            defaults = {k: v for k, v in options.items() if v not in (None, "")}
            defaults.setdefault("data_dir", "/data")
        # Environment wins over add-on options: drop defaults that env sets.
        defaults = {k: v for k, v in defaults.items() if f"FRAME_{k.upper()}" not in os.environ}
        return cls(**defaults)  # type: ignore[arg-type]

    def require_device(self) -> tuple[str, str]:
        if not self.device_host or not self.device_pin:
            raise SystemExit(
                "Panel not configured: set FRAME_DEVICE_HOST and FRAME_DEVICE_PIN "
                "(or pass --host/--pin)."
            )
        return self.device_host, self.device_pin

    def base_url(self) -> str:
        host = self.public_host or local_ip_towards(self.device_host)
        return f"http://{host}:{self.port}"


def local_ip_towards(target: str | None) -> str:
    """The local address used to reach ``target`` (no packets are sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect((target or "192.168.0.1", 9))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"
