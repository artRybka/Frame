"""golden.py <scans folder> <token prefix> <out>: one kept scan merged by the Python code, with what
went into and came out of each step written down: the C++ core is held against it step by step.

<out>/<step>.<n>/call.txt lists the step's n-th call: one line per value, `in.<k>…` what it was given
and `out.<k>…` what it gave back; an array is a file in <out>/arrays/ (by its content, written once).
His photographs: never into the repository."""
import sys, json, hashlib, functools
from pathlib import Path
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
from frame_server.imaging import reflections as R
from frame_server.imaging.cut import valid

STEPS = ['_marks', '_lay', '_settled', '_fine', '_off', '_field', '_about', '_even', '_hide', '_counts',
         '_alone', '_told', '_own', '_one', '_toned', '_outward', '_rim', '_tellings', '_from_sides',
         '_finer', '_reflection', '_apart', '_shared', '_kept', '_grain', '_mend', '_reach', '_line',
         '_carried', '_shown', '_veiled', '_level', '_around', '_subtract']
#: Steps called very often: only so many of their calls are kept.
FEW = {'_off': 3, '_fine': 4, '_about': 2, '_counts': 6, '_reach': 8, '_apart': 4, '_shared': 4, '_tellings': 3}

root, prefix, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
(out / 'arrays').mkdir(parents=True, exist_ok=True)
calls: dict[str, int] = {}

def array(a: np.ndarray) -> str:
    a = np.ascontiguousarray(a)
    if a.dtype == bool: a = a.astype(np.uint8)
    if a.dtype == np.int64: a = a.astype(np.int32)
    name = hashlib.sha1(a.tobytes() + str((a.shape, a.dtype)).encode()).hexdigest()[:16] + '.npy'
    if not (out / 'arrays' / name).exists(): np.save(out / 'arrays' / name, a)
    return name

def lines(key: str, v) -> list[str]:
    if v is None: return [f'{key} none']
    if isinstance(v, (bool, np.bool_)): return [f'{key} {int(v)}']
    if isinstance(v, (int, np.integer)): return [f'{key} {int(v)}']
    if isinstance(v, (float, np.floating)): return [f'{key} {float(v)!r}']
    if isinstance(v, np.ndarray): return [f'{key} {array(v)} {v.dtype} {"x".join(map(str, v.shape))}']
    if isinstance(v, R._View):
        got = []
        for f in ('light', 'side', 'hidden', 'shows', 'photo', 'seen'): got += lines(f'{key}.{f}', getattr(v, f))
        return got + lines(f'{key}.gains', np.array(v.gains, np.float64))
    if isinstance(v, (list, tuple)):
        if v and all(hasattr(k, 'pt') for k in v):  # key points
            return lines(key, np.array([[k.pt[0], k.pt[1], k.size, k.angle, k.response, k.octave] for k in v], np.float64))
        got = [f'{key}.len {len(v)}']
        for i, each in enumerate(v): got += lines(f'{key}.{i}', each)
        return got
    if callable(v): return [f'{key} function']
    raise TypeError(f'{key}: {type(v)}')

def copy(v):
    """As it is now: some steps change what they are given (the views' light, hidden, shows)."""
    if isinstance(v, np.ndarray): return v.copy()
    if isinstance(v, R._View): return R._View(v.light.copy(), v.side, v.hidden, v.shows, v.photo, v.seen, v.gains)
    if isinstance(v, (list, tuple)) and not (v and all(hasattr(k, 'pt') for k in v)): return type(v)(copy(e) for e in v)
    return v

def written(name: str, n: int, given, gave) -> None:
    folder = out / f'{name}.{n}'; folder.mkdir(exist_ok=True)
    text: list[str] = []
    for i, a in enumerate(given): text += lines(f'in.{i}', a)
    text += lines('out', gave)
    (folder / 'call.txt').write_text('\n'.join(text) + '\n')

def recorded(name: str, fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        n = calls.get(name, 0); calls[name] = n + 1
        keep = n < FEW.get(name, 99)
        given = [copy(a) for a in args] + [copy(v) for v in kwargs.values()] if keep else None
        gave = fn(*args, **kwargs)
        if name == '_finer' and gave is not None:
            inner = gave
            def fine(to_part, glare):
                m = calls.get('fine', 0); calls['fine'] = m + 1
                made = inner(to_part, glare)
                if m < 6: written('fine', m, [to_part, glare], made)
                return made
            gave = fine
        if keep:
            # What a step changed in place is part of what it gave back.
            after = [a for a in args if isinstance(a, list) and a and isinstance(a[0], R._View)] if name in ('_even', '_hide') else []
            written(name, n, given, [gave, *after] if after else gave)
        return gave
    return wrapper

for name in STEPS: setattr(R, name, recorded(name, getattr(R, name)))

info = next(s for s in json.load(open(root / 'scans.json')) if s['token'].startswith(prefix))
folder = root / info['token']
def whole(path, side=None):
    with Image.open(path) as img:
        if side is not None: img.draft('RGB', (side, side))
        return np.asarray(img.convert('RGB'))
first = whole(folder / 'first.jpg'); sides = [whole(p, R.MATCH_SIDE) for p in sorted(folder.glob('side*.jpg'))]
quad = valid(info['corners'])
made = R.merge(first, sides, quad, True)
written('merge', 0, [first, sides, np.array(quad, np.float64), True], [made.image, made.used, made.removed, made.doubt])
print(info['token'], 'used', made.used, 'removed', made.removed, 'doubt', made.doubt, getattr(made, 'took', ''))
print(' '.join(f'{k}×{v}' for k, v in calls.items()))
