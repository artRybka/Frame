#!/usr/bin/env python3
"""Finds jumps and blinks in a film of the screen, by numbers.

A way between two looks of a screen is smooth when every part of the screen
changes by about as much in each frame as in the frames beside it. This
cuts the screen into a grid of parts, takes the mean brightness of each in
every frame, and lists:

  jump   a part changed in one frame by much more than in the frames before
         and after it (something came or went at once),
  blink  a part changed and was back within a few frames (something was
         there for a moment).

    film-jumps.py film.mov [--from 12.3 --to 14.0] [--cols 6 --rows 12]

Needs ffmpeg and nothing else. Frames are numbered from 1 within the part
of the film looked at, as `ffmpeg -ss FROM -to TO … %04d.png` numbers them.
Exit code 1 when anything is listed.
"""

import argparse
import subprocess
import sys

WIDE, TALL = 132, 286  # a tenth of a phone's screen; any film is scaled to it


def frames(path: str, start: float | None, end: float | None) -> list[bytes]:
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", path, "-vf", f"scale={WIDE}:{TALL}", "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    size = WIDE * TALL
    return [raw[i : i + size] for i in range(0, len(raw) - size + 1, size)]


def means(frame: bytes, cols: int, rows: int) -> list[float]:
    out = []
    for r in range(rows):
        y0, y1 = r * TALL // rows, (r + 1) * TALL // rows
        for c in range(cols):
            x0, x1 = c * WIDE // cols, (c + 1) * WIDE // cols
            total = 0
            for y in range(y0, y1):
                total += sum(frame[y * WIDE + x0 : y * WIDE + x1])
            out.append(total / ((y1 - y0) * (x1 - x0)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("film")
    ap.add_argument("--from", dest="start", type=float)
    ap.add_argument("--to", dest="end", type=float)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=12)
    ap.add_argument("--least", type=float, default=7.0, help="levels of 255 a part must change by in one frame")
    ap.add_argument("--times", type=float, default=2.5, help="times more than in the frames beside it")
    args = ap.parse_args()

    shots = frames(args.film, args.start, args.end)
    if len(shots) < 5:
        print(f"only {len(shots)} frames")
        return 2
    grid = [means(f, args.cols, args.rows) for f in shots]
    parts = args.cols * args.rows
    found: dict[int, list[str]] = {}
    for p in range(parts):
        row, col = divmod(p, args.cols)
        name = f"r{row + 1}c{col + 1}"
        d = [0.0] + [grid[t][p] - grid[t - 1][p] for t in range(1, len(grid))]
        for t in range(2, len(grid) - 1):
            step = abs(d[t])
            if step < args.least:
                continue
            # A frame the film held (the same picture twice) makes the next
            # step twice as large: not a jump of the screen's.
            beside = max(abs(d[t - 1]), abs(d[t + 1]))
            held = abs(d[t - 1]) < 0.05 or abs(d[t + 1]) < 0.05
            back = [k for k in (1, 2, 3) if t + k < len(grid) and abs(grid[t + k][p] - grid[t - 1][p]) < step * 0.25]
            if back and step >= args.least:
                found.setdefault(t + 1, []).append(f"blink {name} {d[t]:+.0f}, back {back[0]} later")
            elif step > args.times * max(beside, 1.0) and not (held and step < 2 * args.least):
                found.setdefault(t + 1, []).append(f"jump {name} {d[t]:+.0f} (beside {beside:.1f})")
    print(f"{len(shots)} frames, {parts} parts ({args.rows} rows from the top, {args.cols} columns)")
    for frame in sorted(found):
        notes = found[frame]
        print(f"frame {frame:4d}: {len(notes)} parts: " + "; ".join(notes[:6]) + (" …" if len(notes) > 6 else ""))
    if not found:
        print("no jump, no blink")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
