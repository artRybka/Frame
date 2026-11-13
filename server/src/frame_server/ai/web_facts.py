"""Facts about a work from the web, for its study (Mateusz 2026-11-13, "G8":
"może dodać dodatkowych, cennych informacji do studium"; "nie dodajemy
linków w Studium, to zepsułoby jego naturalny charakter").

Before a study is written Claude (Sonnet) searches the web (Anthropic's
web search tool, a few searches) for what only someone who read the
sources knows: conservation and technical studies, the work's fortunes,
exhibitions, how it was received, the painter's own words about it. The
facts go into the study's question as one more source, to be woven into the
text; the pages they came from are kept nowhere (Mateusz 2026-11-13 11:43,
"Claude, źródeł nigdzie"). Google's own search (Gemini's grounding) may not
be stored nor written over, so it is not used.

A published technical study's stages of painting are kept with the facts:
the study's "Jak powstawał" (``G2``) is told only from them, never guessed.

One question per work, kept as a note of :data:`KIND`: a study written
again asks nothing more.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import TYPE_CHECKING, Any

import anthropic
from pydantic import BaseModel, Field, ValidationError

from ..library.markup import strip_markup
from ..library.models import ItemKind, Note
from .client import SONNET, AiUnavailable
from .jobs import text_hash

if TYPE_CHECKING:
    from ..library import Item, Library
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "web_facts"
#: The owner's switch (``AiConfig.web_facts``).
SWITCH = "web_facts"
VERSION = "web-facts-1"
#: How long it thinks: "low" with :data:`SPARING` found as much as "medium"
#: without it (the trial above).
EFFORT = "low"
MODEL = SONNET
#: Searches one question may make at most (each 0.01 USD): six found as
#: much as ten in the trial (van Gogh's "Bedroom": 15 facts, about 0.30 USD).
#: It searches once first and goes on only where the work was written about
#: (:data:`SPARING`; Mateusz 2026-11-13: "gdy do dzieła wyników nie ma, albo
#: są skąpe już przy pierwszym wyszukaniu to może nie warto robić kolejnych?").
#: On ten works through the Batch: 2 searches a work instead of 6, 0.036 USD
#: instead of 0.088, 40 facts instead of 43, three technical studies instead
#: of one (six asked at once had all gone on general pages).
SEARCHES = 6
#: Facts kept for a study at most.
MOST = 16
#: A work whose facts could not be had is not asked again for this long.
RETRY_AFTER = 6 * 3600.0

SYSTEM = """Zbierasz fakty do „Studium dzieła” w domowej aplikacji o sztuce. Studium samo \
opisze kompozycję, barwy i ogólny kontekst, a dostaje też opis muzeum i Wikipedię; brakuje \
w nim faktów, które zna tylko ktoś, kto czytał źródła: badania konserwatorskie i techniczne \
(RTG, reflektografia w podczerwieni, analiza pigmentów, zmiany wprowadzone przez malarza, \
podkład, warstwy), losy dzieła, wystawy, odbiór krytyki, listy i słowa artysty o tym dziele, \
ciekawostki muzeum.

Szukaj w sieci. Bierz tylko fakty o TYM dziele (nie o innej wersji czy kopii, chyba że \
wyraźnie tak napiszesz), potwierdzone przez wiarygodne źródło (muzeum, katalog, publikacja \
naukowa, poważna prasa); pomijaj to, co ogólnie znane i oczywiste. Każdy fakt to jedno-dwa \
zdania po polsku, naturalnie, gotowe do wplecenia w tekst: bez adresów stron, bez nazw \
portali, bez „według źródła”, bez dat dostępu. Gdy nic wartościowego nie znajdziesz, zwróć \
pustą listę; nie wymyślaj.

Osobno: jeśli istnieje opublikowane badanie techniczne tego dzieła, opisz z niego kolejne \
etapy powstawania (rysunek, podmalówka, warstwy, poprawki) tak, jak je opisuje badanie, \
od pierwszego do ostatniego; jeśli takiego badania nie ma, napisz found=false i nie zgaduj.

Na końcu odpowiedz wyłącznie blokiem ```json z polami:
{"facts":[{"kind":"technika|losy|wystawy|odbiór|słowa artysty|ciekawostka","text":"…"}],
 "technical_study":{"found":true|false,"what":"czyje badanie i jakimi metodami",\
"stages":[{"stage":"krótka nazwa etapu","text":"…"}]}}"""

SPARING = """

Oszczędzaj wyszukania: zacznij od jednego ogólnego wyszukania tego dzieła. Szukaj dalej \
tylko wtedy, gdy wyniki pokazują, że o tym dziele coś napisano (strona muzeum z opisem, \
katalog, artykuł, badanie). Gdy pierwsze wyszukanie daje tylko podstawowe dane albo nic, \
zakończ od razu i zwróć to, co masz (także pustą listę)."""


class Fact(BaseModel):
    kind: str = ""
    text: str


class Stage(BaseModel):
    stage: str = ""
    text: str


class Technical(BaseModel):
    """A published technical study of the work, its stages as it tells them."""

    found: bool = False
    what: str = ""
    stages: list[Stage] = Field(default_factory=list)


class Found(BaseModel):
    facts: list[Fact] = Field(default_factory=list)
    technical: Technical = Field(default_factory=Technical)


#: What a page's address or name would leave in a fact.
_URL = re.compile(r"\(?\s*(?:https?://|www\.)\S+\s*\)?")
_CITED = re.compile(r"\s*\[\d+\]")


def _plain(text: Any, limit: int = 600) -> str:
    """A fact without the addresses, footnote marks and markup a model may
    leave in it."""
    out = _CITED.sub("", _URL.sub("", strip_markup(str(text or ""))))
    out = " ".join(out.split()).replace(" .", ".").replace(" ,", ",")
    return out[:limit].strip()


def last_json(text: str) -> dict[str, Any] | None:
    """The answer's last JSON block (or its last ``{...}``); None when there
    is none."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = blocks[-1] if blocks else text[text.find("{") : text.rfind("}") + 1]
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse(text: str) -> Found | None:
    """The answer's facts and technical study, cleaned; None without them."""
    data = last_json(text)
    if data is None:
        return None
    facts = [
        Fact(kind=_plain(f.get("kind"), 40), text=_plain(f.get("text")))
        for f in data.get("facts") or []
        if isinstance(f, dict)
    ]
    study = data.get("technical_study")
    study = study if isinstance(study, dict) else {}
    stages = [
        Stage(stage=_plain(s.get("stage"), 80), text=_plain(s.get("text")))
        for s in study.get("stages") or []
        if isinstance(s, dict)
    ]
    stages = [s for s in stages if s.text]
    technical = Technical(
        # Two stages at least: one is no way a work was made.
        found=bool(study.get("found")) and len(stages) >= 2,
        what=_plain(study.get("what"), 300),
        stages=stages,
    )
    return Found(facts=[f for f in facts if f.text][:MOST], technical=technical)


def question(item: Item) -> str:
    parts = [
        item.artist,
        f"„{strip_markup(item.title)}”",
        item.date_text,
        item.medium,
        item.held_by or item.museum,
    ]
    return "Dzieło: " + ", ".join(p for p in parts if p)


def request(item: Item) -> dict[str, Any]:
    return {
        "model": MODEL,
        "max_tokens": 16000,
        "system": [
            {"type": "text", "text": SYSTEM + SPARING, "cache_control": {"type": "ephemeral"}}
        ],
        "messages": [{"role": "user", "content": question(item)}],
        "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": SEARCHES}],
        "output_config": {"effort": EFFORT},
        "timeout": 600.0,
    }


class WebFacts:
    """The works' facts from the web, kept as notes of :data:`KIND`."""

    def __init__(self, library: Library, claude: Claude, config: AiConfigStore) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        self._lock = threading.Lock()
        self._asking: dict[str, threading.Lock] = {}
        #: Works whose facts could not be had, and when.
        self._failed: dict[str, float] = {}

    def enabled(self) -> bool:
        return self.config.enabled(SWITCH)

    @staticmethod
    def source_hash(item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def found(self, item: Item) -> Found | None:
        """What was found for the work, if it was asked about (and the work
        is still the same)."""
        note = self.library.note(item.id, KIND)
        if note is None or note.prompt_version != VERSION:
            return None
        if note.source_hash != self.source_hash(item):
            return None
        try:
            return Found.model_validate(note.data)
        except ValidationError:
            return None

    def gather(self, item: Item) -> Found | None:
        """The work's facts, asked now when they never were (a study about
        to be written). None without them: no key, the switch off, the
        month's limit, an error (tried again after :data:`RETRY_AFTER`)."""
        if item.kind != ItemKind.ARTWORK:
            return None
        if (have := self.found(item)) is not None or not self.enabled():
            return have
        with self._lock:
            if time.monotonic() - self._failed.get(item.id, -RETRY_AFTER) < RETRY_AFTER:
                return None
            lock = self._asking.setdefault(item.id, threading.Lock())
        with lock:  # the day's page and the card's study at once: asked once
            if (have := self.found(item)) is not None:
                return have
            found = self._ask(item)
        with self._lock:
            self._asking.pop(item.id, None)
            if found is None:
                self._failed[item.id] = time.monotonic()
        return found

    def _ask(self, item: Item) -> Found | None:
        started = time.monotonic()
        try:
            text, usd, stop = self.claude.search(KIND, request(item))
        except (AiUnavailable, anthropic.APIError) as err:
            log.warning("facts of %s from the web not asked: %s", item.id, err)
            return None
        found = parse(text) if stop != "refusal" else None
        if found is None:
            log.warning("facts of %s from the web: no answer (%s, %.2f USD)", item.id, stop, usd)
            return None
        log.info(
            "facts of %s from the web: %d, technical study %s, %.0f s, %.2f USD",
            item.id,
            len(found.facts),
            "found" if found.technical.found else "none",
            time.monotonic() - started,
            usd,
        )
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model=MODEL,
                prompt_version=VERSION,
                source_hash=self.source_hash(item),
                data=found.model_dump(),
            )
        )
        return found

    def for_study(self, item: Item) -> list[str]:
        """The facts as the study's question lists them."""
        found = self.gather(item)
        return [f.text for f in found.facts] if found else []
