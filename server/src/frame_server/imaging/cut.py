"""A museum photograph cut down to the work in it (Mateusz 2026-11-14).

The national museums of Warsaw and Kraków photograph many works as they
stand: a painting in its gilt frame on an easel, a poster on a grey board,
a woodcut on its sheet pasted onto a card. On the frame and in the app the
frame, the easel and the board read as part of the picture. What the work
is, a language model says (:mod:`frame_server.ai.crops`): four corners
around it, from the outside in, which it places a few hundredths off.
Here they are set on the edges the picture really has (:func:`snap`), and
the picture is cut to them, its perspective set straight (:func:`warp`).

A quadrilateral is four corners (top-left, top-right, bottom-right,
bottom-left), each as fractions of the picture's width and height.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import cv2
import numpy as np
from PIL import Image

Corner = tuple[float, float]
Quad = list[Corner]

#: The picture's long side the edges are looked for at.
SNAP_SIDE = 1500
#: How far from the model's side its true edge is looked for (share of the
#: long side): the model is a few hundredths off; further, a frame's outer
#: edge against a white wall would win over its inner edge (Römer, MNW).
BAND = 0.012
#: A print's border line or plate mark lies just inside its sheet's edge,
#: a gilt slip just outside a painting's, and both are stronger edges than
#: the true one: Opus's line was right and the snap took the line next to
#: it (a woodcut's top paper cut away, MNK 314364; the gilt slip of a
#: still life on copper kept, MNK 338944; 2026-11-15). So a sheet's side
#: takes the outermost edge at least :data:`OUTER_SHARE` as strong as the
#: strongest (Opus's line may lie out on the backdrop, the paper's edge
#: is then the only edge), and a painted surface's moves out no further
#: than :data:`HOLD` (share of the long side).
OUTER_SHARE = 0.5
HOLD = 0.004
OUTWARD = frozenset({"sheet"})
INWARD = frozenset({"frame_inner", "canvas"})
#: Points looked for along each side.
SAMPLES = 160
#: A point counts when the edge across the side is this strong (Sobel).
STRENGTH = 25.0
#: The points must lie on one straight line this well (px at SNAP_SIDE) for
#: that share of them, else the model's side stays.
ON_LINE = 2.5
LINE_SHARE = 0.6
#: Cut this much further in (share of each side): a sliver of a gilt frame
#: or of a grey board at the edge reads as a line on the panel.
INSET = 0.004
#: A cut keeps at least this share of the picture, and removes at least
#: this much of it (less is no cut worth making).
LEAST_KEPT = 0.15
MOST_KEPT = 0.985
#: A corner's angle may be this far from square (perspective of an easel).
SQUARE = 16.0


def valid(quad: Sequence[Sequence[float]]) -> Quad | None:
    """``quad`` as four corners within the picture, convex, roughly square
    at each corner and of a sensible size; None when it is not one."""
    if len(quad) != 4 or any(len(c) != 2 for c in quad):
        return None
    pts = np.array([[float(x), float(y)] for x, y in quad])
    if not np.isfinite(pts).all():
        return None
    pts = np.clip(pts, 0.0, 1.0)
    area = _area(pts)
    if not LEAST_KEPT <= area <= 1.0:
        return None
    for i in range(4):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % 4]
        v1, v2 = a - b, c - b
        n = np.linalg.norm(v1) * np.linalg.norm(v2)
        if n < 1e-9:
            return None
        angle = np.degrees(np.arccos(np.clip(v1 @ v2 / n, -1.0, 1.0)))
        if abs(angle - 90.0) > SQUARE:
            return None
    turns = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
    cross = [
        float(turns[i][0] * turns[(i + 1) % 4][1] - turns[i][1] * turns[(i + 1) % 4][0])
        for i in range(4)
    ]
    if not (all(c > 0 for c in cross) or all(c < 0 for c in cross)):
        return None
    return [(round(float(x), 5), round(float(y), 5)) for x, y in pts]


def _area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2)


def area(quad: Quad) -> float:
    """The share of the picture inside ``quad``."""
    return _area(np.array(quad, dtype=float))


def worth_cutting(quad: Quad) -> bool:
    """Whether cutting to ``quad`` takes away more than a hair."""
    return area(quad) < MOST_KEPT


def long_share(quad: Quad, size: tuple[int, int]) -> float:
    """How long the cut's long side is, as a share of the picture's long
    side (``size``: the picture's): a cut picture is smaller for the
    frame."""
    w, h = size
    pts = np.array(quad, dtype=float) * [w, h]
    width = max(np.linalg.norm(pts[1] - pts[0]), np.linalg.norm(pts[2] - pts[3]))
    height = max(np.linalg.norm(pts[3] - pts[0]), np.linalg.norm(pts[2] - pts[1]))
    return float(min(1.0, max(width, height) / max(w, h)))


def _gray(img: Image.Image) -> tuple[np.ndarray, float]:
    """The picture in grey at :data:`SNAP_SIDE`, blurred, and its scale."""
    small = img.convert("RGB")
    scale = min(1.0, SNAP_SIDE / max(small.size))
    if scale < 1.0:
        small = small.resize(
            (max(1, round(small.width * scale)), max(1, round(small.height * scale))),
            Image.Resampling.LANCZOS,
        )
    gray = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0).astype(np.float32), scale


def snap(img: Image.Image, quad: Quad, kind: str = "") -> Quad:
    """``quad`` set on the picture's own edges: along each side, the
    strongest edge across it within :data:`BAND` (the nearer the stronger),
    a straight line through those points, and the corners where the lines
    meet. A side without a clear straight edge keeps the model's line. A
    sheet's side takes the outermost of the strong edges, a painted
    surface's moves out no more than :data:`HOLD` (``kind``: the layer's,
    :data:`OUTWARD`, :data:`INWARD`)."""
    gray, _ = _gray(img)
    h, w = gray.shape
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    q = np.array(quad, dtype=float) * [w, h]
    centre = q.mean(axis=0)
    reach = BAND * max(w, h)
    hold = HOLD * max(w, h)
    # Offsets run inwards (towards the centre) from the model's line.
    offsets = np.arange(-(hold if kind in INWARD else reach), reach + 1.0)
    weight = 1.0 - 0.5 * np.abs(offsets) / max(reach, 1.0)
    lines: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        along = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        normal = np.array([-along[1], along[0]])
        if (centre - a) @ normal < 0:
            normal = -normal
        found = []
        for s in np.linspace(0.08, 0.92, SAMPLES):
            p = a + s * (b - a)
            pts = p[None, :] + offsets[:, None] * normal[None, :]
            xi = np.clip(np.round(pts[:, 0]).astype(int), 0, w - 1)
            yi = np.clip(np.round(pts[:, 1]).astype(int), 0, h - 1)
            g = np.abs(gx[yi, xi] * normal[0] + gy[yi, xi] * normal[1])
            gw = g * weight
            k = int(np.argmax(gw))
            if kind in OUTWARD:  # the outermost edge nearly as strong
                near = np.nonzero((gw >= OUTER_SHARE * gw[k]) & (g > STRENGTH))[0]
                k = int(near[0]) if len(near) else k
            if g[k] > STRENGTH:
                found.append(pts[k])
        line = (a, along)
        if len(found) >= SAMPLES * 0.3:
            pts_ = np.array(found, dtype=np.float32)
            vx, vy, x0, y0 = cv2.fitLine(pts_, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
            off = np.abs((pts_[:, 0] - x0) * vy - (pts_[:, 1] - y0) * vx)
            if float((off < ON_LINE).mean()) >= LINE_SHARE:
                line = (np.array([x0, y0], dtype=float), np.array([vx, vy], dtype=float))
        lines.append(line)
    out = q.copy()
    for i in range(4):  # corner i: where side i-1 meets side i
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        m = np.array([d1, -d2]).T
        if abs(np.linalg.det(m)) < 1e-6:
            continue
        t = np.linalg.solve(m, p2 - p1)
        out[i] = p1 + t[0] * d1
    snapped = valid((out / [w, h]).tolist())
    return snapped if snapped is not None else quad


def warp(
    img: Image.Image,
    quad: Quad,
    inset: float = INSET,
    ratio: Callable[[float], float | None] | None = None,
) -> Image.Image:
    """The part of ``img`` inside ``quad``, its perspective set straight, a
    little further in than the corners (``inset``), at the picture's own
    resolution. ``ratio``: the work's width / height when it is known
    better than the corners tell (a work of the owner's own, measured:
    ``OwnWork.ratio``), given the shape the corners give; the picture
    keeps its number of pixels."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    q = np.array(quad, dtype=np.float64) * [w, h]
    q = q + (q.mean(axis=0) - q) * inset * 2
    tl, tr, br, bl = q
    across = float(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    down = float(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    known = ratio(across / down) if ratio is not None and down > 0 else None
    if known:
        area = across * down
        across, down = math.sqrt(area * known), math.sqrt(area / known)
    width, height = round(across), round(down)
    width, height = max(width, 1), max(height, 1)
    target = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(q.astype(np.float32), target)
    out = cv2.warpPerspective(
        np.asarray(rgb),
        matrix,
        (width, height),
        flags=cv2.INTER_AREA if max(width, height) < max(w, h) * 0.5 else cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    cut = Image.fromarray(out)
    cut.info.update({k: v for k, v in img.info.items() if k != "icc_profile"})
    return cut


def same_picture(aspect: float, size: tuple[int, int]) -> bool:
    """Whether a picture of ``size`` is the one a cut was measured on
    (``aspect``: its width / height): a thumbnail of it, or the original
    at another size, not another copy."""
    w, h = size
    return w > 0 and h > 0 and abs(w / h - aspect) <= 0.03 * aspect


def cut_aspect(quad: Quad, aspect: float, inset: float = INSET) -> float:
    """The width / height of a photograph of ``aspect`` cut to ``quad``
    (:func:`warp`'s picture), 0 for a degenerate quad."""
    q = np.array(quad, dtype=np.float64) * [aspect, 1.0]
    q = q + (q.mean(axis=0) - q) * inset * 2
    tl, tr, br, bl = q
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    return float(width / height) if height > 0 else 0.0


def cut_seen(quad: Quad | None, aspect: float, size: tuple[int, int] | None) -> Quad | None:
    """Which picture one of ``size`` is when a photograph of ``aspect`` is
    cut to ``quad``: the cut one (``quad``) or the photograph whole (None).
    A size that tells neither (none given, or the two pictures nearly the
    same shape) is taken for the cut one, the picture shown now."""
    if quad is None:
        return None
    if size is None or not size[0] or not size[1]:
        return quad
    shown = cut_aspect(quad, aspect)
    ratio = size[0] / size[1]
    off_cut, off_whole = abs(ratio - shown) / shown if shown else 1.0, abs(ratio - aspect) / aspect
    return None if off_whole < off_cut and same_picture(aspect, size) else quad


def _straight(q: np.ndarray) -> tuple[np.ndarray, int, int]:
    """The perspective that sets ``q`` (corners in pixels) straight, as
    :func:`warp` does, and the straight picture's width and height."""
    tl, tr, br, bl = q
    width = max(round(float(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))), 1)
    height = max(round(float(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))), 1)
    target = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    return cv2.getPerspectiveTransform(q.astype(np.float32), target), width, height


def _inset(q: np.ndarray, inset: float = INSET) -> np.ndarray:
    return q + (q.mean(axis=0) - q) * inset * 2


def _in_frame(
    outer: np.ndarray, work: np.ndarray, ratio: Callable[[float], float | None] | None
) -> tuple[np.ndarray, int, int, np.ndarray]:
    """The perspective that sets a frame's outer edge (``outer``, corners
    in pixels) straight for the card's "W ramie", the straight picture's
    width and height, and where the work as shown (cut to ``work``,
    :func:`warp`'s inset) comes to lie in it (its corners there).

    A work shown in another shape than its corners give (``ratio``, as
    :func:`warp`'s: a work of his own, in the shape of the size he gave)
    has the frame's picture as much wider or narrower as gives the work
    in it that shape. Set straight by its own corners alone the frame
    held the work in the photograph's shape: "Out of the box", 29 × 40 cm,
    was 5% narrower on the card than its place in the frame, and the
    frame's photograph showed beside it, the same picture twice (Mateusz
    2026-11-18 21:44 UTC: "Podwójny obraz po wyświetleniu ramy")."""
    matrix, width, height = _straight(outer)
    inner = _inset(work)
    tl, tr, br, bl = inner
    across = float(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    down = float(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    pts = cv2.perspectiveTransform(inner.reshape(-1, 1, 2).astype(np.float32), matrix)
    pts = pts.reshape(-1, 2).astype(np.float64)
    takes = np.ptp(pts, axis=0)
    known = ratio(across / down) if ratio is not None and min(across, down) > 0 else None
    if not known or takes.min() <= 0:
        return matrix, width, height, pts
    # As many pixels as before, in the other shape.
    wider = math.sqrt(known * takes[1] / takes[0])
    stretch = np.array(
        [max(round(width * wider), 1) / width, max(round(height / wider), 1) / height]
    )
    width, height = round(width * stretch[0]), round(height * stretch[1])
    return np.diag([*stretch, 1.0]) @ matrix, width, height, pts * stretch


def framed_geometry(
    outer: Quad,
    work: Quad,
    aspect: float,
    ratio: Callable[[float], float | None] | None = None,
) -> tuple[float, tuple[float, float, float, float]] | None:
    """The card's "W ramie" (:func:`framed`) for a photograph of
    ``aspect`` (width / height): the straight picture's width / height,
    and the box the work as shown (cut to ``work``, :func:`warp`'s inset)
    takes in it (left, top, right, bottom, fractions); of the shape
    ``ratio`` gives the work, when it gives one (:func:`_in_frame`). None
    when the work is not inside ``outer``."""
    if aspect <= 0:
        return None
    scale = np.array([aspect * 1000.0, 1000.0])
    _, width, height, pts = _in_frame(
        np.array(outer, dtype=np.float64) * scale, np.array(work, dtype=np.float64) * scale, ratio
    )
    pts = pts / [width, height]
    xs, ys = pts[:, 0], pts[:, 1]
    box = (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))
    if box[0] < -0.01 or box[1] < -0.01 or box[2] > 1.01 or box[3] > 1.01:
        return None
    if (box[2] - box[0]) * (box[3] - box[1]) > 0.985:
        return None  # nothing around the work worth showing
    clipped = tuple(round(min(1.0, max(0.0, v)), 5) for v in box)
    return round(width / height, 5), (clipped[0], clipped[1], clipped[2], clipped[3])


def framed(
    img: Image.Image,
    outer: Quad,
    work: Quad | None = None,
    shown: Image.Image | None = None,
    ratio: Callable[[float], float | None] | None = None,
) -> Image.Image:
    """The photograph ``img`` cut to ``outer`` (a frame's or a mount's
    outer edge) and set straight, the edge itself kept; the work
    (``work``) in it of the shape ``ratio`` gives it, when it gives one
    (:func:`_in_frame`). With ``shown`` (the work as the card shows it:
    its colours corrected) laid over where the work is in it, so the
    frame holds the same picture."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    corners = np.array(outer, dtype=np.float64) * [w, h]
    if work is not None:
        matrix, width, height, dst = _in_frame(
            corners, np.array(work, dtype=np.float64) * [w, h], ratio
        )
    else:
        matrix, width, height = _straight(corners)
    out = cv2.warpPerspective(
        np.asarray(rgb),
        matrix,
        (width, height),
        flags=cv2.INTER_AREA if max(width, height) < max(w, h) * 0.5 else cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if shown is not None and work is not None:
        sw, sh = shown.size
        src = np.array([[0, 0], [sw, 0], [sw, sh], [0, sh]], dtype=np.float32)
        lay = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
        picture = cv2.warpPerspective(
            np.asarray(shown.convert("RGB")), lay, (width, height), flags=cv2.INTER_AREA
        )
        mask = cv2.warpPerspective(
            np.full((sh, sw), 255, np.uint8), lay, (width, height), flags=cv2.INTER_LINEAR
        )
        a = (mask.astype(np.float32) / 255.0)[..., None]
        out = (picture * a + out * (1.0 - a)).astype(np.uint8)
    made = Image.fromarray(out)
    made.info.update({k: v for k, v in img.info.items() if k != "icc_profile"})
    return made
