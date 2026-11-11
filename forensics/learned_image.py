"""Layer 6: dataset-trained image classifier.

The off-the-shelf CNNSpot / UnivFD checkpoints behind the DetectZoo layer do
not recognize the viral AI image styles in ``Dataset/`` - measured on this
corpus they label EVERY brainrot render and every Ai_generated_dataset image
"human" with ~1.0 confidence (see scripts/eval_image_dataset.py). This layer
adds a classifier trained on that corpus instead:

* **render head** - CLIP ViT-B/32 embeddings + linear head. Trained on
  ``Dataset/brainrot images`` (AI) vs ``Dataset/ai vs real images/real_dataset``
  (real photos). Grouped (unseen-clip-block / unseen-category) AUC 0.9955;
  95.5% recall at a 1% false-positive rate (97.6% at 5%).
* **photo head** - the cheap pixel statistics in forensics/image_features.py +
  linear head, trained on ``Ai_generated_dataset`` (AI) vs ``real_dataset``
  (real). Grouped AUC 0.890; 51.2% recall at a 1% FPR (66.4% at 5%).

Both heads are exported as scaler + coefficients by
``scripts/train_image_classifier.py`` - inference here is numpy only. The CLIP
backbone is loaded lazily with open_clip; when it is unavailable (no weights,
no network, ``LEARNED_IMAGE_CLIP=0``) the render head abstains and the photo
head still votes. The layer also abstains entirely when the model file is
missing, rather than fabricating a score.

Calibrated score mapping (see ``probability_to_score``): probabilities below
0.85 stay below 62 so a weak learned opinion cannot escalate a verdict;
>= 0.85 maps to 62-95, the region where the held-out real-photo false-positive
rate is 8.7% at the bottom (render head) and 1.9% at p >= 0.95, so the voter
treats 62-80 as corroboration rather than proof.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "models", "image_classifier.json"
)
MIN_SIDE = 48

_MODEL_CACHE: Optional[Dict[str, Any]] = None
_MODEL_MTIME: Optional[float] = None
_CLIP_CACHE = None
_CLIP_FAILED = False
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Calibrated probability -> layer score
# ---------------------------------------------------------------------------

def probability_to_score(p: float) -> float:
    """Map a head's probability to the 5-95 layer score.

    Deliberately non-linear: the 62-95 band (which the voter may escalate into
    the suspicious/synthetic tiers) is reserved for probabilities at or above
    0.85, where held-out real-photo false positives fall steeply (8.7% at 0.85,
    1.9% at 0.95 for the render head; 0.9% / 0.4% for the photo head).
    """
    p = float(np.clip(p, 0.0, 1.0))
    if p < 0.5:
        return 5.0 + 50.0 * p
    if p < 0.85:
        return 30.0 + 32.0 * (p - 0.5) / 0.35
    return 62.0 + 33.0 * (p - 0.85) / 0.15


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _load_model() -> Optional[Dict[str, Any]]:
    global _MODEL_CACHE, _MODEL_MTIME
    path = os.environ.get("LEARNED_IMAGE_MODEL", DEFAULT_MODEL_PATH)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with _LOCK:
        if _MODEL_CACHE is not None and _MODEL_MTIME == mtime:
            return _MODEL_CACHE
        try:
            with open(path, "r", encoding="utf-8") as fh:
                _MODEL_CACHE = json.load(fh)
            _MODEL_MTIME = mtime
        except Exception as exc:  # noqa: BLE001
            print(f"Learned image classifier unavailable: {exc}")
            _MODEL_CACHE = None
    return _MODEL_CACHE


def _linear_probability(head: Dict[str, Any], feats: np.ndarray) -> float:
    mean = np.asarray(head["scaler_mean"], dtype=np.float64)
    scale = np.asarray(head["scaler_scale"], dtype=np.float64)
    coef = np.asarray(head["coef"], dtype=np.float64)
    z = float(np.dot((feats - mean) / scale, coef) + float(head["intercept"]))
    # Numerically stable sigmoid
    if z >= 0:
        return 1.0 / (1.0 + np.exp(-z))
    ez = np.exp(z)
    return float(ez / (1.0 + ez))


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _clip_backbone():
    """Lazy CLIP ViT-B/32 loader. Returns (model, preprocess) or None."""
    global _CLIP_CACHE, _CLIP_FAILED
    if os.environ.get("LEARNED_IMAGE_CLIP", "1") in ("0", "false", "no"):
        return None
    if _CLIP_CACHE is not None or _CLIP_FAILED:
        return _CLIP_CACHE
    with _LOCK:
        if _CLIP_CACHE is not None or _CLIP_FAILED:
            return _CLIP_CACHE
        try:
            import torch  # noqa: F401  (open_clip needs torch)
            import open_clip

            model, _, preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="openai", device="cpu"
            )
            model.eval()
            _CLIP_CACHE = (model, preprocess)
            print("Learned image layer: CLIP ViT-B/32 render head loaded.")
        except Exception as exc:  # noqa: BLE001
            _CLIP_FAILED = True
            print(f"Learned image render head unavailable (CLIP): {exc}")
    return _CLIP_CACHE


def clip_embedding(img: Image.Image) -> Optional[np.ndarray]:
    """CLIP embedding used by the render head (public so training matches)."""
    backbone = _clip_backbone()
    if backbone is None:
        return None
    import torch

    model, preprocess = backbone
    try:
        tensor = preprocess(img.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            feats = model.encode_image(tensor)
        return feats[0].cpu().numpy().astype(np.float64)
    except Exception as exc:  # noqa: BLE001
        print(f"Learned image CLIP embedding failed: {exc}")
        return None


def stat_features(img: Image.Image) -> np.ndarray:
    """Feature vector for the photo head, in the model's stored order."""
    from .image_features import extract_features

    feats = extract_features(img)
    model = _load_model() or {}
    names = (model.get("heads", {}).get("photo", {}) or {}).get("feature_names")
    if not names:
        names = sorted(feats.keys())
    return np.asarray([float(feats.get(n, 0.0)) for n in names], dtype=np.float64)


# ---------------------------------------------------------------------------
# Public layer entry point
# ---------------------------------------------------------------------------

def analyze_learned_image(img: Image.Image) -> Dict[str, Any]:
    """Score an image with the dataset-trained heads.

    Returns {"score": int|None, "reasons": [...], "metrics": {...}}.
    score is None when the model is missing or both heads abstain, so callers
    fall back to the rest of the ensemble instead of inventing a vote.
    """
    result: Dict[str, Any] = {"score": None, "reasons": [], "metrics": {}}
    model = _load_model()
    if model is None:
        result["reasons"].append(
            "Dataset-trained image classifier not installed "
            "(run scripts/train_image_classifier.py) - layer inactive."
        )
        return result

    if min(img.size) < MIN_SIDE:
        result["reasons"].append(
            f"Image is too small ({img.size[0]}x{img.size[1]}) for the "
            f"dataset-trained classifier's minimum {MIN_SIDE}px side."
        )
        return result

    heads = model.get("heads", {})
    probabilities: Dict[str, float] = {}

    render_head = heads.get("render")
    if render_head:
        emb = clip_embedding(img)
        if emb is not None and len(emb) == len(render_head.get("coef", [])):
            try:
                probabilities["render"] = _linear_probability(render_head, emb)
            except Exception as exc:  # noqa: BLE001
                print(f"Learned render head failed: {exc}")
        else:
            result["metrics"]["render_head"] = "inactive (CLIP unavailable)"

    photo_head = heads.get("photo")
    if photo_head:
        try:
            probabilities["photo"] = _linear_probability(photo_head, stat_features(img))
        except Exception as exc:  # noqa: BLE001
            print(f"Learned photo head failed: {exc}")

    if not probabilities:
        result["reasons"].append(
            "Dataset-trained classifier heads unavailable for this image; "
            "layer inactive."
        )
        return result

    head_name = max(probabilities, key=probabilities.get)
    p = probabilities[head_name]
    score = int(round(probability_to_score(p)))
    metrics = {
        "render_probability": round(float(probabilities["render"]), 4)
        if "render" in probabilities else None,
        "photo_probability": round(float(probabilities["photo"]), 4)
        if "photo" in probabilities else None,
        "head": head_name,
        "probability": round(float(p), 4),
        "model_trained_at": model.get("trained_at"),
    }
    head_metrics = (heads.get(head_name, {}) or {}).get("metrics", {}) or {}

    label = {
        "render": "AI-render / viral brainrot style",
        "photo": "photorealistic synthetic image",
    }.get(head_name, "AI-generated image")

    if score >= 62:
        detail = (
            f"held-out grouped AUC {head_metrics['grouped_auc']}"
            if head_metrics.get("grouped_auc") is not None else "calibrated on the local corpus"
        )
        tpr = head_metrics.get("tpr_at_fpr_5")
        if isinstance(tpr, (int, float)):
            detail += f", {tpr:.0%} recall at 5% false positives"
        result["reasons"].append(
            f"Dataset-trained classifier: {label} - probability {p:.1%} ({detail}). "
            f"Model trained on the local brainrot and AI-vs-real corpora."
        )
    else:
        result["reasons"].append(
            f"Dataset-trained classifier found no clear AI-render or synthetic "
            f"style signature (best probability {p:.0%})."
        )

    result["score"] = int(np.clip(score, 5, 95))
    result["metrics"] = metrics
    return result
