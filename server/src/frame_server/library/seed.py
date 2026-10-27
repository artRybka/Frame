"""Starter library, themed packs and default playlists, following the owner's
priorities: world museums, Polish art, Japanese woodblock prints, posters &
illustration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .importer import Importer, Job
from .models import Playlist, PlaylistKind, PlaylistRules
from .repo import Library

log = logging.getLogger(__name__)

#: The owner's hearts; always there (see ensure_favorites).
FAVORITES = Playlist(
    name="Ulubione",
    description="Twoje serduszka.",
    rules=PlaylistRules(favorites_only=True),
)

#: (museum, query, how many works)
Query = tuple[str, str, int]

POLISH_PAINTERS = [
    "Józef Chełmoński",
    "Jacek Malczewski",
    "Olga Boznańska",
    "Jan Matejko",
    "Julian Fałat",
    "Władysław Podkowiński",
    "Aleksander Gierymski",
    "Leon Wyczółkowski",
    "Józef Mehoffer",
    "Stanisław Wyspiański",
]

# Painters for the Polish pack on top of the starter ones; all died before
# 1956, so their works are in the public domain in Poland too.
MORE_POLISH_PAINTERS = [
    "Józef Brandt",
    "Maksymilian Gierymski",
    "Wojciech Gerson",
    "Henryk Siemiradzki",
    "Anna Bilińska",
    "Jan Stanisławski",
    "Ferdynand Ruszczyc",
    "Teodor Axentowicz",
    "Józef Pankiewicz",
    "Wojciech Weiss",
    "Artur Grottger",
    "Piotr Michałowski",
    "Alfred Wierusz-Kowalski",
    "Stanisław Witkiewicz",
    "Kazimierz Stabrowski",
]

SEED_QUERIES: list[Query] = [
    # Japanese woodblock prints
    ("aic", "Hokusai", 12),
    ("aic", "Hiroshige", 12),
    ("cma", "Hiroshige", 8),
    ("aic", "Utamaro", 4),
    # Impressionism and around
    ("aic", "Claude Monet", 10),
    ("cma", "Monet", 6),
    ("aic", "Vincent van Gogh", 5),
    ("aic", "Cezanne", 5),
    # Posters and illustration
    ("aic", "Toulouse-Lautrec poster", 6),
    ("aic", "Mucha", 4),
    ("cma", "poster", 8),
    ("cma", "botanical", 8),
    # Polish art (Wikimedia Commons categories)
    *[("wmc", f"Category:Paintings by {name}", 6) for name in POLISH_PAINTERS],
]


@dataclass(frozen=True)
class Pack:
    """A themed batch of museum searches the owner can add with one tap."""

    key: str
    name: str
    description: str
    queries: list[Query]

    @property
    def size(self) -> int:
        """Most works the pack can add (fewer when searches come up short)."""
        return sum(limit for _, _, limit in self.queries)


PACKS: list[Pack] = [
    Pack(
        "impressionism",
        "Impresjonizm i postimpresjonizm",
        "Monet, Renoir, Pissarro, Sisley, Degas, Morisot, Cassatt, van Gogh, Cézanne, Seurat.",
        [
            ("aic", "Claude Monet", 40),
            ("cma", "Monet", 20),
            ("aic", "Pierre-Auguste Renoir", 20),
            ("aic", "Camille Pissarro", 20),
            ("aic", "Alfred Sisley", 10),
            ("aic", "Edgar Degas", 20),
            ("aic", "Berthe Morisot", 10),
            ("aic", "Mary Cassatt", 15),
            ("aic", "Gustave Caillebotte", 8),
            ("aic", "Vincent van Gogh", 15),
            ("aic", "Paul Cezanne", 20),
            ("aic", "Georges Seurat", 8),
            ("aic", "Paul Gauguin", 15),
        ],
    ),
    Pack(
        "ukiyo-e",
        "Japońskie drzeworyty",
        "Hokusai, Hiroshige, Utamaro, Kuniyoshi, Harunobu i inni mistrzowie ukiyo-e.",
        [
            ("aic", "Katsushika Hokusai", 60),
            ("aic", "Utagawa Hiroshige", 80),
            ("cma", "Hiroshige", 40),
            ("cma", "Hokusai", 30),
            ("aic", "Kitagawa Utamaro", 25),
            ("aic", "Utagawa Kuniyoshi", 25),
            ("aic", "Keisai Eisen", 15),
            ("aic", "Suzuki Harunobu", 20),
            ("aic", "Torii Kiyonaga", 15),
        ],
    ),
    Pack(
        "dutch",
        "Malarstwo holenderskie",
        "Rijksmuseum: Vermeer, Rembrandt, Hals, Steen, Ruisdael, aż po Breitnera i Marisa.",
        [
            ("rijks", "creator=Johannes Vermeer&type=painting", 4),
            ("rijks", "creator=Rembrandt van Rijn&type=painting", 24),
            ("rijks", "creator=Frans Hals&type=painting", 9),
            ("rijks", "creator=Jan Havicksz. Steen&type=painting", 22),
            ("rijks", "creator=Pieter de Hooch&type=painting", 6),
            ("rijks", "creator=Jacob Isaacksz. van Ruisdael&type=painting", 12),
            ("rijks", "creator=Hendrick Avercamp&type=painting", 4),
            ("rijks", "creator=Willem Claesz. Heda&type=painting", 4),
            ("rijks", "creator=Jan Davidsz. de Heem&type=painting", 3),
            ("rijks", "creator=Aelbert Cuyp&type=painting", 4),
            ("rijks", "creator=George Hendrik Breitner&type=painting", 30),
            ("rijks", "creator=Jacob Maris&type=painting", 20),
            ("rijks", "creator=Isaac Israels&type=painting", 13),
        ],
    ),
    Pack(
        "polish",
        "Sztuka polska",
        "Więcej obrazów Chełmońskiego, Malczewskiego, Boznańskiej i 15 kolejnych malarzy.",
        [
            *[("wmc", f"Category:Paintings by {name}", 20) for name in POLISH_PAINTERS],
            *[("wmc", f"Category:Paintings by {name}", 12) for name in MORE_POLISH_PAINTERS],
        ],
    ),
    Pack(
        "posters",
        "Plakaty i secesja",
        "Mucha, Toulouse-Lautrec, Steinlen, Chéret, Grasset i plakat przełomu wieków.",
        [
            ("aic", "Alphonse Mucha", 20),
            ("aic", "Toulouse-Lautrec poster", 25),
            ("aic", "Théophile-Alexandre Steinlen", 15),
            ("aic", "Jules Chéret", 15),
            ("aic", "Eugène Grasset", 10),
            ("cma", "poster", 40),
            ("aic", "Pierre Bonnard", 10),
        ],
    ),
    Pack(
        "nature",
        "Botanika i natura",
        "Ryciny botaniczne, ptaki Audubona, motyle i kwiaty Merian.",
        [
            ("cma", "botanical", 40),
            ("aic", "botanical", 20),
            ("aic", "John James Audubon", 20),
            ("met", "Audubon", 15),
            ("rijks", "creator=Maria Sibylla Merian", 4),
            ("met", "Maria Sibylla Merian", 15),
            ("met", "Redouté", 20),
        ],
    ),
    Pack(
        "landscapes",
        "Pejzaże XIX wieku",
        "Turner, Constable, Corot, Inness, Homer, Sargent i Szkoła znad rzeki Hudson.",
        [
            ("aic", "Jean-Baptiste-Camille Corot", 15),
            ("aic", "Joseph Mallord William Turner", 10),
            ("aic", "John Constable", 8),
            ("aic", "George Inness", 10),
            ("aic", "Winslow Homer", 20),
            ("aic", "John Singer Sargent", 15),
            ("cma", "Hudson River School", 15),
            ("met", "Thomas Cole", 10),
            ("met", "Albert Bierstadt", 10),
            ("aic", "James McNeill Whistler", 15),
        ],
    ),
]


def pack(key: str) -> Pack:
    for found in PACKS:
        if found.key == key:
            return found
    raise KeyError(f"unknown pack {key!r}; choose from {[p.key for p in PACKS]}")


DEFAULT_PLAYLISTS: list[Playlist] = [
    Playlist(
        name="Japońskie drzeworyty",
        description="Hokusai, Hiroshige, Utamaro: ukiyo-e, płaskie i wyraziste barwy.",
        rules=PlaylistRules(query="woodblock"),
    ),
    Playlist(
        name="Impresjonizm",
        description="Światło i kolor: Monet, van Gogh, Cézanne.",
        rules=PlaylistRules(artists=["Claude Monet", "Vincent van Gogh", "Paul Cezanne"]),
    ),
    Playlist(
        name="Sztuka polska",
        description="Chełmoński, Malczewski, Boznańska, Matejko i inni.",
        rules=PlaylistRules(artists=POLISH_PAINTERS),
    ),
    Playlist(
        name="Plakaty i ilustracje",
        description="Toulouse-Lautrec, Mucha, secesja i ilustracja botaniczna.",
        rules=PlaylistRules(
            artists=[
                "Henri de Toulouse-Lautrec",
                "Alphonse Marie Mucha",
                "Theo van Rysselberghe",
                "Eugène Grasset",
                "Sydenham Edwards",
            ]
        ),
    ),
    Playlist(
        name="W odcieniach błękitu",
        description="Niebo, woda i indygo.",
        rules=PlaylistRules(colors=["blue"]),
    ),
    Playlist(
        name="Ciepłe barwy",
        description="Ochra, czerwień i złoto.",
        rules=PlaylistRules(colors=["warm"]),
    ),
    FAVORITES,
]


def seed_playlists(importer: Importer) -> None:
    library = importer.library
    if not library.playlists():
        for playlist in DEFAULT_PLAYLISTS:
            library.save_playlist(playlist.model_copy(update={"kind": PlaylistKind.SMART}))
    ensure_favorites(library)


def ensure_favorites(library: Library) -> None:
    """ "Ulubione" is always there, even with no hearts yet: brings it back
    when a library has none (e.g. deleted before it couldn't be)."""
    if not any(p.is_favorites for p in library.playlists()):
        library.save_playlist(FAVORITES.model_copy())


def import_queries(importer: Importer, queries: list[Query], job: Job) -> None:
    """Run museum searches into the library. Each query is best effort."""
    for source, query, limit in queries:
        try:
            importer.import_search(source, query, limit, job)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.warning("query %s %r failed: %s", source, query, err)
            job.failed += 1


def seed_library(importer: Importer, job: Job) -> None:
    """Fill an empty library."""
    seed_playlists(importer)
    import_queries(importer, SEED_QUERIES, job)
