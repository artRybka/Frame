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
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

import httpx
from PIL import Image
from pydantic import BaseModel, Field

from ..imaging.layout import load_image
from ..imaging.text import sentences
from ..library.markup import strip_markup
from ..library.models import Note
from ..library.museums import client
from ..library.wikidata import Facts, Wikidata, wikipedia_intro, wikipedia_text
from .client import OPUS, request
from .jobs import NoteJob, Usage, text_hash
from .pl_text import description

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .config import AiConfigStore

KIND = "daily"
#: Changed whenever the prompt changes, so the text is written again.
PROMPT_VERSION = "daily-5"
#: The tile's two lines under the title (characters).
TEASER_CHARS = 100
#: The picture goes out this big: enough to see the composition.
IMAGE_SIDE = 1568
#: Wikipedia articles about the work, and the artist's opening paragraph.
WORK_CHARS = 9000
ARTIST_CHARS = 1500
MAX_VIEWS = 3
MAX_MARKS = 6
MAX_LINE_POINTS = 12
#: The marks drawn over the picture, and how many points each takes
#: (lines and arrows: 2 up to ``MAX_LINE_POINTS``).
SHAPES = {"arrow": 2, "line": 2, "loop": 2, "triangle": 3, "rect": 2, "underline": 2}
#: The grids the app draws under a view: none, the golden section, thirds.
GRIDS = ("none", "golden", "thirds")
MAX_SIMILAR = 6
#: Fragments worth a close look ("Detale"), and their sides (fractions).
MAX_DETAILS = 3
DETAIL_MIN = 0.04
DETAIL_MAX = 0.6
MAX_LEGACY = 5
SOURCES = ("obraz", "dane muzeum", "Wikidata", "Wikipedia", "wiedza ogólna")
#: Picture, sources and an answer with thinking.
TYPICAL = Usage(input_tokens=9000, cache_read_input_tokens=1500, output_tokens=5000)

MONTHS = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
    "września", "października", "listopada", "grudnia",
)  # fmt: skip

SYSTEM = """Piszesz „Dzieło dnia” do aplikacji domowej ramki z kolorowym e-papierem: \
krótkie, mądre omówienie jednego dzieła dla miłośnika sztuki, który nie jest historykiem sztuki.

Zasady:
- Naturalna, poprawna polszczyzna, jak w dobrym polskim muzeum. Bez superlatywów, bez \
ozdobników i bez zwrotów do czytelnika. Nazwy japońskie i chińskie w polskiej transkrypcji \
(Fudżi, Hiroszige). Ustalone polskie tytuły dzieł, gdy istnieją.
- Fakty bierz z podanych źródeł i z obrazu. Wiedzę ogólną dopuszczasz tylko wtedy, gdy jesteś \
jej pewien jak encyklopedia (np. słynne nawiązania do bardzo znanego dzieła). Nie wymyślaj dat, \
cytatów, nazwisk ani okoliczności. Jeśli czegoś nie wiesz, pomiń to.
- "title": polski tytuł dzieła.
- "teaser": JEDNO zdanie, najwyżej 90 znaków ze spacjami (musi się zmieścić w dwóch wierszach \
kafelka, nie będzie skracane), które zachęci do przeczytania reszty. Bez daty i nazwiska autora \
(aplikacja je pokazuje).
- "focus": najważniejsze miejsce obrazu (twarz głównej postaci albo główny motyw), x i y jak \
w kompozycji. Aplikacja kadruje wokół niego niski, szeroki pasek miniatury.
- "why_today": jedno zdanie, dlaczego to dzieło pasuje do podanej daty: rocznica urodzin lub \
śmierci autora albo powstania dzieła (tylko gdy wynika z dat w źródłach i wypada dziś lub w \
tym tygodniu), pora roku, święto. Pusty, gdy nie ma prawdziwego powodu.
- "headline": tytuł tekstu o okolicznościach (2–6 słów, bez kropki), konkretny dla tego \
dzieła, np. „Pocztówka z pielgrzymki do Fudżi”. Nie „Kontekst”, nie tytuł dzieła.
- "context": dwa krótkie akapity (po 300–550 znaków): kiedy i w jakich okolicznościach dzieło \
powstało, co było w nim nowe, jak je przyjęto.
- "artist": krótka notka o autorze, dwa-trzy zdania (najwyżej 400 znaków): kim był, czym się \
wyróżniał i w którym miejscu jego drogi powstało to dzieło. Bez powtarzania tekstu powyżej.
- "composition": analiza kompozycji jako 1–3 ujęcia ("views"), każde rysowane osobno na \
rozbielonym obrazie jak ołówkiem na kalce. Najczęściej dwa: „Spojrzenie” (co i w jakiej \
kolejności prowadzi wzrok) i „Geometria”. W geometrii szukaj złotego podziału (linie 0,382 i \
0,618), trójpodziału, przekątnych, trójkątów, kół i owali, osi symetrii, rytmu powtórzeń; \
trzecie ujęcie tylko, gdy ma sens (np. „Światło”). Pokazuj tylko to, co naprawdę widać, \
niczego nie naginaj; jeśli żadna siatka nie pasuje, "grid" to "none". Każde ujęcie: \
"title" (1–3 słowa), "grid" ("golden" lub "thirds", gdy kompozycja naprawdę się na nich \
opiera, aplikacja narysuje siatkę), "text" (dwa-trzy zdania, co to ujęcie pokazuje) i \
"marks": 2–5 śladów. Ślad: "shape" i "points" (x i y to ułamki szerokości i wysokości obrazu \
od lewego górnego rogu, 0–1, dokładnie na opisywanej rzeczy): "arrow" (2–12 punktów wzdłuż \
drogi, grot na końcu), "line" (2–12 punktów: horyzont, przekątna, oś, krawędź), "loop" (kółko \
wokół rzeczy: środek i jeden róg prostokąta, w który się wpisuje), "triangle" (3 wierzchołki), \
"rect" (dwa przeciwległe rogi), "underline" (podkreślenie falką: początek i koniec). Do \
każdego "title" (1–3 słowa, podpis przy śladzie) i "text" (najwyżej 45 znaków, dopisek pod \
podpisem). Kolejność śladów to kolejność czytania.
- "colour": dwa-trzy zdania o kolorze i świetle.
- "details": 2–3 fragmenty warte powiększenia, których w całym obrazie na telefonie nie \
widać: twarz, dłoń, przedmiot, napis lub sygnatura, faktura farby, drobny motyw w tle. \
Aplikacja wytnie je z oryginału w pełnej rozdzielczości. Każdy: "title" (1–3 słowa), "text" \
(jedno-dwa zdania, najwyżej 220 znaków: co tu widać i dlaczego warto się przyjrzeć), "x" i \
"y" (lewy górny róg kadru) oraz "w" i "h" (szerokość i wysokość kadru), wszystko jako ułamki \
szerokości i wysokości obrazu. Kadr ciasno wokół rzeczy: bok 10–35% szerokości obrazu, \
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


def _unit(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number)) if number == number else None  # NaN is not a place


def _spot(raw: Any) -> Spot | None:
    if not isinstance(raw, dict):
        return None
    x, y = _unit(raw.get("x")), _unit(raw.get("y"))
    return None if x is None or y is None else Spot(x=x, y=y)


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _mark(raw: dict[str, Any]) -> Mark | None:
    shape, title = str(raw.get("shape") or ""), _text(raw.get("title"), 40)
    spots = [s for s in map(_spot, raw.get("points") or []) if s is not None]
    if shape not in SHAPES or not title or len(spots) < SHAPES[shape]:
        return None
    keep = MAX_LINE_POINTS if shape in ("arrow", "line") else SHAPES[shape]
    return Mark(shape=shape, points=spots[:keep], title=title, text=_text(raw.get("text"), 80))


def _view(raw: dict[str, Any]) -> View | None:
    marks = [m for m in map(_mark, _dicts(raw.get("marks"))) if m is not None][:MAX_MARKS]
    title = _text(raw.get("title"), 40)
    if not marks or not title:
        return None
    grid = raw.get("grid") if raw.get("grid") in GRIDS else "none"
    return View(title=title, grid=str(grid), text=_text(raw.get("text"), 600), marks=marks)


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


def _composition(views: list[View]) -> Composition:
    """The takes, and the first one as 0.42 apps draw it: a numbered point
    per mark and its lines and arrows."""
    if not views:
        return Composition()
    first = views[0].marks
    points = [Point(**m.anchor().model_dump(), title=m.title, text=m.text) for m in first]
    lines = [Line(label=m.title, points=m.points) for m in first if m.shape in ("arrow", "line")]
    return Composition(views=views, points=points, lines=lines)


def clean(data: dict[str, Any], candidates: list[str]) -> Essay | None:
    """A model's answer made safe to show; ``None`` when it is unusable."""
    teaser = short(_text(data.get("teaser"), 400), TEASER_CHARS)
    if not teaser:
        return None
    found = data.get("composition")
    raw: dict[str, Any] = found if isinstance(found, dict) else {}
    views = [v for v in map(_view, _dicts(raw.get("views"))) if v is not None][:MAX_VIEWS]
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


def picture_block(images: ImageCache, item: Item) -> dict[str, Any]:
    """The work's picture, as large as the model reads it: the original when
    it can be had, else the thumbnail."""
    path, _ = images.picture(item)
    img = load_image(path.read_bytes()).convert("RGB")
    img.thumbnail((IMAGE_SIDE, IMAGE_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    data = base64.standard_b64encode(out.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


class DailyJob(NoteJob):
    kind = KIND
    model = OPUS
    prompt_version = PROMPT_VERSION
    typical = TYPICAL

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

    def context(self, item: Item) -> Context:
        facts = self.wikidata.facts(self.http, item)
        return Context(
            day=self.day_of(item.id) or date.today(),
            facts=facts,
            wiki_pl=wikipedia_text(self.http, "pl", facts.wiki_pl, WORK_CHARS) if facts else "",
            wiki_en=wikipedia_text(self.http, "en", facts.wiki_en, WORK_CHARS) if facts else "",
            artist_wiki=(
                wikipedia_intro(self.http, "en", item.artist)[:ARTIST_CHARS] if item.artist else ""
            ),
            candidates=self.candidates(item),
        )

    def params(self, item: Item) -> dict[str, Any]:
        context = self.context(item)
        text = {"type": "text", "text": request_text(item, context)}
        params = request(
            model=OPUS,
            system=SYSTEM,
            content=[picture_block(self.images, item), text],
            schema=SCHEMA,
            max_tokens=16000,
            effort="medium",
        )
        params["timeout"] = 600.0  # a long answer: minutes, not the client's two
        return params

    def apply(self, item: Item, note: Note) -> None:
        """Keeps the answer cleaned: what the app shows."""
        ids = [c.id for c in self.candidates(item)]
        essay = clean(note.data, ids)
        data = essay.model_dump() if essay is not None else {"failed": True}
        self.library.save_note(note.model_copy(update={"data": data}))

    def essay(self, item: Item) -> Essay | None:
        """The work's write-up, if it is up to date."""
        note = self.library.note(item.id, KIND)
        if not self.fresh(item, note) or note is None or "teaser" not in note.data:
            return None
        return Essay.model_validate(note.data)

    def failed(self, item: Item) -> bool:
        """Asked already, without a usable answer: not asked again today."""
        note = self.library.note(item.id, KIND)
        return self.fresh(item, note) and note is not None and "teaser" not in note.data
