"""
Representation-trajectory forensics for video frames.

Two things live here:

1. ``frame_descriptors`` - a lightweight, deterministic per-frame feature
   extractor (multi-scale patch means + gradient energy + color means,
   variance-normalized). It is the training-free stand-in for the visual
   encoders the papers use (XCLIP/DINOv2 in D3 and ReStraV): the geometry of
   the sequence of these descriptors over time is what the temporal layers
   measure. No weights, no torch, CPU-only.

2. ``trajectory_metrics`` - a ReStraV-inspired measurement of the descriptor
   trajectory's *shape*: stepwise distances (how far the video moves through
   feature space per frame) and curvature angles (how sharply that path bends).

   IMPORTANT - this is an APPROXIMATION, deliberately kept out of the vote.
   The published ReStraV detector (Internò et al. 2025, arXiv:2507.00583)
   computes these exact statistics in DINOv2's representation space, where a
   "perceptual straightening" property holds: real videos trace straighter
   paths than generated ones (a 45.46-degree mean-curvature gap), and a
   lightweight trained classifier on those statistics reaches 97.17% accuracy
   on VidProM. In a raw pixel/patch feature space that straightening property
   does NOT hold - this repo's calibration history (pwtf entropy/hf-share
   anti-correlated on real reels) shows what happens when unvalidated feature
   spaces are allowed to vote. So the metrics are computed and reported for
   transparency and future calibration, and the layer does NOT score.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from PIL import Image

TRAJ_RES = 96         # working resolution for descriptor extraction
TRAJ_GRID = 16        # fine patch grid (grid x grid patch means)
COARSE_GRID = 8       # coarse pooling of gradient energy


# ---------------------------------------------------------------------------
# Per-frame descriptor extraction
# ---------------------------------------------------------------------------

def _pool_cells(plane: np.ndarray, grid: int) -> np.ndarray:
    """Mean-pool a (res, res) plane into a (grid, grid) cell grid, flattened."""
    res = plane.shape[0]
    edges = np.linspace(0, res, grid + 1).astype(int)
    cells = np.empty(grid * grid, dtype=np.float64)
    k = 0
    for y0, y1 in zip(edges[:-1], edges[1:]):
        for x0, x1 in zip(edges[:-1], edges[1:]):
            cells[k] = plane[y0:y1, x0:x1].mean()
            k += 1
    return cells


def frame_descriptors(
    frames: List[Image.Image],
    res: int = TRAJ_RES,
    grid: int = TRAJ_GRID,
    coarse: int = COARSE_GRID,
) -> np.ndarray:
    """
    Build one descriptor vector per frame; returns a (T, D) float64 matrix.

    Per frame the descriptor concatenates
      - fine patch-mean intensities   (grid x grid = 256 dims)
      - coarse gradient-energy cells  (coarse x coarse = 64 dims)
      - fine gradient-energy cells    (grid x grid = 256 dims)
      - mean R/G/B                    (3 dims)

    Every dimension is z-scored ACROSS THE CLIP (per-dimension) so that a
    distance between consecutive frames is measured in units of the clip's own
    variation along that dimension - a static background patch contributes ~0
    to frame distances no matter how bright it is, while a moving patch
    dominates. Without this, bright flat regions would swamp the geometry.
    """
    stack = []
    for f in frames:
        g = f.convert("L").resize((res, res), Image.Resampling.BILINEAR)
        gray = np.asarray(g, dtype=np.float64)
        rgb = np.asarray(
            f.convert("RGB").resize((res, res), Image.Resampling.BILINEAR),
            dtype=np.float64,
        )
        gy, gx = np.gradient(gray)
        grad_mag = np.sqrt(gx * gx + gy * gy)
        desc = np.concatenate([
            _pool_cells(gray, grid),
            _pool_cells(grad_mag, coarse),
            _pool_cells(grad_mag, grid),
            rgb.reshape(-1, 3).mean(axis=0),
        ])
        stack.append(desc)
    F = np.stack(stack, axis=0)
    # Per-dimension z-scoring across the clip (guards against zero variance).
    mu = F.mean(axis=0, keepdims=True)
    sd = F.std(axis=0, keepdims=True)
    sd[sd < 1e-6] = 1.0
    return (F - mu) / sd


# ---------------------------------------------------------------------------
# ReStraV-style trajectory geometry (metrics only - see module docstring)
# ---------------------------------------------------------------------------

def trajectory_metrics(descriptors: np.ndarray) -> Dict[str, float]:
    """
    Geometric statistics of the descriptor trajectory z_1..z_T:
      - stepwise distance  d_i = || z_{i+1} - z_i ||            (ReStraV d_i)
      - curvature angle    theta_i = angle( dz_i , dz_{i+1} )   (ReStraV theta_i)
      - path efficiency    chord / arc length (1.0 = perfectly straight)

    These mirror the features of ReStraV (arXiv:2507.00583), reported here in
    a pixel-space proxy. Metrics only - never voted (see module docstring).
    """
    F = descriptors
    T = F.shape[0]
    steps = np.diff(F, axis=0)                     # (T-1, D)
    step_dist = np.linalg.norm(steps, axis=1)      # (T-1,)

    # Curvature between successive displacement vectors.
    norms = step_dist[:-1] * step_dist[1:]
    valid = norms > 1e-9
    curvature_deg = np.full(T - 2, np.nan)
    if valid.any():
        cosang = np.clip(
            (steps[:-1] * steps[1:]).sum(axis=1)[valid] / norms[valid],
            -1.0, 1.0,
        )
        curvature_deg[valid] = np.degrees(np.arccos(cosang))
    curv = curvature_deg[~np.isnan(curvature_deg)]

    # Path efficiency: net displacement over travelled distance.
    arc = float(step_dist.sum())
    chord = float(np.linalg.norm(steps.sum(axis=0))) if T > 1 else 0.0
    efficiency = float(chord / arc) if arc > 1e-9 else 0.0

    return {
        "steps": int(T - 1),
        "step_distance_mean": round(float(step_dist.mean()), 4),
        "step_distance_std": round(float(step_dist.std()), 4),
        "curvature_mean_deg": round(float(curv.mean()), 2) if curv.size else 0.0,
        "curvature_std_deg": round(float(curv.std()), 2) if curv.size else 0.0,
        "path_efficiency": round(efficiency, 4),
    }
