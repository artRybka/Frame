"""Polish titles and texts about works, written by a language model.

A work with a museum description gets a translation (a cheap model is good
at that); a work without one gets a short note written from its picture and
what the museum and Wikidata say (a stronger model sees the picture far
better). Both give the same fields: a title, a text sized for the frame's
DESCRIPTION mode, a fuller text for the app, the medium and the date.

This module builds the requests and checks the answers; sending them and
keeping the results is someone else's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from ..imaging.text import MAX_BODY, sentences
from .markup import strip_markup
from .models import Item
from .nationality import artist_note, fix_note
from .wikidata import Facts

#: Bumped whenever the prompts change, so older texts are written again.
PROMPT_VERSION = 1

TRANSLATE_MODEL = "claude-haiku-5-5"
NOTE_MODEL = "claude-sonnet-5-5"

#: A description shorter than this ("Gift of ...") is no description.
MIN_DESCRIPTION = 80
TITLE_MAX = 80
#: The frame's first sentence is all a small space has room for.
FIRST_SENTENCE_MAX = 180
SHORT_MAX = 120

Written = Literal["translation", "note"]
SOURCES = ("dane muzeum", "Wikidata", "Wikipedia", "obraz")

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
- "full": wierne, pełne tłumaczenie opisu muzeum, do aplikacji. Nie skracaj i nie dopisuj \
niczego.
- Nie dodawaj faktów, których nie ma w danych."""

NOTE_SYSTEM = f"""{_RULES}
- Muzeum nie podaje opisu dzieła, więc piszesz krótką notkę na podstawie danych i załączonego \
obrazu (to reprodukcja tego dzieła).
- "full": notka do aplikacji, 400–900 znaków.
- Opisuj tylko to, co widać na obrazie, albo to, co wynika z podanych danych. Nie wymyślaj dat, \
miejsc, okoliczności powstania, cytatów ani interpretacji spoza tych źródeł. Jeśli czegoś nie \
wiesz, pomiń to.
- "sources": źródła, z których faktycznie skorzystałeś."""

_FIELDS = ("title", "frame", "full", "medium", "date", "artist_note")


def schema(written: Written) -> dict[str, Any]:
    """The JSON the model answers with."""
    props: dict[str, Any] = {name: {"type": "string"} for name in _FIELDS}
    required = list(_FIELDS)
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
    """What a request tells the model besides the item itself."""

    facts: Facts | None = None
    #: Opening paragraphs of the Wikipedia articles about the work.
    wiki_pl: str = ""
    wiki_en: str = ""


def description(item: Item) -> str:
    """The museum's own description, as plain text; "" when it has none worth
    translating."""
    text = strip_markup(item.description)
    return text if len(text) >= MIN_DESCRIPTION else ""


def written_for(item: Item) -> Written:
    return "translation" if description(item) else "note"


def model_for(item: Item) -> str:
    return TRANSLATE_MODEL if written_for(item) == "translation" else NOTE_MODEL


def system_for(item: Item) -> str:
    return TRANSLATE_SYSTEM if written_for(item) == "translation" else NOTE_SYSTEM


def request_text(item: Item, context: Context) -> str:
    """The work's data, in the same order for every work."""
    author = item.artist
    if item.artist_bio:
        author = f"{author} ({item.artist_bio})" if author else item.artist_bio
    lines = [
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
    if text := description(item):
        lines.append(f"Opis muzeum:\n{text}")
    return "DANE\n" + "\n".join(lines)


@dataclass(frozen=True)
class PolishText:
    """One work's Polish texts, as kept and as sent to the app."""

    title: str
    frame: str
    full: str
    medium: str = ""
    date: str = ""
    artist_note: str = ""
    written: Written = "translation"
    #: For a note: what it was written from.
    sources: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "frame": self.frame,
            "full": self.full,
            "medium": self.medium,
            "date": self.date,
            "artist_note": self.artist_note,
            "written": self.written,
            "sources": list(self.sources),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PolishText:
        written: Written = "note" if data.get("written") == "note" else "translation"
        return cls(
            title=str(data.get("title") or ""),
            frame=str(data.get("frame") or ""),
            full=str(data.get("full") or ""),
            medium=str(data.get("medium") or ""),
            date=str(data.get("date") or ""),
            artist_note=str(data.get("artist_note") or ""),
            written=written,
            sources=[str(s) for s in data.get("sources") or []],
        )


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


def clean(data: dict[str, Any], item: Item, context: Context) -> PolishText | None:
    """A model's answer made safe to show; ``None`` when it is unusable."""
    written = written_for(item)
    facts = context.facts
    title = (facts.title_pl if facts and facts.title_pl else "") or _plain(data.get("title"))
    frame = frame_text(_plain(data.get("frame")))
    full = _paragraphs(data.get("full")) or frame
    if not title or not frame:
        return None
    gender = facts.creator_gender if facts else None
    note = artist_note(item.artist_bio, gender) if item.artist_bio else None
    if note is None:
        note = fix_note(_plain(data.get("artist_note"), SHORT_MAX), gender)
    sources = [s for s in data.get("sources") or [] if s in SOURCES] if written == "note" else []
    return PolishText(
        title=_plain(title, TITLE_MAX + 40),  # the frame wraps three lines, then cuts
        frame=frame,
        full=full,
        medium=_plain(data.get("medium"), SHORT_MAX) if item.medium else "",
        date=_plain(data.get("date"), SHORT_MAX) if item.date_text else "",
        artist_note=note,
        written=written,
        sources=sources,
    )
