"""ArtSR G3 (STYL2g, hourly checkpoint after 3 h) on the server: numpy + onnxruntime + PIL, no torch.

    session = ort.InferenceSession("artsr-g3.onnx", opts, providers=["CPUExecutionProvider"])
    look = seen.model.pictures([picture])[0]           # SigLIP 2 ViT-B-16-256, 768-d unit vector
    final = restored(picture, session, look, "painting")

The model: PULSE x4 (LocalSR Photo M, 96 ch x 12 blocks) whose every block is FiLM-scaled by
``cond = [look (768), one-hot kind (3)]`` -> Linear(771, 256) -> SiLU -> Linear(256, 2*96*12).
ONNX inputs: image (n,3,h,w) float32 RGB 0..1; look (n,768) float32; kind (n,3) float32.
Output: out (n,3,4h,4w) float32, roughly 0..1 (clamp it).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

KINDS = {"painting": 0, "print": 1, "drawing": 2}
TILE = 256  # input pixels per tile side
OVERLAP = 32  # input pixels of context around each tile (the reference outputs used 32)
SCALE = 4
LONG_SIDE = 2048  # the model's output is brought to this long side before recolouring
SHARE = 0.7  # restorer.recoloured(picture, out, SHARE)


def cond(look: np.ndarray, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """The conditioning as trained: the unit SigLIP vector rounded through float16 (training kept
    its vectors as float16), and the work's kind as a one-hot of three."""
    v = np.asarray(look, dtype=np.float32).reshape(-1)
    v = v / max(float(np.linalg.norm(v)), 1e-12)
    v = v.astype(np.float16).astype(np.float32)[None]
    k = np.zeros((1, 3), np.float32)
    k[0, KINDS[kind]] = 1.0
    return v, k


def upscaled(picture: Image.Image, session, look: np.ndarray, kind: str = "painting",
             tile: int = TILE, overlap: int = OVERLAP) -> np.ndarray:
    """The model's x4 picture, float32 HxWx3 in 0..1. Tiles of ``tile`` input pixels, each run with
    ``overlap`` pixels of the neighbours' context (cut at the picture's edge, no padding), and only
    its own middle kept; the network pads its own edges (zeros in the convolutions, edge-replicate
    in the fixed x4 base), so no padding is added here and any size works."""
    x = (np.asarray(picture.convert("RGB"), dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
    v, k = cond(look, kind)
    run = lambda part: session.run(None, {"image": np.ascontiguousarray(part), "look": v, "kind": k})[0]
    _, _, h, w = x.shape
    if max(h, w) <= tile:
        out = run(x)
    else:
        out = np.empty((1, 3, SCALE * h, SCALE * w), np.float32)
        for y in range(0, h, tile):
            for x0 in range(0, w, tile):
                y1, x1 = min(y + tile, h), min(x0 + tile, w)
                ya, xa = max(0, y - overlap), max(0, x0 - overlap)
                yb, xb = min(h, y1 + overlap), min(w, x1 + overlap)
                part = run(x[:, :, ya:yb, xa:xb])
                out[:, :, SCALE * y:SCALE * y1, SCALE * x0:SCALE * x1] = part[
                    :, :, SCALE * (y - ya):SCALE * (y1 - ya), SCALE * (x0 - xa):SCALE * (x1 - xa)]
    return np.clip(out[0].transpose(1, 2, 0), 0.0, 1.0)


def image_of(a: np.ndarray) -> Image.Image:
    """Float 0..1 to 8-bit, rounded."""
    return Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), "RGB")


def restored(picture: Image.Image, session, look: np.ndarray, kind: str = "painting",
             long_side: int = LONG_SIDE, share: float = SHARE, tile: int = TILE,
             overlap: int = OVERLAP) -> Image.Image:
    """The whole recipe: model x4, Lanczos to ``long_side``, then the server's own recolouring
    (``frame_server.restorer.recoloured``: the picture's colours and tones at its own scale, ``share``
    of the drawn detail over a plain enlargement)."""
    from frame_server.restorer import recoloured

    drawn = image_of(upscaled(picture, session, look, kind, tile, overlap))
    f = long_side / max(drawn.size)
    drawn = drawn.resize((round(drawn.width * f), round(drawn.height * f)), Image.Resampling.LANCZOS)
    return recoloured(picture.convert("RGB"), drawn, share)


def look_of(picture: Image.Image, siglip_session) -> np.ndarray:
    """The SigLIP 2 vector the training used, by the server's ``picture.onnx`` (same weights and
    preprocessing as open_clip's ``hf-hub:timm/ViT-B-16-SigLIP2-256``: bicubic to 256x256 square,
    RGB / 127.5 - 1). Only for a work the server keeps no vector of."""
    seen = picture.convert("RGB").resize((256, 256), Image.Resampling.BICUBIC)
    px = (np.asarray(seen, dtype=np.float32) / 127.5 - 1.0).transpose(2, 0, 1)[None]
    return np.asarray(siglip_session.run(None, {"pixels": px})[0][0], np.float32)
