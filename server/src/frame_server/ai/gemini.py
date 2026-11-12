"""Google's image model (the Interactions API), asked for a picture: the
one client of everything here that has a picture made (the study sheets of
``ai.drawn``; whatever else asks goes through :class:`Painter` too, so that
there is one key, one count of what was spent and one month's limit).

The key is the owner's, given in the app (Konfiguracja; never the
environment's). What an answer cost is counted from its own ``usage`` into
the image model's own month's spending (:data:`SPEND_KEY`; apart from
Claude's, Mateusz 2026-11-12 23:20: "Dla Gemini trzeba dać osobny segment
w Konfiguracja (tak jak Claude) i tam ustawić osobno limit"), under the
kind its asker names, and nothing is asked once its own month's limit
(``AiConfig.gemini_monthly_limit_usd``) is reached.
"""

from __future__ import annotations

import base64
import io
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from PIL import Image

from .client import AiUnavailable, Spending

if TYPE_CHECKING:
    from .client import Claude
    from .config import AiConfigStore

MODEL = "gemini-nano-banana-2.1"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
REVISION = "2026-05-20"
#: Google's Batch: questions in the request itself (generateContent's
#: shape), answered within a day at half the price.
BATCH_URL = f"{MODELS_URL}/{MODEL}:batchGenerateContent"
BATCHES_URL = "https://generativelanguage.googleapis.com/v1beta"
#: A batch's questions in the request may weigh this much at most (Google:
#: 20 MB).
BATCH_BYTES = 19_000_000
#: The Batch's price, a share of the one asked at once.
BATCH_SHARE = 0.5
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


class Busy(NotDrawn):
    """Google stayed busy (429, 5xx) through every try: ask again later."""


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


def batch_cost(usage: dict[str, Any]) -> float:
    """What a batch's answer cost (generateContent's ``usageMetadata``), at
    the Batch's price."""
    into, text, picture = PRICE
    pictured = sum(
        part.get("tokenCount", 0)
        for part in usage.get("candidatesTokensDetails") or []
        if str(part.get("modality", "")).lower() == "image"
    )
    said = max(usage.get("candidatesTokenCount", 0) - pictured, 0)
    said += usage.get("thoughtsTokenCount", 0)
    spent = usage.get("promptTokenCount", 0) * into + said * text + pictured * picture
    return round(spent * BATCH_SHARE / 1e6, 4)


def _jpeg(img: Image.Image) -> str:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=92)
    return base64.b64encode(out.getvalue()).decode()


def _request(ask: Ask) -> dict[str, Any]:
    """One question as generateContent takes it."""
    parts: list[dict[str, Any]] = [{"text": ask.prompt}]
    parts += [{"inline_data": {"mime_type": "image/jpeg", "data": _jpeg(p)}} for p in ask.pictures]
    return {
        "contents": [{"role": "user", "parts": parts}],
        "generation_config": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"imageSize": ask.size},
        },
    }


def _state(raw: dict[str, Any]) -> str:
    """A batch's state, the last word of Google's ("BATCH_STATE_SUCCEEDED"
    or "JOB_STATE_SUCCEEDED": "SUCCEEDED")."""
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else raw
    state = str((meta or {}).get("state") or "")
    return state.rsplit("_", 1)[-1] if state else ""


def _answers(node: Any) -> list[dict[str, Any]]:
    """A finished batch's answers, wherever Google put them (``response``
    or ``metadata.output``, under ``inlinedResponses`` once or twice)."""
    if isinstance(node, dict):
        inlined = node.get("inlinedResponses")
        if isinstance(inlined, list):
            return [a for a in inlined if isinstance(a, dict)]
        if isinstance(inlined, dict):
            return _answers(inlined)
        for key in ("response", "output", "metadata", "dest"):
            found = _answers(node.get(key))
            if found:
                return found
    return []


def _drawn(answer: dict[str, Any]) -> tuple[Image.Image, float] | NotDrawn:
    """One answer of a batch: its picture and cost, or why there is none."""
    error = answer.get("error")
    if isinstance(error, dict):
        words = (error.get(name) for name in ("status", "reason", "code"))
        code = next((w for w in words if isinstance(w, str) and not w.isdigit()), "")
        return NotDrawn(f"Google: {str(error.get('message') or error)[:300]}", code)
    response = answer.get("response") or {}
    usd = batch_cost(response.get("usageMetadata") or {})
    for candidate in response.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if isinstance(data, str):
                try:
                    img = Image.open(io.BytesIO(base64.b64decode(data)))
                    img.load()
                except (OSError, ValueError) as err:
                    return NotDrawn(f"Google's picture cannot be read: {err}")
                return img.convert("RGB"), usd
    reasons = [str(c.get("finishReason") or "") for c in response.get("candidates") or []]
    blocked = (response.get("promptFeedback") or {}).get("blockReason")
    code = next((r for r in [*reasons, str(blocked or "")] if r and r != "STOP"), "")
    return NotDrawn("Google's answer has no picture", code.lower())


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


#: Where what the image model's answers cost is kept (state), by month and kind.
SPEND_KEY = "gemini_spend"


class Painter:
    """Asks Google's image model and counts what it costs, in a month's
    spending and under a month's limit of its own."""

    def __init__(
        self,
        config: AiConfigStore,
        claude: Claude,
        http: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.config = config
        self.claude = claude
        self.spending = Spending(claude.spending.library, SPEND_KEY)
        self.http = http or (lambda: httpx.Client(timeout=PATIENCE))

    def budget_left(self) -> float:
        """What is left of the image model's month's limit."""
        return self.config.config.gemini_monthly_limit_usd - self.spending.total()

    def check_budget(self) -> None:
        if self.budget_left() <= 0:
            raise AiUnavailable("this month's limit for the image model is reached")

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
        self.check_budget()
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
        self.spending.add(kind, usd)
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
        month's limit, the key's trouble), ValueError when the questions
        weigh more than Google takes in one request (:data:`BATCH_BYTES`:
        fewer at a time) or have names twice."""
        key = self.config.gemini_key
        if not key:
            raise AiUnavailable("no Google API key")
        names = [ask.name for ask in asks]
        if not names or len(set(names)) != len(names):
            raise ValueError("a batch needs questions, each under a name of its own")
        self.check_budget()
        requests = [{"request": _request(a), "metadata": {"key": a.name}} for a in asks]
        weight = sum(len(json.dumps(r)) for r in requests)
        if weight > BATCH_BYTES:
            raise ValueError(
                f"a batch of {len(asks)} questions weighs {weight / 1e6:.1f} MB, "
                f"Google takes {BATCH_BYTES / 1e6:.0f} MB at most: send fewer at a time"
            )
        body = {
            "batch": {
                "display_name": f"frame-{kind}",
                "input_config": {"requests": {"requests": requests}},
            }
        }
        answer = self._send("post", BATCH_URL, key, json=body)
        name = answer.json().get("name")
        if not isinstance(name, str) or not name.startswith("batches/"):
            raise NotDrawn(f"Google's batch has no name: {answer.text[:200]}")
        return name

    def batched(
        self, kind: str, batch: str
    ) -> dict[str, tuple[Image.Image, float] | NotDrawn] | None:
        """The answers of a batch by the questions' names: a picture and
        what it cost, or why there is none; None while Google is at it.
        What they cost is counted as ``kind`` once, when they are read.
        Raises :class:`NotDrawn` when the batch itself is lost (expired,
        cancelled, unknown), :class:`AiUnavailable` for the key's trouble."""
        key = self.config.gemini_key
        if not key:
            raise AiUnavailable("no Google API key")
        try:
            answer = self._send("get", f"{BATCHES_URL}/{batch}", key)
        except (Busy, httpx.HTTPError):
            return None  # looked at again next time
        except NotDrawn as err:
            raise NotDrawn(f"batch {batch}: {err}", err.code or "lost") from err
        raw = answer.json()
        state = _state(raw)
        if state in ("PENDING", "RUNNING", "UNSPECIFIED", ""):
            return None
        if state != "SUCCEEDED":
            raise NotDrawn(f"batch {batch}: {state.lower()}", state.lower())
        found: dict[str, tuple[Image.Image, float] | NotDrawn] = {}
        spent = 0.0
        for at, one in enumerate(_answers(raw)):
            name = str((one.get("metadata") or {}).get("key") or at)
            drawn = _drawn(one)
            if not isinstance(drawn, NotDrawn):
                spent += drawn[1]
            found[name] = drawn
        self.spending.add(kind, round(spent, 4))
        return found

    def _send(self, method: str, url: str, key: str, **kw: Any) -> httpx.Response:
        """A request of the Batch, asked again while Google is busy. Raises
        as :meth:`paint` does; :class:`NotDrawn` for other refusals."""
        headers = {"x-goog-api-key": key}
        answer = None
        with self.http() as http:
            for attempt in range(TRIES):
                answer = http.request(method.upper(), url, headers=headers, **kw)
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
            busy = answer.status_code in AGAIN
            raise (Busy if busy else NotDrawn)(said, _code(answer))
        return answer
