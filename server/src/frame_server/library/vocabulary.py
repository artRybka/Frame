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
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date
from functools import cache, cached_property, lru_cache
from itertools import product
from typing import Literal
from urllib.parse import urlsplit

from .models import ART_PHOTO_ARCHIVES, Item, ItemKind
from .museums import Kind

TermKind = Literal["style", "subject", "period", "technique", "tag"]
Region = Literal["antiquity", "europe", "poland", "east-asia"]
#: discovery kinds (museums.Kind) of techniques that museums can filter by.
TECHNIQUE_KINDS: dict[str, Kind] = {
    "technique:painting": "painting",
    "technique:print": "print",
    "technique:drawing": "drawing",
    "technique:poster": "poster",
    "technique:photography": "photograph",
    "technique:sculpture": "sculpture",
    "technique:decorative": "decorative",
    "technique:manuscripts": "manuscript",
}
MANUSCRIPTS = "technique:manuscripts"
PHOTOGRAPHY = "technique:photography"
SCULPTURE = "technique:sculpture"
DECORATIVE = "technique:decorative"
#: Works their museum counts among its most important (``Item.highlight``).
HIGHLIGHT = "tag:highlight"
#: Photographs in colour from colour processes (autochromes, photochroms,
#: three-colour plates, colour slides): not hand-coloured ones, which a
#: colour check alone takes too (Mateusz 2026-11-07: "Pierwsze kolory"
#: showed painted album pages and portraits). Kept out of :data:`TERMS`
#: (not a suggestion in Szukaj); :func:`term` knows it.
EARLY_COLOUR = "tag:early-colour"
#: Works that are not pictures: shown only when one of these is asked for.
OBJECT_CATEGORIES = (MANUSCRIPTS, PHOTOGRAPHY, SCULPTURE, DECORATIVE)

#: Size of the caches of what a work's texts say (``is_manuscript``,
#: ``object_category``…), asked of every work on every query of the
#: catalogue: above the number of works the catalogue holds. A smaller LRU
#: cache scanned in order over more works keeps none of them (51 000 works
#: on the NAS, 2026-11-06: every query of the catalogue ran each regular
#: expression again, 2–3 s a query).
PER_WORK = 1 << 18


@dataclass(frozen=True)
class Term:
    key: str
    name: str
    #: Matched as whole words (an "s" or "es" plural allowed); a trailing
    #: ``*`` matches any ending. The first word is what museums are asked.
    words: tuple[str, ...] = ()
    year_from: int | None = None
    year_to: int | None = None
    #: A named period's group in the app's Epoka sheet ("europe", "poland",
    #: "east-asia"); the pieces of the time line have none.
    region: Region | None = None
    #: A period of one country's history (a key of :data:`PLACES`): its
    #: works must come from there too, or "Edo" would catch Rembrandt.
    place: str | None = None

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


def _named(
    key: str, name: str, year_from: int, year_to: int, region: Region, place: str | None = None
) -> Term:
    return Term(key, name, year_from=year_from, year_to=year_to, region=region, place=place)


#: Where a work comes from, for the periods of one country: the word to ask
#: museums with, and what its author's bio, culture, museum or style says.
#: Never the title ("The Polish Rider" is Rembrandt's).
PLACES: dict[str, tuple[str, re.Pattern[str]]] = {
    "poland": (
        "polish",
        re.compile(
            r"\b(polish|poland|polsk\w*|polen|polnisch\w*|pologne|polonais\w*|muzeum|"
            r"warsaw|warszaw\w*|cracow|krak[oó]w\w*|krakau|pozna[nń]\w*|wroc[lł]aw\w*|"
            r"gda[nń]sk\w*|l[oó]d[zź]\w*|lw[oó]w\w*|lviv|wilno|young poland)\b",
            re.IGNORECASE,
        ),
    ),
    "japan": (
        "japanese",
        re.compile(r"\b(japan\w*|japon\w*|nippon|ukiyo-?e|ukiyoe|shin[- ]?hanga)\b", re.IGNORECASE),
    ),
    "china": (
        "chinese",
        re.compile(
            r"\b(china|chinese|chiny|chi[nń]sk\w*|chinesisch\w*|chinois\w*)\b", re.IGNORECASE
        ),
    ),
    # Antiquity's, as museums write a work's culture ("Egyptian", "Greek,
    # Attic", "Roman", "Byzantine") in English, French, German or Polish.
    "egypt": (
        "egyptian",
        re.compile(r"\b(egypt\w*|[ée]gypt\w*|[äa]gypt\w*|egipt\w*|fayum|faiyum)\b", re.IGNORECASE),
    ),
    "greece": (
        "greek",
        re.compile(
            r"\b(greek|greece|grec\w*|griech\w*|grecj\w*|greck\w*|attic|hellenistic|"
            r"corinthian|boeotian|cycladic|minoan|mycenaean)\b",
            re.IGNORECASE,
        ),
    ),
    "rome": (
        "roman",
        re.compile(
            # Dura-Europos: a Roman garrison town (Yale: "Syrian, Dura-Europos").
            r"\b(roman|romain\w*|r[öo]misch\w*|rzymsk\w*|pompeii\w*|pomp[eé]i\w*|"
            r"dura[- ]europos)\b",
            re.IGNORECASE,
        ),
    ),
    "byzantium": (
        "byzantine",
        re.compile(r"\b(byzantin\w*|bizanty\w*|constantinople)\b", re.IGNORECASE),
    ),
}
#: Styles that tell the place on their own.
_PLACE_TERMS = {
    "poland": ("style:young-poland",),
    "japan": ("style:ukiyo-e", "style:shin-hanga", "style:rinpa"),
    "china": (),
    "egypt": (),
    "greece": (),
    "rome": (),
    "byzantium": (),
}


TERMS: list[Term] = [
    # Styles and movements
    _t("style:impressionism", "Impresjonizm", "impressionism", "impressionist*"),
    _t(
        "style:post-impressionism",
        "Postimpresjonizm",
        "post-impressionism",
        "post-impressionist*",
        "postimpression*",
    ),
    _t(
        "style:pointillism",
        "Puentylizm",
        "pointillism",
        "pointillis*",
        "neo-impression*",
        "divisionism",
        "divisionis*",
        "puentylizm",
    ),
    _t("style:ukiyo-e", "Ukiyo-e", "ukiyo-e", "ukiyoe", "ukiyo"),
    _t("style:shin-hanga", "Shin-hanga", "shin-hanga", "shin hanga"),
    _t("style:rinpa", "Rinpa", "rinpa", "rimpa"),
    _t("style:romanticism", "Romantyzm", "romanticism", "romantic"),
    _t("style:realism", "Realizm", "realism", "realist"),
    _t("style:barbizon", "Szkoła z Barbizonu", "barbizon"),
    _t(
        "style:munich-school",
        "Szkoła monachijska",
        "munich school",
        "szkoła monachijska",
        "münchner schule",
    ),
    _t("style:orientalism", "Orientalizm", "orientalism", "orientalist*", "orientalizm"),
    _t("style:japonisme", "Japonizm", "japonisme", "japonism", "japonizm"),
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
    _t("style:futurism", "Futuryzm", "futurism", "futurist*", "futuryzm"),
    _t("style:dada", "Dadaizm", "dada", "dadaism", "dadaist*", "dadaizm"),
    _t("style:surrealism", "Surrealizm", "surrealism", "surrealist*", "surrealizm"),
    _t(
        "style:new-objectivity",
        "Nowa Rzeczowość",
        "new objectivity",
        "neue sachlichkeit",
        "nowa rzeczowość",
    ),
    _t("style:tonalism", "Tonalizm", "tonalism", "tonalist"),
    _t("style:hudson-river", "Szkoła znad rzeki Hudson", "hudson river school"),
    _t("style:young-poland", "Młoda Polska", "young poland", "młoda polska"),
    _t(
        "style:abstraction",
        "Abstrakcja",
        "abstraction",
        "abstract art",
        "abstract composition*",
        "abstract painting*",
        "non-objective",
        "abstrakcj*",
    ),
    _t(
        "style:constructivism",
        "Konstruktywizm i suprematyzm",
        "constructivism",
        "constructivist*",
        "suprematism",
        "suprematist*",
        "unism",
        "unizm",
        "konstruktywizm",
    ),
    _t("style:de-stijl", "De Stijl", "de stijl", "neoplasticism", "neo-plasticism"),
    _t("style:bauhaus", "Bauhaus", "bauhaus"),
    _t("style:academic", "Akademizm", "academic art", "academicism", "academism"),
    _t("style:neoclassicism", "Klasycyzm", "neoclassicism", "neoclassical", "neo-classical"),
    _t("style:rococo", "Rokoko", "rococo"),
    _t("style:baroque", "Barok", "baroque"),
    _t("style:dutch-golden-age", "Złoty wiek holenderski", "dutch golden age"),
    _t("style:renaissance", "Renesans", "renaissance"),
    _t("style:mannerism", "Manieryzm", "mannerism", "mannerist*", "manieryzm"),
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
    # Periods: the pieces of the time line, one after another
    _p("period:ancient", "Starożytność", None, 499),
    _p("period:medieval", "Średniowiecze", 500, 1399),
    _p("period:15c", "XV wiek", 1400, 1499),
    _p("period:16c", "XVI wiek", 1500, 1599),
    _p("period:17c", "XVII wiek", 1600, 1699),
    _p("period:18c", "XVIII wiek", 1700, 1799),
    _p("period:1800-1850", "1800–1850", 1800, 1849),
    _p("period:1850-1900", "1850–1900", 1850, 1899),
    _p("period:1900-1930", "1900–1930", 1900, 1930),
    _p("period:1930-1945", "1930–1945", 1930, 1944),
    # Up to this year: with "Użytek prywatny" sources give works still in
    # copyright too; without it they give only free ones anyway. (Until
    # 1.111.0 it ended with the last free death year, 1955 in 2026.)
    _p("period:post-1945", "Po 1945", 1945, date.today().year),
    # Named periods across them. Renesans, Barok, Romantyzm or Młoda Polska
    # are styles already. Europe's are years only; antiquity's, Poland's,
    # Japan's and China's need the place too. Years before Christ are
    # negative, as works' years are (louvre.french_years).
    _named("period:egypt", "Starożytny Egipt", -3100, -30, "antiquity", "egypt"),
    _named("period:greece", "Starożytna Grecja", -800, -31, "antiquity", "greece"),
    _named("period:rome", "Starożytny Rzym", -509, 476, "antiquity", "rome"),
    _named("period:byzantium", "Bizancjum", 330, 1453, "antiquity", "byzantium"),
    _named("period:thirty-years-war", "Wojna trzydziestoletnia", 1618, 1648, "europe"),
    _named("period:enlightenment", "Oświecenie", 1715, 1789, "europe"),
    _named("period:napoleonic", "Epoka napoleońska", 1799, 1815, "europe"),
    _named("period:biedermeier", "Biedermeier", 1815, 1848, "europe"),
    _named("period:victorian", "Epoka wiktoriańska", 1837, 1901, "europe"),
    _named("period:belle-epoque", "Belle Époque", 1880, 1914, "europe"),
    _named("period:great-war", "Wielka Wojna", 1914, 1918, "europe"),
    _named("period:interwar", "Międzywojnie", 1918, 1939, "europe"),
    _named("period:twenties", "Lata dwudzieste", 1920, 1929, "europe"),
    _named("period:ww2", "II wojna światowa", 1939, 1945, "europe"),
    _named("period:pl-golden-age", "Złoty wiek", 1506, 1572, "poland", "poland"),
    _named("period:pl-saxon", "Czasy saskie", 1697, 1763, "poland", "poland"),
    _named("period:pl-stanislaus", "Czasy stanisławowskie", 1764, 1795, "poland", "poland"),
    _named("period:pl-partitions", "Zabory", 1795, 1918, "poland", "poland"),
    _named("period:pl-second-republic", "II Rzeczpospolita", 1918, 1939, "poland", "poland"),
    _named("period:edo", "Edo", 1603, 1868, "east-asia", "japan"),
    _named("period:meiji", "Meiji", 1868, 1912, "east-asia", "japan"),
    _named("period:taisho", "Taishō", 1912, 1926, "east-asia", "japan"),
    _named("period:ming", "Ming", 1368, 1644, "east-asia", "china"),
    _named("period:qing", "Qing", 1644, 1912, "east-asia", "china"),
    # Techniques
    _t(
        "technique:painting",
        "Malarstwo",
        "painting*",
        "oil on",
        "tempera",
        "fresco*",
        "encaustic",
        # The V&A's types: "Icon", "Coloured wax on panel" (Fayum).
        "icon",
        "icons",
        "wax on panel",
        "mummy portrait*",
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
    _t(PHOTOGRAPHY, "Fotografia", "photograph*", "fotografi*"),
    _t(SCULPTURE, "Rzeźba", "sculpture*", "rzeźb*", "statue*"),
    _t(
        DECORATIVE,
        "Ceramika i rzemiosło",
        "ceramic*",
        "ceramik*",
        "porcelain",
        "porcelan*",
        "textile*",
        "tkanin*",
        "rzemiosło",
    ),
    # What museums say about their works
    Term(HIGHLIGHT, "Arcydzieła muzeów"),
]

BY_KEY = {term.key: term for term in TERMS}
BY_KEY[EARLY_COLOUR] = _t(
    EARLY_COLOUR,
    "Wczesna fotografia barwna",
    "autochrome*",
    "photochrom*",
    "three-color",
    "three-colour",
    "kodachrome",
    "dufaycolor",
    "agfacolor",
    "slide : color",
    "transparency : color",
)
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
@lru_cache(maxsize=PER_WORK)
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


@lru_cache(maxsize=PER_WORK)
def _is_photograph(classification: str, medium: str) -> bool:
    return bool(_PHOTOGRAPH.search(" ".join((classification, medium))))


#: Copies of works rather than the works: plates of exhibition albums,
#: pages of books and magazines, glass and lantern slides, postcards of
#: paintings. (Postcards in English stay: artists designed many, e.g. for
#: the Wiener Werkstätte.)
_REPRODUCTION = re.compile(
    r"\b(reprodu[ckz]\w*|glass[- ]slides?|lantern[- ]slides?|slides? \(photographs\)|"
    r"diapozytyw\w*|przezrocz\w*|glasdia\w*|pocztówk\w*|ansichtskarte\w*)\b"
    # "Wspomnienie (page 41 crop)", "Tygodnik Ilustrowany (strona 5)".
    r"|\((?:page|pages|p\.|strona|str\.|s\.|seite|tabl?\.?|tablica|plansza) ?\d+"
    # Leuven's glass slides: "Jozef Chelmonski. Aanval van wolven, GD017005".
    r"|, GD\d{6}\b",
    re.IGNORECASE,
)


def is_reproduction(item: Item) -> bool:
    """A plate, page, slide or postcard reproducing a work, by its title
    and type (the medium is left alone: "photomechanical reproduction" is
    how museums describe posters)."""
    return item.kind == ItemKind.ARTWORK and _is_reproduction(item.title, item.classification)


@lru_cache(maxsize=PER_WORK)
def _is_reproduction(title: str, classification: str) -> bool:
    return bool(_REPRODUCTION.search(f"{title} {classification}"))


#: Words for paintings in museums' types and materials.
_PAINTING = re.compile(
    r"\b(paintings?|oil|oils|olej\w*|tempera|canvas|płótn\w*|gouache|acrylic|fresco|encaustic)\b",
    re.IGNORECASE,
)
#: Pictures with less tint spread (``colors.tint_spread``) have no colour of
#: their own: a painting like that is a black-and-white copy (an album
#: plate, a slide, an old photo of it); real grisailles are rare. Muted
#: paintings (Chełmoński's "Wrony", 0.0055) stay above it.
GREY_PAINTING_SPREAD = 0.005


def is_grey_painting(item: Item, spread: float | None = None) -> bool:
    """A painting whose picture has no colour: a black-and-white copy.
    ``spread`` stands in for the item's own ``tint_spread`` when given."""
    if spread is None:
        spread = item.tint_spread
    return spread is not None and spread < GREY_PAINTING_SPREAD and is_painting(item)


#: Europeana's providers whose pictures are photographs of works taken by an
#: art history photo archive, not the museums' own scans: Bildarchiv Foto
#: Marburg (half of them old black-and-white prints on a catalogue card with
#: the negative number typed below) and Brussels' KIK-IRPA. A black-and-white
#: one is a copy whatever the work, since the paper, chalk or ink colours of
#: a drawing or print are lost too. Their colour photographs are often old
#: slides whose dyes have faded (Marburg's "fmc…" van Goghs: no yellow left,
#: skies white and blue, Mateusz 2026-11-09): any other source's copy comes
#: first (``duplicates.item_rank``) and takes their place in other colours
#: (``sharper``). Marburg is no longer asked (``Europeana.not_art``, 2026-11-09);
#: its works kept before stay. Nor do they name the museum the work is in
#: (``Item.held_by``). As ``Item.credit`` names them: ``models.ART_PHOTO_ARCHIVES``.


def is_art_archive_photo(item: Item) -> bool:
    """A photograph of a work from an art history photo archive."""
    return item.source == "europeana" and item.credit in ART_PHOTO_ARCHIVES


def may_be_grey_copy(item: Item) -> bool:
    """A work whose picture, if it has no colour, is a black-and-white copy:
    a painting, or anything an art photo archive has. (Real prints and
    drawings are often colourless; their museums' scans stay.)"""
    return is_painting(item) or is_art_archive_photo(item)


def is_grey_copy(item: Item, spread: float | None = None) -> bool:
    """A black-and-white copy of a work (:func:`may_be_grey_copy` with a
    picture of no colour). ``spread`` stands in for the item's own
    ``tint_spread`` when given."""
    if spread is None:
        spread = item.tint_spread
    return spread is not None and spread < GREY_PAINTING_SPREAD and may_be_grey_copy(item)


def is_painting(item: Item) -> bool:
    """A museum work its museum calls a painting (by type or material)."""
    return item.kind == ItemKind.ARTWORK and _is_painting(item.classification, item.medium)


@lru_cache(maxsize=PER_WORK)
def _is_painting(classification: str, medium: str) -> bool:
    return bool(_PAINTING.search(f"{classification} {medium}"))


#: Europeana datasets of photo archives that call their photographs
#: paintings, prints and posters: the city of Girona's (football teams, film
#: stills, festival programmes, photographs of pictures; all by "Desconegut").
PHOTO_ARCHIVES = frozenset({"718", "2024914"})


def is_archive_photo(item: Item) -> bool:
    return item.source == "europeana" and item.source_id.split("~")[0] in PHOTO_ARCHIVES


#: Europeana's providers of objects that are no pictures, whatever type
#: they give: Athens' Philatelic Postal Museum (stamps, first-day covers,
#: proofs, all "prints"), as ``Item.credit`` names them.
NOT_ART_PROVIDERS = frozenset({"Philatelic Postal Museum"})
#: Museums' types of stamps, banknotes and the post's papers.
_POSTAL = re.compile(
    r"\b(stamps?|postage|postal|philatel\w*|postmarks?|first[- ]day covers?|bank ?notes?|"
    r"znacz(?:ek|k\w*)|filatel\w*|banknot\w*|γραμματόσημ\w*)\b",
    re.IGNORECASE,
)


def is_postal(item: Item) -> bool:
    """A stamp, banknote or envelope, or a work of a provider of nothing
    else: a photograph of an object, never a picture for the frame."""
    if item.source == "europeana" and item.credit in NOT_ART_PROVIDERS:
        return True
    return item.kind == ItemKind.ARTWORK and _is_postal(item.classification)


@lru_cache(maxsize=PER_WORK)
def _is_postal(classification: str) -> bool:
    return bool(_POSTAL.search(classification))


#: A part of a work cut out of its picture, as titles of the sources that
#: gather pictures say it: Commons' "Young Woman with a Water Jug (detal)",
#: "Girl reading a Letter…, detail", WikiArt's "The Procuress, detail
#: (supposed self-portrait)" (Vermeer, Mateusz 2026-11-09). The word comes
#: first or after a bracket, comma or dash: a museum's "Architectural
#: Detail" is a drawing of its own (and museums are not asked by title
#: here at all). "Fragment" counts only at the very end.
_DETAIL = re.compile(
    r"(?:^|[,;:(\[]|\s[-–—])\s*(?:details?|detal\w*|szczeg[oó]ł\w*|d[ée]tails?|dettagli?o?|"
    r"detalles?|ausschnitt\w*|teilansicht\w*|uitsnede)\b"
    r"|(?:[,(\[]|\s[-–—])\s*fragm\w*\s*[)\]]?\s*$",
    re.IGNORECASE,
)
#: Sources that gather pictures from elsewhere, whose details of works are
#: files like any other.
GATHERED = frozenset({"wmc", "wikiart", "europeana", "openverse"})


def is_detail(item: Item) -> bool:
    """A detail of a work: its title says so (:data:`GATHERED` sources), or
    its picture was found inside another copy's (``Item.detail_of``,
    ``library.twins``). The catalogue's own fragments of tile sets
    (``Item.part_of``) are not."""
    if item.kind != ItemKind.ARTWORK or item.part_of:
        return False
    if item.detail_of:
        return True
    return item.source in GATHERED and _is_detail(item.title)


@lru_cache(maxsize=PER_WORK)
def _is_detail(title: str) -> bool:
    return bool(_DETAIL.search(title.split("\n")[0]))


#: Openverse's copies of works the server has from their museums directly:
#: rawpixel's (pictures of 1024 px, "Young Woman Water Pitcher" by "themet",
#: 15 of the 20 new works a search for Vermeer showed, 2026-11-09) and
#: those of the museums' own pages it passes on.
OPENVERSE_COPIES = (
    "rawpixel.com",
    "metmuseum.org",
    "clevelandart.org",
    "artic.edu",
    "rijksmuseum.nl",
    "smk.dk",
    "nga.gov",
)


def is_openverse_copy(item: Item) -> bool:
    """A work from Openverse that is a copy of one the server asks its
    museum for itself (:data:`OPENVERSE_COPIES`)."""
    if item.source != "openverse":
        return False
    host = (urlsplit(item.url).hostname or "").casefold().removeprefix("www.")
    return any(host == h or host.endswith(f".{h}") for h in OPENVERSE_COPIES)


def is_copy(item: Item) -> bool:
    """A reproduction of a work in print or on a slide, a photograph
    Openverse has from Flickr or one from a photo archive, a stamp, a
    black-and-white photograph of a work, a detail of a work, Openverse's
    copy of a museum's work: never what the frame looks for."""
    return (
        (is_photograph(item) and item.source == "openverse")
        or is_openverse_copy(item)
        or is_detail(item)
        or is_archive_photo(item)
        or is_postal(item)
        or is_reproduction(item)
        or is_grey_copy(item)
    )


#: Museums' types of sculpture and of decorative arts; a type that names a
#: picture technique comes first ("Miniature Painting").
_SCULPTURE = re.compile(
    r"\b(sculptures?|statues?|statuettes?|busts?|reliefs?|figur\w*|netsuke|beeld\w*|rzeźb\w*)\b",
    re.IGNORECASE,
)
_DECORATIVE = re.compile(
    r"\b(ceramics?|porcelain|stoneware|earthenware|pottery|faience|vessels?|vases?|bowls?|"
    r"dish(?:es)?|cups?|pots?|ewers?|jars?|jugs?|pitchers?|platters?|saucers?|aquamanile|"
    r"textiles?|tapestr\w*|embroider\w*|lace|velvet|costumes?|dress\w*|\w*wear|accessor\w*|"
    r"fans?|furniture|metalwork|"
    r"silver|glass|jewel\w*|enamels?|lacquer|jade|arms|armou?r|coins?|medals?|amulets?|"
    r"glyptic|tools|funerary|ritual|miscellaneous|ceramik\w*|porcelan\w*|tkanin\w*|rzemiosło|"
    # A whole mummy with its portrait inserted is no picture; a mummy
    # portrait (the V&A's type of a Fayum panel) is.
    r"mumm(?:y|ies)(?!\s+portraits?)|human remains)\b",
    re.IGNORECASE,
)


#: Wall paintings, as museums write them.
_MURAL = re.compile(r"\b(fresco(?:es|s)?|wall paintings?|murals?|fresk\w*)\b", re.IGNORECASE)


def object_category(item: Item) -> str | None:
    """Which of :data:`OBJECT_CATEGORIES` a museum work belongs to; None for
    a picture (a painting, print, drawing or poster, or a work its museum
    says nothing about)."""
    if item.kind != ItemKind.ARTWORK:
        return None
    return _object_category(item.classification, item.title, item.medium)


@lru_cache(maxsize=PER_WORK)
def _object_category(classification: str, title: str, medium: str) -> str | None:
    if _is_manuscript(classification, title, medium):
        return MANUSCRIPTS
    if _is_photograph(classification, medium):
        return PHOTOGRAPHY
    if _object_technique(classification, ""):
        return None
    # The Met files Boscoreale's walls as "Miscellaneous-Stone": a fresco
    # is a picture whatever its museum's type.
    if _MURAL.search(f"{classification} {medium} {title}"):
        return None
    if _SCULPTURE.search(classification):
        return SCULPTURE
    if _DECORATIVE.search(classification):
        return DECORATIVE
    return None


def other_art(item: Item) -> bool:
    """A work of "Sztuki inne" (a manuscript, photograph, sculpture or piece
    of decorative art): it keeps to its own group in Odkrywaj, Szukaj with
    its technique and playlists that ask for it, never a study, the work of
    the day or Discover's other cards (Mateusz 2026-11-06, "własny sos")."""
    return object_category(item) is not None


def set_aside(item: Item, keys: list[str] | tuple[str, ...] = ()) -> bool:
    """Left out of the catalogue and searches: copies always; manuscripts,
    photographs, sculpture and decorative arts unless ``keys`` ask for them."""
    if is_copy(item):
        return True
    category = object_category(item)
    return category is not None and category not in keys


def category_fits(item: Item, keys: list[str] | tuple[str, ...]) -> bool:
    """A work of a museum's search for ``keys``: of a category asked for, or
    a picture while nothing but such categories is asked for as technique
    (rzeźba alone: no paintings)."""
    if set_aside(item, keys):
        return False
    if object_category(item) is not None:
        return True
    asked = [k for k in keys if k in OBJECT_CATEGORIES]
    techniques = [k for k in keys if k.startswith("technique:")]
    return not asked or len(techniques) > len(asked)


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


def text_of(item: Item) -> str:
    """What terms are looked for in."""
    return " ".join(
        (
            item.title,
            item.classification,
            item.medium,
            item.culture,
            item.description,
            *item.styles,
            *item.subjects,
            *item.keywords,
        )
    )


#: Techniques that say what an object is: when its museum's type or
#: material names one of these, that settles its technique.
_OBJECT_TECHNIQUES = ("technique:painting", "technique:print", "technique:drawing")


def _technique_matches(found: Term, item: Item) -> bool:
    """What the museum says the object is, never what its text or the
    model's keywords mention: a Monet drawing whose description talks of
    his paintings, or a caricature tagged "obraz w ramie", is no painting.
    The type and material decide; without a technique there, the title and
    the museum's own tags. Posters are prints, so a print's title may still
    make it one."""
    pattern = found.pattern
    if pattern is None:
        return False
    if pattern.search(f"{item.classification} {item.medium}"):
        return True
    if found.key != "technique:poster" and _object_technique(item.classification, item.medium):
        return False
    return bool(pattern.search(" ".join((item.title, *item.styles, *item.subjects))))


@lru_cache(maxsize=PER_WORK)
def _object_technique(classification: str, medium: str) -> bool:
    text = f"{classification} {medium}"
    return any(
        (pattern := BY_KEY[key].pattern) is not None and pattern.search(text)
        for key in _OBJECT_TECHNIQUES
    )


def term_matches(found: Term, item: Item, text: str | None = None) -> bool:
    if found.key in OBJECT_CATEGORIES:
        return object_category(item) == found.key
    if found.key == HIGHLIGHT:
        return item.highlight
    if found.kind == "technique":
        return _technique_matches(found, item)
    if found.year_from is not None or found.year_to is not None:
        if item.year is None:
            return False
        if found.year_from is not None and item.year < found.year_from:
            return False
        if found.year_to is not None and item.year > found.year_to:
            return False
        return found.place is None or from_place(item, found.place)
    if found.key in item.terms:
        return True
    if found.kind == "style" and _by_style_artist(found, item):
        return True
    pattern = found.pattern
    return pattern is not None and bool(pattern.search(text if text is not None else text_of(item)))


def from_place(item: Item, place: str) -> bool:
    """The work comes from ``place`` (a key of :data:`PLACES`), as its
    author's bio, its culture, museum or styles say."""
    if any(key in item.terms for key in _PLACE_TERMS[place]):
        return True
    pattern = PLACES[place][1]
    text = " ".join((item.artist_bio, item.culture, item.museum, *item.styles))
    return bool(pattern.search(text))


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


#: When each style was made (the app's Styl shelves show the same years;
#: None: still going). A museum's search for "art deco" also finds Rubens
#: and Mucha (Mateusz 2026-11-09), so a dated work must fit one of its
#: styles' years, with :data:`STYLE_EARLY` before and :data:`STYLE_LATE`
#: after: Munch's 1893 Scream is expressionism, Monet's water lilies of
#: the 1910s impressionism.
STYLE_YEARS: dict[str, tuple[int, int | None]] = {
    "style:gothic": (1250, 1500), "style:renaissance": (1400, 1600),
    "style:mannerism": (1520, 1600), "style:dutch-golden-age": (1600, 1690),
    "style:baroque": (1600, 1750), "style:rococo": (1720, 1780),
    "style:neoclassicism": (1760, 1830), "style:romanticism": (1790, 1850),
    "style:hudson-river": (1825, 1875), "style:barbizon": (1830, 1870),
    "style:academic": (1830, 1900), "style:orientalism": (1830, 1900),
    "style:realism": (1840, 1880), "style:pre-raphaelite": (1848, 1900),
    "style:munich-school": (1860, 1900), "style:impressionism": (1867, 1890),
    "style:japonisme": (1860, 1910), "style:tonalism": (1880, 1915),
    "style:symbolism": (1880, 1910), "style:pointillism": (1884, 1910),
    "style:post-impressionism": (1886, 1905), "style:nabis": (1888, 1900),
    "style:art-nouveau": (1890, 1910), "style:young-poland": (1890, 1918),
    "style:fauvism": (1904, 1908), "style:expressionism": (1905, 1925),
    "style:cubism": (1907, 1920), "style:futurism": (1909, 1916),
    "style:abstraction": (1910, None), "style:constructivism": (1913, 1930),
    "style:dada": (1916, 1924), "style:de-stijl": (1917, 1931),
    "style:bauhaus": (1919, 1933), "style:new-objectivity": (1919, 1933),
    "style:art-deco": (1920, 1940), "style:surrealism": (1924, None),
    "style:rinpa": (1600, 1870), "style:ukiyo-e": (1660, 1900),
    "style:shin-hanga": (1915, None),
}  # fmt: skip
STYLE_EARLY = 15
STYLE_LATE = 40


def in_style_years(item: Item, styles: Iterable[str]) -> bool:
    """``item`` was made when one of ``styles`` was (an undated work, or a
    style with no years, always fits)."""
    if item.year is None:
        return True
    styles = list(styles)
    spans = [STYLE_YEARS[key] for key in styles if key in STYLE_YEARS]
    if not spans or len(spans) < len(styles):
        return True
    year = item.year
    return any(
        start - STYLE_EARLY <= year and (end is None or year <= end + STYLE_LATE)
        for start, end in spans
    )


def matches_terms(item: Item, keys: list[str], judged: Collection[str] = ()) -> bool:
    """Every kind of term in ``keys`` has one that fits ``item``; kinds in
    ``judged`` (:func:`searched_kinds`) are not looked at, but a style's
    years always are (:func:`in_style_years`), and a style the museums'
    search judged still needs :func:`searched_style_fits`."""
    styles = [k for k in keys if k.startswith("style:")]
    if styles and not in_style_years(item, styles):
        return False
    groups = _grouped(tuple(keys))
    text = text_of(item)
    if (
        "style" in judged
        and "style" in groups
        and not any(searched_style_fits(t, item, text) for t in groups["style"])
    ):
        return False
    groups = {k: v for k, v in groups.items() if k not in judged}
    return all(any(term_matches(t, item, text) for t in terms) for terms in groups.values())


#: Styles museums don't name and their search doesn't find ("new
#: objectivity" brought Greek pyxides and video art, and with the style's
#: name wanted nothing, Mateusz 2026-11-09): they are asked by their
#: painters, in turns, and a work of theirs from the style's years fits.
STYLE_ARTISTS: dict[str, tuple[str, ...]] = {
    # Museums' words found few or none of these (2026-11-09, every source
    # asked each style's word: AIC, Cleveland, Met, Rijksmuseum, SMK,
    # Openverse, MNW, MNK, Yale, V&A, Getty, Commons, WikiArt).
    "style:dutch-golden-age": (
        "Rembrandt",
        "Johannes Vermeer",
        "Frans Hals",
        "Jacob van Ruisdael",
        "Jan Steen",
        "Pieter de Hooch",
        "Aelbert Cuyp",
        "Gerard ter Borch",
        "Jan van Goyen",
        "Meindert Hobbema",
        "Willem Claesz. Heda",
        "Gabriel Metsu",
    ),
    "style:academic": (
        "William-Adolphe Bouguereau",
        "Alexandre Cabanel",
        "Jean-Léon Gérôme",
        "Lawrence Alma-Tadema",
        "Frederic Leighton",
        "Paul Delaroche",
        "Thomas Couture",
        "Ernest Meissonier",
        "Henryk Siemiradzki",
        "Jean-Paul Laurens",
        "Pierre-Auguste Cot",
        "Jules Breton",
    ),
    "style:hudson-river": (
        "Thomas Cole",
        "Frederic Edwin Church",
        "Albert Bierstadt",
        "Asher Brown Durand",
        "Jasper Francis Cropsey",
        "Sanford Robinson Gifford",
        "John Frederick Kensett",
        "Thomas Moran",
        "Worthington Whittredge",
        "Martin Johnson Heade",
    ),
    "style:pre-raphaelite": (
        "Dante Gabriel Rossetti",
        "John Everett Millais",
        "William Holman Hunt",
        "Edward Burne-Jones",
        "Ford Madox Brown",
        "Arthur Hughes",
        "John William Waterhouse",
        "Frederick Sandys",
        "Evelyn De Morgan",
        "Elizabeth Siddal",
    ),
    "style:munich-school": (
        "Józef Brandt",
        "Alfred Wierusz-Kowalski",
        "Maksymilian Gierymski",
        "Aleksander Gierymski",
        "Władysław Czachórski",
        "Wilhelm Leibl",
        "Wilhelm Trübner",
        "Franz von Lenbach",
        "Karl von Piloty",
        "Franz von Defregger",
    ),
    "style:tonalism": (
        "James McNeill Whistler",
        "George Inness",
        "Dwight William Tryon",
        "Thomas Wilmer Dewing",
        "Alexander Helwig Wyant",
        "Ralph Albert Blakelock",
        "Henry Ward Ranger",
        "John Francis Murphy",
        "Charles Warren Eaton",
        "Birge Harrison",
    ),
    "style:post-impressionism": (
        "Vincent van Gogh",
        "Paul Cézanne",
        "Paul Gauguin",
        "Henri de Toulouse-Lautrec",
        "Émile Bernard",
        "Henri Rousseau",
        "Louis Anquetin",
        "Charles Laval",
    ),
    "style:nabis": (
        "Pierre Bonnard",
        "Édouard Vuillard",
        "Maurice Denis",
        "Paul Sérusier",
        "Paul Ranson",
        "Félix Vallotton",
        "Ker-Xavier Roussel",
        "Henri-Gabriel Ibels",
    ),
    "style:young-poland": (
        "Stanisław Wyspiański",
        "Jacek Malczewski",
        "Józef Mehoffer",
        "Witold Wojtkiewicz",
        "Władysław Podkowiński",
        "Ferdynand Ruszczyc",
        "Teodor Axentowicz",
        "Wojciech Weiss",
        "Jan Stanisławski",
        "Leon Wyczółkowski",
        "Julian Fałat",
        "Olga Boznańska",
    ),
    "style:fauvism": (
        "Henri Matisse",
        "André Derain",
        "Maurice de Vlaminck",
        "Raoul Dufy",
        "Albert Marquet",
        "Georges Braque",
        "Kees van Dongen",
        "Henri Manguin",
        "Charles Camoin",
        "Othon Friesz",
    ),
    "style:constructivism": (
        "Kazimir Malevich",
        "El Lissitzky",
        "Lyubov Popova",
        "Vladimir Tatlin",
        "Alexander Rodchenko",
        "Varvara Stepanova",
        "Władysław Strzemiński",
        "Katarzyna Kobro",
        "Henryk Stażewski",
        "László Moholy-Nagy",
    ),
    "style:de-stijl": (
        "Piet Mondrian",
        "Theo van Doesburg",
        "Bart van der Leck",
        "Vilmos Huszár",
        "Georges Vantongerloo",
        "Gerrit Rietveld",
        "César Domela",
        "Friedrich Vordemberge-Gildewart",
    ),
    "style:new-objectivity": (
        "Otto Dix",
        "George Grosz",
        "Christian Schad",
        "Georg Schrimpf",
        "Alexander Kanoldt",
        "Rudolf Schlichter",
        "Anton Räderscheidt",
        "Carl Grossberg",
        "Franz Radziwill",
        "Karl Hubbuch",
        "Jeanne Mammen",
        "Max Beckmann",
    ),
    "style:shin-hanga": (
        "Kawase Hasui",
        "Hiroshi Yoshida",
        "Ohara Koson",
        "Ito Shinsui",
        "Hashiguchi Goyo",
        "Tsuchiya Koitsu",
        "Torii Kotondo",
        "Natori Shunsen",
        "Yamamura Koka",
        "Kasamatsu Shiro",
    ),
}
#: Years around a style's own that its painters' works still count.
STYLE_ARTIST_SLACK = 2


def style_artists(keys: Iterable[str]) -> list[str]:
    """What to ask museums for, in turns, when every style in ``keys`` is
    one of :data:`STYLE_ARTISTS` (with another style, its word is asked):
    first the style's own word (``""``), then its painters."""
    styles = [k for k in keys if k.startswith("style:")]
    if not styles or any(k not in STYLE_ARTISTS for k in styles):
        return []
    return ["", *dict.fromkeys(a for k in styles for a in STYLE_ARTISTS[k])]


def asked_topics(chosen: list[str], artist: str, keys: list[str]) -> list[str]:
    """The style or subject asked with ``artist`` (:func:`museum_queries`):
    a style asked by one of its painters isn't named next to them."""
    by_painter = bool(artist) and not chosen and bool(style_artists(keys))
    return museum_queries([k for k in keys if not (by_painter and k in STYLE_ARTISTS)])[:1]


def asked_artists(artists: list[str], keys: Iterable[str]) -> list[str]:
    """The artists a search asks museums for: those chosen, or else the
    painters of the styles chosen (:func:`style_artists`)."""
    return artists or style_artists(keys)


def _by_style_artist(style: Term, item: Item) -> bool:
    """``item`` is by one of ``style``'s painters, from its years (or undated)."""
    artists = STYLE_ARTISTS.get(style.key)
    if not artists or not artist_matches(item.artist, list(artists)):
        return False
    span = STYLE_YEARS.get(style.key)
    if item.year is None or span is None:
        return True
    start, end = span
    return start - STYLE_ARTIST_SLACK <= item.year and (
        end is None or item.year <= end + STYLE_ARTIST_SLACK
    )


def searched_style_fits(style: Term, item: Item, text: str) -> bool:
    """A work the museums found for ``style``'s word fits it when its own
    text names the style, or, for a style of one plain word
    ("impressionism"), when it is dated within the style's years. A
    museum's search takes "de stijl" or "art deco" as two words: Commons
    found road signs and Rijksmuseum "Crucifix in romaanse stijl" for De
    Stijl (Mateusz 2026-11-09), undated or dated by chance."""
    if term_matches(style, item, text):
        return True
    one_word = re.fullmatch(r"\w+", style.query) is not None
    return one_word and item.year is not None and in_style_years(item, [style.key])


def searched_kinds(keys: list[str] | tuple[str, ...]) -> frozenset[str]:
    """Kinds of the terms in ``keys`` that the museums' search itself decides
    (:func:`museum_queries`: styles and subjects are asked as words, one
    technique as the museum's own filter): a work it found for them fits
    them. Periods, tags and two techniques at once are checked on the work."""
    kinds = {"style", "subject"}
    if museum_kind(list(keys)) != "any":
        kinds.add("technique")
    return frozenset(kinds)


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
    # Periods of one country each ("Edo"): their country's word, since the
    # years alone bring mostly other places' works.
    periods = groups.get("period", [])
    if periods and all(p.place for p in periods):
        words.append(sorted({PLACES[p.place][0] for p in periods if p.place}))
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
