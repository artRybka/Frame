# ArtSR G3 (`artsr-g3.onnx`)

The restorer chosen on 2026-11-26: STYL2g after 3 h of its 400 min (`STYL2g_h3.pt`), the one behind
the `*_G-3.jpg` / `*_g3.jpg` files. x4 super-resolution of museum pictures, steered by the work's look.

## Licence

Base weights: **LocalSR Photo M** (`4xLocalSRPhoto_PULSE-96x12`) by Hermes Reisner (HerRei),
https://github.com/HerRei/localsr-models, **CC BY 4.0** (attribution required; code MIT). Trained further
by us (L1 + LPIPS + a light GAN, FiLM style conditioning added) on ~12,000 public-domain / open-access
museum works (NGA, SMK, Art Institute of Chicago, Smithsonian, Yale, …: 4,000 paintings, 4,400 prints,
3,600 drawings). The fine-tune is a derivative of the base: wherever it goes, it carries the
CC BY 4.0 attribution above and says it was modified.

## File

- `artsr-g3.onnx`: 11.3 MB, fp32, opset 17, 2.82 M parameters (PULSE 96 ch × 12 blocks, 2.03 M, + FiLM MLP 0.79 M).
  sha256 `de140408da2e9a9955a66f35c4c81921d2c7628a89dc92d3c487357ea8a9142c`.
- Inputs
  - `image` (n, 3, h, w) float32, RGB 0..1 (8-bit / 255, no other normalisation); any h, w.
  - `look` (n, 768) float32: SigLIP 2 image embedding, L2-normalised, rounded through float16.
  - `kind` (n, 3) float32: one-hot painting / print / drawing.
- Output `out` (n, 3, 4h, 4w) float32, clamp to 0..1.

## The conditioning

- Model: open_clip `ViT-B-16-SigLIP2-256` (`hf-hub:timm/ViT-B-16-SigLIP2-256`, weights identical to
  open_clip `pretrained="webli"`, checked tensor by tensor) — **the same model the server exports in
  `scripts/look-model/export.py` and reads in `seen.py`**. Same preprocessing too: PIL bicubic to
  256×256 (aspect not kept), (x/255 − 0.5)/0.5; `encode_image`, then L2-normalise. Cosine between the
  training's torch vector and the server's ONNX vector of the same picture: 1.00000 on all four
  museum inputs.
- In training the vector was of the whole *degraded low-res* copy of each work (two per work), stored
  as float16. At inference it is of the input picture itself. The server keeps one of the work's
  thumbnail: on a 300 px thumbnail of the four inputs cosine was 0.987–0.995 and the result moved by
  36–45 dB PSNR (van Gogh most). Best: embed the very picture being restored (`look_of` in
  `artsr_infer.py`, 1 extra SigLIP pass); the kept thumbnail vector is a fair, cheaper fallback.
- `kind`: in training, from the museum record's own classification (painting / print / drawing,
  `cat` in the manifest). Museum test runs (`pro/`: Mleczarka, Rembrandt, Holbein, van Gogh): all
  `painting`. De Chirico runs: chosen by hand per work (1 drawing, 2–3 painting, 4 drawing, 5 print).
  The server can map its technique (`seen.technique`) to these three; unknown → painting.

## Recipe (`artsr_infer.py`)

`restored(picture, session, look, kind)`: RGB/255 → model in 256 px tiles, each with 32 px of context
(cut at the edges, no padding: the network's receptive field is 26 px, so 32 gives exactly the
whole-image answer; 16 px differs by ≤ 0.004, 98 dB) → clamp 0..1 → ×255 + 0.5 → uint8 → Lanczos to
2048 px long side → `frame_server.restorer.recoloured(picture, drawn, 0.7)`.

Checked on the Mac (M2 Pro), CPU:

- ONNX vs PyTorch, model output on the four `pro/in` inputs: max abs diff ≤ 1.1e-6 (8-bit: ≤ 1 level).
- Whole recipe vs `mleczarka_g3.jpg`: 43.8 dB PSNR against the JPEG; saved as JPEG q92 like the
  reference: 69.5 dB (the same file but for JPEG rounding). Rembrandt 45.6, Holbein 43.0, van Gogh 39.2 dB
  (vs JPEGs made on MPS).
- onnxruntime 1.32 CPU, 600×450 input (→ 2400×1800), intra_op threads:

  | | 2 threads | 4 threads | peak RSS |
  |---|---|---|---|
  | whole image | 6.2 s | 3.2 s | ~1.0 GB |
  | tiles 256, overlap 16 | 7.3 s | 3.8 s | ~490 MB |
  | tiles 256, overlap 32 | 8.6 s | 4.5 s | ~620 MB |

  M2 Pro cores; a NAS Celeron/Ryzen embedded core is ~3–5× slower. Use tiles on the NAS.
