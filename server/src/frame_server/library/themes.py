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
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

import httpx

from .importer import Importer
from .models import Item, ItemKind, PlaylistRules
from .nationality import artist_note
from .repo import Library
from .seed import MORE_POLISH_PAINTERS, PACKS, POLISH_PAINTERS
from .vocabulary import (
    HIGHLIGHT,
    TERMS,
    _text,
    artist_matches,
    fold,
    museum_queries,
    set_aside,
    term_matches,
)

log = logging.getLogger(__name__)

#: Museums asked for a theme's artists or words when it names no searches.
SEARCH_SOURCES = ("aic", "cma", "met")
#: A theme's page goes on to its next searches while one finds nothing,
#: for this many seconds at most; the app asks for the rest.
BROWSE_WAIT = 8.0

GROUPS = (
    "Na ten tydzień",
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
    #: Words every work's text must have (a season: "autumn").
    query: str = ""
    #: Browsed in the catalogue only (themes made from what it holds).
    catalogue: bool = False

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


WEEKLY = "Na ten tydzień"
STYLES = "Kierunki i style"
PRINTS = "Grafika i plakat"
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


def theme(key: str, library: Library | None = None) -> Theme:
    """A theme by its key: one of ``THEMES`` or of the week's (those need
    ``library`` after a restart)."""
    found = BY_KEY.get(key) or _weekly.get(key)
    if found is None and library is not None:
        weekly_themes(library, date.today())
        found = _weekly.get(key)
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
    ((2, 14), (2, 14), "Walentynki", "flowers"),
    ((3, 21), (3, 21), "Pierwszy dzień wiosny", "spring"),
    ((5, 3), (5, 3), "Święto Konstytucji 3 Maja", "polish"),
    ((6, 21), (6, 21), "Pierwszy dzień lata", "summer"),
    ((9, 23), (9, 23), "Pierwszy dzień jesieni", "autumn"),
    ((11, 1), (11, 2), "Wszystkich Świętych", "autumn"),
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
#: Names that are no artist's.
_NAMELESS = re.compile(r"unknown|anonymous|nieznany|anonim|^$", re.IGNORECASE)

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
    counts = Counter(i.artist for i in items if not _NAMELESS.search(i.artist))
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
        f"Artysta tygodnia. {about}W katalogu: {_works(counts[artist])}.",
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
        text = _text(item)
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
                f"{a.name} i {b.name.lower()}: {_works(pairs[first, second])} w katalogu, "
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


def weekly_themes(library: Library, day: date) -> list[Theme]:
    """The themes of ``day``'s week: made once a week (the first time, a
    pass over the catalogue) and remembered in ``library``."""
    week = week_of(day)
    with _weekly_lock:
        stored: dict[str, Any] = library.get_state(WEEK_KEY, {})
        if stored.get("week") == week:
            themes = [_theme_from(t) for t in stored.get("themes") or []]
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
