"""Starter library and default playlists, following the owner's priorities:
world museums, Polish art, Japanese woodblock prints, posters & illustration.
"""

from __future__ import annotations

import logging

import httpx

from .importer import Importer, Job
from .models import Playlist, PlaylistKind, PlaylistRules

log = logging.getLogger(__name__)

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

SEED_QUERIES: list[tuple[str, str, int]] = [
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
    Playlist(
        name="Najlepiej na e-papierze",
        description="Obrazy, które najlepiej wychodzą na tym ekranie.",
        rules=PlaylistRules(min_suitability=0.72),
    ),
    Playlist(
        name="Ulubione",
        description="Twoje serduszka.",
        rules=PlaylistRules(favorites_only=True),
    ),
]


def seed_playlists(importer: Importer) -> None:
    library = importer.library
    if library.playlists():
        return
    for playlist in DEFAULT_PLAYLISTS:
        library.save_playlist(playlist.model_copy(update={"kind": PlaylistKind.SMART}))


def seed_library(importer: Importer, job: Job) -> None:
    """Fill an empty library. Each query is best effort."""
    seed_playlists(importer)
    for source, query, limit in SEED_QUERIES:
        try:
            importer.import_search(source, query, limit, job)
        except (httpx.HTTPError, OSError, ValueError) as err:
            log.warning("seed query %s %r failed: %s", source, query, err)
            job.failed += 1
