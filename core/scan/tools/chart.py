"""chart.py <chart binary>: the core's putting of a chart's colours (`frame_scan_chart_file`) against the
server's `colorchecker.apply`, on drawn charts (one under a warm lamp, one in a dim room, one with the
photograph's top in it) and pictures of every value, and how long 48 MP take. Run from `server/`:
`uv run python ../core/scan/tools/chart.py <build>/chart`."""
import subprocess, sys, time
from pathlib import Path

import numpy as np

sys.path.insert(0, "tests")
import test_colorchecker as drawn
from frame_server.imaging import colorchecker

binary = sys.argv[1]
shm = Path("/dev/shm/chart")
shm.mkdir(exist_ok=True)
rng = np.random.default_rng(3)
board = drawn._board(colorchecker.REFERENCE.astype(np.uint8))
ramp = np.stack([*np.meshgrid(np.arange(256), np.arange(256), indexing="ij"), np.full((256, 256), 255)], -1)
ramp = ramp.astype(np.uint8)


def core(picture):
    np.save(shm / "p.npy", picture)
    said = subprocess.run([binary, str(shm / "p.npy"), str(shm / "tables")], capture_output=True, text=True, check=True)
    return np.load(shm / "p.npy"), float(said.stdout.strip())


for shot in (drawn._photographed, drawn._in_a_dim_room, drawn._under_a_lamp):
    photo = shot(drawn._scene(board))
    chart = colorchecker.find(photo)
    (shm / "tables").write_bytes(colorchecker.tables(chart))
    pictures = {
        "scene": photo,
        "noise": rng.integers(0, 256, (1200, 1700, 3), dtype=np.uint8),
        "ramp rg": ramp, "ramp gb": ramp[..., [2, 0, 1]], "ramp br": ramp[..., [1, 2, 0]],
    }
    for label, picture in pictures.items():
        made, took = core(picture)
        apart = np.abs(made.astype(np.int16) - colorchecker.apply(picture, chart).astype(np.int16))
        print(f"{shot.__name__:15s} from grey {chart.lightest} {label:8s} {int((apart > 0).sum()):3d} of "
              f"{apart.size} differ ({(apart > 0).mean():.1e}), most {int(apart.max())}, {took:.3f} s")
whole = rng.integers(0, 256, (8064, 6048, 3), dtype=np.uint8)
began = time.perf_counter()
want = colorchecker.apply(whole, chart)
python = time.perf_counter() - began
made, took = core(whole)
apart = np.abs(made.astype(np.int16) - want.astype(np.int16))
print(f"48 MP: python {python:.2f} s, core {took:.2f} s, {(apart > 0).mean():.1e} differ, most {int(apart.max())}")
