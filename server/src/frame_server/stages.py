"""How a work was painted, told in a few sentences in its study ("Jak
powstawał"; Mateusz 2026-11-13, "G2": "mam wątpliwości, bo to troche
wróżenie. chyba że mielibyśmy jakieś dane dotyczęce techniki").

Only for a work whose published technical study the facts from the web
found (``ai.web_facts``: X-rays, infrared, paint samples): Claude tells its
stages as the study does, in two or three sentences, four at most, after
"Kolor i światło". Nothing is guessed when there is no study, and nothing
says where the text came from (Mateusz 2026-11-13 21:42: "rezygnujemy z
rysowania tego przez Gemini. To nie wyglądało dobrze. Samą sekcję
zostawiamy, ale sposób powstawania dzieła tylko opisujemy w 2,3 maks 4
zdaniach. Sekcję umieszczamy po "Kolor i światło". Nie dodajemy przypisu
opisującego genezę powstania tego tekstu.").

Written in the background once the study's page is shown (Sonnet, a
fraction of a cent) and kept for good.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from .ai.client import SONNET, AiUnavailable, request
from .library.markup import strip_markup
from .library.models import ItemKind, Note

if TYPE_CHECKING:
    from .ai.client import Claude
    from .ai.config import AiConfigStore
    from .ai.web_facts import Found, WebFacts
    from .library import Item, Library

log = logging.getLogger(__name__)

KIND = "stages"
#: "stages-1" were pictures drawn by Google's image model: given up.
VERSION = "stages-2"
MODEL = SONNET
#: Sentences at most.
MOST = 4
#: A work whose text could not be had is not asked again for this long.
RETRY_AFTER = 6 * 3600.0

SYSTEM = """Piszesz krótki fragment „Jak powstawał” do „Studium dzieła” w domowej \
aplikacji o sztuce. Dostajesz dzieło i etapy jego powstawania tak, jak je opisuje \
opublikowane badanie techniczne tego obrazu.

Opowiedz, jak dzieło powstawało, w dwóch-trzech zdaniach, najwyżej czterech: od pierwszego \
etapu do ostatniego, to, co najciekawsze (rysunek, podmalówka, warstwy, poprawki malarza). \
Tylko to, co jest w etapach; nic nie dodawaj ani nie zgaduj. Nie pisz, skąd to wiadomo: bez \
nazw instytucji, autorów, publikacji, bez „według badania”, „badacze ustalili”; samą metodę \
(np. „w podczerwieni widać”) wolno wspomnieć, gdy to naturalne. Naturalna, poprawna \
polszczyzna, jak w dobrym polskim muzeum: bez superlatywów, ozdobników i zwrotów do \
czytelnika."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def question(item: Item, found: Found) -> str:
    work = ", ".join(
        p for p in (item.artist, f"„{strip_markup(item.title)}”", item.date_text, item.medium) if p
    )
    listed = "\n".join(
        f"{at}. {s.stage}: {s.text}" for at, s in enumerate(found.technical.stages, start=1)
    )
    return f"Dzieło: {work}\n\nEtapy według badania:\n{listed}"


def sentences(text: str) -> int:
    """About how many sentences the text has."""
    return sum(text.count(end) for end in ".!?") or 1


class PaintingStages:
    """The works' "Jak powstawał", kept as notes of :data:`KIND`."""

    def __init__(
        self, library: Library, claude: Claude, facts: WebFacts, config: AiConfigStore
    ) -> None:
        self.library = library
        self.claude = claude
        self.facts = facts
        self.config = config
        self._lock = threading.Lock()
        self._writing: set[str] = set()
        self._failed: dict[str, float] = {}

    def enabled(self) -> bool:
        return self.config.enabled(KIND)

    def made(self, item: Item) -> str | None:
        """How the work was painted, when it was written."""
        note = self.library.note(item.id, KIND)
        if note is None or note.prompt_version != VERSION:
            return None
        text = str((note.data or {}).get("text") or "").strip()
        return text or None

    def wanted(self, item: Item) -> Found | None:
        """The facts of a work whose text is to be written: a published
        technical study found, nothing written yet."""
        if item.kind != ItemKind.ARTWORK or self.made(item) is not None:
            return None
        found = self.facts.found(item)
        if found is None or not found.technical.found or len(found.technical.stages) < 2:
            return None
        return found

    def write_soon(self, item: Item) -> bool:
        """Writes the text in the background, once; True while it does."""
        if not self.enabled() or self.wanted(item) is None:
            return False
        with self._lock:
            if item.id in self._writing:
                return True
            if time.monotonic() - self._failed.get(item.id, -RETRY_AFTER) < RETRY_AFTER:
                return False
            self._writing.add(item.id)
        threading.Thread(target=self._write, args=(item,), name="stages", daemon=True).start()
        return True

    def _write(self, item: Item) -> None:
        try:
            if not self.write(item):
                with self._lock:
                    self._failed[item.id] = time.monotonic()
        except Exception:
            log.exception("how %s was painted", item.id)
        finally:
            with self._lock:
                self._writing.discard(item.id)

    def write(self, item: Item) -> bool:
        """Writes and keeps the text; False when it could not be had."""
        found = self.wanted(item)
        if found is None:
            return False
        params = request(
            model=MODEL,
            system=SYSTEM,
            content=[{"type": "text", "text": question(item, found)}],
            schema=SCHEMA,
            max_tokens=2000,
        )
        try:
            answer = self.claude.ask(KIND, params)
        except AiUnavailable as err:
            log.warning("how %s was painted not asked: %s", item.id, err)
            return False
        text = " ".join(str((answer.data or {}).get("text") or "").split())
        if not text:
            log.warning("how %s was painted: no answer", item.id)
            return False
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model=MODEL,
                prompt_version=VERSION,
                data={"text": text},
            )
        )
        log.info(
            "how %s was painted: %d sentences, %.4f USD", item.id, sentences(text), answer.cost_usd
        )
        return True
