from __future__ import annotations

import pytest

from frame_server.library import Item, Library
from frame_server.library.commons import REPAIR_STATE_KEY, repair_library
from frame_server.library.dates import text_year, text_years


@pytest.mark.parametrize(
    ("text", "years"),
    [
        ("18th century", (1700, 1799)),
        ("19th century", (1800, 1899)),
        ("late 16th century", (1575, 1599)),
        ("early 18th century", (1700, 1725)),
        ("mid-19th century", (1840, 1860)),
        ("first half 18th century", (1700, 1749)),
        ("second half of the 19th century", (1850, 1899)),
        ("late 18th–early 19th century", (1775, 1799)),
        ("c. 17th century - mid 19th century", (1600, 1699)),
        ("ca. 20th century", (1900, 1999)),
        ("1st century A.D.", (1, 100)),
        ("3rd century A.D.", (200, 299)),
        ("1st century B.C.–1st century A.D.", (-100, -1)),
        ("A.D. 50–79", (50, 79)),
        ("ca. 1890s", (1890, 1899)),
        ("ca.1900", (1900, 1900)),
        ("pierwsza dekada XX wieku", (1900, 1909)),
        ("koniec XIX wieku", (1875, 1899)),
        ("XVIII w.", (1700, 1799)),
        ("I w. p.n.e.", (-100, -1)),
    ],
)
def test_dates_in_words_give_their_years(text: str, years: tuple[int, int]) -> None:
    assert text_years(text) == years


@pytest.mark.parametrize(
    "text",
    ["", "n.d.", "n.d.a.", "nieznana data", "2026-10-29", "2017-11-28 18:40", "i w. domu"],
)
def test_no_date_and_timestamps_give_no_year(text: str) -> None:
    assert text_year(text) is None


def test_stored_works_without_a_year_get_one_from_their_date(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(Item(id="europeana:1", source="europeana", source_id="1", date_text="18th century"))
    lib.upsert(Item(id="yale:1", source="yale", source_id="1", date_text="n.d."))
    lib.upsert(Item(id="icloud:1", source="icloud", source_id="1", date_text="1990s"))
    lib.upsert(Item(id="met:1", source="met", source_id="1", date_text="19th century", year=1850))
    lib.set_state(REPAIR_STATE_KEY, 9)

    repair_library(lib)

    years = {item.id: item.year for item in lib.query(include_excluded=True)[1]}
    assert years == {"europeana:1": 1700, "yale:1": None, "icloud:1": None, "met:1": 1850}
