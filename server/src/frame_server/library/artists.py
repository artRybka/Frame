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

from .given_names import GIVEN, given
from .nationality import NATIONALITIES
from .vocabulary import PER_WORK, fold

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
        "værksted",
        "forgery",
        "forger",
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
        "imprimerie",
        "imprimeur",
        "druckerei",
        "drukkerij",
        "drukarnia",
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


#: Library state: each spelling's Wikidata item as found (``artist_people``)
#: and each item's names and years.
IDS_STATE = "artist_ids"
PEOPLE_STATE = "artist_people"


#: A small letter followed by a capital: two words written together.
_JOINED = re.compile(r"(?<=[a-ząćęłńóśźżäöüéèàç])(?=[A-ZĄĆĘŁŃÓŚŹŻÄÖÜÉÈÀÇ])")


@lru_cache(maxsize=PER_WORK)
def is_artist(name: str) -> bool:
    """``name`` names someone: not "Unknown", "Desconegut", "Fotògraf
    desconegut", "Japanese, Edo period", "Workshop of Rubens" or "Detroit
    Publishing Co."."""
    first_line = name.split("\n")[0].strip()
    if first_line.startswith("#"):
        return False  # a museum's field name ("#PredmetAutor:6058030")
    if _not_theirs(first_line):
        return False  # "Lucas Cranach the Elder, After", "Formerly attributed to Mi Fu"
    # Words run together ("AnonimowyUnknown author") apart.
    first_line = _JOINED.sub(" ", first_line)
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", fold(first_line))
    if not words:
        return False
    if re.search(r"\d", first_line) and all(len(w) <= 3 for w in words):
        return False  # a number ("MTB-PE-817")
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


#: A name the museum takes back or only copies, said after the name:
#: "Lucas Cranach the Elder, After" (the NGA), "Rembrandt van Rijn
#: (værksted)" (SMK), "Bonifacio Bembo, workshop of"; and "Formerly
#: attributed to Mi Fu", "Artist, formerly attributed to: Auguste Rodin"
#: (the Met). Not "Wu Zhang (1671-after 1741)", whose "after" is a year's,
#: nor "Lucas Cranach the Elder and Workshop", his with his workshop.
_AFTER_NAME = re.compile(
    r"(?:[,(]|\s[-–])\s*(?:or\s+)?(?:"
    + "|".join(sorted(re.escape(word) for word in _NOT_BY))
    + r")(?:\s+of)?\s*\)?\s*$"
)
_FORMERLY = frozenset({"formerly", "previously", "dawniej", "voorheen", "ehemals", "anciennement"})


def _not_theirs(line: str) -> bool:
    """``line`` names someone the work is not by: a copy after them or
    their workshop said after the name, or an attribution taken back."""
    folded = fold(line)
    return bool(_AFTER_NAME.search(folded)) or bool(
        _FORMERLY.intersection(_LETTERS.findall(folded))
    )


@lru_cache(maxsize=PER_WORK)
def _maker_words(artist: str) -> frozenset[str]:
    """The words of ``artist`` before any "after", "workshop of" and the
    like: the names of who made the work."""
    words = re.findall(r"[^\W\d_]+", fold(artist))
    cut = next((n for n, w in enumerate(words) if w in _NOT_BY), len(words))
    return frozenset(words[:cut])


#: Words that make the next of a name another person than the name alone:
#: "Utagawa Hiroshige II", "Robert Havell, Jr.", "Vernet fils". ("The
#: Younger" does not: "Hans Holbein" alone is mostly him.)
_SUCCESSORS = frozenset({"ii", "iii", "iv", "jr", "junior", "fils"})


@lru_cache(maxsize=PER_WORK)
def _outside_brackets(artist: str) -> frozenset[str]:
    """The words of ``artist`` that are not in brackets: in "Utagawa
    Kunisada I (Toyokuni III)" the third is of another name of his."""
    return frozenset(_LETTERS.findall(fold(re.sub(r"\([^()]*\)", " ", artist))))


@lru_cache(maxsize=PER_WORK)
def _numbers(artist: str) -> frozenset[str]:
    """The numbers in ``artist``'s name, a bracket's years aside: what
    tells the "Master of 1518" from the Master of 1540."""
    return frozenset(re.findall(r"\d+", re.sub(r"\([^()]*\)", " ", artist.split("\n")[0])))


def made_by(artist: str, wanted: list[str]) -> bool:
    """A work with ``artist`` is by one of ``wanted`` (spelled as museums
    do: "Gogh, Vincent van" is Vincent van Gogh), not a copy after them or
    of their workshop or followers: searching an artist shows only their
    own works (Mateusz, 2026-11-07)."""
    if _not_theirs(artist.split("\n")[0]):
        return False  # "Lucas Cranach the Elder, After" is not Cranach's
    if _known.alike(artist, wanted):
        return True  # "Rembrandt" for "Rembrandt van Rijn" (2026-11-08)
    if _known.apart(artist, wanted):
        return False  # Jan Vermeer van Haarlem for Vermeer of Delft (2026-11-09)
    makers = _maker_words(artist)
    mine = given(makers)
    for name in wanted:
        asked = name_key(name)
        if not asked or asked & _NOT_BY:
            continue  # nobody's own name: "Dürer-School", "Artist, style of: X"
        if not _numbers(name) <= _numbers(artist):
            continue  # "Master of 1518" is not the Master of 1540
        if asked == name_key(artist):
            return True
        if not is_artist(name) or all(len(w) < 2 for w in asked - _FILLER - GIVEN.keys()):
            continue  # nobody ("German"), first names only ("Raphael" is not
            # Anton Raphael Mengs) or initials ("W." is not C.W. Eckersberg)
        if (_outside_brackets(artist) - asked) & _SUCCESSORS:
            continue  # "Utagawa Hiroshige II" is not Utagawa Hiroshige
        # In the name as it is, or with a first name in another language:
        # the V&A's and Europeana's "Alphonse Mucha" for "Alfons Mucha"
        # (2026-11-10).
        if asked <= makers or given(asked) <= mine:
            return True
    return False


def same_hand(artist: str, other: str) -> bool:
    """Two works' artists are one maker, however each museum spells them:
    :func:`made_by` asked either way ("Edgar Degas" and "Hilaire Germain
    Edgar Degas"; not "Rembrandt" and "Pupil of Rembrandt")."""
    key = name_key(artist)
    if key and key == name_key(other) and _numbers(artist) == _numbers(other):
        return True  # the same line: "After Rembrandt" twice
    return made_by(artist, [other]) or made_by(other, [artist])


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
#: Words of what a museum says of the name rather than a name: "Abraham
#: Storck (signed by artist)", "Roeloffzen & Hübner (mentioned on object)",
#: "Vincent van Gogh (possibly)", "Vincent Van Gogh, The Netherlands",
#: "(Dutch, 1853-1890)". Never a generation, workshop or copy: "Pieter
#: Bruegel (the Elder)" and "(copy after)" stay in the name.
_REMARKS = (
    (
        _CULTURES
        | _TIMES
        | ROLES
        | _FILLER
        | frozenset(
            {
                "signed",
                "monogrammed",
                "inscribed",
                "inscription",
                "mentioned",
                "object",
                "by",
                "on",
                "to",
                "in",
                "at",
                "born",
                "died",
                "dated",
                "verso",
                "recto",
                "possible",
                "perhaps",
                "attributed",
                "toegeschreven",
                "doubtful",
                "uncertain",
                "unsure",
            }
        )
    )
    - _GENERATIONS
    - _NOT_BY
    - NOBODY
    - _FIRMS
)
#: Words that never stand in a person's name: a bracket with one of them
#: is a remark, never the Met's full name ("X (signed by artist)" joined
#: everyone signed so into one person, Mateusz 2026-11-09).
_REMARK_ONLY = _REMARKS - _FILLER - frozenset(NATIONALITIES)
_BRACKET_TAIL = re.compile(r"\s*\(([^()]*)\)\s*$")


def _remark(text: str) -> bool:
    """``text`` (a bracket, a part after a comma) says something of the name
    and names nobody: "signed by artist", "possibly", "Dutch, 1853-1890",
    "The Netherlands"."""
    return set(_LETTERS.findall(fold(text))) <= _REMARKS


def _bare(line: str) -> str:
    """The name without remarks after it: "Abraham Storck" for "Abraham
    Storck (signed by artist)", "Vincent Van Gogh" for "Vincent Van Gogh,
    The Netherlands". A reversed name stays: "Gogh, Vincent van", and
    "Opałka, Roman" is not "Opałka" of the Romans."""
    while (bracket := _BRACKET_TAIL.search(line)) and _remark(bracket.group(1)):
        if not line[: bracket.start()].strip():
            break
        line = line[: bracket.start()]
    head, *tail = line.split(",")
    if tail and len(set(_LETTERS.findall(fold(head))) - _FILLER) >= 2:
        while tail and _remark(tail[-1]):
            tail.pop()
        line = ",".join([head, *tail])
    return line


def without_remarks(name: str) -> str:
    """The name's first line without what a museum says after it: "Winslow
    Homer" for "Winslow Homer, American" (:func:`_bare`)."""
    return _bare(name.split("\n")[0]).strip()


@lru_cache(maxsize=PER_WORK)
def name_key(name: str) -> frozenset[str]:
    """The words of the name's first line in lower case without accents,
    without remarks after it: the same for "Jan van Eyck", "Jan Van Eyck",
    "Eyck, Jan van" and "Rembrandt (Rembrandt van Rijn)" with "Rembrandt van
    Rijn", and for "Abraham Storck (signed by artist)" with "Abraham
    Storck"."""
    return frozenset(_LETTERS.findall(fold(_bare(name.split("\n")[0]))))


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

    def __init__(
        self,
        works: Mapping[str, Collection[Hashable]] | None = None,
        ids: Mapping[str, str] | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """``works``: each artist's name as the catalogue spells it, with its
        works (anything that tells works apart). ``ids``: the Wikidata item
        of names whose person is known (``artist_people``), ``labels`` those
        items' English names: spellings of one item are one person, and two
        items are never joined, whatever their words ("Jan Vermeer" of Delft
        and "Jan Vermeer van Haarlem")."""
        works = works or {}
        ids = ids or {}
        labels = labels or {}
        names = sorted(n for n in works if _own_name(n))
        parent: dict[frozenset[str], frozenset[str]] = {}
        #: Each group's Wikidata item, by its root.
        item_of: dict[frozenset[str], str] = {}

        def find(key: frozenset[str]) -> frozenset[str]:
            parent.setdefault(key, key)
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        def join(a: frozenset[str], b: frozenset[str]) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            qa, qb = item_of.get(ra), item_of.get(rb)
            if qa and qb and qa != qb:
                return  # two people Wikidata tells apart
            root, other = min(ra, rb, key=sorted), max(ra, rb, key=sorted)
            parent[other] = root
            if qa or qb:
                item_of[root] = qa or qb  # type: ignore[assignment]

        # Wikidata's people first: their spellings together, and every
        # join after that keeps two of them apart.
        anchor: dict[str, frozenset[str]] = {}
        for name in names:
            qid = ids.get(name)
            key = name_key(name)
            if not qid or not key:
                continue
            root = find(key)
            if item_of.get(root, qid) != qid:
                continue  # these words are someone else's already
            item_of[root] = qid
            if qid in anchor:
                join(key, anchor[qid])
            else:
                anchor[qid] = key

        #: The Met's "X (Y)": each Y with the names before it.
        known: dict[frozenset[str], set[tuple[frozenset[str], frozenset[str]]]] = {}
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
                and not full_key & _REMARK_ONLY
                and not re.search(r"[\d,;&/]", full)
            ):
                known.setdefault(full_key, set()).add((name_key(name), short_key))
        for full_key, shorts in known.items():
            # A full name after two people's names is no one's: a remark
            # the words above missed.
            if any(a[1].isdisjoint(b[1]) for a, b in combinations(shorts, 2)):
                continue
            for whole_key, short_key in shorts:
                join(whole_key, short_key)
                join(whole_key, full_key)

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

        #: Each person -> the name words (:func:`name_key`) that are them.
        self._keys: dict[int, list[frozenset[str]]] = {}
        for key, person in self._person.items():
            self._keys.setdefault(person, []).append(key)
        #: Each person -> their Wikidata item, when known.
        self.items: dict[int, str] = {}
        for key, person in self._person.items():
            if qid := item_of.get(find(key)):
                self.items[person] = qid
        #: Each person's name as shown -> all its spellings, that first.
        self.spellings: dict[str, list[str]] = {}
        self._shown: dict[int, str] = {}
        for person, found in spellings.items():
            found.sort(key=shown)
            # Wikidata's name for them when the catalogue spells it so
            # ("Johannes Vermeer", not "Jan Vermeer" of Commons' 31 works).
            label = labels.get(self.items.get(person, ""), "")
            named = [n for n in found if label and name_key(n) == name_key(label)]
            if named:
                found.remove(named[0])
                found.insert(0, named[0])
            self.spellings[found[0]] = found
            self._shown[person] = found[0]

    def __len__(self) -> int:
        return len(self.spellings)

    def person(self, name: str) -> int | None:
        """The person ``name`` is among the catalogue's artists, if any."""
        return self._person.get(name_key(name)) if name else None

    def keys_of(self, person: int) -> list[frozenset[str]]:
        """The name words (:func:`name_key`) of every spelling of ``person``:
        a name with one of them is that person (:meth:`alike`)."""
        return self._keys.get(person, [])

    def shown(self, name: str) -> str:
        """``name`` as its person is shown: "Rembrandt van Rijn" for
        "Rembrandt (Rembrandt van Rijn)"; an unknown name as it is."""
        person = self.person(name)
        return self._shown.get(person, name) if person is not None else name

    def apart(self, artist: str, wanted: list[str]) -> bool:
        """Wikidata says ``artist`` is someone else than each of ``wanted``."""
        person = self.person(artist)
        mine = self.items.get(person) if person is not None else None
        if not mine:
            return False
        for name in wanted:
            other = self.person(name)
            if other is None or not self.items.get(other) or self.items[other] == mine:
                return False
        return True

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


def other_spelling(name: str) -> str | None:
    """Another way the catalogue spells ``name``'s person, to ask a museum
    whose author field knows them so ("Alphonse Mucha" at the Art Institute
    for "Alfons Mucha", 2026-11-10); None without one."""
    names = _known
    if names.person(name) is None:
        return None
    for spelling in names.spellings.get(names.shown(name), []):
        line = spelling.split("\n")[0]
        if name_key(line) != name_key(name) and not re.search(r"[,()]", line):
            return line
    return None
