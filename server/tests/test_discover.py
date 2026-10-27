"""Discover: the vocabulary, manuscripts, themes and the shared search."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_pools import _wait, museums  # noqa: F401  (fixture)

from frame_server.library import Item, ItemKind, PlaylistRules
from frame_server.library.lifespan import last_free_year
from frame_server.library.repo import matches
from frame_server.library.themes import GROUPS, THEMES, theme_of_the_day
from frame_server.library.vocabulary import (
    BY_KEY,
    artist_matches,
    is_copy,
    is_grey_painting,
    is_manuscript,
    is_photograph,
    is_reproduction,
    museum_queries,
    set_aside,
    suggest,
    term,
)
from frame_server.player import SET_ASIDE_KEY


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
        "impressionism sea",
        "impressionism",
        "sea",
    ]
    assert museum_queries(["subject:sea", "subject:flowers"]) == ["sea", "flower"]
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


def test_photographs_are_told_apart() -> None:
    assert is_photograph(_work(1, classification="Photographs", medium="Gelatin silver print"))
    assert is_photograph(_work(2, title="Venice", medium="Albumen print from glass negative"))
    assert not is_photograph(_work(3, classification="Print", medium="Photomechanical print"))
    assert not is_photograph(_work(4, classification="Poster", medium="Photolithograph"))
    own = Item(
        id="own:1", source="own", source_id="1", kind=ItemKind.PHOTO, classification="Photograph"
    )
    assert not is_photograph(own)  # the owner's photos are never set aside
    page = _work(5, title="Leaf from a Psalter")
    assert set_aside(page) and not set_aside(page, ["technique:manuscripts"])


def test_reproductions_are_told_apart() -> None:
    album = 'Album reprodukcji obrazów z wystawy "Sto lat malarstwa polskiego"'
    assert is_reproduction(_work(1, title=album, classification="Painting"))
    assert is_reproduction(_work(2, title="Józef Chełmoński. Wspomnienie (page 41 crop)"))
    assert is_reproduction(_work(3, title="Jozef Chelmonski. Aanval van wolven, GD017005"))
    assert is_reproduction(_work(4, title="Babie lato", classification="glass slide"))
    assert is_reproduction(_work(5, title="Jozef Chelmonski műveinek reprodukciója"))
    assert is_reproduction(_work(6, title="Babie lato", classification="Pocztówka"))
    assert not is_reproduction(_work(7, title="Babie lato", classification="Painting"))
    # Posters are "photomechanical reproductions"; artists' postcards are prints.
    assert not is_reproduction(_work(8, title="Job", medium="Photomechanical reproduction"))
    assert not is_reproduction(_work(9, title="Postcard for the Wiener Werkstätte"))
    assert not is_reproduction(_work(10, title="The Birds of America, Plate 26"))


def test_paintings_without_colour_are_copies() -> None:
    grey = _work(1, title="Babie lato", classification="Painting", tint_spread=0.002)
    assert is_grey_painting(grey) and is_copy(grey) and set_aside(grey)
    oil = _work(2, title="Babie lato", medium="Oil on canvas", tint_spread=0.002)
    assert is_grey_painting(oil)
    coloured = _work(3, title="Babie lato", classification="Painting", tint_spread=0.03)
    unknown = _work(4, title="Babie lato", classification="Painting")
    etching = _work(5, title="Melencolia I", classification="Print", tint_spread=0.0)
    assert not any(is_grey_painting(i) for i in (coloured, unknown, etching))


def test_catalogue_leaves_manuscripts_out(museums) -> None:  # noqa: F811
    service = museums
    library = service.library
    page = library.upsert(_work(1, title="Leaf from a Psalter", pooled=True))
    kept = library.upsert(_work(2, title="Leaf from a Psalter"))  # saved by the owner
    painting = library.upsert(_work(3, title="Haystacks", pooled=True))
    photo = library.upsert(_work(4, title="Rouen", medium="Salted paper print", pooled=True))
    plate = library.upsert(
        _work(5, title="Orka", classification="Painting", tint_spread=0.001, pooled=True)
    )
    assert {i.id for i in library.query()[1]} == {kept.id, painting.id}
    asked = library.query(PlaylistRules(terms=["technique:manuscripts"]))[1]
    assert {i.id for i in asked} == {page.id, kept.id}

    assert service.player.drop_set_aside() == 3
    assert library.get(page.id) is None and library.get(photo.id) is None
    assert library.get(plate.id) is None
    assert library.get(kept.id) is not None
    assert service.player.drop_set_aside() == 0  # once

    # Libraries cleaned by the first version are cleaned again.
    library.set_state(SET_ASIDE_KEY, True)
    library.upsert(plate)
    assert service.player.drop_set_aside() == 1


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


def test_discover_does_not_wait_for_slow_work(museums, monkeypatch) -> None:  # noqa: F811
    import threading
    import time
    from datetime import date

    from frame_server.library.themes import Theme
    from frame_server.web import discover_api

    service = museums
    library = service.library
    day = date(2026, 10, 26)

    # Theme cards: the old ones at once, new ones worked out behind.
    old: dict[str, tuple[int, list[Item]]] = {"old": (1, [])}
    discover_api._cards = (time.monotonic() - 2 * discover_api.CARDS_TTL, old)
    assert discover_api._theme_cards(service) is old
    for _ in range(100):
        if discover_api._cards[1] is not old:
            break
        time.sleep(0.05)
    assert set(discover_api._cards[1]) == {t.key for t in THEMES}

    # The theme of the day from the catalogue when it has enough works.
    blue = Theme("blue-test", "Błękity", "", GROUPS[0], colors=("blue",))
    with library.batch():
        for n in range(discover_api.DAY_ROW_MIN):
            library.upsert(_work(100 + n, title=f"Blue {n}", color_tags=["blue"], pooled=True))
    asked: list[str] = []
    monkeypatch.setattr(discover_api, "browse_theme", lambda *a: asked.append("museum"))
    discover_api._theme_rows.clear()
    assert len(discover_api._day_row(service, blue, day)) == discover_api.DAY_ROW_MIN
    assert not asked

    # Else the museums, waited for only a moment; a slow answer is kept.
    sea = Theme("sea-test", "Morze", "", GROUPS[0], artists=("Nobody",))
    answered = threading.Event()

    def slow(*args) -> tuple[list[Item], bool]:
        answered.wait(5)
        return [_work(1, title="Wave")], False

    monkeypatch.setattr(discover_api, "browse_theme", slow)
    monkeypatch.setattr(discover_api, "DAY_ROW_WAIT", 0.05)
    discover_api._theme_rows.clear()
    discover_api._day_fetch = (0.0, None)
    assert discover_api._day_row(service, sea, day) == []
    answered.set()
    discover_api._day_fetch[1].join(5)
    assert [i.title for i in discover_api._day_row(service, sea, day)] == ["Wave"]
    discover_api._theme_rows.clear()


def test_theme_pages_pass_over_searches_that_find_nothing() -> None:
    import httpx

    from frame_server.library.themes import Theme, browse_theme, theme

    class Museums:
        """Nothing for the first two searches, one failing, works after."""

        def __init__(self, found: dict[str, int], failing: set[str] = frozenset()) -> None:
            self.found = found
            self.failing = failing
            self.asked: list[str] = []

        def search(self, source: str, query: str, limit: int, page: int) -> tuple[int, list[Item]]:
            self.asked.append(query)
            if query in self.failing:
                raise httpx.ConnectError("down")
            total = self.found.get(query, 0)
            start = (page - 1) * limit
            return total, [
                _work(n, title=f"{query} {n}", artist=query)
                for n in range(start, min(total, start + limit))
            ]

    found = Theme("t", "T", "", GROUPS[0], queries=(("aic", "A"), ("aic", "B"), ("aic", "C")))
    fake = Museums({"C": 30}, failing={"B"})
    items, following = browse_theme(fake, found, 1, 24)  # type: ignore[arg-type]
    assert fake.asked == ["A", "B", "C"] and len(items) == 24 and following == 4
    # Page 4 is C's second round... after A's and B's, which have none.
    fake.asked.clear()
    items, following = browse_theme(fake, found, 4, 24)  # type: ignore[arg-type]
    assert fake.asked == ["A", "B", "C"] and len(items) == 6 and following is None

    # Out of time: an empty page that says where to go on.
    items, following = browse_theme(Museums({}), found, 1, 24, wait=0)  # type: ignore[arg-type]
    assert items == [] and following == 2
    # Nothing anywhere: the last page.
    assert browse_theme(Museums({}), found, 1, 24) == ([], None)  # type: ignore[arg-type]
    # Every museum down: an error, not an empty theme.
    with pytest.raises(httpx.HTTPError):
        browse_theme(Museums({}, failing={"A", "B", "C"}), found, 1, 24)  # type: ignore[arg-type]

    # Polish painters are looked for on Commons, where they are.
    assert all(source == "wmc" for source, _ in theme("young-poland").searches())
    assert all(source == "wmc" for source, _ in theme("polish-landscape").searches())


def test_periods_reach_the_last_year_free_in_the_eu() -> None:
    late = term("period:post-1945")
    assert late is not None and late.year_to == last_free_year()
    assert late.name == f"1945–{last_free_year()}"
    composition = _work(1, title="Composition", year=1950)
    assert matches(composition, PlaylistRules(terms=["period:post-1945"]))
    assert matches(_work(2, title="Unism", year=1934), PlaylistRules(terms=["period:interwar"]))
    assert not matches(composition, PlaylistRules(terms=["period:1930-1945"]))
    # Later styles, and their museum words.
    assert matches(
        _work(3, title="Suprematist composition", year=1916),
        PlaylistRules(terms=["style:constructivism"]),
    )
    assert "style:abstraction" in [t.key for t in suggest("abstrak")]
