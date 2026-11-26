"""ArtSR G3 (STYL2g_h3.pt) -> Core ML .mlpackage (ML Program, FP16), fixed square tile(s).

Inputs as in artsr-g3.onnx: image (1,3,S,S) RGB 0..1, look (1,768), kind (1,3).
Output: out (1,3,4S,4S). S = 320 (256 + 2x32 context) by default; --sizes 320,576 gives one
package with both (EnumeratedShapes, the first is the default).

Where the training's sources are (not in this repo):
    ARTSR_SRC    folder with net.py (StylePULSE)          default ~/Frame-worktrees/artsr
    ARTSR_PULSE  folder with pulse_arch.py (PULSE)        default ~/Frame-worktrees/localsr-trial/models
    ARTSR_CKPT   the G3 weights                           default $ARTSR_SRC/ckpt/styl2g/STYL2g_h3.pt

    python convert.py [--sizes 320] [--io fp32|fp16] [--out ArtSR-G3-320.mlpackage]
"""
import argparse
import os
import sys

import numpy as np
import torch

SRC = os.path.expanduser(os.environ.get("ARTSR_SRC", "~/Frame-worktrees/artsr"))
PULSE_DIR = os.path.expanduser(os.environ.get("ARTSR_PULSE", "~/Frame-worktrees/localsr-trial/models"))
CKPT = os.path.expanduser(os.environ.get("ARTSR_CKPT", os.path.join(SRC, "ckpt/styl2g/STYL2g_h3.pt")))
sys.path.insert(0, SRC)
sys.path.insert(0, PULSE_DIR)
from net import StylePULSE, pulse_from  # noqa: E402

import coremltools as ct  # noqa: E402


class G3(torch.nn.Module):
    """StylePULSE with the ONNX signature (look, kind) instead of one cond vector."""

    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, image, look, kind):
        # Same as StylePULSE.forward, but without its rank-6 view (Core ML allows rank <= 5).
        m = self.m
        gb = m.film(torch.cat([look, kind], dim=1)).view(-1, m.n * 2, m.dim, 1, 1)
        feat = m.stem(image)
        h = feat
        for i, blk in enumerate(m.body):
            h = blk(h)
            h = h * (1 + gb[:, 2 * i]) + gb[:, 2 * i + 1]
        return m.base(image) + m.head(feat + h)


def load():
    base = pulse_from(CKPT)
    m = StylePULSE(base)
    m.load_state_dict(torch.load(CKPT, map_location="cpu"))
    return G3(m).eval()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="320", help="tile side(s), comma-separated")
    ap.add_argument("--io", choices=["fp32", "fp16"], default="fp32")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    sizes = [int(v) for v in a.sizes.split(",")]
    s = sizes[0]
    model = load()
    ex = (torch.rand(1, 3, s, s), torch.nn.functional.normalize(torch.randn(1, 768), dim=1),
          torch.tensor([[1.0, 0.0, 0.0]]))
    traced = torch.jit.trace(model, ex)
    dt = np.float16 if a.io == "fp16" else np.float32
    ml = ct.convert(
        traced,
        inputs=[ct.TensorType("image", dtype=dt, shape=(1, 3, s, s) if len(sizes) == 1 else
                              ct.EnumeratedShapes([(1, 3, v, v) for v in sizes], default=(1, 3, s, s))),
                ct.TensorType("look", shape=(1, 768), dtype=dt),
                ct.TensorType("kind", shape=(1, 3), dtype=dt)],
        outputs=[ct.TensorType("out", dtype=dt)],
        convert_to="mlprogram",
        compute_precision=ct.precision.FLOAT16,
        minimum_deployment_target=ct.target.iOS17,
    )
    ml.short_description = ("ArtSR G3: x4 restorer of museum pictures (PULSE 96x12 + FiLM). "
                            "Base: LocalSR Photo M by Hermes Reisner, CC BY 4.0, modified.")
    ml.input_description["image"] = ("RGB 0..1, NCHW, one tile of " + " or ".join(map(str, sizes))
                                      + " px (kept middle + 2x32 context)")
    ml.input_description["look"] = "SigLIP 2 ViT-B-16-256 image embedding, L2-normalised"
    ml.input_description["kind"] = "one-hot painting / print / drawing"
    ml.output_description["out"] = "x4, clamp to 0..1"
    out = a.out or f"ArtSR-G3-{'-'.join(map(str, sizes))}{'-io16' if a.io == 'fp16' else ''}.mlpackage"
    ml.save(out)
    print("saved", out)


if __name__ == "__main__":
    main()
