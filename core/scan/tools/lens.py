"""lens.py <lens binary>: the core's straightening of a photograph (`frame_scan_straight_file`) and of corners
(`frame_scan_lens_points`) against the server's `imaging/lens.py`, by the one measured term and by a camera's
table about a middle that is not the photograph's, and how long 48 MP take. Run from `server/`:
`uv run python ../core/scan/tools/lens.py <build>/lens`."""
import subprocess, sys, time
from pathlib import Path

import numpy as np

from frame_server.imaging import lens

binary = sys.argv[1]
shm = Path("/dev/shm/lens")
shm.mkdir(exist_ok=True)
rng = np.random.default_rng(5)


def table(k1, count=42, more=0.0):
    """A camera's table that says `k1` (and a term more), as `tests/test_lens.py` draws one."""
    r = np.linspace(0, 1, count)
    return tuple(float(v) for v in k1 * r**2 + more * r**4)


def given(bend):
    if not bend.table:
        return [repr(bend.k1), "0.5", "0.5", "-"]
    (shm / "table").write_text("\n".join(repr(v) for v in bend.table))
    return ["0", repr(bend.centre[0]), repr(bend.centre[1]), str(shm / "table")]


def core(picture, bend):
    np.save(shm / "p.npy", picture)
    said = subprocess.run([binary, "straight", str(shm / "p.npy"), *given(bend)], capture_output=True, text=True, check=True)
    return np.load(shm / "p.npy"), float(said.stdout.strip())


def points(quad, size, bend, way):
    flat = [repr(v) for point in quad for v in point]
    said = subprocess.run([binary, way, str(size[0]), str(size[1]), *given(bend), *flat], capture_output=True, text=True, check=True)
    return [tuple(float(v) for v in line.split()) for line in said.stdout.splitlines()]


bends = {
    "measured": lens.Bend(k1=-0.023),
    "pincushion": lens.Bend(k1=0.031),
    "table": lens.Bend(table=table(-0.0235), centre=(0.5, 0.5)),
    "table off": lens.Bend(table=table(-0.026, 57, 0.004), centre=(0.5123, 0.4871)),
}
smooth = np.stack(np.meshgrid(np.arange(1600), np.arange(1200)), -1).astype(np.float32)
scene = np.stack([np.sin(smooth[..., 0] / 7) * 100 + 128, np.cos(smooth[..., 1] / 5) * 90 + 120,
                  np.sin((smooth[..., 0] + smooth[..., 1]) / 11) * 110 + 130], -1).clip(0, 255).astype(np.uint8)
pictures = {
    "noise": rng.integers(0, 256, (1200, 1600, 3), dtype=np.uint8),
    "scene": scene,
    "upright": rng.integers(0, 256, (1611, 1207, 3), dtype=np.uint8),
}
for name, bend in bends.items():
    for label, picture in pictures.items():
        made, took = core(picture, bend)
        apart = np.abs(made.astype(np.int16) - lens.straight(picture, bend).astype(np.int16))
        print(f"{name:10s} {label:8s} {int((apart > 0).sum()):4d} of {apart.size} differ ({(apart > 0).mean():.1e}), "
              f"most {int(apart.max())}, {took:.3f} s")
    worst = 0.0
    for size in ((8064, 6048), (6048, 8064), (4000, 3000)):
        quad = [(float(x), float(y)) for x, y in rng.random((40, 2))]
        quad += [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.5, 0.5)]
        for way, mine in (("moved", lens.moved), ("bent", lens.bent)):
            want = np.array(mine(quad, *size, bend))
            worst = max(worst, float(np.abs(np.array(points(quad, size, bend, way)) - want).max()))
    print(f"{name:10s} corners moved and back: at most {worst:.1e} apart")
whole = rng.integers(0, 256, (8064, 6048, 3), dtype=np.uint8)
for name in ("measured", "table off"):
    began = time.perf_counter()
    want = lens.straight(whole, bends[name])
    python = time.perf_counter() - began
    made, took = core(whole, bends[name])
    apart = np.abs(made.astype(np.int16) - want.astype(np.int16))
    print(f"48 MP {name}: python {python:.2f} s, core {took:.2f} s (with the file read and written), "
          f"{(apart > 0).mean():.1e} differ, most {int(apart.max())}")
