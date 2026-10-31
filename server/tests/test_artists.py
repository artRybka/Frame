"""Names that are no artist ("Desconegut", "Anonymous", "Japanese") are not
grouped by: no artist of the week, no "Bo lubisz", no artist in the search."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pytest

from frame_server.library import Item, ItemKind
from frame_server.library.artists import is_artist
from frame_server.library.duplicates import artist_words
from frame_server.library.themes import WEEK_KEY, Theme, week_of, weekly_themes


@pytest.mark.parametrize(
    "name",
    [
        "",
        "Desconegut",
        "Anònim",
        "Fotògraf desconegut",
        "Autor desconegut",
        "Unknown",
        "Unknown artist",
        "Artist unknown",
        "Anonymous",
        "Anoniem",
        "Onbekend",
        "Anonyme",
        "Inconnu",
        "Anónimo",
        "Desconocido",
        "Unbekannt",
        "Ukendt",
        "Nieznany",
        "Nieznany artysta",
        "Anonim",
        "Unidentified photographer",
        "Various artists",
        "Artist",
        "Japanese",
        "Japanese, Edo period",
        "French School, 19th century",
        "Workshop of Peter Paul Rubens",
        "Circle of Rembrandt",
        "Attributed to Jan Steen",
        "After Raphael",
        "Detroit Publishing Co.",
        "Imprenta Moderna",
    ],
)
def test_nobody(name: str) -> None:
    assert not is_artist(name)


@pytest.mark.parametrize(
    "name",
    [
        "Vincent van Gogh",
        "Gogh, Vincent van",
        "Katsushika Hokusai\nJapanese, 1760-1849",
        "Roman Opałka",
        "Henri de Toulouse-Lautrec",
        "Jan van Eyck",
        "Ai Weiwei",
        "Currier & Ives",
        "Master of the Female Half-lengths",
        "Józef Chełmoński",
    ],
)
def test_someone(name: str) -> None:
    assert is_artist(name)


def test_nameless_works_are_not_one_artist() -> None:
    assert artist_words("Desconegut") == frozenset()
    assert artist_words("Fotògraf desconegut") == frozenset()
    assert artist_words("Claude Monet") == {"claude", "monet"}


def _work(n: int, artist: str) -> Item:
    return Item(
        id=f"cma:{n}",
        source="cma",
        source_id=str(n),
        kind=ItemKind.ARTWORK,
        title=f"Harbour {n}",
        artist=artist,
        suitability=0.6,
        pooled=True,
    )


def _fill(library) -> None:
    with library.batch():
        for n in range(40):
            library.upsert(_work(n, "Desconegut"))
        for n in range(40, 60):
            library.upsert(_work(n, "Anonymous"))
        for n in range(60, 74):
            library.upsert(_work(n, "Theodore Robinson"))


def test_artist_of_the_week_is_someone(service) -> None:
    library = service.library
    _fill(library)
    themes = weekly_themes(library, date(2026, 11, 2))
    artists = [t for t in themes if t.artists]
    assert [t.name for t in artists] == ["Theodore Robinson"]


def test_a_week_made_with_a_nameless_artist_gets_another(service) -> None:
    library = service.library
    _fill(library)
    day = date(2026, 10, 31)
    nameless = Theme(
        "week-artist-desconegut",
        "Desconegut",
        "Artysta tygodnia. W katalogu: 40 dzieł.",
        "Na ten tydzień",
        artists=("Desconegut",),
        catalogue=True,
    )
    library.set_state(
        WEEK_KEY,
        {"week": week_of(day), "themes": [asdict(nameless)], "history": [nameless.key]},
    )
    themes = weekly_themes(library, day)
    assert [t.name for t in themes if t.artists] == ["Theodore Robinson"]
    assert "Desconegut" not in str(library.get_state(WEEK_KEY, {})["themes"])
    # Remembered: the same again.
    assert [t.key for t in weekly_themes(library, day)] == [t.key for t in themes]


def test_taste_and_search_leave_nobody_out(service) -> None:
    library = service.library
    with library.batch():
        for n in range(5):
            item = _work(n, "Desconegut").model_copy(update={"favorite": True, "pooled": False})
            library.upsert(item)
        library.upsert(_work(9, "Claude Monet").model_copy(update={"favorite": True}))
    assert service.player.taste() == ["Claude Monet"]
    assert [f.value for f in library.facets().artists] == ["Claude Monet"]


def test_girona_photo_archive_is_set_aside() -> None:
    from frame_server.library.vocabulary import set_aside

    photo = Item(
        id="europeana:718~Museu_1",
        source="europeana",
        source_id="718~Museu_1",
        kind=ItemKind.ARTWORK,
        title="[Painting]",
        artist="Desconegut",
    )
    other = photo.model_copy(update={"id": "europeana:2048047~x", "source_id": "2048047~x"})
    assert set_aside(photo) and not set_aside(other)
