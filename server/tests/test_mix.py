"""Rows of Odkrywaj in a mixed order: painters, museums and kinds take
turns."""

from __future__ import annotations

import itertools

from frame_server.library import Item
from frame_server.library.mix import mixed


def _work(n: int, artist: str, museum: str = "", kind: str = "Painting") -> Item:
    return Item(
        id=f"t:{n}",
        source="t",
        source_id=str(n),
        artist=artist,
        museum=museum or f"Museum of {artist}",
        classification=kind,
    )


def _side_by_side(items: list[Item], key: str) -> int:
    return sum(getattr(a, key) == getattr(b, key) for a, b in itertools.pairwise(items))


def test_one_painters_works_do_not_stand_side_by_side() -> None:
    works = [_work(n, "Strzemiński") for n in range(6)] + [
        _work(10 + n, "Witkacy") for n in range(6)
    ]
    out = mixed(works)
    assert sorted(w.id for w in out) == sorted(w.id for w in works)
    assert _side_by_side(out, "artist") == 0


def test_one_museums_works_take_turns_with_others() -> None:
    chicago = [_work(n, f"Painter {n}", "Art Institute of Chicago") for n in range(5)]
    met = [_work(10 + n, f"Artist {n}", "The Met") for n in range(5)]
    assert _side_by_side(mixed(chicago + met), "museum") == 0


def test_kinds_take_turns_and_the_order_is_kept_where_it_can_be() -> None:
    works = [
        _work(1, "A", kind="Print"),
        _work(2, "B", kind="Print"),
        _work(3, "C"),
        _work(4, "D"),
    ]
    assert [w.id for w in mixed(works)] == ["t:1", "t:3", "t:2", "t:4"]
    varied = [_work(n, f"P{n}") for n in range(5)]
    assert mixed(varied)[0].id == "t:0"
