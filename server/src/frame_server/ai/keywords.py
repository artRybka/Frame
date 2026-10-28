"""Keywords: what a picture shows, in words the library can be searched by.

Claude Haiku looks at the thumbnail with what the museum (or the photo)
says about it and answers in a fixed schema: subjects from the vocabulary
(``subject:sea``...), concrete words in English and Polish, the season, the
time of day, how many people and a word or two for the mood. They go onto
the item (``Item.keywords``, ``Item.terms``), so smart playlists, the
playlist editor and the library's search find photos and sparsely described
works by what they show.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..library.models import ItemKind, Note
from ..library.vocabulary import TERMS, set_aside
from .client import HAIKU, image_block, request
from .jobs import NoteJob, text_hash

if TYPE_CHECKING:
    from ..library import Item

KIND = "keywords"
PROMPT_VERSION = "kw-1"
#: Museum text sent along: enough to name a saint or a place.
DESCRIPTION_CHARS = 600
MAX_TAGS = 12
MAX_SUBJECTS = 4
MAX_MOOD = 2

SUBJECTS = [t for t in TERMS if t.kind == "subject"]
SEASONS = {
    "winter": ("winter", "zima"),
    "spring": ("spring", "wiosna"),
    "summer": ("summer", "lato"),
    "autumn": ("autumn", "jesień"),
}
TIMES = {
    "day": ("day", "dzień"),
    "dusk": ("dusk", "zmierzch"),
    "night": ("night", "noc"),
}
#: What a season or a time of day adds to the subjects.
IMPLIED = {"winter": "subject:winter", "night": "subject:night"}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subjects": {
            "type": "array",
            "items": {"type": "string", "enum": [t.key for t in SUBJECTS]},
        },
        "tags_en": {"type": "array", "items": {"type": "string"}},
        "tags_pl": {"type": "array", "items": {"type": "string"}},
        "season": {"type": "string", "enum": [*SEASONS, "unknown"]},
        "time_of_day": {"type": "string", "enum": [*TIMES, "unknown"]},
        "people": {"type": "string", "enum": ["none", "one", "few", "crowd"]},
        "mood_pl": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["subjects", "tags_en", "tags_pl", "season", "time_of_day", "people", "mood_pl"],
    "additionalProperties": False,
}


def _subject_line(term: Any) -> str:
    words = ", ".join(w.rstrip("*") for w in term.words[:4])
    return f"- {term.key}: {term.name} ({words})"


SYSTEM = """You tag pictures in the library of a home art frame, so that its owner can find \
them by what they show. You get one picture, a museum artwork or one of the owner's photos, \
with what is known about it. Answer with the JSON the schema asks for, nothing else.

Rules:
- Describe only what is visible in the picture. The title and the museum's text may help you \
name what you see (a saint, a myth, a city, a plant), but never add what you cannot see.
- subjects: up to 4 keys from the list below that clearly fit the picture; an empty list when \
none does.
- tags_en: 5 to 12 concrete English nouns or short noun phrases in lower case, most important \
first: things, animals, plants, places, activities, kinds of scene. No colours, no styles or \
techniques, no artist names, no words like "painting", "artwork" or "photo".
- tags_pl: the same tags in Polish, in the nominative, lower case, in the same order.
- season and time_of_day: only when the picture shows them, otherwise "unknown".
- people: how many people are visible.
- mood_pl: at most 2 Polish words for the picture's mood (e.g. "spokój", "melancholia"), or \
an empty list.
- Never name or identify real people in photos; say "woman", "child" or "family" instead.

Subjects:
""" + "\n".join(_subject_line(t) for t in SUBJECTS)


def is_photo(item: Item) -> bool:
    return item.kind in (ItemKind.PHOTO, ItemKind.OWN)


def _facts(item: Item) -> str:
    """What is known about the item, as the question's text."""
    lines = [f"Kind: {'photo' if is_photo(item) else 'artwork'}"]
    if item.title:
        lines.append(f"Title: {item.title}")
    if item.artist and not is_photo(item):
        lines.append(f"Artist: {item.artist}")
    if item.date_text:
        lines.append(f"Date: {item.date_text}")
    if item.classification or item.medium:
        lines.append(f"Object: {', '.join(p for p in (item.classification, item.medium) if p)}")
    if item.subjects:
        lines.append(f"Museum subjects: {', '.join(item.subjects[:15])}")
    if item.photo and item.photo.caption:
        lines.append(f"Caption: {item.photo.caption}")
    if item.description:
        lines.append(f"Museum text: {item.description[:DESCRIPTION_CHARS]}")
    return "\n".join(lines)


def _clean(values: Any, limit: int) -> list[str]:
    out: list[str] = []
    for value in values if isinstance(values, list) else []:
        word = str(value).strip().lower()
        if word and word not in out:
            out.append(word)
    return out[:limit]


def words_and_terms(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The item's searchable words and vocabulary terms from an answer."""
    known = {t.key: t for t in SUBJECTS}
    terms = [k for k in _clean(data.get("subjects"), MAX_SUBJECTS) if k in known]
    words = _clean(data.get("tags_en"), MAX_TAGS) + _clean(data.get("tags_pl"), MAX_TAGS)
    words += _clean(data.get("mood_pl"), MAX_MOOD)
    for value, names in ((data.get("season"), SEASONS), (data.get("time_of_day"), TIMES)):
        if value in names:
            words += names[value]
            if value in IMPLIED and IMPLIED[value] not in terms:
                terms.append(IMPLIED[value])
    words += [known[k].name.lower() for k in terms]  # Polish names: "morze", "zima i śnieg"
    return list(dict.fromkeys(words)), terms


def polish_words(data: dict[str, Any]) -> list[str]:
    """What the card shows: the Polish tags and the mood."""
    words = _clean(data.get("tags_pl"), MAX_TAGS) + _clean(data.get("mood_pl"), MAX_MOOD)
    return list(dict.fromkeys(words))


class KeywordsJob(NoteJob):
    kind = KIND
    model = HAIKU
    prompt_version = PROMPT_VERSION

    def _switched_on(self, item: Item) -> bool:
        if item.look is not None or item.excluded:  # sent once, or taken out
            return False
        config = self.config.config
        return config.keywords_photos if is_photo(item) else config.keywords_artworks

    def wanted(self, item: Item) -> bool:
        """The owner's photos and works; works the server pooled once shown."""
        if not self._switched_on(item):
            return False
        return is_photo(item) or not item.pooled or item.favorite or item.show_count > 0

    def in_library(self, item: Item) -> bool:
        """Everything the library shows, pooled works too."""
        return self._switched_on(item) and not (item.pooled and set_aside(item))

    def source_hash(self, item: Item) -> str:
        return text_hash(_facts(item), item.thumb_url)

    def params(self, item: Item) -> dict[str, Any]:
        content = [image_block(self.images, item), {"type": "text", "text": _facts(item)}]
        return request(model=self.model, system=SYSTEM, content=content, schema=SCHEMA)

    def apply(self, item: Item, note: Note) -> None:
        keywords, terms = words_and_terms(note.data)
        self.library.update(item.id, keywords=keywords, terms=terms)
