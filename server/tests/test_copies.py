"""Every copy of a work's picture, for the owner to pick (frame_server.copies)."""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps
from test_sharper import OWN, OWN_THUMB, Web, _copy, _detail, _jpeg, _offer, _own, _print, _serve

from frame_server.config import Settings
from frame_server.service import FrameService
from frame_server.web.app import create_app


@pytest.fixture
def app(tmp_path: Path) -> Iterator[tuple[TestClient, FrameService, Web, list[Any]]]:
    created = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    service: FrameService = created.state.service
    with TestClient(created) as client:
        web: Web = {
            OWN: _jpeg(_print(1, (1686, 1124)), 85),
            OWN_THUMB: _jpeg(_print(1, (600, 400))),
        }
        _serve(service, web)
        hits: list[Any] = []
        service.sharper.commons_file = lambda item: ""
        service.copies.sources = lambda: ["wmc", "met"]

        def search_in(key: str, query: str, n: int) -> list[Any]:
            if key == "met":
                raise ValueError("the Met is down")
            service.importer.remember(hits)
            return list(hits)

        service.copies.search_in = search_in
        yield client, service, web, hits


def _lines(client: TestClient, item_id: str) -> list[dict[str, Any]]:
    resp = client.get(f"/api/library/items/{item_id}/copies")
    assert resp.status_code == 200
    return [json.loads(line) for line in resp.text.splitlines() if line]


def _final(lines: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each copy as last told, by id; dropped ones left out."""
    copies: dict[str, dict[str, Any]] = {}
    for line in lines:
        if line["kind"] == "copy":
            copies[line["copy"]["item_id"]] = line["copy"]
        elif line["kind"] == "drop":
            copies.pop(line["item_id"], None)
    return copies


def test_every_copy_is_listed_with_its_verdict(app: Any) -> None:
    client, service, web, hits = app
    own = _own(service)
    painting = _print(1, (3600, 2400))
    sharper, detail, grey, other, smaller = (
        _copy(1),
        _copy(2),
        _copy(3),
        _copy(4, title="Bathing Nymphs and Child"),
        _copy(5, width=1700, height=1133),
    )
    _offer(web, sharper, painting)
    _offer(web, detail, _detail(painting))
    _offer(web, grey, ImageOps.grayscale(painting).convert("RGB"))
    _offer(web, other, _print(7, (3600, 2400)))  # another work, the same title
    _offer(web, smaller, _print(1, (1700, 1133)))
    hits[:] = [sharper, detail, grey, other, smaller]

    lines = _lines(client, own.id)
    assert lines[0] == {
        "kind": "start",
        "sources": ["wmc", "met"],
        "source": "",
        "found": 0,
        "failed": False,
        "item_id": "",
    }
    assert lines[-1]["kind"] == "end"
    sources = {line["source"]: line for line in lines if line["kind"] == "source"}
    assert sources["met"]["failed"] and not sources["wmc"]["failed"]
    assert sources["wmc"]["found"] == 5
    # Each copy is told at once, then judged.
    assert any(line["kind"] == "copy" and line["copy"]["verdict"] == "checking" for line in lines)

    copies = _final(lines)
    current = copies.pop(own.id)
    assert current["role"] == "current" and current["width"] == 1686
    assert set(copies) == {"wmc:1", "wmc:2", "wmc:3", "wmc:5"}  # another work is dropped
    best = copies["wmc:1"]
    assert best["verdict"] == "better" and best["measured"]
    assert best["width"] == 3600 and best["gain"] == round(2560 / 1686, 2)
    assert "whole" in best["notes"] and "colours" in best["notes"]
    assert copies["wmc:2"]["verdict"] == "off" and "fragment" in copies["wmc:2"]["notes"]
    assert copies["wmc:3"]["verdict"] == "off" and "grey" in copies["wmc:3"]["notes"]
    assert copies["wmc:5"]["verdict"] == "worse"


def test_the_owner_picks_a_copy_and_goes_back(app: Any) -> None:
    client, service, web, hits = app
    own = _own(service, favorite=True)
    copy = _copy(9)
    _offer(web, copy, _print(1, (3600, 2400)))
    service.importer.remember([copy])

    item = client.put(f"/api/library/items/{own.id}/copy", json={"item_id": "wmc:9"}).json()
    assert item["sharper"]["item_id"] == "wmc:9" and item["sharper"]["chosen"]
    assert item["favorite"] and item["title"] == "Bathing Nymphs and Child"
    with Image.open(service.images.image_path(service.library.get(own.id))) as img:
        assert max(img.size) == 2560
    # The look in the background leaves the pick be.
    view = client.post(f"/api/library/items/{own.id}/sharpen").json()
    assert view["status"] == "found" and view["sharper"]["item_id"] == "wmc:9"

    # The list now tells the copy as current and the work's own apart.
    hits[:] = []
    copies = _final(_lines(client, own.id))
    assert copies["wmc:9"]["role"] == "current" and copies["wmc:9"]["chosen"]
    assert copies[own.id]["role"] == "own"
    assert copies[own.id]["width"] == 1686  # noted when the copy took its place

    # Back to the work's own: no copy is looked for again.
    item = client.put(f"/api/library/items/{own.id}/copy", json={"item_id": own.id}).json()
    assert item["sharper"] is None
    service.sharper.search = lambda query, n: pytest.fail("looked again")
    view = client.post(f"/api/library/items/{own.id}/sharpen", params={"wait": 5}).json()
    assert view["status"] == "fine"
    picture = client.get(f"/api/library/items/{own.id}/image")
    with Image.open(io.BytesIO(picture.content)) as img:
        assert max(img.size) == 1686


def test_another_picture_is_refused(app: Any) -> None:
    client, service, web, _ = app
    own = _own(service)
    other = _copy(4, title="Ville-d'Avray")
    _offer(web, other, _print(7, (3600, 2400)))
    service.importer.remember([other])
    resp = client.put(f"/api/library/items/{own.id}/copy", json={"item_id": "wmc:4"})
    assert resp.status_code == 422
    assert (
        client.put(f"/api/library/items/{own.id}/copy", json={"item_id": "xx:1"}).status_code == 404
    )
    stored = service.library.get(own.id)
    assert stored is not None and stored.sharper is None


def test_one_spot_in_both_pictures_at_the_frames_scale(app: Any) -> None:
    client, service, web, _ = app
    own = _own(service)
    copy = _copy(9)
    _offer(web, copy, _print(1, (3600, 2400)))
    service.importer.remember([copy])

    spot = client.get(f"/api/library/items/{own.id}/copies/wmc:9/spot").json()
    assert 0 < spot["x"] < 1 and 0 < spot["y"] < 1
    assert spot["w"] == pytest.approx(320 / 2560)
    here = Image.open(io.BytesIO(base64.b64decode(spot["current"])))
    there = Image.open(io.BytesIO(base64.b64decode(spot["copy"])))
    assert here.size == there.size == (320, 320)
    # The same place in both: the copy's close-up looks like the own's.
    a = np.asarray(ImageOps.grayscale(here.resize((40, 40))), float)
    b = np.asarray(ImageOps.grayscale(there.resize((40, 40))), float)
    assert np.abs(a - b).mean() < 25

    asked = client.get(
        f"/api/library/items/{own.id}/copies/wmc:9/spot", params={"x": 0.1, "y": 0.9}
    )
    corner = asked.json()
    assert corner["x"] == pytest.approx(0.1) and corner["y"] == pytest.approx(0.9)
