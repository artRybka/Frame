"""Galeria: each person's works one after another, from their hearts, works
like them and a few new ones; the works given out lately not again."""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from conftest import jpeg_bytes
from fastapi.testclient import TestClient

from frame_server import gallery
from frame_server.config import Settings
from frame_server.library import ItemKind
from frame_server.web import create_app

OWNER = {"Authorization": "Bearer secret"}
DAY = date(2026, 11, 23)


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


def test_hearts_and_their_look_alikes_come_first_and_nothing_twice(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    with TestClient(app):
        liked = _works(svc, "Ala Malarka", 3)
        alike = _works(svc, "Ola Rytowniczka", 4)
        _works(svc, "Ela Inna", 30)
        for i in liked:
            svc.library.set_favorite("owner", i, True)
        near = {i: alike for i in liked}
        lib = svc.library
        got = gallery.next_works(
            lib, "owner", 8, lambda i, n: near.get(i, []), day=DAY, rng=random.Random(1)
        )
        ids = [i.id for i in got]
        assert len(ids) == 8 and len(set(ids)) == 8
        # Hearts and look-alikes far more than their share of the catalogue.
        assert len([i for i in ids if i in liked or i in alike]) >= 4
        again = gallery.next_works(
            lib, "owner", 8, lambda i, n: near.get(i, []), day=DAY, rng=random.Random(2)
        )
        assert not set(ids) & {i.id for i in again}


def test_a_round_starts_again_when_everything_was_shown(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    with TestClient(app):
        _works(svc, "Ala Malarka", 2)
        _works(svc, "Ola Rytowniczka", 2)
        lib = svc.library
        first = gallery.next_works(lib, "owner", 4, lambda i, n: [], day=DAY)
        assert len(first) == 4
        second = gallery.next_works(lib, "owner", 4, lambda i, n: [], day=DAY)
        assert len(second) == 4  # the round began again


def test_the_endpoint_gives_light_works(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    with TestClient(app) as client:
        _works(svc, "Ala Malarka", 5)
        got = client.get("/api/gallery?count=3", headers=OWNER)
        assert got.status_code == 200, got.text
        assert len(got.json()) == 3
        assert client.get("/api/gallery").status_code == 401


def test_no_more_than_two_of_one_artist_while_there_are_others(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc = app.state.service
    with TestClient(app):
        for n in range(6):
            _works(svc, f"Artysta {n}", 4)
        got = gallery.next_works(svc.library, "owner", 10, lambda i, n: [], day=DAY)
        assert len(got) == 10
        counts: dict[str, int] = {}
        for item in got:
            counts[item.artist] = counts.get(item.artist, 0) + 1
        assert max(counts.values()) <= gallery.SAME_ARTIST


def test_a_hearted_work_comes_only_as_a_heart(tmp_path: Path, monkeypatch) -> None:
    """Works he likes that look like other works he likes are not drawn as
    their look-alikes, nor as their artist's other works or good ones
    (Mateusz 2026-11-25)."""
    app = _app(tmp_path)
    svc = app.state.service
    with TestClient(app):
        liked = _works(svc, "Ala Malarka", 4)
        others = _works(svc, "Ala Malarka", 2)
        for name in ("Ola Rytowniczka", "Ela Inna", "Iza Rzeźbiarka", "Ewa Graficzka"):
            others += _works(svc, name, 3)
        for i in liked:
            svc.library.set_favorite("owner", i, True)
        # Each hearted work's look-alikes: the other hearted ones first.
        near = {i: [j for j in liked if j != i] + others for i in liked}
        # No heart drawn as a heart: whatever comes is from the other pools.
        monkeypatch.setattr(gallery, "WEIGHTS", {**gallery.WEIGHTS, "heart": 0.0})
        got = gallery.next_works(
            svc.library, "owner", 6, lambda i, n: near.get(i, []), day=DAY, rng=random.Random(3)
        )
        ids = [i.id for i in got]
        assert ids and not set(ids) & set(liked)
        assert set(ids) <= set(others)
