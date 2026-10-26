"""Words for finding art: styles, subjects, periods and techniques under
Polish names, with the English (and some Dutch and Polish) words museums
describe their works with. Also tells manuscripts apart, which the frame
leaves out unless asked for.

A term's key (``"subject:sea"``) is what smart playlists store in
``PlaylistRules.terms``; terms of one kind are alternatives, different kinds
must all match (an impressionist sea: ``style:impressionism`` and
``subject:sea``). Ranges of years can be terms too: ``years:1880-1914``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import cache, cached_property, lru_cache
from itertools import product
from typing import Literal

from .models import Item, ItemKind
from .museums import Kind

TermKind = Literal["style", "subject", "period", "technique"]
#: discovery kinds (museums.Kind) of techniques that museums can filter by.
TECHNIQUE_KINDS: dict[str, Kind] = {
    "technique:painting": "painting",
    "technique:print": "print",
    "technique:drawing": "drawing",
    "technique:poster": "poster",
}
MANUSCRIPTS = "technique:manuscripts"


@dataclass(frozen=True)
class Term:
    key: str
    name: str
    #: Matched as whole words (an "s" or "es" plural allowed); a trailing
    #: ``*`` matches any ending. The first word is what museums are asked.
    words: tuple[str, ...] = ()
    year_from: int | None = None
    year_to: int | None = None

    @property
    def kind(self) -> TermKind:
        return self.key.partition(":")[0]  # type: ignore[return-value]

    @property
    def query(self) -> str:
        return self.words[0].rstrip("*") if self.words else ""

    @cached_property
    def pattern(self) -> re.Pattern[str] | None:
        if not self.words:
            return None
        parts = [
            re.escape(w[:-1]) + r"\w*" if w.endswith("*") else re.escape(w) + r"(?:s|es)?\b"
            for w in self.words
        ]
        return re.compile(r"\b(?:" + "|".join(parts) + ")", re.IGNORECASE)


def _t(key: str, name: str, *words: str) -> Term:
    return Term(key, name, words)


def _p(key: str, name: str, year_from: int | None, year_to: int | None) -> Term:
    return Term(key, name, year_from=year_from, year_to=year_to)


TERMS: list[Term] = [
    # Styles and movements
    _t("style:impressionism", "Impresjonizm", "impressionism", "impressionist*"),
    _t(
        "style:post-impressionism",
        "Postimpresjonizm",
        "post-impressionism",
        "post-impressionist*",
        "postimpression*",
        "pointillis*",
        "neo-impression*",
    ),
    _t("style:ukiyo-e", "Ukiyo-e", "ukiyo-e", "ukiyoe", "ukiyo"),
    _t("style:shin-hanga", "Shin-hanga", "shin-hanga", "shin hanga"),
    _t("style:romanticism", "Romantyzm", "romanticism", "romantic"),
    _t("style:realism", "Realizm", "realism", "realist", "barbizon"),
    _t("style:symbolism", "Symbolizm", "symbolism", "symbolist"),
    _t("style:pre-raphaelite", "Prerafaelici", "pre-raphaelite", "pre-raphaelitism"),
    _t(
        "style:art-nouveau",
        "Secesja",
        "art nouveau",
        "jugendstil",
        "secession",
        "secesja",
        "aesthetic movement",
    ),
    _t("style:art-deco", "Art déco", "art deco"),
    _t("style:nabis", "Nabiści", "nabis"),
    _t("style:expressionism", "Ekspresjonizm", "expressionism", "expressionist"),
    _t("style:fauvism", "Fowizm", "fauvism", "fauve"),
    _t("style:cubism", "Kubizm", "cubism", "cubist"),
    _t("style:tonalism", "Tonalizm", "tonalism", "tonalist"),
    _t("style:hudson-river", "Szkoła znad rzeki Hudson", "hudson river school"),
    _t("style:young-poland", "Młoda Polska", "young poland", "młoda polska"),
    _t("style:academic", "Akademizm", "academic art", "academicism", "academism"),
    _t("style:neoclassicism", "Klasycyzm", "neoclassicism", "neoclassical", "neo-classical"),
    _t("style:rococo", "Rokoko", "rococo"),
    _t("style:baroque", "Barok", "baroque"),
    _t("style:dutch-golden-age", "Złoty wiek holenderski", "dutch golden age"),
    _t("style:renaissance", "Renesans", "renaissance"),
    _t("style:gothic", "Gotyk", "gothic"),
    # Subjects
    _t("subject:landscape", "Pejzaż", "landscape*"),
    _t(
        "subject:sea",
        "Morze",
        "sea",
        "seascape*",
        "marine",
        "ocean*",
        "coast*",
        "shore*",
        "beach*",
        "waves",
    ),
    _t("subject:ships", "Statki i łodzie", "ship*", "boat*", "sailing", "harbor*", "harbour*"),
    _t("subject:rivers", "Rzeki i jeziora", "river*", "lake*", "canal*", "waterfall*"),
    _t("subject:mountains", "Góry", "mountain*", "alps", "alpine", "fuji", "tatra*"),
    _t("subject:winter", "Zima i śnieg", "snow*", "winter*", "ice", "skating"),
    _t("subject:night", "Noc i księżyc", "night*", "nocturne*", "moon*", "evening"),
    _t("subject:sky", "Niebo i chmury", "cloud*", "sky", "skies", "sunset*", "sunrise*"),
    _t("subject:trees", "Drzewa i las", "tree*", "forest*", "woods", "woodland*", "birch*"),
    _t(
        "subject:flowers",
        "Kwiaty",
        "flower*",
        "floral",
        "bouquet*",
        "rose",
        "peony",
        "peonies",
        "iris",
        "irises",
        "lily",
        "lilies",
        "chrysanthemum*",
        "tulip*",
        "poppy",
        "poppies",
        "sunflower*",
    ),
    _t("subject:botany", "Botanika", "botanical", "botany", "plant*"),
    _t("subject:gardens", "Ogrody i parki", "garden*", "park"),
    _t(
        "subject:birds",
        "Ptaki",
        "bird*",
        "heron*",
        "crane",
        "cranes",
        "owl*",
        "parrot*",
        "rooster*",
        "duck*",
    ),
    _t(
        "subject:animals",
        "Zwierzęta",
        "animal*",
        "horse*",
        "dog",
        "dogs",
        "cat",
        "cats",
        "cattle",
        "cow*",
        "sheep",
        "deer",
        "tiger*",
    ),
    _t("subject:still-life", "Martwa natura", "still life", "still-life", "nature morte"),
    _t("subject:portrait", "Portret", "portrait*"),
    _t("subject:women", "Kobiety", "woman", "women", "lady", "ladies", "girl*"),
    _t("subject:children", "Dzieci", "child", "children", "boy", "boys"),
    _t(
        "subject:city",
        "Miasto i ulica",
        "cityscape*",
        "city",
        "cities",
        "street*",
        "town*",
        "urban",
        "boulevard*",
    ),
    _t(
        "subject:architecture",
        "Architektura",
        "architecture",
        "cathedral*",
        "church*",
        "castle*",
        "bridge*",
        "temple*",
    ),
    _t("subject:interior", "Wnętrza", "interior*", "room"),
    _t(
        "subject:everyday",
        "Codzienność",
        "genre scene*",
        "genre painting*",
        "everyday life",
        "daily life",
        "domestic",
    ),
    _t("subject:work", "Praca i wieś", "peasant*", "harvest*", "farm*", "labor*", "labour*"),
    _t("subject:music-dance", "Muzyka i taniec", "music*", "danc*"),
    _t("subject:mythology", "Mitologia", "mythology", "mythological", "myth", "nymph*", "venus"),
    _t(
        "subject:religion",
        "Religia",
        "religious",
        "christ",
        "madonna",
        "virgin and child",
        "saint*",
        "biblical",
        "annunciation",
    ),
    _t("subject:history", "Historia i bitwy", "battle*", "war", "soldier*", "cavalry"),
    _t("subject:hunting", "Polowanie", "hunt*"),
    _t("subject:theatre", "Teatr i aktorzy", "kabuki", "actor*", "theater", "theatre"),
    # Periods
    _p("period:medieval", "Średniowiecze", None, 1399),
    _p("period:15c", "XV wiek", 1400, 1499),
    _p("period:16c", "XVI wiek", 1500, 1599),
    _p("period:17c", "XVII wiek", 1600, 1699),
    _p("period:18c", "XVIII wiek", 1700, 1799),
    _p("period:1800-1850", "1800–1850", 1800, 1849),
    _p("period:1850-1900", "1850–1900", 1850, 1899),
    _p("period:belle-epoque", "Belle Époque", 1880, 1914),
    _p("period:1900-1930", "1900–1930", 1900, 1930),
    # Techniques
    _t(
        "technique:painting",
        "Obrazy",
        "painting*",
        "oil on",
        "tempera",
        "schilderij*",
        "obraz",
    ),
    _t(
        "technique:print",
        "Grafika",
        "print",
        "woodblock*",
        "woodcut*",
        "engraving*",
        "etching*",
        "aquatint*",
        "drypoint*",
        "mezzotint*",
        "lithograph*",
        "chromolithograph*",
        "screenprint*",
        "linocut*",
        "prent*",
        "drzeworyt*",
    ),
    _t(
        "technique:drawing",
        "Rysunki i akwarele",
        "drawing*",
        "watercolo*",
        "gouache",
        "chalk",
        "graphite",
        "pastel",
        "tekening*",
        "rysun*",
    ),
    _t("technique:poster", "Plakaty", "poster*", "affiche*", "plakat*"),
    _t(MANUSCRIPTS, "Rękopisy i miniatury", "manuscript*"),
]

BY_KEY = {term.key: term for term in TERMS}
_YEARS = re.compile(r"^years:(\d{1,4})?-(\d{1,4})?$")

#: Pages of manuscripts, codices and albums: mostly script in a narrow
#: column, which the frame leaves out unless asked for.
_MANUSCRIPT = re.compile(
    r"\b(manuscripts?|codex|codices|books? of hours|psalters?|antiphon\w*|graduals?|missals?|"
    r"breviar\w*|qur'?an|koran|shah-?nam\w*|bifoli\w*|folios?|calligraph\w*|"
    r"(?:leaf|leaves|pages?|folios?) from|r[eę]kopis\w*|handschrift\w*)\b",
    re.IGNORECASE,
)


def is_manuscript(item: Item) -> bool:
    return _is_manuscript(item.classification, item.title, item.medium)


# Asked of every work on every query of the catalogue: remembered by text.
@lru_cache(maxsize=1 << 15)
def _is_manuscript(classification: str, title: str, medium: str) -> bool:
    return bool(_MANUSCRIPT.search(" ".join((classification, title, medium))))


#: Photographs in the museums' collections, by department or process; the
#: frame is for paintings, prints and drawings. ("Photomechanical" and
#: "photolithograph" posters stay.)
_PHOTOGRAPH = re.compile(
    r"\b(photograph(?:s|y|ic)?|fotografi\w*|gelatin[- ]silver|albumen|daguerreotype|ambrotype|"
    r"tintype|cyanotype|salted[- ]paper|platinum print|palladium print|chromogenic|"
    r"inkjet print|carte[- ]de[- ]visite|cabinet card|stereograph\w*|collodion|photogravure)\b",
    re.IGNORECASE,
)


def is_photograph(item: Item) -> bool:
    """A museum's photograph (never the owner's own photos)."""
    return item.kind == ItemKind.ARTWORK and _is_photograph(item.classification, item.medium)


@lru_cache(maxsize=1 << 15)
def _is_photograph(classification: str, medium: str) -> bool:
    return bool(_PHOTOGRAPH.search(" ".join((classification, medium))))


def set_aside(item: Item, keys: list[str] | tuple[str, ...] = ()) -> bool:
    """Left out of the catalogue and searches: photographs always, pages of
    manuscripts unless ``keys`` ask for them."""
    return is_photograph(item) or (is_manuscript(item) and not wants_manuscripts(keys))


def term(key: str) -> Term | None:
    """A term by its key; ``years:A-B`` makes one on the fly."""
    if key in BY_KEY:
        return BY_KEY[key]
    match = _YEARS.match(key)
    if match is None:
        return None
    start, end = (int(g) if g else None for g in match.groups())
    if start is None and end is None:
        return None
    name = f"{start or ''}–{end or ''}" if start != end else str(start)
    return Term(key, name, year_from=start, year_to=end)


def _text(item: Item) -> str:
    return " ".join(
        (
            item.title,
            item.classification,
            item.medium,
            item.culture,
            item.description,
            *item.styles,
            *item.subjects,
        )
    )


def term_matches(found: Term, item: Item, text: str | None = None) -> bool:
    if found.key == MANUSCRIPTS:
        return is_manuscript(item)
    if found.year_from is not None or found.year_to is not None:
        if item.year is None:
            return False
        if found.year_from is not None and item.year < found.year_from:
            return False
        return found.year_to is None or item.year <= found.year_to
    pattern = found.pattern
    return pattern is not None and bool(pattern.search(text if text is not None else _text(item)))


def grouped(keys: list[str]) -> dict[str, list[Term]]:
    """Known terms by kind (periods and ``years:`` together)."""
    groups: dict[str, list[Term]] = {}
    for key in keys:
        found = term(key)
        if found is not None:
            kind = "period" if found.kind == "years" else found.kind
            groups.setdefault(kind, []).append(found)
    return groups


@lru_cache(maxsize=256)
def _grouped(keys: tuple[str, ...]) -> dict[str, list[Term]]:
    """``grouped`` for every work of a query: worked out once."""
    return grouped(list(keys))


def matches_terms(item: Item, keys: list[str]) -> bool:
    """Every kind of term in ``keys`` has one that fits ``item``."""
    groups = _grouped(tuple(keys))
    if not groups:
        return True
    text = _text(item)
    return all(any(term_matches(t, item, text) for t in terms) for terms in groups.values())


def wants_manuscripts(keys: list[str] | tuple[str, ...]) -> bool:
    return MANUSCRIPTS in keys


def years(keys: list[str]) -> tuple[int | None, int | None]:
    """The span the period terms cover, to ask museums for."""
    periods = grouped(keys).get("period", [])
    if not periods:
        return None, None
    starts = [p.year_from for p in periods]
    ends = [p.year_to for p in periods]
    return (
        None if None in starts else min(s for s in starts if s is not None),
        None if None in ends else max(e for e in ends if e is not None),
    )


def museum_kind(keys: list[str]) -> Kind:
    """The one technique museums can filter by, else ``any``."""
    kinds = [TECHNIQUE_KINDS[k] for k in keys if k in TECHNIQUE_KINDS]
    return kinds[0] if len(kinds) == 1 else "any"


def museum_queries(keys: list[str], limit: int = 6) -> list[str]:
    """Texts to ask museums for: one word of each style and subject, in
    every combination (an impressionist sea: ``impressionism sea``). Such
    pairs find few works, so each word alone follows; what comes back is
    checked against every term anyway."""
    groups = grouped(keys)
    words = [[t.query for t in groups[k] if t.query] for k in ("style", "subject") if k in groups]
    words = [w for w in words if w]
    if not words:
        return []
    texts = [" ".join(combo) for combo in product(*words)][:limit]
    if len(words) > 1:
        texts += [w for group in words for w in group if w not in texts]
    return texts


def fold(text: str) -> str:
    """Lower case without accents, for matching what people type."""
    decomposed = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


@cache
def name_words(name: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", fold(name)))


def artist_matches(artist: str, wanted: list[str]) -> bool:
    """``artist`` is one of ``wanted``, also when a museum spells the name
    out in full: "Hokusai" fits "Katsushika Hokusai"."""
    have = name_words(artist)
    return bool(have) and any(name_words(w) and name_words(w) <= have for w in wanted)


def suggest(text: str, limit: int = 8) -> list[Term]:
    """Terms whose name or museum words start like ``text``."""
    wanted = fold(text.strip())
    if not wanted:
        return []
    starts, contains = [], []
    for found in TERMS:
        name = fold(found.name)
        words = [fold(w.rstrip("*")) for w in found.words]
        names = [name, *name.split()]
        if any(n.startswith(wanted) for n in names) or any(w.startswith(wanted) for w in words):
            starts.append(found)
        elif wanted in name or (len(wanted) >= 4 and any(wanted in w for w in words)):
            contains.append(found)
    match = re.match(r"^(\d{4})\s*(?:[-–]\s*(\d{4}))?$", text.strip())
    if match:
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start // 10 * 10 + 9
        start = start if match.group(2) else start // 10 * 10
        starts.insert(0, term(f"years:{start}-{end}") or Term("", ""))
    return (starts + contains)[:limit]
