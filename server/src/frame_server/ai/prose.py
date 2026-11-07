"""The text of "Analiza kompozycji" written in one voice, last.

The analysis is made in steps (``ai.composition``): Opus draws it and
writes a draft, the server measures the grid, Sonnet looks at movement.
Each step used to add its own sentence to the draft ("Budowa jest
spokojna…", a sentence on the thirds after the first one), and the draft
itself filled a list of sentences the prompt named ("Zacznij od tego, co
najmocniejsze", one on open or closed, one on balance…). Half the studies
then opened with "Najmocniej działa tu…" and nearly all had "Kompozycja
jest…" and "Budowa jest…" (Mateusz 2026-11-07: "nie wygląda naturalnie").

So the facts are still found apart, and one writer puts them into one text
at the end: Opus with little thinking, no picture (the facts are in the
draft, the marks and what the server measured), told the openings of the
latest pages so that it does not start like them. In a blind trial of ten
studies it was best in nine (Sonnet in one, Haiku and today's texts in
none). Pages written before get their text rewritten the same way, once
(:class:`ProseJob`), their marks left as they are.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..imaging.text import sentences
from ..library.models import Note
from . import grid as grids
from .check import page_views
from .client import OPUS, request
from .daily import CHECK_ROUND, ROUND, TEXT_CHARS, Key, View, _object, _str, _text
from .daily import KIND as DAILY
from .jobs import NoteJob, Usage, text_hash
from .sketch import CUTS, NEAR_LINE, ON_LINE
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import Item, Library
    from .daily import DailyJob
    from .motion import Movement

KIND = "composition_text"
PROMPT_VERSION = "prose-1"
#: A page's composition text as this writer wrote it (or tried to).
PROSE_KEY = "composition_prose"
PROSE = 1
#: The pages it is written into.
PAGES = (DAILY, STUDY)
#: How many of the latest pages' openings it is told not to repeat.
RECENT = 8
#: Words of each opening.
OPENING_WORDS = 7
#: How long the list of pages wanting it is kept between looks.
PAGES_SECONDS = 30.0
#: The draft and its facts in, a short text out (about 0.015 USD with Opus).
TYPICAL = Usage(input_tokens=1500, cache_read_input_tokens=1200, output_tokens=600)

SYSTEM = """Piszesz ostateczny tekst „Analizy kompozycji” jednego dzieła do aplikacji \
domowej ramki, dla miłośnika sztuki, który nie jest historykiem sztuki. Aplikacja pokazuje \
obraz z narysowanymi śladami (ponumerowanymi, z podpisami), a pod nim Twój tekst.

Dostajesz notatki: brudnopis analizy (pisany kawałkami, więc zdania mogą powtarzać ten sam \
schemat i nie trzymać toku), ślady narysowane na obrazie (kształt | tytuł | opis), punkty \
kluczowe, to, co program zmierzył na siatce, i ocenę ruchu. Z tego robisz jeden spójny tekst \
jednym głosem. Obrazu nie widzisz: wszystko, co wiesz, jest w notatkach.

TREŚĆ
- Zachowaj obserwacje, na których stoją ślady: każdy ślad ma w tekście swoje oparcie.
- Zachowaj: czy kompozycja jest otwarta czy zamknięta i po czym to widać; co równoważy \
dominantę albo jak działa kolor; czy budowa jest spokojna czy dynamiczna (z oceny ruchu); co \
leży na liniach siatki (wiernie: „na linii” tylko to, co program zmierzył na linii, \
„blisko linii” to, co blisko; bez siatki o siatce nie piszesz); co układ robi dla tematu.
- Nie dodawaj niczego, czego nie ma w notatkach. Zdanie, które powtarza inne, możesz pominąć. \
Nie pisz, że artysta świadomie użył siatki.

FORMA
- Zacznij od myśli właściwej temu obrazowi, od konkretu. Możliwe wejścia: droga wzroku, \
napięcie albo kontrast, decyzja malarza (co ucina, gdzie stawia horyzont, skąd patrzymy), \
kadr i format, opowieść, którą układ podaje, pełne i puste, światło. Wybierz to, co w tym \
obrazie naprawdę ciekawe.
- Nie zaczynaj od: „Najmocniej…”, „Najmocniejsz…”, „Kompozycja jest…”, „Budowa jest…”, \
„Obraz…”, „W tym obrazie…”. Nie używaj formuł „Kompozycja jest otwarta/zamknięta:”, „Budowa \
jest spokojna/dynamiczna:”, „Taki układ…”, „Dzięki temu układowi…”. Otwartość i budowę \
powiedz własnymi słowami, przy konkretnej rzeczy (np. „krawędź ucina nogę i stolik, więc \
sypialnia trwa dalej poza kadrem”).
- „Równoważy” najwyżej raz; przeciwwagę możesz też pokazać inaczej (odpowiada, trzyma, \
waży tyle co).
- Kolejność zdań wynika z treści, nie ze schematu. 4–6 zdań, 450–800 znaków; prosty obraz \
może mieć mniej. Zdania różnej długości.
- Ten sam rzeczownik najwyżej dwa razy (nie dotyczy imion postaci).
- Naturalna, poprawna polszczyzna, jak w dobrym polskim muzeum. Bez superlatywów, bez \
ozdobników, bez zwrotów do czytelnika.

ODPOWIEDŹ: {"text": "..."}: sam gotowy tekst."""

SCHEMA = _object(text=_str())

#: Each grid's lines by name: across (upright lines), then down (level ones).
_LINES = {
    "golden": (("lewa pionowa", "prawa pionowa"), ("górna pozioma", "dolna pozioma")),
    "thirds": (("lewa pionowa", "prawa pionowa"), ("górna pozioma", "dolna pozioma")),
    "halves": (("pionowa środkowa",), ("pozioma środkowa",)),
}
_GRID_NAMES = {"golden": "złoty podział", "thirds": "trójpodział", "halves": "połowy (2×2)"}


def _line(grid: str, side: str, cut: float) -> str:
    across, down = CUTS[grid]
    names = _LINES.get(grid)
    cuts, labels = (
        (across, names[0]) if side == "x" and names else (down, names[1] if names else ())
    )
    if labels and cut in cuts and len(labels) == len(cuts):
        return f"{labels[cuts.index(cut)]} linia"
    kind = "pionowa" if side == "x" else "pozioma"
    return f"{kind} linia {cut:.3f}"


def grid_facts(grid: str, held: list[grids.Held]) -> list[str]:
    """What the server measured on the grid, in words: each place on or
    near one of its lines. Nothing without a grid."""
    if grid not in CUTS or grid == "none":
        return []
    found = []
    for h in held:
        for side, d, cut in grids.hits(h.key, grid):
            if d <= NEAR_LINE:
                where = "na linii" if d <= ON_LINE else "blisko linii"
                what = h.edge.name if h.free and h.edge is not None else h.key.title
                found.append(f"- {what}: {where} ({_line(grid, side, cut)})")
    if not found:
        return []
    return [f"Siatka: {_GRID_NAMES.get(grid, grid)}.", *found]


def opening(text: str) -> str:
    """The first words of a text, as it is told not to start."""
    said = sentences(text)
    words = said[0].split() if said else []
    return " ".join(words[:OPENING_WORDS]) + ("…" if len(words) > OPENING_WORDS else "")


def recent_openings(library: Library, but: str = "") -> list[str]:
    """How the latest pages' compositions open (not the work ``but``)."""
    pages = [
        note
        for kind in PAGES
        for item_id, note in library.notes(kind).items()
        if item_id != but and page_views(note.data)
    ]
    pages.sort(key=lambda note: note.created_at, reverse=True)
    found: list[str] = []
    for note in pages:
        said = opening(page_views(note.data)[0].text)
        if said and said not in found:
            found.append(said)
        if len(found) >= RECENT:
            break
    return found


def question(
    item: Item,
    view: View,
    grid: list[str],
    movement: Movement | None = None,
    recent: list[str] | None = None,
) -> dict[str, Any]:
    """The writer's question: the draft, its marks and places, what was
    measured, and how the latest pages open."""
    lines = [
        "DZIEŁO",
        f"{item.artist}, {item.title}, {item.date_text}",
        "",
        "BRUDNOPIS ANALIZY",
        view.text,
        "",
        "ŚLADY NA OBRAZIE (kształt | tytuł | opis)",
        *(f"- {m.shape} | {m.title} | {m.text}" for m in view.marks),
    ]
    places: list[Key] = [k for k in view.keys if not k.title.startswith("linia w obrazie")]
    if places:
        lines += [
            "",
            "PUNKTY KLUCZOWE",
            *(f"- {k.title}{' (główny)' if k.main else ''}" for k in places),
        ]
    lines += ["", "SIATKA (pomiar programu)", *(grid or ["Brak siatki: nic o niej nie pisz."])]
    if movement is not None:
        lines += ["", "RUCH (ocena osobnego kroku)", f"Budowa: {movement.build or '?'}."]
        lines.append(movement.sentence)
    if recent:
        lines += [
            "",
            "Ostatnie studia w aplikacji zaczynały się tak; nie zaczynaj podobnie:",
            *(f"„{r}”" for r in recent),
        ]
    content = [{"type": "text", "text": "\n".join(lines)}]
    return request(model=OPUS, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=4000)


def prose(data: dict[str, Any] | None) -> str | None:
    """The writer's text, or None when it wrote nothing usable."""
    text = _text((data or {}).get("text"), TEXT_CHARS)
    return text if len(text) >= 80 else None


def wants(note: Note | None) -> bool:
    """A written page whose composition text is from before this writer
    (and whose analysis is not about to be made again anyway)."""
    if note is None or "teaser" not in note.data:
        return False
    data = note.data
    if data.get(PROSE_KEY, 0) >= PROSE or not page_views(data):
        return False
    return data.get(CHECK_ROUND, 1) >= ROUND


def rewritten(data: dict[str, Any], text: str | None) -> dict[str, Any]:
    """A page with its shown take's text replaced (the marks stay), also
    among its kept versions; marked done even when nothing usable came."""
    out = {**data, PROSE_KEY: PROSE}
    if text is None:
        return out
    composition = data.get("composition")
    shown_views = page_views(data)
    if shown_views and isinstance(composition, dict) and isinstance(composition.get("views"), list):
        views = [dict(v) if isinstance(v, dict) else v for v in composition["views"]]
        shown = shown_views[0]
        old: str | None = None
        # The shown take by its title, or (a page's "Geometria", shown under
        # the new name) by its text.
        match = [v for v in views if isinstance(v, dict) and v.get("title") == shown.title] or [
            v for v in views if isinstance(v, dict) and v.get("text") == shown.text
        ]
        if match:
            old = match[0].get("text") if isinstance(match[0].get("text"), str) else None
            match[0]["text"] = text
        out["composition"] = {**composition, "views": views}
        versions = data.get("composition_versions")
        if old and isinstance(versions, list):
            out["composition_versions"] = [_swap(v, old, text) for v in versions]
    return out


def _swap(version: Any, old: str, text: str) -> Any:
    """A kept version with its text replaced, when it is the one shown."""
    if not isinstance(version, dict) or not isinstance(version.get("composition"), dict):
        return version
    views = version["composition"].get("views")
    if not isinstance(views, list):
        return version
    swapped = [
        {**v, "text": text} if isinstance(v, dict) and v.get("text") == old else v for v in views
    ]
    return {**version, "composition": {**version["composition"], "views": swapped}}


class ProseJob(NoteJob):
    """The composition text of pages written before, rewritten once in one
    voice (Mateusz 2026-11-07: "Tak, działaj"); the marks stay."""

    kind = KIND
    model = OPUS
    prompt_version = PROMPT_VERSION
    typical = TYPICAL

    def __init__(self, page: DailyJob) -> None:
        super().__init__(page.library, page.images, page.config)
        self.page = page
        self._pages: tuple[float, set[str]] = (0.0, set())

    def enabled(self) -> bool:
        """With the pages themselves ("Studium dnia" on)."""
        return self.config.enabled(DAILY)

    def _page(self, item_id: str) -> Note | None:
        for kind in (STUDY, DAILY):
            page = self.library.note(item_id, kind)
            if wants(page):
                return page
        return None

    def waiting(self) -> set[str]:
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
        page = self._page(item.id)
        shown = page_views(page.data) if page is not None else []
        return text_hash(item.title, item.artist, shown[0].text if shown else "")

    def params(self, item: Item) -> dict[str, Any]:
        page = self._page(item.id)
        if page is None:
            raise LookupError(f"no page of {item.id} wants its text")
        view = page_views(page.data)[0]
        held = [grids.Held(key=k) for k in view.keys]
        recent = recent_openings(self.library, but=item.id)
        return question(item, view, grid_facts(view.grid, held), recent=recent)

    def apply(self, item: Item, note: Note) -> None:
        text = prose(note.data)
        for kind in PAGES:
            page = self.library.note(item.id, kind)
            if wants(page) and page is not None:
                data = rewritten(page.data, text)
                self.library.save_note(page.model_copy(update={"data": data}))
        self._pages = (0.0, set())
