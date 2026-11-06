"""Discover's themes: ideas for playlists, each a set of smart playlist rules
plus the museum searches to browse it by.

Artists are written as short as still unambiguous ("Hokusai"), since
museums spell full names differently; rules match them word by word.
"""

from __future__ import annotations

import logging
import random
import re
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from typing import Any

import httpx

from .artists import is_artist
from .importer import Importer
from .models import Item, ItemKind, PlaylistRules
from .nationality import artist_note
from .repo import Library, matches
from .seed import MORE_POLISH_PAINTERS, PACKS, POLISH_PAINTERS
from .viewer import OWNER_ID, viewer_id
from .vocabulary import (
    DECORATIVE,
    HIGHLIGHT,
    MANUSCRIPTS,
    OBJECT_CATEGORIES,
    PHOTOGRAPHY,
    SCULPTURE,
    TERMS,
    Term,
    artist_matches,
    fold,
    museum_queries,
    object_category,
    other_art,
    set_aside,
    term_matches,
    text_of,
)

log = logging.getLogger(__name__)

#: Museums asked for a theme's artists or words when it names no searches.
SEARCH_SOURCES = ("aic", "cma", "met")
#: A theme's page goes on to its next searches while one finds nothing,
#: for this many seconds at most; the app asks for the rest.
BROWSE_WAIT = 8.0

GROUPS = (
    "Dziś dla Ciebie",
    "Bo lubisz",
    "Kierunki i style",
    "Grafika i plakat",
    "Sztuki inne",
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
    #: Words every work's text must have (a season: "autumn").
    query: str = ""
    #: Browsed in the catalogue only (themes made from what it holds).
    catalogue: bool = False
    #: The name of a playlist made from it, when not the theme's own.
    playlist: str = ""
    #: The part of its group's page it stands in ("Starożytność i Bizancjum").
    section: str = ""
    #: The museums' answers kept only when they fit the theme's rules (an
    #: icon search brings enamels and Russian icons of 1800 too).
    strict: bool = False

    def rules(self) -> PlaylistRules:
        return PlaylistRules(
            query=self.query,
            artists=list(self.artists),
            terms=list(self.terms),
            colors=list(self.colors),
            min_suitability=self.min_suitability,
            kinds=[ItemKind.ARTWORK],
        )

    def searches(self) -> list[tuple[str, str]]:
        """Museum searches to browse the theme by; none for themes of
        colour or period, which are browsed in the catalogue."""
        if self.catalogue:
            return []
        if self.queries:
            return spread_searches(list(self.queries), self.artists)
        if self.artists:
            searches = [(s, a) for a in self.artists for s in SEARCH_SOURCES]
            return spread_searches(searches, self.artists)
        return [(s, q) for q in museum_queries(list(self.terms)) for s in SEARCH_SOURCES]


#: Searches in a row that ask for different painters, where a theme has
#: enough of them (a round of the theme stream asks four at once).
ARTIST_SPREAD = 3


def spread_searches(
    searches: list[tuple[str, str]], artists: tuple[str, ...] | list[str]
) -> list[tuple[str, str]]:
    """``searches`` reordered so that the ones asked together look for
    different painters, in different museums where they can: a set's first
    round brings four painters, not two museums' worth of one, and a set of
    a subject does not ask one museum twice in a row. Each next
    search is for the painter asked for least so far, none of the last
    :data:`ARTIST_SPREAD` if it can be, not in the last search's museum if
    it can be, and otherwise the earliest. Searches naming no painter count
    as their own (then only museums take turns)."""
    folded = [(fold(a), fold(a.split()[-1])) for a in artists if a.split()]

    def painter(query: str) -> str:
        text = fold(query)
        return next((name for name, last in folded if name in text or last in text), text)

    left = [(source, query, painter(query)) for source, query in searches]
    done: list[tuple[str, str, str]] = []
    asked: Counter[str] = Counter()
    while left:
        recent = {who for _, _, who in done[-ARTIST_SPREAD:]}
        museum = done[-1][0] if done else None
        index = min(
            range(len(left)),
            key=lambda i: (
                asked[left[i][2]],
                left[i][2] in recent,
                left[i][0] == museum,
                i,
            ),
        )
        picked = left.pop(index)
        asked[picked[2]] += 1
        done.append(picked)
    return [(source, query) for source, query, _ in done]


def _pack_queries(key: str) -> tuple[tuple[str, str], ...]:
    found = next(p for p in PACKS if p.key == key)
    return tuple((source, query) for source, query, _ in found.queries)


def _national(artists: tuple[str, ...] | list[str]) -> tuple[tuple[str, str], ...]:
    """The national museums in Warsaw and Kraków, asked for each painter
    (they hold most of Polish painting, with Polish titles)."""
    return tuple((source, name) for name in artists for source in ("mnw", "mnk"))


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


#: The group of the theme of the day (made in the app) and the week's
#: themes; "Na ten tydzień" before it was renamed.
#: Painters of Rome, Greece and Egypt as the 18th and 19th centuries saw them.
ANTIQUITY_PAINTERS = (
    "Alma-Tadema",
    "Gérôme",
    "Siemiradzki",
    "Hubert Robert",
    "Jacques-Louis David",
    "Puvis de Chavannes",
    "Poynter",
    "Leighton",
    "Panini",
    "Styka",
)
#: Italy's painters on gold, from the Byzantine manner to Giotto's heirs.
GOLD_GROUND = (
    "Duccio",
    "Giotto",
    "Cimabue",
    "Simone Martini",
    "Pietro Lorenzetti",
    "Ambrogio Lorenzetti",
    "Berlinghiero",
    "Segna di Buonaventura",
    "Bernardo Daddi",
    "Lippo Memmi",
    "Paolo Veneziano",
    "Taddeo Gaddi",
)
#: The parts of the "Epoki" page.
ANTIQUITY = "Starożytność i Bizancjum"
LATER = "Średniowiecze i dalej"
#: The years beside each part's name.
SECTION_YEARS = {ANTIQUITY: "3100 p.n.e.–1453", LATER: "od 1250"}

WEEKLY = "Dziś dla Ciebie"
LIKES = "Bo lubisz"
STYLES = "Kierunki i style"
PRINTS = "Grafika i plakat"
#: Manuscripts, photographs, sculpture and decorative arts, in their own
#: group only (Mateusz 2026-11-06).
OTHER_ARTS = "Sztuki inne"
SUBJECTS = "Tematy"
POLISH = "Sztuka polska"
COLOUR = "Kolor i nastrój"
PERIODS = "Epoki"

THEMES: list[Theme] = [
    # Movements and styles
    Theme(
        "masterpieces",
        "Arcydzieła muzeów",
        "Dzieła, które Met i Cleveland liczą do najważniejszych w swoich zbiorach.",
        STYLES,
        terms=(HIGHLIGHT,),
    ),
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
        "autumn",
        "Jesień",
        "Złote liście, mgły, żniwa i pierwsze przymrozki.",
        SUBJECTS,
        query="autumn",
        queries=(("aic", "autumn"), ("cma", "autumn"), ("met", "autumn")),
    ),
    Theme(
        "spring",
        "Wiosna",
        "Kwitnące sady, pierwsza zieleń i wiosenne światło.",
        SUBJECTS,
        query="spring",
        queries=(("aic", "spring"), ("cma", "spring"), ("met", "spring blossom")),
    ),
    Theme(
        "summer",
        "Lato",
        "Plaże, łąki, upał i długie wieczory.",
        SUBJECTS,
        query="summer",
        queries=(("aic", "summer"), ("cma", "summer"), ("met", "summer")),
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
        "antiquity-painted",
        "Antyk oczami malarzy",
        "David, Robert, Gérôme, Alma-Tadema, Siemiradzki.",
        SUBJECTS,
        artists=ANTIQUITY_PAINTERS,
        queries=(
            *((s, a) for a in ANTIQUITY_PAINTERS[:6] for s in SEARCH_SOURCES),
            *_national(("Siemiradzki", "Styka")),
        ),
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
        queries=(*_national(POLISH_PAINTERS), *_pack_queries("polish")),
    ),
    Theme(
        "young-poland",
        "Młoda Polska",
        "Wyspiański, Mehoffer, Malczewski, Boznańska, Stanisławski, Weiss.",
        POLISH,
        artists=YOUNG_POLAND,
        queries=(*_national(YOUNG_POLAND), *_commons(YOUNG_POLAND)),
    ),
    Theme(
        "polish-landscape",
        "Polski pejzaż",
        "Chełmoński, Stanisławski, Fałat, Ruszczyc, Stabrowski.",
        POLISH,
        artists=POLISH_LANDSCAPE,
        queries=(*_national(POLISH_LANDSCAPE), *_commons(POLISH_LANDSCAPE)),
    ),
    Theme(
        "polish-interwar",
        "Polskie międzywojnie",
        "Strzemiński, Witkacy, Chwistek, Czyżewski, Makowski, Kisling.",
        POLISH,
        artists=POLISH_INTERWAR,
        queries=(
            *_national(POLISH_INTERWAR),
            *_commons(POLISH_INTERWAR),
            *(("europeana", a) for a in POLISH_INTERWAR),
        ),
    ),
    # Periods, in the order of time (Mateusz 2026-11-06): antiquity and
    # Byzantium from the museums (the catalogue has few of their pictures),
    # the rest browsed in the catalogue. Pictures only: vases, sculpture,
    # enamels and manuscripts stay in their own group.
    Theme(
        "ancient-egypt",
        "Starożytny Egipt",
        "Grobowce w Tebach, ok. 1400 p.n.e.",
        PERIODS,
        terms=("period:egypt", "technique:painting"),
        # The Met's copies of the tomb paintings, made in Thebes 1907–1937.
        queries=(
            ("met", "Facsimile tomb"),
            ("met", "Nina de Garis Davies"),
            ("met", "Charles K. Wilkinson facsimile"),
            ("met", "Norman de Garis Davies"),
        ),
        section=ANTIQUITY,
        strict=True,
    ),
    Theme(
        "fayum",
        "Portrety fajumskie",
        "Enkaustyka na desce, 50–250 n.e.",
        PERIODS,
        terms=("period:ancient", "technique:painting"),
        query="portrait",
        queries=(
            ("met", "mummy portrait"),
            ("getty", "Romano-Egyptian portrait"),
            ("wmc", "Category:Fayum mummy portraits"),
            ("met", "encaustic portrait"),
        ),
        section=ANTIQUITY,
        strict=True,
    ),
    Theme(
        "roman-frescoes",
        "Freski Rzymu i Pompejów",
        "Wille w Boscoreale i Pompejach, I w. p.n.e.",
        PERIODS,
        terms=("period:rome", "technique:painting"),
        queries=(
            ("met", "Boscoreale wall painting"),
            ("met", "Roman wall painting fresco"),
            ("met", "fresco Pompeii"),
            ("wmc", "Category:Ancient Roman frescos"),
        ),
        section=ANTIQUITY,
        strict=True,
    ),
    Theme(
        "byzantine-icons",
        "Ikony Bizancjum",
        "Konstantynopol, Kreta i Ruś na złocie.",
        PERIODS,
        # Painted icons, also those of Crete and Rus' after 1453: the
        # museums have few from Byzantium itself (the Met's are enamels).
        terms=("period:medieval", "period:15c", "period:16c", "period:17c", "technique:painting"),
        query="icon",
        queries=(
            ("cma", "Byzantine icon"),
            ("met", "Byzantine icon tempera"),
            ("cma", "icon tempera"),
            ("wmc", "Category:Byzantine icons"),
            ("met", "icon Virgin Hodegetria"),
        ),
        section=ANTIQUITY,
        strict=True,
    ),
    Theme(
        "gold-ground",
        "Złote tło: od ikony do Giotta",
        "Duccio, Giotto, Simone Martini, 1250–1400.",
        PERIODS,
        artists=GOLD_GROUND,
        terms=("technique:painting",),
        section=LATER,
        strict=True,
    ),
    Theme(
        "15c",
        "Wczesny renesans, XV wiek",
        "Fra Angelico, Botticelli, van Eyck, Memling, 1400–1500.",
        PERIODS,
        terms=("period:15c",),
        section=LATER,
    ),
    Theme(
        "16c",
        "Renesans i manieryzm, XVI wiek",
        "Tycjan, Dürer, Holbein, Bruegel, Bronzino, 1500–1600.",
        PERIODS,
        terms=("period:16c",),
        section=LATER,
    ),
    Theme(
        "17c",
        "Złoty wiek, XVII wiek",
        "Barok i holenderski złoty wiek, 1600–1700.",
        PERIODS,
        terms=("period:17c",),
        section=LATER,
    ),
    Theme(
        "18c",
        "Wiek XVIII",
        "Rokoko, weduty i klasycyzm, 1700–1800.",
        PERIODS,
        terms=("period:18c",),
        section=LATER,
    ),
    Theme(
        "early-19c",
        "Pierwsza połowa XIX wieku",
        "Goya, Turner, Friedrich, Ingres, Delacroix, 1800–1850.",
        PERIODS,
        terms=("period:1800-1850",),
        section=LATER,
    ),
    Theme(
        "late-19c",
        "Druga połowa XIX wieku",
        "Courbet, Millet, Manet, Matejko, Monet, 1850–1900.",
        PERIODS,
        terms=("period:1850-1900",),
        section=LATER,
    ),
    Theme(
        "belle-epoque",
        "Belle Époque",
        "Paryż i Europa w latach 1880–1914.",
        PERIODS,
        terms=("period:belle-epoque",),
        section=LATER,
    ),
    Theme(
        "interwar",
        "Międzywojnie",
        "Kandinsky, Klee, Mondrian, Witkacy i późny Monet, 1918–1939.",
        PERIODS,
        terms=("period:interwar",),
        section=LATER,
    ),
]

# -- colour and mood ---------------------------------------------------------------

#: Colour cards show paintings, drawings and watercolours only (Mateusz,
#: 2026-11-04): no posters, prints or photographs.
PAINTERLY = ("technique:painting", "technique:drawing")


def _colour(key: str, name: str, description: str, *colors: str) -> Theme:
    """A card of "Kolor i nastrój": colours, moods, accents or "only:"
    colours (:func:`colors.has_colours`), browsed in the catalogue, where
    colours are known."""
    return Theme(key, name, description, COLOUR, colors=colors, terms=PAINTERLY, catalogue=True)


#: Colourings, tones and accents "Kolor i nastrój" draws its cards from,
#: ``COLOUR_CARDS`` a week (:func:`colour_themes`).
COLOUR_POOL: list[Theme] = [
    _colour("blue", "W odcieniach błękitu", "Niebo, woda i indygo.", "blue", "teal"),
    _colour("warm", "Ciepłe barwy", "Ochra, czerwień i złoto.", "warm"),
    _colour("light", "Jasne i spokojne", "Pastelowe, jasne obrazy na spokojne dni.", "light"),
    _colour(
        "vivid",
        "Wyraziste barwy",
        "Mocne kolory, w których ekran Spectra 6 czuje się najlepiej.",
        "vivid",
    ),
    _colour(
        "only-blue",
        "Sam błękit",
        "Obrazy malowane wyłącznie błękitem i turkusem, z bielą i szarością.",
        "only:blue",
        "only:teal",
    ),
    _colour(
        "only-green",
        "Sama zieleń",
        "Zielenie i turkusy, bez żadnej innej barwy.",
        "only:green",
        "only:teal",
    ),
    _colour(
        "earth",
        "Barwy ziemi",
        "Umbra, ochra i brąz, jak u dawnych mistrzów.",
        "only:brown",
        "only:orange",
        "only:yellow",
    ),
    _colour(
        "fire",
        "Czerwień i ogień",
        "Obrazy w samych czerwieniach i oranżach.",
        "warm",  # and so not a page of beige paper
        "only:red",
        "only:orange",
    ),
    _colour("greens", "Wszystkie zielenie", "Las, łąka i ogród w odcieniach zieleni.", "green"),
    _colour("yellows", "Złoto i żółć", "Słoneczne pola, światło i złoto.", "yellow"),
    _colour("pinks", "Róże i pudry", "Różowe chmury, kwiaty i suknie.", "pink"),
    _colour("purples", "Fiolety i lawenda", "Zmierzchy, bzy i lawenda.", "purple"),
    _colour("cool", "Chłodne tonacje", "Zieleń, błękit i fiolet, bez ciepłych barw.", "cool"),
    _colour("muted", "Ciche barwy", "Przygaszone, stonowane kolory, które nie krzyczą.", "muted"),
    _colour("dark", "Mroczne i nastrojowe", "Ciemne obrazy na długie wieczory.", "dark"),
    _colour(
        "monochrome",
        "Jednym kolorem",
        "Grisaille, sepia i obrazy malowane jedną barwą.",
        "monochrome",
    ),
    _colour(
        "colorful", "Cała paleta", "Obrazy, na których spotykają się wszystkie barwy.", "colorful"
    ),
    _colour(
        "red-in-grey",
        "Czerwień w szarości",
        "Stonowane obrazy z jedną czerwoną plamą.",
        "muted",
        "accent:red",
    ),
    _colour(
        "red-in-green",
        "Czerwień w zieleni",
        "Zielone pejzaże z czerwoną plamą: makiem, dachem, chustą.",
        "green",
        "accent:red",
    ),
    _colour(
        "blue-gold",
        "Błękit i złoto",
        "Niebieskie obrazy rozświetlone odrobiną żółci.",
        "blue",
        "teal",
        "accent:yellow",
    ),
    _colour(
        "blue-orange",
        "Błękit i pomarańcz",
        "Barwy dopełniające: niebieskie obrazy z ciepłym blaskiem.",
        "blue",
        "teal",
        "accent:orange",
    ),
    _colour(
        "glow",
        "Światło w mroku",
        "Ciemne obrazy, w których błyska świeca, ogień albo złoto.",
        "dark",
        "accent:yellow",
        "accent:orange",
    ),
]


#: The parts of the group's page, by technique.
OTHER_ART_SECTIONS = {
    MANUSCRIPTS: "Rękopisy i miniatury",
    PHOTOGRAPHY: "Fotografia",
    SCULPTURE: "Rzeźba",
    DECORATIVE: "Ceramika i rzemiosło",
}


def _other(
    key: str,
    name: str,
    description: str,
    category: str,
    *queries: tuple[str, str],
    terms: tuple[str, ...] = (),
    artists: tuple[str, ...] = (),
    query: str = "",
    colors: tuple[str, ...] = (),
) -> Theme:
    """A theme of "Sztuki inne": works of one technique (``category``),
    browsed in the museums by ``queries``; without them, the catalogue's
    works of the technique (the technique's own card)."""
    return Theme(
        key,
        name,
        description,
        OTHER_ARTS,
        section=OTHER_ART_SECTIONS[category],
        artists=artists,
        terms=(category, *terms),
        colors=colors,
        queries=queries,
        query=query,
        catalogue=not queries,
    )


#: "Sztuki inne": a card for each technique, then themes of it. Apart from
#: :data:`THEMES` so that none of them becomes the theme of the day, a card
#: of "Bo lubisz" or a search of the catalogue's growth.
OTHER_ART_THEMES: list[Theme] = [
    _other(
        "other-manuscripts",
        "Rękopisy i miniatury",
        "Karty ksiąg, inicjały i miniatury ze zbiorów muzeów.",
        MANUSCRIPTS,
    ),
    _other(
        "other-photography",
        "Fotografia",
        "Od pierwszych odbitek Talbota po kolorowe slajdy lat 40.",
        PHOTOGRAPHY,
    ),
    _other(
        "other-sculpture",
        "Rzeźba",
        "Marmur, brąz i drewno z pięciu tysięcy lat.",
        SCULPTURE,
    ),
    _other(
        "other-decorative",
        "Ceramika i rzemiosło",
        "Porcelana, wazy, tkaniny i szkło z pracowni całego świata.",
        DECORATIVE,
    ),
    _other(
        "books-of-hours",
        "Godzinki i kalendarze",
        "Limburgowie, Mistrz Boucicaut i miesiące prac w polu.",
        MANUSCRIPTS,
        ("cma", "book of hours"),
        ("met", "book of hours"),
        ("getty", "book of hours"),
        ("cma", "calendar page"),
        ("vam", "book of hours"),
        query="hours",
    ),
    _other(
        "persian-miniatures",
        "Miniatura perska",
        "Szahname Ferdousiego i Chamsa Nizamiego z Tabrizu, Szirazu i Kazwinu.",
        MANUSCRIPTS,
        ("cma", "shahnama"),
        ("met", "shahnama"),
        ("cma", "khamsa"),
        ("met", "khamsa"),
        ("aic", "shahnama"),
        query="iran",
    ),
    _other(
        "initials",
        "Inicjały i antyfonarze",
        "Złote litery, nuty i święci zamknięci w inicjale.",
        MANUSCRIPTS,
        ("cma", "historiated initial"),
        ("met", "historiated initial"),
        ("getty", "initial"),
        ("cma", "antiphonary"),
        ("vam", "manuscript cutting initial"),
        query="initial",
    ),
    _other(
        "photo-pioneers",
        "Pionierzy fotografii",
        "Talbot, Julia Margaret Cameron, Nadar i Le Gray.",
        PHOTOGRAPHY,
        *(
            (s, a)
            for a in ("Talbot", "Julia Margaret Cameron", "Nadar", "Le Gray")
            for s in ("cma", "getty", "met")
        ),
        artists=(
            "William Henry Fox Talbot",
            "Julia Margaret Cameron",
            "Nadar",
            "Gustave Le Gray",
            "Roger Fenton",
        ),
    ),
    _other(
        "atget-paris",
        "Paryż Atgeta",
        "Uliczki, bramy i nabrzeża: Atget, Marville, Baldus, Nègre.",
        PHOTOGRAPHY,
        *((s, a) for a in ("Atget", "Marville", "Baldus") for s in ("cma", "getty", "met")),
        artists=("Eugène Atget", "Charles Marville", "Édouard Baldus", "Charles Nègre"),
    ),
    _other(
        "first-colours",
        "Pierwsze kolory",
        "Prokudin-Gorski, fotochromy, autochromy i kolorowe slajdy FSA.",
        PHOTOGRAPHY,
        ("loc", "Prokudin-Gorskii"),
        ("loc", "photochrom"),
        ("cma", "autochrome"),
        ("met", "autochrome"),
        ("loc", "Kodachrome"),
        terms=("years:1850-1950",),
        colors=("colorful",),
    ),
    _other(
        "america-lens",
        "Ameryka w obiektywie",
        "Dorothea Lange, Lewis Hine, Walker Evans i Stieglitz.",
        PHOTOGRAPHY,
        ("loc", "Dorothea Lange"),
        ("loc", "Lewis Hine"),
        ("cma", "Walker Evans"),
        ("met", "Walker Evans"),
        ("cma", "Stieglitz"),
        artists=("Dorothea Lange", "Lewis Hine", "Walker Evans", "Alfred Stieglitz", "Paul Strand"),
    ),
    _other(
        "rodin",
        "Rodin i jego czasy",
        "Rodin, Camille Claudel, Carpeaux i tancerki Degasa w brązie.",
        SCULPTURE,
        ("cma", "Rodin"),
        ("met", "Rodin bronze"),
        ("aic", "Rodin"),
        ("cma", "Carpeaux"),
        ("met", "Camille Claudel"),
        artists=("Rodin", "Camille Claudel", "Carpeaux", "Degas", "Dalou", "Barye"),
    ),
    _other(
        "gothic-wood",
        "Wit Stwosz i gotyckie drewno",
        "Stwosz, Riemenschneider i malowane Madonny z lipowego drewna.",
        SCULPTURE,
        ("cma", "Riemenschneider"),
        ("met", "Riemenschneider"),
        ("cma", "Veit Stoss"),
        ("cma", "limewood"),
        ("met", "limewood"),
        terms=("years:1250-1550",),
        query="wood",
    ),
    _other(
        "antique-sculpture",
        "Antyk: marmur i brąz",
        "Egipt faraonów, greckie brązy i portrety Rzymian.",
        SCULPTURE,
        ("cma", "Roman marble"),
        ("met", "Greek bronze statuette"),
        ("cma", "Egypt statue"),
        ("met", "Roman portrait head"),
        terms=("period:egypt", "period:greece", "period:rome"),
    ),
    _other(
        "buddhas",
        "Buddowie Azji",
        "Gandhara, Chiny i Japonia: Budda i bodhisattwowie.",
        SCULPTURE,
        ("cma", "Buddha"),
        ("met", "Buddha"),
        ("aic", "Buddha"),
        ("cma", "Bodhisattva"),
        query="buddh",
    ),
    _other(
        "blue-white",
        "Błękit i biel",
        "Kobalt na porcelanie: Jingdezhen, Iznik i Delft.",
        DECORATIVE,
        ("cma", "blue and white"),
        ("met", "blue-and-white porcelain"),
        ("cma", "Iznik"),
        ("met", "Iznik"),
        ("cma", "Delft"),
        query="blue",
    ),
    _other(
        "greek-vases",
        "Wazy greckie",
        "Czarnofigurowe amfory, czerwonofigurowe czary, białe lekyty.",
        DECORATIVE,
        ("cma", "amphora"),
        ("met", "terracotta amphora"),
        ("cma", "lekythos"),
        ("met", "kylix"),
        ("aic", "amphora"),
        terms=("period:greece",),
    ),
    _other(
        "porcelain",
        "Miśnia i Sèvres",
        "Dworska porcelana XVIII wieku: figurki, wazy i serwisy.",
        DECORATIVE,
        ("cma", "Meissen"),
        ("met", "Meissen"),
        ("cma", "Sevres"),
        ("met", "Sèvres"),
        terms=("years:1700-1820",),
        query="porcelain",
    ),
    _other(
        "textiles",
        "Tkaniny i wzory",
        "William Morris, gobeliny i perskie hafty.",
        DECORATIVE,
        ("cma", "William Morris"),
        ("vam", "William Morris textile"),
        ("cma", "tapestry"),
        ("met", "tapestry"),
        query="textil",
    ),
]


def other_art_searches() -> dict[str, list[tuple[str, str]]]:
    """The searches of the themes of "Sztuki inne", by technique: what the
    catalogue's works of each come from first."""
    found: dict[str, list[tuple[str, str]]] = {}
    for t in OTHER_ART_THEMES:
        category = next(k for k in t.terms if k in OBJECT_CATEGORIES)
        found.setdefault(category, []).extend(t.searches())
    return found


BY_KEY = {theme.key: theme for theme in [*THEMES, *OTHER_ART_THEMES, *COLOUR_POOL]}
#: Themes the museums can be asked for, for the theme of the day and the
#: catalogue's growth.
SEARCHABLE = [theme for theme in THEMES if theme.searches()]


#: Works a card needs in the catalogue for a full cover.
COVER_MIN = 8


def thin_searches(library: Library) -> list[tuple[str, str]]:
    """The first searches of the themes kept to their rules (antiquity)
    that the catalogue has too few works of for a cover: asked first when
    the catalogue grows at night, so their cards are not left empty."""
    return [
        search
        for t in THEMES
        if t.strict and t.searches() and library.query(t.rules())[0] < COVER_MIN
        for search in t.searches()[:2]
    ]


def theme(key: str, library: Library | None = None) -> Theme:
    """A theme by its key: one of ``THEMES`` or ``COLOUR_POOL``, of the
    week's or of "Bo lubisz" (those two need ``library``)."""
    found = BY_KEY.get(key) or _weekly.get(key)
    if found is None and library is not None:
        weekly_themes(library, date.today())
        curated(library)
        mine = [*liked(library), *liked(library, OWNER_ID)]
        found = _weekly.get(key) or next((t for t in mine if t.key == key), None)
    if found is None:
        raise KeyError(f"unknown theme {key!r}")
    return found


# -- the theme of the day ------------------------------------------------------

#: The theme of each day lately (ISO date → key), so one day keeps its
#: theme and later days pick others.
DAYS_KEY = "theme_days"
#: A theme of the day is not picked again for this many days (there are
#: some 40 themes, a few of them out of season).
DAY_REPEAT = 30
#: Themes of a season: picked four times as often in it, never in the
#: opposite one and seldom in the two others.
SEASON_THEMES = {
    "winter": ("winter", "night"),
    "spring": ("spring", "flowers"),
    "summer": ("summer", "sea"),
    "autumn": ("autumn", "landscapes"),
}
OPPOSITE = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}


@dataclass(frozen=True)
class Occasion:
    """A day in the Polish calendar with a theme of its own."""

    name: str
    theme: str


#: (first day, last day) as (month, day), the occasion and its theme.
OCCASIONS: tuple[tuple[tuple[int, int], tuple[int, int], str, str], ...] = (
    ((1, 1), (1, 1), "Nowy Rok", "night"),
    ((1, 7), (1, 7), "Prawosławne Boże Narodzenie", "byzantine-icons"),
    ((2, 14), (2, 14), "Walentynki", "flowers"),
    ((3, 21), (3, 21), "Pierwszy dzień wiosny", "spring"),
    ((4, 21), (4, 21), "Urodziny Rzymu", "roman-frescoes"),
    ((5, 3), (5, 3), "Święto Konstytucji 3 Maja", "polish"),
    ((6, 21), (6, 21), "Pierwszy dzień lata", "summer"),
    ((9, 23), (9, 23), "Pierwszy dzień jesieni", "autumn"),
    ((11, 1), (11, 2), "Wszystkich Świętych", "autumn"),
    ((11, 4), (11, 4), "Rocznica odkrycia grobowca Tutanchamona", "ancient-egypt"),
    ((11, 11), (11, 11), "Narodowe Święto Niepodległości", "polish"),
    ((12, 22), (12, 22), "Pierwszy dzień zimy", "winter"),
    ((12, 24), (12, 26), "Boże Narodzenie", "winter"),
    ((12, 31), (12, 31), "Sylwester", "night"),
)


def easter(year: int) -> date:
    """Easter Sunday (the Gregorian computus)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l_) // 433
    month = (h + l_ - 7 * m + 90) // 25
    return date(year, month, (h + l_ - 7 * m + 33 * month + 19) % 32)


def occasion(day: date) -> Occasion | None:
    """The occasion of ``day``, if it has one."""
    if day - easter(day.year) in (timedelta(0), timedelta(days=1)):
        return Occasion("Wielkanoc", "spring")
    for start, end, name, key in OCCASIONS:
        if start <= (day.month, day.day) <= end:
            return Occasion(name, key)
    return None


def season(day: date) -> str:
    return ("winter", "spring", "summer", "autumn")[day.month % 12 // 3]


def _day_weight(found: Theme, now: str, recent: set[str]) -> float:
    weight = 0.0 if found.key in recent else 1.0
    if found.key in SEASON_THEMES[now]:
        return weight * 4
    if found.key in SEASON_THEMES[OPPOSITE[now]]:
        return 0.0
    if any(found.key in keys for keys in SEASON_THEMES.values()):
        return weight * 0.2
    return weight


def _pick_day(day: date, days: dict[str, str]) -> Theme:
    """An occasion's theme; else one drawn for ``day``, the season's more
    often, those of the last ``DAY_REPEAT`` days not at all."""
    found = occasion(day)
    if found is not None:
        return BY_KEY[found.theme]
    now, today = season(day), day.isoformat()
    for repeat in (DAY_REPEAT, DAY_REPEAT // 3, 0):
        since = (day - timedelta(days=repeat)).isoformat()
        recent = {key for when, key in days.items() if since <= when < today}
        weights = [_day_weight(t, now, recent) for t in THEMES]
        if any(weights):
            break
    return random.Random(day.toordinal()).choices(THEMES, weights)[0]


def theme_of_the_day(day: date, library: Library | None = None) -> Theme:
    """The theme of ``day``: worked out once and remembered in ``library``
    (without it, worked out from the date alone)."""
    days: dict[str, str] = library.get_state(DAYS_KEY, {}) if library is not None else {}
    known = BY_KEY.get(days.get(day.isoformat(), ""))
    if known is not None:
        return known
    found = _pick_day(day, days)
    if library is not None:
        since = (day - timedelta(days=2 * DAY_REPEAT)).isoformat()
        kept = {when: key for when, key in days.items() if when >= since}
        library.set_state(DAYS_KEY, {**kept, day.isoformat(): found.key})
    return found


def day_reason(day: date) -> str:
    """Why the theme of the day is what it is, when that is an occasion."""
    found = occasion(day)
    return found.name if found is not None else ""


# -- themes of the week ----------------------------------------------------------

#: The week's themes, made from the catalogue: {"week", "themes", "history"}.
WEEK_KEY = "weekly_themes"
#: Least works of a theme of the week the catalogue must have.
WEEKLY_MIN = 12
#: Pairs of terms each week, besides the artist of the week.
WEEKLY_MIXES = 3
#: A theme of the week is not made again for this many weeks.
WEEKLY_REPEAT = 12
#: Pairs made of a subject and a style, period or one of these techniques.
MIX_TECHNIQUES = ("technique:print", "technique:drawing", "technique:poster")

#: Themes of the week by key: this week's and those seen since the start.
_weekly: dict[str, Theme] = {}
_weekly_lock = threading.Lock()


def week_of(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _works(count: int) -> str:
    """ "1 dzieło", "3 dzieła", "12 dzieł"."""
    if count == 1:
        return "1 dzieło"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} dzieła"
    return f"{count} dzieł"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")


def _theme_from(data: dict[str, Any]) -> Theme:
    fields: dict[str, Any] = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}
    fields["queries"] = tuple(tuple(q) for q in data.get("queries") or ())
    return Theme(**fields)


def _artist_of_the_week(items: list[Item], rng: random.Random, history: set[str]) -> Theme | None:
    """An artist with ``WEEKLY_MIN`` good works in the catalogue, not shown
    lately; those no theme names twice as likely."""
    counts = Counter(i.artist for i in items if is_artist(i.artist) and not other_art(i))
    named = [a for t in THEMES for a in t.artists]
    found = [
        a for a, n in counts.items() if n >= WEEKLY_MIN and f"week-artist-{_slug(a)}" not in history
    ]
    if not found:
        return None
    found.sort()
    weights = [1.0 if artist_matches(a, named) else 2.0 for a in found]
    artist = rng.choices(found, weights)[0]
    bio = next((i.artist_bio for i in items if i.artist == artist and i.artist_bio), "")
    note = artist_note(bio) if bio else None
    about = f"{note}. " if note else ""
    return Theme(
        f"week-artist-{_slug(artist)}",
        artist,
        f"Artysta tygodnia. {about}{_works(counts[artist])} na ten tydzień.",
        WEEKLY,
        artists=(artist,),
        catalogue=True,
    )


def _mixes(items: list[Item], rng: random.Random, history: set[str]) -> list[Theme]:
    """Pairs of a subject and a style, technique or period that at least
    ``WEEKLY_MIN`` works in the catalogue share, and no theme is made of."""
    subjects = [t for t in TERMS if t.kind == "subject"]
    others = [
        t
        for t in TERMS
        if (t.kind in ("style", "period") or t.key in MIX_TECHNIQUES)
        and not t.key.startswith("years:")
    ]
    pairs: Counter[tuple[str, str]] = Counter()
    for item in items:
        text = text_of(item)
        has = [t.key for t in subjects if term_matches(t, item, text)]
        if not has:
            continue
        for other in others:
            if term_matches(other, item, text):
                pairs.update((other.key, subject) for subject in has)
    made = {frozenset(t.terms) for t in THEMES}
    found = sorted(
        pair
        for pair, n in pairs.items()
        if n >= WEEKLY_MIN
        and frozenset(pair) not in made
        and f"week-mix-{_slug(pair[0])}-{_slug(pair[1])}" not in history
    )
    rng.shuffle(found)
    picked: list[Theme] = []
    used: set[str] = set()
    names = {t.key: t for t in TERMS}
    for first, second in found:
        if first in used or second in used:
            continue
        used |= {first, second}
        a, b = names[first], names[second]
        picked.append(
            Theme(
                f"week-mix-{_slug(first)}-{_slug(second)}",
                f"{a.name}: {b.name[0].lower()}{b.name[1:]}",
                f"{a.name} i {b.name.lower()}: {_works(pairs[first, second])}, "
                "wybrane na ten tydzień.",
                WEEKLY,
                terms=(first, second),
                catalogue=True,
            )
        )
        if len(picked) == WEEKLY_MIXES:
            break
    return picked


def make_weekly(library: Library, week: str, history: set[str]) -> list[Theme]:
    """The themes of ``week`` from what the catalogue holds: the artist of
    the week and a few pairs of terms, none made in the weeks before."""
    rules = PlaylistRules(kinds=[ItemKind.ARTWORK])
    items = library.query(rules)[1]
    rng = random.Random(week)
    artist = _artist_of_the_week(items, rng, history)
    return ([artist] if artist else []) + _mixes(items, rng, history)


def _without_nameless(
    library: Library, week: str, stored: dict[str, Any], themes: list[Theme]
) -> list[Theme]:
    """The week's themes made before nameless artists were told apart
    ("Desconegut" as the artist of the week): another artist instead."""
    kept = [t for t in themes if all(map(is_artist, t.artists))]
    history: list[str] = stored.get("history") or []
    made = make_weekly(library, week, set(history))
    found = next((t for t in made if t.artists), None)
    themes = ([found] if found else []) + kept
    library.set_state(
        WEEK_KEY,
        {
            "week": week,
            "themes": [asdict(t) for t in themes],
            "history": history + ([found.key] if found else []),
        },
    )
    log.info("artist of %s made again: %s", week, found.name if found else "none")
    return themes


def weekly_themes(library: Library, day: date) -> list[Theme]:
    """The themes of ``day``'s week: made once a week (the first time, a
    pass over the catalogue) and remembered in ``library``."""
    week = week_of(day)
    with _weekly_lock:
        stored: dict[str, Any] = library.get_state(WEEK_KEY, {})
        if stored.get("week") == week:
            # Stored before the group was renamed: under its new name.
            themes = [replace(_theme_from(t), group=WEEKLY) for t in stored.get("themes") or []]
            if any(not all(map(is_artist, t.artists)) for t in themes):
                themes = _without_nameless(library, week, stored, themes)
        else:
            history: list[str] = stored.get("history") or []
            themes = make_weekly(library, week, set(history))
            history = (history + [t.key for t in themes])[-WEEKLY_REPEAT * (WEEKLY_MIXES + 1) :]
            library.set_state(
                WEEK_KEY,
                {"week": week, "themes": [asdict(t) for t in themes], "history": history},
            )
            log.info("themes of %s: %s", week, ", ".join(t.name for t in themes) or "none")
        _weekly.update({t.key: t for t in themes})
        return themes


ARTIST_PREFIX = "week-artist-"


def artist_of_the_week(library: Library, day: date) -> Theme | None:
    """The artist of ``day``'s week; None when the catalogue has none."""
    return next((t for t in weekly_themes(library, day) if t.key.startswith(ARTIST_PREFIX)), None)


def new_artist_of_the_week(library: Library, day: date) -> Theme | None:
    """Another artist of the week for ``day``'s week, drawn now (the owner's
    "Wylosuj innego" in Konfiguracja); the week's other themes stay. None
    when the catalogue has no other artist fit for it (the week keeps its)."""
    weekly_themes(library, day)  # this week's made first
    week = week_of(day)
    with _weekly_lock:
        stored: dict[str, Any] = library.get_state(WEEK_KEY, {})
        themes = [replace(_theme_from(t), group=WEEKLY) for t in stored.get("themes") or []]
        history: list[str] = stored.get("history") or []
        old = next((t for t in themes if t.key.startswith(ARTIST_PREFIX)), None)
        items = library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]))[1]
        rng = random.Random(f"{week}:{len(history)}")
        found = _artist_of_the_week(items, rng, set(history) | ({old.key} if old else set()))
        if found is None:
            return None
        themes = [found] + [t for t in themes if t is not old]
        library.set_state(
            WEEK_KEY,
            {
                "week": week,
                "themes": [asdict(t) for t in themes],
                # The one set aside stays in it: not drawn again for a while.
                "history": [*history, found.key][-WEEKLY_REPEAT * (WEEKLY_MIXES + 1) :],
            },
        )
        _weekly[found.key] = found
        log.info(
            "artist of %s drawn again: %s instead of %s",
            week,
            found.name,
            old.name if old else "none",
        )
        return found


# -- the curator's cards -----------------------------------------------------------

#: Cards a language model proposed for "Dziś dla Ciebie" (``ai/curator.py``),
#: as the server checked them: {"cards": [{"theme", "made", "seen"}],
#: "history": [keys], "order": {...}}.
CURATED_KEY = "curated_themes"
CURATED_PREFIX = "curator-"
#: The curator's cards at a time; they stand in for as many of the week's
#: pairs of terms (Mateusz 2026-11-06: "Dziś dla Ciebie" does not grow).
CURATED_CARDS = 2
#: A card is made again after this many days, or the night after someone
#: opened it (Mateusz 2026-11-06).
CURATED_DAYS = 7
#: Cards not made again for as long as this many newer ones.
CURATED_REPEAT = 60
#: Terms a card may be made of: styles, subjects, periods (not of one
#: country in Asia) and the techniques of pictures. Never manuscripts,
#: photographs, sculpture or crafts: those keep to their own group.
CURATED_KINDS = ("style", "subject", "period")
CURATED_TECHNIQUES = (
    "technique:painting",
    "technique:drawing",
    "technique:print",
    "technique:poster",
)
#: Lengths the cards have room for (two lines each in the app).
CURATED_NAME = 40
CURATED_DESCRIPTION = 70

_curated_lock = threading.Lock()


def curated_terms() -> list[Term]:
    """The terms the curator may use."""
    return [
        t
        for t in TERMS
        if (t.kind in CURATED_KINDS and t.region != "east-asia" and not t.key.startswith("years:"))
        or t.key in CURATED_TECHNIQUES
    ]


def _curated_state(library: Library) -> dict[str, Any]:
    return dict(library.get_state(CURATED_KEY, {}) or {})


def curated(library: Library) -> list[Theme]:
    """The curator's cards now shown, in "Dziś dla Ciebie"."""
    cards = _curated_state(library).get("cards") or []
    themes = [replace(_theme_from(c["theme"]), group=WEEKLY) for c in cards]
    _weekly.update({t.key: t for t in themes})
    return themes


def for_you(library: Library, day: date) -> list[Theme]:
    """ "Dziś dla Ciebie" without the theme of the day (the app puts it
    first): the artist of the week, the curator's cards, then as many of
    the week's pairs of terms as the curator left room for."""
    weekly = weekly_themes(library, day)
    mine = curated(library)
    artists = [t for t in weekly if t.key.startswith(ARTIST_PREFIX)]
    mixes = [t for t in weekly if not t.key.startswith(ARTIST_PREFIX)]
    return [*artists, *mine, *mixes[: max(0, WEEKLY_MIXES - len(mine))]]


def curated_seen(library: Library, key: str) -> bool:
    """Someone opened the curator's card ``key``: it is made again the
    next night. Whether it was one."""
    if not key.startswith(CURATED_PREFIX):
        return False
    with _curated_lock:
        state = _curated_state(library)
        cards = state.get("cards") or []
        hit = next((c for c in cards if c["theme"]["key"] == key), None)
        if hit is None or hit.get("seen"):
            return hit is not None
        hit["seen"] = True
        library.set_state(CURATED_KEY, {**state, "cards": cards})
    return True


def curated_due(library: Library, day: date) -> int:
    """How many of the curator's cards are to be made for ``day``: those
    missing, opened, or a week old."""
    cards = _curated_state(library).get("cards") or []
    since = (day - timedelta(days=CURATED_DAYS)).isoformat()
    kept = [c for c in cards if not c.get("seen") and c.get("made", "") > since]
    return CURATED_CARDS - min(len(kept), CURATED_CARDS)


def curated_history(library: Library) -> list[str]:
    """Names of the curator's cards so far, the latest last."""
    return list(_curated_state(library).get("history") or [])


def put_curated(library: Library, made: list[Theme], day: date) -> list[Theme]:
    """The new cards in place of those due (``curated_due``); the others
    stay. Returns the cards now shown."""
    with _curated_lock:
        state = _curated_state(library)
        since = (day - timedelta(days=CURATED_DAYS)).isoformat()
        cards = [
            c for c in state.get("cards") or [] if not c.get("seen") and c.get("made", "") > since
        ]
        room = CURATED_CARDS - len(cards)
        new: list[dict[str, Any]] = [
            {"theme": asdict(t), "made": day.isoformat(), "seen": False} for t in made[:room]
        ]
        cards = (cards + new)[:CURATED_CARDS]
        history = [*(state.get("history") or []), *(t.name for t in made[:room])]
        library.set_state(
            CURATED_KEY, {**state, "cards": cards, "history": history[-CURATED_REPEAT:]}
        )
    if new:
        log.info("curator: %s", ", ".join(t.name for t in made[:room]))
    return curated(library)


@dataclass(frozen=True)
class Proposal:
    """A card as the curator wrote it, before the server checks it."""

    name: str
    description: str
    terms: tuple[str, ...] = ()
    artists: tuple[str, ...] = ()


def check_proposals(
    library: Library, proposals: list[Proposal], artists: list[str], day: date
) -> list[Theme]:
    """The proposals that make good cards, in their order: only known terms
    and the catalogue's own artists (``artists``, as it spells them), short
    enough for the card, not a theme there is already or was lately, and
    with at least ``WEEKLY_MIN`` works in the catalogue."""
    allowed = {t.key for t in curated_terms()}
    taken = {fold(t.name) for t in [*THEMES, *for_you(library, day), *curated(library)]}
    taken |= {fold(name) for name in curated_history(library)}
    made = {frozenset(t.terms) for t in [*THEMES, *for_you(library, day)] if not t.artists}
    found: list[Theme] = []
    for p in proposals:
        name, description = " ".join(p.name.split()), " ".join(p.description.split())
        terms = tuple(dict.fromkeys(t for t in p.terms if t in allowed))
        named = tuple(
            dict.fromkeys(a for wanted in p.artists for a in artists if artist_matches(a, [wanted]))
        )
        reason = ""
        if not name or len(name) > CURATED_NAME or len(description) > CURATED_DESCRIPTION:
            reason = "too long"
        elif len(terms) < len(p.terms) or len(named) < len(p.artists):
            reason = "unknown terms or artists"
        elif not (len(terms) >= 2 or len(named) >= 3 or (terms and len(named) >= 2)):
            reason = "too broad"
        elif fold(name) in taken or (not named and frozenset(terms) in made):
            reason = "made before"
        if not reason:
            theme = Theme(
                f"{CURATED_PREFIX}{_slug(name)}",
                name,
                description,
                WEEKLY,
                artists=named,
                terms=terms,
                catalogue=True,
            )
            if library.query(theme.rules())[0] < WEEKLY_MIN:
                reason = "too few works"
        if reason:
            log.info("curator: %r left out (%s)", p.name, reason)
            continue
        taken.add(fold(name))
        found.append(theme)
    return found


# -- the week's colours ----------------------------------------------------------

#: The colour cards of the week: {"week", "keys", "history"}.
COLOURS_KEY = "colour_themes"
#: Cards of "Kolor i nastrój" each week.
COLOUR_CARDS = 4
#: Least works of a colour card the catalogue must have.
COLOUR_MIN = 12
#: A colour card does not come back for this many weeks (while the pool
#: has enough others).
COLOUR_REPEAT = 4
_colours_lock = threading.Lock()


def make_colours(library: Library, week: str, history: list[str]) -> list[Theme]:
    """``COLOUR_CARDS`` of ``COLOUR_POOL`` for ``week``, drawn from those
    with ``COLOUR_MIN`` works in the catalogue: first those not shown in
    the weeks of ``history`` (oldest first), then the longest unshown."""
    fit = [t for t in COLOUR_POOL if library.query(t.rules(), limit=1)[0] >= COLOUR_MIN]
    rng = random.Random(f"colours:{week}")
    fresh = [t for t in fit if t.key not in history]
    rng.shuffle(fresh)
    # Then those shown the longest time ago.
    seen = sorted((t for t in fit if t.key in history), key=lambda t: history.index(t.key))
    return (fresh + seen)[:COLOUR_CARDS]


def colour_themes(library: Library, day: date) -> list[Theme]:
    """The cards of "Kolor i nastrój" for ``day``'s week: drawn once a week
    and remembered in ``library``, so they change every Monday."""
    week = week_of(day)
    with _colours_lock:
        stored: dict[str, Any] = library.get_state(COLOURS_KEY, {})
        if stored.get("week") == week:
            found = [BY_KEY[k] for k in stored.get("keys") or [] if k in BY_KEY]
            if found:
                return found
        # The cards of the weeks before, oldest first (a week's own last).
        history: list[str] = stored.get("history") or []
        found = make_colours(library, week, history)
        keys = [t.key for t in found]
        history = [*(k for k in history if k not in keys), *keys][-COLOUR_REPEAT * COLOUR_CARDS :]
        library.set_state(COLOURS_KEY, {"week": week, "keys": keys, "history": history})
        log.info("colours of %s: %s", week, ", ".join(t.name for t in found) or "none")
        return found


#: Set once playlists of colour cards keep to paintings and drawings.
PAINTERLY_KEY = "colour_playlists_painterly"


def painterly_colour_playlists(library: Library) -> None:
    """Once (1.97.0): playlists made from a colour card (the starters "W
    odcieniach błękitu" and "Ciepłe barwy" too) keep to paintings, drawings
    and watercolours, as the cards do now."""
    if library.get_state(PAINTERLY_KEY, False):
        return
    by_name = {fold(t.name): t for t in COLOUR_POOL}
    for playlist in library.playlists():
        found = BY_KEY.get(playlist.theme or "") or by_name.get(fold(playlist.name))
        rules = playlist.rules
        if (
            found is None
            or found.group != COLOUR
            or not rules.colors
            or any(t.startswith("technique:") for t in rules.terms)
        ):
            continue
        rules = rules.model_copy(update={"terms": [*rules.terms, *PAINTERLY]})
        library.save_playlist(playlist.model_copy(update={"rules": rules}))
    library.set_state(PAINTERLY_KEY, True)


# -- "Bo lubisz" -----------------------------------------------------------------

#: The cards of "Bo lubisz" as last made: a list of themes.
LIKED_KEY = "liked_themes"
#: Artists like a favourite one on its card.
LIKED_ARTISTS = 4
#: Least works of theirs the catalogue must have for the card.
LIKED_MIN = 4


def surname(name: str) -> str:
    """ "Morisot" for "Berthe Morisot", "van Gogh" and "de Hooch" as they
    are, "Witkiewicz" for "Stanisław Ignacy Witkiewicz"."""
    words = name.split()
    start = next((n for n, w in enumerate(words) if w[:1].islower()), len(words) - 1)
    return " ".join(words[start:]) if words else name


def _listed(names: list[str]) -> str:
    """ "Renoir, Morisot, Degas i Gauguin"."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} i {names[-1]}"


def liked_key(user: str) -> str:
    """Each person's "Bo lubisz" (the owner's under the key from before)."""
    return LIKED_KEY if user == OWNER_ID else f"{LIKED_KEY}:{user}"


def make_liked(library: Library, taste: list[str], user: str = OWNER_ID) -> list[Theme]:
    """A card for each artist ``user`` likes (``taste``, most liked first):
    the artists of the first theme naming them, the ones with the most works
    in the catalogue, browsed in the museums like the theme. Remembered in
    ``library``, so a card opened after a restart is still found."""
    rules = PlaylistRules(kinds=[ItemKind.ARTWORK])
    have = Counter(i.artist for i in library.query(rules)[1])
    made: list[Theme] = []
    seen: set[str] = set()
    for artist in taste:
        found = next(
            (t for t in THEMES if t.artists and artist_matches(artist, list(t.artists))), None
        )
        if found is None:
            continue
        own = [a for a in found.artists if artist_matches(artist, [a])]
        if not own or own[0] in seen:
            continue  # the same artist spelled otherwise
        seen.add(own[0])
        counts = {
            a: sum(n for name, n in have.items() if artist_matches(name, [a]))
            for a in found.artists
            if a not in own
        }
        others = sorted((a for a, n in counts.items() if n), key=lambda a: -counts[a])
        others = others[:LIKED_ARTISTS]
        if sum(counts[a] for a in others) < LIKED_MIN:
            continue
        queries = tuple(q for q in found.queries if any(fold(a) in fold(q[1]) for a in others))
        made.append(
            Theme(
                f"like-{_slug(artist)}",
                artist,
                _listed([surname(a) for a in others]),
                LIKES,
                artists=tuple(others),
                queries=queries,
                playlist=f"Bo lubisz: {artist}",
            )
        )
    library.set_state(liked_key(user), [asdict(t) for t in made])
    return made


def liked(library: Library, user: str | None = None) -> list[Theme]:
    """``user``'s cards of "Bo lubisz" as last made (default: the asking
    person's)."""
    return [_theme_from(t) for t in library.get_state(liked_key(user or viewer_id()), [])]


def browse_theme(
    importer: Importer, found: Theme, page: int = 1, limit: int = 24, wait: float = BROWSE_WAIT
) -> tuple[list[Item], int | None]:
    """One page of a theme: its museum searches one after another (page 1
    is the first search, page 2 the next; after the last one their second
    pages follow), or the catalogue for themes without searches. A search
    that finds nothing (or fails) is passed over for the next one, for
    ``wait`` seconds at most. Returns the works and the page to ask for
    next, None after the last."""
    if not found.searches():
        items, more = browse_catalogue(importer.library, found, page, limit)
        return items, page + 1 if more else None
    started = time.monotonic()
    failed: httpx.HTTPError | ValueError | None = None
    answered = False
    while True:
        kept: list[Item] = []
        total = 0
        try:
            kept, total = search_page(importer, found, page, limit)
            answered = True
        except (httpx.HTTPError, ValueError) as err:
            log.warning("theme %s: page %d failed: %s", found.key, page, err)
            failed = err
        following = page_after(found, page, total, limit)
        if kept or following is None or time.monotonic() - started >= wait:
            if not kept and not answered and failed is not None:
                raise failed  # every museum asked failed: say so
            return kept, following
        page = following


def kept_close(found: Theme) -> bool:
    """A theme browsed in the museums whose works the catalogue holds too:
    antiquity (``strict``) and "Sztuki inne". Its set opens with the
    catalogue's works at once (the Met, which most of their searches ask,
    takes seconds a page), and what the museums found joins the catalogue
    for its cover and the next visit."""
    return bool(found.searches()) and (
        found.strict or any(k in OBJECT_CATEGORIES for k in found.terms)
    )


def search_page(
    importer: Importer, found: Theme, page: int, limit: int = 24
) -> tuple[list[Item], int]:
    """The museum search of one page of a theme (with searches): its works,
    without those set aside, and how many the search has in all. Raises
    when the museum fails."""
    searches = found.searches()
    source, query = searches[(page - 1) % len(searches)]
    round_ = (page - 1) // len(searches) + 1
    total, items = importer.search(source, query, limit=limit, page=round_)
    asked = [k for k in found.terms if k in OBJECT_CATEGORIES]
    if asked:  # "Sztuki inne": the theme's technique only
        kept = [i for i in items if object_category(i) in asked and not set_aside(i, asked)]
    else:
        kept = [i for i in items if not set_aside(i)]
    if found.strict:
        rules = found.rules()
        kept = [i for i in kept if matches(i, rules)]
    return kept, total


def page_after(found: Theme, page: int, total: int, limit: int = 24) -> int | None:
    """The page after ``page`` of a theme with searches, whose search has
    ``total`` works; None when it was the last."""
    count = len(found.searches())
    round_ = (page - 1) // count + 1
    return page + 1 if page % count != 0 or round_ * limit < total else None


def batch_of(found: Theme, page: int, size: int) -> list[int]:
    """Pages of a theme with searches asked at once from ``page``: up to
    ``size``, not past the last search of a round (whether another round
    follows is known only from the last one)."""
    count = len(found.searches())
    return list(range(page, page + min(size, count - (page - 1) % count)))


def browse_catalogue(
    library: Library, found: Theme, page: int = 1, limit: int = 24
) -> tuple[list[Item], bool]:
    total, items = library.query(
        found.rules(), sort="suitability", offset=(page - 1) * limit, limit=limit
    )
    return items, page * limit < total
