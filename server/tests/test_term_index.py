"""The suggestions' index counts what the catalogue's search finds."""

from __future__ import annotations

import random
import time
from types import SimpleNamespace

from frame_server.library import Item, ItemKind, PlaylistRules
from frame_server.library import repo as repo_module
from frame_server.library.repo import Library
from frame_server.library.vocabulary import TERMS
from frame_server.web.discover_api import _term_hits

WORDS = [
    "sea",
    "seascape",
    "boats",
    "harbour",
    "portrait",
    "woman",
    "women",
    "seated",
    "still",
    "life",
    "flowers",
    "garden",
    "mountain",
    "snow",
    "night",
    "city",
    "street",
    "horse",
    "birds",
    "landscape",
    "river",
    "ukiyo-e",
    "woodblock",
    "impressionist",
    "nocturne",
    "madonna",
    "angel",
    "saint",
    "ship",
    "o'keeffe",
    "pre-raphaelite",
]
ARTISTS = ["Edward Hopper", "Claude Monet", "Katsushika Hokusai", "Unknown", "Jan Matejko"]


def _catalogue(lib: Library, n: int = 160) -> None:
    rnd = random.Random(7)
    for i in range(n):
        source = ("aic", "met", "europeana", "rijks")[i % 4]
        lib.upsert(
            Item(
                id=f"{source}:{i}",
                source=source,
                source_id=str(i),
                # Every fifth one a copy of another's work (same title and artist).
                title="Nighthawks" if i % 5 == 0 else " ".join(rnd.sample(WORDS, 3)).title(),
                artist=rnd.choice(ARTISTS),
                year=rnd.randint(1500, 1950),
                medium=rnd.choice(["Oil on canvas", "Woodblock print", "Albumen print", ""]),
                classification=rnd.choice(["Painting", "Print", "Photograph", "Sculpture", ""]),
                styles=rnd.sample(["Impressionism", "Ukiyo-e", "Baroque", "Realism"], 1),
                subjects=rnd.sample(WORDS, 2),
                description=" ".join(rnd.choices(WORDS, k=12)),
                keywords=rnd.sample(WORDS, 2),
                terms=["subject:sea"] if i % 11 == 0 else [],
                pooled=i % 3 == 0,
                excluded=i % 17 == 0,
                highlight=i % 13 == 0,
                kind=ItemKind.ARTWORK if i % 23 else ItemKind.PHOTO,
            )
        )


def test_counts_agree_with_the_catalogue(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    _catalogue(lib)
    index = lib.term_index()
    for found in TERMS:
        expected = lib.query(PlaylistRules(terms=[found.key]))[0]
        assert index.term_count(found.key) == expected, found.key
    for words in ["sea", "SEA", "hopper", "o'keeffe", "still life", "ea", "pre-rap", "-", "zzz"]:
        expected = lib.query(PlaylistRules(query=words))[0]
        assert index.word_count(words) == expected, words
    hopper = dict(index.artists("hop"))
    assert list(hopper) == ["Edward Hopper"]
    assert hopper["Edward Hopper"] == lib.query(PlaylistRules(artists=["Edward Hopper"]))[0]
    assert "Unknown" not in dict(index.artists("unk"))


def test_a_changed_catalogue_is_counted_again_in_the_background(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(repo_module, "TERM_INDEX_EVERY", 0.0)
    lib = Library(tmp_path / "lib.db")
    _catalogue(lib, 20)
    before = lib.term_index()
    lib.upsert(Item(id="aic:999", source="aic", source_id="999", title="Rain at sea"))
    # The old index answers at once; a new one follows.
    assert lib.term_index() is before
    for _ in range(200):
        if lib.term_index() is not before:
            break
        time.sleep(0.01)
    after = lib.term_index()
    assert after is not before
    assert after.word_count("rain") == before.word_count("rain") + 1


def test_keywords_and_subjects_are_suggested(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    wave = {"title": "Under the Wave off Kanagawa", "artist": "Katsushika Hokusai"}
    lib.upsert(
        Item(id="met:1", source="met", source_id="1", keywords=["wielka fala", "góra fuji"], **wave)
    )
    lib.upsert(
        Item(
            id="aic:2",
            source="aic",
            source_id="2",
            title="Red Fuji",
            keywords=["góra fuji", "niebo"],
            subjects=["Mount Fuji"],
        )
    )
    lib.upsert(Item(id="aic:3", source="aic", source_id="3", title="Waves", keywords=["fala"]))
    index = lib.term_index()
    # Phrases starting so first, then those with a word starting so; the commonest first.
    assert index.phrases("fuj") == ["góra fuji", "Mount Fuji"]
    assert index.phrases("gora") == ["góra fuji"]
    assert index.phrases("wielka f") == ["wielka fala"]
    assert index.phrases("fal") == ["fala", "wielka fala"]
    assert index.phrases("fala") == ["wielka fala"]  # "fala" itself is the typed words' row
    assert index.phrases("f") == []

    # In /api/terms: words to search by, counted like typed words, before the typed ones.
    hits = _term_hits(SimpleNamespace(library=lib), "fuj", 10)  # type: ignore[arg-type]
    words = [(h.name, h.count) for h in hits if h.kind == "word"]
    assert words == [("góra fuji", 2), ("Mount Fuji", 1), ("fuj", 2)]
    assert hits[0].name == "góra fuji" and hits[-1].name == "fuj"
