"""Discover's work of the day, written up by Claude: why today, the context,
an analysis of the composition as pencil marks on the picture, its colour,
fragments worth a close look, how it fares on the frame, which of the
catalogue's works are like it and what it led to later.

One question a day (Opus sees a picture far better than the others), from
the picture itself and what the museum, Wikidata and Wikipedia say; the
composition is a question of its own (``ai.composition``), asked after it. The
server picks the work (``frame_server.daily``) and the works like it; the
model only says why each one is like it, so it never names a work the
catalogue does not have.
"""

from __future__ import annotations

import base64
import copy
import io
import logging
import re
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
PROMPT_VERSION = "daily-11"
#: The tile's two lines under the title (characters).
TEASER_CHARS = 100
#: The picture goes out this big: as large as Opus reads one, so that it
#: points at things to the pixel.
IMAGE_SIDE = 2576
#: What Opus reads without making the picture smaller first: the long edge
#: and the visual tokens (one per 28 × 28 pixels). A larger picture is made
#: smaller by the API, and the model's pixels are then its, not ours: a
#: 2560 × 1920 picture was read at 2222 × 1667, so every box drawn on the
#: picture before 2026-11-03 came out too small and too far up and left
#: (Mateusz: "wycinki nie trafiają w to, czego dotyczy opis").
MODEL_EDGE = 2576
MODEL_TOKENS = 4784
#: Marks a page whose boxes were asked for on a picture the model read at
#: its own size (:func:`model_size`); pages without it are mended when read.
BOXES = "boxes"
BOXES_VERSION = 2
#: The longest side of a kept original (``library.images.IMAGE_MAX``).
ORIGINAL_SIDE = 2560
#: Wikipedia articles about the work, and the artist's opening paragraph.
WORK_CHARS = 9000
ARTIST_CHARS = 1500
#: The one take on the composition the app shows (Mateusz 2026-11-02:
#: no "Geometria detali" any more, and not called "Geometria").
TAKE = "Analiza kompozycji"
#: Article sections worth keeping when Wikipedia is cut: what it says of
#: the composition.
COMPOSITION_SECTIONS = ("compos", "kompozyc", "analy", "analiz", "descript", "opis")
#: Kept in a page whose composition Claude checked over its own marks drawn
#: on the picture (``ai.check``): what the check changed.
CHECKED = "composition_checked"
#: Which round of the composition a page's take went through (round 2: the
#: great lines of "Geometria"; round 3: the golden spiral, more grids, no
#: "Spojrzenie", both asked for by Mateusz 2026-10-31; round 4: the analysis
#: asked apart, ``ai.composition``, 2026-11-02; round 5: no rhythms of
#: furniture or of a few trees, after the first real analyses; round 6:
#: readable marks, perspective as rays, Mateusz on Nighthawks; round 7: the
#: main layout always drawn, a wedge whose vanishing point lies far off as
#: two lines, as round 6 dropped Nighthawks' wedge). Pages of an
#: earlier round are written again by ``ai.composition.ComposeJob`` as the
#: owner lets it.
CHECK_ROUND = "composition_round"
ROUND = 7
#: Kept in a page that came back without some of what every page has (see
#: :func:`missing`) though it was asked for twice: what it lacks. A page
#: without it that lacks them all was written before the second question
#: and is asked for again once (:meth:`DailyJob.fresh`).
INCOMPLETE = "incomplete"
MAX_MARKS = 6
MAX_LINE_POINTS = 12
#: A rhythm's beats (a pair of points each) and a perspective's rays.
MAX_BEATS = 12
MIN_BEATS = 3
MAX_RAYS = 8
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
#: The marks drawn over the picture, and how many points each takes at
#: least (lines, arrows and motion: up to ``MAX_LINE_POINTS``). A "rhythm"
#: is a pair of points per repeated form, its foot and top: the app draws a
#: stroke along each, parallel to the others, and no line between them
#: (Mateusz 2026-11-02). "rays" are a vanishing point and the far ends of
#: the edges running into it; "motion" a movement in the picture (a
#: flight, a swing), drawn as a sweeping arrow with speed lines. Old pages'
#: rhythms (one point per form) were in a take no longer shown.
SHAPES = {
    "arrow": 2, "line": 2, "loop": 2, "triangle": 3, "rect": 2, "underline": 2, "spiral": 3,
    "rhythm": 2 * MIN_BEATS, "rays": 3, "motion": 2,
}  # fmt: skip
#: The shapes that run through several points.
PATHS = ("arrow", "line", "motion")
#: The shapes of the picture's great lines, which may run on past its
#: edges (a big triangle's apex up in the sky, its feet beyond the frame, a
#: vanishing point above the picture): their points may lie this far
#: outside it (fraction of the side).
REACHING = ("line", "triangle", "spiral", "rays")
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
#: Moments of the artist's life on the line under their name.
MAX_MILESTONES = 3
#: Historical events on the artist's line of life (Mateusz 2026-11-03: "jedno lub dwa").
MAX_EVENTS = 2
#: The paints named under "Kolor i światło" ("Farby, z których powstał").
MAX_PIGMENTS = 4
SOURCES = ("obraz", "dane muzeum", "Wikidata", "Wikipedia", "wiedza ogólna")
#: Picture, sources and an answer with thinking (the composition is asked
#: apart, ``ai.composition``, and counted there).
TYPICAL = Usage(input_tokens=17000, cache_read_input_tokens=2500, output_tokens=6000)

MONTHS = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
    "września", "października", "listopada", "grudnia",
)  # fmt: skip

#: Where the model puts its points: pixels of the picture it gets (it
#: points far better in pixels than in fractions); the server divides them.
POINTS = """Współrzędne podajesz w pikselach \
obrazu, który dostajesz (jego wymiary są w danych: OBRAZ), od lewego górnego rogu: x w prawo, \
y w dół. Celuj dokładnie."""


#: Historical events on the artist's line of life, for the page's question
#: and the one filling older pages in (``ai.extras``).
EVENTS_RULE = """- "events": 1–2 wydarzenia historyczne z czasu życia autora, które dotknęły \
jego świata (kraju, miasta, sztuki), np. „wojna trzydziestoletnia”, „rewolucja francuska”, \
„wynalezienie fotografii”: "year" (rok początku) i "text" (najwyżej 40 znaków, bez kropki). \
Tylko pewne daty; nie powtarzaj chwil z "milestones".
"""


#: The paints, for the page's question and the one filling older pages in
#: (``ai.extras``). Named by the sources, else the likely ones for the
#: picture's main colours (Mateusz 2026-11-03: "dawać je częściej,
#: dopasowując się do kolorów z obrazu"), marked as such and never later
#: than the work.
PIGMENTS_RULE = """- "pigments": 2–4 farby (pigmenty), z których powstały główne kolory tego \
dzieła (spójrz na obraz i na „Kolory (analiza serwera)”), tylko dla dzieł malowanych (olej, \
tempera, akwarela, gwasz, fresk, pastel); dla grafiki, rysunku, fotografii i rzeźby pusta lista. \
Najpierw te, które wymienia opis muzeum, Wikipedia albo pewna wiedza o badaniach \
konserwatorskich tego dzieła: "sure": true. Gdy źródła milczą, podaj farby, którymi ten malarz \
albo malarze jego czasu, miejsca i techniki najpewniej uzyskiwali te kolory: "sure": false, a \
"text" zaczyna się od „Najpewniej” albo „Prawdopodobnie”. Nigdy farby młodszej niż dzieło (np. \
błękit pruski od 1706, biel cynkowa od 1834, błękit kobaltowy od 1802, ultramaryna syntetyczna \
od 1828, żółcień kadmowa od ok. 1840, zieleń szmaragdowa (viridian) od 1838, biel tytanowa od \
1921). Każda: "name" (polska nazwa, np. „ultramaryna naturalna”), "hex" (barwa samej farby, jak \
najbliżej koloru na obrazie, np. "#2A4FA0"), "where" (gdzie na obrazie, 2–5 słów), "text" (jedno \
zdanie, najwyżej 140 znaków: skąd się brała, ile kosztowała, co w niej szczególnego), "sure"."""

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
    + """- "born", "died", "milestones", "events", "pigments": jak niżej (LINIA ŻYCIA I FARBY).
"""
    + """- Analizy kompozycji tu nie piszesz: robi ją osobne pytanie.
- "colour": dwa-trzy zdania o kolorze i świetle.
- "details": 2–3 fragmenty warte powiększenia, których w całym obrazie na telefonie nie \
widać: twarz, dłoń, przedmiot, napis lub sygnatura, faktura farby, drobny motyw w tle. \
Aplikacja wytnie je z oryginału w pełnej rozdzielczości. Każdy: "title" (1–3 słowa), "text" \
(jedno-dwa zdania, najwyżej 220 znaków: co tu widać i dlaczego warto się przyjrzeć), "x" i \
"y" (lewy górny róg kadru) oraz "w" i "h" (szerokość i wysokość kadru), wszystko w pikselach \
obrazu. Kadr ciasno wokół rzeczy: bok 10–35% szerokości obrazu, \
proporcje w pikselach od 3:4 do 4:3. Fragmenty różne od siebie.
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
- "sources": źródła, z których faktycznie skorzystałeś.

"""
    + "LINIA ŻYCIA I FARBY\n"
    + """- "born", "died": rok urodzin i rok śmierci autora; 0, gdy nieznany (także dla autora \
anonimowego lub warsztatu) albo autor żyje.
- "milestones": 2–3 ważne chwile z życia autora na jego linii życia, w porządku lat: "year" \
(rok) i "text" (najwyżej 50 znaków, bez kropki, np. „wstępuje do gildii św. Łukasza”, „wyjazd \
do Paryża”). Bez urodzin, śmierci i powstania tego dzieła. Tylko ze źródeł albo pewnej wiedzy \
encyklopedycznej; pusta lista, gdy ich nie ma.
"""
    + EVENTS_RULE
    + PIGMENTS_RULE
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
#: One take on the composition as the model gives it (``ai.composition``, ``ai.check``).
VIEW = _object(
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

#: The artist's line of life and the work's paints: in the page's answer,
#: and asked alone for pages written before them (``ai.extras``).
EXTRAS_PROPS: dict[str, Any] = {
    "born": {"type": "integer"},
    "died": {"type": "integer"},
    "milestones": _list(_object(year={"type": "integer"}, text=_str())),
    "events": _list(_object(year={"type": "integer"}, text=_str())),
    "pigments": _list(
        _object(name=_str(), hex=_str(), where=_str(), text=_str(), sure={"type": "boolean"})
    ),
}

SCHEMA = _object(
    title=_str(),
    teaser=_str(),
    focus=_POINT,
    why_today=_str(),
    headline=_str(),
    context=_list(_str()),
    artist=_str(),
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
    **EXTRAS_PROPS,
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
        if self.shape in ("spiral", "rays"):  # its eye, its vanishing point
            return self.points[-1] if self.shape == "spiral" else self.points[0]
        if self.shape == "rhythm":  # the middle beat's middle
            a, b = self.points[2 * (len(self.points) // 4) : 2 * (len(self.points) // 4) + 2]
            return Spot(x=(a.x + b.x) / 2, y=(a.y + b.y) / 2)
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


class Milestone(BaseModel):
    """A moment of the artist's life, on the line under their name."""

    year: int
    text: str


class Pigment(BaseModel):
    """A paint the work is made with: as its sources name it (``sure``), or
    the likely one for one of its colours."""

    name: str
    hex: str
    where: str = ""
    text: str = ""
    sure: bool = True


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
    #: The artist's years, when the model knows them (the museum's line
    #: about the artist comes first, ``web.daily_api``).
    born: int | None = None
    died: int | None = None
    milestones: list[Milestone] = Field(default_factory=list)
    #: Historical events in the artist's lifetime (same shape as a moment).
    events: list[Milestone] = Field(default_factory=list)
    pigments: list[Pigment] = Field(default_factory=list)


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
        f"Muzeum: {item.held_by or item.museum}",
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


def _beats(spots: list[Spot]) -> list[Spot]:
    """A rhythm's points as pairs (a form's foot and top), without a pair
    that is a dot."""
    pairs = [(spots[n], spots[n + 1]) for n in range(0, len(spots) - 1, 2)]
    kept = [p for p in pairs if max(abs(p[0].x - p[1].x), abs(p[0].y - p[1].y)) > SAME_SPOT]
    return [s for pair in kept[:MAX_BEATS] for s in pair]


def _rays(spots: list[Spot]) -> list[Spot]:
    """A vanishing point and the far ends of its rays, without an end on
    the point itself or on the end before it."""
    eye, ends = spots[0], _distinct(spots[1:])
    far = [e for e in ends if max(abs(e.x - eye.x), abs(e.y - eye.y)) > MIN_LOOP * 2]
    return [eye, *far[:MAX_RAYS]]


def _mark(raw: dict[str, Any]) -> Mark | None:
    """A mark that can be drawn and means something: a triangle that is not
    a line, a loop around something; a nearly level line drawn level, a
    diagonal from corner to corner; a rhythm of three beats at least. The
    picture's great lines may run on past its edges."""
    shape, title = str(raw.get("shape") or ""), _text(raw.get("title"), 40)
    reach = REACH if shape in REACHING else 0.0
    spots = [s for s in (_spot(p, reach) for p in raw.get("points") or []) if s is not None]
    if shape in PATHS:
        spots = _distinct(spots)
    elif shape == "rhythm":
        spots = _beats(spots)
    elif shape == "rays" and spots:
        spots = _rays(spots)
    if shape not in SHAPES or not title or len(spots) < SHAPES[shape]:
        return None
    if shape in PATHS:
        spots = spots[:MAX_LINE_POINTS]
    elif shape not in ("rhythm", "rays"):
        spots = spots[: SHAPES[shape]]
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
    view = View(title=title, grid=str(grid), text=_text(raw.get("text"), 1000), marks=marks)
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
    """The one take the app shows, called :data:`TAKE`: the analysis, or on
    a page written before it, its "Geometria" (the whole picture's lines).
    Such a page's "Geometria detali", "Spojrzenie" and third take ("Rytm",
    "Światło") are left out, and so are its old rhythms (a point per form,
    in a take no longer shown)."""
    whole = next((v for v in views if v.title == TAKE), None) or next(
        (v for v in views if _geometry(v)), None
    )
    if whole is None:
        return []
    if whole.title != TAKE:
        marks = [m for m in whole.marks if m.shape != "rhythm"]
        whole = whole.model_copy(update={"title": TAKE, "marks": marks})
    return [whole] if whole.marks else []


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
        **extras(data),
    )


HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _year_of(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 0 < year <= date.today().year else None


def extras(data: dict[str, Any]) -> dict[str, Any]:
    """The artist's years, the moments of their life and the historical
    events in it (within it, in order, each year once) and the work's paints
    from a model's answer, made safe to show: as :class:`Essay` keeps them."""
    born, died = _year_of(data.get("born")), _year_of(data.get("died"))
    if born is not None and died is not None and not 10 < died - born < 110:
        born = died = None
    low = born if born is not None else (died - 110 if died is not None else 0)
    high = died + 1 if died is not None else date.today().year
    moments: dict[int, Milestone] = {}
    for m in _dicts(data.get("milestones")):
        year, text = _year_of(m.get("year")), _text(m.get("text"), 60).rstrip(".")
        if year is not None and text and low <= year <= high and year not in moments:
            moments[year] = Milestone(year=year, text=text)
    events: dict[int, Milestone] = {}
    for e in _dicts(data.get("events")):
        year, text = _year_of(e.get("year")), _text(e.get("text"), 50).rstrip(".")
        if year is not None and text and low <= year <= high and year not in events:
            events[year] = Milestone(year=year, text=text)
    pigments = [
        Pigment(
            name=name,
            hex=str(p.get("hex")).upper(),
            where=_text(p.get("where"), 60),
            text=_text(p.get("text"), 200),
            sure=p.get("sure") is not False,
        )
        for p in _dicts(data.get("pigments"))
        if (name := _text(p.get("name"), 50)) and HEX.match(str(p.get("hex") or ""))
    ]
    return {
        "born": born,
        "died": died,
        "milestones": [moments[y] for y in sorted(moments)][:MAX_MILESTONES],
        "events": [events[y] for y in sorted(events)][:MAX_EVENTS],
        "pigments": pigments[:MAX_PIGMENTS],
    }


#: What every page has, besides its text: the takes on its composition,
#: its colour, the fragments worth a close look and how it fares on the
#: frame. Claude once (2026-11-02, Hopper's "Nighthawks") answered with the
#: text and the note about the artist and left all of these empty.
WHOLE = ("composition", "colour", "details", "on_frame")
#: What the page's own question answers of it (the composition is asked apart).
ANSWERED = ("colour", "details", "on_frame")


def missing(data: dict[str, Any], parts: tuple[str, ...] = WHOLE) -> list[str]:
    """What of ``parts`` a page (or a model's answer in fractions) lacks,
    as the app would show it."""
    found = data.get("composition")
    raw: dict[str, Any] = found if isinstance(found, dict) else {}
    views = takes([v for v in map(_view, _dicts(raw.get("views"))) if v is not None])
    has = {
        "composition": bool(views or _dicts(raw.get("points"))),
        "colour": bool(_text(data.get("colour"))),
        "details": any(d is not None for d in map(_detail, _dicts(data.get("details")))),
        "on_frame": bool(_text(data.get("on_frame"))),
    }
    return [part for part in parts if not has[part]]


def unfinished(data: dict[str, Any]) -> bool:
    """A written page without its composition, colour and note on the frame
    that was never asked for again: one to be written once more."""
    if "teaser" not in data or INCOMPLETE in data:
        return False
    lacking = missing(data)
    return all(part in lacking for part in ("composition", "colour", "on_frame"))


def _tokens(width: int, height: int) -> int:
    return -(-width // 28) * -(-height // 28)


def model_size(width: int, height: int) -> tuple[int, int]:
    """The size the model reads a picture at (the API's own rule: the
    largest size of the same proportions within :data:`MODEL_EDGE` and
    :data:`MODEL_TOKENS`); the picture's own when it fits."""

    def fits(w: int, h: int) -> bool:
        edge = MODEL_EDGE
        return (
            -(-w // 28) * 28 <= edge and -(-h // 28) * 28 <= edge and _tokens(w, h) <= MODEL_TOKENS
        )

    if fits(width, height):
        return width, height
    if height > width:
        h, w = model_size(height, width)
        return w, h
    ratio = width / height
    lo, hi = 1, width  # lo fits, hi does not
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if fits(mid, max(round(mid / ratio), 1)):
            lo = mid
        else:
            hi = mid
    return lo, max(round(lo / ratio), 1)


def picture(images: ImageCache, item: Item, side: int = IMAGE_SIDE) -> Image.Image:
    """The work's picture at most ``side`` pixels long, and no larger than
    the model reads one (:func:`model_size`), so that the pixels it answers
    in are the picture's: the original when it can be had, else the
    thumbnail."""
    path, _ = images.picture(item)
    img = load_image(path.read_bytes()).convert("RGB")
    img.thumbnail((side, side), Image.Resampling.LANCZOS)
    size = model_size(*img.size)
    if size != img.size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return img


def mend_boxes(essay: Essay, item: Item) -> Essay:
    """A page written before :data:`BOXES_VERSION`: its details and its
    focus as they were meant, on the picture the model read (the original,
    at most :data:`ORIGINAL_SIDE` long, made smaller by the API). Its
    composition was checked on a picture small enough, so it stays."""
    if not item.width or not item.height:
        return essay
    scale = min(1.0, ORIGINAL_SIDE / max(item.width, item.height))
    sent = (max(round(item.width * scale), 1), max(round(item.height * scale), 1))
    read = model_size(*sent)
    fx, fy = sent[0] / read[0], sent[1] / read[1]
    if fx == 1 and fy == 1:
        return essay
    details = [
        d
        for d in (
            _detail(
                {
                    "title": box.title,
                    "text": box.text,
                    "x": box.x * fx,
                    "y": box.y * fy,
                    "w": box.w * fx,
                    "h": box.h * fy,
                }
            )
            for box in essay.details
        )
        if d is not None
    ]
    focus = essay.focus
    if focus is not None:
        focus = Spot(x=min(focus.x * fx, 1.0), y=min(focus.y * fy, 1.0))
    return essay.model_copy(update={"details": details, "focus": focus})


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
        #: What the sources say of each work being asked about, kept from
        #: the page's question for its composition's (``ai.composition``).
        self._sources: dict[str, Context] = {}

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

    def sources(self, item: Item) -> Context:
        """What Wikidata and Wikipedia say of the work and its artist."""
        facts = self.wikidata.facts(self.http, item)
        return Context(
            day=self.day_of(item.id) or date.today(),
            facts=facts,
            wiki_pl=self._wiki("pl", facts.wiki_pl) if facts else "",
            wiki_en=self._wiki("en", facts.wiki_en) if facts else "",
            artist_wiki=(
                wikipedia_intro(self.http, "en", item.artist)[:ARTIST_CHARS] if item.artist else ""
            ),
        )

    def context(self, item: Item) -> Context:
        return replace(self.sources(item), candidates=self.candidates(item))

    def params(self, item: Item) -> dict[str, Any]:
        img = picture(self.images, item)
        context = replace(self.context(item), size=img.size)
        self._sources[item.id] = context
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
        """The answer's pixels made fractions, and its composition asked for
        apart (``ai.composition``: written, then checked by Claude over the
        marks drawn on the picture). When the composition cannot be had
        (the month's limit, an error) the page is kept without it, and the
        background asks for it later (``ComposeJob``).

        An answer without some of what every page has (:func:`missing`) is
        asked for once more, and the fuller of the two is kept."""
        context = self._sources.pop(item.id, None)
        if answer.data is None:
            return answer
        data = {**to_fractions(answer.data, sent_size(params)), BOXES: BOXES_VERSION}
        if lacking := missing(data, ANSWERED):
            log.warning("page of %s came back without %s: asked again", item.id, ", ".join(lacking))
            try:
                again = ask(params)
            except (AiUnavailable, anthropic.APIError) as err:
                log.warning("page of %s not asked again: %s", item.id, err)
            else:
                answer = replace(answer, cost_usd=answer.cost_usd + again.cost_usd)
                fresh = to_fractions(again.data, sent_size(params)) if again.data else None
                if fresh is not None and len(missing(fresh, ANSWERED)) < len(lacking):
                    data = {**fresh, BOXES: BOXES_VERSION}
            if lacking := missing(data, ANSWERED):
                log.warning("page of %s kept without %s", item.id, ", ".join(lacking))
                data = {**data, INCOMPLETE: lacking}
        from .composition import compose

        data = {**data, "composition": {"views": []}}
        try:
            data.update(compose(self.images, item, context or self.sources(item), ask))
        except (AiUnavailable, anthropic.APIError) as err:
            log.warning("composition of %s not asked: %s", item.id, err)
        except Exception:  # the page is paid for: never lost to its composition
            log.exception("composition of %s failed", item.id)
        return replace(answer, data=data)

    def apply(self, item: Item, note: Note) -> None:
        """Keeps the answer cleaned: what the app shows."""
        ids = [c.id for c in self.candidates(item)]
        essay = clean(note.data, ids)
        if essay is None:
            data: dict[str, Any] = {"failed": True}
        else:
            data = essay.model_dump()
            for key in (CHECKED, CHECK_ROUND, INCOMPLETE, BOXES):
                if key in note.data:
                    data[key] = note.data[key]
        self.library.save_note(note.model_copy(update={"data": data}))

    def fresh(self, item: Item, note: Note | None) -> bool:
        """A written page stays until the work's text (or its day) changes,
        also when the prompt changes: written once, paid for once. A failed
        one is asked again with a new prompt; one that came back without
        its composition, colour and note on the frame before such answers
        were asked for twice (:func:`unfinished`) is asked again once."""
        if note is None or note.source_hash != self.source_hash(item):
            return False
        if "teaser" in note.data:
            return not unfinished(note.data)
        return note.prompt_version == self.prompt_version

    def take(self, item: Item, note: Note | None, *, keep_date: bool = False) -> bool:
        """Keeps another page written about the work (its study, its day's
        page) as this job's, without "why today" (a day's page written
        before keeps its own): the same text is never paid for twice. False
        when ``note`` is no written page, or an unfinished one.
        ``keep_date``: written when that page was (else now)."""
        if note is None or "teaser" not in note.data or unfinished(note.data):
            return False
        own = self.library.note(item.id, self.kind)
        why = ""
        if self.kind == KIND and own is not None and own.source_hash == self.source_hash(item):
            why = str(own.data.get("why_today") or "")
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=self.kind,
                model=note.model,
                prompt_version=self.prompt_version,
                source_hash=self.source_hash(item),
                data={**note.data, "why_today": why},
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
        if note.data.get(BOXES) != BOXES_VERSION:
            essay = mend_boxes(essay, item)
        shown = takes(essay.composition.views)
        if shown == essay.composition.views:
            return essay
        return essay.model_copy(update={"composition": _composition(shown)})

    def failed(self, item: Item) -> bool:
        """Asked already, without a usable answer: not asked again today."""
        note = self.library.note(item.id, self.kind)
        return self.fresh(item, note) and note is not None and "teaser" not in note.data
