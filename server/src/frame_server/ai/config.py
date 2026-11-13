"""What the owner set for the language model (Claude), in the app's
Konfiguracja: the Anthropic API key, which jobs may run and how much they
may cost a month.

The key the app saves wins over ``FRAME_ANTHROPIC_API_KEY`` (frame.env or
the add-on options) and is never sent back, only its last characters.
Without a key nothing is asked and the frame works as before.

And Google's key, for the image model that draws the study sheets of the
analyses of composition (``ai.drawn``): saved in the app only, never taken
from frame.env (Mateusz 2026-11-01: keys go in through a field in
Konfiguracja), never sent back either. Without it the sheets are made as
before it (``imaging.sheet``).
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
    #: Polish words typed in Szukaj translated for the museums abroad (Haiku).
    search_words: bool = True
    #: Discover's curator: two cards of "Dziś dla Ciebie" (Opus, Batch API, nightly).
    curator: bool = True
    #: Copies and details the pictures could not tell apart, judged at night
    #: (Haiku and Haiku as the critic, Batch API).
    twins_judge: bool = True
    #: The catalogue's gatekeeper: pictures from Commons, Europeana, Openverse
    #: and WikiArt that are no artwork for the frame (Haiku and its critic, at night).
    gatekeeper: bool = True
    #: The night audit: 30 works a night looked over, "Do sprawdzenia" (Haiku, at night).
    audit: bool = True
    #: The study's "Droga dzieła": the museum's provenance retold as stops (Haiku).
    journey: bool = True
    #: Facts about a work from the web for its study (Sonnet with the web
    #: search, once a work, about 0.3 USD; ``ai.web_facts``, "G8").
    web_facts: bool = True
    #: Google's key (the image model, ``ai.drawn``).
    gemini_api_key: str | None = None
    #: The study sheets of the analyses drawn by the image model (three
    #: pictures a sheet, about 0.15 USD); needs Google's key.
    drawn: bool = True
    #: How a work was painted, told in a few sentences when a published
    #: technical study of it was found ("G2"; no longer drawn).
    stages: bool = True
    #: How works look as numbers (Google's embedding model): Szukaj by how a
    #: work looks, by a photograph, and the works that look alike ("G1").
    looks: bool = True
    #: Nothing more is asked once this month's cost reaches it.
    monthly_limit_usd: float = Field(5.0, ge=0, le=1000)
    #: The same for the image model, which has a month's limit of its own.
    gemini_monthly_limit_usd: float = Field(5.0, ge=0, le=1000)
    #: The day of the month Claude's period begins on, when the owner's
    #: credit is renewed (Mateusz 2026-11-13): the spending and the limit
    #: count from it.
    period_day: int = Field(1, ge=1, le=28)
    #: "Resztka miesiąca na studia" (Mateusz 2026-11-13): in the period's
    #: last days, what the limit leaves above a reserve goes on more studies
    #: of works the curator found worth one (``frame_server.leftover``).
    leftover: bool = False
    leftover_days: int = Field(3, ge=2, le=10)
    leftover_reserve_usd: float = Field(10.0, ge=0, le=1000)


class AiConfigUpdate(BaseModel):
    """The app's change; fields left out stay as they are."""

    pl_text: bool | None = None
    keywords_artworks: bool | None = None
    keywords_photos: bool | None = None
    daily: bool | None = None
    search_words: bool | None = None
    curator: bool | None = None
    twins_judge: bool | None = None
    gatekeeper: bool | None = None
    audit: bool | None = None
    journey: bool | None = None
    web_facts: bool | None = None
    drawn: bool | None = None
    looks: bool | None = None
    stages: bool | None = None
    monthly_limit_usd: float | None = Field(None, ge=0, le=1000)
    gemini_monthly_limit_usd: float | None = Field(None, ge=0, le=1000)
    period_day: int | None = Field(None, ge=1, le=28)
    leftover: bool | None = None
    leftover_days: int | None = Field(None, ge=2, le=10)
    leftover_reserve_usd: float | None = Field(None, ge=0, le=1000)


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

    @property
    def gemini_key(self) -> str | None:
        """Google's key (the app's; there is no other)."""
        return self.config.gemini_api_key

    @property
    def gemini_tail(self) -> str | None:
        key = self.gemini_key
        return key[-KEY_TAIL:] if key else None

    @property
    def drawn(self) -> bool:
        """Whether the study sheets are drawn by the image model: Google's
        key, and the owner's switch."""
        config = self.config
        return bool(config.gemini_api_key) and config.drawn

    def set_gemini_key(self, key: str | None) -> AiConfig:
        """Keep Google's key (None forgets it)."""
        update = {"gemini_api_key": clean_key(key) if key else None}
        config = self.config.model_copy(update=update)
        self._save(config)
        return config

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
        if kind in ("search_words", "look_words"):  # words for the museums
            return config.search_words
        if kind == "curator":
            return config.curator
        if kind == "twins_judge":
            return config.twins_judge
        if kind in ("gatekeeper", "audit", "journey", "web_facts", "stages"):
            return bool(getattr(config, kind))
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
