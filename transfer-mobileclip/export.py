"""Trial "MobileCLIP zamiast odcisków Gemini" (2026-11-20): run on the Mac
(network only, no MPS). Picks a pool of catalogue works, asks the Frame
server what Gemini's look fingerprints find for the trial's queries, and
downloads the pool's thumbnails into ./out, then out.zip.

Run: python3 export.py   (Python 3.10+, stdlib only)
Env: FRAME_URL (default http://192.100.3.185:8099); token read from
~/.config/frame/nas-token (never printed).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = os.environ.get("FRAME_URL", "http://192.100.3.185:8099").rstrip("/")
TOKEN = (Path.home() / ".config/frame/nas-token").read_text().strip()
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RANDOM = 8000

# Words typed in Szukaj (Polish as typed; English for MobileCLIP's text side,
# as the phone's Translation would give it).
WORDS = {
    "mglisty poranek nad wodą": "misty morning over water",
    "zimowy pejzaż ze śniegiem": "winter landscape with snow",
    "martwa natura z kwiatami": "still life with flowers",
    "portret starej kobiety": "portrait of an old woman",
    "statek na wzburzonym morzu": "ship on a stormy sea",
    "zachód słońca": "sunset",
    "koń": "horse",
    "nocne miasto": "city at night",
    "drzeworyt japoński": "japanese woodcut",
    "gruba faktura farby": "thick impasto brushwork",
    "Zwiastowanie": "the Annunciation",
    "dzieci bawiące się": "children playing",
    "wnętrze z oknem": "interior with a window",
    "kubizm": "cubism",
    "akwarela z łodziami": "watercolour with boats",
}
# Works whose "Podobne do" is compared: the first hit of each search.
WORKS = [
    "Monet Water Lilies", "van Gogh", "Rembrandt", "Hokusai", "Vermeer",
    "Annunciation", "Crucifixion", "Chełmoński", "Turner", "Degas",
    "Hiroshige", "Cézanne", "Matejko", "Klimt", "still life",
]


def get(path: str, params: dict | None = None, raw: bool = False, tries: int = 3):
    url = BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            return data if raw else json.loads(data)
        except urllib.error.HTTPError as err:
            if err.code in (404, 410, 409, 422):
                print("http", err.code, path, flush=True)
                return None
            if attempt == tries - 1:
                raise
        except Exception:
            if attempt == tries - 1:
                raise
        time.sleep(3 * (attempt + 1))
    return None


def page(params: dict, want: int) -> list[dict]:
    found: list[dict] = []
    offset = 0
    while len(found) < want:
        p = get("/api/library/items", {**params, "kind": "artwork", "limit": 200, "offset": offset})
        items = (p or {}).get("items") or []
        if not items:
            break
        found += items
        offset += len(items)
        if offset >= p.get("total", 0):
            break
    return found[:want]


def summary(it: dict) -> dict:
    return {k: it.get(k) for k in ("id", "title", "artist", "year", "source")}


def gemini() -> dict:
    """Gemini's answers: words (120 nearest), works (300 nearest, both)."""
    out: dict = {"words": {}, "works": {}, "items": {}}
    for pl in WORDS:
        a = get("/api/looks/search", {"q": pl, "limit": 120}) or {"items": [], "scores": []}
        out["words"][pl] = list(zip([i["id"] for i in a["items"]], a["scores"]))
        for i in a["items"]:
            out["items"][i["id"]] = summary(i)
        print("words", pl, len(a["items"]), flush=True)
    for q in WORKS:
        hits = page({"q": q, "sort": "relevance"}, 1)
        if not hits:
            continue
        work = hits[0]
        enc = urllib.parse.quote(work["id"], safe=":")
        a = get(f"/api/debug/looks/{enc}", {"count": 300}) or {"items": [], "scores": []}
        out["works"][work["id"]] = {
            "asked": q,
            "near": list(zip([i["id"] for i in a["items"]], a["scores"])),
        }
        out["items"][work["id"]] = summary(work)
        for i in a["items"]:
            out["items"][i["id"]] = summary(i)
        print("work", q, work.get("title"), len(a["items"]), flush=True)
    return out


def one(item_id: str) -> str:
    name = item_id.replace(":", "_").replace("/", "~")
    path = OUT / f"{name}.jpg"
    if path.exists():
        return "kept"
    enc = urllib.parse.quote(item_id, safe=":")
    thumb = get(f"/api/library/items/{enc}/thumb", raw=True)
    if not thumb:
        return "noimage"
    path.write_bytes(thumb)
    return "ok"


def safe(item_id: str) -> str:
    try:
        return one(item_id)
    except Exception as err:  # noqa: BLE001
        print("error", item_id, type(err).__name__, str(err)[:120], flush=True)
        return "error"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    gfile = HERE / "gemini.json"
    if gfile.exists():
        g = json.loads(gfile.read_text())
    else:
        g = gemini()
        gfile.write_text(json.dumps(g, ensure_ascii=False))
    pfile = HERE / "pool.json"
    if pfile.exists():
        pool = json.loads(pfile.read_text())
    else:
        pool = dict(g["items"])
        for it in page({"sort": "random", "seed": 1120}, RANDOM):
            pool.setdefault(it["id"], summary(it))
        pfile.write_text(json.dumps(pool, ensure_ascii=False))
    print("pool:", len(pool), flush=True)
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(6) as ex:
        for n, r in enumerate(ex.map(safe, list(pool)), 1):
            counts[r] = counts.get(r, 0) + 1
            if n % 500 == 0:
                print(n, counts, flush=True)
    print("done", counts, flush=True)
    with zipfile.ZipFile(HERE / "out.zip", "w", zipfile.ZIP_STORED) as z:
        z.write(gfile, "gemini.json")
        z.write(pfile, "pool.json")
        for f in sorted(OUT.glob("*.jpg")):
            z.write(f, f"out/{f.name}")
    print("zip MB:", (HERE / "out.zip").stat().st_size // 1_000_000, flush=True)


if __name__ == "__main__":
    main()
