"""What the owner does with "Do sprawdzenia" in one tap (Mateusz 2026-11-15:
„Muszę tu mieć opcję większego podglądu … co mam robić z tymi pozycjami?”,
then on the decision card: „Pełne poprawki jednym dotknięciem”).

The night audit (:mod:`.audit`) only says what does not add up; until now
"Sprawdzone" was all the list offered, and a wrong title could not be
mended in the app at all. Each finding now carries its own remedy:

- a title, a maker or a date: the corrected value (``fix``; for a title also
  its Polish ``fix_pl``), asked of the audit at night, or of Haiku when the
  owner opens a finding written before (:meth:`ReviewFixes.suggest`); the
  owner's "Popraw" puts it on the work (:meth:`ReviewFixes.apply`), the
  Polish title at once, the Polish text written anew from the new facts;
- a picture with a ruler, a colour chart or a cut edge: "Przytnij" asks
  Opus for the work's corners at once, told what the audit saw
  (:meth:`ReviewFixes.cut`), and the cut is kept as the owner's;
- a picture to be had better elsewhere: the app's copies sheet, after which
  the finding is let go (:meth:`ReviewFixes.drop`);
- anything: "Ukryj" takes the work out of the catalogue (:meth:`ReviewFixes.hide`).

What the gatekeeper wrote about a work it set aside ("why") was English:
the night now writes it in Polish as well (``why_pl``), and what was written
before is translated once, in one short question (:meth:`ReviewFixes.translate`).
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..imaging.text import MAX_BODY
from ..library.viewer import OWNER_ID
from .client import HAIKU, SONNET, image_block, request
from .daily import _object, _str
from .pl_text import _paragraphs, _plain, frame_text

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .audit import Audit
    from .client import Claude
    from .crops import Crops
    from .gatekeeper import Gatekeeper
    from .pl_text import PlTextJob

log = logging.getLogger(__name__)

#: The audit's fields the owner mends with a value.
VALUED = ("title", "artist", "date")
#: Longest value kept.
VALUE_CHARS = 300
#: Gatekeeper's notes translated in one question at most.
TRANSLATE_AT_ONCE = 60

SUGGEST = """You help the owner of a home art frame mend the catalogue. You get one artwork \
(its picture and what the catalogue knows of it) and problems a check found in its title, \
maker or date. For each problem give the corrected value as the catalogue should keep it:

- "fix": for a title, the work's proper title in the language of the catalogue's title, \
without auction or sale notes, dimensions, inventory numbers or a photographer's words; for a \
maker, the maker's name as usually written; for a date, the date as a short text ("1889", \
"c. 1650", "1910-1912"). "" when you cannot tell.
- "fix_pl": for a title only, the proper Polish title of the work (as Polish museums and \
books name it, or a faithful translation); "" for a maker or a date.

Answer with one entry per problem, in the order given."""

SUGGEST_SCHEMA = _object(
    fixes={
        "type": "array",
        "items": _object(field={"type": "string", "enum": list(VALUED)}, fix=_str(), fix_pl=_str()),
    }
)

TRANSLATE = """Translate each short note into Polish: plain, natural Polish, the same facts, \
at most 30 words each, titles and names left as they are. Answer with the translations in the \
order given, one per note."""

TRANSLATE_SCHEMA = _object(notes={"type": "array", "items": _str()})

POLISH = f"""Poprawiasz polski tekst o dziele sztuki w katalogu domowej ramki. Dostajesz obraz, \
to, co katalog wie o dziele, obecny tekst na ramkę ("frame") i obecny pełny tekst ("full") \
oraz uwagę, co w nich jest nie tak.

Popraw tylko to, czego dotyczy uwaga, patrząc na obraz: zdanie z błędem napisz tak, żeby \
zgadzało się z obrazem i danymi, albo je usuń, jeśli nie da się go poprawić bez zgadywania. \
Resztę zostaw słowo w słowo: ten sam styl, te same akapity, nic nowego od siebie. \
"frame": pełne zdania, najwyżej {MAX_BODY} znaków. "full": akapity oddzielone pustą linią."""

POLISH_SCHEMA = _object(frame=_str(), full=_str())

_YEAR = re.compile(r"\b(\d{3,4})\b")


class ReviewError(Exception):
    """What the owner is told, in Polish."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _value(raw: Any) -> str:
    return " ".join(str(raw or "").split()).strip(' "„”')[:VALUE_CHARS]


class ReviewFixes:
    """The remedies of "Do sprawdzenia" (see the module)."""

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        claude: Claude,
        gatekeeper: Gatekeeper,
        audit: Audit,
        crops: Crops,
        pl_text: PlTextJob,
    ) -> None:
        self.library = library
        self.images = images
        self.claude = claude
        self.gatekeeper = gatekeeper
        self.audit = audit
        self.crops = crops
        self.pl_text = pl_text
        self._lock = threading.Lock()
        self._translating = False

    # -- the audit's findings ----------------------------------------------------------

    def finding(self, item_id: str) -> dict[str, Any] | None:
        return next((w for w in self.audit.written() if w.get("id") == item_id), None)

    def _save_finding(self, item_id: str, problems: list[dict[str, Any]]) -> None:
        """The finding with ``problems`` (off the list when none is left)."""
        state = self.audit.state()
        written = state.get("written") or []
        if problems:
            state["written"] = [
                {**w, "problems": problems} if w.get("id") == item_id else w for w in written
            ]
        else:
            state["written"] = [w for w in written if w.get("id") != item_id]
        self.audit._save(state)

    def _work(self, item_id: str) -> Item:
        item = self.library.get(item_id)
        if item is None:
            raise LookupError(item_id)
        return item

    def suggest(self, item_id: str) -> bool:
        """The corrected values of a finding written before the audit gave
        them, asked of Haiku now. Whether any came."""
        item = self._work(item_id)
        found = self.finding(item_id)
        if found is None:
            raise LookupError(item_id)
        problems = [dict(p) for p in found.get("problems") or [] if isinstance(p, dict)]
        wanted = [p for p in problems if p.get("field") in VALUED and not p.get("fix")]
        if not wanted:
            return False
        listed = "\n".join(
            f"{n}. {p['field']}: {p.get('problem', '')}" for n, p in enumerate(wanted, 1)
        )
        text = f"{self.audit.facts(item)}\n\nProblems found:\n{listed}"
        content = [image_block(self.images, item), {"type": "text", "text": text}]
        answer = self.claude.ask(
            self.audit.kind,
            request(
                model=HAIKU,
                system=SUGGEST,
                content=content,
                schema=SUGGEST_SCHEMA,
                max_tokens=3000,
            ),
        )
        if answer.refused or not answer.data:
            return False
        fixes = [f for f in answer.data.get("fixes") or [] if isinstance(f, dict)]
        got = False
        for problem, fix in zip(wanted, fixes, strict=False):
            value = _value(fix.get("fix"))
            if not value:
                continue
            problem["fix"] = value
            if problem.get("field") == "title" and _value(fix.get("fix_pl")):
                problem["fix_pl"] = _value(fix.get("fix_pl"))
            got = True
        if got:
            self._save_finding(item_id, problems)
        return got

    def apply(self, item_id: str, field: str, value: str, value_pl: str | None = None) -> Item:
        """The owner's "Popraw": ``value`` put on the work (and the Polish
        title, for a title); the finding's problem done."""
        if field not in VALUED:
            raise ReviewError("Tego pola nie da się tu poprawić")
        value = _value(value)
        if not value:
            raise ReviewError("Pusta wartość")
        item = self._work(item_id)
        changes: dict[str, Any] = {}
        if field == "title":
            changes["title"] = value
        elif field == "artist":
            changes["artist"] = value
        else:
            changes["date_text"] = value
            year = _YEAR.search(value)
            if year is not None:
                changes["year"] = int(year.group(1))
        updated = self.library.update(item.id, **changes) or item
        if field == "title":
            self._polish_title(updated, _value(value_pl) if value_pl else "")
        log.info("review: the owner mended the %s of %s", field, item_id)
        self.drop(item_id, field)
        return updated

    def _polish_title(self, item: Item, title: str) -> None:
        """The Polish title the app shows, at once: the Polish text is
        written anew from the work's new title later (its facts changed)."""
        note = self.library.note(item.id, self.pl_text.kind)
        if note is None or not title or not isinstance(note.data, dict) or "title" not in note.data:
            return
        self.library.save_note(note.model_copy(update={"data": {**note.data, "title": title}}))
        self.pl_text.forget_title(item.id)

    def cut(self, item_id: str) -> Item:
        """ "Przytnij": Opus finds the work in its photograph now, told what
        the audit saw around it, and the cut is kept as the owner's."""
        item = self._work(item_id)
        if not self.crops.wanted(item):
            raise ReviewError("Tego zdjęcia nie da się przyciąć")
        found = self.finding(item_id) or {}
        hint = " ".join(
            str(p.get("problem") or "")
            for p in found.get("problems") or []
            if isinstance(p, dict) and p.get("field") == "picture"
        )
        updated = self.crops.cut_now(item, hint)
        if updated is None:
            raise ReviewError("Nie znalazłem, co wyciąć. Popraw kadr ręcznie na karcie dzieła.")
        self.drop(item_id, "picture")
        return updated

    # -- the Polish text ------------------------------------------------------------------

    def _polish_note(self, item: Item) -> Any:
        note = self.library.note(item.id, self.pl_text.kind)
        if note is None or not isinstance(note.data, dict) or not note.data.get("full"):
            raise ReviewError("To dzieło nie ma jeszcze polskiego opisu")
        return note

    def propose_polish(self, item_id: str) -> dict[str, str]:
        """ "Popraw opis": the Polish texts mended where the audit's remark
        says (Sonnet, now, about a cent), shown to the owner before they
        are kept (:meth:`save_polish`). Mateusz 2026-11-16, de Chirico's
        self-portrait: "white letters" on a tablet with dark ones."""
        item = self._work(item_id)
        note = self._polish_note(item)
        found = self.finding(item_id) or {}
        remark = " ".join(
            str(p.get("problem") or "")
            for p in found.get("problems") or []
            if isinstance(p, dict) and p.get("field") == "polish"
        )
        text = (
            f"{self.audit.facts(item)}\n\n"
            f"Obecny tekst na ramkę (frame):\n{note.data.get('frame') or ''}\n\n"
            f"Obecny pełny tekst (full):\n{note.data.get('full') or ''}\n\n"
            f"Uwaga: {remark or 'sprawdź, czy tekst zgadza się z obrazem'}"
        )
        answer = self.claude.ask(
            self.pl_text.kind,
            request(
                model=SONNET,
                system=POLISH,
                content=[image_block(self.images, item), {"type": "text", "text": text}],
                schema=POLISH_SCHEMA,
                max_tokens=8000,
            ),
        )
        if answer.refused or not answer.data:
            raise ReviewError("Claude nie poprawił opisu. Spróbuj jeszcze raz.")
        full = _paragraphs(answer.data.get("full"))
        frame = frame_text(_plain(answer.data.get("frame"))) or frame_text(full)
        if not full or not frame:
            raise ReviewError("Claude nie poprawił opisu. Spróbuj jeszcze raz.")
        return {"frame": frame, "full": full}

    def save_polish(self, item_id: str, frame: str, full: str) -> None:
        """The owner's Polish texts kept (as proposed or as he wrote them):
        the frame's text whole sentences that fit, the card's in paragraphs.
        The note keeps what it was written from, so it is not written anew."""
        item = self._work(item_id)
        note = self._polish_note(item)
        full = _paragraphs(full)
        frame = frame_text(_plain(frame)) or frame_text(full)
        if not full or not frame:
            raise ReviewError("Pusty opis")
        data = {**note.data, "frame": frame, "full": full, "by_owner": True}
        fresh = self.pl_text.source_hash(item)
        self.library.save_note(note.model_copy(update={"data": data, "source_hash": fresh}))
        log.info("review: the owner mended the Polish text of %s", item_id)
        self.drop(item_id, "polish")

    def drop(self, item_id: str, field: str) -> None:
        """The finding's ``field`` done (off the list with the last one)."""
        found = self.finding(item_id)
        if found is None:
            return
        problems = [
            p
            for p in found.get("problems") or []
            if isinstance(p, dict) and p.get("field") != field
        ]
        self._save_finding(item_id, problems)

    def hide(self, item_id: str) -> Item:
        """ "Ukryj": the work out of the catalogue (as "Ukryj" on its card),
        and off the list."""
        item = self._work(item_id)
        updated = self.library.set_hidden(OWNER_ID, item.id, True, at=_now()) or item
        self.audit.forget_written(item_id)
        self.gatekeeper.forget_written(item_id)
        return updated

    # -- the gatekeeper's notes in Polish ---------------------------------------------------

    def untranslated(self) -> list[dict[str, Any]]:
        return [w for w in self.gatekeeper.written() if w.get("why") and not w.get("why_pl")]

    def translate_soon(self) -> None:
        """:meth:`translate` in the background, once at a time."""
        if not self.untranslated() or not self.claude.config.api_key:
            return
        with self._lock:
            if self._translating:
                return
            self._translating = True

        def run() -> None:
            try:
                self.translate()
            except Exception as err:  # no key, the limit: asked again next time
                log.info("review: the gatekeeper's notes not translated (%s)", err)
            finally:
                with self._lock:
                    self._translating = False

        threading.Thread(target=run, name="review-translate", daemon=True).start()

    def translate(self) -> int:
        """The gatekeeper's English notes written before it wrote them in
        Polish, translated in one question. How many."""
        waiting = self.untranslated()[:TRANSLATE_AT_ONCE]
        if not waiting:
            return 0
        listed = "\n".join(f"{n}. {w['why']}" for n, w in enumerate(waiting, 1))
        answer = self.claude.ask(
            self.gatekeeper.kind,
            request(
                model=HAIKU,
                system=TRANSLATE,
                content=[{"type": "text", "text": listed}],
                schema=TRANSLATE_SCHEMA,
                max_tokens=6000,
            ),
        )
        if answer.refused or not answer.data:
            return 0
        notes = [_value(n) for n in answer.data.get("notes") or []]
        done = {
            str(w["id"]): note
            for w, note in zip(waiting, notes, strict=False)
            if note and w.get("why")
        }
        if not done:
            return 0
        state = self.gatekeeper.state()
        state["written"] = [
            {**w, "why_pl": done[str(w.get("id"))]} if str(w.get("id")) in done else w
            for w in state.get("written") or []
        ]
        self.gatekeeper._save(state)
        return len(done)
