"""The Met's object records asked once (2026-11-07: its bot wall turned the
home address away; a page of its search is a request a work)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from frame_server.library.hosts import LIMITS
from frame_server.library.met_objects import KEEP_DAYS, MetObjects, met_objects
from frame_server.library.museums import Access, MetropolitanMuseum


def _record(object_id: int, **changes: Any) -> dict[str, Any]:
    return {
        "objectID": object_id,
        "isPublicDomain": True,
        "primaryImage": f"https://images.metmuseum.org/{object_id}.jpg",
        "primaryImageSmall": f"https://images.metmuseum.org/{object_id}s.jpg",
        "title": "Wheat Field with Cypresses",
        "artistDisplayName": "Vincent van Gogh",
        "objectBeginDate": 1889,
        "classification": "Paintings",
        "constituents": [{"name": "Vincent van Gogh"}],  # not kept
        **changes,
    }


def test_each_work_is_asked_once(tmp_path: Path) -> None:
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"total": 3, "objectIDs": [1, 2, 3]})
        object_id = int(request.url.path.rsplit("/", 1)[1])
        if object_id == 3:
            return httpx.Response(404)
        return httpx.Response(200, json=_record(object_id))

    access = Access(data_dir=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        met = MetropolitanMuseum(http, access=access)
        total, items = met.search("cypresses")
        assert total == 3 and [i.id for i in items] == ["met:1", "met:2"]
        assert len(asked) == 4
        asked.clear()
        again = met.search("cypresses")[1]
        assert again == items
        assert asked == ["/public/collection/v1.1/search"]  # the works from disk
        assert met.fetch("3") is None and len(asked) == 1  # gone, remembered
    kept = met_objects(tmp_path)
    found, record = kept.get("1")
    assert found and record is not None and "constituents" not in record
    assert len(kept) == 3


def test_records_grow_old(tmp_path: Path) -> None:
    kept = MetObjects(tmp_path / "objects.sqlite")
    kept.put("7", _record(7), now=1000.0)
    assert kept.get("7", now=1000.0 + 86400)[0]
    assert kept.get("7", now=1000.0 + (KEEP_DAYS + 1) * 86400) == (False, None)
    assert kept.get("8") == (False, None)


def test_without_a_data_folder_nothing_is_kept() -> None:
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(200, json=_record(1))

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        met = MetropolitanMuseum(http)
        assert met.fetch("1") is not None and met.fetch("1") is not None
    assert len(asked) == 2


def test_the_met_is_asked_one_request_at_a_time() -> None:
    assert LIMITS["collectionapi.metmuseum.org"] == 1
