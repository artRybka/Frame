"""The analysis of a work's composition ("Analiza kompozycji"): one take,
drawn in coloured pencil on a study sheet of the picture (``imaging.sheet``:
its masses as stains, a few strokes of a pen), with four to six sentences
under it.

Asked apart from the rest of the page (Mateusz 2026-11-02), in steps, each
by the cheapest model that does it well (Mateusz 2026-11-04, after two
blind trials; about a third of what one long Opus answer and an Opus check
cost):

1. Opus, with medium thinking and the picture alone (no museum text, no
   Wikipedia: they made it no better), draws the masses and their balance,
   the divisions, the one figure that orders it all, great clear rhythms,
   a colour that returns, whether it is open or closed, and names the
   places it rests on (its key points), each mark's points with what they
   lie on and what the whole mark runs along; and the picture's own field
   on a reproduction that shows more (a print's paper). No grids and no
   movement: those are measured apart. It is told how each mark will be
   drawn (Mateusz 2026-11-11: the instruction "mogłaby być lepsza"; the
   first, tidier one "widzi za mało", so this one goes through a list of
   what a picture may rest on and draws at most five).
2. Haiku checks every mark and place against what it was meant to lie on
   (``ai.check``).
3. The server finds the picture's own lines (``ai.lines``) and chooses the
   grid by what lies on them and on the key points (``ai.grid``).
4. Sonnet says whether the composition is still or moving and draws a
   movement that really happens (``ai.motion``).
5. Sonnet draws the picture in a dozen strokes of a pen (``ai.pen``),
   which go into the sheet under the marks.
6. Opus, with little thinking and no picture, writes the text from the
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

import copy
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from datetime import date
from typing import TYPE_CHECKING, Any

import anthropic

from ..imaging.text import sentences
from ..library.markup import strip_markup
from ..library.models import Note
from . import grid as grids
from . import lines as found_lines
from . import motion as motions
from . import pen, prose
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
    Box,
    Context,
    Key,
    View,
    _composition,
    _dicts,
    _field,
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
    from PIL import Image

    from ..library import ImageCache, Item
    from .daily import DailyJob

log = logging.getLogger(__name__)

KIND = "composition"
PROMPT_VERSION = "composition-6"
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
#: The marks Opus may draw (movement is Sonnet's, ``ai.motion``), and how
#: many of them a sheet the width of a hand holds (Mateusz 2026-11-12, on
#: six trial sheets: six marks crowd it).
DRAWN = tuple(s for s in SHAPES if s not in ("motion", "underline"))
MAX_DRAWN = 5
MAIN = "główny"

SYSTEM = """Rysujesz i opisujesz „Analizę kompozycji” jednego dzieła do aplikacji domowej ramki, \
dla miłośnika sztuki, który nie jest historykiem sztuki. Naturalna, poprawna polszczyzna, jak w \
dobrym polskim muzeum, bez superlatywów.

JAK TO WYGLĄDA U CZYTELNIKA
Aplikacja pokazuje arkusz studyjny: obraz uproszczony do plam akwareli i kilku kresek piórkiem, a \
na nim Twoje ślady narysowane kredką. Każdy ślad dostaje numer, a w legendzie pod arkuszem tytuł \
i jedno krótkie zdanie. Arkusz ogląda się w telefonie, ma szerokość dłoni, więc mieści kilka \
dużych, wyraźnych śladów. Czytelnik najpierw patrzy na rysunek, dopiero potem czyta: ślad ma być \
zrozumiały sam. Pokazujesz to, na czym ten obraz naprawdę stoi, najwyżej pięcioma śladami: \
niczego wyraźnego nie pomijasz z ostrożności i niczego nie dorysowujesz dla ozdoby.

Aplikacja rysuje dokładnie to, co podasz, i łączy punkty najkrótszą drogą:
- "line" z 2 punktów to prosta kreska, z 3 punktów ostry klin (ramię, wierzchołek, ramię), z 4 i \
więcej miękka krzywa przez kolejne punkty;
- "triangle" to trzy proste boki między wierzchołkami;
- "loop" to owal wpisany w ramkę, "rect" to prostokąt tej ramki;
- "rhythm" to jedna prosta kreska przy każdej formie, wszystkie ustawione równolegle;
- "rays" to proste od dalekich końców do punktu zbiegu;
- "echo" to małe kółko w każdym podanym miejscu i cienka przerywana linia, która je wiąże, drugim \
kolorem kredki (czytelnik widzi: te miejsca sobie odpowiadają, to nie jest krawędź ani podział);
- "arrow" to linia z grotem przy ostatnim punkcie;
- "spiral" to złota spirala od początku łuku do oka.
Ciągła kreska znaczy: tu w obrazie coś biegnie (krawędź, oś, szereg rzeczy). Jeżeli "line" łączy \
tylko dwie rzeczy przez puste pole, czytelnik zobaczy podział, którego w obrazie nie ma. Związek \
dwóch odległych miejsc pokazuje "echo", a układ trzech miejsc "triangle".

WSPÓŁRZĘDNE
Piksele obrazu, który dostajesz (wymiary w danych: OBRAZ), od lewego górnego rogu: x w prawo, y w \
dół. Każdy punkt stawiasz na konkretnym, nazwanym miejscu formy (czubek głowy, łokieć, róg okna, \
linia horyzontu przy lewej krawędzi) i to miejsce wpisujesz w "na". Punkt, którego nie umiesz tak \
nazwać, nie powstaje.

JAK PRACUJESZ
1. Pole obrazu. Gdy reprodukcja pokazuje więcej niż sam obraz (margines papieru, podpis pod \
ryciną, passe-partout, rama), wskaż w "pole" ramkę samego obrazu. Wszystko dalej dzieje się w tym \
polu, a „bok” znaczy bok pola.
2. Spójrz z daleka: duże masy jasne i ciemne, dominanta, gdzie leży ciężar i co go równoważy po \
drugiej stronie (forma, plama albo pusta przestrzeń), mocne akcenty koloru.
3. Wybierz JEDEN główny układ, najmocniejszy i widoczny od razu (piramida, odwrócony trójkąt lub \
V, przekątna, X, krzyż, owal, krzywa S, klin, perspektywa zbieżna, układ centralny lub \
symetryczny, pasy, podział jednym pionem lub poziomem, rozproszony). Uznaj go tylko, gdy \
wyznaczają go co najmniej trzy ważne formy albo jedna wielka, ciągła forma lub krawędź. To zawsze \
pierwszy ślad.
4. Przejdź po kolei całą listę i dla każdej pozycji odpowiedz sobie, czy ten obraz ją ma: \
dominanta; przeciwwaga; podział pola (horyzont, brzeg, krawędź ściany, oś); mniejszy trójkąt albo \
klin wewnątrz głównego układu (zgięta ręka, klin jasnej bluzki, snop światła, zbiegające się \
zbocza); rytm rzeczy powtórzonych; kolor, który wraca w innym miejscu; rama w ramie; otwartość. Z \
tych, które obraz ma wyraźnie, rysujesz najwyżej cztery najważniejsze. O pozostałych piszesz w \
tekście.
5. Wskaż 3–6 punktów kluczowych: miejsca, na których naprawdę opiera się kompozycja (dominanta, \
oko lub twarz głównej postaci, punkt zbiegu, wierzchołek głównego układu, linia horyzontu, ważna \
pionowa krawędź). Każdy dokładnie na formie, z nazwą.
6. Zrób kontrolę przed oddaniem (niżej), potem napisz brudnopis tekstu z tego, co narysowałeś.
Nie dopasowuj żadnych siatek (złoty podział, trójpodział, połowy) i nie pisz o nich: zrobi to \
osobny krok na podstawie Twoich punktów kluczowych. Nie oceniaj ruchu ani tego, czy kompozycja \
jest statyczna czy dynamiczna, i nie rysuj ruchu: to też osobny krok.
Nie przykładaj wzoru na siłę. Portret na gładkim tle: powiedz to wprost i pokaż oś postaci, \
podział tła albo masę.

CO CHCESZ POKAZAĆ I JAK TO NARYSOWAĆ
Jedna rzecz ma jeden sposób rysowania.
- Piramida, trójkąt postaci, także mniejszy trójkąt w obrębie jednej postaci (kapelusz, łokieć, \
dłoń): "triangle". Wierzchołki na nazwanych, wyraźnych miejscach. Boki pokazują układ między \
trzema miejscami, więc mogą biec przez postać albo tło.
- Przekątna, oś, horyzont, brzeg, krawędź, podział: "line" z 2 punktów, od miejsca, gdzie ta \
linia w obrazie się zaczyna, do miejsca, gdzie się kończy. Rzecz prosta nie dostaje trzeciego \
punktu. Linia biegnie po formie lub krawędzi albo przez co najmniej trzy rzeczy stojące w \
szeregu.
- V, klin, odwrócony trójkąt (zbiegające się zbocza, klin bluzki między połami płaszcza, zgięta \
ręka): "line" z 3 punktów, ramiona po krawędziach, wierzchołek w miejscu, gdzie się schodzą.
- Łuk, krzywa S, zygzak: "line" z 4–8 punktów, gęsto, na jednej ciągłej formie albo na formach \
stojących jedna za drugą.
- Wielki owal układu, dominanta, przeciwwaga, masa, zwarta grupa postaci: "loop". Ramka dotyka \
rzeczy z czterech stron i nie bierze zapasu ani sąsiednich form: pętla wokół postaci kończy się \
na jej głowie, plecach i stopach, nie na krześle obok. Dominanta zawsze dostaje własny ślad.
- Kolor, który wraca (błękit sukni i błękit drugiej sukni, czerwień kamizelki i czerwień \
krzesła), albo dwie formy, które sobie odpowiadają po dwóch stronach obrazu: "echo", 2–4 punkty, \
każdy w środku jednej plamy, najpierw największa. Tylko duże, od razu widoczne plamy, nie drobne \
ozdoby.
- Rama w ramie (okno, drzwi, przejście), pas, prostokątna bryła: "rect" po jej krawędziach.
- Perspektywa zbieżna: "rays", punkt zbiegu i 2–8 dalekich końców po prawdziwych krawędziach. Gdy \
punkt zbiegu leży dalej niż pół boku poza obrazem, zamiast tego dwie "line" po zbiegających się \
krawędziach.
- Rytm: "rhythm", gdy co najmniej trzy rzeczy tego samego rodzaju powtarzają się w szeregu na co \
najmniej jednej trzeciej boku (kolumny, maszty, pnie, postacie, konie w zaprzęgu, otwory okien i \
bram, łodzie). Dla każdej para punktów wzdłuż jej dłuższej osi; gdy rzecz nie jest wydłużona, od \
jej dołu do góry. Wszystkie pary w tym samym kierunku.
- Otwartość: "arrow" wzdłuż formy uciętej krawędzią, od jej środka przez krawędź, co najmniej \
jedna piąta boku. Tylko gdy otwartość mocno decyduje o wyglądzie obrazu.
- Złota spirala: "spiral", tylko po prawdziwych, zwiniętych formach.

Tego nie rysujesz, tylko o tym piszesz:
- ciągłej linii łączącej dwie rzeczy dlatego, że mają ten sam kolor albo się równoważą (to jest \
"echo" albo "loop" na przeciwwadze);
- pustej przestrzeni: nie obwodzisz jej;
- drogi wzroku od rzeczy do rzeczy.

ZASADY ŚLADU
- Linia, krzywa i ramiona klina leżą na formie w całości, nie tylko punktami. Przejedź w myśli \
palcem po każdym odcinku: jeśli w połowie drogi jest pusto albo leży tam cudza twarz, popraw \
punkty albo zmień kształt. Formę przerwaną (szal schowany za głową) rysujesz do przerwy, nie \
przez nią. Trójkąta i echa to nie dotyczy. W "po" wpisujesz, po czym ślad biegnie albo co \
obejmuje (2–6 słów, np. „krawędź dachu lewego domu”).
- Ślad jest czytelny w telefonie. Krótszy niż jedna dziesiąta dłuższego boku pola powstaje tylko \
jako pętla wokół małej rzeczy, która jest dominantą albo akcentem koloru.
- Ślady się nie dublują i nie tłoczą. Dwa nie biegną po tej samej krawędzi i nie obejmują tej \
samej rzeczy tym samym kształtem. Trzy ślady nie kończą się w jednym punkcie. Dwie pętle nie \
zachodzą na siebie.
- 3–5 śladów w kolejności ważności. Obraz wielofigurowy albo pejzaż z kilkoma planami ma zwykle \
pięć, prosty portret trzy lub cztery. Nie dodawaj ozdobników (drobny sprzęt w rogu, strzałka dla \
samej strzałki).
- Tytuł śladu nazywa rzecz z obrazu („Biały kożuch”, „Krawędź fasady”), nie pojęcie („Dominanta”, \
„Przeciwwaga”). Rolę mówi opis.

KONTROLA PRZED ODDANIEM
Dla każdego śladu po kolei: czy każdy punkt leży na nazwanym miejscu; czy linia i klin biegną po \
formie; czy kształt jest tym z listy dla tej rzeczy; czy pętla obejmuje samą rzecz, bez zapasu; \
czy ślad nie dubluje innego. Ślad, który nie przechodzi, poprawiasz. Potem wróć do listy z kroku \
4: czy dominanta ma swój ślad, czy narysowałeś rytm, powtórzony kolor, mniejszy trójkąt albo \
klin, jeśli obraz je ma i są ważniejsze od tego, co narysowałeś? Na koniec spójrz na sam rysunek: \
czy ktoś, kto nie przeczyta tekstu, zobaczy, jak ten obraz jest zbudowany, i czy ślady nie \
zasłaniają się nawzajem?

ODPOWIEDŹ: "composition" z jednym ujęciem w "views", pola w tej kolejności:
- "title": „Analiza kompozycji”.
- "pole": "left", "top", "right", "bottom" w pikselach. Cały obraz, gdy reprodukcja nie ma \
marginesów.
- "marks": 3–5 śladów, najpierw główny układ. Każdy: "shape", "points", "na" (lista: dla każdego \
punktu po kolei nazwa miejsca, na którym leży, 1–5 słów), "po" (po czym biegnie albo co obejmuje \
cały ślad), "title" (1–3 słowa), "text" (najwyżej 45 znaków).
  "line" 2–8 punktów; wielka linia może wyjść poza obraz do pół boku.
  "triangle" 3 wierzchołki; może wyjść poza obraz.
  "loop" i "rect" 2 punkty: lewy górny i prawy dolny róg ramki wokół rzeczy.
  "rhythm" 3–12 par punktów.
  "echo" 2–4 punkty, każdy w środku plamy lub formy.
  "rays" punkt zbiegu, potem 2–8 dalekich końców.
  "arrow" 2 punkty, grot przy drugim.
  "spiral" 3 punkty: początek najszerszego łuku, punkt ćwierć obrotu dalej, oko.
- "points": punkty kluczowe z kroku 5, najważniejszy pierwszy. Każdy: "x", "y" (piksele), "na" \
(1–5 słów), "os": "x" gdy liczy się tylko położenie w poziomie (pionowa krawędź, oś postaci), "y" \
gdy tylko wysokość (horyzont, linia stołu), "xy" dla punktu; "waga": "główny" (najwyżej dwa) albo \
"ważny".
- "text": brudnopis, 4–6 zdań, 450–800 znaków; ostateczny tekst napisze z niego osobny krok. Ma \
zawierać: czy kompozycja jest otwarta czy zamknięta i po czym to widać; co równoważy dominantę \
albo jak działa kolor; co układ robi dla tematu; to, czego nie narysowałeś, a co warto powiedzieć \
(pusta przestrzeń, powtórzony kolor, ucięte formy). Konkretnie, bez wstępów i ocen. Bez zdania o \
statyce, dynamice i ruchu, bez słowa o siatkach. Nic, czego nie widać na obrazie lub w śladach."""

_POINT = _object(x={"type": "number"}, y={"type": "number"})
_KEY = _object(
    x={"type": "number"},
    y={"type": "number"},
    na=_str(),
    os={"type": "string", "enum": list(AXES)},
    waga={"type": "string", "enum": [MAIN, "ważny"]},
)
_EDGE = {"type": "number"}
_VIEW = _object(
    title=_str(),
    pole=_object(left=_EDGE, top=_EDGE, right=_EDGE, bottom=_EDGE),
    marks=_list(
        _object(
            shape={"type": "string", "enum": list(DRAWN)},
            points=_list(_POINT),
            na=_list(_str()),
            po=_str(),
            title=_str(),
            text=_str(),
        )
    ),
    points=_list(_KEY),
    text=_str(),
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
    """The analysis as Opus drew it, in its picture's field: its take (no
    grid, no movement), the places it rests on, what each mark's points lie
    on and what the whole mark runs along, by its title; the field itself,
    when the reproduction shows more than the picture."""

    view: View
    keys: list[Key]
    na: dict[str, list[str]]
    po: dict[str, str] = dataclass_field(default_factory=dict)
    field: Box | None = None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _boxes(data: dict[str, Any]) -> dict[str, Any]:
    """The answer with each loop, asked for as the box around the thing (its
    two corners: easier to place than a centre and a reach), as the app
    keeps it: its centre and a corner."""
    data = copy.deepcopy(data)
    composition = data.get("composition")
    views = _dicts(composition.get("views")) if isinstance(composition, dict) else []
    for mark in (m for v in views for m in _dicts(v.get("marks")) if m.get("shape") == "loop"):
        corners = [p for p in _dicts(mark.get("points"))[:2]]
        xs = [_number(p.get("x")) for p in corners]
        ys = [_number(p.get("y")) for p in corners]
        if len(corners) == 2 and None not in xs and None not in ys:
            mark["points"] = [
                {"x": (xs[0] + xs[1]) / 2, "y": (ys[0] + ys[1]) / 2},  # type: ignore[operator]
                {"x": max(xs), "y": max(ys)},  # type: ignore[type-var]
            ]
    return data


def _pole(raw: Any, size: tuple[int, int] | None) -> Box | None:
    """The picture's field as the answer gave it (its four edges, in the
    pixels of the picture sent), or None for the whole of it."""
    if not isinstance(raw, dict):
        return None
    edges = [_number(raw.get(k)) for k in ("left", "top", "right", "bottom")]
    if None in edges:
        return None
    left, top, right, bottom = (float(e) for e in edges if e is not None)
    w, h = size if size is not None and max(right, bottom) > 1.5 else (1, 1)
    left, right = sorted((left / w, right / w))
    top, bottom = sorted((top / h, bottom / h))
    return _field({"x": left, "y": top, "w": right - left, "h": bottom - top})


def draft(data: dict[str, Any] | None, params: dict[str, Any]) -> Draft | None:
    """The analysis of an answer (in pixels), or None when it has no take."""
    if not data:
        return None
    size = sent_size(params)
    data = _boxes(data)
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
    po = {_text(m.get("title"), 40): _text(m.get("po"), 80) for m in _dicts(first.get("marks"))}
    field = _pole(first.get("pole"), size)
    marks = views[0].marks[:MAX_DRAWN]
    view = views[0].model_copy(
        update={"grid": "none", "keys": keys[:MAX_KEYS], "marks": marks, "field": field}
    )
    # From here on in the field: what is checked, measured and divided is the picture.
    view = view.inside()
    return Draft(
        view=view.model_copy(update={"keys": []}), keys=view.keys, na=na, po=po, field=field
    )


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
    step: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """The analysis checked, its grid chosen and its movement looked at, as
    it goes into a page. Every step that cannot be had (the month's limit,
    an error, an unusable answer) is left out: the analysis is paid for.
    ``step``: told of each part as it begins (the study's Lock Screen card)."""
    tell = step or (lambda part: None)
    img = picture(images, item, CHECK_SIDE)
    if found.field is not None:
        img = cropped(img, found.field)
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

    tell("composition_check")
    looked = run(
        "check",
        lambda: checked(
            view,
            keys,
            asked("check", check_question(img, view, keys, found.na, found.po)),
            img.size,
        ),
    )
    if looked is not None:
        view, keys, changes = looked.view, looked.keys, looked.changes
    tell("composition_motion")
    picture_lines = run("lines", lambda: found_lines.find(img))
    choice = grids.choose(keys, picture_lines) if picture_lines is not None else None
    movement = None
    if picture_lines is not None:
        directions = run("directions", lambda: found_lines.directions(img))
        if directions is not None:
            said = sentences(view.text)
            params = motions.question(img, view, said, directions, picture_lines)
            movement = run("motion", lambda: motions.movement(asked("motion", params), img.size))
    # The few strokes of the pen under the stains of the sheet: without them
    # the sheet is the stains alone.
    strokes = run("sketch", lambda: pen.strokes(asked("sketch", pen.question(img)), img.size))
    # The grid and the movement are facts; the text is written last, in one voice.
    with_grid = merged(view, choice, None)
    facts = prose.grid_facts(choice.grid, choice.held) if choice is not None else []
    tell("composition_text")
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
    # Back on the whole reproduction, as apps before the sheet draw it.
    shown = shown.model_copy(update={"sketch": strokes or []}).on(found.field)
    shown = _view(shown.model_dump()) or shown
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


def cropped(img: Image.Image, field: Box) -> Image.Image:
    """The picture's field alone."""
    w, h = img.size
    box = (
        round(field.x * w),
        round(field.y * h),
        round((field.x + field.w) * w),
        round((field.y + field.h) * h),
    )
    return img.crop(box)


def compose(
    images: ImageCache,
    item: Item,
    context: Context,
    ask: Callable[[dict[str, Any]], Answer],
    recent: list[str] | None = None,
    step: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """The composition of a page being written: what goes into it (its
    take, what the check changed, the round, what it cost), or nothing when
    the answer is unusable. ``step``: told of each part as it begins
    ("composition", then those of :func:`written`)."""
    if step is not None:
        step("composition")
    params = question(images, item, context)
    answer = ask(params)
    found = draft(answer.data, params)
    return written(images, item, found, ask, answer.cost_usd, recent, step) if found else {}


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
