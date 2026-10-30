"""Discover's work of the day, written up by Claude: why today, the context,
an analysis of the composition with points and lines on the picture, its
colour, how it fares on the frame, which of the catalogue's works are like
it and what it led to later.

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
PROMPT_VERSION = "daily-2"
#: The tile's two lines under the title (characters).
TEASER_CHARS = 100
#: The picture goes out this big: enough to see the composition.
IMAGE_SIDE = 1568
#: Wikipedia articles about the work, and the artist's opening paragraph.
WORK_CHARS = 9000
ARTIST_CHARS = 1500
MAX_POINTS = 6
MAX_LINES = 4
MAX_LINE_POINTS = 12
MAX_SIMILAR = 6
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
- "composition": analiza kompozycji widocznej na obrazie. "points": 3–6 punktów, każdy z \
krótkim tytułem (2–3 słowa) i jednym-dwoma zdaniami; x i y to miejsce na obrazie, ułamki \
szerokości i wysokości od lewego górnego rogu (0–1), dokładnie tam, gdzie jest opisywana rzecz. \
Kolejność punktów to kolejność czytania. "lines": 0–4 linie kompozycyjne (główny łuk, \
przekątna, horyzont, oś symetrii, trójkąt), każda jako 2–12 punktów, przez które biegnie, \
i krótki podpis. Rysuj tylko linie, które naprawdę widać.
- "colour": dwa-trzy zdania o kolorze i świetle.
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
        points=_list(
            _object(x={"type": "number"}, y={"type": "number"}, title=_str(), text=_str())
        ),
        lines=_list(_object(label=_str(), points=_list(_POINT))),
    ),
    colour=_str(),
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


class Composition(BaseModel):
    points: list[Point] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)


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


def clean(data: dict[str, Any], candidates: list[str]) -> Essay | None:
    """A model's answer made safe to show; ``None`` when it is unusable."""
    teaser = short(_text(data.get("teaser"), 400), TEASER_CHARS)
    if not teaser:
        return None
    found = data.get("composition")
    raw: dict[str, Any] = found if isinstance(found, dict) else {}
    points = []
    for p in _dicts(raw.get("points"))[:MAX_POINTS]:
        spot, title = _spot(p), _text(p.get("title"), 60)
        if spot is not None and title:
            points.append(Point(x=spot.x, y=spot.y, title=title, text=_text(p.get("text"), 400)))
    lines = []
    for line in _dicts(raw.get("lines"))[:MAX_LINES]:
        spots = [s for s in map(_spot, line.get("points") or []) if s is not None]
        if len(spots) >= 2:
            lines.append(Line(label=_text(line.get("label"), 60), points=spots[:MAX_LINE_POINTS]))
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
        composition=Composition(points=points, lines=lines),
        colour=_text(data.get("colour"), 500),
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
