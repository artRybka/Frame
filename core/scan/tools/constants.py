"""constants.py > ../src/constants.hpp: the merge's numbers as `imaging/reflections.py` has them, so
the C++ core cannot fall out of step with them unnoticed (`tests/test_scan_core.py` makes the file
again and compares). Run it with the server's Python: `cd server && uv run python
../core/scan/tools/constants.py > ../core/scan/src/constants.hpp`."""

from frame_server.imaging import reflections as R


def text() -> str:
    lines = [
        "// Made by tools/constants.py from server/src/frame_server/imaging/reflections.py:",
        "// the numbers are set there (and told there why), never here.",
        "#pragma once\n\n#include <array>\n\nnamespace frame::scan {\n",
    ]
    for name in sorted(vars(R)):
        v = getattr(R, name)
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
    lines.append("\n}  // namespace frame::scan")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(text(), end="")
