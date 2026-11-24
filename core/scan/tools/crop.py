"""crop.py <crop binary> [<photo> <logits.npy> <sure>]…: the core's look at museum photographs from the crop
model's answer (`frame_crop_find`, `frame_crop_letterbox`) against the server's `imaging/crop_model.py`: the
letterboxed photograph, the verdict, how far apart the corners are (px). Without photographs, made-up ones and
made-up masks. Run from `server/`: `uv run python ../core/scan/tools/crop.py <build>/crop`. (The model's own
answers come from `Kadr.mlpackage` on the phone, or from its PyTorch weights on the Mac.)

crop.py <crop binary> plates [<photo> <x0,y0,…,y3>]…: a print's sheet cut down round its impression
(`frame_crop_plate`) against `crop_model.plate`, on photographs and the sheets found on them; without
any, on made-up sheets."""
import subprocess, sys, tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from frame_server.imaging import crop_model as cm

binary = sys.argv[1]
shm = Path(tempfile.mkdtemp(prefix="crop-"))
rng = np.random.default_rng(7)


def made_up(n):
    """A wall with a framed work on it a little turned, and masks a model might give of it."""
    w, h = (int(v) for v in rng.integers(500, 1025, 2))
    wall = np.full((h, w, 3), rng.integers(90, 200, 3), np.uint8)
    wall = (wall + rng.normal(0, 4, wall.shape)).clip(0, 255).astype(np.uint8)
    cx, cy = w / 2 + rng.normal(0, w / 20), h / 2 + rng.normal(0, h / 20)
    fw, fh = w * rng.uniform(0.5, 0.8), h * rng.uniform(0.5, 0.8)
    turn = rng.normal(0, 2.0 if n % 3 else 6.0)
    frame = cv2.boxPoints(((cx, cy), (fw, fh), turn))
    work = cv2.boxPoints(((cx, cy), (fw * 0.8, fh * 0.8), turn))
    cv2.fillPoly(wall, [np.round(frame * 16).astype(np.int32)], (60, 40, 20), cv2.LINE_AA, 4)
    cv2.fillPoly(wall, [np.round(work * 16).astype(np.int32)], tuple(int(v) for v in rng.integers(0, 255, 3)), cv2.LINE_AA, 4)
    _, box = cm.letterbox(wall)
    ox, oy, nw, nh = box
    logits = np.full((2, cm.SIDE, cm.SIDE), -6.0, np.float32)
    for c, quad in enumerate((work, frame)):
        m = np.zeros((cm.SIDE, cm.SIDE), np.float32)
        q = quad * [nw / w, nh / h] + [ox, oy] + rng.normal(0, 1.2, (4, 2))
        cv2.fillPoly(m, [np.round(q * 16).astype(np.int32)], 1.0, cv2.LINE_AA, 4)
        logits[c] = (cv2.GaussianBlur(m, (7, 7), 0) - 0.5) * 14 + rng.normal(0, 0.8, m.shape)
    return wall, logits.astype(np.float32), float(rng.choice([0.05, 0.5, 0.95]))


def core(rgb, logits, sure):
    np.save(shm / "p.npy", np.ascontiguousarray(rgb))
    np.save(shm / "l.npy", np.ascontiguousarray(logits))
    said = subprocess.run([binary, str(shm / "p.npy"), str(shm / "l.npy"), repr(sure)], capture_output=True, text=True, check=True)
    lines = said.stdout.splitlines()
    quads = [None if l == "-" else np.array([float(v) for v in l.split()]).reshape(4, 2) for l in lines[1:3]]
    return int(lines[0]), quads


def boxed(rgb):
    np.save(shm / "p.npy", np.ascontiguousarray(rgb))
    said = subprocess.run([binary, "box", str(shm / "p.npy"), str(shm / "x.npy")], capture_output=True, text=True, check=True)
    return np.load(shm / "x.npy").reshape(3, cm.SIDE, cm.SIDE), tuple(int(v) for v in said.stdout.split())


def made_up_print(n):
    """A sheet of paper on a dark board, an impression on it (a caption under it now and then)."""
    w, h = (int(v) for v in rng.integers(600, 1025, 2))
    board = np.full((h, w, 3), rng.integers(30, 80, 3), np.uint8)
    sx0, sy0 = int(w * rng.uniform(0.05, 0.15)), int(h * rng.uniform(0.05, 0.15))
    sx1, sy1 = int(w * rng.uniform(0.85, 0.95)), int(h * rng.uniform(0.85, 0.95))
    board[sy0:sy1, sx0:sx1] = rng.integers(215, 245, 3)
    share = rng.uniform(0.4, 0.95)
    iw, ih = int((sx1 - sx0) * share), int((sy1 - sy0) * share * rng.uniform(0.8, 1.0))
    ix, iy = sx0 + (sx1 - sx0 - iw) // 2 + int(rng.integers(-10, 11)), sy0 + (sy1 - sy0 - ih) // 3
    y, x = np.mgrid[0:ih, 0:iw]
    ink = ((x * (3 + n % 4) + y * 7) % 23 < 9)[..., None] * rng.integers(60, 160, 3)
    board[iy : iy + ih, ix : ix + iw] = (board[iy : iy + ih, ix : ix + iw] - ink).clip(0, 255)
    if n % 3 == 0:
        cv2.putText(board, "Title of the print", (ix, iy + ih + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 40, 40), 1)
    board = (board + rng.normal(0, 2, board.shape)).clip(0, 255).astype(np.uint8)
    sheet = [[sx0 / w, sy0 / h], [sx1 / w, sy0 / h], [sx1 / w, sy1 / h], [sx0 / w, sy1 / h]]
    return board, sheet


def plated(rgb, sheet):
    np.save(shm / "p.npy", np.ascontiguousarray(rgb))
    corners = [repr(float(v)) for c in sheet for v in c]
    said = subprocess.run([binary, "plate", str(shm / "p.npy"), repr(cm.PLATE_OVER), *corners], capture_output=True, text=True, check=True)
    lines = said.stdout.splitlines()
    quads = [None if l == "-" else np.array([float(v) for v in l.split()]).reshape(4, 2) for l in lines[1:3]]
    return int(lines[0]), quads


if sys.argv[2:3] == ["plates"]:
    sheets = []
    given = sys.argv[3:]
    for n in range(0, len(given), 2):
        corners = [float(v) for v in given[n + 1].split(",")]
        sheets.append((Path(given[n]).name, np.asarray(Image.open(given[n]).convert("RGB")), [corners[i : i + 2] for i in range(0, 8, 2)]))
    if not sheets:
        sheets = [(f"made up {n}", *made_up_print(n)) for n in range(30)]
    worst, differ, cut = 0.0, 0, 0
    for name, rgb, sheet in sheets:
        made, (mine, alone) = plated(rgb, sheet)
        want = cm.plate(rgb, sheet)
        h, w = rgb.shape[:2]
        if bool(made) != (want is not None) or (want is not None and (alone is None) != (want[1] is None)):
            differ += 1
            print(f"{name:24s} {w}x{h} core {'cut' if made else 'sheet'}, server {'sheet' if want is None else 'cut'}")
            continue
        far = 0.0
        if want is not None:
            cut += 1
            far = float(np.abs(mine - np.array(want[0])).max() * max(w, h))
            if alone is not None:
                far = max(far, float(np.abs(alone - np.array(want[1])).max() * max(w, h)))
        worst = max(worst, far)
        print(f"{name:24s} {w}x{h} {'cut' if made else 'sheet':5s} {far:.3f} px")
    print(f"{len(sheets)} sheets, {cut} cut down, {differ} differ, corners at most {worst:.3f} px apart")
    sys.exit(1 if differ else 0)

VERDICTS = {0: "whole", 1: "cut", 2: "unsure"}
cases = []
given = sys.argv[2:]
for n in range(0, len(given), 3):
    rgb = np.asarray(Image.open(given[n]).convert("RGB"))
    cases.append((Path(given[n]).name, rgb, np.load(given[n + 1]).astype(np.float32), float(given[n + 2])))
if not cases:
    for n in range(30):
        cases.append((f"made up {n}", *made_up(n)))
worst = 0.0
differ = 0
for name, rgb, logits, sure in cases:
    x, box = cm.letterbox(rgb)
    mine, my_box = boxed(rgb)
    apart = float(np.abs(mine - x.transpose(2, 0, 1)).max())
    verdict, (work, surround) = core(rgb, logits, sure)
    want = cm.find(rgb, logits, sure)
    h, w = rgb.shape[:2]
    far = []
    for got, wanted in ((work, want.work), (surround, want.surround)):
        if (got is None) != (wanted is None):
            far.append("one has none")
        elif got is not None:
            far.append(f"{np.abs(got - np.array(wanted)).max() * max(w, h):.3f}")
        else:
            far.append("-")
    same = VERDICTS[verdict] == want.verdict and my_box == box
    differ += not same or "one has none" in far
    worst = max([worst] + [float(f) for f in far if f not in ("-", "one has none")])
    print(f"{name:24s} {w}x{h} box {'=' if my_box == box else my_box} letterbox {apart:.0f} "
          f"{VERDICTS[verdict]:6s}{'' if same else ' ≠ ' + want.verdict:9s} work {far[0]} px, surround {far[1]} px")
print(f"{len(cases)} photographs, {differ} differ, corners at most {worst:.3f} px apart")
