"""Timings of ArtSR G3 in Core ML on this Mac, its compute plan, and its agreement with the ONNX.

    python bench.py ArtSR-G3-320.mlpackage [window]      # window: 320 (default) or 576

Needs (not in this repo):
    ARTSR_ONNX   artsr-g3.onnx, the reference                 default ~/Documents/Frame/framecam-share/artsr/onnx/artsr-g3.onnx
    ARTSR_EVAL   the training's evalout/ (works.json: inputs of public-domain test works; vecs.pt:
                 their SigLIP 2 vectors + one-hot kind)        default ~/Frame-worktrees/artsr/evalout
"""
import json
import os
import statistics
import sys
import time
from collections import Counter

import numpy as np
import onnxruntime as ort
import torch
from PIL import Image

import coremltools as ct
from coremltools.models.compute_plan import MLComputePlan
from coremltools.models.compute_device import (MLCPUComputeDevice, MLGPUComputeDevice,
                                               MLNeuralEngineComputeDevice)

ONNX = os.path.expanduser(os.environ.get("ARTSR_ONNX",
                                         "~/Documents/Frame/framecam-share/artsr/onnx/artsr-g3.onnx"))
EVAL = os.path.expanduser(os.environ.get("ARTSR_EVAL", "~/Frame-worktrees/artsr/evalout"))
OVERLAP, SCALE = 32, 4
WIN = int(sys.argv[2]) if len(sys.argv) > 2 else 320  # the tile the model is run on
TILE = WIN - 2 * OVERLAP  # the middle kept of each
UNITS = {"ALL": ct.ComputeUnit.ALL, "CPU_AND_NE": ct.ComputeUnit.CPU_AND_NE,
         "CPU_AND_GPU": ct.ComputeUnit.CPU_AND_GPU, "CPU_ONLY": ct.ComputeUnit.CPU_ONLY}

PKG = sys.argv[1] if len(sys.argv) > 1 else "ArtSR-G3-320.mlpackage"
IO16 = "io16" in PKG
DT = np.float16 if IO16 else np.float32


def cond(look, kind=0):
    v = np.asarray(look, np.float32).reshape(-1)[:768]  # vecs.pt holds look (768) + one-hot kind
    v = (v / np.linalg.norm(v)).astype(np.float16).astype(np.float32)[None]
    k = np.zeros((1, 3), np.float32)
    k[0, kind] = 1
    return v, k


def upscaled(x, run):
    """x (1,3,h,w) float32; run(window 1x3x320x320) -> 1x3x1280x1280. Every window is a full
    320x320 one, moved back inside the picture at its edges (needs h, w >= 320): the kept middle
    always has >= 32 px of real context (receptive field 26), and a window touching an edge pads
    the same as the whole picture would, so the result equals the whole-image answer."""
    _, _, h, w = x.shape
    out = np.empty((1, 3, SCALE * h, SCALE * w), np.float32)
    n = 0
    for y in range(0, h, TILE):
        for x0 in range(0, w, TILE):
            y1, x1 = min(y + TILE, h), min(x0 + TILE, w)
            ya = min(max(0, y - OVERLAP), h - WIN)
            xa = min(max(0, x0 - OVERLAP), w - WIN)
            part = run(x[:, :, ya:ya + WIN, xa:xa + WIN])
            out[:, :, SCALE * y:SCALE * y1, SCALE * x0:SCALE * x1] = part[
                :, :, SCALE * (y - ya):SCALE * (y1 - ya), SCALE * (x0 - xa):SCALE * (x1 - xa)]
            n += 1
    return np.clip(out, 0, 1), n


def onnx_upscaled(x, sess, v, k):
    """artsr_infer.upscaled: tiles cut at the edges, no padding."""
    run = lambda p: sess.run(None, {"image": np.ascontiguousarray(p), "look": v, "kind": k})[0]
    _, _, h, w = x.shape
    out = np.empty((1, 3, SCALE * h, SCALE * w), np.float32)
    for y in range(0, h, TILE):
        for x0 in range(0, w, TILE):
            y1, x1 = min(y + TILE, h), min(x0 + TILE, w)
            ya, xa = max(0, y - OVERLAP), max(0, x0 - OVERLAP)
            yb, xb = min(h, y1 + OVERLAP), min(w, x1 + OVERLAP)
            part = run(x[:, :, ya:yb, xa:xb])
            out[:, :, SCALE * y:SCALE * y1, SCALE * x0:SCALE * x1] = part[
                :, :, SCALE * (y - ya):SCALE * (y1 - ya), SCALE * (x0 - xa):SCALE * (x1 - xa)]
    return np.clip(out, 0, 1)


def ml_runner(model, v, k):
    def run(p):
        r = model.predict({"image": np.ascontiguousarray(p).astype(DT), "look": v.astype(DT),
                           "kind": k.astype(DT)})
        return np.asarray(r["out"], np.float32)
    return run


def psnr8(a, b):
    """PSNR and max difference of two 0..1 pictures after 8-bit rounding (as saved)."""
    a8 = (a * 255 + .5).astype(np.int16)
    b8 = (b * 255 + .5).astype(np.int16)
    mse = float(np.mean((a8 - b8).astype(np.float64) ** 2))
    return (99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse)), int(np.abs(a8 - b8).max()), \
        float(np.abs(a - b).max())


def picture(path, size=None):
    img = Image.open(path).convert("RGB")
    if size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return (np.asarray(img, np.float32) / 255).transpose(2, 0, 1)[None]


def compute_plan(path, unit):
    m = ct.models.MLModel(path, compute_units=unit)  # keeps the compiled copy alive
    compiled = m.get_compiled_model_path()
    plan = MLComputePlan.load_from_path(compiled, compute_units=unit)
    fn = plan.model_structure.program.functions["main"]
    devs, ops = Counter(), Counter()
    for op in fn.block.operations:
        if op.operator_name in ("const",):
            continue
        u = plan.get_compute_device_usage_for_mlprogram_operation(op)
        if u is None:
            continue
        d = u.preferred_compute_device
        name = ("NE" if isinstance(d, MLNeuralEngineComputeDevice) else
                "GPU" if isinstance(d, MLGPUComputeDevice) else
                "CPU" if isinstance(d, MLCPUComputeDevice) else str(d))
        devs[name] += 1
        if name != "NE":
            ops[(op.operator_name, name)] += 1
    return dict(devs), {f"{a}@{b}": n for (a, b), n in ops.items()}


def main():
    res = {"package": PKG}
    vecs = torch.load(f"{EVAL}/vecs.pt", map_location="cpu")
    works = {w["key"]: w for w in json.load(open(f"{EVAL}/works.json"))}
    v, k = cond(vecs["2"].cpu().numpy(), 0)  # Vermeer, Mleczarka: painting

    # Compute plan per unit.
    res["plan"] = {}
    for name in ("ALL", "CPU_AND_NE"):
        res["plan"][name] = compute_plan(PKG, UNITS[name])
        print("plan", name, res["plan"][name], flush=True)

    # One tile, after warm-up, median of 10; load time too.
    tile = np.random.default_rng(0).random((1, 3, WIN, WIN)).astype(np.float32)
    models, res["tile_ms"], res["load_s"] = {}, {}, {}
    for name, unit in UNITS.items():
        t0 = time.perf_counter()
        m = ct.models.MLModel(PKG, compute_units=unit)
        run = ml_runner(m, v, k)
        run(tile)
        res["load_s"][name] = round(time.perf_counter() - t0, 2)
        for _ in range(3):
            run(tile)
        ts = []
        for _ in range(10):
            t0 = time.perf_counter()
            run(tile)
            ts.append(time.perf_counter() - t0)
        res["tile_ms"][name] = {"median": round(1000 * statistics.median(ts), 1),
                                "min": round(1000 * min(ts), 1), "max": round(1000 * max(ts), 1)}
        models[name] = m
        print("tile", name, res["tile_ms"][name], "load", res["load_s"][name], flush=True)

    # Whole pictures in tiles.
    sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"])
    pics = {"600x800": picture(works["2"]["input"], (600, 800)),
            "1800x1350": picture(works["1"]["input"], (1800, 1350))}
    res["whole_s"] = {}
    for pname, x in pics.items():
        res["whole_s"][pname] = {}
        for name in UNITS:
            t0 = time.perf_counter()
            _, n = upscaled(x, ml_runner(models[name], v, k))
            res["whole_s"][pname][name] = round(time.perf_counter() - t0, 2)
            print("whole", pname, name, res["whole_s"][pname][name], f"{n} tiles", flush=True)
        t0 = time.perf_counter()
        onnx_upscaled(x, sess, v, k)
        res["whole_s"][pname]["onnxruntime CPU (default threads)"] = round(time.perf_counter() - t0, 2)
        print("whole", pname, "onnx", res["whole_s"][pname]["onnxruntime CPU (default threads)"], flush=True)

    # Agreement with ONNX: the Vermeer as it is (535x600) and van Gogh (600x475), each with its own
    # vector, plus the 600x800 picture above.
    res["vs_onnx"] = {}
    cases = {"Mleczarka 535x600": ("2", picture(works["2"]["input"])),
             "Gwiazdzista noc 600x475": ("1", picture(works["1"]["input"])),
             "Mleczarka 600x800": ("2", pics["600x800"])}
    for cname, (key, x) in cases.items():
        if min(x.shape[2:]) < WIN:
            continue  # the windows need a picture at least WIN on each side
        cv, ck = cond(vecs[key].cpu().numpy(), 0)
        ref = onnx_upscaled(x, sess, cv, ck)
        res["vs_onnx"][cname] = {}
        for name in ("ALL", "CPU_AND_NE", "CPU_ONLY"):
            out, _ = upscaled(x, ml_runner(models[name], cv, ck))
            p, d8, df = psnr8(out, ref)
            res["vs_onnx"][cname][name] = {"psnr_db": round(p, 2), "max_diff_8bit": d8,
                                           "max_abs_float": round(df, 4)}
            print("vs onnx", cname, name, res["vs_onnx"][cname][name], flush=True)
            if os.environ.get("ARTSR_PNG") and cname.startswith("Mleczarka 535") and name == "CPU_AND_NE":
                Image.fromarray((out[0].transpose(1, 2, 0) * 255 + .5).astype(np.uint8)).save(
                    "mleczarka_coreml_ne.png")
                Image.fromarray((ref[0].transpose(1, 2, 0) * 255 + .5).astype(np.uint8)).save(
                    "mleczarka_onnx.png")

    res["window"] = WIN
    out = PKG.replace(".mlpackage", "") + f"-w{WIN}-results.json"
    json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
    print("saved", out)


if __name__ == "__main__":
    main()
