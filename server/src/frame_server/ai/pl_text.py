"""Polish titles and texts about works, written by Claude.

A work with a museum description gets a translation (Haiku is good at
that and cheap); a work without one gets a short note written from its
picture and what the museum and Wikidata say (Sonnet sees the picture far
better). Both give the same fields: a title, a text sized for the frame's
DESCRIPTION mode, a fuller text for the app, the medium, the date and the
author's nationality with life years. The nationality is put together from
a dictionary where the museum's bio allows it (library/nationality.py):
models keep writing "holenderski" for "Dutch".
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx
from pydantic import BaseModel, Field

from ..imaging.text import MAX_BODY, sentences
from ..library.markup import strip_language_prefix, strip_markup
from ..library.models import ItemKind, Note
from ..library.museums import client
from ..library.nationality import artist_note, fix_note
from ..library.vocabulary import set_aside
from ..library.wikidata import Facts, Wikidata, wikipedia_intro
from .client import HAIKU, SONNET, cost, image_block, request
from .jobs import NoteJob, Usage, text_hash

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .config import AiConfigStore

KIND = "pl_text"
#: Changed whenever the prompts change, so older texts are written again.
PROMPT_VERSION = "pl-1"

#: A description shorter than this ("Gift of ...") is no description.
MIN_DESCRIPTION = 80
TITLE_MAX = 80
#: The frame's first sentence is all a small space has room for.
FIRST_SENTENCE_MAX = 180
SHORT_MAX = 120
#: Wikipedia's opening paragraph, for a note.
WIKI_CHARS = 1200

Written = Literal["translation", "note"]
SOURCES = ("dane muzeum", "Wikidata", "Wikipedia", "obraz")

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
    """What a question tells the model besides the item itself."""

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
    return HAIKU if written_for(item) == "translation" else SONNET


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


def polish_title(raw: Any, facts: Facts | None) -> str:
    """The Polish title as shown: an established one from Wikidata first,
    else the model's; "" when there is none."""
    title = (facts.title_pl if facts and facts.title_pl else "") or _plain(raw)
    # The frame wraps three lines, then cuts.
    return strip_language_prefix(_plain(title, TITLE_MAX + 40)) if title else ""


#: The title in an answer still being written: the schema puts it first, so
#: it is whole long before the texts are.
_TITLE_SO_FAR = re.compile(r'(?:^|[{,])\s*"title"\s*:\s*"((?:[^"\\]|\\.)*)"')
#: Read this far without a title: the answer is not the expected one.
_HEAD_MAX = 4000
#: Titles kept ahead of their texts, at most.
_EARLY_MAX = 500


def clean(data: dict[str, Any], item: Item, facts: Facts | None) -> PolishText | None:
    """A model's answer made safe to show; ``None`` when it is unusable."""
    written = written_for(item)
    title = polish_title(data.get("title"), facts)
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
    )


class PlTextJob(NoteJob):
    kind = KIND
    model = HAIKU  # translations; notes ask SONNET (model_for)
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
        return self.applies(item) and not (item.pooled and set_aside(item))

    def fresh(self, item: Item, note: Note | None) -> bool:
        """Up to date; texts kept with an English copy of the museum's
        description (before ``clean`` caught it) are asked for once more."""
        if not super().fresh(item, note) or note is None:
            return False
        data = note.data
        return "title" not in data or not (
            untranslated(str(data.get("frame", ""))) or untranslated(str(data.get("full", "")))
        )

    def source_hash(self, item: Item) -> str:
        return text_hash(
            item.title, item.artist, item.artist_bio, item.date_text, item.medium,
            description(item),
        )  # fmt: skip

    def estimate_items(self, items: list[Item], batch: bool = True) -> float:
        notes = sum(1 for i in items if written_for(i) == "note")
        return (
            cost(HAIKU, TRANSLATION_USAGE, batch) * (len(items) - notes)
            + cost(SONNET, NOTE_USAGE, batch) * notes
        )

    def facts(self, item: Item) -> Facts | None:
        return self.wikidata.facts(self.http, item)

    def context(self, item: Item) -> Context:
        facts = self.facts(item)
        if written_for(item) == "translation" or facts is None:
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
        written = written_for(item)
        text = {"type": "text", "text": request_text(item, self.context(item))}
        if written == "translation":
            return request(
                model=HAIKU,
                system=TRANSLATE_SYSTEM,
                content=[text],
                schema=schema(written),
                max_tokens=6000,
            )
        return request(
            model=SONNET,
            system=NOTE_SYSTEM,
            content=[image_block(self.images, item), text],
            schema=schema(written),
            max_tokens=6000,
        )

    def apply(self, item: Item, note: Note) -> None:
        """Keeps the answer cleaned: what the frame and the app show."""
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
        title = polish_title(raw, facts)
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
        return PolishText.model_validate(note.data)
