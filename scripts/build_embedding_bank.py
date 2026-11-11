"""Build the real-only DINOv2 embedding bank for the embedding-consistency layer.

Extracts 16 DINOv2-small (224px) frame embeddings per confirmed-real clip,
computes the leave-one-out kNN distance of each real clip and the kNN distance
of the hyper-real clips for calibration, and writes
``forensics/models/real_embedding_bank.npz``.

The bank is the one-class reference the layer measures new clips against; the
calibration record stores the measured gap (real max vs hyper-real min) so the
layer's threshold comes from the data, not a hard-coded constant. Re-run after
growing the real corpus.

Usage:
    .venv/bin/python scripts/build_embedding_bank.py
    .venv/bin/python scripts/build_embedding_bank.py --ids ig-DaAd4iqhbnj,ig-DecK8wQPTM7
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import probe_capture_origin as pco  # noqa: E402
from forensics.embedding_consistency import dinov2_embedding, BANK_PATH  # noqa: E402

N_FRAMES = 16

# Hyper-real Higgsfield clips, used only to record the calibration gap (never
# stored in the bank - the bank is REAL-only by construction).
HYPERREAL_IDS = [
    "ig-Dfko7WRJY9o", "ig-DdDKCrEKT3r", "ig-DeqTgBEhvAu", "ig-DfA6rNyKDRU",
    "ig-De1OcoyBkhZ", "ig-DecPhb-iBFr", "ig-DeWNa25MgzR", "ig-DeZyTL0t2Yi",
]


def embeddings_for(asset_id: str, url: str) -> np.ndarray:
    data = pco.fetch(asset_id, url)
    frames = pco.frames_from_bytes(data)
    idx = sorted({int(round(i * (len(frames) - 1) / (N_FRAMES - 1))) for i in range(N_FRAMES)})
    import cv2

    embs = []
    for i in idx:
        rgb = cv2.cvtColor(frames[i], cv2.COLOR_BGR2RGB)
        from PIL import Image

        e = dinov2_embedding(Image.fromarray(rgb))
        if e is not None:
            embs.append(e)
    return np.stack(embs).astype(np.float64)


def knn_distance(query: np.ndarray, bank: np.ndarray) -> float:
    if bank.shape[0] == 0:
        return float("inf")
    sim = query @ bank.T
    return float((1.0 - sim.max(axis=1)).mean())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default="", help="comma-separated REAL asset ids (default: every 'human' label)")
    ap.add_argument("--no-hyperreal-cal", action="store_true",
                    help="skip measuring the hyper-real gap (bank-only build)")
    args = ap.parse_args()

    assets = pco.load_assets()
    real_ids = args.ids and [s.strip() for s in args.ids.split(",") if s.strip()] or [
        k for k, v in assets.items() if v["label"] == "human"
    ]

    print("Embedding real clips (first clip loads DINOv2)...", flush=True)
    real = {}
    for aid in real_ids:
        a = assets.get(aid)
        if not a:
            print(f"{aid}: not in the asset registry")
            continue
        try:
            embs = embeddings_for(aid, a["url"])
            real[aid] = embs
            print(f"ok   {aid}  {embs.shape[0]} frames", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {aid}: {e}")

    if not real:
        print("No real clips embedded; nothing to write.")
        return 2

    bank = np.vstack(list(real.values()))
    # Fixed-width unicode so the npz loads without allow_pickle.
    clip_ids = np.array(
        [aid for aid, e in real.items() for _ in range(e.shape[0])], dtype="<U32"
    )

    # Leave-one-out kNN for each real clip (its own frames excluded).
    loo = []
    for aid, embs in real.items():
        others = np.vstack([e for k, e in real.items() if k != aid])
        loo.append(knn_distance(embs, others))
    knn_human_max = float(max(loo))
    print(f"\nreal leave-one-out kNN: min {min(loo):.4f}  max {knn_human_max:.4f}")

    knn_ai_min = None
    knn_ai_max = None
    if not args.no_hyperreal_cal:
        print("\nEmbedding hyper-real clips for calibration...", flush=True)
        ai_knn = []
        for aid in HYPERREAL_IDS:
            a = assets.get(aid)
            if not a:
                continue
            try:
                embs = embeddings_for(aid, a["url"])
                ai_knn.append(knn_distance(embs, bank))
                print(f"ok   {aid}  kNN {ai_knn[-1]:.4f}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"FAIL {aid}: {e}")
        if ai_knn:
            knn_ai_min = float(min(ai_knn))
            knn_ai_max = float(max(ai_knn))
            print(f"\nhyper-real kNN: min {knn_ai_min:.4f}  max {knn_ai_max:.4f}")

    if knn_ai_min is None:
        knn_suspicious = knn_human_max + 0.03
    else:
        # Threshold sits in the middle of the measured real/AI gap.
        knn_suspicious = 0.5 * (knn_human_max + knn_ai_min)
    knn_max = knn_ai_max if knn_ai_max is not None else knn_suspicious + 0.2

    calibration = {
        "n_real_clips": len(real),
        "knn_human_max": round(knn_human_max, 5),
        "knn_ai_min": round(knn_ai_min, 5) if knn_ai_min is not None else None,
        "knn_ai_max": round(knn_ai_max, 5) if knn_ai_max is not None else None,
        "knn_suspicious": round(knn_suspicious, 5),
        "knn_max": round(knn_max, 5),
        "real_ids": sorted(real.keys()),
        "build_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "encoder": "vit_small_patch14_dinov2.lvd142m @ 224px",
    }

    os.makedirs(os.path.dirname(BANK_PATH), exist_ok=True)
    np.savez(
        BANK_PATH,
        embeddings=bank.astype(np.float32),
        clip_ids=clip_ids,
        calibration=json.dumps(calibration),
    )
    print(f"\nwrote {os.path.relpath(BANK_PATH, ROOT)}  ({bank.shape[0]} embeddings, "
          f"{calibration['n_real_clips']} real clips)")
    print(f"gap: real max {knn_human_max:.4f}  ->  AI min {knn_ai_min}  ->  "
          f"threshold {knn_suspicious:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
