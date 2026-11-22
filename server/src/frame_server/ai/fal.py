"""fal.ai, where open models run on hired graphics cards: today SeedVR2, the
creative restorer's model (``frame_server.restorer``).

Mateusz 2026-11-22 09:14 UTC ("Zgadzam się na Twoją propozycję"), after two
rounds of trials on 10 museum works (285 pictures, project files
``lokalny-model/``): SeedVR2 (open, Apache 2.0) draws a small picture
larger as Nano Banana did, moved by nothing, its colours off the museum's
by ΔE 1.7–3.5 (Nano Banana's 0.9–2.7, and both are put back in the
picture's colours after), inventing nothing, for some 0.004 USD and 10 s
a work (Nano Banana's Batch 0.03). It refuses nothing either (Google would
not redraw a work it took for a protected one). It is the model a Mac
Studio would run at home later; till then fal runs it.

fal's queue: a picture is sent (``submit``), asked after (``state``) and
its answer fetched (``result``); one work from its card waits for its own
(:meth:`Upscaler.upscale`), the batches of the favourites and playlists
are sent at once and looked at later, as Google's were.

The key is kept from Konfiguracja like Google's (never an environment
variable); what the pictures cost counts in the image models' month's
spending and limit (``Painter.spending``), as "restorer".
"""

from __future__ import annotations

import base64
import io
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from PIL import Image

from .client import AiUnavailable

if TYPE_CHECKING:
    from .client import Spending
    from .config import AiConfigStore

#: The model, as the restorer's notes name it.
MODEL = "seedvr2"
#: fal's endpoint for it, and the app its requests are asked after under.
ENDPOINT = "fal-ai/seedvr/upscale/image"
APP = "fal-ai/seedvr"
QUEUE = "https://queue.fal.run"
#: USD per megapixel of the picture drawn (fal's price list, 2026-11-22).
USD_PER_MP = 0.001
#: About what one work costs (some 2400×1800).
TYPICAL_USD = 0.005
#: The most it enlarges a picture at once.
MOST = 4.0
#: The least worth asking for.
LEAST = 1.25
#: Seconds one work from its card is waited for, and between looks at it.
PATIENCE = 180.0
LOOK = 2.0
#: Its answers' look: the restorer keeps a JPEG of its own after.
FORMAT = "png"


class FalRejected(AiUnavailable):
    """fal does not accept the key."""


class FalNoCredit(AiUnavailable):
    """The account's credit is used up."""


class NotUpscaled(Exception):
    """No picture came back for this one (``code``: fal's word, if any)."""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Asked:
    """One picture in fal's queue."""

    request_id: str
    #: The enlargement asked for.
    factor: float


def factor(size: tuple[int, int], longest: int) -> float:
    """How much a picture of ``size`` is enlarged to reach ``longest`` on
    its long side, within :data:`LEAST`–:data:`MOST`."""
    side = max(size)
    return round(min(MOST, max(LEAST, longest / max(side, 1))), 3)


def cost(size: tuple[int, int]) -> float:
    """What a picture drawn at ``size`` costs."""
    return size[0] * size[1] / 1e6 * USD_PER_MP


def _data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class Upscaler:
    """Asks fal's SeedVR2 and counts what it costs in ``spending``."""

    def __init__(
        self,
        config: AiConfigStore,
        spending: Spending,
        budget_left: Callable[[], float],
        http: Callable[[], httpx.Client] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.spending = spending
        self.budget_left = budget_left
        self.http = http or (lambda: httpx.Client(timeout=60.0))
        self.sleep = sleep

    def enabled(self) -> bool:
        return bool(self.config.fal_key)

    def _headers(self, key: str | None = None) -> dict[str, str]:
        key = key or self.config.fal_key
        if not key:
            raise AiUnavailable("no fal.ai API key")
        return {"Authorization": f"Key {key}"}

    @staticmethod
    def _refused(answer: httpx.Response) -> None:
        if answer.status_code in (401, 403):
            raise FalRejected("fal.ai did not accept the key")
        if answer.status_code == 402 or (
            answer.status_code == 403 and "balance" in answer.text.lower()
        ):
            raise FalNoCredit("fal.ai: the account's credit is used up")

    def check_key(self, key: str) -> None:
        """Raises :class:`FalRejected` when fal refuses ``key``: a request
        that does not exist is asked after (free; a known key hears 404)."""
        url = f"{QUEUE}/{APP}/requests/{uuid.uuid4()}/status"
        with self.http() as http:
            answer = http.get(url, headers=self._headers(key))
        self._refused(answer)

    def submit(self, picture: Image.Image, longest: int) -> Asked:
        """``picture`` sent to be drawn some ``longest`` px on its long side."""
        if self.budget_left() <= 0:
            raise AiUnavailable("this month's limit for the image models is reached")
        times = factor(picture.size, longest)
        body: dict[str, Any] = {
            "image_url": _data_uri(picture),
            "upscale_mode": "factor",
            "upscale_factor": times,
            "output_format": FORMAT,
            # Museum works: a nude is no reason to give nothing back.
            "enable_safety_checker": False,
        }
        with self.http() as http:
            answer = http.post(f"{QUEUE}/{ENDPOINT}", json=body, headers=self._headers())
        self._refused(answer)
        if answer.status_code >= 400:
            raise NotUpscaled(f"fal.ai answered {answer.status_code}: {answer.text[:300]}")
        return Asked(str(answer.json()["request_id"]), times)

    def state(self, request_id: str) -> str:
        """``IN_QUEUE``, ``IN_PROGRESS`` or ``COMPLETED`` (also when it
        failed: :meth:`result` says so); ``LOST`` when fal knows it not."""
        url = f"{QUEUE}/{APP}/requests/{request_id}/status"
        with self.http() as http:
            answer = http.get(url, headers=self._headers())
        self._refused(answer)
        if answer.status_code == 404:
            return "LOST"
        answer.raise_for_status()
        return str(answer.json().get("status", ""))

    def result(self, kind: str, request_id: str) -> tuple[Image.Image, float]:
        """The picture drawn and what it cost, counted as ``kind``; raises
        :class:`NotUpscaled`."""
        url = f"{QUEUE}/{APP}/requests/{request_id}"
        with self.http() as http:
            answer = http.get(url, headers=self._headers())
            self._refused(answer)
            if answer.status_code >= 400:
                raise NotUpscaled(
                    f"fal.ai answered {answer.status_code}: {answer.text[:300]}",
                    _code(answer),
                )
            found = answer.json().get("image") or {}
            link = found.get("url")
            if not link:
                raise NotUpscaled("fal.ai's answer has no picture")
            if str(link).startswith("data:"):
                raw = base64.b64decode(str(link).split(",", 1)[1])
            else:
                got = http.get(str(link))
                got.raise_for_status()
                raw = got.content
        img = Image.open(io.BytesIO(raw))
        img.load()
        usd = cost(img.size)
        self.spending.add(kind, usd)
        return img.convert("RGB"), usd

    def upscale(self, kind: str, picture: Image.Image, longest: int) -> tuple[Image.Image, float]:
        """``picture`` drawn larger now (some 10–30 s), and what it cost."""
        asked = self.submit(picture, longest)
        waited = 0.0
        while True:
            status = self.state(asked.request_id)
            if status == "COMPLETED":
                return self.result(kind, asked.request_id)
            if status == "LOST":
                raise NotUpscaled("fal.ai lost the request")
            if waited >= PATIENCE:
                raise NotUpscaled("fal.ai took too long")
            self.sleep(LOOK)
            waited += LOOK


def _code(answer: httpx.Response) -> str:
    try:
        said = answer.json()
    except ValueError:
        return ""
    if isinstance(said, dict):
        detail = said.get("detail")
        if isinstance(detail, list) and detail and isinstance(detail[0], dict):
            return str(detail[0].get("type", ""))
        return str(said.get("error_type", ""))
    return ""


__all__ = [
    "MODEL",
    "TYPICAL_USD",
    "Asked",
    "FalNoCredit",
    "FalRejected",
    "NotUpscaled",
    "Upscaler",
    "cost",
    "factor",
]
