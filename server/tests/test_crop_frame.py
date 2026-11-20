"""A band found round a work is its frame only when it looks like one
(`crop_model.framed`, Mateusz 2026-11-20: „Model bardzo często dodaje ramę
której nie ma”)."""

import numpy as np

from frame_server.imaging import crop_model as cm

WORK = [[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]]
AROUND = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _photo(band: tuple[int, int, int], outside: tuple[int, int, int]) -> np.ndarray:
    rgb = np.zeros((200, 200, 3), np.uint8)
    rgb[:] = outside
    rgb[40:160, 40:160] = band
    rgb[60:140, 60:140] = (60, 40, 30)
    return rgb


def test_pale_paper_going_on_outwards_is_no_frame() -> None:
    assert not cm.framed(_photo((235, 232, 225), (238, 235, 228)), WORK, AROUND)


def test_gilded_frame_is_one() -> None:
    assert cm.framed(_photo((190, 150, 70), (200, 200, 200)), WORK, AROUND)


def test_grey_frame_on_a_white_wall_is_one() -> None:
    assert cm.framed(_photo((40, 40, 40), (235, 235, 235)), WORK, AROUND)
