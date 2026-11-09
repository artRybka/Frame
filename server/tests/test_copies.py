"""Every copy of a work's picture, for the owner to pick (frame_server.copies)."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps
from test_sharper import (
    OWN,
    OWN_THUMB,
    Web,
    _copy,
    _detail,
    _jpeg,
    _offer,
    _own,
    _print,
    _serve,
    _slide,
)

from frame_server.config import Settings
from frame_server.library import hosts
from frame_server.library.duplicates import surname
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
        service.copies.tiled = lambda item_id: False  # Commons not asked
        service.copies.work_qid = lambda item: ""
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
    # Everything a source found is told, another work too (only to look at).
    assert set(copies) == {"wmc:1", "wmc:2", "wmc:3", "wmc:4", "wmc:5"}
    assert copies["wmc:4"]["verdict"] == "off" and copies["wmc:4"]["notes"] == ["other"]
    assert not any(line["kind"] == "drop" for line in lines)
    best = copies["wmc:1"]
    assert best["verdict"] == "better" and best["measured"]
    assert best["width"] == 3600 and best["gain"] == round(2560 / 1686, 2)
    assert "whole" in best["notes"] and "colours" in best["notes"]
    assert copies["wmc:2"]["verdict"] == "off" and "fragment" in copies["wmc:2"]["notes"]
    assert copies["wmc:3"]["verdict"] == "off" and "grey" in copies["wmc:3"]["notes"]
    assert copies["wmc:5"]["verdict"] == "worse"


def test_a_copy_in_other_colours_than_an_archives_slide_is_better(app: Any) -> None:
    """Foto Marburg's faded slide (Mateusz 2026-11-09): Commons' copy in the
    painting's colours is better, WikiArt's about as large too, with no
    warning about its colours."""
    client, service, web, hits = app
    own = _slide(service, web)
    larger, as_large = _copy(1), _copy(2, width=1618, height=1079)
    _offer(web, larger, _print(1, (3600, 2400)))
    _offer(web, as_large, _print(1, (1618, 1079)))
    hits[:] = [larger, as_large]
    copies = _final(_lines(client, own.id))
    assert copies["wmc:1"]["verdict"] == "better" and "colour-off" in copies["wmc:1"]["notes"]
    assert copies["wmc:2"]["verdict"] == "better"


def test_a_copy_with_a_tile_set_is_offered(app: Any) -> None:
    """ "Nocna straż" (Mateusz 2026-11-09): of two Commons copies as large,
    the one with a tile set goes first and says so."""
    client, service, web, hits = app
    own = _own(service)
    tiled, plain = _copy(1, width=1618, height=1079), _copy(2, width=1618, height=1079)
    for copy in (tiled, plain):
        _offer(web, copy, _print(1, (1618, 1079)))
    hits[:] = [tiled, plain]
    service.copies.tiled = lambda item_id: item_id == "wmc:1"
    copies = _final(_lines(client, own.id))
    assert copies["wmc:1"]["verdict"] == "better" and "tiles" in copies["wmc:1"]["notes"]
    assert copies["wmc:2"]["verdict"] == "worse" and "tiles" not in copies["wmc:2"]["notes"]
    # Shown already with tiles: another tile set is not offered for them.
    service.copies.tiled = lambda item_id: item_id in ("wmc:1", own.id)
    copies = _final(_lines(client, own.id))
    assert "tiles" in copies[own.id]["notes"]
    assert copies["wmc:1"]["verdict"] == "worse" and "tiles" in copies["wmc:1"]["notes"]


def test_a_tiled_commons_file_of_the_work_is_listed(app: Any) -> None:
    """The search by title missed "Nachtwacht" (Mateusz 2026-11-09): the
    Commons files with a tile set are found by the work's Wikidata item."""
    client, service, web, _hits = app
    own = _own(service)
    tiled = _copy(9, width=1618, height=1079)
    _offer(web, tiled, _print(1, (1618, 1079)))
    service.copies.work_qid = lambda item: "Q219831"
    service.copies.tiled = lambda item_id: item_id == "wmc:9"

    class Tiles:
        def tiled_files(self, qid: str) -> list[str]:
            return ["File:Nachtwacht - Google Art Project.jpg"] if qid == "Q219831" else []

    asked: list[str] = []

    def commons_file(name: str) -> Any:
        asked.append(name)
        service.importer.remember([tiled])
        return tiled

    service.importer.fragments = Tiles()  # type: ignore[assignment]
    service.importer.commons_file = commons_file  # type: ignore[method-assign]
    copies = _final(_lines(client, own.id))
    assert asked == ["Nachtwacht - Google Art Project.jpg"]
    assert copies["wmc:9"]["verdict"] == "better" and "tiles" in copies["wmc:9"]["notes"]


def test_a_silent_source_is_told_as_failed_in_time(app: Any) -> None:
    client, service, web, hits = app
    own = _own(service)
    painting = _print(1, (3600, 2400))
    sharper, late = _copy(1), _copy(6)
    _offer(web, sharper, painting)
    _offer(web, late, painting)
    hits[:] = [sharper]
    asked = service.copies.search_in
    hanging = threading.Event()
    queries: dict[str, list[str]] = {}

    def search_in(key: str, query: str, n: int) -> list[Any]:
        queries.setdefault(key, []).append(query)
        if key == "openverse":
            hanging.wait(30)  # as Openverse, a minute for one search
            service.importer.remember([late])
            return [late]
        return list(asked(key, query, n))

    service.copies.sources = lambda: ["wmc", "openverse", "paris"]
    service.copies.search_in = search_in
    service.copies.answer = 0.5
    try:
        started = time.monotonic()
        lines = _lines(client, own.id)
        assert time.monotonic() - started < 10
    finally:
        hanging.set()
    sources = {line["source"]: line for line in lines if line["kind"] == "source"}
    assert sources["openverse"]["failed"] and not sources["wmc"]["failed"]
    assert lines[-1]["kind"] == "end"
    assert set(_final(lines)) == {own.id, "wmc:1"}  # the others' copies are judged
    assert _final(lines)["wmc:1"]["verdict"] == "better"
    # Paris Musées looks for the whole query in titles: only the title is asked.
    assert queries["paris"] == [own.title]
    assert queries["wmc"] == [f"{own.title} {surname(own.artist)}"]

    # Openverse answered after all: the next look has its copy at once.
    for _ in range(100):
        if any(key == "openverse" for key, _ in service.copies._answers):
            break
        time.sleep(0.05)
    lines = _lines(client, own.id)
    sources = {line["source"]: line for line in lines if line["kind"] == "source"}
    assert not sources["openverse"]["failed"] and sources["openverse"]["found"] == 1
    assert "wmc:6" in _final(lines)
    assert len(queries["openverse"]) == 1 and len(queries["wmc"]) == 1  # kept, not asked again


def test_the_sources_are_asked_at_once_while_the_app_is_in_use(app: Any) -> None:
    """The look's own threads asked as the background, which waits while
    the app is in use: every museum stayed silent, the sheet stopped at
    the three sources kept at home (2026-11-07, 3 of 20)."""
    client, service, web, hits = app
    own = _own(service)
    painting = _print(1, (3600, 2400))
    sharper = _copy(1)
    _offer(web, sharper, painting)
    hits[:] = [sharper]
    asked = service.copies.search_in
    service.copies.sources = lambda: ["wmc", "aic"]
    service.copies.answer = 5.0

    def search_in(key: str, query: str, n: int) -> list[Any]:
        hosts.guard.wait_calm("api.artic.edu")  # as a museum's request does
        return list(asked(key, query, n)) if key == "wmc" else []

    service.copies.search_in = search_in
    in_use, calm = hosts.guard.app_in_use, hosts.guard.calm_until
    hosts.guard.app_in_use = lambda: True
    hosts.guard.calm_until = hosts.guard.clock() + 600
    try:
        started = time.monotonic()
        lines = _lines(client, own.id)
        assert time.monotonic() - started < 4
    finally:
        hosts.guard.app_in_use, hosts.guard.calm_until = in_use, calm
    sources = {line["source"]: line for line in lines if line["kind"] == "source"}
    assert not sources["wmc"]["failed"] and not sources["aic"]["failed"]
    assert _final(lines)["wmc:1"]["verdict"] == "better"


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


#: The thumbnail of a copy in its frame (4400 × 3200), give or take rounding.
FRAMED = [(640, 465), (640, 466)]


def _thumb_size(client: TestClient, item_id: str) -> tuple[int, int]:
    resp = client.get(f"/api/library/items/{item_id}/thumb")
    assert resp.status_code == 200
    with Image.open(io.BytesIO(resp.content)) as img:
        return img.size


def test_the_thumbnail_and_colours_follow_the_picked_copy(app: Any) -> None:
    """The thumbnail from before showed the old picture in every list, in
    other tones or without the frame round it (Mateusz, 2026-11-04)."""
    client, service, web, _ = app
    own = _own(service)
    service.importer.measure_again(own)  # the colours of the work's own
    assert _thumb_size(client, own.id) == (600, 400)
    before = service.library.get(own.id)
    assert before is not None and before.colors
    # A copy in its frame, a dark brown round it: another shape, other colours.
    framed = ImageOps.expand(_print(1, (3600, 2400)), border=400, fill=(70, 45, 20))
    copy = _copy(9)
    _offer(web, copy, framed)
    service.importer.remember([copy])

    client.put(f"/api/library/items/{own.id}/copy", json={"item_id": "wmc:9"})
    assert _thumb_size(client, own.id) in FRAMED  # the copy's, frame and all
    after = service.library.get(own.id)
    assert after is not None and after.sharper is not None
    assert after.sharper.thumb_url == copy.thumb_url
    assert after.colors != before.colors
    page = client.get("/api/library/items", params={"q": "Nymphs"}).json()
    assert [i["picture"] for i in page["items"] if i["id"] == own.id] == ["wmc:9"]

    # Had again from the copy's own small picture once dropped (pruned).
    service.images.thumb_path(after).unlink()
    service.images.image_path(after).unlink()
    assert _thumb_size(client, own.id) == (600, 436)

    # Back to the work's own: its thumbnail and colours come back.
    client.put(f"/api/library/items/{own.id}/copy", json={"item_id": own.id})
    assert _thumb_size(client, own.id) == (600, 400)
    back = service.library.get(own.id)
    assert back is not None and back.colors == before.colors
    page = client.get("/api/library/items", params={"q": "Nymphs"}).json()
    assert [i["picture"] for i in page["items"] if i["id"] == own.id] == [""]


def test_thumbnails_kept_from_before_follow_their_copies_once(app: Any) -> None:
    client, service, web, _ = app
    own = _own(service)
    copy = _copy(9)
    framed = ImageOps.expand(_print(1, (3600, 2400)), border=400, fill=(70, 45, 20))
    _offer(web, copy, framed)
    service.importer.remember([copy])
    client.put(f"/api/library/items/{own.id}/copy", json={"item_id": "wmc:9"})
    stored = service.library.get(own.id)
    assert stored is not None
    # As a release before left it: the old thumbnail beside the copy.
    service.images.thumb_path(stored).write_bytes(web[OWN_THUMB])
    service.library.set_state("copy_thumbs", 0)
    assert service.sharper.thumbs_again() == 1
    assert _thumb_size(client, own.id) in FRAMED
    assert service.sharper.thumbs_again() == 0  # once


def test_a_copy_that_does_not_fit_can_be_picked_all_the_same(app: Any) -> None:
    client, service, web, _ = app
    own = _own(service)
    other = _copy(4, title="Ville-d'Avray")
    _offer(web, other, _print(7, (3600, 2400)))
    service.importer.remember([other])
    # Shown side by side at the same place, though not laid over the work.
    spot = client.get(f"/api/library/items/{own.id}/copies/wmc:4/spot")
    assert spot.status_code == 200 and spot.json()["copy"]
    # The owner has seen it and decides.
    resp = client.put(f"/api/library/items/{own.id}/copy", json={"item_id": "wmc:4"})
    assert resp.status_code == 200 and resp.json()["sharper"]["item_id"] == "wmc:4"
    assert (
        client.put(f"/api/library/items/{own.id}/copy", json={"item_id": "xx:1"}).status_code == 404
    )


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


def test_an_aic_work_kept_at_1686_offers_its_download_size(app: Any) -> None:
    """Kept at the API's 1686 px before the website's download size was
    asked (Mateusz 2026-11-05): the list offers the museum's own larger file,
    and picking it downloads it again in place of the small one."""
    client, service, web, _ = app
    own = _own(service)
    client.get(f"/api/library/items/{own.id}/image")  # kept at 1686, as before
    large = "https://www.artic.edu/iiif/2/abc/full/!3000,3000/0/default.jpg"
    stored = service.library.update(own.id, image_url=large, width=2975, height=1983)
    assert stored is not None
    web[large] = _jpeg(_print(1, (2975, 1983)), 85)

    copies = _final(_lines(client, own.id))
    larger = copies[own.id + "~larger"]
    assert larger["role"] == "larger" and larger["verdict"] == "better"
    assert (larger["width"], larger["height"]) == (2975, 1983)
    assert larger["gain"] == round(2560 / 1686, 2)
    assert larger["notes"] == ["whole", "colours", "larger"]

    spot = client.get(f"/api/library/items/{own.id}/copies/{own.id}~larger/spot")
    assert spot.status_code == 200

    item = client.put(f"/api/library/items/{own.id}/copy", json={"item_id": own.id + "~larger"})
    assert item.status_code == 200 and item.json()["sharper"] is None
    with Image.open(service.images.image_path(service.library.get(own.id))) as img:
        assert max(img.size) == 2560
    assert service.images.source_size(service.library.get(own.id))[:2] == (2975, 1983)
    # Kept large now: not offered again.
    assert own.id + "~larger" not in _final(_lines(client, own.id))
