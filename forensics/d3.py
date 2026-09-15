"""
D3: Detection by Difference of Differences - second-order temporal dynamics
ANALYSIS (metrics layer; deliberately NOT a voting layer - see below).

Implements the measurement core of Zheng et al., "D3: Training-Free
AI-Generated Video Detection Using Second-Order Features" (ICCV 2025,
arXiv:2508.00701). Official code: github.com/Zig-HS/D3.

Paper idea, grounded in a second-order dynamical-systems reading of Newtonian
motion (position/velocity/acceleration): for a frame-feature sequence, the
FIRST-order feature is the feature-space distance between consecutive frames
("velocity"), and the SECOND-order feature is the central difference of that
velocity ("acceleration"). Real videos, shot through physical optics, noisy
sensors and lossy codecs, show CHAOTIC, spiky second-order patterns. Generated
videos are instead TOO SMOOTH: generators interpolate motion, so feature
velocities evolve almost linearly and the acceleration signal is nearly flat.

    !! DIRECTION (frequently mis-stated, including in several 2025 summaries):
       HIGH second-order volatility => REAL. LOW volatility ("too perfect"
       motion) => AI-GENERATED. !!

On GenVideo (10 generators) the paper's detector reaches 98.46% mAP, +10.39%
absolute over the prior state of the art, robust to Gaussian blur and JPEG
compression.

WHY THIS IS A METRICS LAYER, NOT A VOTING LAYER (measured, see
forensics/eval_d3.py)
-----------------------------------------------------------------------------
The paper's statistic is computed on features from a SEMANTIC ENCODER
(XCLIP-B/16; DINOv2 and MobileNet-v3 also validated). The semantic feature
space is what makes "too smooth" separable: encoder features track object
identity and motion semantics, which interpolation makes unnaturally linear.

This server's forensic stack is numpy/PIL-only (torch/detectzoo embeddings
are not exposed - detectzoo provides scores only). In PIXEL/patch feature
space the same statistic does NOT separate, and several variants actively
anti-correlate. Measured on the eval_d3 synthetic corpus (physical camera
motion with sensor noise + JPEG recompression vs generation-style content
evolution):

    global trajectory volatility std(accel)/mean(vel)   real 0.25 vs AI 0.25
    scale-invariant std(accel)/std(vel)                 real 0.77-1.58 vs
                                                        gen-like 1.47-1.74
    per-region second-order volatility                  real 0.15-1.08
                                                        (motion-dependent) vs
                                                        gen-like ~1.01
    flow-field neighbor coherence                       real 0.93-0.99 vs
                                                        gen-like 0.93-0.99

Every variant overlaps or lands on the wrong side: a tripod pan of real
footage (velocity dominated by codec noise => high relative volatility) is
indistinguishable from - or smoother than - locally regenerated content.
Allowing any of these to vote would repeat the measured failure mode that
got the PwTF entropy/hf-share rules retired (they anti-correlated on real
Instagram reels). So, per this repo's calibration rule ("calibrated or not
shipped"), this module REPORTS the second-order statistics in the verdict
for transparency and future recalibration, and never scores.

UPGRADE PATH (to activate voting)
-----------------------------------------------------------------------------
Provide semantic embeddings for the window frames (e.g. torch + DINOv2/XCLIP
on the HF Space deployment, 32 frames x ~1k dims) and pass them via
``analyze_second_order_dynamics(frames, frame_interval_seconds=..., 
encoder_embeddings=Z)``. With encoder features the paper's statistic becomes
meaningful; the layer then scores with direction LOW-volatility => AI and
thresholds calibrated per encoder on real social footage vs generated clips
(see eval_d3.py for the harness pattern). Until then ``score`` stays None.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from .trajectory import frame_descriptors, TRAJ_RES

MIN_FRAMES = 8         # need enough steps for a stable second-order sequence
MOTION_GATE = 1.0      # mean abs inter-frame gray delta (0-255) below => static


def second_order_volatility(velocities: np.ndarray) -> float:
    """The D3 second-order volatility statistic (normalized).

    velocities: (T-1,) first-order frame-distance sequence ("velocity").
    Returns std(central differences) / (mean velocity + eps): how spiky the
    acceleration profile is relative to the speed of change. Per the paper,
    LOW => interpolation-smooth (generation-like), HIGH => physical.
    """
    v = np.asarray(velocities, dtype=np.float64)
    if v.size < 3:
        return 0.0
    accel = v[2:] - v[:-2]
    return float(accel.std() / (v.mean() + 1e-9))


def _region_volatility_profile(
    gray_stack: np.ndarray, cells: int = 8
) -> Dict[str, float]:
    """Per-region second-order volatility over a (T, res, res) gray stack,
    motion-weighted so static background cells don't dominate."""
    T, res, _ = gray_stack.shape
    edges = np.linspace(0, res, cells + 1).astype(int)
    vols = []
    motions = []
    for y0, y1 in zip(edges[:-1], edges[1:]):
        for x0, x1 in zip(edges[:-1], edges[1:]):
            trace = gray_stack[:, y0:y1, x0:x1].mean(axis=(1, 2))
            v = np.abs(np.diff(trace))
            if v.size >= 3:
                vols.append(second_order_volatility(v))
                motions.append(float(v.mean()))
    vols = np.asarray(vols, dtype=np.float64)
    motions = np.asarray(motions, dtype=np.float64)
    w = motions + 1e-9
    mean_vol = float((vols * w).sum() / w.sum())
    return {
        "region_volatility_mean": mean_vol,
        "region_uniformity": float(vols.std() / (mean_vol + 1e-9)),
    }


def _inactive(reason: str, n_frames: int, metrics: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    return {
        "score": None,
        "probability": None,
        "label": "Metrics",
        "reasons": [reason],
        "metrics": metrics or {},
        "frames_analyzed": n_frames,
        "active": False,
        "straighten_metrics": None,
    }


def analyze_second_order_dynamics(
    frames: List[Image.Image],
    frame_interval_seconds: Optional[float] = None,
    res: int = TRAJ_RES,
    min_frames: int = MIN_FRAMES,
    encoder_embeddings: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    D3 (ICCV 2025) second-order temporal dynamics ANALYSIS on a frame clip.

    Reports metrics only (see module docstring for the measured negative
    pixel-space calibration result). ``score`` is None and the layer never
    enters the fusion vote, unless ``encoder_embeddings`` (T x D semantic
    frame features, e.g. DINOv2/XCLIP) are supplied AND the D3_ENCODED_VOTE
    environment flag is enabled after per-encoder calibration - the
    documented upgrade path.

    Args:
        frames: CONTIGUOUS PIL frames at (near) native frame rate.
        frame_interval_seconds: real per-frame spacing; None => inactive.
        res: working resolution for patch descriptors.
        min_frames: minimum clip length for a stable second-order statistic.
        encoder_embeddings: optional (T, D) semantic frame features for the
            encoder-space statistic (upgrade path; not scored by default).
    """
    t0 = time.time()
    if not frames or len(frames) < min_frames or not frame_interval_seconds:
        why = (
            f"Insufficient frames for second-order dynamics analysis "
            f"({len(frames) if frames else 0} provided, minimum {min_frames})."
            if not frames or len(frames) < min_frames else
            "Second-order dynamics inactive: no valid frame interval - velocity "
            "sequences on non-contiguous frames are sampling artifacts."
        )
        return _inactive(why, len(frames) if frames else 0)

    try:
        from .trajectory import trajectory_metrics

        gray = [
            np.asarray(
                f.convert("L").resize((res, res), Image.Resampling.BILINEAR),
                dtype=np.float64,
            )
            for f in frames
        ]
        gray_stack = np.stack(gray, axis=0)              # (T, res, res)

        # Absolute motion gate: a locked-off scene cannot testify about the
        # smoothness of motion it does not contain.
        diffs = np.abs(np.diff(gray_stack, axis=0))
        mean_motion = float(diffs.mean())
        if mean_motion < MOTION_GATE:
            return _inactive(
                f"Second-order dynamics inactive: the scene shows negligible "
                f"motion (mean inter-frame change {mean_motion:.2f}/255), so "
                f"motion smoothness is not measurable.",
                len(frames),
                {"mean_interframe_motion": round(mean_motion, 3)},
            )

        F = frame_descriptors(frames, res=res)           # (T, D)
        steps = np.linalg.norm(np.diff(F, axis=0), axis=1)  # velocity sequence
        vol = second_order_volatility(steps)
        region = _region_volatility_profile(gray_stack)
        straighten = trajectory_metrics(F)

        latency_ms = int((time.time() - t0) * 1000)
        reasons = [
            f"D3 second-order dynamics metrics ({len(frames)} frames @ "
            f"{frame_interval_seconds * 1000:.1f}ms, latency {latency_ms}ms): "
            f"trajectory volatility {vol:.3f}, region volatility "
            f"{region['region_volatility_mean']:.3f}. Reported for "
            f"transparency, not voted: in pixel/patch space this statistic "
            f"overlaps between physical motion and generation (calibrated, "
            f"see forensics/eval_d3.py); the ICCV 2025 result requires "
            f"semantic-encoder features. Direction per paper: LOW volatility "
            f"= too-smooth motion = generation-like.",
        ]

        metrics = {
            "volatility": round(vol, 4),
            "mean_velocity": round(float(steps.mean()), 4),
            "mean_interframe_motion": round(mean_motion, 3),
            **{k: round(v, 4) for k, v in region.items()},
        }

        return {
            "score": None,           # metrics-only by design; see docstring
            "probability": None,
            "label": "Metrics",
            "reasons": reasons,
            "metrics": metrics,
            "frames_analyzed": len(frames),
            "active": False,         # never a vote in pixel space
            "straighten_metrics": straighten,
        }
    except Exception as e:  # noqa: BLE001
        return _inactive(f"Second-order dynamics analysis error: {e}", len(frames))
