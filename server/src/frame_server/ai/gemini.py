"""Google's image model (the Interactions API), asked for a picture: the
one client of everything here that has a picture made (the study sheets of
``ai.drawn``; whatever else asks goes through :class:`Painter` too, so that
there is one key, one count of what was spent and one month's limit).

The key is the owner's, given in the app (Konfiguracja; never the
environment's). What an answer cost is counted from its own ``usage`` into
the same month's spending as Claude's answers, under the kind its asker
names, and nothing is asked once the month's limit is reached.
"""

from __future__ import annotations

import base64
import io
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from PIL import Image

from .client import AiUnavailable

if TYPE_CHECKING:
    from .client import Claude
    from .config import AiConfigStore

MODEL = "gemini-nano-banana-2.1"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
REVISION = "2026-05-20"
#: USD per million tokens: what goes in, text and thinking out, picture out
#: (ai.google.dev/pricing, 2026-11-12). A picture at 1K is 1120 tokens.
PRICE = (1.50, 7.50, 30.0)
PATIENCE = 300.0
#: Answers worth asking for again: the service is busy or broke off.
AGAIN = (429, 500, 502, 503, 504)
TRIES = 3


class GeminiRejected(AiUnavailable):
    """Google does not accept the key."""


class NoCredit(AiUnavailable):
    """The key's prepaid credit is used up (HTTP 402)."""


class NotDrawn(Exception):
    """The model gave no picture, or one that cannot be used. ``code``:
    Google's own word for why, when it gave one (``image_recitation``: it
    will not redraw a work it takes for a protected one)."""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Ask:
    """One question of a batch (:meth:`Painter.batch`): the name its answer
    comes back under, and what :meth:`Painter.paint` takes."""

    name: str
    prompt: str
    pictures: Sequence[Image.Image]
    size: str = "1K"


def _code(answer: httpx.Response) -> str:
    """Google's word for an error: the first that is one among its fields."""
    try:
        error = answer.json().get("error")
    except ValueError:
        return ""
    if not isinstance(error, dict):
        return ""
    words = (error.get(name) for name in ("code", "status", "reason"))
    return next((w for w in words if isinstance(w, str) and not w.isdigit()), "")


def cost(usage: dict[str, Any]) -> float:
    """What an answer cost, by its own count of tokens."""
    into, text, picture = PRICE
    pictured = sum(
        part.get("tokens", 0)
        for part in usage.get("output_tokens_by_modality") or []
        if str(part.get("modality", "")).lower() == "image"
    )
    said = max(usage.get("total_output_tokens", 0) - pictured, 0)
    said += usage.get("total_thought_tokens", 0)
    spent = usage.get("total_input_tokens", 0) * into + said * text + pictured * picture
    return round(spent / 1e6, 4)


def _block(img: Image.Image) -> dict[str, Any]:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=92)
    data = base64.b64encode(out.getvalue()).decode()
    return {"type": "image", "mime_type": "image/jpeg", "data": data}


def _pictures(node: Any, found: list[str]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "image" and isinstance(node.get("data"), str):
            found.append(node["data"])
        for value in node.values():
            _pictures(value, found)
    elif isinstance(node, list):
        for value in node:
            _pictures(value, found)


class Painter:
    """Asks Google's image model and counts what it costs, in the same
    month's spending and under the same limit as Claude's answers."""

    def __init__(
        self,
        config: AiConfigStore,
        claude: Claude,
        http: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.config = config
        self.claude = claude
        self.http = http or (lambda: httpx.Client(timeout=PATIENCE))

    def enabled(self) -> bool:
        """Whether there is a key to ask with."""
        return bool(self.config.gemini_key)

    def check_key(self, key: str) -> None:
        """Raises GeminiRejected when Google refuses ``key`` (costs nothing)."""
        with self.http() as http:
            answer = http.get(MODELS_URL, headers={"x-goog-api-key": key}, params={"pageSize": 1})
        if answer.status_code in (400, 401, 403):
            raise GeminiRejected("Google did not accept the key")
        answer.raise_for_status()

    def paint(
        self, kind: str, prompt: str, pictures: Sequence[Image.Image], size: str = "1K"
    ) -> tuple[Image.Image, float]:
        """The model's picture in answer to ``prompt`` and ``pictures``
        (``size``: "1K", "2K", "4K"), and what it cost, counted as ``kind``
        in the month's spending. Raises :class:`AiUnavailable` (no key,
        the month's limit, :class:`GeminiRejected`, :class:`NoCredit`) or
        :class:`NotDrawn` (this answer)."""
        key = self.config.gemini_key
        if not key:
            raise AiUnavailable("no Google API key")
        self.claude.check_budget()
        body = {
            "model": MODEL,
            "input": [{"type": "text", "text": prompt}, *(_block(p) for p in pictures)],
            "response_format": {"type": "image", "image_size": size},
        }
        headers = {"x-goog-api-key": key, "Api-Revision": REVISION}
        answer = None
        with self.http() as http:
            for attempt in range(TRIES):
                answer = http.post(URL, json=body, headers=headers)
                if answer.status_code not in AGAIN or attempt == TRIES - 1:
                    break
                time.sleep(4.0 * (attempt + 1))
        assert answer is not None
        if answer.status_code == 402:
            raise NoCredit("Google: the key's prepaid credit is used up")
        if answer.status_code in (401, 403):
            raise GeminiRejected("Google did not accept the key")
        if answer.status_code >= 400:
            said = f"Google answered {answer.status_code}: {answer.text[:300]}"
            raise NotDrawn(said, _code(answer))
        raw = answer.json()
        usd = cost(raw.get("usage") or {})
        self.claude.spending.add(kind, usd)
        found: list[str] = []
        _pictures(raw, found)
        if not found:
            raise NotDrawn("Google's answer has no picture")
        img = Image.open(io.BytesIO(base64.b64decode(found[-1])))
        img.load()
        return img.convert("RGB"), usd

    def batch(self, kind: str, asks: Sequence[Ask]) -> str:
        """Hands the questions to Google's Batch (answered within a day, at
        half the price): the batch's name, to ask :meth:`batched` with.
        Raises :class:`AiUnavailable` as :meth:`paint` does (no key, the
        month's limit, the key's trouble)."""
        raise NotImplementedError

    def batched(
        self, kind: str, batch: str
    ) -> dict[str, tuple[Image.Image, float] | NotDrawn] | None:
        """The answers of a batch by the questions' names: a picture and
        what it cost, or why there is none; None while Google is at it.
        What they cost is counted as ``kind`` once, when they are read.
        Raises :class:`NotDrawn` when the batch itself is lost (expired,
        cancelled, unknown)."""
        raise NotImplementedError
