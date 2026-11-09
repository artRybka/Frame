"""Propozycje dnia: the first works of each card of "Dziś dla Ciebie", in
fours, made once a day for each person and played in that order."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.library import ItemKind, day_picks
from frame_server.library.themes import Theme
from frame_server.web import create_app

OWNER = {"Authorization": "Bearer secret"}
DAY = date(2026, 11, 9)


def test_fours_from_each_list_in_turn() -> None:
    a = [f"a{n}" for n in range(12)]
    b = [f"b{n}" for n in range(6)]
    c = [f"c{n}" for n in range(12)]
    order = day_picks.in_fours([a, b, c])
    assert order[:12] == [*a[:4], *b[:4], *c[:4]]
    assert order[12:22] == [*a[4:8], *b[4:6], *c[4:8]]
    assert len(order) == 30 and order[-4:] == c[8:]


def _app(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        api_token="secret",
    )
    return create_app(settings)


def _works(svc, artist: str, n: int) -> list[str]:
    return [
        svc.importer.add_upload(
            jpeg_bytes((10 * i % 255, 40 * len(artist) % 255, 90)),
            kind=ItemKind.ARTWORK,
            title=f"{artist} {i}",
            artist=artist,
        ).id
        for i in range(n)
    ]


def _card(key: str, artist: str) -> Theme:
    return Theme(key=key, name=artist, description="", group="Dziś dla Ciebie", artists=(artist,))


def test_the_days_list_is_made_once_and_played_in_fours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    with TestClient(app) as client:  # before the works: a start tidies the library
        ala = set(_works(svc, "Ala Malarka", 14))
        ola = set(_works(svc, "Ola Rytowniczka", 6))
        _works(svc, "Ela Rzadka", 2)  # too few for a card: left out, as in Odkrywaj
        cards = [
            _card("one", "Ala Malarka"),
            _card("two", "Ola Rytowniczka"),
            _card("few", "Ela Rzadka"),
        ]
        monkeypatch.setattr(day_picks, "cards", lambda library, user, day, private: cards)
        monkeypatch.setattr(
            day_picks, "theme_of_the_day", lambda day, library: _card("two", "Ola Rytowniczka")
        )

        got = client.get("/api/suggestions/day", headers=OWNER)
        assert got.status_code == 200, got.text
        body = got.json()
        assert [c["name"] for c in body["cards"]] == ["Ala Malarka", "Motyw dnia: Ola Rytowniczka"]
        ids = [r["item"]["id"] for r in body["items"]]
        assert len(ids) == 12 + 6
        assert set(ids[:4]) <= ala and set(ids[4:8]) <= ola
        assert set(ids[8:12]) <= ala and set(ids[12:14]) <= ola and set(ids[14:]) <= ala

        # Kept for the day: the cards changing does not change it.
        monkeypatch.setattr(day_picks, "cards", lambda library, user, day, private: cards[1:])
        again = client.get("/api/suggestions/day", headers=OWNER).json()
        assert [r["item"]["id"] for r in again["items"]] == ids

        # On the frame in that order, shuffle or not.
        assert client.post("/api/suggestions/play", headers=OWNER).status_code == 202
        assert svc.player.settings.shuffle
        state = svc.player.state
        svc.player._refill(state, svc.player.settings)
        assert [i for i in state.queue if i in ids] == [i for i in ids if i in state.queue]
        assert set(ids) <= set(state.queue) | {state.current_item_id}


def test_another_day_is_made_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    monkeypatch.setattr(
        day_picks, "cards", lambda library, user, day, private: [_card("one", "Ala Malarka")]
    )
    with TestClient(app):
        _works(svc, "Ala Malarka", 8)
        first = svc.player.day_picks("owner", DAY)
        assert first.day == DAY.isoformat() and len(first.ids) == 8
        later = date(2026, 11, 10)
        assert svc.player.day_picks("owner", later).day == later.isoformat()
