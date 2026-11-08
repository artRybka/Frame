"""Names that are no artist ("Desconegut", "Anonymous", "Japanese") are not
grouped by: no artist of the week, no "Bo lubisz", no artist in the search."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pytest

from frame_server.library import Item, ItemKind
from frame_server.library.artists import ArtistNames, is_artist, learn, made_by
from frame_server.library.duplicates import artist_words
from frame_server.library.themes import (
    WEEK_KEY,
    WEEKLY,
    Theme,
    artist_of_the_week,
    new_artist_of_the_week,
    week_of,
    weekly_themes,
)


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


def test_the_artist_of_the_week_drawn_again(service) -> None:
    library = service.library
    with library.batch():
        for n, artist in enumerate(["Theodore Robinson", "Mary Cassatt", "Childe Hassam"]):
            for k in range(14):
                library.upsert(_work(100 * n + k, artist))
    day = date(2026, 11, 2)
    first = artist_of_the_week(library, day)
    assert first is not None
    second = new_artist_of_the_week(library, day)
    assert second is not None and second.name != first.name
    assert second.description.startswith("Artysta tygodnia.")
    # Kept for the week, in the artist's place.
    assert artist_of_the_week(library, day) == second
    assert [t for t in weekly_themes(library, day) if t.artists] == [second]
    third = new_artist_of_the_week(library, day)
    assert third is not None and third.name not in {first.name, second.name}
    assert new_artist_of_the_week(library, day) is None  # nobody left
    assert artist_of_the_week(library, day) == third


def test_a_week_made_with_a_nameless_artist_gets_another(service) -> None:
    library = service.library
    _fill(library)
    day = date(2026, 10, 31)
    nameless = Theme(
        "week-artist-desconegut",
        "Desconegut",
        "Artysta tygodnia. 40 dzieł na ten tydzień.",
        "Dziś dla Ciebie",
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


def test_a_week_stored_under_the_old_group_name_shows_under_the_new(service) -> None:
    library = service.library
    day = date(2026, 10, 31)
    artist = Theme(
        "week-artist-theodore-robinson",
        "Theodore Robinson",
        "Artysta tygodnia. 40 dzieł na ten tydzień.",
        "Na ten tydzień",
        artists=("Theodore Robinson",),
        catalogue=True,
    )
    library.set_state(
        WEEK_KEY,
        {"week": week_of(day), "themes": [asdict(artist)], "history": [artist.key]},
    )
    assert WEEKLY == "Dziś dla Ciebie"
    assert [(t.key, t.group) for t in weekly_themes(library, day)] == [(artist.key, WEEKLY)]


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


def test_konfiguracja_draws_another_artist_of_the_week(service) -> None:
    from fastapi.testclient import TestClient

    from frame_server.web import create_app, discover_api

    app = create_app(service.settings)
    app.state.service = service
    discover_api._cards = (0.0, {})
    with TestClient(app) as client:
        library = service.library
        with library.batch():
            for n, artist in enumerate(["Theodore Robinson", "Mary Cassatt"]):
                for k in range(14):
                    library.upsert(_work(100 * n + k, artist))
        first = artist_of_the_week(library, date.today())
        assert first is not None
        cards = client.get("/api/themes").json()
        assert first.key in [c["key"] for c in cards]
        answer = client.post("/api/themes/week-artist/again")
        assert answer.status_code == 200
        card = answer.json()
        assert card["name"] != first.name and card["count"] == 14 and card["cover"]
        # Discover shows it at once, in the old one's place.
        keys = [c["key"] for c in client.get("/api/themes").json()]
        assert card["key"] in keys and first.key not in keys
        assert client.post("/api/themes/week-artist/again").status_code == 409


def _people(*names: str) -> list[list[str]]:
    found = ArtistNames({n: {n} for n in names})
    return sorted(sorted(s) for s in found.spellings.values())


def test_spellings_of_one_artist() -> None:
    assert _people("Jan van Eyck", "Jan Van Eyck", "Eyck, Jan van") == [
        ["Eyck, Jan van", "Jan Van Eyck", "Jan van Eyck"]
    ]
    # The Met's "X (Y)" says the one-word name is the full one.
    assert _people(
        "Rembrandt",
        "Rembrandt (Rembrandt van Rijn)",
        "Rembrandt Harmensz. van Rijn",
        "Rembrandt Peale",
    ) == [
        ["Rembrandt", "Rembrandt (Rembrandt van Rijn)", "Rembrandt Harmensz. van Rijn"],
        ["Rembrandt Peale"],
    ]
    assert _people(
        "El Greco", "El Greco (Domenikos Theotokopoulos)", "Domenikos Theotokopoulos"
    ) == [["Domenikos Theotokopoulos", "El Greco", "El Greco (Domenikos Theotokopoulos)"]]
    assert _people("Diego Velázquez", "Diego Rodríguez de Silva y Velázquez") == [
        ["Diego Rodríguez de Silva y Velázquez", "Diego Velázquez"]
    ]
    # One name in one longer one only.
    assert _people("Hokusai", "Katsushika Hokusai") == [["Hokusai", "Katsushika Hokusai"]]


def test_other_people_of_a_name_stay_apart() -> None:
    # Without the Met, "Rembrandt" is in two people's names: nobody's.
    assert _people("Rembrandt", "Rembrandt van Rijn", "Rembrandt Peale") == [
        ["Rembrandt"],
        ["Rembrandt Peale"],
        ["Rembrandt van Rijn"],
    ]
    assert _people("Pieter Bruegel", "Pieter Bruegel the Elder", "Pieter Bruegel the Younger") == [
        ["Pieter Bruegel"],
        ["Pieter Bruegel the Elder"],
        ["Pieter Bruegel the Younger"],
    ]
    assert _people("Utagawa Hiroshige", "Utagawa Hiroshige II") == [
        ["Utagawa Hiroshige"],
        ["Utagawa Hiroshige II"],
    ]
    assert _people("Rembrandt van Rijn", "Workshop of Rembrandt van Rijn", "Unknown") == [
        ["Rembrandt van Rijn"]
    ]
    assert _people("Pieter Bruegel (the Elder)", "Pieter Bruegel") == [
        ["Pieter Bruegel"],
        ["Pieter Bruegel (the Elder)"],
    ]


def test_the_shown_name_is_the_one_of_most_works() -> None:
    names = ArtistNames(
        {
            "Rembrandt van Rijn": {1, 2, 3},
            "Rembrandt (Rembrandt van Rijn)": {4, 5, 6, 7},
            "Rembrandt": {8},
        }
    )
    # A plain spelling before the Met's.
    assert names.shown("Rembrandt") == "Rembrandt van Rijn"
    assert names.shown("REMBRANDT VAN RIJN") == "Rembrandt van Rijn"
    assert names.shown("Someone Else") == "Someone Else"


def test_a_search_for_an_artist_finds_every_spelling() -> None:
    assert not made_by("Rembrandt", ["Rembrandt van Rijn"])  # nothing learnt yet
    learn(
        ArtistNames(
            {"Rembrandt (Rembrandt van Rijn)": {1}, "Rembrandt": {2}, "Rembrandt Peale": {3}}
        )
    )
    assert made_by("Rembrandt", ["Rembrandt van Rijn"])
    assert made_by("Rembrandt (Rembrandt van Rijn)", ["Rembrandt"])
    assert not made_by("Rembrandt Peale", ["Rembrandt van Rijn"])
    assert not made_by("Pupil of Rembrandt", ["Rembrandt van Rijn"])
    assert not made_by("After Rembrandt", ["Rembrandt"])
