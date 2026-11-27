"""constants.py > ../src/constants.hpp: the merge's numbers as `imaging/reflections.py` has them, and
the museum crop's as `imaging/cut.py` and `imaging/crop_model.py` have them, and the restorer's as
`imaging/descreen.py` and `restorer.py` have them, so
the C++ core cannot fall out of step with them unnoticed (`tests/test_scan_core.py` makes the file
again and compares). Run it with the server's Python: `cd server && uv run python
../core/scan/tools/constants.py > ../core/scan/src/constants.hpp`."""

from frame_server import restorer
from frame_server.imaging import crop_model, cut, descreen
from frame_server.imaging import reflections as R

#: What of `restorer.py` the phone's restorer goes by (`scan_restore.cpp`).
RESTORER = ("COLOUR_SIGMA", "GRAIN_SIGMA", "DRAWN", "LAID_SIDE", "LAID_MATCH", "LAID_SHIFT", "LONGEST",
            "SKEW_FIXED", "SKEW_MAX")


def text() -> str:
    lines = [
        "// Made by tools/constants.py from server/src/frame_server/imaging/reflections.py",
        "// (and cut.py, crop_model.py, descreen.py, restorer.py): the numbers are set there (and told there why),",
        "// never here.",
        "#pragma once\n\n#include <array>\n\nnamespace frame::scan {\n",
    ]
    lines += _numbers({name: getattr(R, name) for name in vars(R)})
    lines.append("\n}  // namespace frame::scan\n\nnamespace frame::crop {\n")
    lines += _numbers({**{n: getattr(cut, n) for n in vars(cut)}, **{n: getattr(crop_model, n) for n in vars(crop_model)}})
    lines.append("\n}  // namespace frame::crop\n\nnamespace frame::restore {\n")
    lines += _numbers({**{n: getattr(descreen, n) for n in vars(descreen)}, **{n: getattr(restorer, n) for n in RESTORER}})
    lines.append("\n}  // namespace frame::restore")
    return "\n".join(lines) + "\n"


def _numbers(found: dict) -> list[str]:
    lines = []
    for name in sorted(found):
        v = found[name]
        if not name.isupper() or name.startswith("_") or isinstance(v, bool):
            continue
        if isinstance(v, int):
            lines.append(f"inline constexpr int {name} = {v};")
        elif isinstance(v, float):
            lines.append(f"inline constexpr double {name} = {v!r};")
        elif isinstance(v, tuple) and all(isinstance(e, (int, float)) for e in v):
            kind = "int" if all(isinstance(e, int) for e in v) else "double"
            given = ", ".join(repr(e) for e in v)
            lines.append(f"inline constexpr std::array<{kind}, {len(v)}> {name}{{{given}}};")
        elif isinstance(v, tuple) and all(isinstance(e, tuple) for e in v):
            given = ", ".join("{" + ", ".join(map(str, e)) + "}" for e in v)
            lines.append(
                f"inline constexpr std::array<std::array<int, {len(v[0])}>, {len(v)}> {name}{{{{{given}}}}};"
            )
    return lines


if __name__ == "__main__":
    print(text(), end="")
