"""Whether a work's "artist" names an artist at all.

Museums fill the field with what they have: "Unknown", "Anonymous", the
Catalan "Desconegut", the Dutch "Anoniem", "Fotògraf desconegut", a culture
("Japanese, Edo period"), a workshop ("Workshop of Rubens") or a publisher
("Detroit Publishing Co."). Grouped by artist (the artist of the week, "Bo
lubisz", the artists in the search), such names make an artist of hundreds
of unrelated works, so they are left out there.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .nationality import NATIONALITIES
from .vocabulary import PER_WORK, artist_matches, fold, name_words

#: Words for "unknown", "anonymous" and "various" in museums' languages
#: (folded: lower case, no accents).
NOBODY = frozenset(
    {
        # English
        "unknown",
        "unkown",
        "anonymous",
        "anon",
        "unidentified",
        "unattributed",
        "unrecorded",
        "various",
        "multiple",
        # Latin, Catalan, Spanish, Portuguese, French, Italian
        "anonymus",
        "ignotus",
        "desconegut",
        "desconeguda",
        "desconeguts",
        "anonim",
        "anonims",
        "desconocido",
        "desconocida",
        "desconocidos",
        "anonimo",
        "anonima",
        "anonimos",
        "varios",
        "diversos",
        "desconhecido",
        "desconhecida",
        "inconnu",
        "inconnue",
        "inconnus",
        "anonyme",
        "anonymes",
        "divers",
        "ignoto",
        "ignota",
        "sconosciuto",
        "sconosciuta",
        "anonimi",
        # Dutch, German, Scandinavian, Finnish
        "anoniem",
        "onbekend",
        "onbekende",
        "anonym",
        "anonymer",
        "unbekannt",
        "unbekannter",
        "verschiedene",
        "ukendt",
        "ubekendt",
        "anonymt",
        "ukjent",
        "okand",
        "okant",
        "tuntematon",
        "nimeton",
        # Polish, Czech, Slovak, Hungarian, Romanian, Russian
        "nieznany",
        "nieznana",
        "nieznani",
        "anonimowy",
        "rozni",
        "neznamy",
        "neznama",
        "anonymni",
        "ismeretlen",
        "necunoscut",
        "neizvestnyi",
        "neizvestnyy",
        "неизвестный",
        "аноним",
        # Japanese, Chinese
        "fumei",
        "不詳",
        "作者不詳",
        "佚名",
    }
)
#: Who someone was rather than who: "Fotògraf desconegut", "Artist".
ROLES = frozenset(
    {
        "artist",
        "artists",
        "author",
        "authors",
        "autor",
        "autora",
        "autores",
        "auteur",
        "autore",
        "kunstenaar",
        "kunstler",
        "kunstner",
        "konstnar",
        "maker",
        "makers",
        "maker's",
        "creator",
        "painter",
        "pintor",
        "pintora",
        "peintre",
        "pittore",
        "schilder",
        "maler",
        "malarz",
        "photographer",
        "fotograf",
        "fotografo",
        "fotografa",
        "fotograaf",
        "photographe",
        "illustrator",
        "engraver",
        "designer",
        "draughtsman",
        "printmaker",
        "sculptor",
        "hand",
    }
)
#: Small words that name nobody.
_FILLER = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "and",
        "or",
        "el",
        "la",
        "les",
        "le",
        "l",
        "de",
        "del",
        "des",
        "du",
        "di",
        "da",
        "der",
        "die",
        "das",
        "van",
        "het",
        "een",
        "un",
        "una",
        "une",
        "uno",
        "i",
        "y",
        "e",
        "et",
        "und",
        "en",
        "o",
        "ou",
        "oder",
        "s",
    }
)
#: Not one artist: a workshop, school, circle or follower, a copy after one.
_GROUPS = frozenset(
    {
        "workshop",
        "studio",
        "atelier",
        "werkstatt",
        "werkplaats",
        "taller",
        "bottega",
        "pracownia",
        "school",
        "schule",
        "escuela",
        "escola",
        "ecole",
        "scuola",
        "szkola",
        "circle",
        "cercle",
        "kring",
        "umkreis",
        "cerchia",
        "krag",
        "follower",
        "followers",
        "suiveur",
        "navolger",
        "nachfolger",
        "seguace",
        "nasladowca",
        "imitator",
        "manner",
        "entourage",
        "omgeving",
    }
)
#: The first word of a work after someone else's or only given to them.
_ATTRIBUTED = frozenset({"after", "attributed", "copy", "toegeschreven", "naar", "nach", "d'apres"})
#: Publishers and firms: "Detroit Publishing Co.", "Imprenta Moderna".
_FIRMS = frozenset(
    {
        "co",
        "cie",
        "cia",
        "company",
        "compagnie",
        "compania",
        "inc",
        "ltd",
        "limited",
        "gmbh",
        "verlag",
        "publishing",
        "publishers",
        "publisher",
        "editorial",
        "editions",
        "edition",
        "imprenta",
        "impremta",
        "litografia",
        "lithographic",
        "lithographing",
        "photographic",
        "manufacturing",
        "manufactory",
        "factory",
        "fabrik",
        "press",
    }
)
#: Peoples, places and periods: "Japanese, Edo period", "French School".
_CULTURES = frozenset(NATIONALITIES) | frozenset(
    {
        "ancient",
        "roman",
        "etruscan",
        "byzantine",
        "islamic",
        "persian",
        "ottoman",
        "safavid",
        "qajar",
        "mughal",
        "flemish",
        "netherlandish",
        "venetian",
        "sienese",
        "lombard",
        "edo",
        "meiji",
        "taisho",
        "showa",
        "momoyama",
        "muromachi",
        "kamakura",
        "heian",
        "qing",
        "ming",
        "song",
        "tang",
        "yuan",
        "joseon",
        "goryeo",
        "europe",
        "asia",
        "africa",
        "america",
        "japan",
        "china",
        "india",
        "korea",
        "france",
        "italy",
        "germany",
        "spain",
        "netherlands",
    }
)
_TIMES = frozenset(
    {
        "century",
        "centuries",
        "period",
        "dynasty",
        "culture",
        "region",
        "active",
        "about",
        "circa",
        "ca",
        "c",
        "early",
        "late",
        "mid",
        "st",
        "nd",
        "rd",
        "th",
        "or",
        "possibly",
        "probably",
    }
)


@lru_cache(maxsize=PER_WORK)
def is_artist(name: str) -> bool:
    """``name`` names someone: not "Unknown", "Desconegut", "Fotògraf
    desconegut", "Japanese, Edo period", "Workshop of Rubens" or "Detroit
    Publishing Co."."""
    first_line = name.split("\n")[0]
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", fold(first_line))
    if not words:
        return False
    have = set(words)
    if have & NOBODY or have & _GROUPS or have & _FIRMS or words[0] in _ATTRIBUTED:
        return False
    if not have - ROLES - _FILLER:
        return False
    return not (have & _CULTURES and have <= _CULTURES | _TIMES | _FILLER | ROLES)


#: Words after which a name is not the work's maker: a copy after them
#: ("Paul Gachet, after Vincent van Gogh", "d'après Millet", "wg Matejki"),
#: their workshop, school, circle or follower. "Attributed to" still counts:
#: the museum gives the work to them.
_NOT_BY = (
    (_ATTRIBUTED - {"attributed", "toegeschreven"})
    | _GROUPS
    | frozenset({"apres", "wg", "wedlug", "kopia", "copia", "segun", "style", "pupil", "assistant"})
)


@lru_cache(maxsize=PER_WORK)
def _maker_words(artist: str) -> frozenset[str]:
    """The words of ``artist`` before any "after", "workshop of" and the
    like: the names of who made the work."""
    words = re.findall(r"[^\W\d_]+", fold(artist))
    cut = next((n for n, w in enumerate(words) if w in _NOT_BY), len(words))
    return frozenset(words[:cut])


def made_by(artist: str, wanted: list[str]) -> bool:
    """A work with ``artist`` is by one of ``wanted`` (spelled as museums
    do: "Gogh, Vincent van" is Vincent van Gogh), not a copy after them or
    of their workshop or followers: searching an artist shows only their
    own works (Mateusz, 2026-11-07)."""
    if not artist_matches(artist, wanted):
        return False
    makers = _maker_words(artist)
    return any(name_words(w) and name_words(w) <= makers for w in wanted)
