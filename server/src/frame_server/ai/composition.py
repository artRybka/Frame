"""The analysis of a work's composition ("Analiza kompozycji"): one take,
drawn in pencil on the picture, with four to six sentences under it.

Asked apart from the rest of the page (Mateusz 2026-11-02), in steps, each
by the cheapest model that does it well (Mateusz 2026-11-04, after two
blind trials; about a third of what one long Opus answer and an Opus check
cost):

1. Opus, with medium thinking and the picture alone (no museum text, no
   Wikipedia: they made it no better), draws the masses and their balance,
   the divisions, the one figure that orders it all, great clear rhythms,
   whether it is open or closed, and names the places it rests on (its
   key points), each mark's points with what they lie on. No grids and no
   movement: those are measured apart.
2. Haiku checks every mark and place against what it was meant to lie on
   (``ai.check``).
3. The server finds the picture's own lines (``ai.lines``) and chooses the
   grid by what lies on them and on the key points (``ai.grid``).
4. Sonnet says whether the composition is still or moving and draws a
   movement that really happens (``ai.motion``).
5. Opus, with little thinking and no picture, writes the text from the
   draft and what the steps found, in one voice (``ai.prose``): the steps
   no longer add sentences of their own (Mateusz 2026-11-07).

Pages written before are written again (:class:`ComposeJob`) in the
background, one by one, for the works the owner lets it (:data:`REWORK_KEY`:
first a few to see, then all); a page left without its composition (the
question failed) gets it the same way, unasked.

The owner may also ask for one work's analysis anew from its page (held
header "Analiza kompozycji" → "Wykonaj ponowną analizę", Mateusz
2026-11-03; :data:`AGAIN_KEY`): every analysis a page has had is kept
(:data:`VERSIONS`) and the owner picks the one it shows.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from typing import TYPE_CHECKING, Any

import anthropic

from ..imaging.text import sentences
from ..library.markup import strip_markup
from ..library.models import Note
from . import grid as grids
from . import lines as found_lines
from . import motion as motions
from . import prose
from .check import CHECK_SIDE, answer_views, checked, page_views
from .check import question as check_question
from .client import OPUS, AiUnavailable, Answer, request
from .daily import (
    AXES,
    CHECK_ROUND,
    CHECKED,
    MAX_KEYS,
    ROUND,
    SHAPES,
    Context,
    Key,
    View,
    _composition,
    _dicts,
    _key,
    _list,
    _object,
    _str,
    _text,
    _view,
    image_block,
    picture,
    sent_size,
    to_fractions,
)
from .daily import (
    KIND as DAILY,
)
from .jobs import NoteJob, Usage, listed, relist, text_hash
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import ImageCache, Item
    from .daily import DailyJob

log = logging.getLogger(__name__)

KIND = "composition"
PROMPT_VERSION = "composition-5"
#: The pages it is written into.
PAGES = (DAILY, STUDY)
#: The works whose pages written before may be written again: ``True`` for
#: all of them, else a list of item ids (set over ``/api/ai/composition``).
REWORK_KEY = "composition_rework"
#: The take a page had before it was written again, kept to go back to.
BEFORE = "composition_before"
#: The works whose analysis the owner asked to be made anew, one at a time
#: on their page ("Wykonaj ponowną analizę"), until it is.
AGAIN_KEY = "composition_again"
#: Every analysis a page has had since the owner first asked for one anew,
#: oldest first (:func:`version`), the one it shows among them.
VERSIONS = "composition_versions"
#: Which of :data:`VERSIONS` the page shows.
SHOWN = "composition_shown"
#: The owner picked the one shown: a rework of all pages leaves it be.
CHOSEN = "composition_chosen"
#: What each step of the last analysis cost (USD), kept in the page.
COST = "composition_cost"
#: How long the list of pages wanting their composition is kept between looks.
PAGES_SECONDS = 30.0
#: All five steps, as if Opus answered them (about 0.14 USD).
TYPICAL = Usage(input_tokens=10500, cache_read_input_tokens=3200, output_tokens=4600)
#: The marks Opus may draw (movement is Sonnet's, ``ai.motion``).
DRAWN = tuple(s for s in SHAPES if s not in ("motion", "underline"))
MAIN = "główny"

SYSTEM = """Piszesz „Analizę kompozycji” jednego dzieła do aplikacji domowej ramki, dla \
miłośnika sztuki, który nie jest historykiem sztuki. Rysujesz ją ołówkiem na obrazie: aplikacja \
nakłada Twoje ślady na obraz, numeruje je i podpisuje, a pod obrazem pokazuje tekst. Naturalna, \
poprawna polszczyzna, jak w dobrym polskim muzeum, bez superlatywów.

Współrzędne podajesz w pikselach obrazu, który dostajesz (wymiary w danych: OBRAZ), od lewego \
górnego rogu: x w prawo, y w dół. Każdy punkt stawiasz na konkretnym, nazwanym miejscu formy \
(czubek głowy, łokieć, róg okna, linia horyzontu przy lewej krawędzi) i to miejsce wpisujesz \
w "na". Punkt, którego nie umiesz tak nazwać, nie powstaje.

JAK PRACUJESZ (krótko, bez rozważania wszystkich możliwości)
1. Spójrz z daleka: duże masy jasne i ciemne, dominanta, gdzie leży ciężar i co go równoważy \
(przeciwwaga: forma, plama lub pusta przestrzeń po drugiej stronie), mocne akcenty koloru, \
które prowadzą wzrok albo wiążą obraz (powtórzona czerwień, jedyna jasna plama).
2. Wybierz JEDEN główny układ, najmocniejszy i widoczny od razu (piramida, odwrócony trójkąt \
lub V, przekątna, X, krzyż, owal, krzywa S, klin, perspektywa zbieżna, układ centralny lub \
symetryczny, pasy, rozproszony). Uznaj go tylko, gdy wyznaczają go co najmniej trzy ważne \
formy albo jedna wielka, ciągła forma.
3. Dodaj najwyżej 2–4 ślady, które naprawdę dzielą pole albo powtarzają się: horyzont lub \
brzeg, rama w ramie, duży rytm (co najmniej trzy podobne formy niosące konstrukcję: kolumny, \
maszty, pnie, postacie; nie sprzęty i przedmioty, nie drobny wzór), otwartość ucięta \
krawędzią, przeciwwaga, akcent koloru.
4. Nie dopasowuj żadnych siatek (złoty podział, trójpodział, połowy) i nie pisz o nich; zrobi \
to osobny krok na podstawie Twoich punktów kluczowych. Nie oceniaj też ruchu ani tego, czy \
kompozycja jest statyczna czy dynamiczna, i nie rysuj ruchu; to też osobny krok. Złota \
spirala tylko po prawdziwych, zwiniętych formach.
5. Wskaż 3–6 punktów kluczowych: miejsca, na których naprawdę opiera się kompozycja \
(dominanta, oko lub twarz głównej postaci, punkt zbiegu, wierzchołek głównego układu, linia \
horyzontu, ważna pionowa krawędź). Każdy dokładnie na formie, z nazwą.
Lepiej mniej i pewnie niż wzór przyłożony na siłę. Portret na gładkim tle: powiedz to wprost \
i pokaż oś postaci, podział tła albo masę.

ODPOWIEDŹ: "composition" z jednym ujęciem w "views" (tekst bez słowa o siatkach i podziałach \
pola):
- "title": „Analiza kompozycji”.
- "text": brudnopis, 4–6 zdań, 450–800 znaków; ostateczny tekst napisze z niego osobny krok. \
Ma zawierać: czy kompozycja jest otwarta czy zamknięta i po czym to widać; co równoważy \
dominantę albo jak działa kolor; co układ robi dla tematu. Konkretnie, bez wstępów i ocen. Bez \
zdania o statyce, dynamice i ruchu. Nic, czego nie widać na obrazie lub w śladach.
- "points": punkty kluczowe z punktu 5, najważniejszy pierwszy. Każdy: "x", "y" (piksele), \
"na" (1–5 słów), "os": "x" gdy liczy się tylko położenie w poziomie (pionowa krawędź, oś \
postaci), "y" gdy tylko wysokość (horyzont, linia stołu), "xy" dla punktu; "waga": "główny" \
(najwyżej dwa) albo "ważny".
- "marks": 3–6 śladów, najpierw główny układ. Każdy: "shape", "points", "title" (1–3 słowa), \
"text" (najwyżej 45 znaków), "na" (lista: dla każdego punktu po kolei nazwa miejsca, na którym \
leży, 1–5 słów).
  "line" 2–12 punktów: horyzont, podział, oś, krawędź, przekątna, boki V lub klina (3 punkty: \
koniec boku, wierzchołek, koniec drugiego), krzywa S przez kolejne formy; może wyjść poza \
obraz do pół boku.
  "triangle" 3 wierzchołki na prawdziwych punktach formy, może wyjść poza obraz.
  "loop" środek i róg prostokąta, w który się wpisuje: wielki owal układu lub dominanta.
  "rect" dwa przeciwległe rogi: rama w ramie, pas, bryła.
  "rhythm" 3–12 par punktów: dół i góra każdej powtarzanej formy wzdłuż jej osi.
  "rays" punkt zbiegu, potem 2–8 dalekich końców po prawdziwych krawędziach; gdy punkt zbiegu \
leży dalej niż pół boku poza obrazem, zamiast tego dwie "line" po zbiegających się krawędziach.
  "arrow" 2–12 punktów: kierunek wychodzący poza obraz, tylko gdy otwartość mocno decyduje o \
wyglądzie; długi, co najmniej jedna piąta boku.
  "spiral" 3 punkty: początek najszerszego łuku, punkt ćwierć obrotu dalej, oko.
  Czytelność: dwa ślady nie biegną po tej samej krawędzi ani tuż obok siebie; jedna rzecz ma \
jeden ślad."""

_POINT = _object(x={"type": "number"}, y={"type": "number"})
_KEY = _object(
    x={"type": "number"},
    y={"type": "number"},
    na=_str(),
    os={"type": "string", "enum": list(AXES)},
    waga={"type": "string", "enum": [MAIN, "ważny"]},
)
_VIEW = _object(
    title=_str(),
    text=_str(),
    points=_list(_KEY),
    marks=_list(
        _object(
            shape={"type": "string", "enum": list(DRAWN)},
            points=_list(_POINT),
            title=_str(),
            text=_str(),
            na=_list(_str()),
        )
    ),
)
SCHEMA = _object(composition=_object(views=_list(_VIEW)))


def request_text(item: Item, context: Context) -> str:
    """The work: its picture's size, what it is and who made it (no
    sources: the analysis looks at the picture alone)."""
    lines = [
        "DZIEŁO",
        f"Muzeum: {item.held_by or item.museum}",
        f"Tytuł (oryginał): {strip_markup(item.title)}",
        f"Autor: {item.artist}",
        f"Data: {item.date_text}",
        f"Technika: {item.medium}",
    ]
    if context.size:
        w, h = context.size
        lines[:0] = [f"OBRAZ: {w} × {h} px (współrzędne w tych pikselach)", ""]
    if context.facts and context.facts.title_pl:
        lines.append(f"Polski tytuł z Wikidata: {context.facts.title_pl}")
    return "\n".join(lines)


def question(images: ImageCache, item: Item, context: Context) -> dict[str, Any]:
    """The analysis of the work's composition: its picture as large as Opus
    reads one (it points to the pixel)."""
    img = picture(images, item)
    text = request_text(item, replace(context, size=img.size))
    params = request(
        model=OPUS,
        system=SYSTEM,
        content=[image_block(img), {"type": "text", "text": text}],
        schema=SCHEMA,
        max_tokens=24000,
        effort="medium",
    )
    params["timeout"] = 600.0
    return params


@dataclass
class Draft:
    """The analysis as Opus drew it: its take (no grid, no movement), the
    places it rests on, and what each mark's points lie on, by its title."""

    view: View
    keys: list[Key]
    na: dict[str, list[str]]


def draft(data: dict[str, Any] | None, params: dict[str, Any]) -> Draft | None:
    """The analysis of an answer (in pixels), or None when it has no take."""
    if not data:
        return None
    size = sent_size(params)
    fractions = to_fractions(data, size)
    views = answer_views(fractions)
    if not views:
        return None
    composition = data.get("composition")
    raw = _dicts(composition.get("views")) if isinstance(composition, dict) else []
    first = raw[0] if raw else {}
    w, h = size if size is not None and fractions is not data else (1, 1)
    keys = []
    for p in _dicts(first.get("points")):
        x, y = p.get("x"), p.get("y")
        if not isinstance(x, int | float) or not isinstance(y, int | float):
            continue
        found = _key(
            {
                "x": x / w,
                "y": y / h,
                "title": p.get("na"),
                "axis": p.get("os"),
                "main": p.get("waga") == MAIN,
            }
        )
        if found is not None:
            keys.append(found)
    na = {
        _text(m.get("title"), 40): [_text(n, 60) for n in m.get("na") or [] if isinstance(n, str)]
        for m in _dicts(first.get("marks"))
    }
    view = views[0].model_copy(update={"grid": "none", "keys": []})
    return Draft(view=view, keys=keys[:MAX_KEYS], na=na)


def take(data: dict[str, Any] | None, params: dict[str, Any]) -> list[View]:
    """The take of an answer (in pixels), as the app shows it: one or none."""
    found = draft(data, params)
    return [found.view] if found else []


def _insert(said: list[str], sentence: str, after: int) -> None:
    """``sentence`` after the ``after``-th of ``said`` (0: at the end)."""
    said.insert(after if 1 <= after <= len(said) else len(said), sentence)


def merged(
    view: View,
    choice: grids.Choice | None,
    movement: motions.Movement | None,
    said: bool = True,
) -> View:
    """The take with the grid and movement steps put in: the grid and the
    places it was chosen by, the movement's marks after the analysis's and,
    when ``said``, its sentence in place of the one that spoke of it (or
    where it said)."""
    out = sentences(view.text)
    if movement is not None and said:
        if 1 <= movement.replaces <= len(out):
            out[movement.replaces - 1] = movement.sentence
        else:
            _insert(out, movement.sentence, movement.where)
    marks = [*view.marks, *(movement.marks if movement else [])]
    update: dict[str, Any] = {"text": " ".join(out), "marks": marks}
    if choice is not None:
        update.update(grid=choice.grid, keys=choice.kept())
    shown = view.model_copy(update=update)
    return _view(shown.model_dump()) or shown


def written(
    images: ImageCache,
    item: Item,
    found: Draft,
    ask: Callable[[dict[str, Any]], Answer],
    analysis_usd: float = 0.0,
    recent: list[str] | None = None,
) -> dict[str, Any]:
    """The analysis checked, its grid chosen and its movement looked at, as
    it goes into a page. Every step that cannot be had (the month's limit,
    an error, an unusable answer) is left out: the analysis is paid for."""
    img = picture(images, item, CHECK_SIDE)
    costs = {"analysis": analysis_usd}
    view, keys, changes = found.view, found.keys, list[str]()

    def asked(step: str, params: dict[str, Any]) -> dict[str, Any] | None:
        answer = ask(params)
        costs[step] = costs.get(step, 0.0) + answer.cost_usd
        return answer.data

    def run(step: str, work: Callable[[], Any]) -> Any:
        try:
            return work()
        except (AiUnavailable, anthropic.APIError) as err:
            log.warning("composition %s of %s skipped: %s", step, item.id, err)
        except Exception:  # the analysis is paid for: never lost to a later step
            log.exception("composition %s of %s failed", step, item.id)
        return None

    looked = run(
        "check",
        lambda: checked(
            view, keys, asked("check", check_question(img, view, keys, found.na)), img.size
        ),
    )
    if looked is not None:
        view, keys, changes = looked.view, looked.keys, looked.changes
    picture_lines = run("lines", lambda: found_lines.find(img))
    choice = grids.choose(keys, picture_lines) if picture_lines is not None else None
    movement = None
    if picture_lines is not None:
        directions = run("directions", lambda: found_lines.directions(img))
        if directions is not None:
            said = sentences(view.text)
            params = motions.question(img, view, said, directions, picture_lines)
            movement = run("motion", lambda: motions.movement(asked("motion", params), img.size))
    # The grid and the movement are facts; the text is written last, in one voice.
    with_grid = merged(view, choice, None)
    facts = prose.grid_facts(choice.grid, choice.held) if choice is not None else []
    text = run(
        "text",
        lambda: prose.prose(
            asked("text", prose.question(item, with_grid, facts, movement, recent or []))
        ),
    )
    # Without it, the draft with the movement's sentence put in.
    shown = (
        merged(with_grid.model_copy(update={"text": text}), None, movement, said=False)
        if text
        else merged(view, choice, movement)
    )
    log.info(
        "composition of %s: %.3f USD (%s), grid %s, %d marks",
        item.id,
        sum(costs.values()),
        ", ".join(f"{k} {v:.3f}" for k, v in costs.items()),
        shown.grid,
        len(shown.marks),
    )
    return {
        "composition": _composition([shown]).model_dump(),
        CHECKED: changes,
        CHECK_ROUND: ROUND,
        COST: {k: round(v, 4) for k, v in costs.items()},
        **({prose.PROSE_KEY: prose.PROSE} if text else {}),
    }


def compose(
    images: ImageCache,
    item: Item,
    context: Context,
    ask: Callable[[dict[str, Any]], Answer],
    recent: list[str] | None = None,
) -> dict[str, Any]:
    """The composition of a page being written: what goes into it (its
    take, what the check changed, the round, what it cost), or nothing when
    the answer is unusable."""
    params = question(images, item, context)
    answer = ask(params)
    found = draft(answer.data, params)
    return written(images, item, found, ask, answer.cost_usd, recent) if found else {}


def failed(note: Note | None) -> bool:
    """An answer that gave no take: kept (so it is not paid for again and
    again), but let be asked once more when the owner lets the work again."""
    return note is not None and any(note.data.get(k) for k in ("unusable", "refused", "failed"))


def version(data: dict[str, Any], made: str, model: str) -> dict[str, Any]:
    """One analysis as a page keeps it among its :data:`VERSIONS`: the take,
    what the check changed, its round, when and by which model."""
    return {
        "composition": data.get("composition") or {"views": []},
        CHECKED: data.get(CHECKED, []),
        CHECK_ROUND: data.get(CHECK_ROUND, 1),
        "made": made,
        "model": model,
    }


def versions(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The analyses a page has had (none before the owner asked anew)."""
    return [v for v in _dicts(data.get(VERSIONS)) if isinstance(v.get("composition"), dict)]


def wants(
    note: Note | None, rework: bool | list[str], again: set[str] | frozenset[str] = frozenset()
) -> bool:
    """A written page whose composition is of an earlier round, when the
    owner lets it be written again; one without any, always; one whose
    analysis the owner asked for anew (``again``), always."""
    if note is None or "teaser" not in note.data:
        return False
    if note.item_id in again:
        return True
    if note.data.get(CHOSEN) and page_views(note.data):
        return False
    if note.data.get(CHECK_ROUND, 1) >= ROUND:
        return False
    if not page_views(note.data):
        return True
    return rework is True or (isinstance(rework, list) and note.item_id in rework)


class ComposeJob(NoteJob):
    """The composition written again, in the background, for pages written
    before (or left without one): once per page and :data:`PROMPT_VERSION`,
    the rest of the page as it was."""

    kind = KIND
    model = OPUS
    prompt_version = PROMPT_VERSION
    typical = TYPICAL

    def __init__(self, page: DailyJob) -> None:
        super().__init__(page.library, page.images, page.config)
        #: The day's page job: what Wikidata says of a work.
        self.page = page
        self._pages: tuple[float, set[str]] = (0.0, set())

    def rework(self) -> bool | list[str]:
        found = self.library.get_state(REWORK_KEY, [])
        return found if found is True or isinstance(found, list) else []

    def let(self, rework: bool | list[str]) -> None:
        """The works whose pages may be written again (``True``: all); an
        answer that gave them no take is forgotten, so it is asked again."""
        self.library.set_state(REWORK_KEY, rework)
        for item_id in self.failed():
            if rework is True or (isinstance(rework, list) and item_id in rework):
                self.library.delete_notes(KIND, item_id)
        self.forget()

    def failed(self) -> set[str]:
        """The works whose analysis (of this prompt) gave no take."""
        return {
            item_id
            for item_id, note in self.library.notes(KIND).items()
            if note.prompt_version == PROMPT_VERSION and failed(note)
        }

    def forget(self) -> None:
        """The pages wanting their composition looked up afresh next time."""
        self._pages = (0.0, set())

    def asked_again(self) -> set[str]:
        """The works whose analysis the owner asked for anew, not made yet."""
        return listed(self.library, AGAIN_KEY)

    def _pages_of(self, item_id: str) -> list[Note]:
        """The work's written pages (its study, its day's page)."""
        found = (self.library.note(item_id, kind) for kind in PAGES)
        return [page for page in found if page is not None and "teaser" in page.data]

    def again(self, item: Item) -> bool:
        """The owner's "Wykonaj ponowną analizę": the work's analysis asked
        anew, the one its pages show kept as their first version. False
        when the work has no written page."""
        pages = self._pages_of(item.id)
        if not pages:
            return False
        old = self.library.note(item.id, KIND)
        for page in pages:
            if VERSIONS in page.data or not page_views(page.data):
                continue
            # The analysis of its own question, when it was asked apart.
            own = old is not None and "composition" in old.data
            made = old.created_at if own and old is not None else page.created_at
            model = old.model if own and old is not None else page.model
            data = {**page.data, VERSIONS: [version(page.data, made, model)], SHOWN: 0}
            self.library.save_note(page.model_copy(update={"data": data}))
        relist(self.library, AGAIN_KEY, item.id, on=True)
        self.library.delete_notes(KIND, item.id)
        self.forget()
        return True

    def pending(self, item_id: str) -> bool:
        """The owner asked for the work's analysis anew and it is on its way
        (not when the answer came back without a take)."""
        return item_id in self.asked_again() and not failed(self.library.note(item_id, KIND))

    def choose(self, item: Item, n: int) -> bool:
        """The owner's pick among the analyses the work's pages have had:
        the one they show from now on. False when there is no such one."""
        chosen = False
        for page in self._pages_of(item.id):
            kept = versions(page.data)
            if not 0 <= n < len(kept):
                continue
            pick = kept[n]
            data = {
                **page.data,
                "composition": pick["composition"],
                CHECKED: pick.get(CHECKED, []),
                CHECK_ROUND: pick.get(CHECK_ROUND, ROUND),
                SHOWN: n,
                CHOSEN: True,
            }
            self.library.save_note(page.model_copy(update={"data": data}))
            chosen = True
        self.forget()
        return chosen

    def waiting(self) -> set[str]:
        """The works with a page wanting its composition (looked up again
        every :data:`PAGES_SECONDS`: the background asks about every item)."""
        when, ids = self._pages
        if time.monotonic() - when > PAGES_SECONDS:
            rework, again = self.rework(), self.asked_again()
            ids = {
                item_id
                for kind in PAGES
                for item_id, note in self.library.notes(kind).items()
                if wants(note, rework, again)
            } - self.failed()
            self._pages = (time.monotonic(), ids)
        return ids

    def wanted(self, item: Item) -> bool:
        return item.id in self.waiting()

    def source_hash(self, item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def params(self, item: Item) -> dict[str, Any]:
        facts = self.page.wikidata.facts(self.page.http, item)
        return question(self.images, item, Context(day=date.today(), facts=facts))

    def revise(
        self, item: Item, params: dict[str, Any], answer: Answer, ask: Callable[..., Answer]
    ) -> Answer:
        found = draft(answer.data, params)
        if found is None:
            # Kept whole, to see why: the next analysis is not free.
            log.warning(
                "composition of %s gave no take: %s", item.id, json.dumps(answer.data)[:2000]
            )
            return replace(answer, data={"unusable": True, "answer": answer.data})
        recent = prose.recent_openings(self.library, but=item.id)
        data = written(self.images, item, found, ask, answer.cost_usd, recent)
        return replace(answer, data=data)

    def apply(self, item: Item, note: Note) -> None:
        """Puts the take in each of the work's pages wanting it, keeping the
        one it had (:data:`BEFORE`; among its :data:`VERSIONS` once the
        owner asked for one anew, the new one shown)."""
        again = self.asked_again()
        if "composition" in note.data:
            rework = self.rework()
            for kind in PAGES:
                page = self.library.note(item.id, kind)
                if page is None or not wants(page, rework, again):
                    continue
                data = {**page.data, **note.data}
                if VERSIONS in page.data or item.id in again:
                    kept = [*versions(page.data), version(note.data, note.created_at, note.model)]
                    data.update({VERSIONS: kept, SHOWN: len(kept) - 1})
                    data.pop(CHOSEN, None)
                else:
                    data.setdefault(BEFORE, page.data.get("composition"))
                self.library.save_note(page.model_copy(update={"data": data}))
        if item.id in again:  # made, or came back without a take: asked no more
            relist(self.library, AGAIN_KEY, item.id, on=False)
        self.forget()
