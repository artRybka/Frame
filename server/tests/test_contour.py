"""The drawn contour of a picture (``library.contour``, Mateusz 2026-11-13)."""

from __future__ import annotations

import io
import math

from conftest import jpeg_bytes
from PIL import Image, ImageDraw

from frame_server.library import ItemKind
from frame_server.library.contour import CONTOUR_VERSION, contour, need


def _figure(
    ground: tuple[int, int, int], line: tuple[int, int, int], width: int = 6
) -> Image.Image:
    """A pink-on-red nude drawn round in long lines, as Matisse's."""
    img = Image.new("RGB", (480, 640), ground)
    draw = ImageDraw.Draw(img)
    draw.ellipse((150, 120, 330, 520), fill=(226, 186, 176))
    for k in range(5):
        cx = 120 + 60 * k
        points = [(cx + 40 * math.sin(t / 9), 60 + t * 5) for t in range(110)]
        draw.line(points, fill=line, width=width, joint="curve")
    draw.ellipse((150, 120, 330, 520), outline=line, width=width)
    return img


def test_black_lines_on_a_light_picture_are_its_contour() -> None:
    found = contour(_figure((196, 70, 72), (30, 26, 28)))
    assert found is not None
    r, g, b = (int(found.hex[i : i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) < 70  # a dark line, deepened
    assert found.length >= need(0.0)
    assert 0.5 < found.width < 3


def test_a_coloured_contour_keeps_its_colour() -> None:
    found = contour(_figure((226, 196, 90), (40, 70, 160)))
    assert found is not None
    r, g, b = (int(found.hex[i : i + 2], 16) for i in (1, 3, 5))
    assert b > r and b > g  # blue, as Gauguin's


def test_shadows_in_a_dark_picture_are_no_contour() -> None:
    """Narrow darks between light shapes in a dark picture: folds, fingers."""
    img = Image.new("RGB", (480, 640), (40, 30, 24))
    draw = ImageDraw.Draw(img)
    for k in range(6):
        draw.rectangle((40 + 70 * k, 200, 90 + 70 * k, 460), fill=(200, 170, 140))
    assert contour(img) is None


def test_a_plain_picture_a_frame_and_odd_thumbnails_have_none() -> None:
    assert contour(Image.open(io.BytesIO(jpeg_bytes((150, 150, 150))))) is None
    framed = Image.new("RGB", (480, 640), (230, 220, 200))
    ImageDraw.Draw(framed).rectangle((30, 30, 449, 609), outline=(20, 20, 20), width=6)
    assert contour(framed) is None
    for odd in (
        Image.new("RGB", (1, 1)),
        Image.new("P", (40, 30)),
        Image.new("CMYK", (60, 80), (0, 0, 0, 255)),
    ):
        assert contour(odd) is None


def test_a_picture_of_one_tint_has_none() -> None:
    assert contour(_figure((196, 70, 72), (30, 26, 28)), ["monochrome"]) is None


def test_library_contours_are_measured_once(service) -> None:
    from frame_server.player import CONTOUR_KEY

    library = service.library
    buffer = io.BytesIO()
    _figure((196, 70, 72), (30, 26, 28)).save(buffer, "JPEG", quality=95)
    work = service.importer.add_upload(
        buffer.getvalue(), kind=ItemKind.OWN, title="Akt", artist="Ala"
    )
    measured = library.get(work.id).contour
    assert measured is not None  # on import
    library.update(work.id, contour=None)
    library.set_state(CONTOUR_KEY, CONTOUR_VERSION - 1)
    assert service.player.contours() == 1
    assert library.get(work.id).contour == measured
    assert library.get_state(CONTOUR_KEY) == CONTOUR_VERSION
    library.update(work.id, contour=None)
    assert service.player.contours() == 0  # only once
