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
