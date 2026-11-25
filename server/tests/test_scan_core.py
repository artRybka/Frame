"""The scan's C++ core (``core/scan``: the merge of three photographs as
the phone makes it in its trial, Mateusz 2026-11-19: "Najpierw próba na
iPhonie") takes the merge's numbers from the server's."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

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
    # How its core merges: raised with the server's, once the core is
    # changed as ``reflections`` was (the server makes a scan that says
    # less again of its kept photographs).
    assert number("merging") == own_works.MERGING


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


def test_a_charts_tables_carry_all_that_puts_its_colours() -> None:
    """Mateusz 2026-11-19 08:09 UTC: "Czy iPhone będzie także obsługiwać
    kartę koloru". The phone is given what ``colorchecker.apply`` goes by
    (``colorchecker.tables``) and puts its own photographs through it
    before it makes the scan. Read as the core reads them, the tables
    make of any picture what ``apply`` makes of it: but for a level in
    one value of a million (the server's OpenCV adds up in one step where
    the processor can), also with the photograph's top in the chart."""
    import numpy as np
    import test_colorchecker as drawn

    from frame_server.imaging import colorchecker

    board = drawn._board(colorchecker.REFERENCE.astype(np.uint8))
    rng = np.random.default_rng(5)
    picture = rng.integers(0, 256, (600, 800, 3), dtype=np.uint8)
    picture[:8] = 255
    picture[8:16] = 0
    tops = []
    for shot in (drawn._photographed, drawn._in_a_dim_room, drawn._under_a_lamp):
        chart = colorchecker.find(shot(drawn._scene(board)))
        assert chart is not None
        tops.append(chart.lightest > 0)
        tables = colorchecker.tables(chart)
        for photo in (picture, shot(drawn._scene(board))):
            want = colorchecker.apply(photo, chart).astype(int)
            apart = np.abs(_as_the_core(tables, photo).astype(int) - want)
            assert apart.max() <= 1 and (apart > 0).mean() < 1e-4, shot.__name__
    assert tops == [False, False, True]


def test_the_phone_puts_a_charts_colours_as_the_server_does() -> None:
    """The chart the app's tests put a made-up picture in the colours of
    (``PhoneScanTests``), with the tables of it and what the core makes
    of the picture: the tables are this server's of that chart, the core
    read them as this file's reading does (value for value), and that is
    what ``colorchecker.apply`` makes of the picture here."""
    import base64
    import json
    import re
    import zlib

    import numpy as np

    from frame_server.imaging import colorchecker

    source = IOS / "FrameTests" / "PhoneScanTests.swift"
    if not source.is_file():
        pytest.skip("the server's tree without the app beside it")
    text = source.read_text()

    def held(name: str) -> bytes:
        found = re.search(rf'static let {name} = """\n(.*?)\n\s*"""', text, re.S)
        assert found is not None, name
        return base64.b64decode("".join(found.group(1).split()))

    said = re.search(r'static let chart = #"(.*)"#', text)
    assert said is not None
    chart = colorchecker.Chart.from_json(json.loads(said.group(1)))
    # (Packed with no head: what the phone's ``NSData`` unpacks.)
    tables = zlib.decompress(held("chartTables"), -15)
    picture = np.frombuffer(held("chartPicture"), np.uint8).reshape(24, 32, 3)
    put = np.frombuffer(held("chartPut"), np.uint8).reshape(24, 32, 3)

    mine = colorchecker.tables(chart)
    head = len(colorchecker.TABLES)
    floats = head + 4 * (3 * 256 + 256 + 9)
    assert len(mine) == len(tables) and mine[:head] == tables[:head]
    # (To the last bit but where a processor's power of 2.4 ends otherwise.)
    assert np.allclose(
        np.frombuffer(mine[head:floats], "<f4"),
        np.frombuffer(tables[head:floats], "<f4"),
        1e-6,
        1e-9,
    )
    assert mine[floats:] == tables[floats:]
    # The fixture is of a chart with the photograph's top in it, and of
    # colours that ran into each other.
    assert chart.lightest > 0 and abs(chart.matrix[0][1]) > 0.02

    assert (_as_the_core(tables, picture) == put).all()
    apart = np.abs(colorchecker.apply(picture, chart).astype(int) - put)
    assert apart.max() <= 1 and (apart > 0).mean() < 0.002
    assert (np.abs(put.astype(int) - picture) > 8).mean() > 0.3  # the chart did set colours


def test_the_phone_takes_a_lens_bend_out_as_the_server_does() -> None:
    """Mateusz 2026-11-19 09:52 UTC: "prostowanie obiektywu. Czy tego
    także nie lepiej robić na iPhone?". The made-up picture the app's
    tests straighten with the core (``PhoneScanTests``), by the one
    measured term and by a camera's table about a middle of its own, and
    the corners they move both ways: what ``lens.straight``,
    ``lens.moved`` and ``lens.bent`` make of them here, pixel for pixel.
    (The core against them on whole photographs, on this processor and on
    one like the phone's: ``core/scan/tools/lens.py``.)"""
    import base64
    import json
    import re

    import numpy as np

    from frame_server.imaging import lens

    source = IOS / "FrameTests" / "PhoneScanTests.swift"
    if not source.is_file():
        pytest.skip("the server's tree without the app beside it")
    text = source.read_text()

    def held(name: str) -> Any:
        found = re.search(rf'static let {name} = """\n(.*?)\n\s*"""', text, re.S)
        assert found is not None, name
        data = base64.b64decode("".join(found.group(1).split()))
        return np.frombuffer(data, np.uint8).reshape(48, 36, 3)

    def said(name: str) -> Any:
        found = re.search(rf"static let {name}(?:: [\[\]A-Za-z]+)? = (.*)\n", text)
        assert found is not None, name
        return json.loads(found.group(1))

    number, table, centre = said("lensNumber"), said("lensTable"), said("lensCentre")
    # The number is the one measured of his phone; the table one the
    # server would take from a camera, about a middle that is not the
    # photograph's.
    assert number == lens.BENDS[lens.PHONE]
    own = lens.table(table, centre)
    assert own is not None and own[1] != (0.5, 0.5)
    bends = [lens.Bend(k1=number), lens.Bend(table=own[0], centre=own[1])]
    picture = held("lensPicture")
    corners = [tuple(c) for c in said("lensCorners")]
    moved, bent = said("lensMoved"), said("lensBent")
    for n, (bend, name) in enumerate(zip(bends, ("lensByNumber", "lensByTable"), strict=True)):
        want = held(name)
        assert (lens.straight(picture, bend) == want).all(), name
        assert (want != picture).mean() > 0.3  # the bend did move the picture
        assert lens.moved(corners, 6048, 8064, bend) == [tuple(c) for c in moved[n]]
        assert lens.bent(corners, 6048, 8064, bend) == [tuple(c) for c in bent[n]]
    # The two bends are not one another's.
    assert (held("lensByNumber") != held("lensByTable")).mean() > 0.05


def _as_the_core(tables: bytes, photo: Any) -> Any:
    """``photo`` (uint8 RGB) put through a chart's ``tables`` as the core
    does it (``core/scan`` ``scan_chart.cpp``): in float32, one sum after
    another and nothing fused, so that it comes out the same on every
    processor."""
    import numpy as np

    from frame_server.imaging import colorchecker

    head = len(colorchecker.TABLES)
    assert tables[:head] == colorchecker.TABLES
    assert len(tables) == head + 4 * (3 * 256 + 256 + 9) + 4 + 8 * 3 + 65536
    at = head

    def take(kind: str, count: int) -> Any:
        nonlocal at
        out = np.frombuffer(tables, kind, count, at)
        at += out.nbytes
        return out

    curves = take("<f4", 3 * 256).reshape(3, 256)
    linear = take("<f4", 256)
    matrix = take("<f4", 9).reshape(3, 3)
    top = bool(take("<u4", 1)[0])
    start = take("<f8", 3)
    lit = take("u1", 65536)
    none, all_ = np.float32(0), np.float32(1)
    light = np.stack([curves[c][photo[..., c]] for c in range(3)], axis=-1)
    if top:
        lifted = light.copy()
        for c in range(3):
            above = np.float32(max(1.0 - float(start[c]), 1e-6))
            near = np.clip((linear[photo[..., c]] - np.float32(start[c])) / above, none, all_)
            others = np.maximum(light[..., (c + 1) % 3], light[..., (c + 2) % 3])
            lifted[..., c] = light[..., c] + near * np.maximum(others - light[..., c], none)
        light = lifted
    out = np.empty_like(photo)
    for c in range(3):
        total = matrix[c, 0] * light[..., 0] + matrix[c, 1] * light[..., 1]
        total = np.clip(total + matrix[c, 2] * light[..., 2], none, all_)
        out[..., c] = lit[(total * np.float32(65535) + np.float32(0.5)).astype(np.uint16)]
    return out


def test_the_phone_finds_a_museum_work_as_the_server_does() -> None:
    """Mateusz 2026-11-20: „Przecież wszystko miało iść na iPhone”. The
    museum photographs are cut on the phone (``MuseumCrop`` in the app,
    the core's ``frame_crop_find``) by what ``imaging/crop_model.py`` makes
    of the model's answer: the app's numbers are the server's, and what the
    app's tests find with the core in a made-up photograph and made-up
    masks (``MuseumCropTests``) is what ``crop_model.find`` finds here.
    (The core against it on museum photographs and the model's own
    answers: ``core/scan/tools/crop.py``.)"""
    import json
    import re

    import numpy as np

    from frame_server.imaging import crop_model as cm

    source = IOS / "Frame" / "Model" / "MuseumCrop.swift"
    tests = IOS / "FrameTests" / "MuseumCropTests.swift"
    if not source.is_file() or not tests.is_file():
        pytest.skip("the server's tree without the app beside it")
    text, held = source.read_text(), tests.read_text()
    assert re.search(r'static let model = "([^"]+)"', text).group(1) == cm.MODEL  # type: ignore[union-attr]
    painting = re.search(r'static let paintingModel = "([^"]+)"', text)
    assert painting is not None and painting.group(1) == cm.PAINTING_MODEL
    for name, number in (("sure", cm.SURE), ("paintingSure", cm.PAINTING_SURE)):
        found = re.search(rf"static let {name} = ([0-9.]+)\n", text)
        assert found is not None and float(found.group(1)) == number, name
    assert re.search(r"static let side = (\d+)", text).group(1) == str(cm.SIDE)  # type: ignore[union-attr]
    found = re.search(r"static let photoSide = (\d+)", text)
    assert found is not None and int(found.group(1)) == cm.PHOTO_SIDE

    def said(name: str) -> Any:
        found = re.search(rf"static let {name}(?:: [\[\]A-Za-z?]+)? = (.*)\n", held)
        assert found is not None, name
        return json.loads(found.group(1))

    # The made-up photograph and masks, as the app's test makes them.
    h, w = 240, 300
    photo = np.full((h, w, 3), 120, np.uint8)
    photo[30:210, 40:260] = (200, 160, 60)
    y, x = np.mgrid[50:190, 60:240]
    photo[50:190, 60:240, 0] = (x * 7 + y * 13) % 60 + 30
    photo[50:190, 60:240, 1] = (x * 3 + y * 5) % 40 + 20
    photo[50:190, 60:240, 2] = (x + y * 11) % 80 + 90
    logits = np.full((2, cm.SIDE, cm.SIDE), -8.0, np.float32)
    logits[0, 102:281, 77:307] = 8.0
    logits[1, 76:307, 51:333] = 8.0
    assert "photo[(y * columns + x) * 3] = UInt8((x * 7 + y * 13) % 60 + 30)" in held
    assert "logits[(y * side + x)] = 8" in held

    want = cm.find(photo, logits, said("sure"))
    assert want.verdict == said("verdict") == "cut"
    assert [list(c) for c in want.work or []] == said("work")
    assert [list(c) for c in want.surround or []] == said("surround")
    # Not sure enough, or sure it wants none: as here.
    assert cm.find(photo, logits, 0.5).verdict == "unsure"
    assert cm.find(photo, logits, 0.05).verdict == "whole"

    # A print's wide sheet cut down round its impression (Mateusz
    # 2026-11-24): as here, and the app says it did it as the server would.
    found = re.search(r"static let plates = (\d+)\n", text)
    assert found is not None and int(found.group(1)) == cm.PLATE
    found = re.search(r"static let plateOver = ([0-9.]+)\n", text)
    assert found is not None and float(found.group(1)) == cm.PLATE_OVER
    found = re.search(r"static let upright = ([0-9.]+)\n", text)
    assert found is not None and float(found.group(1)) == cm.UPRIGHT
    found = re.search(r"static let plateSame = ([0-9.]+)\n", text)
    assert found is not None and float(found.group(1)) == cm.PLATE_SAME
    found = re.search(r"static let printKind = (\d+)\n", text)
    assert found is not None and int(found.group(1)) == cm.KINDS.index("print")
    sheet = np.full((h, w, 3), 50, np.uint8)
    sheet[20:220, 30:270] = (236, 230, 216)
    y, x = np.mgrid[70:170, 100:200]
    sheet[70:170, 100:200][(x * 3 + y * 7) % 19 < 8] = (70, 60, 50)
    assert "where (x * 3 + y * 7) % 19 < 8" in held
    edges = [[30, 20], [270, 20], [270, 220], [30, 220]]
    assert said("printSheet") == [[a / w, b / h] for a, b in edges]
    made = cm.plate(sheet, said("printSheet"))
    assert made is not None
    assert [list(c) for c in made[0]] == said("printCut")
    assert [list(c) for c in made[1]] == said("printPlate")


def test_the_servers_crop_models_are_the_apps() -> None:
    """Mateusz 2026-11-24 10:53 UTC, „Na serwerze w nocy”: the night cuts
    museum photographs with the app's own models, exported to ONNX
    (``imaging/models``, ``crop_night.py``). Each names its model as
    ``crop_model`` does and the app's weights it was made beside: a new
    model comes on both sides at once, or this fails."""
    import hashlib

    import onnxruntime as ort

    from frame_server.imaging import crop_model as cm

    for model, package in ((cm.MODEL, "Kadr"), (cm.PAINTING_MODEL, "KadrPainting")):
        session = ort.InferenceSession(str(cm.WEIGHTS / f"{model}.onnx"))
        said = session.get_modelmeta().custom_metadata_map
        assert said["model"] == model
        weights = IOS / "Models" / f"{package}.mlpackage" / "Data" / "com.apple.CoreML"
        weights = weights / "weights" / "weight.bin"
        if weights.is_file():
            assert hashlib.sha256(weights.read_bytes()).hexdigest() == said["mlpackage"], package
