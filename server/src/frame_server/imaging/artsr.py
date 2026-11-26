"""Our own restorer's model, ArtSR G3 (Mateusz 2026-11-26: "Nasz nowy model
to główny i domyślny restaurator"): LocalSR Photo M (Hermes Reisner,
CC BY 4.0, ``models/README.md``) taught further on some 12,000 public-domain
museum works, each of its blocks led by how the work looks (its SigLIP 2
vector, :mod:`frame_server.seen`) and by its kind (painting, print,
drawing). Four times larger, on the server's own processor, free.

Of 32 works with a large original, it kept nearest to them of everything
tried (Gemini's drawings 1-2.5 dB further off, 2026-11-26); some 9 s for a
picture of 600 px on two threads in the cloud, three to five times that on
the NAS.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..library import Item

log = logging.getLogger(__name__)

#: The model, as its notes name it.
NAME = "artsr-g3"
FILE = Path(__file__).parent / "models" / f"{NAME}.onnx"
#: Its kinds, the one-hot it was taught with (the museum's own
#: classification; one not known was taught as a painting).
KINDS = {"painting": 0, "print": 1, "drawing": 2}
#: Input pixels a tile's side, and the neighbours' context run with each
#: (cut at the picture's edge, no padding: the network pads itself).
TILE = 256
OVERLAP = 32
SCALE = 4
#: Threads of the processor it takes: the NAS has others to serve.
THREADS = 2
#: How long its vector is (SigLIP 2's).
LOOK = 768

_PRINT = (
    "woodcut",
    "woodblock",
    "drzeworyt",
    "etching",
    "engraving",
    "akwafort",
    "miedzioryt",
    "staloryt",
    "intaglio",
    "drypoint",
    "sucha igła",
    "mezzotint",
    "aquatint",
    "akwatint",
    "lithograph",
    "litografi",
    "screenprint",
    "serigraph",
    "sitodruk",
    "linocut",
    "linoryt",
    "gravure",
    "eau-forte",
    "print",
    "grafika",
    "ukiyo",
)
_DRAWING = (
    "graphite",
    "pencil",
    "ołówek",
    "charcoal",
    "węgiel",
    "chalk",
    "kred",
    "pen ",
    "pióro",
    "ink",
    "tusz",
    "sanguine",
    "crayon",
    "fusain",
    "drawing",
    "rysun",
    "watercolo",
    "akwarel",
    "aquarelle",
    "gouache",
    "gwasz",
    "pastel",
)
_PAINT = (
    "painting",
    "malarstwo",
    "oil",
    "olej",
    "huile",
    "tempera",
    "acrylic",
    "akryl",
    "canvas",
    "płótn",
    "panel",
)


def kind_of(item: Item) -> str:
    """The kind the model is led by: of the work's technique (or the
    museum's classification), a painting when neither says."""
    words = " ".join(part for part in (item.medium, item.classification) if part).lower()
    if any(w in words for w in _PAINT):
        return "painting"
    if any(w in words for w in _PRINT):
        return "print"
    if any(w in words for w in _DRAWING):
        return "drawing"
    return "painting"


def condition(look: np.ndarray, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """As taught: the unit vector rounded through float16 (its vectors were
    kept so), and the kind as a one-hot of three."""
    v = np.asarray(look, dtype=np.float32).reshape(-1)
    v = v / max(float(np.linalg.norm(v)), 1e-12)
    v = v.astype(np.float16).astype(np.float32)[None]
    k = np.zeros((1, 3), np.float32)
    k[0, KINDS.get(kind, 0)] = 1.0
    return v, k


class ArtSR:
    """The model, read on first use and kept (11 MB)."""

    def __init__(self, path: Path = FILE, threads: int = THREADS) -> None:
        self.path = path
        self.threads = threads
        self._session: Any = None
        self._lock = threading.Lock()

    def here(self) -> bool:
        return self.path.is_file()

    def session(self) -> Any:
        with self._lock:
            if self._session is None:
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.intra_op_num_threads = self.threads
                options.inter_op_num_threads = 1
                self._session = ort.InferenceSession(
                    str(self.path), options, providers=["CPUExecutionProvider"]
                )
            return self._session

    def larger(self, picture: Image.Image, look: np.ndarray, kind: str) -> Image.Image:
        """``picture`` four times larger, led by ``look`` and ``kind``."""
        session = self.session()
        x = (np.asarray(picture.convert("RGB"), dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
        v, k = condition(look, kind)

        def run(part: np.ndarray) -> np.ndarray:
            feed = {"image": np.ascontiguousarray(part), "look": v, "kind": k}
            return np.asarray(session.run(None, feed)[0], dtype=np.float32)

        _, _, h, w = x.shape
        if max(h, w) <= TILE:
            out = run(x)
        else:
            # Bytes, not floats: a picture of 1800 px is 7200 px drawn.
            out = np.empty((1, 3, SCALE * h, SCALE * w), np.uint8)
            for y in range(0, h, TILE):
                for x0 in range(0, w, TILE):
                    y1, x1 = min(y + TILE, h), min(x0 + TILE, w)
                    ya, xa = max(0, y - OVERLAP), max(0, x0 - OVERLAP)
                    yb, xb = min(h, y1 + OVERLAP), min(w, x1 + OVERLAP)
                    part = run(x[:, :, ya:yb, xa:xb])
                    out[:, :, SCALE * y : SCALE * y1, SCALE * x0 : SCALE * x1] = _bytes(
                        part[
                            :,
                            :,
                            SCALE * (y - ya) : SCALE * (y1 - ya),
                            SCALE * (x0 - xa) : SCALE * (x1 - xa),
                        ]
                    )
            return Image.fromarray(np.ascontiguousarray(out[0].transpose(1, 2, 0)), "RGB")
        return Image.fromarray(np.ascontiguousarray(_bytes(out)[0].transpose(1, 2, 0)), "RGB")


def _bytes(part: np.ndarray) -> np.ndarray:
    """The model's 0..1 values as bytes."""
    return (np.clip(part, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
