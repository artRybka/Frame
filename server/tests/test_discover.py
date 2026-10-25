"""Discover: the vocabulary, manuscripts, themes and the shared search."""

from __future__ import annotations

from fastapi.testclient import TestClient
from test_pools import _wait, museums  # noqa: F401  (fixture)

from frame_server.library import Item, PlaylistRules
from frame_server.library.repo import matches
from frame_server.library.themes import GROUPS, THEMES, theme_of_the_day
from frame_server.library.vocabulary import (
    BY_KEY,
    artist_matches,
    is_manuscript,
    museum_queries,
    suggest,
    term,
)


def _work(n: int, **fields) -> Item:
    return Item(id=f"aic:{n}", source="aic", source_id=str(n), **fields)


def test_terms_match_works() -> None:
    sea = _work(
        1,
        title="The Beach at Sainte-Adresse",
        styles=["Impressionism"],
        subjects=["seascapes", "boats"],
        year=1867,
    )
    portrait = _work(2, title="Portrait of a Woman, seated", year=1650)
    rules = PlaylistRules(terms=["style:impressionism", "subject:sea"])
    assert matches(sea, rules) and not matches(portrait, rules)
    # Terms of one kind are alternatives; kinds must all fit.
    either = PlaylistRules(terms=["subject:sea", "subject:portrait"])
    assert matches(sea, either) and matches(portrait, either)
    assert matches(portrait, PlaylistRules(terms=["period:17c"]))
    assert not matches(sea, PlaylistRules(terms=["period:17c"]))
    assert matches(sea, PlaylistRules(terms=["years:1860-1870"]))
    # Whole words: "seated" is not the sea.
    assert not matches(portrait, PlaylistRules(terms=["subject:sea"]))


def test_terms_are_suggested_in_polish_and_english() -> None:
    assert [t.key for t in suggest("morz")] == ["subject:sea"]
    assert "subject:sea" in [t.key for t in suggest("seasc")]
    assert [t.key for t in suggest("gory")] == ["subject:mountains"]  # without the accent
    assert suggest("1885")[0].key == "years:1880-1889"
    assert term("years:1880-1914") is not None and term("years:x") is None
    assert museum_queries(["style:impressionism", "subject:sea", "period:17c"]) == [
        "impressionism sea"
    ]
    # Every theme's terms are known.
    assert all(t in BY_KEY for theme in THEMES for t in theme.terms)
    assert {theme.group for theme in THEMES} == set(GROUPS)
    assert theme_of_the_day.__name__  # importable


def test_artists_match_by_their_words() -> None:
    assert artist_matches("Katsushika Hokusai", ["Hokusai"])
    assert artist_matches("Théodore Géricault", ["Géricault"])
    assert artist_matches("Claude Monet", ["claude monet"])
    assert not artist_matches("Monet", ["Claude Monet"])
    assert not artist_matches("", ["Monet"])


def test_manuscripts_are_told_apart() -> None:
    assert is_manuscript(_work(1, title="Folio from a Shahnama", classification="Painting"))
    assert is_manuscript(_work(2, title="Leaf from a Book of Hours"))
    assert is_manuscript(_work(3, classification="Manuscripts and Illuminations"))
    assert not is_manuscript(_work(4, title="Water Lilies", classification="Painting"))


def test_catalogue_leaves_manuscripts_out(museums) -> None:  # noqa: F811
    service = museums
    library = service.library
    page = library.upsert(_work(1, title="Leaf from a Psalter", pooled=True))
    kept = library.upsert(_work(2, title="Leaf from a Psalter"))  # saved by the owner
    painting = library.upsert(_work(3, title="Haystacks", pooled=True))
    assert {i.id for i in library.query()[1]} == {kept.id, painting.id}
    asked = library.query(PlaylistRules(terms=["technique:manuscripts"]))[1]
    assert {i.id for i in asked} == {page.id, kept.id}

    assert service.player.drop_manuscripts() == 1
    assert library.get(page.id) is None and library.get(kept.id) is not None
    assert service.player.drop_manuscripts() == 0  # once


def test_theme_playlists_and_terms(museums) -> None:  # noqa: F811
    from frame_server.web import create_app, discover_api

    service = museums
    app = create_app(service.settings)
    app.state.service = service
    discover_api._theme_rows.clear()
    discover_api._cards = (0.0, {})
    with TestClient(app) as client:
        cards = client.get("/api/themes").json()
        assert len(cards) == len(THEMES)
        assert [c["group"] for c in cards] == sorted((c["group"] for c in cards), key=GROUPS.index)
        made = client.post("/api/themes/romanticism/playlist", json={}).json()
        assert made["playlist"]["theme"] == "romanticism" and made["job_id"]
        _wait(service.importer.jobs[made["job_id"]])
        playlist = service.library.playlist(made["playlist"]["id"])
        assert len(service.library.playlist_items(playlist)) > 0
        again = client.post("/api/themes/romanticism/playlist", json={"play": True}).json()
        assert again["playlist"]["id"] == playlist.id and again["job_id"] is None
        assert service.player.settings.playlist_id == playlist.id
        discover_api._cards = (0.0, {})
        card = next(c for c in client.get("/api/themes").json() if c["key"] == "romanticism")
        assert card["playlist_id"] == playlist.id and card["count"] > 0 and card["cover"]

        # A colour theme is browsed in the catalogue.
        assert client.get("/api/themes/blue", params={"page": 1}).status_code == 200

        terms = client.get("/api/terms", params={"q": "Turn"}).json()
        assert terms[0]["kind"] == "artist" and terms[0]["count"] > 0
        assert terms[-1] == {
            "kind": "word",
            "key": "Turn",
            "name": "Turn",
            "detail": "",
            "count": terms[-1]["count"],
        }
        hint = client.get("/api/terms/museums", params={"q": "Kandinsky"}).json()
        assert hint["total"] > 0 and hint["artists"][0]["name"] == "Kandinsky"

        found = client.get(
            "/api/discover/search", params={"artist": ["Kandinsky"], "term": ["style:fauvism"]}
        ).json()
        assert found["items"] and all("Kandinsky" in r["item"]["artist"] for r in found["items"])
        assert client.get("/api/discover/search").json()["total"] == 0
        catalogue = client.get(
            "/api/library/items", params={"term": ["subject:birds"], "kind": ["artwork"]}
        ).json()
        assert catalogue["total"] == 0
        assert len(client.get("/api/vocabulary").json()) == len(BY_KEY)
