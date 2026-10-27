"""The author's nationality and life years in Polish: "Holender, 1853–1890".

Museums write the author's nationality as an English adjective ("Dutch,
Zundert 1853–1890 Auvers-sur-Oise"). Polish says it about a person, with a
noun in the author's gender ("Holender", "Holenderka"); an adjective
("holenderski") reads as a translation error. Models get this wrong often
enough that the note is put together here, from a dictionary, and a model's
own note is only corrected.
"""

from __future__ import annotations

import re
from typing import Literal

Gender = Literal["male", "female"]

#: English adjective → (man, woman, Polish adjective in the masculine).
NATIONALITIES: dict[str, tuple[str, str, str]] = {
    "american": ("Amerykanin", "Amerykanka", "amerykański"),
    "argentine": ("Argentyńczyk", "Argentynka", "argentyński"),
    "argentinian": ("Argentyńczyk", "Argentynka", "argentyński"),
    "armenian": ("Ormianin", "Ormianka", "ormiański"),
    "australian": ("Australijczyk", "Australijka", "australijski"),
    "austrian": ("Austriak", "Austriaczka", "austriacki"),
    "bavarian": ("Bawarczyk", "Bawarka", "bawarski"),
    "belgian": ("Belg", "Belgijka", "belgijski"),
    "bohemian": ("Czech", "Czeszka", "czeski"),
    "brazilian": ("Brazylijczyk", "Brazylijka", "brazylijski"),
    "british": ("Brytyjczyk", "Brytyjka", "brytyjski"),
    "bulgarian": ("Bułgar", "Bułgarka", "bułgarski"),
    "canadian": ("Kanadyjczyk", "Kanadyjka", "kanadyjski"),
    "chilean": ("Chilijczyk", "Chilijka", "chilijski"),
    "chinese": ("Chińczyk", "Chinka", "chiński"),
    "colombian": ("Kolumbijczyk", "Kolumbijka", "kolumbijski"),
    "croatian": ("Chorwat", "Chorwatka", "chorwacki"),
    "cuban": ("Kubańczyk", "Kubanka", "kubański"),
    "czech": ("Czech", "Czeszka", "czeski"),
    "danish": ("Duńczyk", "Dunka", "duński"),
    "dutch": ("Holender", "Holenderka", "holenderski"),
    "egyptian": ("Egipcjanin", "Egipcjanka", "egipski"),
    "english": ("Anglik", "Angielka", "angielski"),
    "estonian": ("Estończyk", "Estonka", "estoński"),
    "finnish": ("Fin", "Finka", "fiński"),
    "flemish": ("Flamand", "Flamandka", "flamandzki"),
    "florentine": ("Florentczyk", "Florentynka", "florencki"),
    "french": ("Francuz", "Francuzka", "francuski"),
    "georgian": ("Gruzin", "Gruzinka", "gruziński"),
    "german": ("Niemiec", "Niemka", "niemiecki"),
    "greek": ("Grek", "Greczynka", "grecki"),
    "hungarian": ("Węgier", "Węgierka", "węgierski"),
    "icelandic": ("Islandczyk", "Islandka", "islandzki"),
    "indian": ("Hindus", "Hinduska", "indyjski"),
    "iranian": ("Irańczyk", "Iranka", "irański"),
    "irish": ("Irlandczyk", "Irlandka", "irlandzki"),
    "israeli": ("Izraelczyk", "Izraelka", "izraelski"),
    "italian": ("Włoch", "Włoszka", "włoski"),
    "japanese": ("Japończyk", "Japonka", "japoński"),
    "korean": ("Koreańczyk", "Koreanka", "koreański"),
    "latvian": ("Łotysz", "Łotyszka", "łotewski"),
    "lithuanian": ("Litwin", "Litwinka", "litewski"),
    "mexican": ("Meksykanin", "Meksykanka", "meksykański"),
    "netherlandish": ("Niderlandczyk", "Niderlandka", "niderlandzki"),
    "norwegian": ("Norweg", "Norweżka", "norweski"),
    "persian": ("Pers", "Persjanka", "perski"),
    "peruvian": ("Peruwiańczyk", "Peruwianka", "peruwiański"),
    "polish": ("Polak", "Polka", "polski"),
    "portuguese": ("Portugalczyk", "Portugalka", "portugalski"),
    "prussian": ("Prusak", "Prusaczka", "pruski"),
    "romanian": ("Rumun", "Rumunka", "rumuński"),
    "russian": ("Rosjanin", "Rosjanka", "rosyjski"),
    "scottish": ("Szkot", "Szkotka", "szkocki"),
    "serbian": ("Serb", "Serbka", "serbski"),
    "slovak": ("Słowak", "Słowaczka", "słowacki"),
    "slovenian": ("Słoweniec", "Słowenka", "słoweński"),
    "spanish": ("Hiszpan", "Hiszpanka", "hiszpański"),
    "swedish": ("Szwed", "Szwedka", "szwedzki"),
    "swiss": ("Szwajcar", "Szwajcarka", "szwajcarski"),
    "thai": ("Taj", "Tajka", "tajski"),
    "tibetan": ("Tybetańczyk", "Tybetanka", "tybetański"),
    "turkish": ("Turek", "Turczynka", "turecki"),
    "ukrainian": ("Ukrainiec", "Ukrainka", "ukraiński"),
    "venetian": ("Wenecjanin", "Wenecjanka", "wenecki"),
    "vietnamese": ("Wietnamczyk", "Wietnamka", "wietnamski"),
    "welsh": ("Walijczyk", "Walijka", "walijski"),
}

# Polish adjective (any gender, either case) → its English key.
_ADJECTIVES = {
    form: key
    for key, (_, _, adjective) in NATIONALITIES.items()
    for form in (adjective, adjective[:-1] + "a", adjective + "e")
}

_YEAR = r"\d{3,4}(?:s)?"
_APPROX = r"(?:ca\.|c\.|circa|about)\s*"
_RANGE = re.compile(rf"(?:({_APPROX}))?({_YEAR})\s*[-–—]\s*(?:({_APPROX}))?({_YEAR})")
_ONE = re.compile(rf"\b(born|died|active)\b[^0-9]*?(?:({_APPROX}))?({_YEAR})", re.IGNORECASE)


def noun(nationality: str, gender: Gender | None = None) -> str | None:
    """The Polish noun for an English nationality: "Dutch" → "Holender" (a
    woman: "Holenderka"); ``None`` when unknown.

    Without a known gender the masculine form is used, as Polish does for
    a person in general.
    """
    entry = NATIONALITIES.get(nationality.strip().casefold())
    if entry is None:
        return None
    return entry[1] if gender == "female" else entry[0]


def _nationality(bio: str) -> str:
    """The leading adjective of "American (born Germany), 1830–1902"."""
    head = re.split(r"[,(;]", bio, maxsplit=1)[0].strip()
    return head if head.casefold() in NATIONALITIES else ""


def _year(text: str) -> str:
    # "1850s": the decade; Polish writes "lata 50. XIX w.", too long here.
    return text[:-1] if text.endswith("s") else text


def _years(bio: str, gender: Gender | None) -> str:
    """Life years in Polish: "1853–1890", "ok. 1615–1673", "ur. 1950"."""
    if match := _RANGE.search(bio):
        born = ("ok. " if match.group(1) else "") + _year(match.group(2))
        died = ("ok. " if match.group(3) else "") + _year(match.group(4))
        active = re.search(r"\bactive\b", bio[: match.start()], re.IGNORECASE)
        prefix = ("czynna " if gender == "female" else "czynny ") if active else ""
        return f"{prefix}{born}–{died}"
    if match := _ONE.search(bio):
        word = match.group(1).casefold()
        year = ("ok. " if match.group(2) else "") + _year(match.group(3))
        if word == "active":
            return ("czynna " if gender == "female" else "czynny ") + year
        return ("ur. " if word == "born" else "zm. ") + year
    return ""


def artist_note(bio: str, gender: Gender | None = None) -> str | None:
    """The note after the author's name: "Dutch, Zundert 1853–1890
    Auvers-sur-Oise" → "Holender, 1853–1890".

    ``None`` when the bio names no nationality the dictionary knows: then a
    model's note (corrected by ``fix_note``) is the best there is.
    """
    nationality = _nationality(bio)
    if not nationality:
        return None
    person = noun(nationality, gender)
    years = _years(bio, gender)
    return f"{person}, {years}" if years else person


def fix_note(note: str, gender: Gender | None = None) -> str:
    """A model's note with a leading adjective made a noun:
    "holenderski, 1853–1890" → "Holender, 1853–1890"."""
    match = re.match(r"^\s*([^\W\d_]+)\b", note)
    if not match:
        return note.strip()
    key = _ADJECTIVES.get(match.group(1).casefold())
    if key is None:
        return note.strip()
    person = noun(key, gender) or match.group(1)
    return (person + note[match.end() :]).strip()
