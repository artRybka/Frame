"""Szukaj by a work's title (Mateusz 2026-11-13: "trzeba jeszcze ogarnąć
szukanie po tytule dzieła"): the titles among the suggestions, and a title
asked finds the works with it in their title, also by their Polish one."""

from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from frame_server.library import Item, ItemKind
from frame_server.library.models import Note, PlaylistRules
from frame_server.service import FrameService


def _work(service: FrameService, n: int, title: str, **fields: object) -> Item:
    return service.library.upsert(
        Item(
            id=f"aic:{n}",
            source="aic",
            source_id=str(n),
            title=title,
            artist=str(fields.pop("artist", "Vincent van Gogh")),
            kind=ItemKind.ARTWORK,
            **fields,  # type: ignore[arg-type]
        )
    )


def test_a_title_is_suggested_and_found_by_itself(service: FrameService) -> None:
    from frame_server.web import create_app

    night = _work(service, 1, "The Starry Night")
    _work(service, 2, "Starry Night over the Rhône")
    _work(service, 3, "Café Terrace", description="Painted under a starry night sky.")
    _work(service, 4, "Słoneczniki", artist="Claude Monet")
    service.library.save_note(
        Note(
            item_id=night.id,
            kind="pl_text",
            model="m",
            prompt_version="x",
            source_hash="h",
            data={"title": "Gwiaździsta noc"},
        )
    )
    library = service.library

    # Only the works with it in their title, not those that mention it.
    found = library.query(PlaylistRules(title="starry night"))[1]
    assert {i.id for i in found} == {"aic:1", "aic:2"}
    words = library.query(PlaylistRules(query='"starry night"'))[1]
    assert "aic:3" in {i.id for i in words}
    # By its Polish title, and with other choices.
    assert [i.id for i in library.query(PlaylistRules(title="Gwiaździsta noc"))[1]] == ["aic:1"]
    assert library.query(PlaylistRules(title="starry night", artists=["Claude Monet"]))[0] == 0

    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        hits = client.get("/api/terms", params={"q": "starry night"}).json()
        titles = [h for h in hits if h["kind"] == "title"]
        assert [h["name"] for h in titles] == ["The Starry Night", "Starry Night over the Rhône"]
        assert titles[0]["exact"] and titles[0]["item"] == "aic:1"
        assert titles[1]["exact"]  # the title starts with the two words
        assert titles[0]["detail"]  # the artist
        polish = client.get("/api/terms", params={"q": "gwiaździsta noc"}).json()
        assert [(h["name"], h["exact"]) for h in polish if h["kind"] == "title"] == [
            ("Gwiaździsta noc", True)
        ]
        partly = client.get("/api/terms", params={"q": "słoneczn"}).json()
        assert [(h["name"], h["exact"]) for h in partly if h["kind"] == "title"] == [
            ("Słoneczniki", False)
        ]
        page = client.get("/api/library/items", params={"title": "Gwiaździsta noc"}).json()
        assert [i["id"] for i in page["items"]] == ["aic:1"]


def test_searches_without_a_title_keep_their_keys() -> None:
    """Works remember the museum searches that found them by this key."""
    rules = PlaylistRules(query="morze", artists=["Monet"])
    asked = ["morze", ["Monet"], [], [], None, None]
    text = json.dumps(asked, ensure_ascii=False)
    assert rules.search_key() == "s:" + hashlib.sha1(text.encode()).hexdigest()[:16]
    assert PlaylistRules(query="morze", title="Fala").search_key() != rules.search_key()
    assert PlaylistRules(title="Fala").search_key()
    assert not PlaylistRules(title="Fala").is_empty()
