"""SigLIP 2 (ViT-B-16, 256 px; Google, Apache 2.0) in the shape the server
reads (``frame_server.seen``): ONNX of its picture side and its words side,
both answering unit vectors, the words side's table of tokens as bytes
(the rest as it was: quantising its products moved the answers too far),
and its tokenizer. Run by ``.github/workflows/look-model.yml``, which puts
what it writes on a release of the repository; the server fetches it from
there on its first start.

    python export.py OUT_DIR
"""

import hashlib
import shutil
import sys
from pathlib import Path

import open_clip
import torch
from huggingface_hub import hf_hub_download
from onnxruntime.quantization import QuantType, quantize_dynamic

NAME = "ViT-B-16-SigLIP2-256"
HUB = "timm/ViT-B-16-SigLIP2-256"


class Picture(torch.nn.Module):
    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, pixels: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.normalize(self.model.encode_image(pixels), dim=-1)


class Words(torch.nn.Module):
    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.normalize(self.model.encode_text(tokens), dim=-1)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    model, _, _ = open_clip.create_model_and_transforms(NAME, pretrained="webli")
    model.eval()
    pixels = torch.randn(2, 3, 256, 256)
    tokens = torch.ones(2, 64, dtype=torch.long)
    with torch.no_grad():
        torch.onnx.export(
            Picture(model), (pixels,), out / "picture.onnx", input_names=["pixels"],
            output_names=["look"], dynamic_axes={"pixels": {0: "n"}, "look": {0: "n"}},
            opset_version=17, dynamo=False,
        )
        torch.onnx.export(
            Words(model), (tokens,), out / "words-full.onnx", input_names=["tokens"],
            output_names=["look"], dynamic_axes={"tokens": {0: "n"}, "look": {0: "n"}},
            opset_version=17, dynamo=False,
        )
    quantize_dynamic(
        out / "words-full.onnx", out / "words.onnx", weight_type=QuantType.QInt8,
        op_types_to_quantize=["Gather"],
    )
    (out / "words-full.onnx").unlink()
    shutil.copy(hf_hub_download(HUB, "tokenizer.json"), out / "tokenizer.json")
    sums = []
    for name in ("picture.onnx", "words.onnx", "tokenizer.json"):
        digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
        sums.append(f"{digest}  {name}")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print("\n".join(sums))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
