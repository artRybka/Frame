"""The studies written before the facts from the web, filled in (Mateusz
2026-11-13 12:42: "Czy masz pomysł jak przepisać tylko te wcześniejsze
studia gdzie warto? Na pewno pomożemy zostawić stare analizy kompozycji.";
12:49, on the card: "Tak, z przyciskiem").

The owner starts it from Konfiguracja, which shows how many studies have no
facts from the web yet and about what it would cost. Two orders of the
Batch API follow, at half the price:

1. Claude (Sonnet, the web search) is asked about each such work as a new
   study would be (``ai.web_facts``), shown the study already written: only
   facts missing from it, and how much they would add ("worth", 0–3). They
   are kept as the work's facts (its stages of painting too: "Jak
   powstawał" then appears, ``stages``).
2. Where they add much (:data:`WORTH`), Opus rewrites the study's text about
   the work's circumstances and its colour with them woven in. Its other
   parts stay as they were: the analysis of composition and its sheets,
   the details, the work's road, the artist's line of life, the similar
   works. The text before is kept on the page (:data:`REFRESHED`).

A thread follows the orders until both are in (each within a day), also
after a restart.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from ..library.models import ItemKind, Note
from . import web_facts
from .client import OPUS, SEARCH_USD, AiUnavailable, cost, request
from .daily import KIND as DAILY
from .daily import _text
from .night_order import NightOrder
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import Item, Library
    from .client import Claude
    from .web_facts import WebFacts

log = logging.getLogger(__name__)

#: What the spending is counted under.
KIND = "study_refresh"
STATE = "study_refresh"
VERSION = "refresh-1"
#: The pages a study is kept as: the study of a work and the day's page.
PAGES = (STUDY, DAILY)
#: The page's text before it was filled in, and with what.
REFRESHED = "refreshed"
#: The fields rewritten; everything else on the page stays.
FIELDS = ("headline", "context", "colour")
#: How much the new facts must add for the text to be rewritten (of 0–3).
WORTH = 2
#: About what each step costs a study through the Batch API: the search
#: (Sonnet's tokens halved, its six searches not) and the rewrite (Opus,
#: text only).
FACTS_USD = 0.18
REWRITE_USD = 0.06
#: Of the studies asked about, about how many get rewritten (a guess, told
#: as "up to" in the app until the first answers are in).
REWRITE_SHARE = 0.5
#: Tries for a work whose answer did not come (an error, no JSON).
TRIES = 2
#: How often the thread looks at its batches, and waits when it has none.
POLL = 300.0
IDLE = 3600.0

ASK = (
    "\n\nSTUDIUM JUŻ NAPISANE O TYM DZIELE (szukaj faktów, których w nim nie ma; tego, co już "
    "jest, nie powtarzaj):\n{study}\n\n"
    'W bloku JSON dodaj pole "worth": liczba 0–3, ile nowe fakty wniosą do tego tekstu '
    "(0: nic, 1: drobiazgi, 2: wyraźnie go wzbogacą, 3: zmieniają to, co wiadomo o dziele)."
)

SYSTEM = """Uzupełniasz napisane już „Studium dzieła” w domowej aplikacji o sztuce o nowe \
fakty z wiarygodnych źródeł. Dostajesz obecny tekst i listę faktów.

Przepisz tylko trzy pola:
- "headline": tytuł tekstu o okolicznościach (2–6 słów, bez kropki), konkretny dla tego \
dzieła. Zmień go tylko wtedy, gdy nowa treść tego wymaga.
- "context": dwa, najwyżej trzy krótkie akapity (po 300–550 znaków): kiedy i w jakich \
okolicznościach dzieło powstało, czym się wyróżniało, jak je przyjęto, jakie miało losy. \
Zacznij od tego, co w tej historii najciekawsze dla tego dzieła, nie od formuły \
„Obraz powstał…”.
- "colour": dwa-trzy zdania o kolorze i świetle (tu pasują fakty o farbach i warstwach).

Zasady:
- Zachowaj to, co w tekście dobre i prawdziwe, jego ton i długość. Wpleć te fakty, które \
naprawdę go wzbogacają, tam, gdzie pasują, naturalnie, bez wzmianki o źródłach, stronach czy \
szukaniu, bez adresów.
- Nie dodawaj niczego spoza obecnego tekstu i listy faktów. Gdy fakt przeczy tekstowi, \
wierz faktowi.
- Pole, do którego fakty nic nie wnoszą, zwróć bez zmian.
- Naturalna, poprawna polszczyzna, jak w dobrym polskim muzeum: bez superlatywów, ozdobników \
i zwrotów do czytelnika."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "context": {"type": "array", "items": {"type": "string"}},
        "colour": {"type": "string"},
    },
    "required": ["headline", "context", "colour"],
    "additionalProperties": False,
}


def study_text(data: dict[str, Any]) -> str:
    """What a page tells in words, as the questions show it."""
    parts = [
        str(data.get("teaser") or ""),
        str(data.get("headline") or ""),
        *[str(p) for p in data.get("context") or []],
        str(data.get("artist") or ""),
        str(data.get("colour") or ""),
    ]
    return "\n\n".join(p for p in parts if p.strip())


def worth_of(text: str) -> int:
    """The answer's "worth" (0 when it has none)."""
    data = web_facts.last_json(text) or {}
    try:
        return max(0, min(3, int(data.get("worth") or 0)))
    except (TypeError, ValueError):
        return 0


class StudyRefresh(NightOrder):
    """Fills in the studies written before the facts from the web."""

    name = "study refresh"

    def __init__(self, library: Library, claude: Claude, facts: WebFacts) -> None:
        self.library = library
        self.claude = claude
        self.facts = facts
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # -- what waits ----------------------------------------------------------

    def _state(self) -> dict[str, Any]:
        return dict(self.library.get_state(STATE, {}) or {})

    def _save(self, state: dict[str, Any]) -> None:
        self.library.set_state(STATE, state)

    def _pages(self) -> dict[str, list[Note]]:
        """The written pages, by work."""
        out: dict[str, list[Note]] = {}
        for kind in PAGES:
            for item_id, note in self.library.notes(kind).items():
                if "teaser" in note.data and note.data.get("context"):
                    out.setdefault(item_id, []).append(note)
        return out

    def _found(self) -> dict[str, Note]:
        return {
            item_id: note
            for item_id, note in self.library.notes(web_facts.KIND).items()
            if note.prompt_version == web_facts.VERSION
        }

    def waiting(self) -> list[str]:
        """Works with a study and no facts from the web yet (those that
        failed :data:`TRIES` times left out)."""
        found, tries = self._found(), self._state().get("tries", {})
        return [
            item_id
            for item_id in self._pages()
            if item_id not in found and tries.get(item_id, 0) < TRIES
        ]

    def to_rewrite(self) -> list[str]:
        """Works whose facts were asked for their study and add much to it,
        with a page not yet filled in."""
        found = self._found()
        out = []
        for item_id, notes in self._pages().items():
            note = found.get(item_id)
            if note is None or int(note.data.get("worth") or 0) < WORTH:
                continue
            if not note.data.get("facts"):
                continue
            if any(REFRESHED not in n.data for n in notes):
                out.append(item_id)
        return out

    def view(self) -> dict[str, Any]:
        """What Konfiguracja shows."""
        state = self._state()
        waiting, rewrite = len(self.waiting()), len(self.to_rewrite())
        return {
            "waiting": waiting,
            "rewrite_waiting": rewrite,
            "running": bool(state.get("facts") or state.get("rewrite")),
            "asked": len((state.get("facts") or {}).get("items", [])),
            "rewriting": len((state.get("rewrite") or {}).get("items", [])),
            "found": int(state.get("found", 0)),
            "rewritten": int(state.get("rewritten", 0)),
            "spent_usd": round(float(state.get("usd", 0.0)), 2),
            "facts_usd": round(waiting * FACTS_USD, 2),
            "rewrite_usd": round((rewrite + waiting * REWRITE_SHARE) * REWRITE_USD, 2),
        }

    # -- the orders ------------------------------------------------------------

    def _item(self, item_id: str) -> Item | None:
        item = self.library.get(item_id)
        return item if item is not None and item.kind == ItemKind.ARTWORK else None

    def facts_request(self, item: Item, page: Note) -> dict[str, Any]:
        params = web_facts.request(item)
        text = web_facts.question(item) + ASK.format(study=study_text(page.data))
        return {**params, "messages": [{"role": "user", "content": text}]}

    def rewrite_request(self, item: Item, page: Note, facts: list[str]) -> dict[str, Any]:
        data = page.data
        lines = [
            web_facts.question(item),
            "",
            "OBECNY TEKST",
            f'"headline": {data.get("headline") or ""}',
            '"context":',
            *[f"{p}" for p in data.get("context") or []],
            f'"colour": {data.get("colour") or ""}',
            "",
            "Dla porządku, reszta studium (bez zmian, nie powtarzaj jej):",
            str(data.get("teaser") or ""),
            str(data.get("artist") or ""),
            "",
            "NOWE FAKTY",
            *(f"- {f}" for f in facts),
        ]
        return request(
            model=OPUS,
            system=SYSTEM,
            content=[{"type": "text", "text": "\n".join(lines)}],
            schema=SCHEMA,
            max_tokens=8000,
            effort="medium",
        )

    def start(self) -> int:
        """The owner's tap: the studies without facts asked about now (one
        batch). How many; 0 when an order is under way or none waits."""
        with self._lock:
            state = self._state()
            if state.get("facts"):
                return 0
            pages = self._pages()
            requests: list[dict[str, Any]] = []
            items: list[str] = []
            for item_id in self.waiting():
                item = self._item(item_id)
                if item is None or self.facts.found(item) is not None:
                    continue
                page = next((n for n in pages[item_id] if n.kind == STUDY), pages[item_id][0])
                requests.append(
                    {"custom_id": f"f{len(items)}", "params": self.facts_request(item, page)}
                )
                items.append(item_id)
            if not requests:
                return 0
            batch = self.send(requests)
            if batch is None:
                return 0
            state["facts"] = {"batch": batch, "items": items}
            self._save(state)
        log.info("study refresh: facts of %d studies asked (batch %s)", len(items), batch)
        self._wake.set()
        return len(items)

    def order_rewrites(self) -> int:
        """The studies whose facts add much rewritten (one batch)."""
        with self._lock:
            state = self._state()
            if state.get("rewrite"):
                return 0
            pages, found = self._pages(), self._found()
            requests: list[dict[str, Any]] = []
            items: list[str] = []
            for item_id in self.to_rewrite():
                item = self._item(item_id)
                if item is None:
                    continue
                facts = [str(f.get("text") or "") for f in found[item_id].data.get("facts") or []]
                page = next((n for n in pages[item_id] if n.kind == STUDY), pages[item_id][0])
                requests.append(
                    {
                        "custom_id": f"r{len(items)}",
                        "params": self.rewrite_request(item, page, facts),
                    }
                )
                items.append(item_id)
            if not requests:
                return 0
            batch = self.send(requests)
            if batch is None:
                return 0
            state["rewrite"] = {"batch": batch, "items": items}
            self._save(state)
        log.info("study refresh: %d studies to be rewritten (batch %s)", len(items), batch)
        return len(items)

    # -- the answers -----------------------------------------------------------

    def collect(self) -> bool | None:
        """Both orders' answers put in, once their batches ended: True when
        one was, False while they run, None without an order."""
        state = self._state()
        if not state.get("facts") and not state.get("rewrite"):
            return None
        done = False
        # (a rewrite ordered once the facts are in waits for the next look)
        if state.get("rewrite"):
            done = self._collect_rewrites() or done
        if state.get("facts"):
            done = self._collect_facts() or done
        return done

    def _spent(self, state: dict[str, Any], usd: float) -> None:
        state["usd"] = float(state.get("usd", 0.0)) + usd
        self.claude.spending.add(KIND, usd)

    def _collect_facts(self) -> bool:
        order = self._state()["facts"]
        results = self.answers(order["batch"])
        if results is None:
            return False
        items: list[str] = order["items"]
        by_id = dict(results)
        with self._lock:
            state = self._state()
            tries: dict[str, int] = dict(state.get("tries", {}))
            usd, kept = 0.0, 0
            for n, item_id in enumerate(items):
                message = by_id.get(f"f{n}")
                if message is not None:
                    tools = getattr(message.usage, "server_tool_use", None)
                    searches = (getattr(tools, "web_search_requests", 0) or 0) if tools else 0
                    usd += cost(web_facts.MODEL, message.usage, batch=True) + searches * SEARCH_USD
                if not self._keep_facts(item_id, message):
                    tries[item_id] = tries.get(item_id, 0) + 1
                else:
                    kept += 1
            state.pop("facts", None)
            state["tries"] = tries
            state["found"] = int(state.get("found", 0)) + kept
            self._spent(state, usd)
            self._save(state)
        log.info("study refresh: facts of %d of %d studies kept, %.2f USD", kept, len(items), usd)
        self.order_rewrites()
        return True

    def _keep_facts(self, item_id: str, message: Any) -> bool:
        item = self._item(item_id)
        if item is None or message is None or message.stop_reason == "refusal":
            return False
        text = "".join(b.text for b in message.content if b.type == "text")
        found = web_facts.parse(text)
        if found is None:
            return False
        self.library.save_note(
            Note(
                item_id=item_id,
                kind=web_facts.KIND,
                model=web_facts.MODEL,
                prompt_version=web_facts.VERSION,
                source_hash=self.facts.source_hash(item),
                data={**found.model_dump(), "worth": worth_of(text), "refresh": VERSION},
            )
        )
        return True

    def _collect_rewrites(self) -> bool:
        order = self._state()["rewrite"]
        results = self.answers(order["batch"])
        if results is None:
            return False
        items: list[str] = order["items"]
        by_id = dict(results)
        usd, written = 0.0, 0
        for n, item_id in enumerate(items):
            message = by_id.get(f"r{n}")
            if message is None:
                continue
            answer = self.claude.answer(KIND, OPUS, message, batch=True)
            usd += answer.cost_usd
            if answer.data and self.rewrite(item_id, answer.data):
                written += 1
        with self._lock:
            state = self._state()
            state.pop("rewrite", None)
            state["rewritten"] = int(state.get("rewritten", 0)) + written
            # (the answers' cost is counted by ``answer``)
            state["usd"] = float(state.get("usd", 0.0)) + usd
            # A study whose rewrite came to nothing is not asked again.
            for item_id in items:
                self._mark(item_id)
            self._save(state)
        log.info("study refresh: %d of %d studies rewritten, %.2f USD", written, len(items), usd)
        return True

    def rewrite(self, item_id: str, data: dict[str, Any]) -> bool:
        """The answer's text on every page of the work, the text before
        kept; False when it is no usable text."""
        context = [_text(p, 900) for p in data.get("context") or [] if _text(p)][:3]
        if len(context) < 2:
            return False
        new = {
            "headline": _text(data.get("headline"), 80).rstrip("."),
            "context": context,
            "colour": _text(data.get("colour"), 500),
        }
        changed = False
        for kind in PAGES:
            note = self.library.note(item_id, kind)
            if note is None or "teaser" not in note.data:
                continue
            before = {k: note.data.get(k) for k in FIELDS}
            fresh = {k: v or before[k] for k, v in new.items()}
            refreshed = {"version": VERSION, "before": before}
            self.library.save_note(
                note.model_copy(update={"data": {**note.data, **fresh, REFRESHED: refreshed}})
            )
            changed = True
        return changed

    def _mark(self, item_id: str) -> None:
        """A page left as it was marked asked, so the work is not rewritten
        again."""
        for kind in PAGES:
            note = self.library.note(item_id, kind)
            if note is None or "teaser" not in note.data or REFRESHED in note.data:
                continue
            self.library.save_note(
                note.model_copy(
                    update={"data": {**note.data, REFRESHED: {"version": VERSION, "kept": True}}}
                )
            )

    # -- the thread ----------------------------------------------------------

    def start_thread(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="study-refresh", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            pause = IDLE
            try:
                if self.collect() is not None or (self.to_rewrite() and self.order_rewrites()):
                    pause = POLL
            except AiUnavailable as err:
                log.info("study refresh: %s", err)
            except Exception:
                log.exception("study refresh: a round failed")
            self._wake.wait(pause)
            self._wake.clear()
