"""Weights sheets: Treść (by=subject) and Forma (by=style) with the other
layer taken off by off = 0 / 0.25 / 0.5 / 0.75 / 1 (GET /api/debug/seen,
read only). Writes wagi-tresc.png, wagi-forma.png, wagi.json."""
import io, json, sys
from collections import Counter
from pathlib import Path

sys.argv = ["x"]
exec(open(Path(__file__).parent / "tresc.py").read().split("def variants")[0])
from PIL import Image, ImageDraw, ImageFont

WORKS = ["mnk:374514", "rijks:200126050", "rijks:200108369", "wikiart:57727255edc2cb3880c4c51a", "wmc:4532878"]
OFFS = [0, 0.25, 0.5, 0.75, 1]
N = 7
TH = 150
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 24)
    mid = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 17)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 12)
except OSError:
    font = mid = small = ImageFont.load_default()
thumbs = {}


def tile(i):
    if i not in thumbs:
        try:
            img = Image.open(io.BytesIO(get(f"/api/library/items/{urllib.parse.quote(i, safe=':')}/thumb", raw=True))).convert("RGB")
        except Exception:
            img = Image.new("RGB", (TH, TH), (200, 200, 200))
        img.thumbnail((TH, TH))
        cell = Image.new("RGB", (TH, TH + 32), (245, 240, 232))
        cell.paste(img, ((TH - img.width) // 2, (TH - img.height) // 2))
        m = meta(i)
        d = ImageDraw.Draw(cell)
        d.text((0, TH + 2), tech(m), fill=(150, 60, 40), font=small)
        d.text((0, TH + 16), (m.get("title") or "")[:22], fill=(60, 50, 40), font=small)
        thumbs[i] = cell
    return thumbs[i]


out = {}
for by, name in (("subject", "Treść"), ("style", "Forma")):
    rows = []
    for w in WORKS:
        r = {}
        for off in OFFS:
            ids = [i for i in get("/api/debug/seen", item=w, by=by, count=30, off=off)["ids"] if i.split(":")[0] not in PRIVATE][:N]
            r[off] = ids
            print(name, meta(w).get("title", "")[:30], off, dict(Counter(tech(meta(i)) for i in ids)), flush=True)
        rows.append((w, r))
    out[name] = [{"asked": w, **{str(k): v for k, v in r.items()}} for w, r in rows]
    GAP, LABEL = 8, 90
    width = 20 + TH + 24 + LABEL + N * (TH + GAP) + 20
    block = len(OFFS) * (TH + 32 + 8) + 34
    sheet = Image.new("RGB", (width, 66 + len(rows) * block), (245, 240, 232))
    d = ImageDraw.Draw(sheet)
    other = "formy" if by == "subject" else "treści"
    d.text((20, 18), f"„{name}” sama: waga odejmowanej {other} 0 / 0,25 / 0,5 / 0,75 / 1 (dziś w aplikacji 0,5)", fill=(30, 25, 20), font=font)
    y = 66
    for w, r in rows:
        sheet.paste(tile(w), (20, y + 10))
        for k, off in enumerate(OFFS):
            yy = y + k * (TH + 32 + 8)
            d.text((20 + TH + 24, yy + TH // 2), f"waga {off}", fill=(30, 25, 20), font=mid)
            for n, i in enumerate(r[off]):
                sheet.paste(tile(i), (20 + TH + 24 + LABEL + n * (TH + GAP), yy))
        y += block
        d.line([(20, y - 18), (width - 20, y - 18)], fill=(200, 190, 175), width=2)
    sheet.save(OUT / f"wagi-{'tresc' if by == 'subject' else 'forma'}.png")
(OUT / "wagi.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print("saved")
