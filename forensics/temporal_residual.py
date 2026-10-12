"""
Cheap full-resolution temporal residual probe for video clips.

Design: on a contiguous native-fps window, predict each frame from the average of
its temporal neighbors (a training-free predictor) and measure the residual. Real
footage has physically persistent texture, so residuals look like local motion +
sensor/compression noise and stay spatially structured. Generated footage whose
frames are synthesized semi-independently can leave residuals that are larger
and/or less spatially structured (whiter) in regenerated regions.

This is a BROADER net than the existing PwTF-DVD rules, which key on coherence-floor
collapse + hotspot cluster. It is NOT a replacement; it is a complementary signal
that runs on full-res frames and may catch cases where PwTF sees a healthy floor.

Calibrate thresholds on a real-reel corpus before promoting any non-trivial rule to a
vote. Until then the probe reports metrics and only assigns a score when a clear,
conservative threshold is crossed.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    _NP_AVAILABLE = True
except ImportError:  # pragma: no cover - degrades to inactive
    np = None  # type: ignore[assignment]
    _NP_AVAILABLE = False

try:
    import cv2  # noqa: F401
    _CV_AVAILABLE = True
except ImportError:
    _CV_AVAILABLE = False

# Vote thresholds. A clip is flagged when residual energy is high AND residuals
# are spatially unstructured (white-ish) in a meaningful fraction of the frame.
#
# STRICT MODE (VIDEO_STRICT, default ON) lowers the gate to bias toward recall:
#   default : energy > 0.018 AND white_frac > 0.45
#   strict  : energy > 0.014 AND white_frac > 0.30
# Measured margin (2026-10-12): real clips read white_frac 0.103 (local) and
# tr=None (human Instagram post), so the strict 0.30 floor keeps them silent;
# the known-AI clips read 0.47 and 0.93. Both bands are env-overridable for
# calibration on the expanded real-reel corpus.
_STRICT = os.environ.get("VIDEO_STRICT", "1") not in ("0", "false", "no")
_RESIDUAL_ENERGY_HIGH = float(os.environ.get(
    "TR_RESIDUAL_ENERGY_HIGH", "0.014" if _STRICT else "0.018"))
_RESIDUAL_WHITE_FRAC = float(os.environ.get(
    "TR_RESIDUAL_WHITE_FRAC", "0.30" if _STRICT else "0.45"))
_RESIDUAL_WHITE_THRESHOLD = 0.06  # residual magnitude below which a pixel is "structured"


def _to_gray_float(frame: Any) -> Optional[np.ndarray]:
    """Convert a PIL RGB image or numpy array to a float32 grayscale HxW array."""
    if frame is None:
        return None
    try:
        if hasattr(frame, "convert"):
            arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
        else:
            arr = np.asarray(frame, dtype=np.float32)
        if arr.ndim == 3 and arr.shape[2] >= 3:
            g = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
        elif arr.ndim == 2:
            g = arr.astype(np.float32)
        else:
            return None
        g = g / 255.0
        return g
    except Exception:
        return None


def _predict_residuals(frames_gray: List[np.ndarray]) -> Tuple[np.ndarray, List[str]]:
    """Predict each frame as the mean of its temporal neighbors and return residuals.

    For interior frames: predict = mean(prev, next).
    For first frame: predict = next.
    For last frame: predict = prev.
    Returns (residuals HxWxN normalized 0..1, reasons).
    """
    n = len(frames_gray)
    if n < 3:
        return np.array([]), ["Too few frames for temporal residual prediction (need >= 3)."]

    residuals = []
    reasons = []
    for i in range(n):
        if i == 0:
            pred = frames_gray[1]
        elif i == n - 1:
            pred = frames_gray[n - 2]
        else:
            pred = (frames_gray[i - 1] + frames_gray[i + 1]) * 0.5
        resid = np.abs(frames_gray[i] - pred)
        residuals.append(resid)
    R = np.stack(residuals, axis=-1)  # HxWxN
    return R, reasons


def analyze_temporal_residual(frames: List[Any]) -> Dict[str, Any]:
    """Run the cheap full-res temporal residual probe on a frame window.

    Args:
        frames: list of PIL RGB images or numpy arrays (contiguous, native-fps).

    Returns dict with score/active/reasons/metrics. score is None until calibration.
    """
    reasons: List[str] = []
    metrics: Dict[str, Any] = {"n_frames": len(frames)}

    if not _NP_AVAILABLE:
        return {
            "score": None,
            "active": False,
            "reasons": ["Temporal residual probe unavailable: numpy not available."],
            "metrics": metrics,
        }

    grays = []
    for f in frames:
        g = _to_gray_float(f)
        if g is None:
            return {
                "score": None,
                "active": False,
                "reasons": ["Temporal residual probe: could not convert a frame to grayscale."],
                "metrics": metrics,
            }
        grays.append(g)

    if len(grays) < 3:
        return {
            "score": None,
            "active": False,
            "reasons": [f"Too few frames ({len(grays)}) for temporal residual probe."],
            "metrics": metrics,
        }

    R, pred_reasons = _predict_residuals(grays)
    metrics["predictor"] = "neighbor_mean"
    reasons.extend(pred_reasons)

    # Normalize energy relative to the frame's own brightness range so clips with
    # different exposure stay comparable. Use the pooled per-pixel mean luminance as
    # a rough scale; avoid divide-by-zero.
    mean_lum = float(np.mean(np.stack(grays, axis=-1)))
    scale = max(mean_lum, 1e-3)
    resid_norm = R / scale

    # Per-pixel residual energy (mean abs residual across time).
    energy_map = float(resid_norm.mean()) if R.size else 0.0
    metrics["residual_energy_mean"] = round(energy_map, 5)

    # Spatial variation of residual energy: real motion residuals are spatially
    # structured (edges/motion boundaries); white noise residuals are spatially
    # uniform-ish. Compute CV of per-pixel energy across the frame.
    per_pixel_energy = resid_norm.mean(axis=-1)  # HxW
    energy_cv = float(np.std(per_pixel_energy) / (np.mean(per_pixel_energy) + 1e-6))
    metrics["residual_energy_cv"] = round(energy_cv, 4)

    # "White fraction": fraction of pixels whose residual is small and uniform across
    # time (i.e. the predictor already explained them). A higher white fraction with
    # high overall energy is a mild sign of structured-but-predictable motion (real);
    # a LOWER white fraction at high energy is more consistent with per-pixel noise.
    flat_frac = float((per_pixel_energy < _RESIDUAL_WHITE_THRESHOLD).mean())
    metrics["residual_flat_fraction"] = round(flat_frac, 4)
    metrics["residual_white_frac"] = round(1.0 - flat_frac, 4)

    # Count how many pixels are "hot" in residual energy.
    hot_frac = float((per_pixel_energy > 0.05).mean())
    metrics["residual_hot_frac"] = round(hot_frac, 4)

    reasons.append(
        f"Temporal residual probe (neighbor-mean predictor, {len(grays)} frames): "
        f"mean residual energy {energy_map:.4f}, spatial energy CV {energy_cv:.3f}, "
        f"flat fraction {flat_frac*100:.1f}%, hot fraction {hot_frac*100:.2f}%."
    )

    # Score: start conservative. Only vote when energy is clearly high AND the
    # residual is spatially unstructured (white-ish), which is the more generation-
    # like profile. Calibrate before widening.
    score: Optional[int] = None
    if energy_map > _RESIDUAL_ENERGY_HIGH and (1.0 - flat_frac) > _RESIDUAL_WHITE_FRAC:
        score = 62
        reasons.append(
            "Temporal residual probe flagged high residual energy with a spatially "
            "unstructured (white-ish) residual profile - a possible generation-style "
            "temporal signal. This is an uncalibrated heuristic; treat as a weak vote."
        )
    elif energy_map > _RESIDUAL_ENERGY_HIGH:
        reasons.append(
            "Temporal residual probe: elevated residual energy but residual remains "
            "spatially structured - consistent with real motion; not flagged."
        )

    metrics["residual_score"] = score
    return {
        "score": score,
        "active": True,
        "reasons": reasons,
        "metrics": metrics,
    }
