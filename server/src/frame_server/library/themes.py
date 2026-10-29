"""Discover's themes: ideas for playlists, each a set of smart playlist rules
plus the museum searches to browse it by.

Artists are written as short as still unambiguous ("Hokusai"), since
museums spell full names differently; rules match them word by word.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date

import httpx

from .importer import Importer
from .models import Item, ItemKind, PlaylistRules
from .repo import Library
from .seed import MORE_POLISH_PAINTERS, PACKS, POLISH_PAINTERS
from .vocabulary import museum_queries, set_aside

log = logging.getLogger(__name__)

#: Museums asked for a theme's artists or words when it names no searches.
SEARCH_SOURCES = ("aic", "cma", "met")
#: A theme's page goes on to its next searches while one finds nothing,
#: for this many seconds at most; the app asks for the rest.
BROWSE_WAIT = 8.0

GROUPS = (
    "Kierunki i style",
    "Grafika i plakat",
    "Tematy",
    "Sztuka polska",
    "Kolor i nastrój",
    "Epoki",
)


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    description: str
    group: str
    artists: tuple[str, ...] = ()
    terms: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    min_suitability: float | None = None
    #: (museum, query) to browse by; else the artists', else the terms'.
    queries: tuple[tuple[str, str], ...] = ()

    def rules(self) -> PlaylistRules:
        return PlaylistRules(
            artists=list(self.artists),
            terms=list(self.terms),
            colors=list(self.colors),
            min_suitability=self.min_suitability,
            kinds=[ItemKind.ARTWORK],
        )

    def searches(self) -> list[tuple[str, str]]:
        """Museum searches to browse the theme by; none for themes of
        colour or period, which are browsed in the catalogue."""
        if self.queries:
            return list(self.queries)
        if self.artists:
            return [(s, a) for a in self.artists for s in SEARCH_SOURCES]
        return [(s, q) for q in museum_queries(list(self.terms)) for s in SEARCH_SOURCES]


def _pack_queries(key: str) -> tuple[tuple[str, str], ...]:
    found = next(p for p in PACKS if p.key == key)
    return tuple((source, query) for source, query, _ in found.queries)


def _commons(artists: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Commons categories of painters the big museums hardly have (Polish
    ones: Chicago, Cleveland and the Met find nothing for Wyspiański)."""
    return tuple(("wmc", f"Category:Paintings by {name}") for name in artists)


YOUNG_POLAND = (
    "Stanisław Wyspiański",
    "Józef Mehoffer",
    "Jacek Malczewski",
    "Olga Boznańska",
    "Leon Wyczółkowski",
    "Jan Stanisławski",
    "Wojciech Weiss",
    "Teodor Axentowicz",
    "Józef Pankiewicz",
    "Władysław Podkowiński",
)
POLISH_LANDSCAPE = (
    "Józef Chełmoński",
    "Jan Stanisławski",
    "Julian Fałat",
    "Ferdynand Ruszczyc",
    "Kazimierz Stabrowski",
    "Leon Wyczółkowski",
)
#: Painters who died in or before 1955: free in Poland since 2026 at the
#: latest, though American museums keep their later works closed.
AVANT_GARDE = (
    "Kandinsky",
    "Mondrian",
    "Paul Klee",
    "Malevich",
    "Fernand Léger",
    "Robert Delaunay",
    "Jawlensky",
    "Oskar Schlemmer",
    "van Doesburg",
)
POLISH_INTERWAR = (
    "Władysław Strzemiński",
    "Stanisław Ignacy Witkiewicz",
    "Leon Chwistek",
    "Tytus Czyżewski",
    "Tadeusz Makowski",
    "Mojżesz Kisling",
    "Roman Kramsztyk",
)


STYLES = "Kierunki i style"
PRINTS = "Grafika i plakat"
SUBJECTS = "Tematy"
POLISH = "Sztuka polska"
COLOUR = "Kolor i nastrój"
PERIODS = "Epoki"

THEMES: list[Theme] = [
    # Movements and styles
    Theme(
        "impressionism",
        "Impresjonizm i postimpresjonizm",
        "Monet, Renoir, Pissarro, Degas, Morisot, Cassatt, van Gogh, Cézanne, Seurat.",
        STYLES,
        artists=(
            "Claude Monet",
            "Renoir",
            "Pissarro",
            "Sisley",
            "Degas",
            "Berthe Morisot",
            "Mary Cassatt",
            "Caillebotte",
            "van Gogh",
            "Cezanne",
            "Seurat",
            "Gauguin",
        ),
        queries=_pack_queries("impressionism"),
    ),
    Theme(
        "dutch",
        "Malarstwo holenderskie",
        "Złoty wiek: Vermeer, Rembrandt, Hals, Steen, Ruisdael, aż po Breitnera.",
        STYLES,
        artists=(
            "Vermeer",
            "Rembrandt",
            "Frans Hals",
            "Steen",
            "Pieter de Hooch",
            "Ruisdael",
            "Avercamp",
            "Heda",
            "Cuyp",
            "Breitner",
            "Maris",
        ),
        queries=_pack_queries("dutch"),
    ),
    Theme(
        "romanticism",
        "Romantyzm",
        "Burze, ruiny i światło: Turner, Friedrich, Delacroix, Géricault.",
        STYLES,
        artists=(
            "Turner",
            "Caspar David Friedrich",
            "Delacroix",
            "Géricault",
            "John Martin",
            "Thomas Cole",
        ),
    ),
    Theme(
        "realism",
        "Realizm i Barbizon",
        "Wieś, praca i pejzaż prosto z natury: Courbet, Millet, Corot, Daubigny.",
        STYLES,
        artists=(
            "Courbet",
            "Millet",
            "Corot",
            "Daubigny",
            "Théodore Rousseau",
            "Rosa Bonheur",
            "Jules Breton",
        ),
    ),
    Theme(
        "symbolism",
        "Prerafaelici i symbolizm",
        "Mity, sny i legendy: Rossetti, Burne-Jones, Waterhouse, Moreau, Redon.",
        STYLES,
        artists=(
            "Rossetti",
            "Burne-Jones",
            "Waterhouse",
            "Millais",
            "Gustave Moreau",
            "Odilon Redon",
            "Puvis de Chavannes",
            "Böcklin",
            "Khnopff",
        ),
    ),
    Theme(
        "nabis",
        "Nabiści i intymiści",
        "Ciche wnętrza i płaskie plamy koloru: Bonnard, Vuillard, Vallotton, Denis.",
        STYLES,
        artists=("Bonnard", "Vuillard", "Vallotton", "Maurice Denis", "Sérusier"),
    ),
    Theme(
        "vienna",
        "Wiedeńska secesja",
        "Złoto, ornament i linia: Klimt, Schiele, Moser.",
        STYLES,
        artists=("Klimt", "Schiele", "Koloman Moser", "Carl Moll"),
    ),
    Theme(
        "rococo",
        "Rokoko",
        "Ogrody, huśtawki i pastelowe niebo: Watteau, Fragonard, Boucher.",
        STYLES,
        artists=("Watteau", "Fragonard", "Boucher", "Lancret", "Chardin"),
    ),
    Theme(
        "northern",
        "Dawni mistrzowie Północy",
        "Dürer, Bruegel, Holbein, van Eyck, Cranach: obrazy i ryciny.",
        STYLES,
        artists=("Dürer", "Bruegel", "Holbein", "van Eyck", "Cranach", "Memling", "Bosch"),
    ),
    Theme(
        "north-light",
        "Światło Północy",
        "Skandynawia około 1900: Hammershøi, Larsson, Zorn, Krøyer, Munch.",
        STYLES,
        artists=("Hammershøi", "Carl Larsson", "Zorn", "Krøyer", "Gallen-Kallela", "Munch"),
    ),
    Theme(
        "expressionism",
        "Fowizm i ekspresjonizm",
        "Czysty kolor: Matisse, Derain, Marc, Macke, Kirchner, Kandinsky i inni.",
        STYLES,
        artists=(
            "Matisse",
            "Derain",
            "Vlaminck",
            "Franz Marc",
            "August Macke",
            "Kirchner",
            "Kandinsky",
        ),
    ),
    Theme(
        "avant-garde",
        "Awangarda i abstrakcja",
        "Kandinsky, Mondrian, Klee, Malewicz, Léger, Delaunay, także ich późne prace.",
        STYLES,
        artists=AVANT_GARDE,
        # Europeana first: its later works are free by the EU rule.
        queries=tuple((s, a) for a in AVANT_GARDE for s in ("europeana", "aic", "cma")),
    ),
    # Prints and posters
    Theme(
        "ukiyo-e",
        "Japońskie drzeworyty",
        "Hokusai, Hiroshige, Utamaro, Kuniyoshi, Harunobu i inni mistrzowie ukiyo-e.",
        PRINTS,
        artists=(
            "Hokusai",
            "Hiroshige",
            "Utamaro",
            "Kuniyoshi",
            "Keisai Eisen",
            "Harunobu",
            "Kiyonaga",
        ),
        queries=_pack_queries("ukiyo-e"),
    ),
    Theme(
        "kacho-e",
        "Kwiaty i ptaki ukiyo-e",
        "Kachō-e: ptaki, gałęzie i kwiaty u Hokusaia, Hiroshigego i Kosona.",
        PRINTS,
        artists=("Hokusai", "Hiroshige", "Koson", "Bairei", "Kuniyoshi"),
        terms=("subject:birds", "subject:flowers"),
        queries=(
            ("aic", "Hiroshige bird"),
            ("aic", "Hokusai flowers"),
            ("aic", "Ohara Koson"),
            ("cma", "Hiroshige bird"),
            ("met", "kacho-e"),
        ),
    ),
    Theme(
        "posters",
        "Plakaty i secesja",
        "Mucha, Toulouse-Lautrec, Steinlen, Chéret, Grasset i plakat przełomu wieków.",
        PRINTS,
        artists=("Mucha", "Toulouse-Lautrec", "Steinlen", "Chéret", "Grasset"),
        queries=_pack_queries("posters"),
    ),
    Theme(
        "nature",
        "Botanika i natura",
        "Ryciny botaniczne, ptaki Audubona, motyle i kwiaty Merian.",
        PRINTS,
        terms=(
            "subject:botany",
            "subject:flowers",
            "subject:birds",
            "technique:print",
            "technique:drawing",
        ),
        queries=_pack_queries("nature"),
    ),
    Theme(
        "black-white",
        "Czerń i biel",
        "Akwaforty, miedzioryty i drzeworyty; ekran oddaje je wyjątkowo czysto.",
        PRINTS,
        terms=("technique:print",),
        colors=("monochrome",),
        queries=(("aic", "etching"), ("met", "etching"), ("cma", "engraving"), ("aic", "woodcut")),
    ),
    # Subjects
    Theme(
        "sea",
        "Morze i statki",
        "Fale, porty i żagle, od Turnera po Homera i Hiroshigego.",
        SUBJECTS,
        terms=("subject:sea", "subject:ships"),
    ),
    Theme(
        "landscapes",
        "Pejzaże XIX wieku",
        "Turner, Constable, Corot, Inness, Homer, Sargent i Szkoła znad rzeki Hudson.",
        SUBJECTS,
        artists=(
            "Corot",
            "Turner",
            "Constable",
            "Inness",
            "Winslow Homer",
            "Sargent",
            "Thomas Cole",
            "Bierstadt",
            "Whistler",
        ),
        queries=_pack_queries("landscapes"),
    ),
    Theme(
        "mountains",
        "Góry",
        "Alpy, Tatry i Fudżi.",
        SUBJECTS,
        terms=("subject:mountains",),
    ),
    Theme(
        "winter",
        "Zima i śnieg",
        "Śnieg u Moneta, Hiroshigego, Avercampa i Fałata.",
        SUBJECTS,
        terms=("subject:winter",),
    ),
    Theme(
        "night",
        "Nokturny",
        "Noc, księżyc i latarnie: Whistler, Hiroshige, Grimshaw.",
        SUBJECTS,
        terms=("subject:night",),
    ),
    Theme(
        "flowers",
        "Kwiaty",
        "Bukiety i kwitnące ogrody na płótnie.",
        SUBJECTS,
        terms=("subject:flowers", "subject:gardens", "technique:painting"),
    ),
    Theme(
        "still-life",
        "Martwa natura",
        "Od holenderskich stołów po jabłka Cézanne’a.",
        SUBJECTS,
        terms=("subject:still-life",),
    ),
    Theme(
        "city",
        "Miasto i ulica",
        "Paryż, Amsterdam, Wenecja i Edo.",
        SUBJECTS,
        terms=("subject:city",),
    ),
    Theme(
        "interiors",
        "Wnętrza i codzienność",
        "Vermeer, de Hooch, Hammershøi, Vuillard: spokojne pokoje i zwykłe chwile.",
        SUBJECTS,
        terms=("subject:interior", "subject:everyday"),
    ),
    Theme(
        "animals",
        "Zwierzęta",
        "Konie, psy, koty i ptactwo domowe.",
        SUBJECTS,
        terms=("subject:animals",),
    ),
    Theme(
        "portraits",
        "Portrety",
        "Twarze od Rembrandta po Boznańską i Sargenta.",
        SUBJECTS,
        terms=("subject:portrait", "technique:painting"),
    ),
    # Polish art
    Theme(
        "polish",
        "Sztuka polska",
        "Chełmoński, Malczewski, Boznańska, Matejko i 20 kolejnych malarzy.",
        POLISH,
        artists=tuple(POLISH_PAINTERS + MORE_POLISH_PAINTERS),
        queries=_pack_queries("polish"),
    ),
    Theme(
        "young-poland",
        "Młoda Polska",
        "Wyspiański, Mehoffer, Malczewski, Boznańska, Stanisławski, Weiss.",
        POLISH,
        artists=YOUNG_POLAND,
        queries=_commons(YOUNG_POLAND),
    ),
    Theme(
        "polish-landscape",
        "Polski pejzaż",
        "Chełmoński, Stanisławski, Fałat, Ruszczyc, Stabrowski.",
        POLISH,
        artists=POLISH_LANDSCAPE,
        queries=_commons(POLISH_LANDSCAPE),
    ),
    Theme(
        "polish-interwar",
        "Polskie międzywojnie",
        "Strzemiński, Witkacy, Chwistek, Czyżewski, Makowski, Kisling.",
        POLISH,
        artists=POLISH_INTERWAR,
        queries=(
            *_commons(POLISH_INTERWAR),
            *(("europeana", a) for a in POLISH_INTERWAR),
        ),
    ),
    # Colour and mood: browsed in the catalogue, where colours are known
    Theme(
        "blue",
        "W odcieniach błękitu",
        "Niebo, woda i indygo.",
        COLOUR,
        colors=("blue", "teal"),
    ),
    Theme(
        "warm",
        "Ciepłe barwy",
        "Ochra, czerwień i złoto.",
        COLOUR,
        colors=("warm",),
    ),
    Theme(
        "light",
        "Jasne i spokojne",
        "Pastelowe, jasne obrazy na spokojne dni.",
        COLOUR,
        colors=("light",),
    ),
    Theme(
        "vivid",
        "Wyraziste barwy",
        "Mocne kolory, w których ekran Spectra 6 czuje się najlepiej.",
        COLOUR,
        colors=("vivid",),
    ),
    # Periods: browsed in the catalogue
    Theme(
        "17c",
        "Złoty wiek, XVII wiek",
        "Barok i holenderski złoty wiek, 1600–1700.",
        PERIODS,
        terms=("period:17c",),
    ),
    Theme(
        "18c",
        "Wiek XVIII",
        "Rokoko, weduty i klasycyzm, 1700–1800.",
        PERIODS,
        terms=("period:18c",),
    ),
    Theme(
        "belle-epoque",
        "Belle Époque",
        "Paryż i Europa w latach 1880–1914.",
        PERIODS,
        terms=("period:belle-epoque",),
    ),
]

BY_KEY = {theme.key: theme for theme in THEMES}
#: Themes the museums can be asked for, for the theme of the day and the
#: catalogue's growth.
SEARCHABLE = [theme for theme in THEMES if theme.searches()]


def theme(key: str) -> Theme:
    try:
        return BY_KEY[key]
    except KeyError:
        raise KeyError(f"unknown theme {key!r}") from None


def theme_of_the_day(day: date) -> Theme:
    return SEARCHABLE[day.toordinal() % len(SEARCHABLE)]


def browse_theme(
    importer: Importer, found: Theme, page: int = 1, limit: int = 24, wait: float = BROWSE_WAIT
) -> tuple[list[Item], int | None]:
    """One page of a theme: its museum searches one after another (page 1
    is the first search, page 2 the next; after the last one their second
    pages follow), or the catalogue for themes without searches. A search
    that finds nothing (or fails) is passed over for the next one, for
    ``wait`` seconds at most. Returns the works and the page to ask for
    next, None after the last."""
    searches = found.searches()
    if not searches:
        items, more = browse_catalogue(importer.library, found, page, limit)
        return items, page + 1 if more else None
    count = len(searches)
    started = time.monotonic()
    failed: httpx.HTTPError | ValueError | None = None
    answered = False
    while True:
        source, query = searches[(page - 1) % count]
        round_ = (page - 1) // count + 1
        kept: list[Item] = []
        total = 0
        try:
            total, items = importer.search(source, query, limit=limit, page=round_)
            kept = [i for i in items if not set_aside(i)]
            answered = True
        except (httpx.HTTPError, ValueError) as err:
            log.warning("theme %s: asking %s for %r failed: %s", found.key, source, query, err)
            failed = err
        following = page + 1 if page % count != 0 or round_ * limit < total else None
        if kept or following is None or time.monotonic() - started >= wait:
            if not kept and not answered and failed is not None:
                raise failed  # every museum asked failed: say so
            return kept, following
        page = following


def browse_catalogue(
    library: Library, found: Theme, page: int = 1, limit: int = 24
) -> tuple[list[Item], bool]:
    total, items = library.query(
        found.rules(), sort="suitability", offset=(page - 1) * limit, limit=limit
    )
    return items, page * limit < total
