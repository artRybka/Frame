"""Discover: the vocabulary, manuscripts, themes and the shared search."""

from __future__ import annotations

import itertools
from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_pools import _wait, museums  # noqa: F401  (fixture)

from frame_server.library import Item, ItemKind, PlaylistRules
from frame_server.library.importer import span
from frame_server.library.repo import matches
from frame_server.library.themes import (
    ARTIST_SPREAD,
    COLOUR,
    COLOUR_POOL,
    GROUPS,
    OTHER_ART_THEMES,
    OTHER_ARTS,
    THEMES,
    WEEKLY,
    theme_of_the_day,
)
from frame_server.library.vocabulary import (
    BY_KEY,
    EARLY_COLOUR,
    STYLE_YEARS,
    TERMS,
    artist_matches,
    category_fits,
    is_copy,
    is_grey_copy,
    is_grey_painting,
    is_manuscript,
    is_photograph,
    is_postal,
    is_reproduction,
    museum_queries,
    object_category,
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


def test_schools_split_off_their_bigger_styles() -> None:
    """Barbizon and pointillism are styles of their own (Mateusz 2026-11-08),
    no longer caught by realism and post-impressionism."""
    corot = _work(3, title="Landscape", styles=["Barbizon School"], year=1860)
    seurat = _work(4, title="Study", styles=["Neo-Impressionism"], year=1886)
    assert matches(corot, PlaylistRules(terms=["style:barbizon"]))
    assert not matches(corot, PlaylistRules(terms=["style:realism"]))
    assert matches(seurat, PlaylistRules(terms=["style:pointillism"]))
    assert not matches(seurat, PlaylistRules(terms=["style:post-impressionism"]))
    dada = _work(5, title="Merz picture", styles=["Dada"], year=1920)
    assert matches(dada, PlaylistRules(terms=["style:dada"]))
    hive = _work(6, title="Dadant hive", year=1900)
    assert not matches(hive, PlaylistRules(terms=["style:dada"]))
    assert len([t for t in TERMS if t.kind == "style"]) == 39


def test_a_style_keeps_to_its_years() -> None:
    """A museum's search for "art deco" also finds Rubens and Mucha
    (Mateusz 2026-11-09): what it found must have been made when the style
    was, give or take; an undated work stays."""
    deco = PlaylistRules(terms=["style:art-deco"])
    key = deco.search_key()
    rubens = _work(7, title="The Calydonian Boar Hunt", year=1611, found_for=[key])
    mucha = _work(8, title="Sarah Bernhardt in the role of La Tosca", year=1899, found_for=[key])
    lamp = _work(9, title="Art deco lamp", year=1928, found_for=[key])
    undated = _work(10, title="Metal mesh purse", found_for=[key])
    assert not matches(rubens, deco)
    assert not matches(mucha, deco)
    assert matches(lamp, deco)
    assert matches(undated, deco)
    # Either of two styles will do; the slack keeps early and late works.
    both = PlaylistRules(terms=["style:art-deco", "style:art-nouveau"])
    assert matches(mucha.model_copy(update={"found_for": [both.search_key()]}), both)
    scream = _work(11, title="The Scream", styles=["Expressionism"], year=1893)
    assert matches(scream, PlaylistRules(terms=["style:expressionism"]))
    lilies = _work(12, title="Water Lilies", styles=["Impressionism"], year=1916)
    assert matches(lilies, PlaylistRules(terms=["style:impressionism"]))
    assert {t.key for t in TERMS if t.kind == "style"} == set(STYLE_YEARS)


def test_techniques_follow_what_the_object_is() -> None:
    painting = PlaylistRules(terms=["technique:painting"])
    drawing = PlaylistRules(terms=["technique:drawing"])
    oil = _work(1, classification="Painting", medium="Oil on canvas")
    # Art Institute drawings by Monet: the museum's text talks of his
    # paintings, the model's keywords of a framed picture in it.
    boy = _work(
        2,
        title="Boy in the Country",
        classification="Drawing and Watercolor",
        medium="Graphite on ivory wove paper",
        description="Before turning to painting, Monet drew caricatures.",
    )
    caricature = _work(
        3,
        title="Caricature of Léon Manchon",
        classification="Drawing and Watercolor",
        medium="Black and white chalks on blue laid paper",
        keywords=["obraz w ramie", "plakat", "szyld"],
    )
    assert matches(oil, painting) and not matches(oil, drawing)
    for work in (boy, caricature):
        assert matches(work, drawing) and not matches(work, painting)
    assert not matches(caricature, PlaylistRules(terms=["technique:poster"]))
    # Without a technique in the type or material, the title and the
    # museum's tags; a print's title can still make it a poster.
    tagged = _work(4, classification="digitized_artwork", subjects=["painting", "river"])
    assert matches(tagged, painting)
    poster = _work(5, title="Affiche pour Job", classification="Print", medium="Lithograph")
    assert matches(poster, PlaylistRules(terms=["technique:poster"]))
    study = _work(6, title="Study for the painting", classification="Drawing", medium="Pen")
    assert not matches(study, painting)


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
    # Made, not fixed: the week's themes ("Ponieważ lubisz" too) and the
    # week's colours.
    assert {theme.group for theme in THEMES} == set(GROUPS) - {WEEKLY, COLOUR, OTHER_ARTS}
    # Mateusz's order of the groups (2026-11-07).
    assert GROUPS == (
        "Dziś dla Ciebie",
        "Kierunki i style",
        "Sztuka polska",
        "Kolor i nastrój",
        "Epoki",
        "Tematy",
        "Grafika i plakat",
        "Sztuki inne",
    )
    prints = [t.key for t in THEMES if t.group == "Grafika i plakat"]
    assert prints == ["posters", "ukiyo-e", "nature", "kacho-e", "black-white"]
    assert [t.key for t in OTHER_ART_THEMES[:4]] == [
        "other-manuscripts",
        "other-sculpture",
        "other-photography",
        "other-decorative",
    ]
    assert {theme.group for theme in OTHER_ART_THEMES} == {OTHER_ARTS}
    assert {theme.group for theme in COLOUR_POOL} == {COLOUR}
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


def test_sculpture_photographs_and_crafts_only_when_asked_for() -> None:
    bust = _work(1, title="Claude Monet", classification="Sculpture", medium="bronze")
    vase = _work(2, title="Vase", classification="Ceramics", medium="Hard-paste porcelain")
    photo = _work(3, title="Venice", classification="Photograph", medium="Gelatin silver print")
    lilies = _work(4, title="Water Lilies", classification="Painting", medium="Oil on canvas")
    # A portrait miniature is watercolour on ivory: a picture.
    miniature = _work(5, classification="Portrait Miniature", medium="watercolor on ivory")
    assert [object_category(w) for w in (bust, vase, photo, lilies, miniature)] == [
        "technique:sculpture",
        "technique:decorative",
        "technique:photography",
        None,
        None,
    ]
    for work in (bust, vase, photo):
        assert set_aside(work) and not set_aside(work, [object_category(work) or ""])
    monet = PlaylistRules(artists=["Claude Monet"], query="")
    for work in (bust, vase, photo, lilies):
        work.artist = "Claude Monet"
    assert [matches(w, monet) for w in (bust, vase, photo, lilies)] == [False] * 3 + [True]
    # The library as a whole and the favourites keep what the owner kept.
    bust.favorite = True
    assert matches(bust, PlaylistRules()) and matches(bust, PlaylistRules(favorites_only=True))
    sculpture = PlaylistRules(artists=["Claude Monet"], terms=["technique:sculpture"])
    assert matches(bust, sculpture) and not matches(lilies, sculpture)
    either = ["technique:sculpture", "technique:painting"]
    assert matches(bust, PlaylistRules(terms=either)) and matches(
        lilies, PlaylistRules(terms=either)
    )
    # Museums' answers: a category alone brings no paintings.
    assert category_fits(bust, ["technique:sculpture"])
    assert not category_fits(lilies, ["technique:sculpture"])
    assert category_fits(lilies, either) and not category_fits(vase, either)
    assert category_fits(lilies, []) and not category_fits(bust, [])
    # Openverse's photographs are Flickr's: never.
    flickr = Item(id="openverse:1", source="openverse", source_id="1", classification="photograph")
    assert set_aside(flickr, ["technique:photography"])


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


def test_black_and_white_photos_of_art_archives_are_copies() -> None:
    """Foto Marburg's old prints on a catalogue card ("La Berceuse, Bildnis
    der Madame Roulin", Neg.-Nr. typed below) are copies whatever the work;
    its colour photographs, and museums' own grey prints, stay."""
    marburg = "German Documentation Center for Art History - Marburg Picture Index"

    def archive(n: int, **fields) -> Item:
        return Item(
            id=f"europeana:199~{n}",
            source="europeana",
            source_id=f"199~{n}",
            credit=marburg,
            **fields,
        )

    berceuse = archive(1, title="La Berceuse, Bildnis der Madame Roulin", tint_spread=0.0)
    drawing = archive(
        2, title="Kartoffelfeld in den Dünen", classification="Drawing", tint_spread=0.0
    )
    assert all(is_grey_copy(i) and is_copy(i) and set_aside(i) for i in (berceuse, drawing))
    colour = archive(3, title="La Berceuse / Madame Roulin", tint_spread=0.027)
    unknown = archive(4, title="La Berceuse / Madame Roulin")
    assert not is_copy(colour) and not is_copy(unknown)
    etching = _work(5, title="Melencolia I", classification="Print", tint_spread=0.0)
    assert not is_grey_copy(etching) and not is_copy(etching)
    grey_oil = _work(6, title="Babie lato", classification="Painting", tint_spread=0.002)
    assert is_grey_copy(grey_oil)
    # Kept, it stays in the library and the favourites, but no search finds it.
    berceuse.favorite = True
    berceuse.artist = "Vincent van Gogh"
    assert matches(berceuse, PlaylistRules(favorites_only=True))
    assert not matches(berceuse, PlaylistRules(artists=["Vincent van Gogh"]))
    assert matches(
        colour.model_copy(update={"artist": "Vincent van Gogh"}),
        PlaylistRules(artists=["Vincent van Gogh"]),
    )


def test_stamps_are_never_pictures() -> None:
    athens = Item(
        id="europeana:1592~76122",
        source="europeana",
        source_id="1592~76122",
        title="Igrzyska Olimpijskie Ateny 2004: starożytne monety olimpijskie",
        credit="Philatelic Postal Museum",
    )
    assert is_postal(athens) and is_copy(athens) and set_aside(athens)
    assert set_aside(athens, ["technique:decorative"])
    assert is_postal(_work(1, title="Wilhelmina", classification="Postage stamp"))
    assert is_postal(_work(2, title="Chopin", classification="Znaczek pocztowy"))
    # Posters for the post and artists' postcards are pictures.
    poster = _work(3, title="Poste aérienne", classification="Poster", credit="Postal Museum")
    card = _work(4, title="Postcard for the Wiener Werkstätte", classification="Print")
    assert not is_postal(poster) and not is_postal(card)
    # Kept, it stays in the library and the favourites, but no search finds it.
    athens.favorite = True
    athens.terms = ["subject:still-life"]
    assert matches(athens, PlaylistRules()) and matches(athens, PlaylistRules(favorites_only=True))
    assert not matches(athens, PlaylistRules(terms=["subject:still-life"]))
    # Of another provider of Greek works, the same title is no stamp.
    other = athens.model_copy(update={"credit": "Numismatic Museum of Athens"})
    assert not is_postal(other)


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
    stamps = library.upsert(
        _work(6, title="Ateny 2004", credit="Philatelic Postal Museum", pooled=True).model_copy(
            update={"id": "europeana:1592~6", "source": "europeana", "source_id": "1592~6"}
        )
    )
    marburg = library.upsert(
        _work(
            7,
            title="La Berceuse",
            credit="German Documentation Center for Art History - Marburg Picture Index",
            tint_spread=0.0,
            pooled=True,
        ).model_copy(update={"id": "europeana:199~7", "source": "europeana", "source_id": "199~7"})
    )
    assert {i.id for i in library.query()[1]} == {kept.id, painting.id}
    asked = library.query(PlaylistRules(terms=["technique:manuscripts"]))[1]
    assert {i.id for i in asked} == {page.id, kept.id}

    assert service.player.drop_set_aside() == 3
    # Pages of manuscripts and photographs belong to "Sztuki inne" now.
    assert library.get(page.id) is not None and library.get(photo.id) is not None
    assert library.get(plate.id) is None and library.get(stamps.id) is None
    assert library.get(marburg.id) is None
    assert library.get(kept.id) is not None
    assert service.player.drop_set_aside() == 0  # once

    # Libraries cleaned by the first version are cleaned again.
    library.set_state(SET_ASIDE_KEY, True)
    library.upsert(plate)
    assert service.player.drop_set_aside() == 1


def test_theme_playlists_and_terms(museums, monkeypatch) -> None:  # noqa: F811
    from frame_server.web import create_app, discover_api

    service = museums
    monkeypatch.setattr(discover_api, "CARD_MIN", 0)  # every card, however empty
    app = create_app(service.settings)
    app.state.service = service
    discover_api._theme_rows.clear()
    discover_api._cards = (0.0, {})
    with TestClient(app) as client:
        cards = client.get("/api/themes").json()
        # Without "Użytek prywatny", none of the themes of works in copyright.
        private = [t.key for t in THEMES if t.private]
        assert private == ["contemporary", "polish-postwar"]
        assert len(cards) == len(THEMES) - len(private) + len(OTHER_ART_THEMES)
        assert [c["group"] for c in cards] == sorted((c["group"] for c in cards), key=GROUPS.index)
        assert client.get("/api/themes/contemporary").status_code == 404
        settings = client.get("/api/settings").json()
        client.put("/api/settings", json={**settings, "private_use": True})
        keys = [c["key"] for c in client.get("/api/themes").json()]
        assert "contemporary" in keys and "polish-postwar" in keys
        client.put("/api/settings", json=settings)
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
        keys = {t["key"] for t in client.get("/api/vocabulary").json()}
        assert keys == set(BY_KEY) - {EARLY_COLOUR}  # a card's mark, no suggestion


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
    assert set(discover_api._cards[1]) == {t.key for t in [*THEMES, *OTHER_ART_THEMES]}

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

    from frame_server.library.themes import (
        Theme,
        batch_of,
        browse_theme,
        page_after,
        search_page,
        theme,
    )

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

    # The stream asks a few pages at once, within a round of searches.
    assert batch_of(found, 1, 4) == [1, 2, 3]
    assert batch_of(found, 2, 1) == [2]
    assert batch_of(found, 5, 4) == [5, 6]
    fake = Museums({"C": 30})
    assert search_page(fake, found, 6, 24)[1] == 30  # type: ignore[arg-type]
    assert [len(search_page(fake, found, p, 24)[0]) for p in (3, 6)] == [24, 6]  # type: ignore[arg-type]
    assert page_after(found, 2, 0, 24) == 3
    assert page_after(found, 3, 30, 24) == 4
    assert page_after(found, 6, 30, 24) is None

    # Polish painters are looked for in the national museums in Warsaw and
    # Kraków first, then on Commons.
    for key in ("young-poland", "polish-landscape"):
        sources = [source for source, _ in theme(key).searches()]
        assert set(sources) == {"mnw", "mnk", "wmc"}
        assert sources[:2] == ["mnw", "mnk"]


def test_a_sets_searches_asked_together_are_for_different_painters() -> None:
    # The museums answer one painter at a time; a round asks four searches
    # at once, so four painters come in the first round, not two museums'
    # worth of one (Strzemiński in Warsaw, then Strzemiński in Kraków).
    found = next(t for t in THEMES if t.key == "polish-interwar")
    searches = found.searches()
    assert sorted(searches) == sorted(found.queries)  # only the order differs
    painters = [next(a for a in found.artists if a.split()[-1] in query) for _, query in searches]
    assert len(set(painters[:7])) == 7  # every painter before anyone twice
    for start in range(len(painters) - ARTIST_SPREAD):
        assert len(set(painters[start : start + ARTIST_SPREAD + 1])) == ARTIST_SPREAD + 1
    sources = [source for source, _ in searches]
    assert all(a != b for a, b in itertools.pairwise(sources))

    # Themes of painters without set searches: each painter's museums in
    # turn, a new painter in each.
    plain = next(t for t in THEMES if t.artists and not t.queries)
    first = plain.searches()[: len(plain.artists)]
    assert len({query for _, query in first}) == len(plain.artists)


def test_the_last_period_reaches_this_year() -> None:
    """With "Użytek prywatny" sources give works still in copyright, so
    the period after 1945 no longer stops at the last free death year."""
    late = term("period:post-1945")
    assert late is not None and late.year_to == date.today().year
    assert late.name == "Po 1945"
    composition = _work(1, title="Composition", year=1950)
    assert matches(composition, PlaylistRules(terms=["period:post-1945"]))
    assert matches(_work(3, title="Untitled", year=1987), PlaylistRules(terms=["period:post-1945"]))
    assert matches(_work(2, title="Unism", year=1934), PlaylistRules(terms=["period:interwar"]))
    assert not matches(composition, PlaylistRules(terms=["period:1930-1945"]))
    # Later styles, and their museum words.
    assert matches(
        _work(3, title="Suprematist composition", year=1916),
        PlaylistRules(terms=["style:constructivism"]),
    )
    assert "style:abstraction" in [t.key for t in suggest("abstrak")]


def test_named_periods_of_one_country_need_the_place_too() -> None:
    hokusai = _work(1, title="The Great Wave", year=1831, artist_bio="Japanese, 1760-1849")
    rembrandt = _work(2, title="The Night Watch", year=1642, artist_bio="Dutch, 1606-1669")
    polish_rider = _work(3, title="The Polish Rider", year=1655, artist_bio="Dutch, 1606-1669")
    hiroshige = _work(4, title="Kambara", year=1833, terms=["style:ukiyo-e"])
    vase = _work(5, title="Vase", year=1700, culture="China")
    canaletto = _work(6, title="Warsaw", year=1775, museum="Muzeum Narodowe w Warszawie")
    edo = PlaylistRules(terms=["period:edo"])
    assert matches(hokusai, edo) and matches(hiroshige, edo)
    assert not matches(rembrandt, edo)
    assert matches(vase, PlaylistRules(terms=["period:qing"]))
    assert not matches(vase, PlaylistRules(terms=["period:edo"]))
    stanislaus = PlaylistRules(terms=["period:pl-stanislaus"])
    assert matches(canaletto, stanislaus)
    # The title says nothing of where a work comes from.
    assert not matches(polish_rider, PlaylistRules(terms=["period:pl-saxon"]))
    # Europe's are years only.
    assert matches(rembrandt, PlaylistRules(terms=["period:thirty-years-war"]))
    # Museums are asked with the country's word.
    assert museum_queries(["period:edo", "period:meiji"]) == ["japanese"]
    assert museum_queries(["period:edo", "period:17c"]) == []
    # The app's Epoka sheet: twenty-four named periods in four groups.
    named = [t for t in TERMS if t.kind == "period" and t.region]
    assert len(named) == 24
    assert {t.region for t in named} == {"antiquity", "europe", "poland", "east-asia"}
    assert all(t.region is None for t in TERMS if t.kind == "period" and t not in named)


def test_antiquity_comes_before_the_middle_ages() -> None:
    fayum = _work(1, title="Portrait of a Woman", year=150, culture="Roman, Egypt")
    krater = _work(2, title="Krater", year=-440, culture="Greek, Attic")
    papyrus = _work(3, title="Book of the Dead", year=-1250, culture="Egyptian")
    icon = _work(4, title="Virgin Hodegetria", year=1350, culture="Byzantine")
    madonna = _work(5, title="Madonna", year=1350, artist_bio="Italian, Siena")
    ancient = PlaylistRules(terms=["period:ancient"])
    assert all(matches(w, ancient) for w in (fayum, krater, papyrus))
    assert not matches(icon, ancient)
    medieval = PlaylistRules(terms=["period:medieval"])
    assert matches(icon, medieval) and matches(madonna, medieval)
    assert not matches(fayum, medieval)
    # Named periods of antiquity need the culture too.
    assert matches(krater, PlaylistRules(terms=["period:greece"]))
    assert not matches(papyrus, PlaylistRules(terms=["period:greece"]))
    assert matches(papyrus, PlaylistRules(terms=["period:egypt"]))
    assert matches(fayum, PlaylistRules(terms=["period:rome"]))
    assert matches(icon, PlaylistRules(terms=["period:byzantium"]))
    assert not matches(madonna, PlaylistRules(terms=["period:byzantium"]))
    assert museum_queries(["period:egypt", "period:greece"]) == ["egyptian", "greek"]
    # Museums' date filters know no years before Christ: the start is left
    # open and the end is year 1.
    assert span(PlaylistRules(terms=["period:egypt"])) == (None, 1)
    assert span(PlaylistRules(terms=["period:rome"])) == (None, 476)
    assert span(PlaylistRules(terms=["period:ancient"])) == (None, 499)
