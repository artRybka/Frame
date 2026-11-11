"""A work's details on its card (Library.details, GET .../details; Mateusz
2026-11-11): pictures of a part of the work, kept apart from the catalogue
as copies, shown with the work."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.library import Item, Library
from frame_server.service import FrameService
from frame_server.web.app import create_app


def _item(item_id: str, title: str, **fields: Any) -> Item:
    source, _, source_id = item_id.partition(":")
    return Item(
        id=item_id,
        source=source,
        source_id=source_id,
        title=title,
        artist="Rembrandt van Rijn",
        **fields,
    )


WHOLE = _item("rijks:1", "The Night Watch", favorite=True)


def _library(tmp_path: Path) -> Library:
    lib = Library(tmp_path / "lib.db")
    for item in (
        WHOLE,
        # Another copy of the work, and a detail found inside it.
        _item("wikiart:3", "De Nachtwacht", copy_of="rijks:1"),
        _item("wmc:4", "Kapitein Frans Banninck Cocq", detail_of="wikiart:3"),
        # Found inside the museum's own picture, twice the same picture.
        _item("wmc:2", "Night Watch, the drummer", detail_of="rijks:1", picture_hash="ab"),
        _item("wmc:7", "Nachtwacht trommelaar", detail_of="rijks:1", picture_hash="ab"),
        # Its title says it: a copy of the work by title, and a detail.
        _item("wmc:5", "The Night Watch - detail"),
        # Hidden in the app, and one that is also a postcard.
        _item("wmc:6", "Night Watch hand", detail_of="rijks:1", excluded=True),
        _item("wmc:8", "Night Watch shield", detail_of="rijks:1", seen_as="postal"),
        # Another work's.
        _item("rijks:9", "The Syndics", favorite=True),
        _item("wmc:10", "Syndics hat", detail_of="rijks:9"),
    ):
        lib.upsert(item)
    return lib


def test_details_of_a_work_and_of_its_copies(tmp_path: Path) -> None:
    lib = _library(tmp_path)
    found = {i.id for i in lib.details(WHOLE)}
    assert found == {"wmc:2", "wmc:4", "wmc:5"}
    # The same from the card of another copy.
    copy = lib.get("wikiart:3")
    assert copy is not None
    assert {i.id for i in lib.details(copy)} == found


def test_a_detail_names_its_whole_work(tmp_path: Path) -> None:
    lib = _library(tmp_path)
    detail = lib.get("wmc:4")
    assert detail is not None
    whole = lib.whole_of(detail)
    assert whole is not None and whole.id == "rijks:1"
    assert lib.whole_of(WHOLE) is None


def test_a_work_with_no_details_has_none(tmp_path: Path) -> None:
    lib = _library(tmp_path)
    lib.upsert(_item("rijks:11", "Self-portrait", favorite=True))
    item = lib.get("rijks:11")
    assert item is not None
    assert lib.details(item) == []


def test_details_follow_the_pictures_found_later(tmp_path: Path) -> None:
    lib = _library(tmp_path)
    lib.update("wmc:10", detail_of="rijks:1")
    assert "wmc:10" in {i.id for i in lib.details(WHOLE)}


def test_card_asks_for_details(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        # After the start's tidying, which leaves out works nobody keeps.
        svc.library.upsert(WHOLE)
        drummer = _item("wmc:2", "Night Watch drummer", detail_of="rijks:1", favorite=True)
        svc.library.upsert(drummer)
        view = client.get("/api/library/items/rijks:1/details").json()
        assert [d["item"]["id"] for d in view["details"]] == ["wmc:2"]
        assert view["whole"] is None
        back = client.get("/api/library/items/wmc:2/details").json()
        assert back["whole"]["item"]["id"] == "rijks:1"
        assert back["details"] == []
        # Another detail's card: the whole work, and the other details.
        hand = _item("wmc:3", "Night Watch hand", detail_of="rijks:1", favorite=True)
        svc.library.upsert(hand)
        other = client.get("/api/library/items/wmc:3/details").json()
        assert other["whole"]["item"]["id"] == "rijks:1"
        assert [d["item"]["id"] for d in other["details"]] == ["wmc:2"]
