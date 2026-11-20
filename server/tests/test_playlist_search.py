"""Searching inside one playlist: the magnifier beside "…" on its page
(Mateusz 2026-11-19: "Wyszukiwanie wewnątrz playlist", "Zdecydowanie lupa
obok"). The works found are the playlist's, all of them, in its order; the
suggestions are counted in it."""

from __future__ import annotations

from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.library import ItemKind


def _add(svc, n: int, title: str, artist: str, year: int) -> str:
    added = svc.importer.add_upload(
        jpeg_bytes((30 * n, 60, 200 - 20 * n)), kind=ItemKind.OWN, title=title, artist=artist
    )
    svc.library.update(added.id, year=year)
    return added.id


def test_the_playlists_works_found_in_its_order(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    sea = _add(svc, 1, "Morze o świcie", "Ivan Aivazovsky", 1850)
    storm = _add(svc, 2, "Burza na morzu", "Ivan Aivazovsky", 1870)
    pond = _add(svc, 3, "Staw z liliami", "Claude Monet", 1899)
    other = _add(svc, 4, "Morze nocą", "Claude Monet", 1880)  # not on the playlist

    with TestClient(app) as client:
        made = client.post(
            "/api/playlists",
            json={"name": "Wybrane", "kind": "manual", "item_ids": [sea, storm, pond]},
        ).json()
        pid = made["playlist"]["id"]
        client.put(f"/api/playlists/{pid}/sort", json={"key": "year", "reverse": True})

        found = client.get("/api/library/items", params={"q": "morze", "playlist": pid}).json()
        # The work off the playlist with the same word is not there.
        assert [i["id"] for i in found["items"]] == [sea] and found["total"] == 1
        his = client.get(
            "/api/library/items", params={"artist": "Ivan Aivazovsky", "playlist": pid}
        ).json()
        assert [i["id"] for i in his["items"]] == [storm, sea]  # its order: the newest first

        monet = client.get(
            "/api/library/items", params={"artist": "Claude Monet", "playlist": pid}
        ).json()
        assert [i["id"] for i in monet["items"]] == [pond]
        everywhere = client.get("/api/library/items", params={"artist": "Claude Monet"}).json()
        assert {i["id"] for i in everywhere["items"]} == {pond, other}

        # The suggestions counted in the playlist; the typed words always last.
        hits = client.get("/api/terms", params={"q": "Monet", "playlist": pid}).json()
        artist = next(h for h in hits if h["kind"] == "artist")
        assert artist["key"] == "Claude Monet" and artist["count"] == 1
        assert hits[-1]["kind"] == "word" and hits[-1]["key"] == "Monet"
        # An artist with no work on it is no suggestion there.
        none = client.get("/api/terms", params={"q": "Aivazovsky", "playlist": pid}).json()
        assert any(h["kind"] == "artist" for h in none)
        lonely = client.post(
            "/api/playlists", json={"name": "Staw", "kind": "manual", "item_ids": [pond]}
        ).json()["playlist"]["id"]
        hits = client.get("/api/terms", params={"q": "Aivazovsky", "playlist": lonely}).json()
        assert [h["kind"] for h in hits] == ["word"]

        assert client.get("/api/library/items", params={"playlist": 9999}).status_code == 404
        assert client.get("/api/terms", params={"q": "x", "playlist": 9999}).status_code == 404


def test_while_typing_the_grid_shows_what_the_suggestions_count(service) -> None:
    """Mateusz's first look (2026-11-19): "morze" found none of the playlist
    while "Morze · Temat" under the field counted 3. Typed words find what
    any of their suggestions finds; picked, only that."""
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    wave = _add(svc, 1, "The Great Wave", "Hokusai", 1831)
    svc.library.update(wave, subjects=["sea", "waves"])
    named = _add(svc, 2, "Morze o świcie", "Ivan Aivazovsky", 1850)
    pond = _add(svc, 3, "Staw z liliami", "Claude Monet", 1899)

    with TestClient(app) as client:
        pid = client.post(
            "/api/playlists",
            json={"name": "Woda", "kind": "manual", "item_ids": [wave, named, pond]},
        ).json()["playlist"]["id"]
        sea = next(
            h
            for h in client.get("/api/terms", params={"q": "morze", "playlist": pid}).json()
            if h["key"] == "subject:sea"
        )
        assert sea["count"] == 1

        typed = client.get("/api/library/items", params={"typed": "morze", "playlist": pid}).json()
        assert {i["id"] for i in typed["items"]} == {wave, named} and typed["total"] == 2
        # Half a word is no word yet, but it is the subject's beginning.
        half = client.get("/api/library/items", params={"typed": "mor", "playlist": pid}).json()
        assert wave in {i["id"] for i in half["items"]}
        assert pond not in {i["id"] for i in half["items"]}
        # A suggestion picked: only what it finds.
        picked = client.get(
            "/api/library/items", params={"term": "subject:sea", "playlist": pid}
        ).json()
        assert [i["id"] for i in picked["items"]] == [wave]
        # Typing on after a chip: within the chip's works.
        both = client.get(
            "/api/library/items",
            params={"artist": "Hokusai", "typed": "morze", "playlist": pid},
        ).json()
        assert [i["id"] for i in both["items"]] == [wave]


def test_only_the_playlists_works_and_the_letter_before_is_let_go(service) -> None:
    """On the NAS (2026-11-20) "Słowa" in a two-work playlist answered ten
    works, nine of them not on it; and every letter's search went on to its
    end beside the next one's."""
    from frame_server.web import create_app, library_api

    app = create_app(service.settings)
    svc = app.state.service
    sea = _add(svc, 1, "Morze o świcie", "Ivan Aivazovsky", 1850)
    for n in range(2, 6):
        _add(svc, n, f"Morze {n}", "Ivan Aivazovsky", 1850 + n)

    with TestClient(app) as client:
        pid = client.post(
            "/api/playlists", json={"name": "Jedno", "kind": "manual", "item_ids": [sea]}
        ).json()["playlist"]["id"]
        for params in ({"q": "morze", "seen": "true"}, {"q": "morze"}, {"typed": "morze"}):
            found = client.get("/api/library/items", params={**params, "playlist": pid}).json()
            assert [i["id"] for i in found["items"]] == [sea] and found["total"] == 1

        # A search whose asker has asked again meanwhile: no answer.
        real = svc.library.query

        def next_letter_comes(*args, **kwargs):
            for key in library_api._PLAYLIST_ASKED:
                library_api._PLAYLIST_ASKED[key] += 1
            return real(*args, **kwargs)

        svc.library.query = next_letter_comes
        try:
            left = client.get("/api/library/items", params={"typed": "morze", "playlist": pid})
        finally:
            svc.library.query = real
        assert left.json() == {"total": 0, "items": [], "later": False}
