"""What is worth looking at in a picture, for automatic crops.

A small map of "interest" per area: fine detail and local contrast (edges),
colourfulness, and above all faces (YuNet via OpenCV), with a mild pull
towards the centre so scanning borders and paper edges do not win. Crops
are then the windows of the requested shape with the most interest per pixel.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .layout import Crop, crop_box

log = logging.getLogger(__name__)

MAP_SIZE = 192  # long side of the analysis map
FACE_INPUT = 640  # long side of the image the face detector sees
FACE_WEIGHT = 6.0  # a face pixel counts as much as this many average-detail pixels
MODEL = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"

_face_lock = threading.Lock()


@lru_cache(maxsize=1)
def _face_detector() -> object | None:
    try:
        import cv2

        return cv2.FaceDetectorYN.create(str(MODEL), "", (320, 320), 0.75, 0.3, 50)
    except Exception as err:  # no OpenCV or no model: crops without faces
        log.warning("face detection unavailable: %s", err)
        return None


def detect_faces(img: Image.Image) -> list[tuple[float, float, float, float]]:
    """Faces as (x0, y0, x1, y1) fractions of the picture."""
    detector = _face_detector()
    if detector is None:
        return []
    small = img.convert("RGB")
    small.thumbnail((FACE_INPUT, FACE_INPUT))
    bgr = np.ascontiguousarray(np.asarray(small)[:, :, ::-1])
    h, w = bgr.shape[:2]
    with _face_lock:  # one detector instance, not thread-safe
        detector.setInputSize((w, h))  # type: ignore[attr-defined]
        _, found = detector.detect(bgr)  # type: ignore[attr-defined]
    if found is None:
        return []
    return [
        (max(f[0], 0) / w, max(f[1], 0) / h, min(f[0] + f[2], w) / w, min(f[1] + f[3], h) / h)
        for f in found
    ]


class InterestMap:
    def __init__(self, img: Image.Image) -> None:
        self.size = img.size
        small = img.convert("RGB")
        small.thumbnail((MAP_SIZE, MAP_SIZE), Image.Resampling.BILINEAR)
        rgb = np.asarray(small, dtype=np.float32) / 255.0
        h, w = rgb.shape[:2]
        luma = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        gy, gx = np.gradient(luma)
        edges = np.hypot(gx, gy)
        chroma = rgb.max(axis=-1) - rgb.min(axis=-1)
        energy = edges / (edges.mean() + 1e-6) + 0.3 * chroma / (chroma.mean() + 1e-6)
        # A few very hard edges (frame, paper border) must not decide alone.
        energy = np.minimum(energy, np.percentile(energy, 98))

        self.faces = detect_faces(img)
        for x0, y0, x1, y1 in self.faces:
            # The face and a bit around it (hair, the rest of the head).
            fw, fh = x1 - x0, y1 - y0
            ys = slice(int(max(y0 - 0.3 * fh, 0) * h), int(np.ceil(min(y1 + 0.2 * fh, 1) * h)))
            xs = slice(int(max(x0 - 0.2 * fw, 0) * w), int(np.ceil(min(x1 + 0.2 * fw, 1) * w)))
            energy[ys, xs] += FACE_WEIGHT * float(energy.mean())

        yy, xx = np.mgrid[0:h, 0:w]
        r2 = ((xx + 0.5) / w - 0.5) ** 2 + ((yy + 0.5) / h - 0.5) ** 2
        self.map = energy * (1.0 - 0.6 * r2)

    def pick(self, aspect: float, zooms: Sequence[float]) -> list[Crop]:
        """One window of ``aspect`` per zoom, the most interesting first.

        Each further window keeps clear of the earlier ones (at least half a
        window away, so not simply the next strip above or beside them) and
        what they show no longer counts; the distance is relaxed only if the
        picture is too small for it.
        """
        mh, mw = self.map.shape
        interest = self.map.copy()
        taken: list[tuple[int, int, int, int]] = []  # left, top, w, h in map pixels
        crops: list[Crop] = []
        for zoom in zooms:
            x0, y0, x1, y1 = crop_box((mw, mh), aspect, Crop(zoom=zoom))
            bw, bh = max(1, round(x1 - x0)), max(1, round(y1 - y0))
            s = np.pad(interest.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
            scores = (s[bh:, bw:] - s[:-bh, bw:] - s[bh:, :-bw] + s[:-bh, :-bw]) / (bw * bh)
            ys, xs = np.mgrid[0 : scores.shape[0], 0 : scores.shape[1]]
            blocked = np.zeros(scores.shape, dtype=bool)
            for spacing in (0.5, 0.25, 0.0):
                blocked[:] = False
                for left, top, w, h in taken:
                    gx, gy = spacing * max(w, bw), spacing * max(h, bh)
                    blocked |= (
                        (xs < left + w + gx)
                        & (xs + bw > left - gx)
                        & (ys < top + h + gy)
                        & (ys + bh > top - gy)
                    )
                if not blocked.all():
                    break
            else:
                blocked[:] = False  # nowhere apart: overlap rather than fail
            best = int(np.argmax(np.where(blocked, -np.inf, scores)))
            top, left = (int(v) for v in np.unravel_index(best, scores.shape))
            taken.append((left, top, bw, bh))
            interest[top : top + bh, left : left + bw] = 0.0
            crops.append(Crop(x=(left + bw / 2) / mw, y=(top + bh / 2) / mh, zoom=zoom))
        return crops

    def auto(self, aspect: float, zooms: Sequence[float]) -> list[Crop]:
        return self.pick(aspect, zooms)
