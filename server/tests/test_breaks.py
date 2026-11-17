"""Polish line breaking: no one-letter word left at a line's end, on the frame."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from frame_server.imaging.breaks import NBSP, bound
from frame_server.imaging.caption import font
from frame_server.imaging.text import wrap


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("krytyk sztuki i kolekcjoner", "krytyk sztuki i_kolekcjoner"),
        ("Duret siedzi w ciemnym ubraniu", "Duret siedzi w_ciemnym ubraniu"),
        ("a w domu z kotem", "a_w_domu z_kotem"),
        ("Pisał o nich (i o innych)", "Pisał o_nich (i_o_innych)"),
        ("„A potem” u niego", "„A_potem” u_niego"),
        ("W gabinecie. Z kotem", "W_gabinecie. Z_kotem"),
        ("J. M. W. Turner malował", "J._M._W._Turner malował"),
        ("w 1868 r. i w XIX wieku", "w_1868_r. i_w_XIX_wieku"),
        ("ok. 2000 px, 50 cm", "ok. 2000_px, 50_cm"),
        ("Duret – krytyk", "Duret_– krytyk"),
        # Not words of their own: an "a" inside a word or after a hyphen.
        ("kawa mała", "kawa mała"),
        ("x-a b", "x-a b"),
        ("", ""),
    ],
)
def test_bound(text: str, expected: str) -> None:
    assert bound(text) == expected.replace("_", NBSP)


def test_the_length_stays_so_offsets_hold() -> None:
    text = "Znał Maneta, Whistlera i Moneta, a sam zbierał ich prace w 1870 r."
    assert len(bound(text)) == len(text)
    assert bound(text).replace(NBSP, " ") == text


def test_the_frame_wraps_with_the_one_letter_word_on_the_next_line() -> None:
    draw = ImageDraw.Draw(Image.new("1", (10, 10)))
    fnt = font(20, "serif")
    text = (
        "Théodore Duret, francuski krytyk sztuki i kolekcjoner, "
        "był jednym z pierwszych obrońców impresjonistów."
    )
    for width in range(160, 600, 7):
        lines = wrap(draw, text, fnt, width)
        assert " ".join(lines) == text  # nothing lost, plain spaces drawn
        for line in lines[:-1]:
            assert line.split(" ")[-1] not in {"i", "z", "w", "a", "o", "u"}, (width, lines)
        assert all(NBSP not in line for line in lines)


def test_a_bound_run_wider_than_the_line_still_breaks() -> None:
    draw = ImageDraw.Draw(Image.new("1", (10, 10)))
    fnt = font(20, "serif")
    lines = wrap(draw, "a w z i o u", fnt, 30)
    assert len(lines) > 1
    assert " ".join(lines) == "a w z i o u"
