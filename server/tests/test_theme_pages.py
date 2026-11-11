"""Odkrywaj sets open at once: the catalogue's page of a set as last worked
out, ahead of the museums (Mateusz 2026-11-06: ~10 s to the first works)."""

from __future__ import annotations

import json
import threading
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from frame_server.library import Item, ItemKind
from frame_server.library.themes import THEMES, kept_close
from frame_server.library.vocabulary import PER_WORK, _is_manuscript
from frame_server.web import create_app, discover_api


def _work(item_id: str, **fields: Any) -> Item:
    fields.setdefault("kind", ItemKind.ARTWORK)
    source, _, source_id = item_id.partition(":")
    return Item(id=item_id, source=source, source_id=source_id, **fields)


#: A set of painters searched in the museums, not one kept close.
PAINTERS = next(t for t in THEMES if t.artists and t.searches() and not kept_close(t))


def _paintings(service, count: int, start: int = 0) -> list[Item]:
    with service.library.batch():
        return [
            service.library.upsert(
                _work(
                    f"met:{n}",
                    title=f"Painting {n}",
                    artist=PAINTERS.artists[0],
                    classification="Paintings",
                    medium="Oil on canvas",
                    year=1880,
                    suitability=0.5,
                    pooled=True,
                )
            )
            for n in range(start, start + count)
        ]


def test_a_set_comes_as_last_worked_out_and_is_worked_out_again_after(service) -> None:
    _paintings(service, 2)
    items, more = discover_api.catalogue_page(service, PAINTERS)
    assert {i.id for i in items} == {"met:0", "met:1"} and not more

    asked = threading.Event()
    went_on = threading.Event()
    query = service.library.query

    def slow(*args: Any, **kwargs: Any) -> tuple[int, list[Item]]:
        asked.set()
        went_on.wait(5)
        return query(*args, **kwargs)

    _paintings(service, 1, start=2)  # the catalogue changed
    service.library.query = slow  # type: ignore[method-assign]
    try:
        items, _ = discover_api.catalogue_page(service, PAINTERS)
        # At once, as before; the new page is worked out in the background.
        assert {i.id for i in items} == {"met:0", "met:1"}
        assert asked.wait(5)
    finally:
        went_on.set()
        service.library.query = query  # type: ignore[method-assign]
    for _ in range(100):
        items, _ = discover_api.catalogue_page(service, PAINTERS)
        if len(items) == 3:
            break
        threading.Event().wait(0.05)
    assert {i.id for i in items} == {"met:0", "met:1", "met:2"}


def test_a_set_is_worked_out_again_on_another_day(service, monkeypatch) -> None:
    """The good works come in another order each day (``library.good``):
    the page as last worked out comes at once, the day's own for the next
    visit."""

    class Today(date):
        day = date(2026, 11, 12)

        @classmethod
        def today(cls) -> date:
            return cls.day

    monkeypatch.setattr(discover_api, "date", Today)
    _paintings(service, 2)
    discover_api.catalogue_page(service, PAINTERS)
    seeds: list[int] = []
    query = service.library.query

    def asked(*args: Any, **kwargs: Any) -> tuple[int, list[Item]]:
        seeds.append(kwargs["seed"])
        assert kwargs["sort"] == "good"
        return query(*args, **kwargs)

    monkeypatch.setattr(service.library, "query", asked)
    discover_api.catalogue_page(service, PAINTERS)
    assert not seeds  # the same day: as worked out
    Today.day = date(2026, 11, 13)
    items, _ = discover_api.catalogue_page(service, PAINTERS)
    assert {i.id for i in items} == {"met:0", "met:1"}  # at once
    for _ in range(100):
        if seeds:
            break
        threading.Event().wait(0.05)
    assert seeds == [date(2026, 11, 13).toordinal()]
    for _ in range(100):  # the day's page is kept: nothing more to work out
        if not _pages(service).working:
            break
        threading.Event().wait(0.05)
    discover_api.catalogue_page(service, PAINTERS)
    assert len(seeds) == 1


def _pages(service) -> Any:
    return discover_api._pages_of(service.library)


def test_the_cards_work_out_each_sets_first_page(service, monkeypatch) -> None:
    _paintings(service, 2)
    discover_api._cards = (0.0, {})
    discover_api.work_out_cards(service, force=True)

    def unasked(*args: Any, **kwargs: Any) -> tuple[int, list[Item]]:
        raise AssertionError("the page was worked out with the cards")

    monkeypatch.setattr(service.library, "query", unasked)
    items, _ = discover_api.catalogue_page(service, PAINTERS)
    assert {i.id for i in items} == {"met:0", "met:1"}


def test_every_set_opens_with_the_catalogues_works_before_the_museums(service, monkeypatch) -> None:
    _paintings(service, 3)
    found = _work(
        "aic:900",
        title="From the museum",
        artist=PAINTERS.artists[0],
        classification="Painting",
        thumb_url="https://example.org/900.jpg",
    )
    monkeypatch.setattr(service.importer, "search", lambda *a, **k: (1, [found]))
    monkeypatch.setattr(service.importer, "measure", lambda *a, **k: None)
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        reply = client.get(f"/api/themes/{PAINTERS.key}/stream?page=1")
    lines = [json.loads(line) for line in reply.text.splitlines() if line]
    assert {i["item"]["id"] for i in lines[0]["items"]} == {"met:0", "met:1", "met:2"}
    later = {i["item"]["id"] for line in lines[1:] for i in line.get("items") or []}
    assert "aic:900" in later
    assert lines[-1]["end"] and not lines[-1]["failed"]


def test_covers_leave_out_what_the_app_does_not_read(service, monkeypatch) -> None:
    monkeypatch.setattr(discover_api, "CARD_MIN", 0)
    _paintings(service, 1)
    service.library.update("met:0", keywords=["sea", "morze"], terms=["subject:sea"])
    discover_api._cards = (0.0, {})
    cards = discover_api._theme_list(service)
    covers = [r.item for card in cards for r in card.cover if r.item.id == "met:0"]
    assert covers and all(not c.keywords and not c.terms for c in covers)


def test_a_works_texts_are_remembered_for_a_whole_catalogue() -> None:
    # A smaller cache, scanned in order over more works, keeps none of them.
    assert PER_WORK >= 200_000
    assert _is_manuscript.cache_info().maxsize == PER_WORK


def test_cards_with_too_few_works_are_not_shown(service, monkeypatch) -> None:
    # "Pierwsze kolory" with 2 works and two grey squares (Mateusz 2026-11-06).
    two = _paintings(service, 2)
    four = _paintings(service, 4, start=10)
    thin, full = THEMES[0], THEMES[1]
    cards = {thin.key: (2, two), full.key: (4, four)}
    monkeypatch.setattr(discover_api, "_theme_cards", lambda svc: cards)
    keys = [c.key for c in discover_api._theme_list(service)]
    assert keys == [full.key]
    assert discover_api.CARD_MIN == 4
