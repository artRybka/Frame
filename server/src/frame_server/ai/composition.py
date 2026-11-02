"""The analysis of a work's composition ("Analiza kompozycji"): one take,
drawn in pencil on the picture, with four to six sentences under it.

Asked apart from the rest of the page (Mateusz 2026-11-02), with more
thinking, so the model looks only at how the picture is built: the masses
and their balance, the divisions, the one figure that orders it all,
great clear rhythms, whether the composition is open or closed, still or
moving, and what that does for the subject; the grids last, only as a
measure. Then Claude checks its own marks drawn on the picture
(``ai.check``).

Pages written before are written again (:class:`ComposeJob`) in the
background, one by one, for the works the owner lets it (:data:`REWORK_KEY`:
first a few to see, then all); a page left without its composition (the
question failed) gets it the same way, unasked.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import anthropic

from ..library.markup import strip_markup
from ..library.models import Note
from .check import check, page_views
from .client import OPUS, AiUnavailable, Answer, request
from .daily import (
    CHECK_ROUND,
    CHECKED,
    POINTS,
    ROUND,
    VIEW,
    Context,
    View,
    _composition,
    _list,
    _object,
    image_block,
    picture,
    sent_size,
    to_fractions,
)
from .daily import (
    KIND as DAILY,
)
from .jobs import NoteJob, Usage, text_hash
from .pl_text import description
from .study import KIND as STUDY

if TYPE_CHECKING:
    from ..library import ImageCache, Item
    from .daily import DailyJob

log = logging.getLogger(__name__)

KIND = "composition"
PROMPT_VERSION = "composition-1"
#: The pages it is written into.
PAGES = (DAILY, STUDY)
#: The works whose pages written before may be written again: ``True`` for
#: all of them, else a list of item ids (set over ``/api/ai/composition``).
REWORK_KEY = "composition_rework"
#: The take a page had before it was written again, kept to go back to.
BEFORE = "composition_before"
#: How long the list of pages wanting their composition is kept between looks.
PAGES_SECONDS = 30.0
#: The analysis (picture, sources, much thinking), then its check.
TYPICAL = Usage(input_tokens=26000, cache_read_input_tokens=5000, output_tokens=16000)

SYSTEM = (
    """Piszesz „Analizę kompozycji” jednego dzieła do aplikacji domowej ramki: dla \
miłośnika sztuki, który nie jest historykiem sztuki. Analizę rysujesz ołówkiem na obrazie: \
aplikacja nakłada Twoje ślady na obraz, numeruje je i podpisuje, a pod obrazem pokazuje Twój \
tekst. Naturalna, poprawna polszczyzna, jak w dobrym polskim muzeum; bez superlatywów i ozdobników.

"""
    + POINTS
    + """ Kółko ma środek w środku rzeczy, a róg na krawędzi prostokąta, w który się ona \
wpisuje; horyzont leży na horyzoncie; krawędź lub oś idzie po tej krawędzi lub osi; wierzchołki \
trójkąta leżą na prawdziwych punktach formy (czubek głowy, łokieć, skraj szaty), nie obok; \
kreska rytmu idzie po osi powtarzanej formy; promień perspektywy po prawdziwej krawędzi; oko \
spirali leży na rzeczy, w którą spirala się zwija.

JAK PATRZYSZ (w myślach, po kolei, zanim cokolwiek narysujesz)
1. Źródła. Przeczytaj, co opis muzeum i Wikipedia mówią o kompozycji (rozdziały „Composition”, \
„Kompozycja”, „Analysis”). Każde ich twierdzenie sprawdź na obrazie: co się zgadza, pokaż; \
czego obraz nie potwierdza, pomiń.
2. Format. Pionowy, poziomy, kwadratowy, wydłużony; czy układ go podkreśla (pion – \
wertykalizm, szeroki pas – horyzontalizm).
3. Z daleka, przez zmrużone oczy. Duże masy jasne i ciemne, główny motyw (dominanta) i 1–3 \
akcenty. Gdzie leży ciężar obrazu i czym jest zrównoważony: symetria względem osi albo \
równowaga mas (duża masa po jednej stronie, mała przeciwwaga po drugiej, jak na wadze z \
ramieniem).
4. Podziały. Linie, które naprawdę dzielą pole obrazu: horyzont lub linia brzegu (nisko, w \
połowie, wysoko), krawędź stołu, ściany, kolumny, maszt, pień, rama okna lub drzwi (rama w \
ramie), granica jasnej i ciemnej strefy, oś symetrii. Pasy poziome lub pionowe, plany \
(pierwszy, drugi, dalszy), kulisy po bokach, wyraźny prostokąt (okno, otwór, ciemne pole). \
Zmierz, gdzie leżą.
5. Główny układ. Jedna figura, która porządkuje całość: trójkąt lub piramida, odwrócony \
trójkąt lub V, jedna mocna przekątna, X przekątnych, krzyż (pion i poziom), koło lub owal \
(formy ułożone w krąg), krzywa S lub zygzak (droga, rzeka, wygięcie postaci), litera L, układ \
centralny, symetria osiowa, perspektywa zbieżna (krawędzie sufitu, ścian, podłogi, rzędy okien \
lub kolumn, szereg postaci malejących w głąb biegną do jednego punktu zbiegu), układ \
promienisty (linie rozchodzące się z jednego miejsca), klin, układ pasowy, szereg, układ \
rozproszony (all-over). Takie linie zwykle nie są narysowane: wyznacza je kilka form ułożonych \
w jednym kierunku, a oko je dopowiada. Uznaj układ tylko wtedy, gdy wyznaczają go co najmniej \
trzy ważne formy albo jedna wielka, ciągła forma (krawędź, linia brzegu, ciało). Prowadź jego \
linie przez środki i krawędzie tych form, nie obok, i kończ je tam, gdzie kończą się formy.
6. Rytmy. Tylko duże i wyraźne, widoczne z kilku metrów: co najmniej trzy podobne formy \
powtórzone w odstępach na dużej części obrazu (co najmniej jedna trzecia szerokości lub \
wysokości). Najczęściej to rytm pionów: kolumny, pilastry, słupki balustrady, słupki i ramy \
okien, stolarka fasady, maszty i żagle, pnie, stojące postacie; bywa też rytm grup postaci, \
łuków, łodzi czy fal. Nazwij rodzaj: równy, malejący w głąb, naprzemienny (jasne – ciemne), \
falujący. Drobne powtórzenia (szprosy okna, guziki, wzór tkaniny, cegły, liście) pomijasz, \
chyba że wypełniają duży obszar i budują całość. Dwie podobne formy to echo, nie rytm. Formy, \
które tylko przypadkiem stoją obok siebie (kilka drzew, kilka stołków), nie są rytmem: rytm \
widać od razu, nie trzeba go szukać.
7. Otwarta czy zamknięta. Zamknięta: ważne formy mieszczą się w polu, krawędzie ich nie tną, \
układ wraca do środka (kulisy po bokach, łuk, ściana w głębi równoległa do obrazu, rama w \
ramie, piony i poziomy powtarzające krawędzie obrazu); obraz jest skończoną całością. Otwarta: \
krawędzie tną ważne formy (postać, łódź, drzewo, budynek), linie i ruch wychodzą poza obraz, \
przestrzeń trwa dalej, kadr wygląda jak wycinek (japońskie drzeworyty, fotografia, \
impresjoniści). Wiele obrazów łączy obie cechy: powiedz, która przeważa i po czym to widać.
8. Ruch. Statyczna (przewaga pionów i poziomów, symetria, spokój) czy dynamiczna (skosy, łuki, \
linie łamane, asymetria); dośrodkowa (kierunki prowadzą do środka) czy odśrodkowa (ku \
krawędziom).
9. Znaczenie. Co ten układ robi dla tematu (piramida daje postaci stałość; ucięty kadr każe \
myśleć o świecie za krawędzią; rytm łodzi pokazuje siłę fali).
10. Siatki na końcu i tylko jako pomiar. Złoty podział (0,382 i 0,618), trójpodział (1/3 i \
2/3), połowy, 3×2 i 2×3. Ustaw "grid", gdy coś ważnego (horyzont, oś, wierzchołek układu, \
dominanta, przecięcie linii) leży na linii siatki lub na przecięciu dwóch jej linii, i nazwij \
to w tekście: do ok. 2% boku „na linii”, do ok. 5% „blisko linii”, dalej siatka nie pasuje. \
Złoty podział i trójpodział leżą blisko siebie: wybierz ten, którego linia jest bliżej. Złota \
spirala tylko wtedy, gdy jej łuki naprawdę biegną po kilku formach (zwinięta fala, \
ślimacznica, zwinięta grupa postaci), a nie przez puste niebo; obróć ją i skręć w tę stronę, w \
którą biegnie forma. Nie twierdź, że artysta celowo użył złotego podziału, jeśli nie mówią \
tego źródła.

UCZCIWOŚĆ
Jakiś wzór da się przyłożyć do każdego obrazu, więc nazywasz tylko to, co ten obraz naprawdę \
porządkuje. Każdy układ, podział i rytm wynika z konkretnych, nazwanych form. Lepiej mniej i \
pewnie: czego nie widać wyraźnie, nie szukasz na siłę, tylko pomijasz. Gdy obraz nie ma \
wyraźnej figury (portret na gładkim tle, układ rozproszony), powiedz to wprost i pokaż to, co \
go porządkuje (oś postaci, podział tła, masa).

ODPOWIEDŹ: "composition" z jednym ujęciem w "views":
- "title": „Analiza kompozycji”.
- "text": 4–6 zdań o kompozycji, konkretnie, ok. 450–800 znaków. Jedno z nich mówi, czy \
kompozycja jest otwarta czy zamknięta i po czym to widać. Typ kompozycji możesz nazwać na \
początku („Kompozycja zamknięta i statyczna, zbudowana na piramidzie.”), ale nie musisz: \
zacznij od tego, co w tym obrazie najmocniejsze. Pozostałe zdania: główny układ i formy, które \
go wyznaczają; podziały i rytmy (jeśli są); co układ robi dla tematu. Tekst nie twierdzi \
niczego, czego nie widać na obrazie lub w śladach.
- "grid": "golden", "thirds", "halves", "3x2", "2x3" na warunkach z punktu 10, inaczej "none".
- "marks": 3–6 śladów, najpierw główny układ, potem podziały i rytm. Każdy ślad pokazuje jedną \
rzecz z tekstu. Kształty:
  "line" (2–12 punktów): horyzont, podział, oś, krawędź, przekątna, boki otwartego trójkąta lub \
V (3 punkty: koniec boku, wierzchołek, koniec drugiego boku), krzywa S lub zygzak przez \
kolejne formy. Może wychodzić poza obraz do połowy boku.
  "triangle" (3 wierzchołki): zamknięty trójkąt układu, może wychodzić poza obraz.
  "loop" (środek i róg prostokąta, w który się wpisuje): wielki krąg lub owal układu, owal masy, \
łuk sklepienia; wokół pojedynczej rzeczy tylko, gdy jest dominantą albo przeciwwagą.
  "rect" (dwa przeciwległe rogi): rama w ramie (okno, drzwi, łuk, ciemna kulisa wokół jasnego \
środka), bryła lub pas.
  "rhythm" (3–12 par punktów, po kolei): po jednej parze na każdą powtarzaną formę, jej dół i \
góra wzdłuż jej osi (stopa i szczyt kolumny, słupka, masztu, pnia, postaci). Aplikacja rysuje \
przy każdej formie równoległą kreskę, lekko wyprostowaną i wydłużoną, bez linii, która je \
łączy.
  "rays" (punkt zbiegu, potem 2–8 dalekich końców): perspektywa zbieżna. Każdy promień biegnie \
od końca po prawdziwej krawędzi (sufitu, ściany, kobierca, podłogi, rzędu okien, linii głów \
lub stóp szeregu postaci) do punktu zbiegu.
  "motion" (2–12 punktów po torze, grot na końcu): ruch, który dzieje się w obrazie (lot, \
huśtanie, galop, fala, wiatr, taniec); aplikacja rysuje go zamaszystą strzałką ze smugami, \
żeby było widać dynamikę.
  "arrow" (2–12 punktów, grot na końcu): kierunek, który wychodzi poza obraz (kompozycja \
otwarta) albo prowadzi do środka (dośrodkowa). Otwartość lub zamknięcie rysuj tylko wtedy, gdy \
mocno decyduje o wyglądzie obrazu (ucięta wielka forma, wiatr ciągnący za krawędź, rama z \
drzew wokół sceny); inaczej wystarczy zdanie w tekście. Nie rysuj strzałką drogi wzroku od \
rzeczy do rzeczy.
  "spiral" (3 punkty: początek najszerszego łuku, punkt na nim ćwierć obrotu dalej, oko): tylko \
na warunkach z punktu 10; początek może leżeć w dowolnym kierunku od oka, więc spiralę \
obracasz tak, by jej łuki szły po formie.
  Do każdego śladu "title" (1–3 słowa, np. „Piramida”, „Horyzont nisko”, „Rytm masztów”, „Punkt \
zbiegu”, „Lot”, „Ucięta łódź”) i "text" (najwyżej 45 znaków)."""
)

SCHEMA = _object(composition=_object(views=_list(VIEW)))


def request_text(item: Item, context: Context) -> str:
    """The work and what the museum and Wikipedia say of it."""
    lines = [
        "DZIEŁO",
        f"Muzeum: {item.museum}",
        f"Tytuł (oryginał): {strip_markup(item.title)}",
        f"Autor: {item.artist}",
        f"Data: {item.date_text}",
        f"Technika: {item.medium}",
    ]
    if context.size:
        w, h = context.size
        lines[:0] = [f"OBRAZ: {w} × {h} px (współrzędne w tych pikselach)", ""]
    facts = context.facts
    if facts and facts.title_pl:
        lines.append(f"Polski tytuł z Wikidata: {facts.title_pl}")
    if facts and (facts.depicts_pl or facts.depicts_en):
        lines.append(f"Wikidata, co przedstawia: {', '.join(facts.depicts_pl + facts.depicts_en)}")
    if text := description(item):
        lines += ["", "OPIS MUZEUM", text]
    if context.wiki_pl:
        lines += ["", "WIKIPEDIA (pl) O DZIELE", context.wiki_pl]
    if context.wiki_en:
        lines += ["", "WIKIPEDIA (en) O DZIELE", context.wiki_en]
    return "\n".join(lines)


def question(images: ImageCache, item: Item, context: Context) -> dict[str, Any]:
    """The analysis of the work's composition: its picture as large as Opus
    reads one (it points to the pixel) and what the sources say."""
    img = picture(images, item)
    text = request_text(item, replace(context, size=img.size))
    params = request(
        model=OPUS,
        system=SYSTEM,
        content=[image_block(img), {"type": "text", "text": text}],
        schema=SCHEMA,
        max_tokens=32000,
        effort="high",
    )
    params["timeout"] = 900.0  # much thinking: minutes
    return params


def take(data: dict[str, Any] | None, params: dict[str, Any]) -> list[View]:
    """The take of an answer (in pixels), as the app shows it: one or none."""
    if data is None:
        return []
    return page_views(to_fractions(data, sent_size(params)))


def written(
    images: ImageCache, item: Item, views: list[View], ask: Callable[[dict[str, Any]], Answer]
) -> dict[str, Any]:
    """The take checked by Claude over its marks drawn on the picture
    (``ai.check``), as it goes into a page; as it was when the check
    cannot be had."""
    page = {"composition": {"views": [v.model_dump() for v in views]}}
    try:
        page = check(images, item, page, ask)
    except (AiUnavailable, anthropic.APIError) as err:
        log.warning("composition check of %s skipped: %s", item.id, err)
    except Exception:  # the analysis is paid for: never lost to its check
        log.exception("composition check of %s failed", item.id)
    shown = page_views(page)
    return {
        "composition": _composition(shown or views).model_dump(),
        CHECKED: page.get(CHECKED, []),
        CHECK_ROUND: ROUND,
    }


def compose(
    images: ImageCache, item: Item, context: Context, ask: Callable[[dict[str, Any]], Answer]
) -> dict[str, Any]:
    """The composition of a page being written: what goes into it (its
    take, what the check changed, the round), or nothing when the answer
    is unusable."""
    params = question(images, item, context)
    views = take(ask(params).data, params)
    return written(images, item, views, ask) if views else {}


def wants(note: Note | None, rework: bool | list[str]) -> bool:
    """A written page whose composition is of an earlier round, when the
    owner lets it be written again; one without any, always."""
    if note is None or "teaser" not in note.data:
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
        #: The day's page job: what the sources say of a work.
        self.page = page
        self._pages: tuple[float, set[str]] = (0.0, set())

    def rework(self) -> bool | list[str]:
        found = self.library.get_state(REWORK_KEY, [])
        return found if found is True or isinstance(found, list) else []

    def let(self, rework: bool | list[str]) -> None:
        """The works whose pages may be written again (``True``: all)."""
        self.library.set_state(REWORK_KEY, rework)
        self.forget()

    def forget(self) -> None:
        """The pages wanting their composition looked up afresh next time."""
        self._pages = (0.0, set())

    def waiting(self) -> set[str]:
        """The works with a page wanting its composition (looked up again
        every :data:`PAGES_SECONDS`: the background asks about every item)."""
        when, ids = self._pages
        if time.monotonic() - when > PAGES_SECONDS:
            rework = self.rework()
            ids = {
                item_id
                for kind in PAGES
                for item_id, note in self.library.notes(kind).items()
                if wants(note, rework)
            }
            self._pages = (time.monotonic(), ids)
        return ids

    def wanted(self, item: Item) -> bool:
        return item.id in self.waiting()

    def source_hash(self, item: Item) -> str:
        return text_hash(item.title, item.artist, item.date_text)

    def params(self, item: Item) -> dict[str, Any]:
        return question(self.images, item, self.page.sources(item))

    def revise(
        self, item: Item, params: dict[str, Any], answer: Answer, ask: Callable[..., Answer]
    ) -> Answer:
        views = take(answer.data, params)
        if not views:
            return replace(answer, data={"unusable": True})
        return replace(answer, data=written(self.images, item, views, ask))

    def apply(self, item: Item, note: Note) -> None:
        """Puts the take in each of the work's pages wanting it, keeping the
        one it had (:data:`BEFORE`)."""
        if "composition" in note.data:
            rework = self.rework()
            for kind in PAGES:
                page = self.library.note(item.id, kind)
                if page is None or not wants(page, rework):
                    continue
                data = {**page.data, **note.data}
                data.setdefault(BEFORE, page.data.get("composition"))
                self.library.save_note(page.model_copy(update={"data": data}))
        self.forget()
