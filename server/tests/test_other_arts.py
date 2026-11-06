"""Sztuki inne: manuscripts, photographs, sculpture and decorative arts keep
a small share of the catalogue and keep to their own group (Mateusz
2026-11-06, "własny sos")."""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import date

from fastapi.testclient import TestClient
from test_pools import _fake, _wait, museums  # noqa: F401  (fixture)

from frame_server.library import Item, Job, PlaylistRules
from frame_server.library.museums import MUSEUMS, Discovery
from frame_server.library.themes import (
    COVER_MIN,
    GROUPS,
    OTHER_ART_THEMES,
    OTHER_ARTS,
    PRINTS,
    THEMES,
    other_art_searches,
    thin_other_art,
)
from frame_server.library.vocabulary import (
    DECORATIVE,
    MANUSCRIPTS,
    OBJECT_CATEGORIES,
    PHOTOGRAPHY,
    SCULPTURE,
    object_category,
    term,
)
from frame_server.player import OTHER_ART_SHARES

#: A museum's type for each kind it is asked for.
TYPES = {
    "photograph": "Photograph",
    "manuscript": "Manuscript",
    "sculpture": "Sculpture",
    "decorative": "Ceramic",
}


def _objects(key: str) -> type:
    """A museum that draws works of the kind asked for."""
    plain = _fake(key)

    class Objects(plain):  # type: ignore[misc,valid-type]
        def random_draw(self, spec: Discovery, rng: random.Random) -> Iterator[Item]:
            if spec.kind not in TYPES:
                return super().random_draw(spec, rng)
            works = (self._work(n, f"{key} {spec.kind}") for n in range(60))
            return (w.model_copy(update={"classification": TYPES[spec.kind]}) for w in works)

    return Objects


def _work(n: int, **fields) -> Item:
    return Item(
        id=f"aic:{n}",
        source="aic",
        source_id=str(n),
        artist=fields.pop("artist", f"Painter {n}"),
        image_url=f"https://aic.invalid/{n % 6}.jpg",
        thumb_url=f"https://aic.invalid/{n % 6}.jpg",
        **fields,
    )


def _paintings(library, count: int) -> None:
    with library.batch():
        for n in range(count):
            library.upsert(_work(n, classification="Painting", pooled=True))


def test_themes_of_other_arts_keep_to_their_group() -> None:
    assert GROUPS.index(OTHER_ARTS) == GROUPS.index(PRINTS) + 1
    assert all(t.group == OTHER_ARTS for t in OTHER_ART_THEMES)
    assert not any(t.group == OTHER_ARTS for t in THEMES)  # never the theme of the day
    for found in OTHER_ART_THEMES:
        categories = [k for k in found.terms if k in OBJECT_CATEGORIES]
        assert len(categories) == 1, found.key
        assert all(term(k) is not None for k in found.terms), found.key
    # A card for each technique, from the catalogue, then themes searched in museums.
    cards = [t for t in OTHER_ART_THEMES if t.catalogue]
    assert [t.terms for t in cards] == [(k,) for k in OBJECT_CATEGORIES]
    assert set(other_art_searches()) == set(OBJECT_CATEGORIES)
    assert abs(sum(OTHER_ART_SHARES.values()) - 0.06) < 1e-9


def test_the_catalogue_keeps_a_share_of_other_arts(museums, monkeypatch) -> None:  # noqa: F811
    service = museums
    monkeypatch.setattr("frame_server.player.thin_other_art", lambda library: [])
    for key in [k for k, m in MUSEUMS.items() if m.draws]:
        monkeypatch.setitem(MUSEUMS, key, _objects(key))
    library, player = service.library, service.player
    _paintings(library, 200)
    room = player.other_art_room(fresh=True)
    assert room == {PHOTOGRAPHY: 4, MANUSCRIPTS: 3, SCULPTURE: 2, DECORATIVE: 2}

    job = Job(id="test", description="catalogue")
    player._add_other_art(job)
    works = [i for i in library.query(include_excluded=True)[1] if i.pooled]
    have = {k: sum(object_category(i) == k for i in works) for k in OBJECT_CATEGORIES}
    assert have == {PHOTOGRAPHY: 4, MANUSCRIPTS: 3, SCULPTURE: 2, DECORATIVE: 2}
    assert player.other_art_room(fresh=True) == {}
    # Found only when asked for.
    assert library.query(PlaylistRules(terms=[SCULPTURE]))[0] == 2
    assert not any(object_category(i) for i in library.query()[1])

    # Over its share (a lowered limit, searches): the ones seen least go.
    with library.batch():
        for n in range(1000, 1010):
            library.upsert(_work(n, classification="Sculpture", pooled=True))
    liked = library.upsert(_work(1010, classification="Sculpture", pooled=True, favorite=True))
    assert player.trim_other_art() == 11  # 13 of 222 works, 2 wanted
    left = library.query(PlaylistRules(terms=[SCULPTURE]))[1]
    assert len(left) == 2 and liked.id in {i.id for i in left}


def test_other_arts_have_no_study_nor_painting_cards(museums) -> None:  # noqa: F811
    from frame_server.library.themes import _artist_of_the_week
    from frame_server.web import create_app

    service = museums
    library = service.library
    _paintings(library, 3)
    # Kept and liked by the owner, so no rule of the catalogue leaves it out.
    bust = library.upsert(
        _work(500, artist="Auguste Rodin", classification="Sculpture", favorite=True)
    )
    assert "Auguste Rodin" not in service.player.taste()
    assert service.study.status(bust) == ("off", "")
    week = _artist_of_the_week([bust] * 10, random.Random(1), set())
    assert week is None
    assert bust.id not in {i.id for i in service.daily.candidates(library.get("aic:0"))}

    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        refused = client.post(f"/api/study/{bust.id}")
        assert refused.status_code == 409
        assert client.get(f"/api/study/{bust.id}").json()["status"] == "off"
    assert service.daily.choose(date(2026, 11, 6)) is None or (
        service.daily.choose(date(2026, 11, 6)).id != bust.id
    )


def test_thin_cards_of_other_arts_are_filled_first(museums, monkeypatch) -> None:  # noqa: F811
    # "Pierwsze kolory" had 2 works (Mateusz 2026-11-06): the night looks
    # for the works of such cards first, whatever room their technique has.
    service = museums
    library, player = service.library, service.player
    colours = next(t for t in OTHER_ART_THEMES if t.key == "first-colours")
    thin = dict(thin_other_art(library))
    assert thin[colours] == 0
    assert not any(t.catalogue for t in thin)  # the technique's own card has no searches
    with library.batch():
        for n in range(COVER_MIN):
            library.upsert(
                _work(
                    700 + n,
                    classification="Photograph",
                    medium="1 photograph : autochrome, color",
                    year=1910,
                    color_tags=["colorful"],
                    pooled=True,
                )
            )
    assert colours not in dict(thin_other_art(library))

    asked: list[tuple[str, int]] = []

    def collect(category, searches, count, job, fits) -> None:
        asked.append((category, count))
        assert list(searches)

    monkeypatch.setattr(service.importer, "collect_searched", collect)
    monkeypatch.setattr(player, "other_art_room", lambda fresh=False: {})  # all full
    player._add_other_art(Job(id="test", description="catalogue"))
    assert asked and all(count <= COVER_MIN for _, count in asked)
    assert {c for c, _ in asked} <= set(OBJECT_CATEGORIES)
    assert len(asked) == len(thin_other_art(library))
