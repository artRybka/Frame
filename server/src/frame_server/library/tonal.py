"""The bar of colours of a painting: its tonal masses and its accents.

Mateusz 2026-11-21 21:37, of Czechowicz's „Chrystus ukazujący się
apostołom” (MNK), whose bar was four muddy browns and lacked the yellowish
white of the robe: the bar is to be „emanacja kolorystyki dzieła. Wrażenie,
z jakich kolorów składa się obraz”. The bar ``colors.analyse`` gives a
painting was the means of its four largest k-means colours with what did
not fit added after them; tried anew on 48 of his works and drawn as the
app paints it (sheets of 2026-11-21, /mnt/project-files/paski-akcent/),
he answered „Jest naprawdę dobrze” (22:55).

The bar is built as a painter would see the picture:

* its **masses**: the picture in up to ``MAX_MASSES`` tones, from the
  darkest to the lightest, each at least ``BAND`` of it (the width the app
  paints a colour as a band and not as a dab), each in the clean colour
  of its own tone (the more coloured half of its pixels; a mean greys it);
* its **accents**: what the eye goes to beside the masses — the server's
  own accents (``colors.analyse``'s), the lightest light, the small
  clusters, the white, the colours off the picture's cast and its greens
  however dark (Vermeer's shutters, Bruegel's trees: Mateusz 22:35,
  „Super pomysł”). An accent lies on the mass it stands on in the picture
  (``at``: its place along the bar), is as large as there is of it
  (``amount``: the app's dab is shorter and thinner for less, 22:28) and
  is one dab for what the eye takes for one colour (``SAME``). A dark
  colour with a clear hue is lifted, as white is (``DARK``).
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from frame_server.library import colors as C
from frame_server.library.models import ColorSwatch

#: A mass is at least this share of the picture: the app paints a colour
#: under ``Paint.touch`` (44 of 350 pt) as a dab, not as a band.
BAND = 0.13
#: The most masses, and the k-means clusters they are made of.
MAX_MASSES = 5
CLUSTERS = 10
#: The most accents (Mateusz 2026-11-21 22:35: „mi się akurat ta mnogość
#: podoba”).
MAX_ACCENTS = 6
#: A colour this dark with a clear hue is lifted towards the light.
DARK = 0.45
#: Two accents closer than this (lightness counted half), of hues within
#: ``SAME_HUE``°, or of one hue (``ONE_HUE``°) and nearly one lightness, are
#: one (Mateusz 2026-11-21 22:35, of three oranges side by side: „racja”).
SAME = 0.09
SAME_HUE = 30.0
ONE_HUE = 12.0
ONE_LIGHT = 0.1
#: An accent's weight on the bar: what it holds of the masses' room.
LEAST, MOST = 0.015, 0.06
#: A candidate this close to the mass it stands on is that mass.
APART = 0.08
#: Colours off the picture's cast by this much, on this much of it, are
#: candidates (lifted ``CAST_LIFT`` further off the cast).
OFF_CAST, OFF_AREA, CAST_LIFT = 0.035, 0.01, 0.5
#: Greens (OKLab hue), however olive or dark, on this much of the picture.
GREENS, GREEN_CHROMA, GREEN_AREA, GREEN_LIFT = (100.0, 170.0), 0.025, 0.012, 1.6
#: A white: this light, this little coloured, on this much of the picture.
WHITE_LIGHT, WHITE_CHROMA, WHITE_AREA = 0.8, 0.06, 0.02
#: The lightest light, lighter than every mass by this much, on this much.
TOP_ABOVE, TOP_AREA = 0.06, 0.02
#: A light or a dark against its mass: a face in the dark.
LIT = 0.25


def _hue(lab: np.ndarray) -> float:
    return float(np.degrees(np.arctan2(lab[2], lab[1])) % 360)


def _hue_apart(p: np.ndarray, q: np.ndarray) -> float:
    return abs((_hue(p) - _hue(q) + 180) % 360 - 180)


def _near(lab: np.ndarray, colour: np.ndarray) -> np.ndarray:
    """How far each pixel is from ``colour``, squared (chroma counted twice)."""
    d = lab - colour
    return np.asarray(d[..., 0] ** 2 + 4 * (d[..., 1] ** 2 + d[..., 2] ** 2))


def _lifted(colour: np.ndarray) -> np.ndarray:
    """A dark colour with a hue, lighter and as much more coloured: the eye
    reads a dark green shutter as green, the bar would paint it black."""
    out = colour.copy()
    k = (DARK - out[0]) * 0.6
    out[0] += k
    out[1:] *= 1 + 1.5 * k / DARK
    return out


def clusters(fine: np.ndarray, k: int = CLUSTERS) -> list[tuple[np.ndarray, float]]:
    """The picture's colours, each its clean colour (the more coloured half
    of its pixels) at its own lightness, and its share."""
    weighted = (fine * np.array([1.0, 2.0, 2.0])).astype(np.float32)
    rng = np.random.default_rng(0)
    centres = weighted[rng.choice(len(weighted), min(k, len(weighted)), replace=False)]
    # Pixels along the columns: the nearest centre is a column's least, the
    # first of equals as ``np.argmin`` has it (which is slower across).
    across = np.ascontiguousarray(weighted.T)
    own = (weighted**2).sum(1)[None]
    d = np.empty((len(centres), len(weighted)), np.float32)

    def nearest() -> np.ndarray:
        np.matmul(centres, across, out=d)
        np.multiply(d, -2, out=d)
        np.add(d, own, out=d)
        np.add(d, (centres**2).sum(1)[:, None], out=d)
        least = d.min(0)
        at = np.full(len(weighted), len(d) - 1, np.intp)
        for j in range(len(d) - 2, -1, -1):
            at[d[j] == least] = j
        return at

    owner = nearest()
    for _ in range(25):
        count = np.bincount(owner, minlength=len(centres)).astype(np.float32)
        sums = np.stack(
            [np.bincount(owner, weights=across[c], minlength=len(centres)) for c in range(3)], 1
        )
        centres = np.where(
            count[:, None] > 0, sums / np.maximum(count, 1)[:, None], centres
        ).astype(np.float32)
        before, owner = owner, nearest()
        if np.array_equal(before, owner):
            break
    out = []
    for j in range(len(centres)):
        pixels = fine[owner == j]
        if not len(pixels):
            continue
        chroma = np.hypot(pixels[:, 1], pixels[:, 2])
        core = pixels[chroma >= np.median(chroma)].mean(0)
        core[0] = pixels[:, 0].mean()
        out.append((core, len(pixels) / len(fine)))
    return out


def masses(found: Sequence[tuple[np.ndarray, float]]) -> list[tuple[np.ndarray, float]]:
    """The clusters merged into at most ``MAX_MASSES``, each at least
    ``BAND``, from the darkest; a merged mass keeps the cleaner chroma."""
    m = [(c.copy(), w) for c, w in found]

    def merge(i: int, j: int) -> None:
        (a, wa), (b, wb) = m[i], m[j]
        w = wa + wb
        c = (a * wa + b * wb) / w
        keep = max(float(np.hypot(*a[1:])), float(np.hypot(*b[1:])))
        now = float(np.hypot(*c[1:]))
        if now > 1e-6:
            c[1:] *= min(keep / now, 1.3)
        m[i] = (c, w)
        m.pop(j)

    while len(m) > 1:
        small = [i for i, (_, w) in enumerate(m) if w < BAND]
        if not small and len(m) <= MAX_MASSES:
            break
        if small:
            i = min(range(len(m)), key=lambda x: m[x][1])
            j = min(
                (x for x in range(len(m)) if x != i), key=lambda x: C._distance(m[i][0], m[x][0])
            )
        else:
            _, i, j = min(
                (C._distance(m[a][0], m[b][0]), a, b)
                for a in range(len(m))
                for b in range(a + 1, len(m))
            )
        merge(*sorted((i, j)))
    return sorted(m, key=lambda x: float(x[0][0]))


def candidates(
    fine: np.ndarray,
    found: Sequence[tuple[np.ndarray, float]],
    mains: Sequence[tuple[np.ndarray, float]],
    cast: np.ndarray | None = None,
) -> list[tuple[np.ndarray, float]]:
    """What may be an accent, after the server's own ones: the lightest
    light, the small clusters, the white, the colours off the cast, the
    greens."""
    out: list[tuple[np.ndarray, float]] = []
    lightest = max(float(c[0]) for c, _ in mains)
    top = max(found, key=lambda x: float(x[0][0]))
    if top[1] >= TOP_AREA and top[0][0] - lightest >= TOP_ABOVE:
        out.append(top)
    out += [(c, w) for c, w in found if w < BAND]
    white = (fine[:, 0] >= WHITE_LIGHT) & (np.hypot(fine[:, 1], fine[:, 2]) <= WHITE_CHROMA)
    if white.mean() >= WHITE_AREA:
        out.append((fine[white].mean(0), float(white.mean())))
    cast = np.median(fine[:, 1:], 0) if cast is None else cast
    off = fine[:, 1:] - cast
    off_hue = np.degrees(np.arctan2(off[:, 1], off[:, 0])) % 360
    off_by = np.hypot(off[:, 0], off[:, 1])
    lit = fine[:, 0] > 0.15
    off_enough = (off_by >= OFF_CAST) & lit
    for _, start, end in C.ACCENT_SECTORS:
        sector = ((off_hue - start) % 360 < end - start) & off_enough
        if sector.mean() >= OFF_AREA:
            c = fine[sector].mean(0)
            c[1:] += CAST_LIFT * (c[1:] - cast)
            out.append((c, float(sector.mean())))
    hue = np.degrees(np.arctan2(fine[:, 2], fine[:, 1])) % 360
    green = (
        (hue >= GREENS[0])
        & (hue < GREENS[1])
        & (np.hypot(fine[:, 1], fine[:, 2]) >= GREEN_CHROMA)
        & lit
    )
    if green.mean() >= GREEN_AREA:
        c = fine[green].mean(0)
        c[1:] += GREEN_LIFT * (c[1:] - cast)
        out.append((c, float(green.mean())))
    return out


def bar(grid: np.ndarray, own: Sequence[tuple[np.ndarray, float]] = ()) -> list[ColorSwatch]:
    """A painting's bar from its OKLab ``grid`` (``colors._grid``, 128):
    its masses from the darkest, then its accents in their places along
    the bar; ``own``: the accents ``colors.analyse`` found (colour, share),
    shown unless the bar has their colour already."""
    fine = grid.reshape(-1, 3)
    cast = np.median(fine[:, 1:], 0)
    found = clusters(fine)
    mains = masses(found)
    owner = np.argmin(np.stack([_near(grid, c) for c, _ in mains]), 0)
    lightest = max(float(c[0]) for c, _ in mains)
    darkest = min(float(c[0]) for c, _ in mains)
    trusted = len(own)
    kernel = np.ones((5, 5), np.uint8)
    picked: list[tuple[np.ndarray, float, float, int, float]] = []
    for n, (colour, share) in enumerate([*own, *candidates(fine, found, mains, cast)]):
        c = np.asarray(colour, dtype=float).copy()
        far = _near(grid, c)
        here = far < 0.06**2
        if here.sum() < 3:
            here = far < 0.1**2
        ring = cv2.dilate(here.astype(np.uint8), kernel).astype(bool) & ~here
        around = owner[ring] if ring.any() else owner[here]
        host = int(np.bincount(around, minlength=len(mains)).argmax()) if around.size else 0
        ground = mains[host][0]
        off_cast = float(np.hypot(*(c[1:] - cast)))
        chroma = float(np.hypot(c[1], c[2]))
        cast_hue = float(np.degrees(np.arctan2(cast[1], cast[0])) % 360)
        apart = abs((_hue(c) - cast_hue + 180) % 360 - 180)
        white = c[0] >= 0.78 and chroma <= 0.07 and c[0] - lightest >= 0.04
        black = c[0] <= 0.22 and c[0] < darkest - 0.06
        coloured = (off_cast >= 0.05 and chroma >= 0.04) or (
            off_cast >= 0.035 and chroma >= 0.015 and apart >= 90
        )
        lit = abs(float(c[0] - ground[0])) >= LIT or (
            c[0] - lightest >= TOP_ABOVE and share >= TOP_AREA
        )
        lifted = n < trusted and c[0] < DARK and chroma >= 0.03 and C._distance(c, ground) < APART
        if lifted:
            # The server's own dark accent: off its ground first.
            c = _lifted(c)
        if C._distance(c, ground) < APART and not white:
            continue
        if not (coloured or white or black or lit or n < trusted):
            continue
        if white:
            c = C.whiter(c)
        elif (coloured or n < trusted) and not lifted and c[0] < DARK and chroma >= 0.02:
            c = _lifted(c)
        score = max(off_cast, abs(float(c[0] - ground[0])) / 3, 0.08 if white or black else 0.0)
        picked.append(
            (
                c,
                min(max(share, LEAST), MOST),
                score * float(np.sqrt(max(share, 0.005))),
                host,
                share,
            )
        )
    # What the eye takes for one colour is one accent: the stronger keeps it, with both amounts.
    kept: list[tuple[np.ndarray, float, float, int, float]] = []
    for p in sorted(picked, key=lambda p: -p[2]):
        for i, q in enumerate(kept):
            near = C._distance(p[0], q[0], 0.5) < SAME and _hue_apart(p[0], q[0]) < SAME_HUE
            if near or (
                _hue_apart(p[0], q[0]) < ONE_HUE and abs(float(p[0][0] - q[0][0])) < ONE_LIGHT
            ):
                kept[i] = (q[0], max(q[1], p[1]), q[2], q[3], q[4] + p[4])
                break
        else:
            kept.append(p)
    kept = kept[:MAX_ACCENTS]
    total = sum(w for _, w in mains)
    edges = np.cumsum([0.0] + [w / total for _, w in mains])
    placed = []
    for host in sorted({p[3] for p in kept}):
        on = sorted((p for p in kept if p[3] == host), key=lambda p: float(p[0][0]))
        a, b = edges[host], edges[host + 1]
        placed += [(p, float(a + (b - a) * (k + 1) / (len(on) + 1))) for k, p in enumerate(on)]
    placed.sort(key=lambda x: x[1])
    out = [C._swatch(c, w) for c, w in mains]
    for (c, w, _, _, amount), at in placed:
        swatch = C._swatch(c, w, accent=True)
        swatch.at = round(at, 3)
        swatch.amount = round(float(amount), 4)
        out.append(swatch)
    return out
