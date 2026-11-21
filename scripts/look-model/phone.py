"""SigLIP 2 (ViT-B-16, 256 px; Google, Apache 2.0) picture side as Core ML for
the phone: the same numbers as the server's ``picture.onnx``
(``frame_server.seen``), made from a photograph on the phone so that only the
numbers go to the server. Needs macOS (Core ML predicts only there).

    python phone.py OUT_DIR IMAGE...

Writes ``Look.mlpackage`` into OUT_DIR and prints how near its numbers are
to PyTorch's (fp32, CPU) on the images given, on each of Core ML's compute
units, failing below :data:`LEAST`. Released packed as an uncompressed tar
(``COPYFILE_DISABLE=1 tar --no-mac-metadata --format ustar -cf
Look.mlpackage.tar Look.mlpackage``) as ``look-model-siglip2-b16-phone-1``;
its sum goes to ``seen.PHONE_SUM``.

Input ``pixels`` (1, 3, 256, 256) float32 as ``seen.SeenModel.pixels``: RGB,
256x256 bicubic (not keeping proportions), /127.5 - 1, CHW. Output ``look``
(1, 768), a unit vector.

Computed in fp32, weights stored as int8 per channel, all but the position
table (``pos_embed``): quantising that one alone moved the numbers to a
cosine of 0.83. A model computed in fp16 was off by up to 0.993 on the CPU
(fine on the Neural Engine, but the phone may not use it), and twice the size.
On a Mac M2 Pro, 60 images: cosine min 0.9973, median 0.9993, 98% of the ten
nearest neighbours the same; 89.5 MB; 15 ms a picture (ALL), 39 ms (CPU).
Made with torch 2.7.0, open_clip_torch 4.2.2, coremltools 9.0, Python 3.12.
"""

import sys
import time
from pathlib import Path

import coremltools as ct
import coremltools.optimize.coreml as cto
import numpy as np
import open_clip
import torch
from PIL import Image

NAME = "ViT-B-16-SigLIP2-256"
SIDE = 256
NEIGHBOURS = 10
#: Least cosine to PyTorch's numbers the model must keep on every image.
LEAST = 0.995
#: The weight left as it is (see above).
KEPT = "model_visual_trunk_pos_embed"


class Picture(torch.nn.Module):
    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, pixels: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.normalize(self.model.encode_image(pixels), dim=-1)


def pixels(path: Path) -> np.ndarray:
    seen = Image.open(path).convert("RGB").resize((SIDE, SIDE), Image.Resampling.BICUBIC)
    return (np.asarray(seen, dtype=np.float32) / 127.5 - 1.0).transpose(2, 0, 1)[None]


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def agreement(a: np.ndarray, b: np.ndarray) -> float:
    def nearest(v: np.ndarray) -> np.ndarray:
        near = v @ v.T
        np.fill_diagonal(near, -2)
        return np.argsort(-near, axis=1)[:, :NEIGHBOURS]

    pairs = zip(nearest(a), nearest(b), strict=True)
    return float(np.mean([len(set(x) & set(y)) / NEIGHBOURS for x, y in pairs]))


def main(out: Path, images: list[Path]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    model, _, _ = open_clip.create_model_and_transforms(NAME, pretrained="webli")
    picture = Picture(model.eval()).eval()
    batch = [pixels(p) for p in images]
    with torch.no_grad():
        truth = unit(np.concatenate([picture(torch.from_numpy(x)).numpy() for x in batch]))
        traced = torch.jit.trace(picture, torch.from_numpy(batch[0]))
    full = ct.convert(
        traced,
        inputs=[ct.TensorType(name="pixels", shape=(1, 3, SIDE, SIDE), dtype=np.float32)],
        outputs=[ct.TensorType(name="look", dtype=np.float32)],
        minimum_deployment_target=ct.target.iOS18,
        convert_to="mlprogram",
        compute_precision=ct.precision.FLOAT32,
    )
    look = cto.linear_quantize_weights(
        full,
        cto.OptimizationConfig(
            global_config=cto.OpLinearQuantizerConfig(
                mode="linear_symmetric", dtype="int8", granularity="per_channel"
            ),
            op_name_configs={KEPT: None},
        ),
    )
    look.short_description = (
        "SigLIP 2 ViT-B-16 256 px picture side (Google, Apache 2.0): "
        "a picture's look as 768 numbers, as the server's picture.onnx."
    )
    path = out / "Look.mlpackage"
    look.save(str(path))
    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    worst = 1.0
    for units in (ct.ComputeUnit.CPU_ONLY, ct.ComputeUnit.CPU_AND_NE, ct.ComputeUnit.ALL):
        loaded = ct.models.MLModel(str(path), compute_units=units)
        loaded.predict({"pixels": batch[0]})
        start = time.perf_counter()
        found = [loaded.predict({"pixels": x})["look"].reshape(1, -1) for x in batch]
        each = (time.perf_counter() - start) / len(batch)
        found = unit(np.concatenate(found).astype(np.float32))
        cos = np.sum(found * truth, axis=1)
        worst = min(worst, float(cos.min()))
        print(
            f"{units.name:11s} {size / 2**20:6.1f} MB  cos min {cos.min():.4f} "
            f"median {np.median(cos):.4f}  neighbours {agreement(truth, found):.3f}  "
            f"{each * 1000:.0f} ms"
        )
    if worst < LEAST:
        sys.exit(f"cosine {worst:.4f} below {LEAST}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]])
