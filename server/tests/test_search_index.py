"""The catalogue's search index answers as looking at every work did, only
in a moment (Mateusz 2026-11-09: "to co mamy w katalogu musi się wyszukiwać
błyskawicznie"), and Szukaj shows the best fits first and all of them."""

from __future__ import annotations

import random
import threading

import pytest

from frame_server.library import Item, Library
from frame_server.library import repo as repo_module
from frame_server.library.models import PlaylistRules
from frame_server.library.repo import has_words

ARTISTS = [
    "Johannes Vermeer",
    "Vermeer, Johannes",
    "Jan Vermeer van Haarlem",
    "Rembrandt van Rijn",
    "Rembrandt (Rembrandt van Rijn)",
    "Pupil of Rembrandt",
    "Claude Monet",
    "Katsushika Hokusai",
    "Józef Chełmoński",
    "",
]
WORDS = [
    "landscape",
    "Landscapes",
    "still life",
    "martwa natura",
    "żółw",
    "Stuttgart",
    "art",
    "pre-raphaelite",
    "night watch",
    "nocnej straży",
    "fala",
    "wielka fala",
    "sea",
    "seascape",
    "portrait",
    "Vermeer",
    "Delft",
    "góra fuji",
]
RULES = [
    PlaylistRules(query="vermeer"),
    PlaylistRules(query="art"),
    PlaylistRules(query="zolw"),
    PlaylistRules(query="żółw"),
    PlaylistRules(query="pre-rap"),
    PlaylistRules(query='"still life"'),
    PlaylistRules(query='"nocna straż"'),
    PlaylistRules(query='"wielka fala" sea'),
    PlaylistRules(query="-"),
    PlaylistRules(query="ea"),
    PlaylistRules(artists=["Johannes Vermeer"]),
    PlaylistRules(artists=["Rembrandt van Rijn"]),
    PlaylistRules(artists=["Rembrandt"]),
    PlaylistRules(artists=["Hokusai"]),
    PlaylistRules(artists=["Józef Chełmoński", "Claude Monet"]),
    PlaylistRules(terms=["subject:landscape"]),
    PlaylistRules(terms=["subject:still-life"]),
    PlaylistRules(terms=["subject:landscape", "subject:still-life"]),
    PlaylistRules(terms=["style:baroque"]),
    PlaylistRules(terms=["style:impressionism", "subject:landscape"]),
    PlaylistRules(terms=["style:impressionism", "style:unknown-one"]),
    PlaylistRules(terms=["years:1600-1700"]),
    PlaylistRules(terms=["tag:highlight"]),
    PlaylistRules(year_from=1650, year_to=1700),
    PlaylistRules(sources=["met"]),
    PlaylistRules(query="sea", sources=["aic", "rijks"], year_from=1800),
    PlaylistRules(query="landscape", artists=["Claude Monet"]),
    PlaylistRules(favorites_only=True),
    PlaylistRules(favorites_only=True, query="sea"),
    PlaylistRules(terms=["mine:favorites"], query="art"),
    PlaylistRules(),
]


def _catalogue(lib: Library, n: int, seed: int = 3) -> random.Random:
    rng = random.Random(seed)
    for k in range(n):
        source = rng.choice(["met", "aic", "rijks", "commons"])
        lib.upsert(
            Item(
                id=f"{source}:{k}",
                source=source,
                source_id=str(k),
                title=" ".join(rng.sample(WORDS, rng.randint(1, 3))).capitalize(),
                artist=rng.choice(ARTISTS),
                year=rng.choice([None, 1500, 1640, 1665, 1700, 1820, 1880, 1905]),
                description=" ".join(rng.sample(WORDS, rng.randint(0, 4))),
                keywords=rng.sample(WORDS, rng.randint(0, 2)),
                highlight=rng.random() < 0.2,
                found_for=["q:vermeer"] if rng.random() < 0.05 else [],
                terms=["subject:landscape"] if rng.random() < 0.05 else [],
            )
        )
    return rng


def _scanned(lib: Library, rules: PlaylistRules) -> list[str]:
    """What looking at every work finds (the index switched off)."""
    index, lib._search = lib._search, None
    real = lib.search_index
    lib.search_index = lambda wait=True: None  # type: ignore[method-assign]
    lib._queries.clear()
    try:
        return sorted(i.id for i in lib.query(rules)[1])
    finally:
        lib.search_index = real  # type: ignore[method-assign]
        lib._search = index
        lib._queries.clear()


def _indexed(lib: Library, rules: PlaylistRules) -> list[str]:
    lib._queries.clear()
    assert lib.search_index() is not None
    return sorted(i.id for i in lib.query(rules)[1])


def test_the_index_finds_what_looking_at_every_work_finds(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    rng = _catalogue(lib, 400)
    for k in rng.sample(range(400), 30):
        item_id = next(i.id for i in lib.all_items() if i.source_id == str(k))
        lib.set_favorite("owner", item_id, True)
    for rules in RULES:
        assert _indexed(lib, rules) == _scanned(lib, rules), rules
    # Changed, added and taken out after the index was made, and asked again.
    for item in rng.sample(lib.all_items(), 40):
        lib.update(item.id, title="A seascape by Vermeer", artist=rng.choice(ARTISTS))
    for item in rng.sample(lib.all_items(), 20):
        lib.delete(item.id)
    _catalogue(lib, 60, seed=9)
    for rules in RULES:
        assert _indexed(lib, rules) == _scanned(lib, rules), rules


def test_words_are_found_at_a_word_start_whatever_their_accents() -> None:
    item = Item(
        id="x:1", source="x", source_id="1", title="Żółw in Stuttgart", artist="Ann Pre-Raphael"
    )
    assert has_words(item, "zolw")
    assert has_words(item, "ŻÓŁW")
    assert has_words(item, "stutt")
    assert not has_words(item, "art")  # inside "Stuttgart": no longer
    assert has_words(item, "pre-raph")
    assert not has_words(item, "olw")


def test_a_search_shows_the_artists_own_works_first_and_all_of_them(tmp_path) -> None:
    """Mateusz, 2026-11-09: Vermeer's works first, then works that only
    mention him; and the catalogue's every work, not the first 60."""
    lib = Library(tmp_path / "lib.db")
    lib.upsert(Item(id="a:1", source="a", source_id="1", title="Vermeer's studio, a copy"))
    lib.upsert(
        Item(id="a:2", source="a", source_id="2", title="View of Delft", artist="Johannes Vermeer")
    )
    lib.upsert(
        Item(id="a:3", source="a", source_id="3", title="Sea", description="after Vermeer")
    )
    lib.upsert(
        Item(
            id="a:4",
            source="a",
            source_id="4",
            title="The Milkmaid",
            artist="Johannes Vermeer",
            highlight=True,
        )
    )
    for n in range(5, 125):
        lib.upsert(Item(id=f"a:{n}", source="a", source_id=str(n), title=f"Vermeer study {n}"))
    total, first = lib.query(PlaylistRules(query="vermeer"), sort="relevance", limit=60)
    assert total == 124
    assert [i.id for i in first[:2]] == ["a:4", "a:2"]  # his, the highlight first
    assert first[2].id != "a:3"  # in the title before only in the description
    _, last = lib.query(PlaylistRules(query="vermeer"), sort="relevance", offset=120, limit=60)
    assert len(last) == 4 and last[-1].id == "a:3"
    # The old apps' "suitability" is relevance for a search.
    assert lib.query(PlaylistRules(query="vermeer"), sort="suitability", limit=2)[1] == first[:2]


def test_the_index_is_made_outside_the_lock_with_the_changes_made_meanwhile(
    tmp_path, monkeypatch
) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(3):
        lib.upsert(Item(id=f"a:{n}", source="a", source_id=str(n), title=f"Sea {n}"))
    making, go_on = threading.Event(), threading.Event()
    real = repo_module.SearchIndex

    def slow(items):  # type: ignore[no-untyped-def]
        items = list(items)
        making.set()
        go_on.wait(5)
        return real(items)

    monkeypatch.setattr(repo_module, "SearchIndex", slow)
    maker = threading.Thread(target=lib.search_index)
    maker.start()
    assert making.wait(5)
    lib.upsert(Item(id="a:9", source="a", source_id="9", title="Sea 9"))
    lib.delete("a:0")
    lib.update("a:1", title="Field")
    go_on.set()
    maker.join(5)
    assert lib._search is not None
    assert sorted(i.id for i in lib.query(PlaylistRules(query="sea"))[1]) == ["a:2", "a:9"]


@pytest.mark.parametrize("dead", [0.5])
def test_an_index_mostly_changed_is_made_anew(tmp_path, dead: float) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(10):
        lib.upsert(Item(id=f"a:{n}", source="a", source_id=str(n), title="Sea"))
    first = lib.search_index()
    for n in range(10):
        lib.update(f"a:{n}", title="Field")
    assert first is not None and first.dead_share() >= dead
    for _ in range(500):
        if lib._search is not first:
            break
        threading.Event().wait(0.01)
    assert lib._search is not first
    assert lib.query(PlaylistRules(query="field"))[0] == 10
