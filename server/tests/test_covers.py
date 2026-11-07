"""Theme covers stay put while the catalogue grows."""

from __future__ import annotations

from frame_server.library import Item, ItemKind
from frame_server.web import discover_api


def _work(n: int) -> Item:
    return Item(
        id=f"cma:{n}", source="cma", source_id=str(n), kind=ItemKind.ARTWORK, artist=f"A{n}"
    )


def _ids(items: list[Item]) -> list[str]:
    return [i.id for i in items]


def test_a_new_work_changes_a_cover_by_little() -> None:
    seed = "2026-11-07:winter"
    pool = [_work(n) for n in range(100, 100 + discover_api.COVER_POOL)]
    before = _ids(discover_api._cover(pool, seed))
    kept = 0
    for n in range(40):
        # A new, better work comes in at the top; the last one of the pool drops out.
        pool = [_work(n), *pool]
        after = _ids(discover_api._cover(pool, seed))
        assert len(set(after) - set(before)) <= 2
        kept += after == before
        before = after
    assert kept >= 25  # a shuffle of the pool changed nearly every cover


def test_covers_differ_from_day_to_day() -> None:
    pool = [_work(n) for n in range(40)]
    covers = {tuple(_ids(discover_api._cover(pool, f"2026-11-0{d}:x"))) for d in range(1, 8)}
    assert len(covers) > 1
