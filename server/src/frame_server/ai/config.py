"""What the owner set for the language model (Claude), in the app's
Konfiguracja: the Anthropic API key, which jobs may run and how much they
may cost a month.

The key the app saves wins over ``FRAME_ANTHROPIC_API_KEY`` (frame.env or
the add-on options) and is never sent back, only its last characters.
Without a key nothing is asked and the frame works as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..config import Settings
    from ..library import Library

STATE_KEY = "ai_config"
KEY_TAIL = 4


class AiConfig(BaseModel):
    api_key: str | None = None
    #: Polish titles and descriptions of works.
    pl_text: bool = True
    #: Keywords for museum works and for the owner's photos (sent as thumbnails).
    keywords_artworks: bool = True
    keywords_photos: bool = True
    #: Discover's work of the day: its story and composition (Opus, once a day).
    daily: bool = True
    #: Nothing more is asked once this month's cost reaches it.
    monthly_limit_usd: float = Field(5.0, ge=0, le=1000)


class AiConfigUpdate(BaseModel):
    """The app's change; fields left out stay as they are."""

    pl_text: bool | None = None
    keywords_artworks: bool | None = None
    keywords_photos: bool | None = None
    daily: bool | None = None
    monthly_limit_usd: float | None = Field(None, ge=0, le=1000)


def clean_key(value: str) -> str:
    key = value.strip()
    if not key or any(c.isspace() for c in key) or len(key) > 300:
        raise ValueError("invalid API key")
    return key


class AiConfigStore:
    def __init__(self, settings: Settings, library: Library) -> None:
        self.settings = settings
        self.library = library

    @property
    def config(self) -> AiConfig:
        saved = self.library.get_state(STATE_KEY)
        return AiConfig.model_validate(saved) if saved else AiConfig()

    @property
    def api_key(self) -> str | None:
        """The app's key, else frame.env's."""
        return self.config.api_key or self.settings.anthropic_api_key

    @property
    def key_from_app(self) -> bool:
        return bool(self.config.api_key)

    @property
    def key_tail(self) -> str | None:
        key = self.api_key
        return key[-KEY_TAIL:] if key else None

    def enabled(self, kind: str) -> bool:
        """Whether jobs of ``kind`` may run: a key, and the owner's switch."""
        if not self.api_key:
            return False
        config = self.config
        if kind == "pl_text":
            return config.pl_text
        if kind == "keywords":
            return config.keywords_artworks or config.keywords_photos
        if kind == "daily":
            return config.daily
        return True

    def update(self, update: AiConfigUpdate) -> AiConfig:
        config = self.config.model_copy(update=update.model_dump(exclude_none=True))
        self._save(config)
        return config

    def set_key(self, key: str | None) -> AiConfig:
        """Keep the app's key (None forgets it: frame.env's applies again)."""
        config = self.config.model_copy(update={"api_key": clean_key(key) if key else None})
        self._save(config)
        return config

    def _save(self, config: AiConfig) -> None:
        self.library.set_state(STATE_KEY, config.model_dump())
