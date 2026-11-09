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
from collections.abc import Collection, Hashable, Mapping
from functools import lru_cache
from itertools import combinations

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
    if _known.alike(artist, wanted):
        return True  # "Rembrandt" for "Rembrandt van Rijn" (2026-11-08)
    if not artist_matches(artist, wanted):
        return False
    makers = _maker_words(artist)
    return any(name_words(w) and name_words(w) <= makers for w in wanted)


# -- one artist under many spellings -------------------------------------------

#: Words that make another person of the same name: "Pieter Bruegel the
#: Younger", "Utagawa Hiroshige II", "Vernet fils".
_GENERATIONS = frozenset(
    {
        "elder",
        "younger",
        "oude",
        "jonge",
        "jongere",
        "altere",
        "jungere",
        "vecchio",
        "giovane",
        "giovine",
        "ancien",
        "jeune",
        "pere",
        "fils",
        "viejo",
        "mozo",
        "starszy",
        "mlodszy",
        "jr",
        "sr",
        "junior",
        "senior",
        "ii",
        "iii",
        "iv",
    }
)
#: Words a longer spelling may not add to a name and still be the same
#: person: another generation, a workshop or copy, nobody, a firm.
_OTHER_PERSON = _GENERATIONS | _NOT_BY | NOBODY | _FIRMS
_LETTERS = re.compile(r"[^\W\d_]+")
#: Words a longer spelling may add to a name and still be the same person:
#: "Katsushika Hokusai" for "Hokusai", "Francisco José de Goya y Lucientes"
#: for "Goya"; a name with more is a list or a description, not a spelling.
LONGER_WORDS = 4
#: The Met's "Rembrandt (Rembrandt van Rijn)", "El Greco (Domenikos
#: Theotokopoulos)": the name known by, then the full one.
_KNOWN_AS = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")


@lru_cache(maxsize=PER_WORK)
def name_key(name: str) -> frozenset[str]:
    """The words of the name's first line in lower case without accents:
    the same for "Jan van Eyck", "Jan Van Eyck", "Eyck, Jan van" and
    "Rembrandt (Rembrandt van Rijn)" with "Rembrandt van Rijn"."""
    return frozenset(_LETTERS.findall(fold(name.split("\n")[0])))


def _own_name(name: str) -> bool:
    """``name`` names one artist by their own name: not nobody, not a copy
    after them or their workshop ("Pupil of Rembrandt")."""
    key = name_key(name)
    return bool(key - _FILLER) and is_artist(name) and not key & _NOT_BY


class ArtistNames:
    """Which of the catalogue's artists are one person: museums spell
    Rembrandt "Rembrandt van Rijn" (Rijksmuseum, NGA), "Rembrandt" (Commons),
    "Rembrandt (Rembrandt van Rijn)" (the Met) and "Rembrandt Harmensz. van
    Rijn" (Europeana), and Jan van Eyck once "Jan Van Eyck" (Mateusz,
    2026-11-08: one artist in the search, not four).

    Names are one person when they have the same words (case, order and
    brackets aside); when the Met says one is the other ("X (Y)"); and when
    one is in a longer one that adds no "the Younger", "II", "workshop" or
    the like ("Rembrandt Harmensz. van Rijn", "Hokusai" in "Katsushika
    Hokusai") and in no other person's name: with "Rembrandt Peale" in the
    catalogue too, "Rembrandt" alone is Rembrandt van Rijn only on the Met's
    say, and "Bruegel" stays nobody's."""

    def __init__(self, works: Mapping[str, Collection[Hashable]] | None = None) -> None:
        """``works``: each artist's name as the catalogue spells it, with its
        works (anything that tells works apart)."""
        works = works or {}
        names = sorted(n for n in works if _own_name(n))
        parent: dict[frozenset[str], frozenset[str]] = {}

        def find(key: frozenset[str]) -> frozenset[str]:
            parent.setdefault(key, key)
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        def join(a: frozenset[str], b: frozenset[str]) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb, key=sorted)] = min(ra, rb, key=sorted)

        for name in names:
            find(name_key(name))
            known_as = _KNOWN_AS.match(name.split("\n")[0])
            if known_as is None:
                continue
            short, full = known_as.group(1), known_as.group(2)
            short_key, full_key = name_key(short), name_key(full)
            if (
                short_key
                and len(full_key - _FILLER) >= 2
                and is_artist(short)
                and is_artist(full)
                and not (short_key | full_key) & _OTHER_PERSON
            ):
                join(name_key(name), short_key)
                join(name_key(name), full_key)

        keys = sorted(parent, key=sorted)
        with_word: dict[str, list[frozenset[str]]] = {}
        for key in keys:
            for word in key:
                with_word.setdefault(word, []).append(key)
        several: dict[frozenset[str], bool] = {}

        def names_several(key: frozenset[str]) -> bool:
            """``key`` holds two other artists' whole names that share no
            word ("Albrecht Dürer, Vincent van Gogh, Pierre-Auguste Renoir",
            "Renoir, Dürer"): a list of people, never one of them under a
            longer spelling."""
            if key not in several:
                inside = {
                    core
                    for word in key - _FILLER
                    for other in with_word.get(word, ())
                    if other < key
                    and (core := other - _FILLER)
                    and (len(core) >= 2 or len(min(core)) >= 5)
                }
                several[key] = any(a.isdisjoint(b) for a, b in combinations(inside, 2))
            return several[key]

        for key in keys:
            core = key - _FILLER
            if not core or key & _GENERATIONS or (len(core) == 1 and len(min(core)) < 4):
                continue
            rarest = min(core, key=lambda w: (len(with_word[w]), w))
            longer = {
                find(other)
                for other in with_word[rarest]
                if key < other
                and not (other - key) & _OTHER_PERSON
                and len((other - key) - _FILLER) <= LONGER_WORDS
                and not names_several(other)
            }
            # In one person's names only: "Rembrandt", the Met's Rembrandt
            # van Rijn, stays out of "Rembrandt Peale".
            if len(longer) == 1:
                join(key, longer.pop())

        #: Each name's key -> its person (a number).
        self._person: dict[frozenset[str], int] = {}
        roots: dict[frozenset[str], int] = {}
        for key in keys:
            self._person[key] = roots.setdefault(find(key), len(roots))
        spellings: dict[int, list[str]] = {}
        for name in names:
            spellings.setdefault(self._person[name_key(name)], []).append(name)

        def shown(name: str) -> tuple[bool, int, int, str]:
            # The most works' spelling, a plain one before "X (Y)" and
            # "Gogh, Vincent van".
            plain = "(" not in name and "," not in name.split("\n")[0]
            return (not plain, -len(works[name]), len(name), name)

        #: Each person's name as shown -> all its spellings, that first.
        self.spellings: dict[str, list[str]] = {}
        self._shown: dict[int, str] = {}
        for person, found in spellings.items():
            found.sort(key=shown)
            self.spellings[found[0]] = found
            self._shown[person] = found[0]

    def __len__(self) -> int:
        return len(self.spellings)

    def person(self, name: str) -> int | None:
        """The person ``name`` is among the catalogue's artists, if any."""
        return self._person.get(name_key(name)) if name else None

    def shown(self, name: str) -> str:
        """``name`` as its person is shown: "Rembrandt van Rijn" for
        "Rembrandt (Rembrandt van Rijn)"; an unknown name as it is."""
        person = self.person(name)
        return self._shown.get(person, name) if person is not None else name

    def alike(self, artist: str, wanted: list[str]) -> bool:
        """``artist`` is one of the people ``wanted`` under another spelling
        (only its own name: "Pupil of Rembrandt" is not Rembrandt)."""
        person = self.person(artist)
        if person is None or name_key(artist) & _NOT_BY:
            return False
        return any(self.person(w) == person for w in wanted)


#: The catalogue's artists as last counted (:meth:`learn`): who is who for
#: the searches.
_known = ArtistNames()


def known_names() -> ArtistNames:
    return _known


def learn(names: ArtistNames) -> None:
    """Search with ``names`` from now on (built with the term index)."""
    global _known
    _known = names
