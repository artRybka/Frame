"""What a work led to ("Co z niego wyrosło"), with pictures and links: each
later work Claude names in a page (the work of the day, a study) is looked
up once, in the museums and on Wikipedia, and what was found is kept.

A museum's copy is taken only when its author is the one named and its
title shares a word with the one named; a Wikipedia article only when it
names the author. Wikipedia's picture is a free one (what its summaries
give), so a work still under copyright gets a link without a picture.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from .ai.jobs import text_hash
from .library import Item
from .library.duplicates import surname
from .library.models import Note
from .library.museums import client
from .library.vocabulary import artist_matches, fold

if TYPE_CHECKING:
    from .ai.daily import Legacy
    from .library import Library

log = logging.getLogger(__name__)

KIND = "later"
VERSION = "later-1"
#: Results asked from each museum for one later work.
MUSEUM_HITS = 4
#: Title words this short say nothing ("the", "of", "la").
WORD_MIN = 4


class LaterLink(BaseModel):
    """What was found for one later work."""

    #: A museum's copy of it (not in the library).
    item: Item | None = None
    #: Its Wikipedia article, and the article's (free) picture.
    wiki_url: str = ""
    wiki_title: str = ""
    picture: str = ""


def entry_key(entry: Legacy) -> str:
    return text_hash(entry.who, entry.title, entry.search)[:12]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", fold(text)) if len(w) >= WORD_MIN and not w.isdigit()}


def same_work(hit: Item, entry: Legacy) -> bool:
    """``hit`` is by the author named and its title shares a word with the
    title named (the original one in ``search`` or the Polish one)."""
    if not hit.artist or not artist_matches(hit.artist, [entry.who]):
        return False
    named = (_words(entry.search) | _words(entry.title)) - _words(entry.who)
    return bool(named & _words(hit.title))


class LaterWorks:
    def __init__(
        self,
        library: Library,
        search: Callable[[str, int], tuple[int, list[Item], list[str]]],
    ) -> None:
        self.library = library
        #: Every museum at once: ``Importer.search_all``.
        self.search = search
        self._http: httpx.Client | None = None
        self._lock = threading.Lock()
        self._looking: set[str] = set()

    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = client()
        return self._http

    def known(self, item_id: str) -> dict[str, LaterLink]:
        """What was found for the later works of ``item_id``'s pages, by
        :func:`entry_key`."""
        note = self.library.note(item_id, KIND)
        if note is None or note.prompt_version != VERSION:
            return {}
        return {k: LaterLink.model_validate(v) for k, v in note.data.items()}

    def missing(self, item_id: str, entries: list[Legacy]) -> list[Legacy]:
        known = self.known(item_id)
        return [e for e in entries if entry_key(e) not in known]

    def looking(self, item_id: str) -> bool:
        return item_id in self._looking

    def look_soon(self, item: Item, entries: list[Legacy]) -> bool:
        """Looks the later works up in the background unless they are known;
        True while they are being looked up."""
        if not self.missing(item.id, entries):
            return False
        with self._lock:
            if item.id in self._looking:
                return True
            self._looking.add(item.id)
        threading.Thread(
            target=self._look_then_done, args=(item, entries), name="later-works", daemon=True
        ).start()
        return True

    def _look_then_done(self, item: Item, entries: list[Legacy]) -> None:
        try:
            self.look(item, entries)
        except Exception:
            log.exception("later works of %s", item.id)
        finally:
            with self._lock:
                self._looking.discard(item.id)

    def look(self, item: Item, entries: list[Legacy]) -> dict[str, LaterLink]:
        """Looks up the later works not known yet and keeps what was found
        (also nothing: not asked again)."""
        known = self.known(item.id)
        for entry in entries:
            key = entry_key(entry)
            if key not in known:
                known[key] = self._find(item, entry)
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model="",
                prompt_version=VERSION,
                data={k: v.model_dump(mode="json") for k, v in known.items()},
            )
        )
        return known

    def _find(self, item: Item, entry: Legacy) -> LaterLink:
        found = LaterLink(item=self._museum(item, entry))
        return found.model_copy(update=self._wikipedia(entry))

    def _museum(self, item: Item, entry: Legacy) -> Item | None:
        if not entry.search:
            return None
        try:
            hits = self.search(entry.search, MUSEUM_HITS)[1]
        except (httpx.HTTPError, ValueError) as err:
            log.info("museums on %r: %s", entry.search, err)
            return None
        return next((h for h in hits if h.id != item.id and same_work(h, entry)), None)

    def _wikipedia(self, entry: Legacy) -> dict[str, Any]:
        """The article about the later work (Polish first), when one names
        its author."""
        name = fold(surname(entry.who) or entry.who)
        asks = [("pl", f"{entry.who} {entry.title}"), ("en", entry.search or entry.title)]
        person: dict[str, Any] = {}
        for lang, query in asks:
            if not query.strip() or not name:
                continue
            for title in self._titles(lang, query):
                summary = self._summary(lang, title)
                text = fold(" ".join(str(summary.get(k) or "") for k in ("title", "extract")))
                page = (summary.get("content_urls") or {}).get("mobile") or {}
                url = str(page.get("page") or "")
                if name not in text or not url:
                    continue
                found = {
                    "wiki_url": url,
                    "wiki_title": str(summary.get("title") or title),
                    "picture": str((summary.get("thumbnail") or {}).get("source") or ""),
                }
                if _words(found["wiki_title"]) <= _words(entry.who):
                    # The author's own article: a link, not their portrait.
                    person = person or {**found, "picture": ""}
                    continue
                return found
        return person

    def _titles(self, lang: str, query: str) -> list[str]:
        try:
            resp = self.http().get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 2,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            hits = (resp.json().get("query") or {}).get("search") or []
        except (httpx.HTTPError, ValueError):
            return []
        return [str(h["title"]) for h in hits if h.get("title")]

    def _summary(self, lang: str, title: str) -> dict[str, Any]:
        try:
            resp = self.http().get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
                + quote(title.replace(" ", "_"), safe="")
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return {}
        return data if isinstance(data, dict) and data.get("type") != "disambiguation" else {}
