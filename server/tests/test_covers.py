"""Theme covers stay put while the catalogue grows."""

from __future__ import annotations

from frame_server.library import Item, ItemKind
from frame_server.library.themes import Theme
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


def _painting(n: int, medium: str = "oil on canvas") -> Item:
    return Item(
        id=f"cma:p{n}",
        source="cma",
        source_id=f"p{n}",
        kind=ItemKind.ARTWORK,
        artist=f"P{n}",
        medium=medium,
    )


def _print(n: int) -> Item:
    return Item(
        id=f"cma:e{n}",
        source="cma",
        source_id=f"e{n}",
        kind=ItemKind.ARTWORK,
        artist=f"E{n}",
        classification="Print",
        medium="etching and aquatint",
    )


def _theme(**kw: object) -> Theme:
    return Theme("t", "T", "", kw.pop("group", "Tematy"), **kw)  # type: ignore[arg-type]


def test_paintings_come_first_on_a_cover() -> None:
    # Mateusz 2026-11-12: drawings and prints inside, painting on the cover;
    # a painting far down the theme's works still beats the prints at the top.
    items = [*(_print(n) for n in range(60)), _painting(1), _painting(2), _painting(3)]
    cover = discover_api._cover(items, "2026-11-12:t", _theme(terms=("subject:war",)))
    assert {i.id for i in cover[:3]} == {"cma:p1", "cma:p2", "cma:p3"}
    assert cover[3].id.startswith("cma:e")


def test_a_theme_of_prints_keeps_its_prints_on_the_cover() -> None:
    # The paintings below the best COVER_POOL are not lifted onto its cover.
    items = [*(_print(n) for n in range(60)), _painting(1), _painting(2)]
    for found in (
        _theme(terms=("technique:print",)),
        _theme(terms=("subject:birds", "technique:drawing")),
        _theme(group="Grafika i plakat"),
    ):
        cover = discover_api._cover(items, "2026-11-12:t", found)
        assert all(i.id.startswith("cma:e") for i in cover), found
    # Paintings and drawings both asked (colour cards): paintings first.
    painterly = _theme(terms=("technique:painting", "technique:drawing"))
    cover = discover_api._cover(items, "2026-11-12:t", painterly)
    assert {i.id for i in cover[:2]} == {"cma:p1", "cma:p2"}
