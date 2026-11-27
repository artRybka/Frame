"""restore.py <restore binary> [<picture>]…: the core's restorer steps around its model
(`frame_restore_descreen`, `frame_restore_colours`) against the server's `imaging/descreen.py` and
`restorer.py`: how far apart the two pictures are (levels of 255, mean and most), and whether both found
a screen and laid the drawing on its picture. Without pictures, made-up ones: paintings, printed ones,
small ones. The model's drawing is made up too (the picture enlarged four times, a little sharpened and
a little off in colour, or another picture). Run from `server/`: `uv run python
../core/scan/tools/restore.py <build>/restore`."""
import subprocess, sys, tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

from frame_server import restorer
from frame_server.imaging import descreen

binary = sys.argv[1]
shm = Path(tempfile.mkdtemp(prefix="restore-"))
rng = np.random.default_rng(11)


def painting(h, w):
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack([0.5 + 0.4 * np.sin(x / 90), 0.5 + 0.3 * np.cos(y / 70), 0.4 + 0.3 * np.sin((x + y) / 120)], -1)
    base = base + rng.normal(0, 0.03, (h, w, 1))
    for _ in range(30):
        cy, cx, r = rng.integers(0, h), rng.integers(0, w), rng.integers(10, 90)
        base[(y - cy) ** 2 + (x - cx) ** 2 < r * r] = rng.random(3)
    return np.clip(base, 0, 1)


def printed(base, period, angle):
    h, w = base.shape[:2]
    y, x = np.mgrid[0:h, 0:w]
    a = np.deg2rad(angle)
    u = (x * np.cos(a) + y * np.sin(a)) / period
    v = (-x * np.sin(a) + y * np.cos(a)) / period
    dot = np.hypot(u - np.round(u), v - np.round(v))
    ink = dot[..., None] < np.sqrt((1 - base) / np.pi)
    out = np.where(ink, 0.0, 1.0) * 0.85 + base * 0.15
    return np.asarray(Image.fromarray((out * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)))


def made_up():
    for h, w, period in ((600, 480, None), (1300, 1100, None), (700, 900, 3.4), (1400, 1200, 4.0), (1700, 1250, 3.0)):
        base = painting(h, w)
        yield f"{w}x{h}" + (f" printed {period}" if period else ""), (
            printed(base, period, 15) if period else (base * 255).astype(np.uint8)
        )


def run(*args):
    out = subprocess.run([binary, *map(str, args)], check=True, capture_output=True, text=True).stdout.split()
    return out


def apart(a, b):
    if a.shape != b.shape:
        return f"sizes {a.shape} {b.shape}"
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return f"mean {d.mean():.3f} most {d.max()} over 2: {(d > 2).mean() * 100:.2f}%"


pictures = [(p, np.asarray(Image.open(p).convert("RGB"))) for p in sys.argv[2:]] or list(made_up())
for name, rgb in pictures:
    np.save(shm / "p.npy", rgb)
    found, took = run("descreen", shm / "p.npy", shm / "d.npy")
    core = np.load(shm / "d.npy")
    want = np.asarray(descreen.descreened(Image.fromarray(rgb)))
    print(f"{name}: screen {len(descreen.screen(Image.fromarray(rgb)))} / core {found}, "
          f"descreened {apart(core, want)} ({took} s)")
    # The model's drawing: four times larger, a little sharper and warmer; and of another picture.
    h, w = want.shape[:2]
    big = cv2.resize(want, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    big = np.clip((big + 0.5 * (big - cv2.GaussianBlur(big, (0, 0), 3))) * (1.04, 1.0, 0.95), 0, 255).astype(np.uint8)
    for kind, drawn in (("drawn", big), ("another", np.ascontiguousarray(big[::-1]))):
        np.save(shm / "b.npy", drawn)
        laid, took = run("colours", shm / "d.npy", shm / "b.npy", restorer.DRAWN, shm / "c.npy")
        core = np.load(shm / "c.npy")
        k = restorer.LONGEST / max(drawn.shape[:2])
        # Brought to 2K as the core brings it (OpenCV's area; the server's own drawing goes by Pillow's
        # Lanczos, a step that is the model's drawing's alone): what follows is the server's.
        two = Image.fromarray(cv2.resize(drawn, (round(drawn.shape[1] * k), round(drawn.shape[0] * k)), interpolation=cv2.INTER_AREA))
        made = np.asarray(restorer.recoloured(Image.fromarray(want), restorer.fit((w, h), two)))
        same = np.array_equal(made, np.asarray(two))
        print(f"  {kind}: laid {'no' if same else 'yes'} / core {'yes' if laid == '1' else 'no'}, {apart(core, made)} ({took} s)")
