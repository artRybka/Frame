"""MobileCLIP trial, part 2: Gemini's "Treść" (subject) and "Forma" (style)
neighbours of 40 works of the pool, plus each pool work's medium.
Run on the Mac next to pool.json: python3 export2.py (stdlib; token from
~/.config/frame/nas-token, never printed). Writes gemini2.json."""
import json, os, random, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = os.environ.get("FRAME_URL", "http://192.100.3.185:8099").rstrip("/")
TOKEN = (Path.home() / ".config/frame/nas-token").read_text().strip()
HERE = Path(__file__).resolve().parent


def get(path, params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as err:
            if err.code in (404, 409, 410, 422):
                return None
        except Exception:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def near(item_id, by):
    enc = urllib.parse.quote(item_id, safe=":")
    a = get(f"/api/debug/looks/{enc}", {"count": 400, "by": by}) or {"items": [], "scores": []}
    return [[i["id"], s] for i, s in zip(a["items"], a["scores"])]


def meta(item_id):
    enc = urllib.parse.quote(item_id, safe=":")
    m = get(f"/api/library/items/{enc}") or {}
    return item_id, {k: m.get(k) for k in ("medium", "artist", "date_text", "keywords", "subjects", "styles", "terms")}


def main():
    pool = json.loads((HERE / "pool.json").read_text())
    g = json.loads((HERE / "gemini.json").read_text())
    have = {p.name[:-4] for p in (HERE / "out").glob("*.jpg")}
    ids = [i for i in pool if i.replace(":", "_").replace("/", "~") in have]
    rnd = random.Random(1120)
    works = [w for w in g["works"] if w in pool] + rnd.sample(ids, 25)
    out = {"works": {}, "meta": {}}
    for w in works:
        out["works"][w] = {"subject": near(w, "subject"), "style": near(w, "style"), "both": near(w, "")}
        print("work", w, len(out["works"][w]["subject"]), flush=True)
    with ThreadPoolExecutor(6) as ex:
        for n, (i, m) in enumerate(ex.map(meta, ids), 1):
            out["meta"][i] = m
            if n % 1000 == 0:
                print("meta", n, flush=True)
    (HERE / "gemini2.json").write_text(json.dumps(out, ensure_ascii=False))
    print("done", len(out["works"]), len(out["meta"]), (HERE / "gemini2.json").stat().st_size // 1000, "kB", flush=True)


if __name__ == "__main__":
    main()
