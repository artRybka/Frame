"""Where a work hangs, for works from sources that gather pictures.

A work from a museum's own collection hangs where its source says. A work
from Wikimedia Commons, Openverse, WikiArt or Europeana is a picture
gathered from somewhere: "Wikimedia Commons" is where the picture is from,
not the museum the work is in (Mateusz, 2026-11-02: "muzeum to muzeum, a
źródło zdjęcia to osobny temat"). What can be said without asking anyone
is in ``Item.held_by`` (Europeana's data provider, a sharper copy from the
museum itself, WikiArt's gallery). The rest is looked up here, when the
work's card opens and at night, and kept on the work (``Item.holder``):

1. the library's copy of the same work from a museum's own collection;
2. the collection (P195, else the location P276) of the work on Wikidata,
   found by the ``wikidata`` field of its Commons page, by WikiArt's id, or
   by the Commons file as its picture (P18);
3. the institution named on its Commons page ({{Institution:...}}, by its
   Wikidata item when it has one, for the Polish name).

Names are Polish where Wikidata has them ("Muzeum Narodowe w Warszawie"),
else English.
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
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from .library import Item, ItemKind
from .library.models import COLLECTIONS, Note
from .library.wikidata import Wikidata, record_id

if TYPE_CHECKING:
    from .library import Library

log = logging.getLogger(__name__)

KIND = "holder"
VERSION = "holder-1"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
#: A work whose museum nobody knew is asked about again after this.
AGAIN = timedelta(days=30)
#: A look that failed (the network, a rate limit) is tried again after this.
RETRY = timedelta(minutes=10)
#: Looked up at once.
THREADS = 2
#: Works whose last look is kept in memory (also those not in the library).
REMEMBERED = 4000

Status = Literal["found", "none", "looking", "off"]

#: Statements of a work on Wikidata that name where it is, the best first:
#: the collection, then the location.
WHERE = ("P195", "P276")
#: A qualifier saying the statement is over ("end time"): a former owner.
ENDED = "P582"


def _now() -> datetime:
    return datetime.now(UTC)


# -- Commons pages -------------------------------------------------------------


def _param(wikitext: str, name: str) -> str:
    """The value of the template parameter ``name`` on its own line
    (``| institution = {{Institution:Louvre}}``), "" when there is none."""
    match = re.search(rf"^\s*\|\s*{name}\s*=(.*)$", wikitext, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def work_qid(wikitext: str) -> str:
    """The Wikidata item of the work its Commons page describes
    ({{Artwork |wikidata = Q...}}), "" when the page names none."""
    match = re.fullmatch(r"(Q\d+)\b.*", _param(wikitext, "wikidata"))
    return match.group(1) if match else ""


def institution(wikitext: str) -> tuple[str, str]:
    """The institution a Commons page names: (its Wikidata item, its name).
    ``{{Institution:Muzeum Narodowe w Krakowie}}`` gives ("", that name, the
    page in the Institution namespace); ``{{Institution|wikidata=Q...}}``
    gives (that item, ""); a link or plain text gives ("", the text)."""
    value = _param(wikitext, "institution")
    if not value:
        return "", ""
    if match := re.search(r"\{\{\s*Institution\s*:\s*([^}|]+?)\s*[}|]", value, re.IGNORECASE):
        return "", match.group(1)
    if match := re.search(r"wikidata\s*=\s*(Q\d+)", value, re.IGNORECASE):
        return match.group(1), ""
    if "{{" in value:
        return "", ""  # another template: nothing to name it by
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", value)  # [[w:X|Name]] → Name
    text = re.sub(r"\[\S+\s+([^\]]*)\]", r"\1", text)  # [https://... Name] → Name
    text = re.sub(r"<[^>]+>|'{2,}", "", text).strip(" ,;")
    return "", text if 2 < len(text) <= 120 else ""


def commons_file(item: Item) -> tuple[str, str]:
    """The Commons page of ``item``'s picture: (its page id, its "File:"
    title); ("", "") when the picture is not from Commons."""
    if item.source == "wmc":
        return item.source_id, ""
    parts = urlsplit(item.url)
    if not (parts.hostname or "").endswith("wikimedia.org"):
        return "", ""
    if curid := parse_qs(parts.query).get("curid"):
        return curid[0], ""
    if "/wiki/File:" in parts.path:
        return "", unquote(parts.path.split("/wiki/", 1)[1]).replace("_", " ")
    return "", ""


def _where(entity: dict[str, Any]) -> list[str]:
    """The collections (else locations) a work's Wikidata item names, the
    preferred first, leaving out former ones and deprecated statements."""
    for prop in WHERE:
        found: list[tuple[int, str]] = []
        for claim in (entity.get("claims") or {}).get(prop) or []:
            rank = claim.get("rank")
            if rank == "deprecated" or ENDED in (claim.get("qualifiers") or {}):
                continue
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, dict) and isinstance(value.get("id"), str):
                found.append((0 if rank == "preferred" else 1, value["id"]))
        if found:
            return [qid for _, qid in sorted(found, key=lambda f: f[0])]
    return []


def _name(entity: dict[str, Any]) -> str:
    labels = entity.get("labels") or {}
    for lang in ("pl", "en"):
        if label := str(labels.get(lang, {}).get("value") or ""):
            return label
    return ""


class Holders:
    """Looks up the museums of works from sources that gather pictures."""

    def __init__(self, library: Library, http: Callable[[], httpx.Client]) -> None:
        self.library = library
        self.http = http
        self.clock: Callable[[], datetime] = _now
        self._turns = threading.Semaphore(THREADS)
        self._lock = threading.Lock()
        self._looking: dict[str, Future[str]] = {}
        #: The last look's answer ("" for none), and when, by item id.
        self._known: OrderedDict[str, tuple[str, datetime]] = OrderedDict()

    # -- what is known ---------------------------------------------------------

    @staticmethod
    def applies(item: Item) -> bool:
        """A work whose museum its source does not name."""
        artwork = item.kind == ItemKind.ARTWORK and item.look is None
        return artwork and item.source not in COLLECTIONS

    def known(self, item: Item) -> tuple[Status, str] | None:
        """What is known without looking: ("found", the museum), ("off", "")
        for what needs no look, ("none", "") when nobody knew lately; None
        when it is to be looked up."""
        stored = self.library.get(item.id) or item
        if held := self.fill(stored).held_by:
            return "found", held
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
            name = str(note.data.get("name") or "")
        else:
            name, at = known
        if name:
            return "found", name
        if self.clock() - at < AGAIN:
            return "none", ""
        return None

    def fill(self, item: Item) -> Item:
        """``item`` with the museum looked up for it, when only memory has
        it (a work only looked at, not in the library)."""
        if item.holder or not self.applies(item):
            return item
        with self._lock:
            known = self._known.get(item.id)
        if known is None or not known[0]:
            return item
        return item.model_copy(update={"holder": known[0]})

    def soon(self, item: Item) -> Future[str]:
        """The museum of ``item``, looked up in the background unless it is
        known ("" when nobody knows it); one look for every asker."""
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
            target=self._look_then_done, args=(item, future), name="holder", daemon=True
        ).start()
        return future

    def look(self, item: Item, wait: float) -> tuple[Status, str]:
        """The museum of ``item`` as far as known after ``wait`` seconds."""
        future = self.soon(item)
        try:
            name = future.result(wait)
        except Late:
            return "looking", ""
        if name:
            return "found", name
        known = self.known(item)
        return ("off", "") if known is not None and known[0] == "off" else ("none", "")

    def _look_then_done(self, item: Item, future: Future[str]) -> None:
        name = ""
        try:
            with self._turns:
                name = self.find(item)
            self._remember(item, name)
        except (httpx.HTTPError, ValueError, KeyError) as err:
            log.info("museum of %s: %s", item.id, err)
            with self._lock:  # in memory only: asked again in a few minutes
                self._known[item.id] = ("", self.clock() - AGAIN + RETRY)
        except Exception:
            log.exception("museum of %s", item.id)
        finally:
            with self._lock:
                self._looking.pop(item.id, None)
            future.set_result(name)

    # -- looking -----------------------------------------------------------------

    def find(self, item: Item) -> str:
        """The museum ``item`` is in, "" when nobody says (see the module)."""
        twin = self.library.twin(item)
        if twin is not None and twin.source in COLLECTIONS and twin.museum:
            return twin.museum
        with self.http() as http:
            qid, place_qid, place = "", "", ""
            page_id, title = commons_file(item)
            if page_id or title:
                text, title = self._wikitext(http, page_id, title)
                qid = work_qid(text)
                place_qid, place = institution(text)
            if not qid and (ref := record_id(item)) is not None:
                qid = Wikidata._find(http, *ref) or ""
            if not qid and not place_qid and not place and title:
                qid = self._by_picture(http, title)
            if qid:
                work = Wikidata._entities(http, [qid], "claims").get(qid) or {}
                if (where := _where(work)[:1]) and (name := self._label(http, where[0])):
                    return name
            if place and not place_qid:
                place_qid = self._institution_qid(http, place)
            if place_qid and (name := self._label(http, place_qid)):
                return name
            return place

    @staticmethod
    def _label(http: httpx.Client, qid: str) -> str:
        return _name(Wikidata._entities(http, [qid], "labels").get(qid) or {})

    def _wikitext(self, http: httpx.Client, page_id: str, title: str) -> tuple[str, str]:
        """A Commons page's wikitext and title, by its id or title."""
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
        }
        params["pageids" if page_id else "titles"] = page_id or title
        resp = http.get(COMMONS_API, params=params)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages") or []
        if not pages or "revisions" not in pages[0]:
            return "", title
        page = pages[0]
        text = page["revisions"][0].get("slots", {}).get("main", {}).get("content") or ""
        return str(text), str(page.get("title") or title)

    def _institution_qid(self, http: httpx.Client, name: str) -> str:
        """The Wikidata item of the Commons institution ``name``
        (Institution:<name>), "" when its page names none."""
        text, _ = self._wikitext(http, "", f"Institution:{name}")
        match = re.search(r"wikidata\s*=\s*(Q\d+)", text, re.IGNORECASE)
        return match.group(1) if match else ""

    @staticmethod
    def _by_picture(http: httpx.Client, title: str) -> str:
        """The Wikidata item whose picture (P18) is the Commons file
        ``title``, "" when there is none."""
        name = title.removeprefix("File:")
        resp = http.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": f'haswbstatement:"P18={name}"',
                "srlimit": 1,
                "format": "json",
            },
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search") or []
        return str(hits[0]["title"]) if hits else ""

    # -- keeping it ----------------------------------------------------------------

    def _remember(self, item: Item, name: str) -> None:
        with self._lock:
            self._known[item.id] = (name, self.clock())
            self._known.move_to_end(item.id)
            while len(self._known) > REMEMBERED:
                self._known.popitem(last=False)
        if self.library.get(item.id) is None:
            return  # a work only looked at: remembered in memory only
        if name:
            self.library.update(item.id, holder=name)
            log.info("museum of %s: %s", item.id, name)
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model="",
                prompt_version=VERSION,
                data={"name": name, "at": self.clock().isoformat()},
            )
        )
