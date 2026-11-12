"""Names that are no artist ("Desconegut", "Anonymous", "Japanese") are not
grouped by: no artist of the week, no "Bo lubisz", no artist in the search."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pytest

from frame_server.library import Item, ItemKind
from frame_server.library.artists import (
    ArtistNames,
    is_artist,
    learn,
    made_by,
    name_key,
    same_hand,
)
from frame_server.library.duplicates import artist_words
from frame_server.library.themes import (
    CURATED_KEY,
    WEEK_KEY,
    WEEKLY,
    Theme,
    artist_of_the_week,
    curated,
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


def test_a_card_stored_with_what_a_theme_no_longer_has_still_shows(service) -> None:
    """1.145.14 took ``min_suitability`` from the themes; the week's themes
    and the curator's cards stored before it failed to be read, and with
    them Odkrywaj's cards and the day's proposals (the NAS, 2026-11-12)."""
    library = service.library
    day = date(2026, 10, 31)
    artist = Theme(
        "week-artist-theodore-robinson",
        "Theodore Robinson",
        "Artysta tygodnia. 40 dzieł na ten tydzień.",
        WEEKLY,
        artists=("Theodore Robinson",),
        catalogue=True,
    )
    stored = {**asdict(artist), "min_suitability": 0.4}
    library.set_state(WEEK_KEY, {"week": week_of(day), "themes": [stored], "history": [artist.key]})
    assert [t.key for t in weekly_themes(library, day)] == [artist.key]
    card = {**asdict(artist), "key": "curator-light", "min_suitability": None}
    library.set_state(CURATED_KEY, {"cards": [{"theme": card, "day": day.isoformat()}]})
    assert [t.key for t in curated(library)] == ["curator-light"]


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
    from frame_server.library.verdict import Place, against

    photo = Item(
        id="europeana:718~Museu_1",
        source="europeana",
        source_id="718~Museu_1",
        kind=ItemKind.ARTWORK,
        title="[Painting]",
        artist="Desconegut",
    )
    other = photo.model_copy(update={"id": "europeana:2048047~x", "source_id": "2048047~x"})
    assert against(photo, Place.SOUGHT) and not against(other, Place.SOUGHT)


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


def test_a_list_of_artists_joins_none_of_them() -> None:
    # One work credited to several people, or a description of a set, held
    # Dürer, Renoir, Tiepolo and Toulouse-Lautrec as one person, and Van Gogh
    # with them (Mateusz, 2026-11-09: "Olbracht Dürer" for "vincent van gogh").
    listed = (
        "Albrecht Dürer, Vincent van Gogh, Pierre-Auguste Renoir, "
        "Henri de Toulouse-Lautrec, Giovanni Battista Tiepolo"
    )
    people = _people(
        "Albrecht Dürer",
        "Vincent van Gogh",
        "Pierre-Auguste Renoir",
        "Henri de Toulouse-Lautrec",
        "Giovanni Battista Tiepolo",
        listed,
        "Renoir, Dürer",
    )
    assert all(len(p) == 1 for p in people), people
    # Spellings of one person still join: few words more, nobody else's.
    assert _people("Renoir", "Pierre-Auguste Renoir", "Dürer", "Dürer, Renoir") == [
        ["Dürer"],
        ["Dürer, Renoir"],
        ["Pierre-Auguste Renoir", "Renoir"],
    ]


def test_a_remark_in_brackets_joins_nobody() -> None:
    # "(signed by artist)" after Dürer, Van Gogh and Storck read as the Met's
    # full name and made one person of all three: "Olbracht Dürer" 3033 for
    # "van Gogh", Storck in the Van Gogh playlist (Mateusz, 2026-11-09).
    people = _people(
        "Albrecht Dürer",
        "Albrecht Dürer (signed by artist)",
        "Vincent van Gogh",
        "Vincent van Gogh (signed by artist)",
        "Vincent Van Gogh, The Netherlands",
        "Vincent van Gogh (possibly)",
        "Vincent van Gogh (Dutch, 1853-1890)",
        "Abraham Storck",
        "Abraham Storck (signed by artist)",
        "Pierre-Auguste Renoir (mentioned on object)",
        "Roeloffzen & Hübner (mentioned on object)",
        "Giovanni Battista Tiepolo (mentioned on object)",
    )
    assert people == [
        ["Abraham Storck", "Abraham Storck (signed by artist)"],
        ["Albrecht Dürer", "Albrecht Dürer (signed by artist)"],
        ["Giovanni Battista Tiepolo (mentioned on object)"],
        ["Pierre-Auguste Renoir (mentioned on object)"],
        ["Roeloffzen & Hübner (mentioned on object)"],
        [
            "Vincent Van Gogh, The Netherlands",
            "Vincent van Gogh",
            "Vincent van Gogh (Dutch, 1853-1890)",
            "Vincent van Gogh (possibly)",
            "Vincent van Gogh (signed by artist)",
        ],
    ]
    # A full name after two people's names is a remark too.
    assert len(_people("Jan Steen (Hanna Blom)", "Frans Hals (Hanna Blom)")) == 2
    # What makes another person stays: a generation, a reversed name.
    assert _people("Pieter Bruegel (the Elder)", "Pieter Bruegel") == [
        ["Pieter Bruegel"],
        ["Pieter Bruegel (the Elder)"],
    ]
    assert name_key("Opałka, Roman") == {"opalka", "roman"}
    assert name_key("Gogh, Vincent van") == name_key("Vincent van Gogh")


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


def test_a_name_the_museum_takes_back_is_not_the_maker() -> None:
    """A copy said after the name, an attribution given up, a forgery (the
    catalogue of 2026-11-11: 15 works "Lucas Cranach the Elder, After", 12
    "formerly attributed to" Rodin, all among the artists' own)."""
    for line in (
        "Lucas Cranach the Elder, After",
        "Formerly attributed to Mi Fu (傳)米芾 (1052-1107)",
        "Artist, formerly attributed to: Auguste Rodin",
        "Artist, forgery of: John Trumbull",
    ):
        assert not is_artist(line), line
    assert not made_by("Lucas Cranach the Elder, After", ["Lucas Cranach the Elder"])
    assert not made_by("Formerly attributed to Vincent van Gogh", ["Vincent van Gogh"])
    assert not made_by("Artist, formerly attributed to: Auguste Rodin", ["Auguste Rodin"])
    assert not made_by("Artist, forgery of: John Trumbull", ["John Trumbull"])
    assert not made_by("Rembrandt van Rijn (værksted)", ["Rembrandt van Rijn"])
    # A year's "after" takes nothing back, and the museum still gives an
    # attributed work to them.
    assert is_artist("Wu Zhang (1671-after 1741)")
    assert made_by("Wu Zhang (1671-after 1741)", ["Wu Zhang"])
    assert made_by("Attributed to Rembrandt van Rijn", ["Rembrandt van Rijn"])


def test_another_person_with_the_name_in_theirs_is_not_the_artist() -> None:
    """The next of the name, someone with it as a first name, a line that
    names nobody."""
    assert not made_by("Utagawa Hiroshige II (Shigenobu)", ["Utagawa Hiroshige"])
    assert not made_by("Robert Havell, Jr.", ["Robert Havell"])
    assert made_by("Utagawa Hiroshige II (Shigenobu)", ["Utagawa Hiroshige II"])
    assert made_by("Hiroshige I Utagawa", ["Utagawa Hiroshige"])
    assert made_by("Utagawa Kunisada I (Toyokuni III)", ["Utagawa Kunisada"])
    assert made_by("Hans Holbein the Younger", ["Hans Holbein"])  # mostly him
    # Two first names are no surname.
    assert not made_by("Anton Raphael Mengs", ["Raphael"])
    assert not made_by("Hans Simon Holtzbecker", ["John Simon"])
    assert made_by("Hubert Robert, French", ["Hubert Robert"])
    # What is asked for is somebody.
    assert not made_by("Albrecht Dürer", ["Dürer-School"])
    assert not made_by("unknown artist", ["Artist, style of: Giuseppe Arcimboldo"])
    assert not made_by("Joseph Anton Seethaler II, German", ["German"])
    assert not made_by("Master of 1518", ["Master of 1540"])
    assert not made_by("C.W. Eckersberg", ["W."])  # initials are nobody's name
    assert made_by("C.W. Eckersberg", ["Eckersberg"])
    assert made_by("Katsushika Hokusai", ["Katsushika Hokusai (1760-1849)"])


def test_two_works_are_by_one_hand_whichever_is_asked_first() -> None:
    """Until 1.145.31 the other works of an artist were those whose line
    had every word of this work's: "Hilaire Germain Edgar Degas" found no
    "Edgar Degas", and "Rembrandt" every follower of his."""
    for one, other in (
        ("Edgar Degas", "Hilaire Germain Edgar Degas"),
        ("Jan Piotr Norblin", "Jean Pierre Norblin de la Gourdaine"),
        ("Winslow Homer, American", "Winslow Homer"),
        ("Rembrandt van Rijn", "Attributed to Rembrandt van Rijn"),
        ("After Rembrandt", "After Rembrandt"),
        ("Currier & Ives", "Currier & Ives Lithography Company"),
    ):
        assert same_hand(one, other) and same_hand(other, one), (one, other)
    for one, other in (
        ("Rembrandt van Rijn", "Follower of Rembrandt van Rijn"),
        ("Honoré Daumier", "Style of Honoré Victorin Daumier"),
        ("Albrecht Dürer", "Według Albrecht Dürer"),
        ("Utagawa Hiroshige", "Utagawa Hiroshige II"),
        ("Pierre Ranson, French", "French School"),
        ("Unknown artist", "Artist, style of: Abraham Genoels II"),
    ):
        assert not same_hand(one, other) and not same_hand(other, one), (one, other)
