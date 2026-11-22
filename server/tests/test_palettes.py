"""„Barwy” in „Podobne do” (Mateusz 2026-11-21): works found by their
palettes, a photograph's palette made on the phone the same way."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.imaging.color import linear_to_oklab
from frame_server.library import palettes as P
from frame_server.library.models import ColorSwatch, Item, ItemKind, PlaylistRules
from frame_server.service import FrameService

REPO = Path(__file__).resolve().parents[2]
SWIFT = REPO / "ios" / "FrameTests" / "PhonePaletteTests.swift"
DEMO = REPO / "ios" / "Frame" / "Resources" / "DemoImages" / "aic_14598.jpg"


def _made_up() -> np.ndarray:
    """The made-up picture ``PhonePaletteTests`` draws too: a red, a blue,
    a beige and a small green patch."""
    rgb = np.zeros((30, 40, 3), np.uint8)
    for y in range(30):
        for x in range(40):
            if 30 <= x < 34 and 5 <= y < 9:
                v: tuple[int, int, int] = (40, 140, 60)
            elif x < 14:
                v = (180 + y, 40 + x, 30)
            elif x < 27:
                v = (30, 60 + y, 150 + x)
            else:
                v = (220 - y, 205 - y, 180)
            rgb[y, x] = v
    return rgb


def _swift_rows(name: str) -> np.ndarray:
    text = SWIFT.read_text()
    block = re.search(rf"// {name}: begin\n(.*?)// {name}: end", text, re.S)
    assert block, f"no {name} in {SWIFT.name}"
    numbers = [float(n) for n in re.findall(r"-?\d+\.\d+", block.group(1))]
    return np.asarray(numbers, dtype=np.float32).reshape(-1, 4)


def _swift(rows: np.ndarray) -> str:
    """Rows as the Swift fixture writes them."""
    return "\n".join(
        "        [" + ", ".join(f"{v:.5f}" for v in row) + "]," for row in rows.tolist()
    )


def test_the_phone_makes_a_photographs_palette_as_the_server_does() -> None:
    """``PhonePaletteTests`` holds the phone to these: the made-up picture's
    colours exactly, the demo photograph's (read and made smaller by each
    in its own way) near. A change here is a change there: print
    ``_swift(rows)`` and paste it between the markers."""
    made_up = P.colours_of(P.picture(_made_up()))
    assert np.allclose(_swift_rows("made-up"), made_up, atol=2e-5), _swift(made_up)
    demo = P.colours_of(linear_to_oklab(P.C._grid(Image.open(DEMO), P.GRID)))
    assert np.allclose(_swift_rows("demo"), demo, atol=2e-5), _swift(demo)
    text = SWIFT.read_text()
    for name, value in {
        "grid": P.GRID,
        "clusters": P.CLUSTERS,
        "rounds": P.ROUNDS,
        "maxMasses": P.tonal.MAX_MASSES,
    }.items():
        assert re.search(rf"static let {name} = {value}\b", (REPO / _PHONE).read_text()), name
    for name, value in {"band": P.tonal.BAND, "apart": P.tonal.APART}.items():
        assert re.search(rf"static let {name}: Double = {value}\b", (REPO / _PHONE).read_text()), (
            name
        )
    assert "made-up" in text


_PHONE = Path("ios/Frame/Networking/PhonePalette.swift")


def test_the_made_up_picture_has_its_four_colours() -> None:
    rows = P.colours_of(P.picture(_made_up()))
    hues = np.degrees(np.arctan2(rows[:, 2], rows[:, 1])) % 360
    chroma = np.hypot(rows[:, 1], rows[:, 2])
    assert any(c > 0.15 and (h < 45 or h > 330) for c, h in zip(chroma, hues, strict=True))  # red
    assert any(c > 0.1 and 230 < h < 290 for c, h in zip(chroma, hues, strict=True))  # blue
    assert any(c > 0.1 and 120 < h < 175 for c, h in zip(chroma, hues, strict=True))  # green
    assert abs(float(rows[:, 3][: len(rows)].sum()) - 1) < 0.05  # the green is no mass


def _palette(*colours: tuple[str, float]) -> np.ndarray:
    return P.palette([P.C._lab(h) for h, _ in colours], [w for _, w in colours])


def test_palettes_are_as_far_as_their_colours_must_move() -> None:
    red = _palette(("#e8dcc4", 0.7), ("#b02020", 0.3))
    redder = _palette(("#e8dcc4", 0.65), ("#b82418", 0.35))
    blue = _palette(("#e8dcc4", 0.7), ("#2040b0", 0.3))
    grey = _palette(("#e8dcc4", 0.7), ("#606060", 0.3))
    colours = np.stack([p[:, :3] for p in (red, redder, blue, grey)])
    weights = np.stack([p[:, 3] for p in (red, redder, blue, grey)])
    d = P.distances(red, colours, weights)
    assert d[0] < 0.005 and d[0] < d[1] < d[3] < d[2]
    # The red counts more than its share: a beige paper does not outweigh it.
    assert red[1, 3] > 0.3 + 0.1


def _work(service: FrameService, item_id: str, medium: str, *colours: tuple[str, float]) -> Item:
    source, _, source_id = item_id.partition(":")
    return service.library.upsert(
        Item(
            id=item_id,
            source=source,
            source_id=source_id,
            kind=ItemKind.ARTWORK,
            title=item_id,
            medium=medium,
            colors=[ColorSwatch(hex=h, weight=w) for h, w in colours],
        )
    )


def test_barwy_alone_finds_the_works_of_near_colours_of_its_kind(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from frame_server.web import create_app

    monkeypatch.setattr(P, "LEAST", 1)
    _work(service, "met:1", "oil on canvas", ("#e8dcc4", 0.7), ("#b02020", 0.3))
    _work(service, "met:2", "oil on canvas", ("#e8dcc4", 0.65), ("#b82418", 0.35))
    _work(service, "met:3", "oil on canvas", ("#e8dcc4", 0.7), ("#2040b0", 0.3))
    _work(service, "met:4", "etching", ("#e8dcc4", 0.7), ("#b02020", 0.3))  # paper
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:

        def ids(**params: Any) -> list[str]:
            answer = client.get("/api/library/items", params=params)
            assert answer.status_code == 200, answer.text
            return [i["id"] for i in answer.json()["items"]]

        # Szukanie wyglądem off: "Barwy" alone needs no numbers.
        assert not service.looks.enabled()
        assert ids(like="met:1", like_by="colours") == ["met:2"]
        monkeypatch.setattr(P, "LEAST", 2)  # however far: the blue after the red
        assert ids(like="met:1", like_by="colours", like_further=3) == ["met:2", "met:3"]
        monkeypatch.setattr(P, "LEAST", 1)
        assert ids(like="met:4", like_by="colours") == []  # no other work on paper
        assert client.get("/api/library/items", params={"like": "met:1"}).status_code == 409
    rules = PlaylistRules(like="met:1", like_by="colours")  # a smart playlist keeps it
    assert [i.id for i in service.library.query(rules)[1]] == ["met:2"]


def test_barwy_beside_the_shape_keeps_its_works_of_near_colours(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    looks = service.looks
    monkeypatch.setattr(P, "LEAST", 1)
    _work(service, "met:1", "oil", ("#e8dcc4", 0.7), ("#b02020", 0.3))
    _work(service, "met:2", "oil", ("#e8dcc4", 0.65), ("#b82418", 0.35))
    _work(service, "met:3", "oil", ("#e8dcc4", 0.7), ("#2040b0", 0.3))
    monkeypatch.setattr(looks, "enabled", lambda: True)
    monkeypatch.setattr(looks, "similar", lambda *a, **k: [_Found("met:3"), _Found("met:2")])
    assert looks.alike("met:1") == ["met:3", "met:2"]
    assert looks.alike("met:1", colours=True) == ["met:2"]


class _Found:
    def __init__(self, item_id: str) -> None:
        self.item = Item(id=item_id, source="met", source_id=item_id)


def test_a_photographs_palette_comes_with_its_numbers_or_is_made_here(
    service: FrameService, monkeypatch: pytest.MonkeyPatch
) -> None:
    looks = service.looks
    monkeypatch.setattr(looks, "local", lambda: True)
    monkeypatch.setattr(looks, "_asked", lambda: type("A", (), {"size": 4})())
    rows = P.colours_of(P.picture(_made_up()))
    key = looks.photo_numbers(np.ones(4, dtype=np.float32), rows)
    kept = looks.photo_palette(key)
    assert kept is not None and np.allclose(kept, P.palette(rows[:, :3], rows[:, 3]))
    with pytest.raises(ValueError):
        looks.photo_numbers(np.ones(4, dtype=np.float32), np.ones(5, dtype=np.float32))
    _work(service, "met:1", "oil", ("#c03028", 0.4), ("#3048a0", 0.4), ("#d8cfb8", 0.2))
    _work(service, "met:2", "oil", ("#203018", 0.9), ("#101010", 0.1))
    monkeypatch.setattr(P, "LEAST", 1)
    assert looks.alike(key, by="colours") == ["met:1"]
