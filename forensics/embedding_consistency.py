"""
One-class DINOv2 embedding-consistency layer for PHOTOREAL diffusion video.

Why this layer exists
---------------------
`forensics/camera_physics.py` measured every camera-physics statistic this repo
could think of (photon-transfer curve, fixed-pattern noise, residual spectrum)
and none separates photoreal diffusion video (Higgsfield, Veo, Sora, Kling)
from real camera footage with a defensible margin - photoreal diffusion is
photoreal *per frame*, so there is no sensor artifact left to measure.

This layer tests the plan's Phase-2 hypothesis instead: the frames of a real
clip are draws from ONE physical scene, while a photoreal render's frames are
not. It embeds each frame with a self-supervised DINOv2 encoder (which models
scene structure, unlike content-based CLIP) and measures how far the clip's
frames sit from a bank of embeddings built from the REAL corpus only - a
one-class detector that needs no AI labels to fit.

Calibration (2026-11-11, `scripts/probe_embedding_consistency.py`, 224px input,
16 frames/clip, cosine distance `1 - max_sim` to the leave-one-out real bank):

    kNN distance   real (7 clips)      hyper-real (8 clips)
                   0.398 - 0.642        0.678 - 0.847

The gap (0.642 vs 0.678) is clean at BOTH 224px and 518px input, which is why
the layer is allowed to vote. It is capped at SUSPICIOUS (79) - never
SYNTHETIC_AI - because "far from these 7 real clips" is evidence of a non-real
origin, not proof of a specific generator, and a hand-made render or an unusual
camera would also be far. It never overrides a confirmed-authentic C2PA camera
manifest.

CALIBRATION LIMIT: the bank is 7 real clips. The repo's plan requires 30+
confirmed-real clips before a production-safe threshold; re-run
`scripts/build_embedding_bank.py` and re-check the gap when the corpus grows.
The threshold is stored in the bank file, not hard-coded, so a rebuilt bank
carries its own calibration.

CPU-only, lazy-loaded DINOv2-small (~29 ms/frame at 224px).
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

MIN_FRAMES = 8
N_FRAMES = 16               # evenly-spread frames embedded per window

BANK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "models", "real_embedding_bank.npz"
)

# Fallback thresholds, used only when the bank file lacks a calibration record.
_FALLBACK_KNN_SUSPICIOUS = 0.67
_FALLBACK_KNN_MAX = 0.85

_DINOV2 = None
_BANK = None
_BANK_FAILED = False
_LOCK = threading.Lock()


def _dinov2():
    """Lazy DINOv2-small loader (224px, cached in the HF hub)."""
    global _DINOV2
    if _DINOV2 is not None:
        return _DINOV2
    with _LOCK:
        if _DINOV2 is not None:
            return _DINOV2
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


def dinov2_embedding(img: Image.Image) -> Optional[np.ndarray]:
    """L2-normalized DINOv2 feature for one PIL RGB image (or None)."""
    try:
        import torch

        model, xf = _dinov2()
        t = xf(img.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            feats = model(t)
        v = feats[0].cpu().numpy().astype(np.float64)
        return v / (np.linalg.norm(v) + 1e-9)
    except Exception as exc:  # noqa: BLE001
        print(f"Embedding-consistency DINOv2 embedding failed: {exc}")
        return None


def _load_bank() -> Optional[Dict[str, Any]]:
    global _BANK, _BANK_FAILED
    if _BANK is not None or _BANK_FAILED:
        return _BANK
    with _LOCK:
        if _BANK is not None or _BANK_FAILED:
            return _BANK
        try:
            z = np.load(BANK_PATH, allow_pickle=False)
            emb = z["embeddings"].astype(np.float64)
            # Re-normalize defensively (bank is built normalized; this guards a
            # hand-edited or recompressed file).
            emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
            cal = {}
            if "calibration" in z:
                try:
                    cal = json.loads(str(z["calibration"]))
                except (ValueError, TypeError):
                    cal = {}
            _BANK = {
                "embeddings": emb,
                "clip_ids": [str(s) for s in z["clip_ids"]] if "clip_ids" in z else [],
                "calibration": cal,
            }
        except FileNotFoundError:
            _BANK_FAILED = True
            _BANK = None
            print("Embedding-consistency layer inactive: real bank not built "
                  "(run scripts/build_embedding_bank.py).")
        except Exception as exc:  # noqa: BLE001
            _BANK_FAILED = True
            _BANK = None
            print(f"Embedding-consistency layer inactive (bank load failed): {exc}")
    return _BANK


def _to_rgb_pil(frame: Any) -> Image.Image:
    if isinstance(frame, Image.Image):
        return frame.convert("RGB")
    a = np.asarray(frame)
    if a.ndim == 3 and a.shape[2] == 3:
        # OpenCV convention: BGR.
        import cv2  # noqa: PLC0415

        return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
    return Image.fromarray(a).convert("RGB")


def analyze_embedding_consistency(frames: List[Any]) -> Dict[str, Any]:
    """Score a contiguous native-frame window against the real-only bank.

    Returns {"score": int|None, "active": bool, "metrics": {...},
             "reasons": [...], "detail": {...}}. `score` is None (abstain) when
    the bank/model is unavailable, the window is too short, or the distance
    sits inside the real range. Never raises.
    """
    try:
        if os.environ.get("EMBEDDING_LAYER", "1") in ("0", "false", "no"):
            return {
                "score": None, "active": False, "metrics": {},
                "reasons": ["Embedding-consistency layer disabled (EMBEDDING_LAYER=0)."],
                "detail": {},
            }
        bank = _load_bank()
        if bank is None:
            return {
                "score": None, "active": False, "metrics": {},
                "reasons": ["Embedding-consistency layer inactive: no real-embedding bank."],
                "detail": {},
            }
        usable = [f for f in frames if f is not None]
        if len(usable) < MIN_FRAMES:
            return {
                "score": None, "active": False, "metrics": {},
                "reasons": [
                    f"Embedding-consistency layer inactive: {len(usable)} usable frame(s), "
                    f"needs at least {MIN_FRAMES}."
                ],
                "detail": {},
            }

        idx = sorted({
            int(round(i * (len(usable) - 1) / (N_FRAMES - 1))) for i in range(N_FRAMES)
        })
        embs = []
        for i in idx:
            e = dinov2_embedding(_to_rgb_pil(usable[i]))
            if e is not None:
                embs.append(e)
        if len(embs) < MIN_FRAMES:
            return {
                "score": None, "active": False, "metrics": {},
                "reasons": ["Embedding-consistency layer inactive: no embeddings produced."],
                "detail": {},
            }

        embs = np.stack(embs)
        bank_emb = bank["embeddings"]
        sim = embs @ bank_emb.T                      # (n_frames, n_bank)
        knn = float((1.0 - sim.max(axis=1)).mean())  # mean cosine distance to nearest real frame

        cal = bank.get("calibration") or {}
        suspicious = float(cal.get("knn_suspicious", _FALLBACK_KNN_SUSPICIOUS))
        knn_max = float(cal.get("knn_max", _FALLBACK_KNN_MAX))

        metrics = {
            "knn_distance": round(knn, 5),
            "frames_embedded": int(len(embs)),
            "bank_size": int(bank_emb.shape[0]),
            "bank_clips": int(cal.get("n_real_clips", len(set(bank["clip_ids"])) or 0)),
        }

        score: Optional[int] = None
        active = False
        reasons = [
            f"Embedding-consistency probe ({len(embs)} frames, bank {bank_emb.shape[0]} "
            f"real-clip embeddings): mean distance to nearest real frame {knn:.3f} "
            f"(real reference range up to {cal.get('knn_human_max', '~0.64')})."
        ]
        if knn >= suspicious:
            active = True
            strength = max(0.0, min(1.0, (knn - suspicious) / max(1e-6, knn_max - suspicious)))
            score = int(round(70.0 + 9.0 * strength))
            reasons.append(
                f"Frames sit far from the real-capture bank: mean nearest-neighbour distance "
                f"{knn:.3f} exceeds the measured real maximum ({cal.get('knn_human_max', '~0.64')}) "
                f"by a clear margin. A real clip's frames are draws from one physical scene and "
                f"stay close to the bank; this clip's frames are not, which is consistent with "
                f"photoreal synthesis (or another non-camera origin). Calibrated on "
                f"{cal.get('n_real_clips', 7)} confirmed-real clips vs 8 hyper-real clips "
                f"(real max {cal.get('knn_human_max', 0.642)}, hyper-real min "
                f"{cal.get('knn_ai_min', 0.678)}). Capped at SUSPICIOUS: distance from a small "
                f"real bank proves non-camera origin, not a specific generator."
            )
        else:
            reasons.append(
                "Embedding-consistency layer found the frames inside the real-capture range "
                "and abstains (no evidence either way)."
            )

        return {
            "score": score,
            "active": active,
            "metrics": metrics,
            "reasons": reasons,
            "detail": {"frames_sampled": len(idx)},
        }
    except Exception as e:  # noqa: BLE001 - layer must never break a verdict
        return {
            "score": None, "active": False, "metrics": {},
            "reasons": [f"Embedding-consistency layer unavailable: {e}"],
            "detail": {},
        }
