"""Polish line breaking: what must not stay at the end of a line.

A one-letter word (a, i, o, u, w, z) goes to the next line with the word
after it, initials stay with the name, a number with its "r." or "w.", a
Roman century with "w." or "wieku", and a dash never starts a line. Each
such space becomes a no-break space (U+00A0), one character for one, so
offsets into the text stay valid. The app does the same on the phone
(ios/Frame/Design/Typography.swift); keep the two in step.
"""

from __future__ import annotations

import re

NBSP = "\u00a0"

_RULES = (
    # a, i, o, u, w, z (and capitals) as words of their own, also in a run
    # ("a w domu"); after a space, a bracket, a quote or a dash.
    re.compile(r"(?<![^\s(\[„\"'“‘«—–])([aiouwzAIOUWZ]) (?=\S)"),
    # Initials: "J. M. W. Turner".
    re.compile(r"(?<![^\s(\[„\"'“‘«])([A-ZĄĆĘŁŃÓŚŹŻ]\.) (?=[A-ZĄĆĘŁŃÓŚŹŻ])"),
    # "1868 r.", "XIX w.", "XIX wieku", "50 cm".
    re.compile(r"(\d|\b[IVXLC]+) (?=(?:r\.|w\.|wiek\w*|cm\b|mm\b|m\b|px\b|kg\b|zł\b|%))"),
    # A dash goes with the word before it: "Duret – krytyk".
    re.compile(r"(?<=\S) (?=[–—] )"),
)


def bound(text: str) -> str:
    """``text`` with no-break spaces where Polish typesetting wants them."""
    for rule in _RULES:
        text = rule.sub(lambda m: (m.group(1) if m.groups() else "") + NBSP, text)
    return text
