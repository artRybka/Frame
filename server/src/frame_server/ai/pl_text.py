"""Polish titles and texts about works, written by Claude.

A work with a museum description gets a translation (Haiku is good at
that and cheap); a work without one gets a short note written from its
picture and what the museum and Wikidata say (Sonnet sees the picture far
better). Both give the same fields: a title, a text sized for the frame's
DESCRIPTION mode, a fuller text for the app, the medium, the date and the
author's nationality with life years. The nationality is put together from
a dictionary where the museum's bio allows it (library/nationality.py):
models keep writing "holenderski" for "Dutch".

A note is written round one of four ideas Sonnet first finds in the work
itself (the number dealt by the server, never the first, the most obvious),
in a form dealt out too: its length, how it opens and its tone
(:data:`LENGTHS`, :data:`OPENINGS`, :data:`TONES`; Mateusz 2026-11-26: "żeby
wyglądały na naprawdę pisane bez promptu"). It is told the phrases the
latest notes wore out (:func:`worn_phrases`), counted on them anew every
hour, so that a new habit is caught as it forms. A museum text that says
nothing about the work itself (the artist's life, a series, a collection)
is no description: Haiku says so while translating it, and Sonnet writes a
note instead.
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
from ..library.markup import strip_language_prefix, strip_markup, tidy_title
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
#: Not for the five styles of notes (2026-11-14) nor for their forms and
#: ideas (2026-11-26): the texts written before stay (Mateusz: "te które
#: są zostawiamy").
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
#: How many of the latest notes the worn phrases are counted on, how many
#: are named to a note, how many notes (and what share of them) a phrase is
#: in to be worn, and how long the count is kept (a night's batch asks
#: hundreds at once).
WORN_NOTES = 300
WORN = 15
WORN_MIN = 5
WORN_SHARE = 0.03
WORN_SECONDS = 3600.0
#: The ideas a note is written round, and the ones it may be dealt: never
#: the first, which is the most obvious (the trial of 2026-11-26).
IDEAS = 4
IDEA_NUMBERS = (2, 3, 4)

#: The form of a note, dealt out on three sides at once (3 × 7 × 3); each
#: a name kept with the note and what the question says. Told in words a
#: note cannot copy: the five styles before them came back in the notes'
#: own phrases ("łatwo przeoczyć", "warto spojrzeć dłużej").
LENGTHS: dict[str, str] = {
    "krotka": "krótka: 2–3 zdania, razem 180–320 znaków",
    "zwykla": "zwykła: 400–600 znaków",
    "dluzsza": "dłuższa: 700–900 znaków",
}
OPENINGS: dict[str, str] = {
    "obserwacja": "pierwsze zdanie ma kilka słów: jedna rzecz, którą widać od razu",
    "pytanie": "pierwsze zdanie to pytanie, które ten obraz stawia patrzącemu; dalsze "
    "zdania na nie odpowiadają",
    "miejsce": "zaczyna się w jednym konkretnym miejscu obrazu (róg, krawędź, tło, środek) "
    "od tego, co tam jest",
    "swiatlo": "zaczyna się od światła, pory dnia, pogody albo jednego koloru",
    "postac": "zaczyna się od jednej postaci, zwierzęcia albo rzeczy: co robi albo jak wygląda",
    "tytul": "zaczyna się od tytułu: co mówi, co obiecuje albo czego nie mówi o tym, co widać",
    "temat": "zaczyna się od tematu, legendy, zwyczaju albo miejsca, które dzieło pokazuje",
}
TONES: dict[str, str] = {
    "przewodnik": "rzeczowy przewodnik: konkret, bez ozdobników",
    "obok": "ktoś, kto stoi obok przed obrazem i pokazuje go znajomemu: prosto, "
    "bezpośrednio, może zwrócić się do czytającego",
    "malarz": "malarz, który patrzy na robotę kolegi: co i czym tu zrobiono, tylko to, "
    "co widać na reprodukcji",
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
- Najpierw w "ideas" wypisz {IDEAS} krótkie pomysły (po kilka słów), co w tym konkretnym \
dziele jest ciekawe: rzeczy widoczne na tym obrazie albo wynikające z danych, nie ogólne \
kategorie ("kompozycja", "kolorystyka"). Każdy inny.
- "full": notka do aplikacji, napisana wokół pomysłu o numerze podanym w pytaniu, w formie \
z pytania (FORMA: długość, początek, ton). Pozostałe pomysły najwyżej jednym zdaniem. Ma \
brzmieć jak tekst człowieka, który zna się na sztuce i lubi ten obraz, nie jak opis \
katalogowy: nie wyliczaj wszystkiego, co widać, tylko to, co służy pomysłowi; zdania różnej \
długości. Formy nie nazywaj ani nie zapowiadaj.
- O samym dziele piszesz tylko to, co widać na obrazie albo wynika z podanych danych. Nie \
wymyślaj dat, miejsc, okoliczności powstania, zamówień, cytatów ani interpretacji tego \
konkretnego dzieła. Ogólna, pewna wiedza o temacie (legenda, postać, zwyczaj, gatunek malarski, \
miejsce) jest dozwolona, gdy pomysł albo początek tego wymaga; jeśli nie jesteś pewien, pomiń.
- Nie pisz o tym, czego dane nie mówią ("muzeum nie podaje…", "nie wiadomo, kim…"), i nie \
asekuruj się ("choć obraz tego nie wyjaśnia"): po prostu to pomiń. Nie kończ morałem ani \
podsumowaniem ("nadaje całości…", "podkreśla…") ani zdaniem, które tylko powtarza autora, \
epokę albo technikę. Skończ, gdy powiesz swoje.
- Nie zaczynaj od "Obraz", "Dzieło", "Portret" czy "Pejzaż" z "przedstawia", "pokazuje" albo \
"ukazuje". Unikaj zwrotów: "warto spojrzeć", "warto zwrócić uwagę", "łatwo przeoczyć", \
"uwagę przyciąga", "wzrok prowadzi", "na pierwszym planie", "nadaje całości", "Autorem jest", \
ani tych, które pytanie wymienia jako ZUŻYTE.
- "sources": źródła, z których faktycznie skorzystałeś."""

_FIELDS = ("title", "frame", "full", "medium", "date", "artist_note")


def schema(written: Written) -> dict[str, Any]:
    """The JSON the model answers with; a translation first says whether the
    museum's text is about the work at all (:func:`about_work`)."""
    props: dict[str, Any] = {}
    required: list[str] = []
    if written == "note":  # first: the note is written round one of them
        props["ideas"] = {"type": "array", "items": {"type": "string"}}
        required.append("ideas")
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


def is_own(item: Item) -> bool:
    """A work of the owner's own ("Dodaj własne dzieło"): always a note, as
    of a museum work with no description (Mateusz 2026-11-16: "powinno mieć
    normalnie tworzoną notatkę"), his own note one of its facts; his title,
    date and technique stay as he wrote them."""
    return item.kind == ItemKind.OWN and item.source == "upload"


def written_for(item: Item) -> Written:
    return "translation" if description(item) and not is_own(item) else "note"


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
    if is_own(item):
        return own_request_text(item)
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


def own_request_text(item: Item) -> str:
    """A work of his own: what he wrote, nothing from Wikidata (a family
    painter's name finds someone else's works there)."""
    lines = [
        "Dzieło z domowej kolekcji właściciela ramki (nie z muzeum), sfotografowane telefonem.",
        f"Tytuł: {strip_markup(item.title)}",
        f"Autor: {item.artist}",
        f"Data: {item.date_text}",
        f"Technika: {item.medium}",
    ]
    own = item.own
    if own is not None and own.height_cm and own.width_cm:
        lines.append(f"Rozmiar: {own.height_cm:g} × {own.width_cm:g} cm (wys. × szer.)")
    if own is not None and own.origin:
        lines.append(f"Skąd w kolekcji: {own.origin}")
    if text := strip_markup(item.description)[:WIKI_CHARS]:
        lines.append(f"Notatka właściciela (fakty z niej są pewne; nie przepisuj jej):\n{text}")
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
    #: For a note: its form, "length/opening/tone/idea" (:class:`Form`;
    #: before 2026-11-26 one of five styles, "opis", "temat"…).
    style: str = ""
    #: For a note: the ideas Sonnet found in the work, one written round.
    ideas: list[str] = Field(default_factory=list)
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
    return tidy_title(strip_language_prefix(_plain(title, TITLE_MAX + 40)), artist)


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
    if is_own(item):
        # His own words stay (the model's only where he wrote none).
        data = {
            **data,
            "date": item.date_text or data.get("date"),
            "medium": item.medium or data.get("medium"),
        }
        title = strip_markup(item.title).strip()[: TITLE_MAX + 40] or title
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
        ideas=(
            [_plain(i, SHORT_MAX) for i in data.get("ideas") or [] if _plain(i)][:IDEAS]
            if written == "note"
            else []
        ),
        general=bool(data.get("general")) and written == "note",
        about_work=(
            data["about_work"]
            if written == "translation" and isinstance(data.get("about_work"), bool)
            else None
        ),
    )


@dataclass(frozen=True)
class Form:
    """How a note is written: its length, opening and tone, and the number
    of the idea it is written round."""

    length: str
    opening: str
    tone: str
    idea: int

    @property
    def name(self) -> str:
        """As kept with the note (``style``) and asked back in its answer."""
        return f"{self.length}/{self.opening}/{self.tone}/{self.idea}"


class _Deck:
    """A shuffled round of all the values, never the same twice in a row."""

    def __init__(self, values: tuple[Any, ...]) -> None:
        self.values = values
        self.left: list[Any] = []
        self.last: Any = None

    def deal(self) -> Any:
        if not self.left:
            deal = list(self.values)
            random.shuffle(deal)
            if len(deal) > 1 and deal[0] == self.last:
                deal.append(deal.pop(0))
            self.left = deal
        self.last = self.left.pop(0)
        return self.last


_NOTE_WORD = re.compile(r"[^\W\d_]+")
#: Words that make no phrase on their own: "w tym", "a na" are no habit.
_GLUE = frozenset(
    {
        "a", "albo", "ale", "aż", "bo", "obok", "niej", "nich", "niego", "by", "co",
        "czy", "dla", "do", "go", "i", "ich",
        "iż", "jak", "jego", "jej", "jest", "już", "ku", "lub", "ma", "na", "nad", "nie",
        "o", "od", "oraz", "po", "pod", "przed", "przez", "przy", "się", "są", "ta", "tak",
        "te", "tego", "tej", "ten", "to", "tu", "tym", "u", "w", "we", "z", "za", "ze", "że",
    }
)  # fmt: skip


def _phrases(text: str) -> set[str]:
    """The note's phrases of 2 to 4 words, without names (a capital in the
    middle of a sentence) and without those made of glue words alone."""
    found: set[str] = set()
    for sentence in sentences(text):
        words = _NOTE_WORD.findall(sentence)
        for n in (2, 3, 4):
            for i in range(len(words) - n + 1):
                part = words[i : i + n]
                if any(w[0].isupper() for w in part[1 if i == 0 else 0 :]):
                    continue
                low = [w.casefold() for w in part]
                if all(w in _GLUE or len(w) < 5 for w in low):
                    continue
                found.add(" ".join(low))
    return found


def worn_phrases(texts: list[str]) -> list[str]:
    """The phrases the notes keep coming back to: in at least ``WORN_MIN``
    of them and ``WORN_SHARE``, most worn first; a phrase inside one named
    already (or holding it) is the same habit and is left out."""
    counts: dict[str, int] = {}
    for text in texts:
        for phrase in _phrases(text):
            counts[phrase] = counts.get(phrase, 0) + 1
    least = max(WORN_MIN, round(WORN_SHARE * len(texts)))
    ranked = sorted(
        (p for p, c in counts.items() if c >= least),
        key=lambda p: (-counts[p], -len(p.split()), p),
    )
    chosen: list[str] = []
    for phrase in ranked:
        padded = f" {phrase} "
        if any(padded in f" {c} " or f" {c} " in padded for c in chosen):
            continue
        chosen.append(phrase)
        if len(chosen) >= WORN:
            break
    return chosen


def note_question(data_text: str, form: Form, worn: list[str]) -> str:
    """A note's question: the work's data, its form and the worn phrases."""
    lines = [
        data_text,
        "",
        "FORMA:",
        f"- długość: {LENGTHS[form.length]}",
        f"- początek: {OPENINGS[form.opening]}",
        f"- ton: {TONES[form.tone]}",
        "",
        f'Napisz notkę wokół pomysłu nr {form.idea} z "ideas".',
    ]
    if worn:
        lines += ["", "ZUŻYTE (nie używaj ani ich odmian):", ", ".join(f"„{w}”" for w in worn)]
    return "\n".join(lines)


class PlTextJob(NoteJob):
    kind = KIND
    steady = True
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
        #: The forms of notes, each side dealt in its own round.
        self._decks = (
            _Deck(tuple(LENGTHS)),
            _Deck(tuple(OPENINGS)),
            _Deck(tuple(TONES)),
            _Deck(IDEA_NUMBERS),
        )
        #: The latest notes' worn phrases, and when they were counted.
        self._worn: tuple[float, list[str]] | None = None

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = client()
        return self._http

    @staticmethod
    def applies(item: Item) -> bool:
        """Museum works shown on their own and works of his own; not photos,
        not taken out."""
        if is_own(item):
            return not item.excluded
        return item.kind == ItemKind.ARTWORK and item.look is None and not item.excluded

    def wanted(self, item: Item) -> bool:
        """The owner's works; works the server pooled once shown."""
        return self.applies(item) and (not item.pooled or item.favorite or item.show_count > 0)

    def in_library(self, item: Item) -> bool:
        return self.applies(item) and not against(item, Place.LISTED)

    def fresh(self, item: Item, note: Note | None) -> bool:
        """Up to date; texts kept with an English copy of the museum's
        description (before ``clean`` caught it) are asked for once more."""
        if note is not None and note.data.get("by_owner"):
            # Mended by the owner ("Do sprawdzenia"): kept while the work's
            # facts stay, whatever prompt writes the others.
            return note.source_hash == self.source_hash(item)
        if not super().fresh(item, note) or note is None:
            return False
        data = note.data
        if data.get("general") and "title" not in data:
            return False  # its museum text is about something else: a note is due
        return "title" not in data or not (
            untranslated(str(data.get("frame", ""))) or untranslated(str(data.get("full", "")))
        )

    def source_hash(self, item: Item) -> str:
        if is_own(item):  # his note is a fact, however short; what he wrote of it too
            return text_hash(own_request_text(item))
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
        if is_own(item):
            return None
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
        return self.note_params(item, general=bool(description(item)) and not is_own(item))

    def note_params(self, item: Item, general: bool = False) -> dict[str, Any]:
        """Sonnet's note, in the next form; the form is asked back in the
        answer (one value allowed), so that a night's batch keeps it too."""
        form = self.next_form()
        data_text = request_text(item, self.context(item, note=True), general=general)
        note_schema = schema("note")
        note_schema["properties"]["style"] = {"type": "string", "enum": [form.name]}
        note_schema["required"].append("style")
        return request(
            model=SONNET,
            system=NOTE_SYSTEM,
            content=[
                image_block(self.images, item),
                {"type": "text", "text": note_question(data_text, form, self.worn())},
            ],
            schema=note_schema,
            max_tokens=6000,
        )

    def next_form(self) -> Form:
        """The next form: each side the next of its own shuffled round."""
        with self._lock:
            length, opening, tone, idea = (deck.deal() for deck in self._decks)
        return Form(length, opening, tone, idea)

    def worn(self) -> list[str]:
        """The phrases the latest notes wore out (counted again after an hour)."""
        with self._lock:
            if self._worn is not None and time.monotonic() - self._worn[0] < WORN_SECONDS:
                return list(self._worn[1])
        notes = [
            n
            for n in self.library.notes(KIND).values()
            if n.data.get("written") == "note" and n.data.get("full")
        ]
        notes.sort(key=lambda n: n.created_at, reverse=True)
        found = worn_phrases([str(n.data["full"]) for n in notes[:WORN_NOTES]])
        with self._lock:
            self._worn = (time.monotonic(), found)
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
        if "style" in note.data and description(item) and not is_own(item):
            # a note in place of a museum text that is not about the work
            note = note.model_copy(update={"data": {**note.data, "general": True}})
        text = clean(note.data, item, self.facts(item))
        data = text.model_dump() if text is not None else {"failed": True}
        self.library.save_note(note.model_copy(update={"data": data}))
        with self._lock:
            self._titles.pop(item.id, None)

    def forget_title(self, item_id: str) -> None:
        """The title picked out of an answer being written, dropped: the
        owner set the Polish title himself ("Do sprawdzenia" → "Popraw")."""
        with self._lock:
            self._titles.pop(item_id, None)

    def partial(self, item: Item, piece: str) -> None:
        """Picks the title out of the answer as it is written (a second or
        two in, the texts take several more), for the card to show first."""
        with self._lock:
            if item.id in self._titles:
                return
            if is_own(item) and item.title.strip():  # his title, not the model's
                self._titles[item.id] = strip_markup(item.title).strip()
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
        if is_own(item):
            return text
        # Wikidata's title, also when it came after the texts; texts written
        # before the name was left out of titles lose it.
        title = polish_title(
            text.title, own_title_first(item, self.wikidata.known(item)), item.artist
        )
        return text if title == text.title else text.model_copy(update={"title": title})
