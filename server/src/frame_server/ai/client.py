"""Asking Claude (Anthropic's API) and counting what it costs.

Every question is a structured one: a stable system prompt (cached), the
item's content (a thumbnail, its text) and a JSON schema the answer must
follow. What each answer cost is added to this month's spending, by kind of
job; nothing more is asked once the owner's monthly limit is reached.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import anthropic
from PIL import Image

from ..imaging.layout import load_image

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .config import AiConfigStore

log = logging.getLogger(__name__)

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"
SPEND_KEY = "ai_spend"
#: The Batch API's discount on every token.
BATCH_DISCOUNT = 0.5
#: Thumbnails go out at most this big: plenty to tell what a picture shows,
#: 266 image tokens at 512×384 (the server keeps 640 px ones).
IMAGE_SIDE = 512


@dataclass(frozen=True)
class Price:
    """USD per million tokens (prompts up to 100k tokens)."""

    input: float
    cache_write: float  # 5-minute cache
    cache_read: float
    output: float


PRICES = {
    HAIKU: Price(0.10, 0.125, 0.01, 0.50),
    SONNET: Price(2.00, 2.50, 0.10, 10.00),
    OPUS: Price(4.00, 5.00, 0.20, 20.00),
}


class AiUnavailable(Exception):
    """No key, or the month's limit is reached: nothing is asked."""


class KeyRejected(AiUnavailable):
    """Anthropic does not accept the key."""


@dataclass
class Answer:
    data: dict[str, Any] | None  # the JSON answer; None when refused
    refused: bool
    cost_usd: float
    model: str


def _price(model: str) -> Price:
    """The model's price; a dated id ("claude-haiku-5-5-2026…") counts as its
    model, an unknown model as the dearest."""
    for known, price in PRICES.items():
        if model == known or model.startswith(f"{known}-"):
            return price
    return PRICES[SONNET]


def cost(model: str, usage: Any, batch: bool = False) -> float:
    price = _price(model)
    usd = (
        (usage.input_tokens or 0) * price.input
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * price.cache_write
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * price.cache_read
        + (usage.output_tokens or 0) * price.output
    ) / 1_000_000
    return usd * (BATCH_DISCOUNT if batch else 1.0)


def request(
    *,
    model: str,
    system: str,
    content: list[dict[str, Any]],
    schema: dict[str, Any],
    max_tokens: int = 2000,
    effort: str = "low",
) -> dict[str, Any]:
    """The Messages API parameters of one question (sent alone or in a batch).

    The system prompt is the same for every item of a job: it is cached.
    Thinking is on for current models and counts towards ``max_tokens``."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": content}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }


def image_block(images: ImageCache, item: Item, max_side: int = IMAGE_SIDE) -> dict[str, Any]:
    """The item's thumbnail as an image content block (downloaded if missing)."""
    img = load_image(images.ensure_thumb(item).read_bytes()).convert("RGB")
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    data = base64.standard_b64encode(out.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def month(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


class Spending:
    """What answers cost, by month and kind of job (kept in the library)."""

    def __init__(self, library: Library) -> None:
        self.library = library
        self._lock = threading.Lock()

    def add(self, kind: str, usd: float) -> None:
        if usd <= 0:
            return
        with self._lock:
            spent = self.library.get_state(SPEND_KEY, {})
            this = spent.setdefault(month(), {})
            this[kind] = round(this.get(kind, 0.0) + usd, 6)
            self.library.set_state(SPEND_KEY, spent)

    def by_kind(self, when: str | None = None) -> dict[str, float]:
        return dict(self.library.get_state(SPEND_KEY, {}).get(when or month(), {}))

    def total(self, when: str | None = None) -> float:
        return sum(self.by_kind(when).values())


def _text(message: Any) -> str:
    return next((b.text for b in message.content if b.type == "text"), "")


class Claude:
    def __init__(
        self,
        config: AiConfigStore,
        library: Library,
        factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.config = config
        self.spending = Spending(library)
        self.factory = factory or (
            lambda key: anthropic.Anthropic(api_key=key, max_retries=3, timeout=120.0)
        )
        self._clients: dict[str, Any] = {}

    def client(self) -> Any:
        key = self.config.api_key
        if not key:
            raise AiUnavailable("no Anthropic API key")
        if key not in self._clients:
            self._clients = {key: self.factory(key)}
        return self._clients[key]

    def budget_left(self) -> float:
        return self.config.config.monthly_limit_usd - self.spending.total()

    def check_budget(self) -> None:
        if self.budget_left() <= 0:
            raise AiUnavailable("this month's limit is reached")

    def check_key(self, key: str) -> None:
        """Raises KeyRejected when Anthropic refuses ``key`` (costs nothing)."""
        try:
            self.factory(key).models.retrieve(HAIKU)
        except anthropic.AuthenticationError as err:
            raise KeyRejected("Anthropic did not accept the key") from err
        except anthropic.PermissionDeniedError as err:
            raise KeyRejected("the key may not use Claude models") from err

    def ask(
        self, kind: str, params: dict[str, Any], on_text: Callable[[str], None] | None = None
    ) -> Answer:
        """One question now (``params`` from :func:`request`). With
        ``on_text``, the answer is streamed and each piece of its text is
        passed on as it comes (e.g. a title before the rest is written)."""
        self.check_budget()
        try:
            if on_text is None:
                message = self.client().messages.create(**params)
            else:
                with self.client().messages.stream(**params) as stream:
                    for piece in stream.text_stream:
                        try:
                            on_text(piece)
                        except Exception:  # only a head start: never the answer's end
                            log.exception("%s: reading the answer as it came failed", kind)
                    message = stream.get_final_message()
        except anthropic.AuthenticationError as err:
            raise KeyRejected("Anthropic did not accept the key") from err
        return self.answer(kind, params["model"], message, batch=False)

    def answer(self, kind: str, model: str, message: Any, *, batch: bool) -> Answer:
        usd = cost(model, message.usage, batch)
        self.spending.add(kind, usd)
        if message.stop_reason == "refusal":
            return Answer(None, True, usd, model)
        try:
            data = json.loads(_text(message))
        except ValueError:
            log.warning("%s: an answer that is not JSON (%s)", kind, message.stop_reason)
            return Answer(None, False, usd, model)
        return Answer(data if isinstance(data, dict) else None, False, usd, model)

    # -- batches -----------------------------------------------------------

    def create_batch(self, requests: list[dict[str, Any]]) -> str:
        """``requests``: ``{"custom_id": ..., "params": request(...)}``."""
        self.check_budget()
        try:
            return str(self.client().messages.batches.create(requests=requests).id)
        except anthropic.AuthenticationError as err:
            raise KeyRejected("Anthropic did not accept the key") from err

    def batch_ended(self, batch_id: str) -> tuple[bool, int]:
        """Whether the batch is done, and how many of its questions are."""
        batch = self.client().messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        done = counts.succeeded + counts.errored + counts.canceled + counts.expired
        return batch.processing_status == "ended", done

    def batch_results(self, batch_id: str) -> Iterator[tuple[str, Any | None]]:
        """``(custom_id, message)``; the message is None for a failed question."""
        for result in self.client().messages.batches.results(batch_id):
            message = result.result.message if result.result.type == "succeeded" else None
            yield result.custom_id, message
