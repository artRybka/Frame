"""both.py <scans folder> <merge binary> <note.json> [token prefixes]: every kept scan merged by the
server's Python and by the C++ core, and how far the two photographs are apart, level by level."""
import json, subprocess, sys, time
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
from frame_server.imaging import reflections as R
from frame_server.imaging.cut import valid

root, binary, note_at = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
only = sys.argv[4:]
shm = Path("/dev/shm/both")
shm.mkdir(exist_ok=True)


def whole(path, side=None):
    with Image.open(path) as img:
        if side is not None:
            img.draft("RGB", (side, side))
        return np.asarray(img.convert("RGB"))


note = json.loads(note_at.read_text()) if note_at.exists() else {}
for s in json.load(open(root / "scans.json")):
    token, folder = s["token"], root / s["token"]
    quad = valid(s.get("corners") or [])
    if not quad or not (folder / "side1.jpg").is_file():
        continue
    if only and not any(token.startswith(o) for o in only):
        continue
    photo = whole(folder / "first.jpg")
    sides = [whole(p, R.MATCH_SIDE) for p in sorted(folder.glob("side*.jpg"))]
    began = time.perf_counter()
    m = R.merge(photo, sides, quad, True)
    python = time.perf_counter() - began
    np.save(shm / "first.npy", photo)
    names = []
    for n, side in enumerate(sides):
        np.save(shm / f"side{n}.npy", side)
        names.append(str(shm / f"side{n}.npy"))
    corners = [str(v) for point in quad for v in point]
    said = subprocess.run(
        [binary, str(shm / "first.npy"), str(shm / "out.npy"), "1", *corners, *names],
        capture_output=True, text=True, check=True,
    ).stdout
    core = json.loads(said.strip().splitlines()[-1])
    made = np.load(shm / "out.npy")
    apart = np.abs(made.astype(np.int16) - m.image.astype(np.int16))
    row = {
        "python": round(python, 2), "core": core["seconds"], "parts": core["took"],
        "python_parts": getattr(m, "took", {}),
        "same": bool(core["used"] == m.used and abs(core["removed"] - m.removed) < 1e-9 and core["doubt"] == m.doubt),
        "used": m.used, "removed": m.removed, "values": int(apart.size),
        "by1": int((apart >= 1).sum()), "by2": int((apart >= 2).sum()), "by4": int((apart >= 4).sum()),
        "by8": int((apart >= 8).sum()), "most": int(apart.max()),
    }
    note[token] = row
    note_at.write_text(json.dumps(note, indent=1))
    print(
        token[:6], "as told" if row["same"] else "TOLD APART", f"used {m.used} removed {m.removed}",
        f"| differ {100 * row['by1'] / row['values']:.3f}% by 1, {row['by2']} by 2+, {row['by4']} by 4+,"
        f" {row['by8']} by 8+, most {row['most']} | python {python:.1f} s, core {core['seconds']:.1f} s {core['took']}",
        flush=True,
    )
