"""Years from the date texts sources give without a year of their own.

About 8% of the catalogue had no year (2026-11-06), mostly Europeana and
Yale. Most of those have no date at all, but some ~250 say it in words
("18th century", "late 16th century", "1st century A.D.", "ca. 1890s",
"pierwsza dekada XX wieku") that the sources' own readers skipped. Without
a year a work is never found by Epoka.
"""

from __future__ import annotations

import re

_ORDINAL = r"(\d{1,2})\s*(?:st|nd|rd|th)"
#: "early", "mid", "late", "first half", "second half of the" before a century.
_PART_EN = (
    r"(early|mid|late|first\s+half|second\s+half|first\s+quarter|last\s+quarter)"
    r"[\s-]+(?:of\s+the\s+)?"
)
_CENTURY_EN = re.compile(
    rf"\b(?:{_PART_EN})?{_ORDINAL}[\s-]+century\b",
    re.IGNORECASE,
)
#: "late 18th–early 19th century": the first century has no word of its own.
_CENTURY_RANGE_EN = re.compile(
    rf"\b(?:{_PART_EN})?{_ORDINAL}\s*[–—-]\s*(?:{_PART_EN})?\d{{1,2}}\s*(?:st|nd|rd|th)"
    r"[\s-]+century\b",
    re.IGNORECASE,
)
_PART_YEARS = {
    "early": (0, 25),
    "mid": (40, 60),
    "late": (75, 99),
    "first half": (0, 49),
    "second half": (50, 99),
    "first quarter": (0, 24),
    "last quarter": (75, 99),
}
_PART_PL = (
    r"(początek|początku|połowa|połowie|koniec|końca|schyłek|"
    r"pierwsza\s+połowa|pierwszej\s+połowie|druga\s+połowa|drugiej\s+połowie|"
    r"pierwsza\s+dekada|pierwszej\s+dekadzie)\s+"
)
_CENTURY_PL = re.compile(
    rf"(?:\b{_PART_PL})?\b((?-i:[IVXL]+))\s*(?:wiek|wieku|w\.)",
    re.IGNORECASE,
)
_PL_YEARS = {
    "początek": (0, 25),
    "połowa": (40, 60),
    "koniec": (75, 99),
    "schyłek": (75, 99),
    "pierwsza połowa": (0, 49),
    "druga połowa": (50, 99),
    "pierwsza dekada": (0, 9),
}
_PL_FORMS = {
    "początku": "początek",
    "połowie": "połowa",
    "końca": "koniec",
    "pierwszej połowie": "pierwsza połowa",
    "drugiej połowie": "druga połowa",
    "pierwszej dekadzie": "pierwsza dekada",
}
_BC = re.compile(r"\b(?:B\.?\s?C\.?(?:E\.?)?|p\.?\s?n\.?\s?e\.?)(?=\W|$)", re.IGNORECASE)
_AD = re.compile(r"\b(?:A\.?\s?D\.?|C\.?E\.?|n\.\s?e\.)(?=\W|$)", re.IGNORECASE)
_DECADE = re.compile(r"\b(1[0-9]{2}0)\s*'?s\b")
_YEAR = re.compile(r"\b(1[0-9]{3}|[5-9][0-9]{2})\b")
#: A timestamp ("2026-10-29", "2017-11-28 18:38"): when the file was made or
#: brought in, not the work.
_STAMP = re.compile(r"^\s*\d{4}-\d{2}-\d{2}")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def _bc_at(text: str, end: int) -> bool:
    """Whether the era written right after ``end`` (before the next date) is
    before Christ: "1st century B.C.–1st century A.D." is BC at its start."""
    rest = re.split(r"[–—-]\s*(?=\D*\d)", text[end:], maxsplit=1)[0]
    return bool(_BC.search(rest))


def text_years(text: str) -> tuple[int, int] | None:
    """The years a date written in words names, negative before Christ, or
    None: "18th century" -> (1700, 1799), "late 16th century" -> (1575,
    1599), "1st century A.D." -> (1, 100), "ca. 1890s" -> (1890, 1899),
    "ca.1900" -> (1900, 1900), "pierwsza dekada XX wieku" -> (1900, 1909),
    "A.D. 50–79" -> (50, 79). Ranges give their first part. Timestamps and
    "n.d." give None."""
    from .louvre import _roman, _span  # louvre imports the importer

    if not text or _STAMP.match(text):
        return None
    if found := _CENTURY_RANGE_EN.search(text) or _CENTURY_EN.search(text):
        part, number = found.groups()[:2]
        first, last = _PART_YEARS[_flat(part)] if part else (0, 99)
        return _span(int(number), first, last, _bc_at(text, found.end()))
    if found := _CENTURY_PL.search(text):
        part, roman = found.groups()
        if part:
            part = _flat(part)
            part = _PL_FORMS.get(part, part)
        first, last = _PL_YEARS[part] if part else (0, 99)
        return _span(_roman(roman), first, last, _bc_at(text, found.end()))
    if found := _DECADE.search(text):
        start = int(found.group(1))
        return start, start + 9
    era = _AD.search(text) or _BC.search(text)
    if era and (found := re.search(r"\b(\d{1,4})(?:\s*[–—-]\s*(\d{1,4}))?\b", text)):
        start = int(found.group(1))
        end = int(found.group(2) or start)
        return (-start, -end) if _BC.search(text) else (start, end)
    if found := _YEAR.search(text):
        year = int(found.group(1))
        return year, year
    return None


def text_year(text: str) -> int | None:
    """The first year of :func:`text_years`, as an item's ``year``."""
    span = text_years(text)
    return span[0] if span else None
