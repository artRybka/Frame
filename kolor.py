"""Kolor sketch: nearest palettes in his catalogue (read only from the NAS).
Writes kolor-wyniki.png and kolor-wyniki.json next to itself."""
import io, json, os, sys, urllib.parse, urllib.request
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

H = "http://192.100.3.185:8099"
T = open(os.path.expanduser("~/.config/frame/nas-token")).read().strip()
OUT = Path(__file__).with_suffix("")
PRIVATE = ("own", "photo", "photos", "icloud", "album")


def get(path, raw=False, **q):
    url = H + path + ("?" + urllib.parse.urlencode(q, doseq=True) if q else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + T})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    return data if raw else json.loads(data)


def oklab(hexes):
    rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], dtype=np.float64) / 255
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806985808, 0.1073979210], [0.0883024619, 0.2817188376, 0.6299787005]])
    lms = np.cbrt(lin @ m1.T)
    m2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])
    return lms @ m2.T


# 1. Every work's palette (paged; a few minutes).
items, offset = [], 0
while True:
    page = get("/api/library/items", limit=200, offset=offset)
    got = page["items"]
    items += got
    offset += len(got)
    if not got or offset >= page["total"]:
        break
    if offset % 20000 < 200:
        print("read", offset, "of", page["total"], file=sys.stderr)
works = [i for i in items if i.get("colors") and i["id"].split(":")[0] not in PRIVATE and i.get("kind") not in PRIVATE]
print("works with palettes:", len(works), "of", len(items))
K = 8
P = np.zeros((len(works), K, 3))
W = np.zeros((len(works), K))
for n, w in enumerate(works):
    sw = sorted(w["colors"], key=lambda s: -s["weight"])[:K]
    P[n, : len(sw)] = oklab([s["hex"] for s in sw])
    W[n, : len(sw)] = [max(s["weight"], 1e-4) for s in sw]
W /= W.sum(1, keepdims=True)
index = {w["id"]: n for n, w in enumerate(works)}


def distance(n):
    """Sinkhorn (approximate earth mover's) distance from work n to every work."""
    a, pa = W[n], P[n]
    cost = np.linalg.norm(pa[None, :, None, :] - P[:, None, :, :], axis=-1)  # (N, K, K)
    kern = np.exp(-cost / 0.02)
    u = np.ones((len(P), K))
    v = np.ones((len(P), K))
    for _ in range(80):
        u = a[None, :] / np.maximum(np.einsum("nij,nj->ni", kern, v), 1e-30)
        v = W / np.maximum(np.einsum("nij,ni->nj", kern, u), 1e-30)
    plan = u[:, :, None] * kern * v[:, None, :]
    return (plan * cost).sum((1, 2))


# 2. Works asked: a few well-known ones of his catalogue.
WANT = [("Water Lilies", "Monet"), ("Great Wave", "Hokusai"), ("Milkmaid", "Vermeer"),
        ("Starry Night", "Gogh"), ("Sunday on La Grande", "Seurat"), ("Hay", "Monet")]
asked = []
for title, artist in WANT:
    found = [w for w in works if title.lower() in (w.get("title") or "").lower() and artist.lower() in (w.get("artist") or "").lower()]
    if found:
        asked.append(found[0])
asked = asked[:4]
rows = []
for w in asked:
    n = index[w["id"]]
    d = distance(n)
    d[n] = 9
    alone = [works[i]["id"] for i in np.argsort(d)[:6]]
    try:
        near = get("/api/debug/seen", item=w["id"], by="subject", count=400)["ids"]
    except Exception:
        near = []
    near = [i for i in near if i in index and i != w["id"]]
    subject = sorted(near, key=lambda i: d[index[i]])[:6]
    rows.append({"asked": w["id"], "alone": alone, "subject": subject,
                 "dist_alone": [round(float(d[index[i]]), 3) for i in alone],
                 "dist_subject": [round(float(d[index[i]]), 3) for i in subject]})
    print(w["title"], "->", [round(float(d[index[i]]), 3) for i in alone])
(OUT.parent / "kolor-wyniki.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))

# 3. The sheet.
by_id = {w["id"]: w for w in works}
TH = 200
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 22)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 15)
except OSError:
    font = small = ImageFont.load_default()


def tile(item_id):
    try:
        img = Image.open(io.BytesIO(get(f"/api/library/items/{urllib.parse.quote(item_id, safe=':')}/thumb", raw=True))).convert("RGB")
    except Exception:
        img = Image.new("RGB", (TH, TH), (200, 200, 200))
    img.thumbnail((TH, TH))
    cell = Image.new("RGB", (TH, TH + 46), (245, 240, 232))
    cell.paste(img, ((TH - img.width) // 2, (TH - img.height) // 2))
    x = 0
    sw = sorted(by_id[item_id]["colors"], key=lambda s: -s["weight"])[:K]
    total = sum(s["weight"] for s in sw) or 1
    draw = ImageDraw.Draw(cell)
    for s in sw:
        width = round(TH * s["weight"] / total)
        draw.rectangle([x, TH + 6, x + width, TH + 22], fill=s["hex"])
        x += width
    title = (by_id[item_id].get("title") or "")[:26]
    draw.text((0, TH + 26), title, fill=(60, 50, 40), font=small)
    return cell


GAP = 12
width = (TH + GAP) * 13 + 60
height = 70 + len(rows) * (TH + 46 + 50)
sheet = Image.new("RGB", (width, height), (245, 240, 232))
draw = ImageDraw.Draw(sheet)
draw.text((20, 20), "Szkic: „Kolor” — dzieła o najbliższej palecie (z Twojego katalogu, paski jak dziś)", fill=(30, 25, 20), font=font)
y = 70
for row in rows:
    draw.text((20, y), "Dzieło", fill=(120, 110, 100), font=small)
    draw.text((20 + TH + GAP + 30, y), "Sam Kolor", fill=(120, 110, 100), font=small)
    draw.text((20 + (TH + GAP) * 7 + 60, y), "Kolor + Treść", fill=(120, 110, 100), font=small)
    y += 22
    sheet.paste(tile(row["asked"]), (20, y))
    for k, i in enumerate(row["alone"]):
        sheet.paste(tile(i), (20 + (TH + GAP) * (k + 1) + 30, y))
    for k, i in enumerate(row["subject"]):
        sheet.paste(tile(i), (20 + (TH + GAP) * (k + 7) + 60, y))
    y += TH + 46 + 28
sheet.save(OUT.parent / "kolor-wyniki.png")
print("saved", OUT.parent / "kolor-wyniki.png")
