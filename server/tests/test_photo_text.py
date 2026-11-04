"""A photo's title and line (caption, the model's words, the day, the town)
and the towns of its coordinates."""

from __future__ import annotations

import httpx
import pytest

from frame_server import places
from frame_server.library import Item, ItemKind, ItemSummary, PhotoInfo
from frame_server.player import caption_for, text_block_for


def _photo(title: str = "", **info: object) -> Item:
    return Item(
        id="icloud:G1",
        kind=ItemKind.PHOTO,
        source="icloud",
        source_id="G1",
        title=title,
        date_text="2026-10-29",
        photo=PhotoInfo(**info),  # type: ignore[arg-type]
    )


def test_the_title_is_the_caption_then_the_models_words_then_the_day() -> None:
    words = _photo(place="Kraków")
    words.photo.title = "Montaż drewnianej ścianki"  # type: ignore[union-attr]
    summary = ItemSummary.of(words)
    assert summary.title == "Montaż drewnianej ścianki"
    assert summary.subtitle == "29 października 2026 · Kraków"

    own = _photo(title="Hel", caption="Hel")
    own.photo.title = "Plaża nad morzem"  # type: ignore[union-attr]
    assert ItemSummary.of(own).title == "Hel"  # the owner's caption wins

    model = _photo(place="Rzym, Włochy")
    model.photo.title = "Fontanna na placu"  # type: ignore[union-attr]
    assert ItemSummary.of(model).title == "Fontanna na placu"
    assert caption_for(model) == "Fontanna na placu · 29 października 2026 · Rzym, Włochy"

    # Nothing written yet: the day is the title, and not said twice.
    bare = _photo(taken_at="2026-10-28T21:15:00", place="Kraków")
    summary = ItemSummary.of(bare)
    assert summary.title == "28 października 2026"
    assert summary.subtitle == "Kraków"
    block = text_block_for(bare)
    assert block.title == "28 października 2026" and block.meta == ["Kraków"]


def test_works_keep_their_title_and_artist() -> None:
    work = Item(id="met:1", source="met", source_id="1", title="Boats", artist="Monet")
    summary = ItemSummary.of(work)
    assert summary.title == "Boats" and summary.subtitle == ""


def test_town_names_from_nominatim() -> None:
    home = {"address": {"city": "Kraków", "country": "Polska", "country_code": "pl"}}
    abroad = {"address": {"town": "Tivoli", "country": "Włochy", "country_code": "it"}}
    village = {"address": {"village": "Zawoja", "county": "suski", "country_code": "pl"}}
    assert places.name_of(home) == "Kraków"
    assert places.name_of(abroad) == "Tivoli, Włochy"
    assert places.name_of(village) == "Zawoja"
    assert places.name_of({"address": {"country": "Norwegia", "country_code": "no"}}) == "Norwegia"
    assert places.name_of({}) == ""


def test_photos_get_their_towns_once_for_each_spot(
    service, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return httpx.Response(200, json={"address": {"city": "Kraków", "country_code": "pl"}})

    monkeypatch.setattr(
        places, "client", lambda: httpx.Client(transport=httpx.MockTransport(answer))
    )
    lib = service.library
    for n, (lat, lon) in enumerate([(50.0614, 19.9372), (50.0631, 19.9405), (None, None)]):
        lib.upsert(
            Item(
                id=f"icloud:{n}",
                kind=ItemKind.PHOTO,
                source="icloud",
                source_id=str(n),
                photo=PhotoInfo(latitude=lat, longitude=lon),
            )
        )
    assert service.places.fill() == 2
    # Two photos a few hundred metres apart: one question, sent rounded.
    assert len(asked) == 1
    params = asked[0].url.params
    assert (params["lat"], params["lon"], params["accept-language"]) == ("50.06", "19.94", "pl")
    assert lib.get("icloud:0").photo.place == "Kraków"  # type: ignore[union-attr]
    assert lib.get("icloud:2").photo.place is None  # type: ignore[union-attr]

    # Named photos are not asked about again; a new one at a known spot neither.
    lib.upsert(
        Item(
            id="icloud:3",
            kind=ItemKind.PHOTO,
            source="icloud",
            source_id="3",
            photo=PhotoInfo(latitude=50.06, longitude=19.94),
        )
    )
    assert service.places.fill() == 1
    assert len(asked) == 1


def test_a_failed_lookup_is_tried_again_later(service) -> None:
    # The tests' Nominatim answers 404 (conftest).
    service.library.upsert(
        Item(
            id="icloud:1",
            kind=ItemKind.PHOTO,
            source="icloud",
            source_id="1",
            photo=PhotoInfo(latitude=50.06, longitude=19.94),
        )
    )
    assert service.places.fill() == 0
    assert service.library.get("icloud:1").photo.place is None  # type: ignore[union-attr]
