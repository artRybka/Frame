"""Polish titles and texts about works, written by Claude.

A work with a museum description gets a translation (Haiku is good at
that and cheap); a work without one gets a short note written from its
picture and what the museum and Wikidata say (Sonnet sees the picture far
better). Both give the same fields: a title, a text sized for the frame's
DESCRIPTION mode, a fuller text for the app, the medium, the date and the
author's nationality with life years. The nationality is put together from
a dictionary where the museum's bio allows it (library/nationality.py):
models keep writing "holenderski" for "Dutch".

A note looks at the work from one of five sides (:data:`STYLES`), dealt
out in turn so that notes in a row differ (Mateusz 2026-11-14: "losować
będziemy z 5 różnych stylów"), and is told how the latest notes open. A
museum text that says nothing about the work itself (the artist's life, a
series, a collection) is no description: Haiku says so while translating
it, and Sonnet writes a note instead.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

import httpx
from pydantic import BaseModel, Field

from ..imaging.text import MAX_BODY, sentences
from ..library.markup import strip_artist, strip_language_prefix, strip_markup
from ..library.models import ItemKind, Note
from ..library.museums import client
from ..library.nationality import artist_note, fix_note
from ..library.verdict import Place, against
from ..library.wikidata import Facts, Wikidata, wikipedia_intro
from .client import HAIKU, SONNET, Answer, cost, image_block, request
from .jobs import NoteJob, Usage, text_hash

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .config import AiConfigStore

KIND = "pl_text"
#: Changed whenever the prompts change, so older texts are written again.
#: Not for the five styles of notes (2026-11-14): the texts written before
#: stay (Mateusz: "te które są zostawiamy").
PROMPT_VERSION = "pl-1"

#: A description shorter than this ("Gift of ...") is no description.
MIN_DESCRIPTION = 120
#: Nor is one with fewer words of its own than this: words that are not the
#: title, the author, the date, the medium, the museum or a catalogue's stock
#: words. "Boy in a Red Waistcoat, oil painting by Paul Cézanne, 1888–1890;
#: high-resolution scan" (a Commons file's caption) has three. Such a work
#: gets a note, written with the short text as one more fact.
MIN_OWN_WORDS = 10
TITLE_MAX = 80
#: The frame's first sentence is all a small space has room for.
FIRST_SENTENCE_MAX = 180
SHORT_MAX = 120
#: Wikipedia's opening paragraph, for a note.
WIKI_CHARS = 1200

Written = Literal["translation", "note"]
SOURCES = ("dane muzeum", "Wikidata", "Wikipedia", "obraz")
#: How many of the latest notes' openings a note is told not to repeat.
RECENT = 8
#: Words of each opening.
OPENING_WORDS = 7
#: How long the latest openings are kept between questions (a night's
#: batch asks hundreds at once).
RECENT_SECONDS = 60.0

#: The sides a note looks at the work from, dealt out in turn (a shuffled
#: round of all five, never the same twice in a row); tried on nine Met
#: works first (https://claude.ai/artifact/Etdn2eQhvP4w6xPai4Jihd).
STYLES: dict[str, tuple[str, str]] = {
    "opis": (
        "Opis",
        "Opisz dzieło jako całość: co i kogo przedstawia, jak jest ułożone, jakie ma barwy i "
        "światło, co w nim szczególne.",
    ),
    "wzrok": (
        "Co widać",
        "Prowadź wzrok po obrazie: od tego, co przyciąga najpierw, przez kolejne miejsca, do "
        "tego, na co warto spojrzeć dłużej.",
    ),
    "warsztat": (
        "Jak zrobione",
        "Pisz o tym, jak dzieło zostało zrobione: jak położona jest farba (gładko, grubo, "
        "widoczne pociągnięcia), rysunek i kontur, kolor i światło, faktura, którymi środkami "
        "artysta osiąga efekt (mgła, połysk materii, głębia, ruch). W grafice: kreska, druk, "
        "plamy koloru. Tylko to, co widać na reprodukcji; czego w tej skali nie widać, nie "
        "zgaduj.",
    ),
    "temat": (
        "Temat",
        "Kilka zdań o temacie: co znaczy przedstawiona scena, postać albo motyw, skąd się "
        "wziął (historia, legenda, zwyczaj, gatunek malarski, miejsce), czemu artyści go "
        "malowali i co z tego widać w tym dziele.",
    ),
    "szczegol": (
        "Szczegół",
        "Zacznij od jednego szczegółu, który łatwo przeoczyć, i od niego przejdź do całości: "
        "co ten szczegół mówi o dziele.",
    ),
}

#: A translation: the description in, two Polish versions of it out.
TRANSLATION_USAGE = Usage(input_tokens=500, cache_read_input_tokens=1000, output_tokens=1400)
#: A note: the thumbnail and the facts in, a note out.
NOTE_USAGE = Usage(input_tokens=1100, cache_read_input_tokens=1100, output_tokens=1200)

_RULES = f"""Przygotowujesz polskie teksty o dziełach sztuki do domowej ramki z kolorowym \
e-papierem i do aplikacji.

Zasady:
- Pisz naturalną, poprawną polszczyzną, jak w dobrym polskim muzeum. Bez ozdobników i bez \
superlatywów.
- Jeśli dzieło ma ustalony polski tytuł, użyj go. Polskie nazwy geograficzne zgodnie z polską \
tradycją; imiona i nazwiska artystów bez zmian.
- "title": polski tytuł, najwyżej {TITLE_MAX} znaków.
- "frame": tekst na ramkę, 300–{MAX_BODY} znaków, pełne zdania. Pierwsze zdanie ma najwyżej \
{FIRST_SENTENCE_MAX} znaków i samo mówi najważniejsze: co przedstawia dzieło i co w nim \
szczególne. Dalsze zdania w kolejności ważności, bo ramka przy małym miejscu ucina tekst od \
końca, całymi zdaniami.
- "medium": technika po polsku, małą literą (np. "olej na płótnie").
- "date": data po polsku (np. "ok. 1647", "1899, przemalowany do 1906").
- "artist_note": narodowość autora rzeczownikiem, jak o osobie i we właściwej płci, potem lata \
życia (np. "Holender, 1853–1890", "Brytyjczyk, 1775–1851", "Amerykanka, 1844–1926"). Nigdy \
przymiotnikiem ("holenderski"). Pusty, gdy dane tego nie mówią.
- W tekście na ramkę nie powtarzaj techniki, daty powstania ani nazwy muzeum, bo ramka drukuje \
je obok. Każde zdanie ma mówić coś o samym dziele.
- Nazwy japońskie i chińskie w polskiej transkrypcji (Fudżi, Edo, Hiroszige).
- Pomiń znaczniki HTML i wielokropki ze źródła. Sprawdź odmianę i rodzaj gramatyczny (łódź \
jest rodzaju żeńskiego, topola też)."""

TRANSLATE_SYSTEM = f"""{_RULES}
- "full": wierne, pełne tłumaczenie opisu muzeum na polski, do aplikacji. Nie skracaj i nie \
dopisuj niczego. Nigdy nie przepisuj opisu w oryginalnym języku.
- Opis muzeum bywa po angielsku, niderlandzku, niemiecku, francusku czy włosku: każdy \
tłumaczysz na polski. Wszystkie pola odpowiedzi są po polsku.
- Nie dodawaj faktów, których nie ma w danych.
- "about_work": true, gdy opis muzeum mówi o tym konkretnym dziele (co przedstawia, jak \
powstało, jego dzieje, choćby jednym zdaniem). false, gdy to tylko ogólny tekst: życiorys \
artysty, opis serii, zbioru, epoki, miejsca albo techniki, bez niczego o samym dziele. Wtedy \
pozostałe pola i tak wypełnij."""

NOTE_SYSTEM = f"""{_RULES}
- Muzeum nie podaje opisu dzieła (najwyżej krótką adnotację albo ogólny tekst o artyście), \
więc piszesz krótką notkę na podstawie danych i załączonego obrazu (to reprodukcja tego dzieła).
- "full": notka do aplikacji, 400–900 znaków.
- Notka patrzy na dzieło z jednej strony, wskazanej w pytaniu jako STYL. Pierwsze zdanie i tak \
mówi, co dzieło przedstawia, ale już z tej strony. Inne strony dzieła pojawiają się najwyżej na \
marginesie. Nie nazywaj stylu ani nie zapowiadaj, z której strony patrzysz.
- O samym dziele piszesz tylko to, co widać na obrazie albo wynika z podanych danych. Nie \
wymyślaj dat, miejsc, okoliczności powstania, zamówień, cytatów ani interpretacji tego \
konkretnego dzieła. Ogólna, pewna wiedza o temacie (legenda, postać, zwyczaj, gatunek malarski, \
miejsce) jest dozwolona, gdy styl tego wymaga; jeśli nie jesteś pewien, pomiń.
- Nie pisz o tym, czego dane nie mówią ("muzeum nie podaje…", "nie wiadomo, kim…"): po prostu \
to pomiń. Nie kończ zdaniem, które tylko powtarza autora, epokę albo technikę z danych.
- Nie zaczynaj od "Obraz przedstawia", "Obraz pokazuje" ani "Dzieło przedstawia", ani tak jak \
notki wymienione w pytaniu jako OSTATNIE POCZĄTKI: inne pierwsze słowa i inna budowa pierwszego \
zdania.
- "sources": źródła, z których faktycznie skorzystałeś."""

_FIELDS = ("title", "frame", "full", "medium", "date", "artist_note")


def schema(written: Written) -> dict[str, Any]:
    """The JSON the model answers with; a translation first says whether the
    museum's text is about the work at all (:func:`about_work`)."""
    props: dict[str, Any] = {}
    required: list[str] = []
    if written == "translation":
        props["about_work"] = {"type": "boolean"}
        required.append("about_work")
    props |= {name: {"type": "string"} for name in _FIELDS}
    required += _FIELDS
    if written == "note":
        props["sources"] = {"type": "array", "items": {"type": "string", "enum": list(SOURCES)}}
        required.append("sources")
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class Context:
    """What a question tells the model besides the item itself."""

    facts: Facts | None = None
    #: Opening paragraphs of the Wikipedia articles about the work.
    wiki_pl: str = ""
    wiki_en: str = ""


# Words a caption or a catalogue entry is made of, in the languages museums
# write in; with words under three letters, never a description's own.
_STOCK = frozenset(
    {
        "the", "and", "with", "from", "for", "this", "that", "its", "his", "her", "their",
        "are", "was", "were", "has", "had", "into", "oil", "oils", "painting", "paintings",
        "painted", "canvas", "panel", "board", "paper", "wood", "copper", "tempera",
        "watercolour", "watercolor", "gouache", "pastel", "drawing", "print", "etching",
        "engraving", "woodcut", "lithograph", "photograph", "photo", "image", "picture", "scan",
        "scanned", "high", "resolution", "file", "detail", "version", "reproduction", "copy",
        "work", "artwork", "artist", "signed", "dated", "lower", "left", "right", "museum",
        "gallery", "collection", "national", "art", "arts", "public", "domain", "gift",
        "bequest", "purchase", "purchased", "fund", "acquired", "lent", "loan", "courtesy",
        "credit", "inv", "inventory", "object", "accession", "van", "het", "een", "met", "voor",
        "die", "der", "das", "und", "mit", "von", "dem", "den", "des", "les", "une", "sur",
        "par", "avec", "pour", "del", "della", "dello", "con", "per", "una", "gli",
    }
)  # fmt: skip
_TEXT_WORD = re.compile(r"[^\W\d_]{3,}")


def _words(*texts: str) -> set[str]:
    return {w for text in texts for w in _TEXT_WORD.findall(text.casefold())}


def own_words(item: Item, text: str) -> set[str]:
    """The words of ``text`` that say more than the work's data does."""
    known = _words(
        strip_markup(item.title), item.artist, item.artist_bio, item.date_text,
        item.medium, item.classification, item.culture, item.museum, item.credit,
        item.held_by,
    )  # fmt: skip
    return _words(text) - known - _STOCK


def description(item: Item) -> str:
    """The museum's own description, as plain text; "" when it has none worth
    translating: too short, or saying little more than the title, the author
    and the date (a Commons file's one-line caption)."""
    text = strip_markup(item.description)
    if len(text) < MIN_DESCRIPTION or len(own_words(item, text)) < MIN_OWN_WORDS:
        return ""
    return text


def short_description(item: Item) -> str:
    """What the museum says when it is too little to translate: one more fact
    for a note."""
    return "" if description(item) else strip_markup(item.description)[:MAX_BODY]


def written_for(item: Item) -> Written:
    return "translation" if description(item) else "note"


def model_for(item: Item) -> str:
    return HAIKU if written_for(item) == "translation" else SONNET


def about_work(data: dict[str, Any]) -> bool:
    """Whether a translation's museum text is about the work: false when
    Haiku found only the artist's life or the like in it."""
    return data.get("about_work") is not False


def request_text(item: Item, context: Context, general: bool = False) -> str:
    """The work's data, in the same order for every work; ``general``: the
    museum's text is about something else than the work (a note is written)."""
    author = item.artist
    if item.artist_bio:
        author = f"{author} ({item.artist_bio})" if author else item.artist_bio
    lines = [
        f"Muzeum: {item.held_by or item.museum}",
        f"Tytuł (oryginał): {strip_markup(item.title)}",
        f"Autor: {author}",
        f"Data: {item.date_text}",
        f"Technika: {item.medium}",
    ]
    if item.classification:
        lines.append(f"Rodzaj: {item.classification}")
    if item.culture:
        lines.append(f"Kultura: {item.culture}")
    tags = [*item.styles, *item.subjects]
    if tags:
        lines.append(f"Tagi muzeum: {', '.join(tags)}")
    facts = context.facts
    if facts and facts.title_pl:
        lines.append(f"Polski tytuł z Wikidata: {facts.title_pl}")
    if facts and (facts.depicts_pl or facts.depicts_en):
        lines.append(f"Wikidata, co przedstawia: {', '.join(facts.depicts_pl + facts.depicts_en)}")
    if context.wiki_pl:
        lines.append(f"Wikipedia (pl): {context.wiki_pl}")
    if context.wiki_en:
        lines.append(f"Wikipedia (en): {context.wiki_en}")
    if (text := description(item)) and general:
        lines.append(
            "Tekst muzeum (ogólny, nie o tym dziele; najwyżej tło, nie streszczaj go):\n"
            + text[:WIKI_CHARS]
        )
    elif text:
        lines.append(f"Opis muzeum:\n{text}")
    elif short := short_description(item):
        lines.append(f"Krótka adnotacja muzeum (za mało na opis): {short}")
    return "DANE\n" + "\n".join(lines)


class PolishText(BaseModel):
    """One work's Polish texts, as kept and as sent to the app."""

    title: str
    frame: str
    full: str
    medium: str = ""
    date: str = ""
    artist_note: str = ""
    written: Written = "translation"
    #: For a note: what it was written from.
    sources: list[str] = Field(default_factory=list)
    #: For a note: the side it looks at the work from (:data:`STYLES`).
    style: str = ""
    #: The museum's text was not about the work: a note took its place.
    general: bool = False
    #: For a translation: whether Haiku found the museum's text to be about
    #: the work (None: kept before it was asked, ``ai.text_review``).
    about_work: bool | None = None


# Marks of a cut quote: "[...]", "(…)", and a text ending in an ellipsis.
_CUT = re.compile(r"\s*[\[(]\s*(?:\.\.\.|…)\s*[\])]")
_TRAILING = re.compile(r"\s*(?:\.\.\.|…)\s*$")


def _plain(value: Any, limit: int | None = None) -> str:
    text = _TRAILING.sub("", _CUT.sub("", strip_markup(str(value or ""))))
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:–-")
    return text


def _paragraphs(value: Any) -> str:
    """Like ``_plain``, but paragraphs stay paragraphs (the app shows them)."""
    parts = [_plain(p) for p in re.split(r"\n\s*\n", str(value or ""))]
    return "\n\n".join(p for p in parts if p)


def frame_text(text: str) -> str:
    """Leading whole sentences of ``text`` that fit ``MAX_BODY``."""
    chosen: list[str] = []
    for sentence in sentences(text):
        if sum(len(s) + 1 for s in chosen) + len(sentence) > MAX_BODY:
            break
        chosen.append(sentence)
    return " ".join(chosen)


#: Words that give a text in another language away (English, Dutch,
#: German, French, Italian, Spanish); Polish has none of them. Particles of
#: names ("van", "de", "di") are left out: Polish texts name painters.
_FOREIGN = frozenset(
    {
        "the", "and", "of", "is", "was", "were", "with", "this", "that", "which",
        "his", "her", "its", "from", "are", "has", "have", "in", "an", "it",
        "het", "een", "en", "op", "met", "zijn", "voor", "niet", "wordt", "aan",
        "bij", "uit", "naar", "dat", "deze", "ook", "staat", "werd",
        "der", "die", "das", "und", "ist", "mit", "den", "dem", "ein", "eine",
        "auf", "für", "sich", "nicht", "wird", "wurde", "auch", "einem", "einer",
        "le", "la", "les", "et", "des", "du", "une", "est", "dans", "avec",
        "pour", "sur", "qui", "par", "au", "aux", "ne", "il", "elle",
        "che", "con", "per", "del", "sono", "nel", "gli", "un", "una", "uno",
        "el", "los", "las", "y", "por", "que", "es", "se",
    }
)  # fmt: skip
#: Short Polish words found in nearly every Polish sentence.
_POLISH = frozenset(
    {
        "się", "jest", "są", "był", "była", "było", "były", "na", "nie", "że",
        "przez", "oraz", "jego", "jej", "ich", "który", "która", "które",
        "którego", "której", "którym", "do", "od", "po", "jak", "ze", "we", "w",
        "z", "dla", "przy", "pod", "nad", "tym", "tego", "także", "też", "tylko",
        "gdzie", "jako",
    }
)  # fmt: skip
_WORD = re.compile(r"[^\W\d_]+")


def untranslated(text: str) -> bool:
    """Whether ``text`` is in another language rather than Polish: a model
    sometimes copies the museum's description (English, Dutch, German...)
    instead of translating it."""
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) < 12:
        return False
    foreign = sum(w in _FOREIGN for w in words)
    polish = sum(w in _POLISH for w in words)
    return foreign >= 3 and foreign > polish


#: Museums whose own titles are Polish: theirs stay, Wikidata's label (often
#: shorter, sometimes another wording) does not take their place.
OWN_POLISH_TITLES = frozenset({"mnw", "mnk"})


def own_title_first(item: Item, facts: Facts | None) -> Facts | None:
    """``facts`` without Wikidata's title where the museum's is Polish."""
    if facts is None or not facts.title_pl or item.source not in OWN_POLISH_TITLES:
        return facts
    return replace(facts, title_pl="")


def polish_title(raw: Any, facts: Facts | None, artist: str = "") -> str:
    """The Polish title as shown: an established one from Wikidata first,
    else the model's; "" when there is none. Without the artist's name in
    front ("Tadeusz Makowski Skąpiec"), which a model copies from a Commons
    file name."""
    title = (facts.title_pl if facts and facts.title_pl else "") or _plain(raw)
    # The frame wraps three lines, then cuts.
    if not title:
        return ""
    return strip_artist(strip_language_prefix(_plain(title, TITLE_MAX + 40)), artist)


#: The title in an answer still being written: the schema puts it first, so
#: it is whole long before the texts are.
_TITLE_SO_FAR = re.compile(r'(?:^|[{,])\s*"title"\s*:\s*"((?:[^"\\]|\\.)*)"')
#: Read this far without a title: the answer is not the expected one.
_HEAD_MAX = 4000
#: Titles kept ahead of their texts, at most.
_EARLY_MAX = 500


def clean(data: dict[str, Any], item: Item, facts: Facts | None) -> PolishText | None:
    """A model's answer made safe to show; ``None`` when it is unusable."""
    written: Written = "note" if "style" in data else written_for(item)
    title = polish_title(data.get("title"), facts, item.artist)
    frame = frame_text(_plain(data.get("frame")))
    full = _paragraphs(data.get("full"))
    if untranslated(frame):
        return None
    if not full or untranslated(full):
        full = frame  # the frame's text is Polish: better than the original again
    if not title or not frame:
        return None
    gender = facts.creator_gender if facts else None
    note = artist_note(item.artist_bio, gender) if item.artist_bio else None
    if note is None:
        note = fix_note(_plain(data.get("artist_note"), SHORT_MAX), gender)
    sources = [s for s in data.get("sources") or [] if s in SOURCES] if written == "note" else []
    return PolishText(
        title=title,
        frame=frame,
        full=full,
        medium=_plain(data.get("medium"), SHORT_MAX) if item.medium else "",
        date=_plain(data.get("date"), SHORT_MAX) if item.date_text else "",
        artist_note=note,
        written=written,
        sources=sources,
        style=str(data.get("style") or "") if written == "note" else "",
        general=bool(data.get("general")) and written == "note",
        about_work=(
            data["about_work"]
            if written == "translation" and isinstance(data.get("about_work"), bool)
            else None
        ),
    )


def opening(text: str) -> str:
    """The first words of a note, as the next ones are told not to start."""
    said = sentences(text)
    words = said[0].split() if said else []
    return " ".join(words[:OPENING_WORDS]) + ("…" if len(words) > OPENING_WORDS else "")


def note_question(data_text: str, style: str, recent: list[str]) -> str:
    """A note's question: the work's data, its style and how to not start."""
    name, how = STYLES[style]
    lines = [data_text, "", f"STYL: {name}. {how}"]
    if recent:
        lines += ["", "OSTATNIE POCZĄTKI (nie zaczynaj podobnie):", *(f"„{r}”" for r in recent)]
    return "\n".join(lines)


class PlTextJob(NoteJob):
    kind = KIND
    model = HAIKU  # translations; notes ask SONNET (model_for)
    night = True
    prompt_version = PROMPT_VERSION
    typical = TRANSLATION_USAGE
    #: The title is shown on the card as soon as it is written (``early_title``).
    streams = True

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
        self._lock = threading.Lock()
        #: Answers being written, until their title is whole.
        self._heads: dict[str, str] = {}
        #: Titles written ahead of their texts.
        self._titles: dict[str, str] = {}
        #: The styles still to deal out in this round, and the last one dealt.
        self._styles: list[str] = []
        self._last_style = ""
        #: The latest notes' openings, and when they were read.
        self._recent: tuple[float, list[str]] = (0.0, [])

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = client()
        return self._http

    @staticmethod
    def applies(item: Item) -> bool:
        """Museum works shown on their own; not photos, not taken out."""
        return item.kind == ItemKind.ARTWORK and item.look is None and not item.excluded

    def wanted(self, item: Item) -> bool:
        """The owner's works; works the server pooled once shown."""
        return self.applies(item) and (not item.pooled or item.favorite or item.show_count > 0)

    def in_library(self, item: Item) -> bool:
        return self.applies(item) and not against(item, Place.LISTED)

    def fresh(self, item: Item, note: Note | None) -> bool:
        """Up to date; texts kept with an English copy of the museum's
        description (before ``clean`` caught it) are asked for once more."""
        if not super().fresh(item, note) or note is None:
            return False
        data = note.data
        if data.get("general") and "title" not in data:
            return False  # its museum text is about something else: a note is due
        return "title" not in data or not (
            untranslated(str(data.get("frame", ""))) or untranslated(str(data.get("full", "")))
        )

    def source_hash(self, item: Item) -> str:
        return text_hash(
            item.title, item.artist, item.artist_bio, item.date_text, item.medium,
            description(item),
        )  # fmt: skip

    def general(self, item: Item, note: Note | None = None) -> bool:
        """Whether the work's museum text was found to be about something
        else than the work (by its last translation, its text unchanged)."""
        if note is None:
            note = self.library.notes(KIND).get(item.id)
        return (
            note is not None
            and bool(note.data.get("general"))
            and note.source_hash == self.source_hash(item)
        )

    def written(self, item: Item) -> Written:
        """A translation of the museum's description, or a note."""
        if written_for(item) == "note" or self.general(item):
            return "note"
        return "translation"

    def estimate_items(self, items: list[Item], batch: bool = True) -> float:
        notes = sum(1 for i in items if self.written(i) == "note")
        return (
            cost(HAIKU, TRANSLATION_USAGE, batch) * (len(items) - notes)
            + cost(SONNET, NOTE_USAGE, batch) * notes
        )

    def facts(self, item: Item) -> Facts | None:
        return own_title_first(item, self.wikidata.facts(self.http, item))

    def context(self, item: Item, note: bool = False) -> Context:
        """Wikidata's facts; for a note also the Wikipedia openings."""
        facts = self.facts(item)
        if not note or facts is None:
            return Context(facts=facts)
        return Context(
            facts=facts,
            wiki_pl=wikipedia_intro(self.http, "pl", facts.wiki_pl)[:WIKI_CHARS],
            wiki_en=wikipedia_intro(self.http, "en", facts.wiki_en)[:WIKI_CHARS],
        )

    def params(self, item: Item) -> dict[str, Any]:
        with self._lock:  # asked (again): read from the start
            self._heads.pop(item.id, None)
            self._titles.pop(item.id, None)
        if self.written(item) == "translation":
            text = {"type": "text", "text": request_text(item, self.context(item))}
            return request(
                model=HAIKU,
                system=TRANSLATE_SYSTEM,
                content=[text],
                schema=schema("translation"),
                max_tokens=6000,
            )
        return self.note_params(item, general=bool(description(item)))

    def note_params(self, item: Item, general: bool = False) -> dict[str, Any]:
        """Sonnet's note, in the next style; the style is asked back in the
        answer (one value allowed), so that a night's batch keeps it too."""
        style = self.next_style()
        data_text = request_text(item, self.context(item, note=True), general=general)
        note_schema = schema("note")
        note_schema["properties"]["style"] = {"type": "string", "enum": [style]}
        note_schema["required"].append("style")
        return request(
            model=SONNET,
            system=NOTE_SYSTEM,
            content=[
                image_block(self.images, item),
                {"type": "text", "text": note_question(data_text, style, self.recent())},
            ],
            schema=note_schema,
            max_tokens=6000,
        )

    def next_style(self) -> str:
        """The next of a shuffled round of all styles, never the last one again."""
        with self._lock:
            if not self._styles:
                deal = list(STYLES)
                random.shuffle(deal)
                if deal[0] == self._last_style:
                    deal.append(deal.pop(0))
                self._styles = deal
            self._last_style = self._styles.pop(0)
            return self._last_style

    def recent(self) -> list[str]:
        """How the latest notes open (read again after a minute)."""
        with self._lock:
            at, found = self._recent
            if time.monotonic() - at < RECENT_SECONDS:
                return list(found)
        notes = [
            n
            for n in self.library.notes(KIND).values()
            if n.data.get("written") == "note" and n.data.get("full")
        ]
        notes.sort(key=lambda n: n.created_at, reverse=True)
        found = []
        for note in notes:
            said = opening(str(note.data["full"]))
            if said and said not in found:
                found.append(said)
            if len(found) >= RECENT:
                break
        with self._lock:
            self._recent = (time.monotonic(), found)
        return list(found)

    def revise(
        self, item: Item, params: dict[str, Any], answer: Answer, ask: Callable[..., Answer]
    ) -> Answer:
        """A translation of a museum text that is not about the work gives
        way to Sonnet's note, asked at once (a night's batch answer is kept
        as such and the note asked the next night: :meth:`apply`)."""
        if params["model"] != HAIKU or answer.data is None or about_work(answer.data):
            return answer
        note = ask(self.note_params(item, general=True))
        if note.data is not None:
            note.data["general"] = True
        return note

    def apply(self, item: Item, note: Note) -> None:
        """Keeps the answer cleaned: what the frame and the app show. A
        translation of a museum text that is not about the work is kept as
        only that, so that a note is asked next (:meth:`fresh`)."""
        if "style" not in note.data and not about_work(note.data):
            data: dict[str, Any] = {"general": True}
            self.library.save_note(note.model_copy(update={"data": data}))
            with self._lock:
                self._titles.pop(item.id, None)
            return
        if "style" in note.data and description(item):
            # a note in place of a museum text that is not about the work
            note = note.model_copy(update={"data": {**note.data, "general": True}})
        text = clean(note.data, item, self.facts(item))
        data = text.model_dump() if text is not None else {"failed": True}
        self.library.save_note(note.model_copy(update={"data": data}))
        with self._lock:
            self._titles.pop(item.id, None)

    def partial(self, item: Item, piece: str) -> None:
        """Picks the title out of the answer as it is written (a second or
        two in, the texts take several more), for the card to show first."""
        with self._lock:
            if item.id in self._titles:
                return
            head = self._heads.get(item.id, "") + piece
            self._heads[item.id] = head
        facts = self.facts(item)
        raw = ""
        if not (facts and facts.title_pl):
            match = _TITLE_SO_FAR.search(head)
            if match is None:
                if len(head) > _HEAD_MAX:
                    with self._lock:
                        self._titles[item.id] = ""  # none to come: stop reading
                        self._heads.pop(item.id, None)
                return
            try:
                raw = json.loads(f'"{match.group(1)}"')
            except ValueError:
                return
        title = polish_title(raw, facts, item.artist)
        with self._lock:
            self._heads.pop(item.id, None)
            if len(self._titles) > _EARLY_MAX:
                self._titles.clear()
            self._titles[item.id] = title

    def early_title(self, item_id: str) -> str | None:
        """The Polish title of texts still being written, once it is."""
        with self._lock:
            return self._titles.get(item_id) or None

    def text(self, item: Item) -> PolishText | None:
        """The item's Polish texts, if they are switched on and up to date."""
        if not self.enabled() or not self.applies(item):
            return None
        note = self.library.note(item.id, KIND)
        if not self.fresh(item, note) or note is None or "title" not in note.data:
            return None
        text = PolishText.model_validate(note.data)
        # Wikidata's title, also when it came after the texts; texts written
        # before the name was left out of titles lose it.
        title = polish_title(
            text.title, own_title_first(item, self.wikidata.known(item)), item.artist
        )
        return text if title == text.title else text.model_copy(update={"title": title})
