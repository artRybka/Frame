"""The cultural circle a work comes from: Europe and the West, East Asia,
South Asia, the Islamic world and so on, for "Inni w tym samym czasie" to
show what was made elsewhere in the world at the time, not only in the
next country (Mateusz 2026-11-06: "przy twórcy europejskim także coś z
Azji").

Told by what the museums say about the author ("Japanese, 1760–1849"), the
work's culture or place ("Iran", "India (Rajasthan)", "Japonia") and its
styles ("Edo period", "Qing dynasty"); never by the title or description,
which talk of anything ("The Japanese Bridge", Van Gogh copying Hiroshige).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from .models import Item
from .vocabulary import fold

Circle = Literal[
    "west",
    "latin-america",
    "east-asia",
    "south-asia",
    "southeast-asia",
    "islamic",
    "africa",
    "native-america",
    "oceania",
]

_WORDS: dict[Circle, tuple[str, ...]] = {
    # Europe with the Americas, Australia and Russia of European descent:
    # one circle, so that a Frenchman's "elsewhere" is not Boston.
    "west": (
        "american", "united states", "usa", "canadian", "canada", "australian", "australia",
        "new zealander", "european", "europe",
        "austrian", "austria", "bavarian", "belgian", "belgium", "bohemian", "bohemia",
        "british", "britain", "england", "english", "scottish", "scotland", "welsh", "wales",
        "irish", "ireland", "bulgarian", "bulgaria", "croatian", "croatia", "czech",
        "danish", "denmark", "dutch", "netherlands", "netherlandish", "holland", "flemish",
        "flanders", "estonian", "estonia", "finnish", "finland", "french", "france",
        "german", "germany", "prussian", "greek", "greece", "hungarian", "hungary",
        "icelandic", "iceland", "italian", "italy", "florentine", "venetian", "venice",
        "rome", "roman", "latvian", "latvia", "lithuanian", "lithuania", "norwegian",
        "norway", "polish", "poland", "portuguese", "portugal", "romanian", "romania",
        "russian", "russia", "serbian", "serbia", "slovak", "slovakia", "slovenian",
        "slovenia", "spanish", "spain", "swedish", "sweden", "swiss", "switzerland",
        "ukrainian", "ukraine", "armenian", "georgian", "byzantine", "catalan",
        # Polish, as the Polish museums and our own adjectives write it
        "polska", "polski", "francja", "francuski", "niemcy", "niemiecki", "wlochy",
        "wloski", "holandia", "holenderski", "anglia", "angielski", "brytyjski", "austria",
        "austriacki", "rosja", "rosyjski", "hiszpania", "hiszpanski", "amerykanski",
        "czechy", "czeski", "belgia", "belgijski", "flamandzki", "wegry", "wegierski",
        "litwa", "litewski", "ukraina", "ukrainski", "szwecja", "szwedzki", "dania", "dunski",
        "norwegia", "norweski", "szwajcaria", "szwajcarski", "europa",
    ),
    "latin-america": (
        "mexican", "mexico", "brazilian", "brazil", "argentine", "argentinian", "argentina",
        "chilean", "chile", "colombian", "colombia", "cuban", "cuba", "peruvian", "venezuelan",
        "venezuela", "uruguayan", "uruguay", "latin american", "meksyk", "meksykanski",
        "brazylia", "brazylijski", "argentynski", "kubanski",
    ),
    "east-asia": (
        "japanese", "japan", "chinese", "china", "korean", "korea", "tibetan", "tibet",
        "mongolian", "mongolia", "edo", "meiji", "taisho", "showa", "momoyama", "muromachi",
        "kamakura", "heian", "ukiyo e", "ukiyoe", "shin hanga", "ming", "qing", "yuan",
        "song dynasty", "tang dynasty", "joseon", "goryeo",
        "japonia", "japonski", "chiny", "chinski", "korea", "koreanski", "tybet", "tybetanski",
    ),
    "south-asia": (
        "indian", "india", "pakistani", "pakistan", "bangladesh", "nepalese", "nepali",
        "nepal", "sri lanka", "sri lankan", "mughal", "rajput", "rajasthan", "pahari",
        "deccan", "deccani", "bengal", "punjab", "kangra", "mewar", "bundi", "kota",
        "indie", "indyjski", "nepalski",
    ),
    "southeast-asia": (
        "thai", "thailand", "siam", "vietnamese", "vietnam", "burmese", "burma", "myanmar",
        "cambodian", "cambodia", "khmer", "indonesian", "indonesia", "java", "javanese",
        "bali", "balinese", "philippine", "philippines", "filipino", "laos", "malay",
        "tajski", "wietnamski", "indonezyjski",
    ),
    "islamic": (
        "persian", "persia", "iranian", "iran", "ottoman", "turkish", "turkey", "anatolia",
        "safavid", "qajar", "timurid", "islamic", "arab", "arabic", "syrian", "syria",
        "iraqi", "iraq", "egyptian", "egypt", "mamluk", "moroccan", "morocco", "uzbek",
        "bukhara", "afghan", "afghanistan", "herat", "tabriz", "isfahan", "shiraz",
        "persja", "perski", "iranski", "turcja", "turecki", "osmanski", "egipt", "egipski",
    ),
    "africa": (
        "african", "africa", "nigerian", "nigeria", "yoruba", "benin", "ghanaian", "ghana",
        "ethiopian", "ethiopia", "congolese", "congo", "kenyan", "kenya", "malian", "mali",
        "senegalese", "senegal", "south african", "cameroon", "ivory coast", "afryka",
        "afrykanski",
    ),
    "native-america": (
        "native american", "aztec", "maya", "mayan", "inca", "olmec", "navajo", "lakota",
        "sioux", "cheyenne", "hopi", "pre columbian", "precolumbian", "first nations",
        "inuit",
    ),
    "oceania": (
        "maori", "aboriginal", "papua", "papuan", "new guinea", "hawaiian", "hawaii",
        "polynesian", "polynesia", "melanesian", "melanesia", "micronesia", "fiji", "samoa",
        "tahiti", "oceania",
    ),
}  # fmt: skip

_CIRCLE_OF: dict[str, Circle] = {}
for _circle, _words in _WORDS.items():
    for _word in _words:
        _CIRCLE_OF.setdefault(_word, _circle)
_LONGEST = max(len(w.split()) for w in _CIRCLE_OF)


@lru_cache(maxsize=1 << 14)
def _circle_in(text: str) -> Circle | None:
    """The circle of the first word of ``text`` that names one; pairs of
    words first ("South African" is not "African" alone, "Song dynasty"
    is not a song)."""
    words = re.findall(r"[a-z]+", fold(text))
    for start in range(len(words)):
        for size in range(min(_LONGEST, len(words) - start), 0, -1):
            found = _CIRCLE_OF.get(" ".join(words[start : start + size]))
            if found is not None:
                return found
    return None


def circle(item: Item) -> Circle | None:
    """Where ``item`` comes from, in the broad: the author's nationality
    first, then the work's culture, then its styles; None when nothing
    says."""
    for text in (item.artist_bio, item.culture, *item.styles):
        if text and (found := _circle_in(text)) is not None:
            return found
    return None
