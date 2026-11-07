"""The museum's own words on a work's card, in Polish.

Museums describe their works in their own language: the kind of object
("Painting"), where it comes from ("Italy", "French"), its styles and
subjects ("18th Century", "portraits: male subject", "pilgrimages"). The
card shows them beside the model's keywords, so they are said in Polish:
the common kinds and places from the table below at once, the rest asked of
Haiku once per label and remembered (the same few thousand labels come back
on every card). Without a key, or with the Polish texts switched off, the
labels the table does not know stay as the museum wrote them.

The museum's styles and subjects that only repeat a keyword ("boys" beside
"chłopiec") are left out: :func:`leftovers`.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_all
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..library.vocabulary import fold
from .client import HAIKU, request

if TYPE_CHECKING:
    from ..library import Item, Library
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "museum_words"
STATE_KEY = "museum_words"
#: Labels remembered (in the library's state, so a restart asks nothing again).
REMEMBERED = 20000
#: Longer texts are not labels: left as they are.
MAX_CHARS = 80
#: Labels in one question at most.
PER_QUESTION = 40
#: How many of the museum's styles and subjects a card asks for.
MAX_LABELS = 24
#: Two words sharing their first letters this long are taken for one
#: ("pielgrzym", "pielgrzymka"); shorter words must be equal.
SAME_STEM = 6

#: Kinds of object museums name most often.
KINDS = {
    "painting": "obraz",
    "paintings": "obraz",
    "oil painting": "obraz olejny",
    "drawing": "rysunek",
    "drawings": "rysunek",
    "drawing and watercolor": "rysunek i akwarela",
    "drawings and watercolors": "rysunek i akwarela",
    "watercolor": "akwarela",
    "watercolour": "akwarela",
    "pastel": "pastel",
    "print": "grafika",
    "prints": "grafika",
    "woodblock print": "drzeworyt",
    "etching": "akwaforta",
    "engraving": "miedzioryt",
    "lithograph": "litografia",
    "photograph": "fotografia",
    "photographs": "fotografia",
    "photography": "fotografia",
    "sculpture": "rzeźba",
    "sculptures": "rzeźba",
    "miniature": "miniatura",
    "manuscript": "rękopis",
    "manuscripts": "rękopis",
    "illuminated manuscript": "iluminowany rękopis",
    "poster": "plakat",
    "posters": "plakat",
    "book": "książka",
    "books": "książka",
    "map": "mapa",
    "fresco": "fresk",
    "tapestry": "tapiseria",
    "textile": "tkanina",
    "textiles": "tkanina",
    "ceramics": "ceramika",
    "ceramic": "ceramika",
    "vessel": "naczynie",
    "vase": "waza",
    "icon": "ikona",
    "altarpiece": "ołtarz",
    "screen": "parawan",
    "folding screen": "parawan",
    "hanging scroll": "zwój wiszący",
    "handscroll": "zwój poziomy",
    "album leaf": "karta z albumu",
    "decorative arts": "rzemiosło artystyczne",
}

#: Countries, in English and as the adjectives museums use for a culture.
PLACES = {
    "Polska": ("Poland", "Polish"),
    "Włochy": ("Italy", "Italian"),
    "Francja": ("France", "French"),
    "Niemcy": ("Germany", "German"),
    "Holandia": ("Netherlands", "The Netherlands", "Holland", "Dutch"),
    "Flandria": ("Flanders", "Flemish"),
    "Belgia": ("Belgium", "Belgian"),
    "Hiszpania": ("Spain", "Spanish"),
    "Portugalia": ("Portugal", "Portuguese"),
    "Anglia": ("England", "English"),
    "Wielka Brytania": ("United Kingdom", "Great Britain", "Britain", "British"),
    "Szkocja": ("Scotland", "Scottish"),
    "Irlandia": ("Ireland", "Irish"),
    "Walia": ("Wales", "Welsh"),
    "Stany Zjednoczone": ("United States", "United States of America", "USA", "American"),
    "Kanada": ("Canada", "Canadian"),
    "Meksyk": ("Mexico", "Mexican"),
    "Austria": ("Austria", "Austrian"),
    "Szwajcaria": ("Switzerland", "Swiss"),
    "Czechy": ("Czech Republic", "Czechia", "Bohemia", "Czech", "Bohemian"),
    "Węgry": ("Hungary", "Hungarian"),
    "Dania": ("Denmark", "Danish"),
    "Szwecja": ("Sweden", "Swedish"),
    "Norwegia": ("Norway", "Norwegian"),
    "Finlandia": ("Finland", "Finnish"),
    "Rosja": ("Russia", "Russian"),
    "Ukraina": ("Ukraine", "Ukrainian"),
    "Grecja": ("Greece", "Greek"),
    "Turcja": ("Turkey", "Türkiye", "Turkish", "Ottoman"),
    "Egipt": ("Egypt", "Egyptian"),
    "Iran": ("Iran", "Persia", "Iranian", "Persian"),
    "Irak": ("Iraq",),
    "Indie": ("India", "Indian"),
    "Chiny": ("China", "Chinese"),
    "Japonia": ("Japan", "Japanese"),
    "Korea": ("Korea", "Korean"),
    "Tajlandia": ("Thailand", "Thai"),
    "Indonezja": ("Indonesia", "Indonesian"),
    "Australia": ("Australia", "Australian"),
    "Brazylia": ("Brazil", "Brazilian"),
    "Argentyna": ("Argentina", "Argentinian"),
    "Peru": ("Peru", "Peruvian"),
    "Rumunia": ("Romania", "Romanian"),
    "Chorwacja": ("Croatia", "Croatian"),
    "Litwa": ("Lithuania", "Lithuanian"),
    "Łotwa": ("Latvia", "Latvian"),
    "Estonia": ("Estonia", "Estonian"),
    "Słowacja": ("Slovakia", "Slovak"),
    "Słowenia": ("Slovenia", "Slovenian"),
    "Serbia": ("Serbia", "Serbian"),
    "Bułgaria": ("Bulgaria", "Bulgarian"),
    "Izrael": ("Israel", "Israeli"),
    "Wenecja": ("Venice", "Venetian"),
    "Florencja": ("Florence", "Florentine"),
    "Rzym": ("Rome",),
    "Paryż": ("Paris",),
    "Londyn": ("London",),
}

#: What the table knows, folded English -> Polish.
KNOWN: dict[str, str] = {
    **{fold(en): pl for en, pl in KINDS.items()},
    **{fold(name): pl for pl, names in PLACES.items() for name in names},
}

SYSTEM = """\
You translate the labels museums give their works into Polish, for the card \
of a work in a Polish art app. A label is a kind of object ("Painting", \
"Woodblock print"), a place or culture ("Italy", "Flemish", "Edo period, Japan"), \
a style or period ("18th Century", "Impressionism") or a subject ("portraits: \
male subject", "pilgrimages", "red (color)").

For each label give "pl": the Polish a museum catalogue would use, short:
- subjects and kinds of object: a noun or short noun phrase in the nominative \
singular, lower case ("boys" -> "chłopiec", "pilgrimages" -> "pielgrzymka", \
"portraits: male subject" -> "portret męski", "red (color)" -> "czerwień", \
"Painting" -> "obraz");
- places: the Polish name of the country or city, capitalised ("Italy" -> \
"Włochy", "Edo period, Japan" -> "Japonia, okres Edo"); a culture's adjective \
as its country ("Flemish" -> "Flandria");
- centuries in Roman numerals ("18th Century" -> "XVIII wiek"), styles and \
periods as Polish art history names them ("Impressionism" -> "impresjonizm");
- names of people stay as they are; a label already in Polish stays as it is.
Give every label once, in the order given, with "en" repeating it exactly.
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"en": {"type": "string"}, "pl": {"type": "string"}},
                "required": ["en", "pl"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}


def _key(text: str) -> str:
    return fold(" ".join(text.split()))


def _tidy(text: str) -> str:
    return " ".join(str(text).split()).strip(" .;,")


@dataclass(frozen=True)
class Labels:
    """A work's labels its card shows, tidied."""

    kind: str
    culture: str
    #: Styles, then subjects.
    tags: list[str]

    @property
    def all(self) -> list[str]:
        return [t for t in dict.fromkeys([self.kind, self.culture, *self.tags]) if t]


def museum_labels(item: Item) -> Labels:
    """The labels of ``item``: kind, place, styles and subjects."""
    tags = (_tidy(t) for t in [*item.styles, *item.subjects][:MAX_LABELS])
    return Labels(
        kind=_tidy(item.classification),
        culture=_tidy(item.culture),
        tags=[t for t in dict.fromkeys(tags) if t],
    )


def _stems(text: str) -> list[str]:
    return [w for w in fold(text).replace("-", " ").split() if w]


def _same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < SAME_STEM:
        return False
    return a[:SAME_STEM] == b[:SAME_STEM]


def repeats(tag: str, words: Iterable[str]) -> bool:
    """Whether ``tag`` says nothing more than one of ``words``: the same
    word or phrase, or some of the words of a phrase ("kapelusz" beside
    "szeroki kapelusz"), maybe with another ending ("pielgrzymka" beside
    "pielgrzym")."""
    mine = _stems(tag)
    if not mine:
        return True
    for word in words:
        theirs = _stems(word)
        if theirs and all(any(_same_word(m, t) for t in theirs) for m in mine):
            return True
    return False


def leftovers(tags: Iterable[str], words: Iterable[str]) -> list[str]:
    """``tags`` without those that repeat ``words`` or a fuller tag
    ("portret" beside "portret męski")."""
    words = list(words)
    kept: list[str] = []
    for tag in (_tidy(t) for t in tags):
        if tag and not repeats(tag, words) and not repeats(tag, kept):
            kept.append(tag)
    return [tag for i, tag in enumerate(kept) if not repeats(tag, kept[i + 1 :])]


class MuseumWords:
    def __init__(self, library: Library, claude: Claude, config: AiConfigStore) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        self._lock = threading.Lock()
        self._asking: dict[str, Future[None]] = {}
        self._pool = ThreadPoolExecutor(2, thread_name_prefix="museum-words")
        self._known: OrderedDict[str, str] = OrderedDict(library.get_state(STATE_KEY, {}) or {})

    def known(self, label: str) -> str | None:
        """The Polish of ``label`` if the table or an earlier answer has it."""
        key = _key(label)
        if key in KNOWN:
            return KNOWN[key]
        with self._lock:
            return self._known.get(key)

    def polish(self, labels: Iterable[str], wait: float = 0.0) -> tuple[dict[str, str], bool]:
        """Each of ``labels`` in Polish (as it was when nobody knows it), and
        whether some are still being asked. Waits at most ``wait`` seconds."""
        labels = [t for t in dict.fromkeys(_tidy(x) for x in labels) if t]
        asking = self.ask(labels)
        if asking and wait > 0:
            wait_all(asking, timeout=wait)
        found = {label: self.known(label) or label for label in labels}
        return found, any(not f.done() for f in asking)

    def ask(self, labels: Iterable[str]) -> list[Future[None]]:
        """Asks the model for the labels nobody knows yet; the questions
        under way for them."""
        if not self.config.enabled("pl_text"):
            return []
        new: list[str] = []
        asking: set[Future[None]] = set()
        with self._lock:
            for label in labels:
                key = _key(label)
                if not key or len(label) > MAX_CHARS or key in KNOWN or key in self._known:
                    continue
                if key in self._asking:
                    asking.add(self._asking[key])
                elif label not in new:
                    new.append(label)
            for start in range(0, len(new), PER_QUESTION):
                part = new[start : start + PER_QUESTION]
                future = self._pool.submit(self._translate, part)
                for label in part:
                    self._asking[_key(label)] = future
                asking.add(future)
        return list(asking)

    def _translate(self, labels: list[str]) -> None:
        try:
            self._answer(labels)
        except Exception as err:
            log.warning("translating museum labels failed: %s", err)
        finally:
            with self._lock:
                for label in labels:
                    self._asking.pop(_key(label), None)

    def _answer(self, labels: list[str]) -> None:
        params = request(
            model=HAIKU,
            system=SYSTEM,
            content=[{"type": "text", "text": "\n".join(labels)}],
            schema=SCHEMA,
            max_tokens=2000,
        )
        data = self.claude.ask(KIND, params).data or {}
        wanted = {_key(label) for label in labels}
        found: dict[str, str] = {}
        for pair in data.get("labels") or []:
            if not isinstance(pair, dict):
                continue
            key = _key(str(pair.get("en") or ""))
            polish = _tidy(pair.get("pl") or "")
            if key in wanted and polish and len(polish) <= MAX_CHARS:
                found[key] = polish
        if not found:
            return
        with self._lock:
            for key, polish in found.items():
                self._known[key] = polish
                self._known.move_to_end(key)
            while len(self._known) > REMEMBERED:
                self._known.popitem(last=False)
            saved = dict(self._known)
        self.library.set_state(STATE_KEY, saved)
        log.info("museum labels in Polish: %d of %d", len(found), len(labels))
