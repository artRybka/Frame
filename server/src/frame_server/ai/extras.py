"""The artist's line of life and the work's paints for pages written before
the page's question asked for them (Mateusz 2026-11-02: "uzupełnij
wszystkie"): one short question about the sources, no picture (the paints
come from what the sources say, never from how the picture looks), once per
page, in the background.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..library.models import Note
from .client import SONNET, request
from .daily import EXTRAS_PROPS, _object, extras, request_text
from .daily import KIND as DAILY
from .jobs import NoteJob, Usage, text_hash
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import Item
    from .daily import DailyJob

KIND = "study_extras"
PROMPT_VERSION = "extras-1"
#: The pages it is written into.
PAGES = (DAILY, STUDY)
#: How long the list of pages wanting it is kept between looks.
PAGES_SECONDS = 30.0
#: The sources (no picture), a short answer.
TYPICAL = Usage(input_tokens=6000, cache_read_input_tokens=1500, output_tokens=1200)

SYSTEM = """Uzupełniasz stronę o dziele w aplikacji domowej ramki: linię życia autora i farby, \
z których dzieło powstało. Naturalna, poprawna polszczyzna, jak w dobrym polskim muzeum. Fakty \
bierz z podanych źródeł; wiedzę ogólną dopuszczasz tylko wtedy, gdy jesteś jej pewien jak \
encyklopedia. Nie wymyślaj dat ani faktów: jeśli czegoś nie wiesz, pomiń to.

- "born", "died": rok urodzin i rok śmierci autora; 0, gdy nieznany (także dla autora \
anonimowego lub warsztatu) albo autor żyje.
- "milestones": 2–3 ważne chwile z życia autora na jego linii życia, w porządku lat: "year" \
(rok) i "text" (najwyżej 50 znaków, bez kropki, np. „wstępuje do gildii św. Łukasza”, „wyjazd \
do Paryża”). Bez urodzin, śmierci i powstania tego dzieła. Pusta lista, gdy ich nie znasz.
- "pigments": 0–4 farby (pigmenty), z których to dzieło namalowano, TYLKO gdy wymienia je \
opis muzeum, Wikipedia albo pewna wiedza encyklopedyczna o tym konkretnym dziele (badania \
konserwatorskie). Nie zgaduj. Każda: "name" (polska nazwa, np. „ultramaryna naturalna”), \
"hex" (barwa samej farby, np. "#2A4FA0"), "where" (gdzie na obrazie, 2–5 słów), "text" (jedno \
zdanie o tej farbie, najwyżej 140 znaków: skąd się brała, ile kosztowała, co w niej \
szczególnego). Pusta lista, gdy źródła milczą."""

SCHEMA = _object(**EXTRAS_PROPS)


def wants(note: Note | None) -> bool:
    """A written page from before the line of life and the paints."""
    return note is not None and "teaser" in note.data and "milestones" not in note.data


class ExtrasJob(NoteJob):
    kind = KIND
    model = SONNET
    prompt_version = PROMPT_VERSION
    typical = TYPICAL
    system = SYSTEM

    def __init__(self, page: DailyJob) -> None:
        super().__init__(page.library, page.images, page.config)
        #: The day's page job: what the sources say of a work.
        self.page = page
        self._pages: tuple[float, set[str]] = (0.0, set())

    def enabled(self) -> bool:
        """With the pages themselves ("Studium dnia" on)."""
        return self.config.enabled(DAILY)

    def waiting(self) -> set[str]:
        """The works with a page wanting it (looked up again every
        :data:`PAGES_SECONDS`: the background asks about every item)."""
        when, ids = self._pages
        if time.monotonic() - when > PAGES_SECONDS:
            ids = {
                item_id
                for kind in PAGES
                for item_id, note in self.library.notes(kind).items()
                if wants(note)
            }
            self._pages = (time.monotonic(), ids)
        return ids

    def wanted(self, item: Item) -> bool:
        return item.id in self.waiting()

    def source_hash(self, item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def params(self, item: Item) -> dict[str, Any]:
        context = replace(self.page.sources(item), candidates=[])
        text = {"type": "text", "text": request_text(item, context)}
        return request(model=SONNET, system=SYSTEM, content=[text], schema=SCHEMA, max_tokens=4000)

    def apply(self, item: Item, note: Note) -> None:
        """Puts what it found in each of the work's pages wanting it (also
        nothing: an empty line of life is not asked for again)."""
        found = extras(note.data)
        data = {
            "born": found["born"],
            "died": found["died"],
            "milestones": [m.model_dump() for m in found["milestones"]],
            "pigments": [p.model_dump() for p in found["pigments"]],
        }
        for kind in PAGES:
            page = self.library.note(item.id, kind)
            if wants(page) and page is not None:
                self.library.save_note(page.model_copy(update={"data": {**page.data, **data}}))
        self._pages = (0.0, set())
