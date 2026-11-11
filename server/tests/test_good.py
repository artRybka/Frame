"""Where the server proposes works, the good ones come first, by many hands,
others each day (Mateusz 2026-11-11: "Dzieła w Odkrywaj mają być po prostu
dobre"; until then a theme's highlights and its artists from A to Z)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from frame_server.library import (
    Item,
    ItemKind,
    Library,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    good,
)
from frame_server.library.models import SharperCopy


def _work(item_id: str, **fields: Any) -> Item:
    fields.setdefault("kind", ItemKind.ARTWORK)
    fields.setdefault("title", f"Work {item_id}")
    source, _, source_id = item_id.partition(":")
    return Item(id=item_id, source=source, source_id=source_id, **fields)


def test_what_a_work_is_worth() -> None:
    plain = _work("met:1", artist="Jan Matejko")
    assert good.worth(_work("met:2", artist="Jan Matejko", highlight=True)) > good.worth(plain)
    assert good.worth(plain) > good.worth(_work("met:3", artist="Unknown"))
    assert good.worth(plain) > good.worth(_work("met:4", artist="Roman, 1st century"))
    assert good.worth(_work("met:5", artist="Jan Matejko", description="x" * 200)) > good.worth(
        plain
    )
    assert good.worth(_work("met:6", artist="Jan Matejko", title="Study of a horse")) < good.worth(
        plain
    )
    # A museum's highlight by nobody known is still before a named work.
    assert good.worth(_work("met:7", artist="Unknown", highlight=True)) > good.worth(plain)


def test_the_copy_counts_only_where_its_size_is_known() -> None:
    # The Met says no size: its 600 px is its thumbnail's.
    assert good.copy_quality(_work("met:1", width=600, height=400)) == 0.0
    assert good.copy_quality(_work("aic:1", width=3000, height=2000)) == good.SHARP_BONUS
    assert good.copy_quality(_work("aic:2", width=1200, height=800)) == -good.WEAK_PENALTY
    copy = SharperCopy(
        item_id="wmc:9", source="wmc", url="https://example.org/a.jpg", width=4000, height=3000
    )
    assert good.copy_quality(_work("met:2", sharper=copy)) == good.SHARP_BONUS


def test_one_artists_works_stand_among_the_others() -> None:
    many = [_work(f"met:{n}", artist="Jacek Malczewski") for n in range(20)]
    others = [_work(f"mnk:{n}", artist=f"Painter Number{chr(65 + n)}") for n in range(7)]
    order = good.good_first([*many, *others], seed=1)
    # His fifth work is worth less than any other painter's only one.
    assert {i.id for i in others} <= {i.id for i in order[:11]}
    assert sum(i.artist == "Jacek Malczewski" for i in order[:11]) == 4
    assert len(order) == 27 and {i.id for i in order} == {i.id for i in [*many, *others]}


def test_spellings_of_one_artist_are_one_hand() -> None:
    spelled = [
        _work(f"met:{n}", artist=name)
        for n, name in enumerate(["Jan van Eyck", "Jan Van Eyck", "Eyck, Jan van"] * 4)
    ]
    others = [_work(f"mnk:{n}", artist=f"Painter Number{chr(65 + n)}") for n in range(7)]
    order = good.good_first([*spelled, *others], seed=1)
    assert {i.id for i in others} <= {i.id for i in order[:11]}


def test_the_nameless_are_one_hand_behind_the_named() -> None:
    nameless = [_work(f"met:{n}", artist=["Unknown", "Roman", ""][n % 3]) for n in range(12)]
    named = [_work(f"mnk:{n}", artist=f"Painter Number{chr(65 + n)}") for n in range(6)]
    order = good.good_first([*nameless, *named], seed=3)
    assert {i.id for i in order[:6]} == {i.id for i in named}


def test_no_museum_has_the_whole_first_page() -> None:
    # One museum writes about its works, so each of its is worth a little
    # more: it had 23 of the 24 first "Arcydzieła muzeów".
    wordy = [
        _work(f"cma:{n}", artist=f"Painter Wordy{n}", highlight=True, description="x" * 300)
        for n in range(60)
    ]
    silent = [_work(f"met:{n}", artist=f"Painter Silent{n}", highlight=True) for n in range(60)]
    order = good.good_first([*wordy, *silent], seed=5)
    first = [i.source for i in order[:24]]
    assert 6 <= first.count("met") <= 14


def test_each_day_another_order_and_the_same_all_day() -> None:
    works = [_work(f"met:{n}", artist=f"Painter Number{n}") for n in range(60)]
    today = [i.id for i in good.good_first(works, seed=100)]
    assert today == [i.id for i in good.good_first(list(reversed(works)), seed=100)]
    tomorrow = [i.id for i in good.good_first(works, seed=101)]
    assert today != tomorrow and sorted(today) == sorted(tomorrow)
    # A work lucky in one theme is not lucky in all.
    assert today != [i.id for i in good.good_first(works, seed=100, salt="another theme")]
    # A highlight is still mostly first: the draw is worth half of one.
    starred = [*works, _work("met:star", artist="Painter Star", highlight=True)]
    assert all(good.good_first(starred, seed=day)[0].id == "met:star" for day in range(20))


def test_what_fits_better_comes_before_what_is_better(tmp_path: Path) -> None:
    library = Library(tmp_path / "library.db")
    with library.batch():
        for n in range(6):
            library.upsert(
                _work(f"met:{n}", title=f"View {n}", artist="Johannes Vermeer", pooled=True)
            )
        # A highlight that only names him: found, and after his own works.
        library.upsert(
            _work(
                "met:after",
                title="The Lacemaker, after Johannes Vermeer",
                artist="Somebody Else",
                highlight=True,
                pooled=True,
            )
        )
    rules = PlaylistRules(query="vermeer")
    total, items = library.query(rules, sort="good", seed=7, proposing=True)
    assert total == 7 and items[-1].id == "met:after"
    # Kept for the day, and another day's is another answer.
    assert library.query(rules, sort="good", seed=7, proposing=True)[1] == items
    days = {tuple(i.id for i in library.query(rules, sort="good", seed=d)[1]) for d in range(12)}
    assert len(days) > 1
    library.close()


def test_a_playlists_cover_is_its_best_works(tmp_path: Path) -> None:
    library = Library(tmp_path / "library.db")
    with library.batch():
        ids = [
            library.upsert(
                _work(
                    f"met:{n}",
                    artist=f"Painter Number{n}",
                    highlight=n >= 6,
                )
            ).id
            for n in range(8)
        ]
    playlist = library.save_playlist(Playlist(name="Mine", kind=PlaylistKind.MANUAL, item_ids=ids))
    summary = library.playlist_summary(playlist)
    assert summary.cover_item_ids[:2] == ["met:6", "met:7"]
    library.close()
