"""The scan's C++ core (``core/scan``: the merge of three photographs as
the phone makes it in its trial, Mateusz 2026-11-19: "Najpierw próba na
iPhonie") takes the merge's numbers from the server's."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "core" / "scan"


def test_the_cores_numbers_are_the_servers() -> None:
    """A number changed in ``imaging/reflections.py`` is changed in the
    core's ``constants.hpp`` by making it again (``tools/constants.py``),
    never by hand: the two merge alike only with the same numbers."""
    tool = CORE / "tools" / "constants.py"
    if not tool.is_file():
        pytest.skip("the server's tree without the core beside it")
    spec = importlib.util.spec_from_file_location("scan_core_constants", tool)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    again = "uv run python ../core/scan/tools/constants.py > ../core/scan/src/constants.hpp"
    assert module.text() == (CORE / "src" / "constants.hpp").read_text(), again


IOS = Path(__file__).resolve().parents[2] / "ios"


def test_the_phone_goes_by_the_servers_numbers() -> None:
    """The phone makes the scan itself (``PhoneScan`` in the app; Mateusz
    2026-11-19 07:42 UTC: "Tak, składaj na iPhonie") by rules that are
    the server's: which side photographs, how small they are read, what
    corners will do, how far around them is cleaned, the JPEG kept."""
    import re

    from frame_server import own_works
    from frame_server.imaging import cut, reflections

    source = IOS / "Frame" / "Model" / "PhoneScan.swift"
    if not source.is_file():
        pytest.skip("the server's tree without the app beside it")
    text = source.read_text()

    def number(name: str) -> float:
        found = re.search(rf"static let {name} = ([0-9._]+)", text)
        assert found is not None, name
        return float(found.group(1).replace("_", ""))

    assert number("matchSide") == reflections.MATCH_SIDE
    assert number("sideAngle") == own_works.SIDE_ANGLE
    assert number("around") == reflections.AROUND
    assert number("leastKept") == cut.LEAST_KEPT
    assert number("square") == cut.SQUARE
    assert number("quality") * 100 == own_works.INCOMING_QUALITY


def test_the_phone_and_the_server_read_a_photograph_alike() -> None:
    """The made-up photograph the app's tests read (Display P3, lying on
    its side with an EXIF turn) and what they hold the phone's reading to
    (``PhoneScanTests``): the server's reading of that very file. A scan
    made on the phone is of the colours the server would have had."""
    import base64
    import io
    import re

    import numpy as np
    from PIL import Image

    from frame_server.imaging.layout import load_image
    from frame_server.own_works import INCOMING_QUALITY

    source = IOS / "FrameTests" / "PhoneScanTests.swift"
    if not source.is_file():
        pytest.skip("the server's tree without the app beside it")
    text = source.read_text()
    file = re.search(r'static let photograph = """\n(.*?)\n\s*"""', text, re.S)
    table = re.search(r"static let read: \[\[Int\]\] = \[\n(.*?)\n    \]", text, re.S)
    assert file is not None and table is not None
    data = base64.b64decode("".join(file.group(1).split()))
    squares = re.findall(r"\[([0-9, ]+)\]", table.group(1))
    told = [[int(n) for n in square.split(",")] for square in squares]
    assert len(told) == 24

    with Image.open(io.BytesIO(data)) as stored:
        assert stored.size == (96, 64) and stored.info.get("icc_profile")
    upright = load_image(data).convert("RGB")
    assert upright.size == (64, 96)
    seen = np.asarray(upright)
    middles = [seen[r * 16 + 8, k * 16 + 8].tolist() for r in range(6) for k in range(4)]
    assert middles == told
    # Read as they stand, the camera's numbers are other colours: its
    # 200, 100, 50 is sRGB's 215, 93, 31.
    with Image.open(io.BytesIO(data)) as stored:
        lying = np.asarray(stored.convert("RGB")).astype(int)
    as_stored = [lying[r * 16 + 8, k * 16 + 8] for r in range(4) for k in range(6)]
    assert any(np.abs(colour - (200, 100, 50)).max() <= 2 for colour in as_stored)
    assert [215, 93, 31] in told

    # As the merge reads it here: of the server's own copy, a side one small.
    kept = io.BytesIO()
    upright.save(kept, "JPEG", quality=INCOMING_QUALITY)
    for side, square in ((None, 16), (24, 8)):
        with Image.open(io.BytesIO(kept.getvalue())) as again:
            if side is not None:
                again.draft("RGB", (side, side))
            read = np.asarray(again.convert("RGB"))
        assert read.shape == (6 * square, 4 * square, 3)
        for n, colour in enumerate(told):
            r, k = divmod(n, 4)
            here = read[r * square + square // 2, k * square + square // 2].astype(int)
            assert np.abs(here - colour).max() <= 6, (side, n, here, colour)
