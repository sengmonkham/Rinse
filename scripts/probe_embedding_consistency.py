"""Phase-2 feasibility probe: per-frame CLIP-embedding consistency.

Companion to `scripts/probe_camera_physics.py` and Phase 2 of
`docs/ultra-realistic-video-plan.md`. Photoreal diffusion is photoreal *per
frame*; the plan's hypothesis is that its frames are not draws from the same
physical scene, so per-frame embeddings drift more (or sit farther from a
one-class bank built from the REAL corpus only) than a real clip's do.

Uses the CLIP ViT-B/32 backbone already loaded by forensics/learned_image.py
(no new weights, CPU). Reports, per clip:

* `drift`  - mean L2 distance between consecutive frame embeddings (temporal
             consistency of the scene);
* `spread` - mean distance from the clip's own embedding centroid (scene
             coherence across the window);
* `knn`    - mean distance from each frame to its nearest neighbour in the
             REAL-only bank (one-class "is this a real capture" distance).

This is a MEASUREMENT script, not a detector: it only prints separation. It
does not wire a vote, and Phase 2 remains gated on corpus growth + a real
held-out AUROC (see the plan).

Usage:
    .venv/bin/python scripts/probe_embedding_consistency.py --label human
    .venv/bin/python scripts/probe_embedding_consistency.py --hyperreal
    .venv/bin/python scripts/probe_embedding_consistency.py --ids ig-DfA6rNyKDRU,ig-DaAd4iqhbnj
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import probe_capture_origin as pco  # noqa: E402
from forensics.learned_image import clip_embedding  # noqa: E402

HYPERREAL_IDS = [
    "ig-Dfko7WRJY9o", "ig-DdDKCrEKT3r", "ig-DeqTgBEhvAu", "ig-DfA6rNyKDRU",
    "ig-De1OcoyBkhZ", "ig-DecPhb-iBFr", "ig-DeWNa25MgzR", "ig-DeZyTL0t2Yi",
]

N_FRAMES = 16

_DINOV2 = None


def _dinov2():
    """Lazy DINOv2-small loader (self-supervised, cached in the HF hub).

    224px input: DINOv2 patch14 is resolution-robust for one-class scene
    matching and 224px is ~6x faster on CPU than the default 518px.
    """
    global _DINOV2
    if _DINOV2 is None:
        import timm

        model = timm.create_model(
            "vit_small_patch14_dinov2.lvd142m", pretrained=True, num_classes=0,
            img_size=224,
        )
        model.eval()
        cfg = timm.data.resolve_model_data_config(model)
        cfg["input_size"] = (3, 224, 224)
        xf = timm.data.create_transform(**cfg, is_training=False)
        _DINOV2 = (model, xf)
    return _DINOV2


def dinov2_embedding(img: Image.Image) -> np.ndarray:
    import torch

    model, xf = _dinov2()
    t = xf(img.convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        feats = model(t)
    return feats[0].cpu().numpy().astype(np.float64)


def embeddings_for(asset_id: str, url: str, encoder: str = "clip") -> np.ndarray:
    data = pco.fetch(asset_id, url)
    frames = pco.frames_from_bytes(data)
    idx = sorted({int(round(i * (len(frames) - 1) / (N_FRAMES - 1))) for i in range(N_FRAMES)})
    embed = dinov2_embedding if encoder == "dinov2" else clip_embedding
    embs = []
    for i in idx:
        rgb = cv2.cvtColor(frames[i], cv2.COLOR_BGR2RGB)
        e = embed(Image.fromarray(rgb))
        if e is not None:
            e = e / (np.linalg.norm(e) + 1e-9)
            embs.append(e)
    return np.stack(embs).astype(np.float64) if embs else np.zeros((0, 512))


def clip_stats(embs: np.ndarray, bank: np.ndarray) -> dict:
    if embs.shape[0] < 2:
        return {"drift": None, "spread": None, "knn": None}
    drift = float(np.linalg.norm(np.diff(embs, axis=0), axis=1).mean())
    centroid = embs.mean(axis=0)
    spread = float(np.linalg.norm(embs - centroid, axis=1).mean())
    knn = None
    if bank.shape[0]:
        # Cosine distance via normalized dot product (both sides L2-normalized).
        sim = embs @ bank.T  # (N_frames, N_bank)
        knn = float((1.0 - sim.max(axis=1)).mean())
    return {"drift": round(drift, 5), "spread": round(spread, 5), "knn": round(knn, 5) if knn is not None else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default="", help="comma-separated asset ids")
    ap.add_argument("--label", default="", help="run every asset with this label")
    ap.add_argument("--hyperreal", action="store_true", help="run the 8 hyper-real clips")
    ap.add_argument("--encoder", default="clip", choices=("clip", "dinov2"),
                    help="embedding backbone (default clip; dinov2 is the "
                         "self-supervised encoder the plan recommends)")
    ap.add_argument("--out", default="tests/embedding_consistency_probe.json")
    args = ap.parse_args()

    assets = pco.load_assets()
    todo = []
    if args.ids:
        for i in [s.strip() for s in args.ids.split(",") if s.strip()]:
            a = assets.get(i)
            if a:
                todo.append((i, a["label"], a["url"]))
            else:
                print(f"{i}: not in the asset registry")
    if args.label:
        todo += [(k, v["label"], v["url"]) for k, v in assets.items() if v["label"] == args.label]
    if args.hyperreal:
        for i in HYPERREAL_IDS:
            a = assets.get(i)
            if a:
                todo.append((i, a["label"], a["url"]))

    print(f"Extracting {args.encoder} embeddings (first clip loads the backbone)...", flush=True)
    cache = {}
    rows = []
    for asset_id, label, url in todo:
        try:
            embs = embeddings_for(asset_id, url, encoder=args.encoder)
            cache[asset_id] = embs
            print(f"ok   {asset_id} ({label})  {embs.shape[0]} frames", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {asset_id} ({label}): {e}")

    # One-class bank from the REAL clips only (never from AI labels). Built
    # per-clip below with leave-one-out, so a real clip is not its own
    # nearest neighbour.
    real_ids = [k for k, v in assets.items() if v["label"] == "human"]

    for asset_id, label, url in todo:
        if asset_id not in cache:
            rows.append({"id": asset_id, "label": label})
            continue
        # One-class bank from the REAL clips only, leave-one-out so a real clip
        # is not its own nearest neighbour (self-distance would zero it out).
        bank_ids = [i for i in real_ids if i != asset_id and i in cache]
        bank = np.vstack([cache[i] for i in bank_ids]) if bank_ids else np.zeros((0, 512))
        rows.append({"id": asset_id, "label": label, **clip_stats(cache[asset_id], bank)})

    if rows:
        hdr = f"{'id':24}{'lab':8}{'drift':>12}{'spread':>12}{'knn':>12}"
        print("\n" + hdr)
        for r in sorted(rows, key=lambda r: (r["label"], r["id"])):
            print(f"{r['id']:24}{r['label']:8}"
                  f"{r.get('drift') if r.get('drift') is not None else '-':>12}"
                  f"{r.get('spread') if r.get('spread') is not None else '-':>12}"
                  f"{r.get('knn') if r.get('knn') is not None else '-':>12}")

        print("\n=== SEPARATION ===")
        for k in ("drift", "spread", "knn"):
            hv = [r[k] for r in rows if r["label"] == "human" and isinstance(r.get(k), float)]
            av = [r[k] for r in rows if r["label"] == "ai" and isinstance(r.get(k), float)]
            if not hv or not av:
                continue
            sep = " <-- SEPARATES" if (max(hv) < min(av) or min(hv) > max(av)) else ""
            print(f"{k:8} human [{min(hv):.4f}, {max(hv):.4f}]  ai [{min(av):.4f}, {max(av):.4f}]{sep}")

        out = os.path.join(ROOT, args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(rows, f, indent=2)
        print(f"\nwrote {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
