"""The same picture in two items, whatever their titles say.

Copies of a work from two sources often share no title: "The Great Wave
off Kanagawa" from a museum, "Wielka fala w Kanagawie" from Commons, "Under
the Wave off Kanagawa (Kanagawa oki nami ura)…" from the Met. Their
thumbnails tell: ORB keypoints matched between them and kept only where
one picture maps onto the other (a shift and a scale, RANSAC). Paper tone,
light, margins, mats and a crop leave hundreds of such matches; two
different prints by one artist leave a handful.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np

from ..imaging.layout import load_image
from .models import Item

if TYPE_CHECKING:
    from .images import ImageCache

log = logging.getLogger(__name__)

#: Long side the keypoints are looked for at.
SIDE = 400
FEATURES = 500
#: Matches that fit one mapping of one picture onto the other: copies of
#: a work have well over a hundred, different works under ten.
SAME = 25
#: Best match clearly better than the second best (Lowe's ratio test).
RATIO = 0.75
#: Pixels (at :data:`SIDE`) a match may miss the mapping by.
SLACK = 6.0
#: Pictures whose keypoints are kept in memory.
REMEMBERED = 256
#: One picture in place of another (:meth:`Likeness.whole`): many more
#: matches than :data:`SAME`, ...
WHOLE_MATCHES = 40
#: ... the one laid over the other covering it (intersection over union of
#: the two frames), ...
WHOLE_COVER = 0.88
#: ... and turned by no more than this (degrees).
WHOLE_TURN = 2.0


class Keypoints(NamedTuple):
    points: Any  # float32 (n, 2)
    descriptors: Any  # uint8 (n, 32)
    #: The picture's size where the points were found.
    size: tuple[int, int] = (SIDE, SIDE)


def keypoints(path: Path) -> Keypoints | None:
    """ORB keypoints of the picture at ``path``; None for a picture with too
    few (plain, tiny) or when OpenCV is missing."""
    try:
        import cv2
    except ImportError:  # pragma: no cover - a dependency, but optional here
        return None
    img = load_image(path).convert("L")
    img.thumbnail((SIDE, SIDE))
    orb = cv2.ORB_create(nfeatures=FEATURES)  # type: ignore[attr-defined]
    found, descriptors = orb.detectAndCompute(np.asarray(img), None)
    if descriptors is None or len(found) < SAME:
        return None
    points = np.array([k.pt for k in found], dtype=np.float32)
    return Keypoints(points, descriptors, img.size)


def mapping(a: Keypoints, b: Keypoints) -> tuple[int, Any]:
    """How many of the keypoints match under one mapping of ``a`` onto ``b``
    (a shift, a scale and a turn), and that mapping (2×3; None with too few
    matches)."""
    import cv2

    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(a.descriptors, b.descriptors, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < RATIO * p[1].distance]
    if len(good) < SAME:
        return len(good), None
    src = a.points[[m.queryIdx for m in good]]
    dst = b.points[[m.trainIdx for m in good]]
    found, inliers = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=SLACK
    )
    return (0, None) if inliers is None else (int(inliers.sum()), found)


def matches(a: Keypoints, b: Keypoints) -> int:
    """How many of the keypoints match under one mapping of ``a`` onto ``b``."""
    return mapping(a, b)[0]


def cover(a: Keypoints, b: Keypoints, found: Any) -> float:
    """How well ``a``'s frame laid over ``b`` by ``found`` covers ``b``'s:
    intersection over union of the two; 1.0 for the same picture with the
    same edges, far less for a detail of it or a page it is printed on."""
    width, height = a.size
    corners = np.array([[0, 0, 1], [width, 0, 1], [width, height, 1], [0, height, 1]], float)
    laid = corners @ np.asarray(found, float).T
    left, top = laid.min(axis=0)
    right, bottom = laid.max(axis=0)
    bw, bh = b.size
    inside = max(0.0, min(right, bw) - max(left, 0.0)) * max(0.0, min(bottom, bh) - max(top, 0.0))
    union = (right - left) * (bottom - top) + bw * bh - inside
    return float(inside / union) if union > 0 else 0.0


def turn(found: Any) -> float:
    """How far ``found`` turns a picture, in degrees."""
    return abs(math.degrees(math.atan2(float(found[1][0]), float(found[0][0]))))


class Likeness:
    """Tells copies of one picture apart by their thumbnails, where the
    cache has them (none is downloaded here). Safe to share between
    threads."""

    def __init__(self, images: ImageCache) -> None:
        self.images = images
        self._known: OrderedDict[tuple[str, int], Keypoints | None] = OrderedDict()
        self._lock = threading.Lock()

    def _keypoints(self, item: Item) -> Keypoints | None:
        path = self.images.thumb_path(item)
        try:
            key = (str(path), path.stat().st_mtime_ns)
        except OSError:
            return None
        with self._lock:
            if key in self._known:
                self._known.move_to_end(key)
                return self._known[key]
        try:
            found = keypoints(path)
        except Exception as err:  # a broken file: no opinion
            log.info("keypoints of %s: %s", item.id, err)
            found = None
        with self._lock:
            self._known[key] = found
            while len(self._known) > REMEMBERED:
                self._known.popitem(last=False)
        return found

    def same(self, a: Item, b: Item) -> bool:
        """``a`` and ``b`` show one picture; False when either thumbnail is
        missing or says too little."""
        if a.id == b.id:
            return True
        ka = self._keypoints(a)
        if ka is None:
            return False
        kb = self._keypoints(b)
        return kb is not None and matches(ka, kb) >= SAME

    def whole(self, a: Item, b: Item) -> bool:
        """``b`` is ``a``'s picture whole, fit to stand in for it: one
        picture by many matches, neither turned nor a detail of the other,
        nor printed on a page or a slide with more around it."""
        ka = self._keypoints(a)
        kb = self._keypoints(b) if ka is not None else None
        if ka is None or kb is None:
            return False
        count, found = mapping(ka, kb)
        if count < WHOLE_MATCHES or found is None:
            return False
        overlap, angle = cover(ka, kb, found), turn(found)
        log.info(
            "%s over %s: %d matches, cover %.2f, turned %.1f°", a.id, b.id, count, overlap, angle
        )
        return overlap >= WHOLE_COVER and angle <= WHOLE_TURN
