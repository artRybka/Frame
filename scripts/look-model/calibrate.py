"""SigLIP floors set against Gemini's on the NAS (read only). Prints a small table."""
import json, os, random, statistics, urllib.parse, urllib.request
H = os.environ["FRAME_HOST"]  # http://<nas>:8099
T = open(os.path.expanduser(os.environ.get("FRAME_TOKEN_FILE", "~/.config/frame/nas-token"))).read().strip()
def get(path, **q):
    url = H + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + T})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)
state = get("/api/debug/seen", count=1)
share = state["done"] / state["total"]
print("share", round(share, 3))
random.seed(7)
works = []
for text in ["oil painting", "drawing", "print", "watercolour", "photograph", "landscape", "portrait"]:
    ids = get("/api/debug/seen", text=text, count=400)["ids"]
    works += random.sample(ids, 5)
GEM = {"": 0.50, "subject": 0.58, "style": 0.57}
cands = [round(0.40 + 0.01 * k, 2) for k in range(56)]
for by, floor in GEM.items():
    gem, sig = [], []
    for w in works:
        try:
            g = get(f"/api/debug/looks/{urllib.parse.quote(w, safe=':')}", by=by, count=2000)["scores"]
            s = get("/api/debug/seen", item=w, by=by, count=2000)["scores"]
        except Exception as e:
            continue
        if not g or not s:
            continue
        gem.append(sum(1 for x in g if x >= floor)); sig.append(s)
    target = statistics.median(gem) * share
    best = min(cands, key=lambda f: abs(statistics.median([sum(1 for x in s if x >= f) for s in sig]) - target))
    print(f"by={by!r} works={len(gem)} gemini median {statistics.median(gem)} (x share {target:.0f}) -> siglip floor {best}")
    for f in cands[::5]:
        print("   ", f, statistics.median([sum(1 for x in s if x >= f) for s in sig]))
    print("    siglip top1/top10/top50 median:", [round(statistics.median([s[k] for s in sig if len(s) > k]), 3) for k in (0, 9, 49)])
WORDS = {"mglisty poranek nad wodą": "misty morning over water", "zimowy pejzaż ze śniegiem": "winter landscape with snow",
         "martwa natura z kwiatami": "still life with flowers", "portret starej kobiety": "portrait of an old woman",
         "statek na wzburzonym morzu": "ship on a stormy sea", "zachód słońca": "sunset", "koń": "horse",
         "miasto nocą": "city at night", "dzieci bawiące się": "children playing", "wnętrze z oknem": "interior with a window",
         "pies": "dog", "parowiec na rzece": "steamboat on a river"}
print("words: gemini shown | siglip best, count within best-nb for nb 0.01..0.06, floor-ish")
for pl, en in WORDS.items():
    try:
        g = get("/api/looks/search", q=pl)
        gn = len(g.get("items", []))
    except Exception as e:
        gn = f"err {e}"
    s = get("/api/debug/seen", text=en, count=600)["scores"]
    b = s[0]
    print(f"  {en[:28]:28s} gem {gn} | best {b:.3f} " + " ".join(str(sum(1 for x in s if x >= b - nb / 100)) for nb in range(1, 7)) + f" | s@60 {s[59]:.3f}")
