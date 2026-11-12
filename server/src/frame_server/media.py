"""How a work is made, for works whose source does not say.

WikiArt's search gives no technique, Commons' pictures come with none, a
good part of Europeana's records and the V&A's search results neither.
The app paints a work's colours in its technique (``PaintCore.swift``) and
takes a work that names none for an oil painting (Mateusz 2026-11-12
12:25), so Wyspiański's pastel "Śpiący Staś" (WikiArt) was painted in oil
(Mateusz 2026-11-12 15:28: „Może jest szansa na uzupełnienie danych o
technice dzieł”). What the work is made with is looked up here, when its
card opens and at night, and kept as the work's ``medium``; only works
whose ``medium`` is empty are looked up, and nothing a museum said is
replaced:

1. the library's copy of the same work from a museum's own collection;
2. the work's own record where the search left it out: WikiArt's work
   (``media``: "pastel, paper"), the V&A's object ("Tempera on panel"),
   Europeana's record (``dctermsMedium``, ``dcFormat``);
3. the Commons page of its picture ({{Artwork |medium = {{Technique|
   pastel|paper}}}});
4. the materials (P186) of the work on Wikidata ("pastel, paper"), found
   by its Commons page, its record's id or its picture.

What is found is in English (the card's Polish texts translate it).
"""

from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as Late
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

import httpx

from .holders import Holders, commons_file, work_qid
from .library import Item, ItemKind
from .library.models import COLLECTIONS, Note
from .library.museums import museum
from .library.wikidata import Wikidata

if TYPE_CHECKING:
    from .library import Library
    from .library.importer import Importer

log = logging.getLogger(__name__)

KIND = "medium"
VERSION = "medium-1"
#: A work nobody named the technique of is asked about again after this.
AGAIN = timedelta(days=30)
#: A look that failed (the network, a rate limit) is tried again after this.
RETRY = timedelta(minutes=10)
#: Looked up at once.
THREADS = 2
#: Works whose last look is kept in memory (also those not in the library).
REMEMBERED = 4000
#: The longest technique kept (a museum's text may run on).
LONGEST = 200

#: Sources whose own record names the technique their search leaves out.
RECORDS = frozenset({"wikiart", "vam", "europeana"})

Status = Literal["found", "none", "looking", "off"]

#: Words that make a Commons template's name a technique ({{Oil on canvas}},
#: {{Pastel}}) or a Wikidata type one ("pastel artwork").
MADE_WITH = re.compile(
    r"\b(oil|tempera|acrylic|canvas|panel|pastel|watercolou?r|gouache|ink|chalk|charcoal|"
    r"pencil|graphite|crayon|fresco|silverpoint|etching|engraving|woodcut|lithograph\w*|"
    r"mezzotint|aquatint|drypoint|linocut|paper|cardboard|parchment|vellum|copper|wood)\b",
    re.IGNORECASE,
)
#: A size, not a technique (Europeana's ``dcFormat`` holds both).
SIZE = re.compile(r"\d\s*(?:cm|mm|in|inch|x|×)\b|^\s*[\d.,\s×x]+$", re.IGNORECASE)
#: "Applies to part" (a frame of gilt wood is not what the picture is in).
APPLIES_TO_PART = "P518"


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,;.")
    return text[:LONGEST]


def _joined(parts: list[str]) -> str:
    """``parts`` once each (ignoring case), joined by commas."""
    seen: dict[str, str] = {}
    for part in parts:
        part = _clean(part)
        if part and part.lower() not in seen:
            seen[part.lower()] = part
    return _clean(", ".join(seen.values()))


# -- Commons pages -------------------------------------------------------------


def _template_args(body: str) -> tuple[list[str], dict[str, str]]:
    """A template's positional and named arguments, empty ones left out."""
    positional: list[str] = []
    named: dict[str, str] = {}
    for part in body.split("|"):
        name, eq, value = part.partition("=")
        if eq and re.fullmatch(r"\s*[\w ]+\s*", name):
            key, value = name.strip().lower(), value.strip()
            if key.isdigit():
                while len(positional) < int(key) - 1:
                    positional.append("")
                positional.insert(int(key) - 1, value)
            elif value:
                named[key] = value
        elif part.strip():
            positional.append(part.strip())
    return [p for p in positional if p], named


def _technique(args: list[str], named: dict[str, str]) -> str:
    """{{Technique|oil|canvas|and=gold}}: "oil and gold on canvas"."""
    if not args:
        return ""
    made = args[0]
    for key in ("and", "and2"):
        if named.get(key):
            made += f" and {named[key]}"
    if named.get("over"):
        made += f" over {named['over']}"
    if len(args) > 1:
        made += f" on {args[1]}"
    if named.get("mounted"):
        made += f" mounted on {named['mounted']}"
    return made


def commons_medium(wikitext: str) -> str:
    """The technique a Commons page's {{Artwork}} names ("pastel on
    paper"), "" when it names none. Its English text when it is given in
    several languages."""
    match = re.search(r"^\s*\|\s*(?:medium|technique)\s*=(.*)$", wikitext, re.M | re.I)
    value = re.sub(r"<!--.*?-->", "", match.group(1) if match else "").strip()
    if not value:
        return ""
    if english := re.search(r"\{\{\s*en\s*\|\s*(?:1\s*=)?([^{}]*)\}\}", value, re.I):
        value = english.group(1)
    found: list[str] = []
    for name, body in re.findall(r"\{\{\s*([^|{}]+?)\s*(?:\|([^{}]*))?\}\}", value):
        args, named = _template_args(body or "")
        if name.lower() in ("technique", "tecnique", "technik"):
            found.append(_technique(args, named))
        elif not args and MADE_WITH.search(name):
            found.append(name.lower())
    plain = re.sub(r"\{\{[^{}]*\}\}", " ", value)
    plain = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", plain)  # [[w:X|Name]] → Name
    plain = re.sub(r"<[^>]+>|'{2,}", " ", plain)
    if re.search(r"[A-Za-z]{3}", plain) and MADE_WITH.search(plain):
        found.append(plain)
    return _joined(found)


# -- Wikidata ------------------------------------------------------------------


def _claimed(entity: dict[str, Any], prop: str) -> list[tuple[str, bool]]:
    """(item, said of a part only) of ``entity``'s statements of ``prop``,
    deprecated ones left out."""
    found: list[tuple[str, bool]] = []
    for claim in (entity.get("claims") or {}).get(prop) or []:
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            found.append((value["id"], APPLIES_TO_PART in (claim.get("qualifiers") or {})))
    return found


def _label(entity: dict[str, Any]) -> str:
    labels = entity.get("labels") or {}
    for lang in ("en", "pl"):
        if label := str(labels.get(lang, {}).get("value") or ""):
            return label
    return ""


def wikidata_medium(http: httpx.Client, entity: dict[str, Any]) -> str:
    """What a work's Wikidata item says it is made with: its materials
    (P186, those of the whole before those of a part: "pastel, paper"),
    else a type that names a technique ("pastel artwork")."""
    materials = _claimed(entity, "P186")
    whole = [qid for qid, part in materials if not part]
    ids = whole or [qid for qid, _ in materials]
    types = [qid for qid, _ in _claimed(entity, "P31")]
    if not ids and not types:
        return ""
    labels = Wikidata._entities(http, list(dict.fromkeys(ids or types))[:20], "labels")
    names = [_label(labels.get(qid) or {}) for qid in ids or types]
    if not ids:
        names = [n for n in names if MADE_WITH.search(n)]
    return _joined(names)


# -- the lookups -----------------------------------------------------------------


class Media:
    """Looks up how works are made when their source does not say."""

    def __init__(self, library: Library, importer: Importer, holders: Holders) -> None:
        self.library = library
        self.importer = importer
        self.holders = holders
        self.http: Callable[[], httpx.Client] = holders.http
        self.clock: Callable[[], datetime] = _now
        self._turns = threading.Semaphore(THREADS)
        self._lock = threading.Lock()
        self._looking: dict[str, Future[str]] = {}
        #: The last look's answer ("" for none), and when, by item id.
        self._known: OrderedDict[str, tuple[str, datetime]] = OrderedDict()

    # -- what is known ---------------------------------------------------------

    @staticmethod
    def applies(item: Item) -> bool:
        """A work that names no technique."""
        artwork = item.kind == ItemKind.ARTWORK and item.look is None
        return artwork and not item.medium.strip()

    def known(self, item: Item) -> tuple[Status, str] | None:
        """What is known without looking: ("found", the technique), ("off",
        "") for what needs no look, ("none", "") when nobody said lately;
        None when it is to be looked up."""
        stored = self.library.get(item.id) or item
        if stored.medium.strip():
            return "found", stored.medium
        if not self.applies(item):
            return "off", ""
        with self._lock:
            known = self._known.get(item.id)
        if known is None:
            note = self.library.note(item.id, KIND)
            if note is None or note.prompt_version != VERSION:
                return None
            try:
                at = datetime.fromisoformat(str(note.data.get("at")))
            except ValueError:
                return None
            known = (str(note.data.get("medium") or ""), at)
        text, at = known
        if text:
            return "found", text
        if self.clock() - at < AGAIN:
            return "none", ""
        return None

    def fill(self, item: Item) -> Item:
        """``item`` with the technique looked up for it, when only memory
        has it (a work only looked at, not in the library)."""
        if item.medium.strip() or not self.applies(item):
            return item
        with self._lock:
            known = self._known.get(item.id)
        if known is None or not known[0]:
            return item
        return item.model_copy(update={"medium": known[0]})

    def soon(self, item: Item) -> Future[str]:
        """The technique of ``item``, looked up in the background unless it
        is known ("" when nobody says); one look for every asker."""
        known = self.known(item)
        if known is not None:
            done: Future[str] = Future()
            done.set_result(known[1])
            return done
        with self._lock:
            running = self._looking.get(item.id)
            if running is not None:
                return running
            future: Future[str] = Future()
            self._looking[item.id] = future
        threading.Thread(
            target=self._look_then_done, args=(item, future), name="medium", daemon=True
        ).start()
        return future

    def look(self, item: Item, wait: float) -> tuple[Status, str]:
        """The technique of ``item`` as far as known after ``wait`` seconds."""
        future = self.soon(item)
        try:
            text = future.result(wait)
        except Late:
            return "looking", ""
        if text:
            return "found", text
        known = self.known(item)
        return ("off", "") if known is not None and known[0] == "off" else ("none", "")

    def _look_then_done(self, item: Item, future: Future[str]) -> None:
        text = ""
        try:
            with self._turns:
                text, origin = self.find(item)
            self._remember(item, text, origin)
        except (httpx.HTTPError, ValueError, KeyError) as err:
            log.info("technique of %s: %s", item.id, err)
            with self._lock:  # in memory only: asked again in a few minutes
                self._known[item.id] = ("", self.clock() - AGAIN + RETRY)
        except Exception:
            log.exception("technique of %s", item.id)
        finally:
            with self._lock:
                self._looking.pop(item.id, None)
            future.set_result(text)

    # -- looking -----------------------------------------------------------------

    def _copy_says(self, item: Item) -> str:
        """The technique a museum's own copy of the same work names."""
        works = self.library.works()
        index = works.group_of(item)
        if index is None:
            return ""
        copies = [c for c in works.groups[index] if c.id != item.id and c.medium.strip()]
        museums = [c for c in copies if c.source in COLLECTIONS]
        return _clean((museums or copies)[0].medium) if museums or copies else ""

    def _record_says(self, item: Item, http: httpx.Client) -> str:
        """The technique the work's own record names (:data:`RECORDS`)."""
        if item.source not in RECORDS or item.source not in self.importer.sources():
            return ""
        return _clean(museum(item.source, http, self.importer.access()).medium(item.source_id))

    def find(self, item: Item) -> tuple[str, str]:
        """How ``item`` is made and who said so ("" and "" when nobody
        does; see the module)."""
        if said := self._copy_says(item):
            return said, "copy"
        unread: httpx.HTTPError | None = None
        with self.http() as http:
            try:
                if said := self._record_says(item, http):
                    return said, item.source
            except httpx.HTTPError as err:
                # WikiArt's questions run out within the hour: Commons and
                # Wikidata may still know; if not, asked again later.
                unread = err
            qid = ""
            page_id, title = commons_file(item)
            if page_id or title:
                text, title = self.holders._wikitext(http, page_id, title)
                if said := commons_medium(text):
                    return said, "commons"
                qid = work_qid(text)
                if not qid and title:
                    qid = Holders._by_picture(http, title)
        qid = qid or self.holders.work_qid(item)
        if qid:
            with self.http() as http:
                work = Wikidata._entities(http, [qid], "claims").get(qid) or {}
                if said := wikidata_medium(http, work):
                    return said, "wikidata"
        if unread is not None:
            raise unread
        return "", ""

    # -- keeping it ----------------------------------------------------------------

    def _remember(self, item: Item, text: str, origin: str) -> None:
        with self._lock:
            self._known[item.id] = (text, self.clock())
            self._known.move_to_end(item.id)
            while len(self._known) > REMEMBERED:
                self._known.popitem(last=False)
        stored = self.library.get(item.id)
        if stored is None:
            return  # a work only looked at: remembered in memory only
        if text and not stored.medium.strip():
            self.library.update(item.id, medium=text)
            log.info("technique of %s: %s (%s)", item.id, text, origin)
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model="",
                prompt_version=VERSION,
                data={"medium": text, "from": origin, "at": self.clock().isoformat()},
            )
        )
