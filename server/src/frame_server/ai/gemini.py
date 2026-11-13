"""Google's image model (the Interactions API), asked for a picture: the
one client of everything here that has a picture made (the study sheets of
``ai.drawn``; whatever else asks goes through :class:`Painter` too, so that
there is one key, one count of what was spent and one month's limit). Its
embedding model too (:meth:`Painter.embed`): the looks of works,
``library.looks``.

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
#: Google's cheapest image model (Nano Banana 2 Lite): its picture costs as
#: much as :data:`MODEL`'s, what goes in and its words a fifth. Good enough
#: for a simple change of a finished picture (a sheet's spill), not for
#: redrawing a work (trial of 2026-11-13: the study looks like an
#: illustration, the pencil marks wander).
LITE = "gemini-3.1-flash-lite-image"
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
PRICES = {MODEL: (1.50, 7.50, 30.0), LITE: (0.25, 1.50, 30.0)}
PRICE = PRICES[MODEL]
#: Google's words for a question it will not take at all (the picture or
#: the words): nothing is drawn and nothing is paid, so asking again costs
#: nothing, and now and then the same question goes through (a nude:
#: Degas's "Retiring" about one time in four, 2026-11-13).
BLOCKED = ("prohibited_content", "image_prohibited_content", "image_safety", "safety", "blocklist")


def blocked(code: str) -> bool:
    """Whether Google's ``code`` is one of :data:`BLOCKED`."""
    return code.lower() in BLOCKED


#: Google's embedding model: a picture or words as numbers in one space,
#: where works that look alike and the words for how they look lie close.
EMBED_MODEL = "gemini-embedding-2"
EMBED_URL = f"{MODELS_URL}/{EMBED_MODEL}:batchEmbedContents"
#: Numbers kept of each (Google: 768, 1536 or 3072; 768 lose little).
EMBED_SIZE = 768
#: USD per million tokens going in: words, pictures (a picture is 258).
EMBED_PRICES = (0.20, 0.45)
#: At most this many in one request.
EMBED_MAX = 20
#: The embedding model's Batch (answered within a day, at half the price):
#: how the works' pictures get their numbers in the background.
EMBED_BATCH_URL = f"{MODELS_URL}/{EMBED_MODEL}:asyncBatchEmbedContent"
#: Tokens of one picture, to count a batch's cost when its answers do not.
PICTURE_TOKENS = 258

PATIENCE = 300.0
#: Answers worth asking for again: the service is busy or broke off.
AGAIN = (429, 500, 502, 503, 504)
TRIES = 3


class GeminiRejected(AiUnavailable):
    """Google does not accept the key."""


class NoCredit(AiUnavailable):
    """The key's prepaid credit is used up (HTTP 402)."""


class TooHeavy(ValueError):
    """A batch's questions weigh more than Google takes in one request
    (:data:`BATCH_BYTES`): fewer at a time."""


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
    #: How much the model thinks first ("minimal", "medium", "high"; None:
    #: its own default), as :meth:`Painter.paint` takes it.
    think: str | None = None


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


def cost(usage: dict[str, Any], model: str = MODEL) -> float:
    """What an answer of ``model`` cost, by its own count of tokens."""
    into, text, picture = PRICES.get(model, PRICE)
    pictured = sum(
        part.get("tokens", 0)
        for part in usage.get("output_tokens_by_modality") or []
        if str(part.get("modality", "")).lower() == "image"
    )
    said = max(usage.get("total_output_tokens", 0) - pictured, 0)
    said += usage.get("total_thought_tokens", 0)
    spent = usage.get("total_input_tokens", 0) * into + said * text + pictured * picture
    return round(spent / 1e6, 4)


def embed_cost(usage: dict[str, Any]) -> float:
    """What a request of the embedding model cost (its ``usageMetadata``)."""
    words, pictures = EMBED_PRICES
    by = {
        str(part.get("modality", "")).lower(): part.get("tokenCount", 0)
        for part in usage.get("promptTokenDetails") or []
    }
    if not by:
        by = {"text": usage.get("promptTokenCount", 0)}
    spent = by.get("text", 0) * words + by.get("image", 0) * pictures
    return round(spent / 1e6, 6)


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
    config: dict[str, Any] = {
        "responseModalities": ["IMAGE"],
        "imageConfig": {"imageSize": ask.size},
    }
    if ask.think:
        config["thinkingConfig"] = {"thinkingLevel": ask.think}
    return {"contents": [{"role": "user", "parts": parts}], "generation_config": config}


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
        if inlined is None:  # the embedding model's batch
            inlined = node.get("inlinedEmbedContentResponses")
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
        if "prohibited content" in str(error.get("message") or "").lower():
            code = "prohibited_content"
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
    held = (response.get("promptFeedback") or {}).get("blockReason")
    code = next((r for r in [*reasons, str(held or "")] if r and r != "STOP"), "")
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
        self,
        kind: str,
        prompt: str,
        pictures: Sequence[Image.Image],
        size: str = "1K",
        *,
        model: str = MODEL,
        think: str | None = None,
    ) -> tuple[Image.Image, float]:
        """The picture of ``model`` in answer to ``prompt`` and ``pictures``
        (``size``: "1K", "2K", "4K"; ``think``: how much it thinks first,
        None for its default), and what it cost, counted as ``kind`` in the
        month's spending. Raises :class:`AiUnavailable` (no key, the
        month's limit, :class:`GeminiRejected`, :class:`NoCredit`) or
        :class:`NotDrawn` (this answer)."""
        key = self.config.gemini_key
        if not key:
            raise AiUnavailable("no Google API key")
        self.check_budget()
        body: dict[str, Any] = {
            "model": model,
            "input": [{"type": "text", "text": prompt}, *(_block(p) for p in pictures)],
            "response_format": {"type": "image", "image_size": size},
        }
        if think:
            body["generation_config"] = {"thinking_level": think}
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
        usd = cost(raw.get("usage") or {}, model)
        self.spending.add(kind, usd)
        found: list[str] = []
        _pictures(raw, found)
        if not found:
            raise NotDrawn("Google's answer has no picture")
        img = Image.open(io.BytesIO(base64.b64decode(found[-1])))
        img.load()
        return img.convert("RGB"), usd

    def embed(self, kind: str, inputs: Sequence[Image.Image | str]) -> list[list[float]]:
        """The numbers of each of ``inputs`` (a picture, or words as they
        are, with their task's prefix if any) in the embedding model's
        space, :data:`EMBED_SIZE` of them, in order; counted as ``kind``.
        Raises as :meth:`paint` does; :class:`NotDrawn` for an answer that
        is not one."""
        key = self.config.gemini_key
        if not key:
            raise AiUnavailable("no Google API key")
        if not inputs or len(inputs) > EMBED_MAX:
            raise ValueError(f"1 to {EMBED_MAX} inputs at a time")
        self.check_budget()
        requests = []
        for one in inputs:
            part: dict[str, Any] = (
                {"text": one}
                if isinstance(one, str)
                else {"inline_data": {"mime_type": "image/jpeg", "data": _jpeg(one)}}
            )
            requests.append(
                {
                    "model": f"models/{EMBED_MODEL}",
                    "content": {"parts": [part]},
                    "output_dimensionality": EMBED_SIZE,
                }
            )
        raw = self._send("post", EMBED_URL, key, json={"requests": requests}).json()
        found = [e.get("values") for e in raw.get("embeddings") or []]
        if len(found) != len(inputs) or not all(isinstance(v, list) and v for v in found):
            raise NotDrawn(f"Google's embeddings do not fit the question: {str(raw)[:200]}")
        self.spending.add(kind, embed_cost(raw.get("usageMetadata") or {}))
        return [[float(x) for x in v] for v in found]

    def embed_batch(self, kind: str, pictures: Sequence[tuple[str, Image.Image]]) -> str:
        """Hands pictures (each under a name of its own) to the embedding
        model's Batch, at half the price: the batch's name, to ask
        :meth:`embed_batched` with. Raises as :meth:`batch` does."""
        key = self.config.gemini_key
        if not key:
            raise AiUnavailable("no Google API key")
        names = [name for name, _ in pictures]
        if not names or len(set(names)) != len(names):
            raise ValueError("a batch needs pictures, each under a name of its own")
        self.check_budget()
        requests = [
            {
                "request": {
                    "content": {
                        "parts": [{"inline_data": {"mime_type": "image/jpeg", "data": _jpeg(img)}}]
                    },
                    "output_dimensionality": EMBED_SIZE,
                },
                "metadata": {"key": name},
            }
            for name, img in pictures
        ]
        weight = sum(len(json.dumps(r)) for r in requests)
        if weight > BATCH_BYTES:
            raise TooHeavy(
                f"a batch of {len(pictures)} pictures weighs {weight / 1e6:.1f} MB, "
                f"Google takes {BATCH_BYTES / 1e6:.0f} MB at most: send fewer at a time"
            )
        body = {
            "batch": {
                "display_name": f"frame-{kind}",
                "input_config": {"requests": {"requests": requests}},
            }
        }
        answer = self._send("post", EMBED_BATCH_URL, key, json=body)
        name = answer.json().get("name")
        if not isinstance(name, str) or not name.startswith("batches/"):
            raise NotDrawn(f"Google's batch has no name: {answer.text[:200]}")
        return name

    def embed_batched(self, kind: str, batch: str) -> dict[str, list[float] | None] | None:
        """The numbers of a batch's pictures by their names (None for one
        Google did not answer); None while Google is at it. What they cost
        is counted as ``kind`` once, when they are read. Raises as
        :meth:`batched` does."""
        key = self.config.gemini_key
        if not key:
            raise AiUnavailable("no Google API key")
        try:
            answer = self._send("get", f"{BATCHES_URL}/{batch}", key)
        except (Busy, httpx.HTTPError):
            return None
        except NotDrawn as err:
            raise NotDrawn(f"batch {batch}: {err}", err.code or "lost") from err
        raw = answer.json()
        state = _state(raw)
        if state in ("PENDING", "RUNNING", "UNSPECIFIED", ""):
            return None
        if state != "SUCCEEDED":
            raise NotDrawn(f"batch {batch}: {state.lower()}", state.lower())
        found: dict[str, list[float] | None] = {}
        spent = 0.0
        for at, one in enumerate(_answers(raw)):
            name = str((one.get("metadata") or {}).get("key") or at)
            reply = one.get("response") if isinstance(one.get("response"), dict) else one
            values = ((reply or {}).get("embedding") or {}).get("values")
            if isinstance(values, list) and values:
                found[name] = [float(x) for x in values]
                usage = (reply or {}).get("usageMetadata")
                tokens = (reply or {}).get("tokenCount")
                if isinstance(usage, dict):
                    spent += embed_cost(usage)
                else:  # a picture's tokens, as the answer counts them or as they are
                    count = int(str(tokens)) if str(tokens or "").isdigit() else PICTURE_TOKENS
                    spent += count * EMBED_PRICES[1] / 1e6
            else:
                found[name] = None
        self.spending.add(kind, round(spent * BATCH_SHARE, 6))
        return found

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
            raise TooHeavy(
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
