"""Keeping Discover fresh: the theme of the day by the calendar, themes of
the week from the catalogue, new and returning works, museums' highlights
and the Statens Museum for Kunst."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
from test_pools import _wait, museums  # noqa: F401  (fixture)

from frame_server.library import Item, ItemKind, PlaylistRules
from frame_server.library.museums import (
    ClevelandMuseum,
    Discovery,
    Europeana,
    MetropolitanMuseum,
    StatensMuseum,
)
from frame_server.library.repo import matches
from frame_server.library.themes import (
    BY_KEY,
    DAY_REPEAT,
    DAYS_KEY,
    SEASON_THEMES,
    WEEKLY,
    easter,
    occasion,
    season,
    theme,
    theme_of_the_day,
    weekly_themes,
)
from frame_server.library.vocabulary import HIGHLIGHT


def _work(n: int, **fields) -> Item:
    fields.setdefault("kind", ItemKind.ARTWORK)
    return Item(id=f"cma:{n}", source="cma", source_id=str(n), **fields)


def test_calendar() -> None:
    assert easter(2026) == date(2026, 4, 5) and easter(2027) == date(2027, 3, 28)
    assert occasion(date(2027, 3, 29)).name == "Wielkanoc"  # Easter Monday
    assert occasion(date(2026, 11, 11)).theme == "polish"
    assert occasion(date(2026, 12, 25)).theme == "winter"
    assert occasion(date(2026, 10, 30)) is None
    assert [season(date(2026, m, 1)) for m in (1, 4, 7, 10, 12)] == [
        "winter",
        "spring",
        "summer",
        "autumn",
        "winter",
    ]


def test_theme_of_the_day_follows_the_calendar_and_does_not_repeat(service) -> None:
    library = service.library
    assert theme_of_the_day(date(2026, 11, 11)).key == "polish"
    start = date(2026, 1, 3)
    picked = [theme_of_the_day(start + timedelta(days=n), library).key for n in range(DAY_REPEAT)]
    assert len(set(picked)) == len(picked)  # none twice within DAY_REPEAT days
    assert not set(picked) & set(SEASON_THEMES["summer"])  # no beach in January
    # A day keeps its theme, also after a restart (it is remembered).
    assert theme_of_the_day(start, library).key == picked[0]
    assert library.get_state(DAYS_KEY, {})[start.isoformat()] == picked[0]


def test_themes_of_the_week_come_from_the_catalogue(service) -> None:
    library = service.library
    with library.batch():
        for n in range(14):
            library.upsert(
                _work(
                    n,
                    title=f"River at dawn {n}",
                    artist="Theodore Robinson",
                    artist_bio="American, 1852-1896",
                    styles=["Impressionism"],
                    suitability=0.6,
                    pooled=True,
                )
            )
        library.upsert(_work(99, title="River", artist="Weak", suitability=0.1, pooled=True))
    day = date(2026, 11, 2)
    themes = weekly_themes(library, day)
    keys = [t.key for t in themes]
    assert keys[0] == "week-artist-theodore-robinson"
    artist = themes[0]
    assert artist.group == WEEKLY and "Amerykanin" in artist.description
    assert "14 dzieł" in artist.description
    mix = theme("week-mix-style-impressionism-subject-rivers")
    assert mix.name == "Impresjonizm: rzeki i jeziora" and mix.searches() == []
    assert library.query(mix.rules())[0] == 14
    # The same all week; another week makes others.
    assert [t.key for t in weekly_themes(library, day + timedelta(days=4))] == keys
    assert not set(keys) & {t.key for t in weekly_themes(library, day + timedelta(days=7))}


def test_new_and_returning_works_and_daily_covers(museums) -> None:  # noqa: F811
    from fastapi.testclient import TestClient

    from frame_server.web import create_app, discover_api

    service = museums
    library = service.library
    old = (datetime.now(UTC) - timedelta(days=400)).isoformat(timespec="seconds")
    with library.batch():
        for n in range(6):
            library.upsert(_work(n, title=f"New snow {n}", suitability=0.8, pooled=True))
        for n in range(10, 15):
            item = library.upsert(_work(n, title=f"Kept {n}", suitability=0.8))
            library.update(item.id, added_at=old)
    app = create_app(service.settings)
    app.state.service = service
    discover_api._theme_rows.clear()
    discover_api._cards = (0.0, {})
    with TestClient(app) as client:
        rows = {r["key"]: r for r in client.get("/api/suggestions").json()}
        assert "new" not in rows  # no "Nowe w katalogu" row (Mateusz, 2026-10-30)
        assert len(rows["back"]["items"]) == 5
        winter = next(c for c in client.get("/api/themes").json() if c["key"] == "winter")
        assert winter["count"] == 6 and "new_count" not in winter

    pool = [_work(n, artist=f"A{n}") for n in range(40)]
    covers = {
        tuple(i.id for i in discover_api._cover(pool, f"2026-11-0{d}:x")) for d in range(1, 8)
    }
    assert len(covers) > 1  # other works each day


def test_highlights() -> None:
    star = _work(1, highlight=True)
    rules = PlaylistRules(terms=[HIGHLIGHT])
    assert matches(star, rules) and not matches(_work(2), rules)
    assert BY_KEY["masterpieces"].rules().terms == [HIGHLIGHT]

    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if "clevelandart" in request.url.host:
            return httpx.Response(200, json={"info": {"total": 0}, "data": []})
        return httpx.Response(200, json={"total": 0, "objectIDs": []})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        ClevelandMuseum(http).discover(Discovery(kind="painting", highlight=True))
        MetropolitanMuseum(http).discover(Discovery(kind="painting", highlight=True))
        assert list(Europeana(http).random_draw(Discovery(highlight=True), None)) == []
    assert sent[0].url.params["highlight"] == "1"
    assert sent[1].url.params["isHighlight"] == "true"
    assert len(sent) == 2  # Europeana cannot tell its highlights: not asked

    met = MetropolitanMuseum(httpx.Client())._map(
        {"objectID": 1, "isPublicDomain": True, "primaryImageSmall": "x", "isHighlight": True}
    )
    assert met is not None and met.highlight


SMK_RECORD = {
    "object_number": "KMS1620",
    "public_domain": True,
    "titles": [
        {"title": "Stue i Strandgade", "type": "museumstitel"},
        {"title": "Interior in Strandgade", "language": "engelsk"},
    ],
    "artist": ["Vilhelm Hammershøi"],
    "production": [
        {
            "creator": "Hammershøi, Vilhelm",
            "creator_nationality": "Danish",
            "creator_date_of_birth": "1864-05-15T00:00:00.000Z",
            "creator_date_of_death": "1916-02-13T00:00:00.000Z",
        }
    ],
    "production_date": [{"start": "1901-01-01T00:00:00.000Z", "period": "1901"}],
    "techniques": ["Oil on canvas"],
    "object_names": [{"name": "Painting"}],
    "frontend_url": "https://open.smk.dk/artwork/image/KMS1620",
    "image_iiif_id": "https://iip.smk.dk/iiif/jp2/abc.tif.jp2",
    "image_thumbnail": "https://iip-thumb.smk.dk/iiif/jp2/abc.tif.jp2/full/!1024,/0/default.jpg",
    "image_width": 4000,
    "image_height": 3000,
}


def test_statens_museum_for_kunst() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        closed = {**SMK_RECORD, "object_number": "KMS2", "public_domain": False}
        return httpx.Response(200, json={"found": 2, "items": [SMK_RECORD, closed]})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        smk = StatensMuseum(http)
        total, items = smk.search("Hammershøi", limit=2)
        smk.discover(Discovery(kind="painting", year_from=1880, year_to=1914), limit=2, page=2)
        assert smk.discover(Discovery(kind="poster")) == (0, [])
        found = smk.fetch("KMS1620")
    assert total == 2 and [i.id for i in items] == ["smk:KMS1620"]
    item = items[0]
    assert item.title == "Interior in Strandgade" and item.artist == "Vilhelm Hammershøi"
    assert item.year == 1901 and item.artist_bio == "Danish, 1864–1916"
    assert item.thumb_url.endswith("/full/600,/0/default.jpg")
    assert item.image_url == "https://iip.smk.dk/iiif/jp2/abc.tif.jp2/full/!2560,2560/0/default.jpg"
    assert found is not None and found.id == item.id
    search, discover = sent[0].url.params, sent[1].url.params
    assert search["keys"] == "Hammershøi" and search["lang"] == "en"
    assert discover["filters"].endswith(",[object_names:painting]")
    assert discover["offset"] == "2" and discover["range"].startswith(
        "[production_dates_start:{1880-01-01"
    )
    assert len(sent) == 3  # no request for posters


def test_statens_museum_for_kunst_for_private_use() -> None:
    from frame_server.library.museums import PRIVATE_LICENCE

    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        closed = {**SMK_RECORD, "object_number": "KMS7288", "public_domain": False}
        return httpx.Response(200, json={"found": 2, "items": [SMK_RECORD, closed]})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        _, items = StatensMuseum(http, private_use=True).search("Picasso", limit=2)
    assert sent[0].url.params["filters"] == "[has_image:true]"
    assert [i.license for i in items] == ["Public Domain Mark 1.0", PRIVATE_LICENCE]


def test_a_full_catalogue_still_takes_in_new_works(museums) -> None:  # noqa: F811
    service = museums
    player = service.player
    _wait(player.grow_catalogue())
    service.settings.catalogue_mb = 1
    service.images.thumbs_size = lambda: 2 * 1024 * 1024  # full
    job = player.grow_catalogue()
    assert job is not None  # a few new works, and as many old ones go
    _wait(job)
    assert player.grow_catalogue() is None  # not again for a while


def test_the_catalogue_takes_in_museum_highlights(museums, monkeypatch) -> None:  # noqa: F811
    from frame_server.library.museums import MUSEUMS
    from frame_server.player import CATALOGUE_HIGHLIGHT_MIN, HIGHLIGHTS_KEY

    service = museums
    library = service.library

    def starred(plain):
        class Starred(plain):  # type: ignore[misc,valid-type]
            def random_draw(self, spec: Discovery, rng):
                if not spec.highlight:
                    return super().random_draw(spec, rng)
                works = (self._work(n, "Star") for n in range(60))
                return (w.model_copy(update={"highlight": True}) for w in works)

        return Starred

    from frame_server.library.importer import HIGHLIGHT_SOURCES

    for key in HIGHLIGHT_SOURCES:
        monkeypatch.setitem(MUSEUMS, key, starred(MUSEUMS[key]))
    # Taken in before museums' highlights were kept: marked when met again.
    old = library.upsert(Item(id="met:Star-0", source="met", source_id="Star-0"))
    assert not old.highlight

    _wait(service.player.grow_catalogue())
    stars = library.query(PlaylistRules(terms=[HIGHLIGHT]))[0]
    assert stars >= CATALOGUE_HIGHLIGHT_MIN
    assert library.get(old.id).highlight
    assert library.get_state(HIGHLIGHTS_KEY)  # not asked again today


def test_a_card_for_each_liked_artist(museums) -> None:  # noqa: F811
    """ "Bo lubisz": a card per favourite artist, naming the artists like them
    with the most works in the catalogue (Mateusz, 2026-10-31)."""
    from fastapi.testclient import TestClient

    from frame_server.library.themes import LIKES, liked, make_liked, surname
    from frame_server.web import create_app, discover_api

    assert [surname(n) for n in ("Berthe Morisot", "van Gogh", "Pieter de Hooch")] == [
        "Morisot",
        "van Gogh",
        "de Hooch",
    ]
    assert surname("Stanisław Ignacy Witkiewicz") == "Witkiewicz"

    service = museums
    library = service.library
    painters = {"Claude Monet": 2, "Pierre-Auguste Renoir": 5, "Edgar Degas": 3, "Gauguin": 1}
    with library.batch():
        n = 0
        for artist, count in painters.items():
            for _ in range(count):
                n += 1
                library.upsert(_work(n, artist=artist, title=f"Work {n}", suitability=0.8))
        library.update("cma:1", favorite=True)
    taste = service.player.taste()
    assert taste[0] == "Claude Monet"

    made = make_liked(library, ["Claude Monet", "Monet", "Nobody Known"])
    assert [t.name for t in made] == ["Claude Monet"]  # once, and no theme names the third
    card = made[0]
    assert card.group == LIKES and card.key == "like-claude-monet"
    assert card.description == "Renoir, Degas i Gauguin"
    assert card.playlist == "Bo lubisz: Claude Monet"
    assert "Claude Monet" not in card.artists
    assert liked(library) == made
    assert theme(card.key, library) == card  # also after a restart

    app = create_app(service.settings)
    app.state.service = service
    discover_api._theme_rows.clear()
    discover_api._cards = (0.0, {})
    with TestClient(app) as client:
        cards = client.get("/api/themes").json()
        groups = list(dict.fromkeys(c["group"] for c in cards))
        assert groups[:2] == [WEEKLY, LIKES] or groups[0] == LIKES
        mine = next(c for c in cards if c["key"] == "like-claude-monet")
        assert mine["name"] == "Claude Monet" and mine["count"] == 9
        assert all(w["item"]["artist"] != "Claude Monet" for w in mine["cover"])
        rows = client.get("/api/suggestions").json()
        assert not [r for r in rows if r["key"].startswith("like:")]
        made = client.post(f"/api/themes/{card.key}/playlist", json={}).json()
        assert made["playlist"]["name"] == "Bo lubisz: Claude Monet"
        mine = next(c for c in client.get("/api/themes").json() if c["key"] == card.key)
        assert mine["playlist_id"] == made["playlist"]["id"]
