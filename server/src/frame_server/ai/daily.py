"""Discover's work of the day, written up by Claude: why today, the context,
an analysis of the composition as pencil marks on the picture, its colour,
fragments worth a close look, how it fares on the frame, which of the
catalogue's works are like it and what it led to later.

One question a day (Opus sees a picture far better than the others), from
the picture itself and what the museum, Wikidata and Wikipedia say. The
server picks the work (``frame_server.daily``) and the works like it; the
model only says why each one is like it, so it never names a work the
catalogue does not have.
"""

from __future__ import annotations

import base64
import copy
import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
from PIL import Image
from pydantic import BaseModel, Field

from ..imaging.layout import load_image
from ..imaging.text import sentences
from ..library.markup import strip_markup
from ..library.models import Note
from ..library.museums import client
from ..library.wikidata import Facts, Wikidata, wikipedia_intro, wikipedia_text
from .client import OPUS, AiUnavailable, Answer, request
from .jobs import NoteJob, Usage, text_hash
from .pl_text import description
from .sketch import grid_fits

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "daily"
#: Changed whenever the prompt changes, so the text is written again.
PROMPT_VERSION = "daily-10"
#: The tile's two lines under the title (characters).
TEASER_CHARS = 100
#: The picture goes out this big: as large as Opus reads one, so that it
#: points at things to the pixel.
IMAGE_SIDE = 2576
#: Wikipedia articles about the work, and the artist's opening paragraph.
WORK_CHARS = 9000
ARTIST_CHARS = 1500
#: "Geometria" and "Geometria detali" (Mateusz 2026-10-31 dropped "Rytm",
#: the model hunted for small repetitions, and then "Spojrzenie").
MAX_VIEWS = 2
#: Article sections worth keeping when Wikipedia is cut: what it says of
#: the composition.
COMPOSITION_SECTIONS = ("compos", "kompozyc", "analy", "analiz", "descript", "opis")
#: Kept in a page whose composition Claude checked over its own marks drawn
#: on the picture (``ai.check``): what the check changed.
CHECKED = "composition_checked"
#: Which round of the check a page's takes went through: pages checked by
#: an earlier one are checked once more (round 2: the great lines of
#: "Geometria"; round 3: the golden spiral, more grids, no "Spojrzenie";
#: both asked for by Mateusz 2026-10-31).
CHECK_ROUND = "composition_round"
ROUND = 3
MAX_MARKS = 6
MAX_LINE_POINTS = 12
#: Points closer than this (fraction of the picture) are one.
SAME_SPOT = 0.012
#: A triangle smaller than this (fraction of the picture) is a line.
MIN_TRIANGLE = 0.0015
#: A loop's half-width and half-height at least (fraction of the side).
MIN_LOOP = 0.015
#: A two-point line this near level (or upright) is drawn level (upright),
#: and its ends this near opposite corners run exactly corner to corner.
STRAIGHTEN = 0.012
SNAP_CORNER = 0.04
#: The marks drawn over the picture, and how many points each takes
#: (lines and arrows: 2 up to ``MAX_LINE_POINTS``). Older pages may hold
#: "rhythm" marks too; their take is no longer shown.
SHAPES = {
    "arrow": 2, "line": 2, "loop": 2, "triangle": 3, "rect": 2, "underline": 2, "spiral": 3,
}  # fmt: skip
#: The shapes that run through several points.
PATHS = ("arrow", "line")
#: The shapes of the picture's great lines, which may run on past its
#: edges (a big triangle's apex up in the sky, its feet beyond the frame):
#: their points may lie this far outside it (fraction of the side).
REACHING = ("line", "triangle", "spiral")
REACH = 0.5
#: The grids the app draws under a view: none, the golden section, thirds
#: (3×3), halves (2×2), thirds across and halves down (3×2) and the other
#: way round (2×3).
GRIDS = ("none", "golden", "thirds", "halves", "3x2", "2x3")
MAX_SIMILAR = 6
#: Fragments worth a close look ("Detale"), and their sides (fractions).
MAX_DETAILS = 3
DETAIL_MIN = 0.04
DETAIL_MAX = 0.6
MAX_LEGACY = 5
SOURCES = ("obraz", "dane muzeum", "Wikidata", "Wikipedia", "wiedza ogólna")
#: Picture, sources and an answer with thinking, then the check of the
#: composition over the marks drawn on the picture (``ai.check``).
TYPICAL = Usage(input_tokens=19000, cache_read_input_tokens=2500, output_tokens=9000)

MONTHS = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
    "września", "października", "listopada", "grudnia",
)  # fmt: skip

#: Where the model puts its points: pixels of the picture it gets (it
#: points far better in pixels than in fractions); the server divides them.
POINTS = """Współrzędne podajesz w pikselach \
obrazu, który dostajesz (jego wymiary są w danych: OBRAZ), od lewego górnego rogu: x w prawo, \
y w dół. Celuj dokładnie: kółko ma środek w środku rzeczy, a róg na krawędzi prostokąta, \
w który się ona wpisuje; horyzont leży na horyzoncie; krawędź lub oś idzie po tej krawędzi \
lub osi; wierzchołki trójkąta leżą na prawdziwych punktach formy (czubek głowy, łokieć, skraj \
szaty), nie obok; przekątna obrazu biegnie od rogu do rogu; oko spirali leży na rzeczy, \
w którą spirala się zwija. Linie, trójkąty i spirale mogą wychodzić poza obraz (opis niżej)."""

#: How the composition is looked at, as Mateusz asked (2026-10-31, with
#: patterns: a central division, converging perspective, diagonals, golden
#: triangles, the golden spiral on "The Great Wave", golden circles): what
#: the sources say first, then the masses, then each pattern laid over the
#: picture and kept only where it holds; the whole picture's skeleton
#: first (the model used to ring single things), smaller things apart.
COMPOSITION = """- "composition": analiza kompozycji \
jako ujęcia ("views"), każde rysowane osobno ołówkiem na obrazie: „Geometria” (układ całego \
obrazu) i „Geometria detali” (układy w mniejszych rzeczach), i żadnych innych (o świetle \
piszesz w "colour"). Pracuj jak historyk sztuki, po kolei:
  1. Przeczytaj, co źródła mówią o kompozycji dzieła (Wikipedia często ma rozdział \
„Composition” lub „Kompozycja”). Układ, który opisują, sprawdź na obrazie; jeśli się \
zgadza, pokaż go śladami.
  2. Zmruż oczy: gdzie leżą duże masy jasne i ciemne, główny motyw i 2–4 ważne punkty \
(twarz, szczyt, najjaśniejsza plama, punkt zbiegu, przecięcie ważnych krawędzi).
  3. Przyłóż do obrazu po kolei wzory i zostaw tylko te, które naprawdę pasują:
  * siatki: złoty podział (linie w 0,382 i 0,618 boku), trójpodział 3×3 (1/3 i 2/3), podział \
centralny 2×2 (połowy), 3×2 (pionowe linie w 1/3 i 2/3 szerokości, pozioma w połowie \
wysokości) i 2×3 (pionowa w połowie szerokości, poziome w 1/3 i 2/3 wysokości). Siatka \
pasuje, gdy główny motyw, horyzont, oś, wierzchołek albo przecięcie linii leży na jej linii \
lub na przecięciu dwóch jej linii (mocny punkt), do około 5% boku;
  * złota spirala (Fibonacciego): jej promień maleje 1,618 raza co ćwierć obrotu, jak łuki \
w kolejnych kwadratach złotego prostokąta. Oko spirali leży zwykle na głównym motywie, często \
na przecięciu linii złotego podziału, a łuki prowadzą przez inne ważne formy (grzbiet fali, \
ramię, łuk drogi, krawędź chmury). Może być obrócona i większa niż obraz. Pokaż ją tylko, \
gdy łuki naprawdę biegną po formach;
  * przekątne: obie przekątne obrazu (z rogu do rogu, razem jako X), złote trójkąty (jedna \
przekątna i linie do niej prostopadłe z dwóch pozostałych rogów; ich przecięcia z przekątną to \
mocne punkty), przekątne przechodzące przez kilka form (ukośne, nie z rogu do rogu), \
perspektywa zbieżna (linie zbiegające się w punkcie zbiegu);
  * figury: wielki trójkąt lub piramida (wierzchołek w najwyższym ważnym punkcie, boki przez \
ramiona, szaty, zbocza aż do dolnej krawędzi albo za nią), V i odwrócone V, koło i owal \
(formy ułożone w krąg, sklepienie, łuk fali, złote koła wpisane w kwadraty złotego \
prostokąta), krzywa S, oś pionowa i równowaga mas.
  Takie linie zwykle nie są narysowane: wyznacza je kilka rzeczy ułożonych w jednym kierunku, \
a oko je dopowiada. Prowadź je przez środki i krawędzie tych rzeczy, nie obok.
  4. Wybierz najmocniejsze: jakiś wzór da się przyłożyć do każdego obrazu, więc nazwij tylko \
te, które porządkują ten obraz. Najciekawsze jest, gdy figura krzyżuje się z siatką: oko \
spirali, wierzchołek trójkąta, środek koła albo przecięcie przekątnych trafia w linię lub \
mocny punkt siatki. Ustaw wtedy "grid" i nazwij to w tekście („Oko spirali na przecięciu \
złotych linii”, „Wierzchołek piramidy na górnej linii trójpodziału”). Do ok. 2% boku od \
linii pisz „na linii”, dalej „blisko linii”. Złoty podział i trójpodział leżą blisko \
siebie, więc wybierz siatkę, której linia jest bliżej; gdy żadna nie pasuje, "grid" to \
"none". Nie przypisuj artyście świadomego użycia złotego podziału, jeśli źródła tego nie \
mówią.
  „Geometria”: 2–5 śladów układu całego obrazu, najpierw najmocniejszy. Linie, trójkąty \
i spirale mogą wychodzić poza obraz (do połowy szerokości lub wysokości za krawędzią, także \
ujemne); aplikacja przytnie rysunek do obrazu. Otwarty trójkąt lub V rysuj jako "line" \
z 3 punktami (koniec boku, wierzchołek, koniec drugiego boku), X jako dwie linie, złote \
trójkąty jako przekątną i dwie prostopadłe. Bez kółek wokół pojedynczych rzeczy, chyba że \
rzecz leży w mocnym punkcie siatki albo kółko jest wielkim kręgiem układu.
  „Geometria detali”: te same wzory w mniejszych częściach obrazu (grupa postaci, martwa \
natura, twarz z dłońmi, budynek, łódź, drzewo): trójkąt grupy, owal głowy i ramion, oś \
postaci, przekątna wiosła, koło talerza, mała spirala liścia lub fali, podział okna. 2–4 \
ślady, każdy na innej rzeczy nazwanej w podpisie, z wierzchołkami i liniami na prawdziwych \
krawędziach i osiach tej rzeczy; także gdy taki detal powtarza lub odwraca wielki układ. \
Pomiń to ujęcie, gdy w detalach nie ma wyraźnej geometrii.
  """

SYSTEM = (
    """Piszesz „Dzieło dnia” do aplikacji domowej ramki z kolorowym e-papierem: \
krótkie, mądre omówienie jednego dzieła dla miłośnika sztuki, który nie jest historykiem sztuki.

Zasady:
- Naturalna, poprawna polszczyzna, jak w dobrym polskim muzeum. Bez superlatywów, bez \
ozdobników i bez zwrotów do czytelnika. Nazwy japońskie i chińskie w polskiej transkrypcji \
(Fudżi, Hiroszige). Ustalone polskie tytuły dzieł, gdy istnieją.
- Fakty bierz z podanych źródeł i z obrazu. Wiedzę ogólną dopuszczasz tylko wtedy, gdy jesteś \
jej pewien jak encyklopedia (np. słynne nawiązania do bardzo znanego dzieła). Nie wymyślaj dat, \
cytatów, nazwisk ani okoliczności. Jeśli czegoś nie wiesz, pomiń to.
- """
    + POINTS
    + """
- "title": polski tytuł dzieła.
- "teaser": JEDNO zdanie, najwyżej 90 znaków ze spacjami (musi się zmieścić w dwóch wierszach \
kafelka, nie będzie skracane), które zachęci do przeczytania reszty. Bez daty i nazwiska autora \
(aplikacja je pokazuje).
- "focus": najważniejsze miejsce obrazu (twarz głównej postaci albo główny motyw), punkt \
w pikselach. Aplikacja kadruje wokół niego niski, szeroki pasek miniatury.
- "why_today": jedno zdanie, dlaczego to dzieło pasuje do podanej daty: rocznica urodzin lub \
śmierci autora albo powstania dzieła (tylko gdy wynika z dat w źródłach i wypada dziś lub w \
tym tygodniu), pora roku, święto. Pusty, gdy nie ma prawdziwego powodu.
- "headline": tytuł tekstu o okolicznościach (2–6 słów, bez kropki), konkretny dla tego \
dzieła, np. „Pocztówka z pielgrzymki do Fudżi”. Nie „Kontekst”, nie tytuł dzieła.
- "context": dwa krótkie akapity (po 300–550 znaków): kiedy i w jakich okolicznościach dzieło \
powstało, co było w nim nowe, jak je przyjęto.
- "artist": krótka notka o autorze, dwa-trzy zdania (najwyżej 400 znaków): kim był, czym się \
wyróżniał i w którym miejscu jego drogi powstało to dzieło. Bez powtarzania tekstu powyżej.
"""
    + COMPOSITION
    + """
  Każde ujęcie: "title" (1–3 słowa), "grid" ("golden", "thirds", "halves", "3x2" lub \
"2x3" tylko na warunkach powyżej, aplikacja narysuje siatkę; inaczej "none"), "text" \
(dwa-trzy zdania, co to ujęcie pokazuje) i "marks". Ślad: "shape" i "points" w pikselach: \
"line" (2–12 punktów: przekątna, oś, horyzont, krawędź, boki otwartego trójkąta, linia \
perspektywy), "triangle" (3 wierzchołki), "loop" (koło lub owal: środek i jeden róg \
prostokąta, w który się wpisuje), "spiral" (złota spirala, 3 punkty: początek najszerszego \
łuku, punkt na tym łuku mniej więcej ćwierć obrotu dalej, który wyznacza kierunek skrętu, \
i oko spirali; serwer i aplikacja narysują z nich dokładną złotą spiralę), "rect" (dwa \
przeciwległe rogi: rama w ramie, złoty prostokąt). Do każdego "title" (1–3 słowa, podpis \
przy śladzie) i "text" (najwyżej 45 znaków, dopisek pod podpisem). Serwer narysuje ślady na \
obrazie i sprawdzi, czy trafiają.
- "colour": dwa-trzy zdania o kolorze i świetle.
- "details": 2–3 fragmenty warte powiększenia, których w całym obrazie na telefonie nie \
widać: twarz, dłoń, przedmiot, napis lub sygnatura, faktura farby, drobny motyw w tle. \
Aplikacja wytnie je z oryginału w pełnej rozdzielczości. Każdy: "title" (1–3 słowa), "text" \
(jedno-dwa zdania, najwyżej 220 znaków: co tu widać i dlaczego warto się przyjrzeć), "x" i \
"y" (lewy górny róg kadru) oraz "w" i "h" (szerokość i wysokość kadru), wszystko w pikselach \
obrazu. Kadr ciasno wokół rzeczy: bok 10–35% szerokości obrazu, \
proporcje w pikselach od 3:4 do 4:3. Fragmenty różne od siebie i od tego, co pokazuje \
kompozycja.
- "on_frame": jedno-dwa zdania, jak dzieło wypadnie na ramce. Ramka ma sześć tuszy: czarny, \
biały, czerwony, żółty, niebieski, zielony; pozostałe barwy, beże i pastele składa z \
drobnego rastra tych tuszy. Ocena serwera (0–1) jest w danych.
- "similar": z listy KANDYDACI wybierz 3–6 dzieł naprawdę podobnych i do każdego podaj krótką \
etykietę, dlaczego (najwyżej 40 znaków, np. "ta sama seria", "ten sam motyw fali"). Używaj \
tylko identyfikatorów z listy.
- "legacy": 0–5 późniejszych dzieł, artystów lub zjawisk, które wprost czerpały z tego dzieła, \
od najwcześniejszego. Rok, kto, tytuł po polsku, jedno-dwa zdania i, jeśli źródło go podaje, \
krótki cytat. "search": nazwisko i oryginalny tytuł do wyszukania w katalogu. Pusta lista, gdy \
źródła o tym milczą, a dzieło nie jest na tyle słynne, żebyś był pewien.
- "sources": źródła, z których faktycznie skorzystałeś."""
)


def _str(description: str = "") -> dict[str, Any]:
    return {"type": "string", "description": description} if description else {"type": "string"}


def _object(**props: Any) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def _list(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


_POINT = _object(x={"type": "number"}, y={"type": "number"})

SCHEMA = _object(
    title=_str(),
    teaser=_str(),
    focus=_POINT,
    why_today=_str(),
    headline=_str(),
    context=_list(_str()),
    artist=_str(),
    composition=_object(
        views=_list(
            _object(
                title=_str(),
                grid={"type": "string", "enum": list(GRIDS)},
                text=_str(),
                marks=_list(
                    _object(
                        shape={"type": "string", "enum": list(SHAPES)},
                        points=_list(_POINT),
                        title=_str(),
                        text=_str(),
                    )
                ),
            )
        ),
    ),
    colour=_str(),
    details=_list(
        _object(
            title=_str(),
            text=_str(),
            x={"type": "number"},
            y={"type": "number"},
            w={"type": "number"},
            h={"type": "number"},
        )
    ),
    on_frame=_str(),
    similar=_list(_object(id=_str(), why=_str())),
    legacy=_list(
        _object(year=_str(), who=_str(), title=_str(), text=_str(), quote=_str(), search=_str())
    ),
    sources=_list({"type": "string", "enum": list(SOURCES)}),
)


class Spot(BaseModel):
    """A place on the picture: fractions of its width and height."""

    x: float
    y: float


class Point(Spot):
    title: str
    text: str


class Line(BaseModel):
    label: str = ""
    points: list[Spot]


class Mark(BaseModel):
    """A pencil mark on the picture, with its label around it."""

    shape: str
    points: list[Spot]
    title: str
    text: str = ""

    def anchor(self) -> Spot:
        """Where a remark about the mark points: its middle."""
        if self.shape == "loop" or len(self.points) == 1:
            return self.points[0]
        if self.shape == "rect":
            a, b = self.points
            return Spot(x=(a.x + b.x) / 2, y=(a.y + b.y) / 2)
        if self.shape == "triangle":
            return Spot(x=sum(p.x for p in self.points) / 3, y=sum(p.y for p in self.points) / 3)
        if self.shape == "spiral":  # its eye
            return self.points[-1]
        return self.points[len(self.points) // 2]


class View(BaseModel):
    """One take on the composition: its marks over the picture, a grid under
    them and a few sentences."""

    title: str
    grid: str = "none"
    text: str = ""
    marks: list[Mark] = Field(default_factory=list)


class Composition(BaseModel):
    views: list[View] = Field(default_factory=list)
    #: The first take as numbered points and lines, for 0.42 apps.
    points: list[Point] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)


class Detail(BaseModel):
    """A fragment worth a close look: a box on the picture (fractions of its
    width and height, from the top left), cut from the original."""

    title: str
    text: str = ""
    x: float
    y: float
    w: float
    h: float


class Similar(BaseModel):
    id: str
    why: str


class Legacy(BaseModel):
    year: str
    who: str
    title: str
    text: str
    quote: str = ""
    search: str = ""


class Essay(BaseModel):
    """What the model wrote about the work of the day, cleaned."""

    title: str = ""
    teaser: str
    #: Where the tile's band is cropped around.
    focus: Spot | None = None
    why_today: str = ""
    #: The title of the text (instead of "Kontekst").
    headline: str = ""
    context: list[str] = Field(default_factory=list)
    #: A short note about the artist.
    artist: str = ""
    composition: Composition = Field(default_factory=Composition)
    colour: str = ""
    #: Fragments worth a close look ("Detale").
    details: list[Detail] = Field(default_factory=list)
    on_frame: str = ""
    similar: list[Similar] = Field(default_factory=list)
    legacy: list[Legacy] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class Context:
    """What the question tells the model besides the work and its picture."""

    day: date
    facts: Facts | None = None
    wiki_pl: str = ""
    wiki_en: str = ""
    artist_wiki: str = ""
    candidates: list[Item] = field(default_factory=list)
    #: The picture's size as sent, in pixels.
    size: tuple[int, int] | None = None


def polish_date(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def request_text(item: Item, context: Context) -> str:
    author = item.artist
    if item.artist_bio:
        author = f"{author} ({item.artist_bio})" if author else item.artist_bio
    lines = [
        f"Dziś jest {polish_date(context.day)}.",
        "",
        "DZIEŁO",
        f"Muzeum: {item.museum}",
        f"Tytuł (oryginał): {strip_markup(item.title)}",
        f"Autor: {author}",
        f"Data: {item.date_text}",
        f"Technika: {item.medium}",
    ]
    if context.size:
        lines.insert(
            2, f"OBRAZ: {context.size[0]} × {context.size[1]} px (współrzędne w tych pikselach)"
        )
        lines.insert(3, "")
    if item.classification:
        lines.append(f"Rodzaj: {item.classification}")
    if item.culture:
        lines.append(f"Kultura: {item.culture}")
    if tags := [*item.styles, *item.subjects]:
        lines.append(f"Tagi muzeum: {', '.join(tags)}")
    if item.colors:
        palette = ", ".join(f"{c.hex} ({c.weight:.0%})" for c in item.colors[:6])
        lines.append(f"Kolory (analiza serwera): {palette}")
    if item.suitability is not None:
        lines.append(f"Ocena na e-papier (serwer, 0–1): {item.suitability:.2f}")
    facts = context.facts
    if facts and facts.title_pl:
        lines.append(f"Polski tytuł z Wikidata: {facts.title_pl}")
    if facts and (facts.depicts_pl or facts.depicts_en):
        lines.append(f"Wikidata, co przedstawia: {', '.join(facts.depicts_pl + facts.depicts_en)}")
    if text := description(item):
        lines += ["", "OPIS MUZEUM", text]
    if context.artist_wiki:
        lines += ["", "WIKIPEDIA O AUTORZE (wstęp)", context.artist_wiki]
    if context.wiki_pl:
        lines += ["", "WIKIPEDIA (pl) O DZIELE", context.wiki_pl]
    if context.wiki_en:
        lines += ["", "WIKIPEDIA (en) O DZIELE", context.wiki_en]
    if context.candidates:
        lines += ["", "KANDYDACI (podobne dzieła z katalogu: id | autor | tytuł | data)"]
        lines += [
            f"{c.id} | {c.artist} | {strip_markup(c.title)} | {c.date_text}"
            for c in context.candidates
        ]
    return "\n".join(lines)


def _text(value: Any, limit: int = 2000) -> str:
    text = " ".join(strip_markup(str(value or "")).split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:–-") + "…"
    return text


def short(text: str, limit: int) -> str:
    """``text`` as it fits the tile: its first sentence when the whole is too
    long, cut at a word only when that is too long as well."""
    if len(text) <= limit:
        return text
    found = sentences(text)
    first = found[0] if found else text
    if len(first) <= limit:
        return first
    return first[:limit].rsplit(" ", 1)[0].rstrip(" ,;:–-") + "…"


def _unit(value: Any, reach: float = 0.0) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN is not a place
        return None
    return min(1.0 + reach, max(-reach, number))


def _spot(raw: Any, reach: float = 0.0) -> Spot | None:
    """A point on the picture, or up to ``reach`` beyond its edges."""
    if not isinstance(raw, dict):
        return None
    x, y = _unit(raw.get("x"), reach), _unit(raw.get("y"), reach)
    return None if x is None or y is None else Spot(x=x, y=y)


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _distinct(spots: list[Spot]) -> list[Spot]:
    """The points without one landing on the one before it."""
    kept: list[Spot] = []
    for s in spots:
        if not kept or max(abs(s.x - kept[-1].x), abs(s.y - kept[-1].y)) > SAME_SPOT:
            kept.append(s)
    return kept


def _straight(spots: list[Spot]) -> list[Spot]:
    """A two-point line as it is meant: a diagonal from corner to corner,
    a level horizon, an upright axis."""
    if len(spots) != 2:
        return spots
    a, b = spots
    corners = [(round(a.x), round(a.y)), (round(b.x), round(b.y))]
    opposite = corners[0][0] != corners[1][0] and corners[0][1] != corners[1][1]
    near = all(
        abs(s.x - cx) <= SNAP_CORNER and abs(s.y - cy) <= SNAP_CORNER
        for s, (cx, cy) in zip(spots, corners, strict=True)
    )
    if opposite and near:
        return [Spot(x=cx, y=cy) for cx, cy in corners]
    if abs(a.y - b.y) <= STRAIGHTEN:
        y = (a.y + b.y) / 2
        return [Spot(x=a.x, y=y), Spot(x=b.x, y=y)]
    if abs(a.x - b.x) <= STRAIGHTEN:
        x = (a.x + b.x) / 2
        return [Spot(x=x, y=a.y), Spot(x=x, y=b.y)]
    return spots


def _loop_corner(centre: Spot, corner: Spot) -> Spot:
    """A loop's corner far enough from its centre to go around something."""

    def side(c: float, k: float) -> float:
        if abs(k - c) >= MIN_LOOP:
            return k
        return c + MIN_LOOP if c + MIN_LOOP <= 1 else c - MIN_LOOP

    return Spot(x=side(centre.x, corner.x), y=side(centre.y, corner.y))


def _area(a: Spot, b: Spot, c: Spot) -> float:
    return abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2


def _too_near(a: Spot, b: Spot) -> bool:
    return max(abs(a.x - b.x), abs(a.y - b.y)) < MIN_LOOP * 2


def _mark(raw: dict[str, Any]) -> Mark | None:
    """A mark that can be drawn and means something: a triangle that is not
    a line, a loop around something; a nearly level line drawn level, a
    diagonal from corner to corner. The picture's great lines may run on
    past its edges. Old pages' rhythms are no longer drawn."""
    shape, title = str(raw.get("shape") or ""), _text(raw.get("title"), 40)
    reach = REACH if shape in REACHING else 0.0
    spots = [s for s in (_spot(p, reach) for p in raw.get("points") or []) if s is not None]
    if shape in PATHS:
        spots = _distinct(spots)
    if shape not in SHAPES or not title or len(spots) < SHAPES[shape]:
        return None
    keep = MAX_LINE_POINTS if shape in PATHS else SHAPES[shape]
    spots = spots[:keep]
    if shape == "triangle" and _area(*spots) < MIN_TRIANGLE:
        return None
    if shape == "rect" and (
        abs(spots[0].x - spots[1].x) < SAME_SPOT or abs(spots[0].y - spots[1].y) < SAME_SPOT
    ):
        return None
    if shape == "spiral" and _too_near(spots[0], spots[2]):
        return None
    if shape == "loop":
        spots = [spots[0], _loop_corner(*spots)]
    if shape == "line":
        spots = _straight(spots)
    return Mark(shape=shape, points=spots, title=title, text=_text(raw.get("text"), 80))


def _view(raw: dict[str, Any]) -> View | None:
    marks = [m for m in map(_mark, _dicts(raw.get("marks"))) if m is not None][:MAX_MARKS]
    title = _text(raw.get("title"), 40)
    if not marks or not title:
        return None
    grid = raw.get("grid") if raw.get("grid") in GRIDS else "none"
    view = View(title=title, grid=str(grid), text=_text(raw.get("text"), 600), marks=marks)
    # A grid drawn under a take that nothing in it lies on proves nothing.
    return view if grid_fits(view) else view.model_copy(update={"grid": "none"})


def _detail(raw: dict[str, Any]) -> Detail | None:
    """A fragment's box kept on the picture and neither a speck nor the
    whole of it."""
    title = _text(raw.get("title"), 40)
    x, y, w, h = (_unit(raw.get(k)) for k in ("x", "y", "w", "h"))
    if not title or x is None or y is None or w is None or h is None:
        return None
    w, h = min(max(w, DETAIL_MIN), DETAIL_MAX), min(max(h, DETAIL_MIN), DETAIL_MAX)
    x, y = min(x, 1 - w), min(y, 1 - h)
    return Detail(title=title, text=_text(raw.get("text"), 300), x=x, y=y, w=w, h=h)


def _in_detail(view: View) -> bool:
    return "detal" in view.title.casefold()


def _geometry(view: View) -> bool:
    return view.title.casefold().startswith("geometr") and not _in_detail(view)


def takes(views: list[View]) -> list[View]:
    """The takes the app shows: "Geometria", then "Geometria detali" when
    there is one. Pages written before had "Spojrzenie" and a third take
    ("Rytm", or one "if it made sense", e.g. "Światło"): left out."""
    kept: list[View] = []
    for view in views:
        marks = [m for m in view.marks if m.shape in SHAPES]
        if marks:
            kept.append(view if marks == view.marks else view.model_copy(update={"marks": marks}))
    found = (
        next((v for v in kept if _geometry(v)), None),
        next((v for v in kept if _in_detail(v)), None),
    )
    return [v for v in found if v is not None]


def _composition(views: list[View]) -> Composition:
    """The takes, and the first one as 0.42 apps draw it: a numbered point
    per mark and its lines and arrows."""
    if not views:
        return Composition()
    first = views[0].marks
    points = [
        Point(x=_unit(a.x) or 0.0, y=_unit(a.y) or 0.0, title=m.title, text=m.text)
        for m in first
        for a in [m.anchor()]
    ]
    lines = [Line(label=m.title, points=m.points) for m in first if m.shape in ("arrow", "line")]
    return Composition(views=views, points=points, lines=lines)


def clean(data: dict[str, Any], candidates: list[str]) -> Essay | None:
    """A model's answer made safe to show; ``None`` when it is unusable."""
    teaser = short(_text(data.get("teaser"), 400), TEASER_CHARS)
    if not teaser:
        return None
    found = data.get("composition")
    raw: dict[str, Any] = found if isinstance(found, dict) else {}
    views = takes([v for v in map(_view, _dicts(raw.get("views"))) if v is not None])
    allowed, similar = set(candidates), list[Similar]()
    for s in _dicts(data.get("similar")):
        item_id = str(s.get("id") or "")
        if item_id in allowed and all(item_id != x.id for x in similar):
            similar.append(Similar(id=item_id, why=_text(s.get("why"), 50)))
    legacy = [
        Legacy(
            year=_text(e.get("year"), 20),
            who=_text(e.get("who"), 80),
            title=_text(e.get("title"), 120),
            text=_text(e.get("text"), 400),
            quote=_text(e.get("quote"), 300).strip("„”\"'"),
            search=_text(e.get("search"), 120),
        )
        for e in _dicts(data.get("legacy"))[:MAX_LEGACY]
        if _text(e.get("who")) and _text(e.get("text"))
    ]
    context = [_text(p, 900) for p in data.get("context") or [] if _text(p)][:3]
    return Essay(
        title=_text(data.get("title"), 120),
        teaser=teaser,
        focus=_spot(data.get("focus")),
        why_today=_text(data.get("why_today"), 220),
        headline=_text(data.get("headline"), 80).rstrip("."),
        context=context,
        artist=_text(data.get("artist"), 600),
        composition=_composition(views),
        colour=_text(data.get("colour"), 500),
        details=[d for d in map(_detail, _dicts(data.get("details"))) if d is not None][
            :MAX_DETAILS
        ],
        on_frame=_text(data.get("on_frame"), 400),
        similar=similar[:MAX_SIMILAR],
        legacy=legacy,
        sources=[s for s in data.get("sources") or [] if s in SOURCES],
    )


def picture(images: ImageCache, item: Item, side: int = IMAGE_SIDE) -> Image.Image:
    """The work's picture at most ``side`` pixels long: the original when it
    can be had, else the thumbnail."""
    path, _ = images.picture(item)
    img = load_image(path.read_bytes()).convert("RGB")
    img.thumbnail((side, side), Image.Resampling.LANCZOS)
    return img


def image_block(img: Image.Image) -> dict[str, Any]:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    data = base64.standard_b64encode(out.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def sent_size(params: dict[str, Any]) -> tuple[int, int] | None:
    """The size of the first picture a question sends, in pixels."""
    for block in params["messages"][0]["content"]:
        if block.get("type") == "image":
            raw = base64.standard_b64decode(block["source"]["data"])
            with Image.open(io.BytesIO(raw)) as img:
                return img.size
    return None


def _numbers(data: dict[str, Any]) -> list[float]:
    """Every coordinate of an answer: the focus, the marks, the details."""
    found: list[float] = []
    for spot in [data.get("focus"), *_spots(data)]:
        if isinstance(spot, dict):
            found += [v for k in ("x", "y") if isinstance(v := spot.get(k), int | float)]
    for d in _dicts(data.get("details")):
        found += [v for k in ("x", "y", "w", "h") if isinstance(v := d.get(k), int | float)]
    return found


def _spots(data: dict[str, Any]) -> list[Any]:
    composition = data.get("composition")
    views = _dicts(composition.get("views")) if isinstance(composition, dict) else []
    views += _dicts(data.get("views"))  # a check's answer
    return [p for v in views for m in _dicts(v.get("marks")) for p in m.get("points") or []]


def _scale(raw: dict[str, Any], keys: tuple[str, ...], size: tuple[int, int]) -> None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, int | float):
            raw[key] = value / (size[0] if key in ("x", "w") else size[1])


def to_fractions(data: dict[str, Any], size: tuple[int, int] | None) -> dict[str, Any]:
    """The answer with its pixels made fractions of the picture's sides (as
    the app and :func:`clean` take them). An answer already in fractions
    (all of it within the picture's unit square) is left as it is."""
    numbers = _numbers(data)
    if size is None or not numbers or max(numbers) <= 1.5:
        return data
    data = copy.deepcopy(data)
    if isinstance(data.get("focus"), dict):
        _scale(data["focus"], ("x", "y"), size)
    for spot in _spots(data):
        if isinstance(spot, dict):
            _scale(spot, ("x", "y"), size)
    for d in _dicts(data.get("details")):
        _scale(d, ("x", "y", "w", "h"), size)
    return data


class DailyJob(NoteJob):
    kind = KIND
    model = OPUS
    prompt_version = PROMPT_VERSION
    typical = TYPICAL
    system = SYSTEM

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        config: AiConfigStore,
        wikidata: Wikidata | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        super().__init__(library, images, config)
        self.wikidata = wikidata or Wikidata()
        self._http = http
        #: The day each picked work is the work of; set by ``frame_server.daily``.
        self.day_of: Callable[[str], date | None] = lambda item_id: None
        #: The catalogue's works like a work, for the model to choose from.
        self.candidates: Callable[[Item], list[Item]] = lambda item: []

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = client()
        return self._http

    def wanted(self, item: Item) -> bool:
        """Never in the background: the work of the day asks for itself."""
        return False

    def in_library(self, item: Item) -> bool:
        return self.day_of(item.id) is not None

    def source_hash(self, item: Item) -> str:
        """A work picked again another day is written about again (why today)."""
        day = self.day_of(item.id)
        return text_hash(item.title, item.artist, item.date_text, day.isoformat() if day else "")

    def _wiki(self, lang: str, title: str) -> str:
        return wikipedia_text(self.http, lang, title, WORK_CHARS, COMPOSITION_SECTIONS)

    def context(self, item: Item) -> Context:
        facts = self.wikidata.facts(self.http, item)
        return Context(
            day=self.day_of(item.id) or date.today(),
            facts=facts,
            wiki_pl=self._wiki("pl", facts.wiki_pl) if facts else "",
            wiki_en=self._wiki("en", facts.wiki_en) if facts else "",
            artist_wiki=(
                wikipedia_intro(self.http, "en", item.artist)[:ARTIST_CHARS] if item.artist else ""
            ),
            candidates=self.candidates(item),
        )

    def params(self, item: Item) -> dict[str, Any]:
        img = picture(self.images, item)
        context = replace(self.context(item), size=img.size)
        text = {"type": "text", "text": request_text(item, context)}
        params = request(
            model=OPUS,
            system=self.system,
            content=[image_block(img), text],
            schema=SCHEMA,
            max_tokens=16000,
            effort="medium",
        )
        params["timeout"] = 600.0  # a long answer: minutes, not the client's two
        return params

    def revise(
        self, item: Item, params: dict[str, Any], answer: Answer, ask: Callable[..., Answer]
    ) -> Answer:
        """The answer's pixels made fractions, and its composition checked by
        Claude over the marks drawn on the picture (``ai.check``): a mark that
        missed moved, one that cannot be defended left out. When the check
        cannot be had (the month's limit, an error) the answer stays as it was."""
        if answer.data is None:
            return answer
        data = to_fractions(answer.data, sent_size(params))
        from .check import check

        try:
            data = check(self.images, item, data, ask)
        except (AiUnavailable, anthropic.APIError) as err:
            log.warning("composition check of %s skipped: %s", item.id, err)
        except Exception:  # the page is paid for: never lost to its check
            log.exception("composition check of %s failed", item.id)
        return replace(answer, data=data)

    def apply(self, item: Item, note: Note) -> None:
        """Keeps the answer cleaned: what the app shows."""
        ids = [c.id for c in self.candidates(item)]
        essay = clean(note.data, ids)
        if essay is None:
            data: dict[str, Any] = {"failed": True}
        else:
            data = essay.model_dump()
            for key in (CHECKED, CHECK_ROUND):
                if key in note.data:
                    data[key] = note.data[key]
        self.library.save_note(note.model_copy(update={"data": data}))

    def fresh(self, item: Item, note: Note | None) -> bool:
        """A written page stays until the work's text (or its day) changes,
        also when the prompt changes: written once, paid for once. A failed
        one is asked again with a new prompt."""
        return (
            note is not None
            and note.source_hash == self.source_hash(item)
            and ("teaser" in note.data or note.prompt_version == self.prompt_version)
        )

    def take(self, item: Item, note: Note | None, *, keep_date: bool = False) -> bool:
        """Keeps another page written about the work (its study, its day's
        page) as this job's, without "why today": the same text is never
        paid for twice. False when ``note`` is no written page. ``keep_date``:
        written when that page was (else now)."""
        if note is None or "teaser" not in note.data:
            return False
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=self.kind,
                model=note.model,
                prompt_version=self.prompt_version,
                source_hash=self.source_hash(item),
                data={**note.data, "why_today": ""},
                created_at=note.created_at if keep_date else "",
            )
        )
        return True

    def essay(self, item: Item) -> Essay | None:
        """The work's write-up, if it is up to date."""
        note = self.library.note(item.id, self.kind)
        if not self.fresh(item, note) or note is None or "teaser" not in note.data:
            return None
        essay = Essay.model_validate(note.data)
        shown = takes(essay.composition.views)
        if shown == essay.composition.views:
            return essay
        return essay.model_copy(update={"composition": _composition(shown)})

    def failed(self, item: Item) -> bool:
        """Asked already, without a usable answer: not asked again today."""
        note = self.library.note(item.id, self.kind)
        return self.fresh(item, note) and note is not None and "teaser" not in note.data
