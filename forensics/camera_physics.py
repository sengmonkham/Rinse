"""
Camera-physics probe: NATIVE-RESOLUTION sensor-vs-render evidence for
PHOTOREAL diffusion video.

Why this layer exists
---------------------
`forensics/capture_origin.py` catches *rendered image grids* (pixel-art /
flat-shaded animation): exactly-flat fills, byte-identical rows, hard edges.
A photoreal diffusion clip (Higgsfield, Veo, Sora, Kling) has none of those -
it is photoreal *per frame* - so that layer correctly abstains on it.

The tell for photoreal diffusion is different: the frames are not draws from
the same physical camera. A camera imposes physics that a diffusion sampler
never reproduces, and those physics live BELOW the 128x128 grayscale thumbnail
that every temporal layer (PwTF-DVD, temporal-residual, D3, rPPG) sees:

  1. Photon shot noise + read noise make a camera's temporal noise variance a
     LINEAR function of pixel intensity: `var = a*I + b` with `a > 0, b > 0`
     (the photon-transfer curve). A diffusion render has no sensor; whatever
     noise survives re-encoding is a codec property and does not obey that
     curve.
  2. A camera's noise field is partly FIXED across frames (fixed-pattern
     noise / PRNU-like). Generated noise is independent per frame.
  3. A camera's noise in flat regions is spatially WHITE. Warped generated
     texture is smooth (low-frequency).

All three are measured on NATIVE-resolution frames, because that is where the
physics lives. CPU-only, numpy, no weights, no network.

Calibration discipline: this module ships METRICS-ONLY (`score` is None) until
`scripts/probe_camera_physics.py` has run over the labelled corpus and placed a
threshold in a measured gap. It never votes until then, and the calibration
note at the bottom is the single authority for any score mapping.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

MIN_FRAMES = 8

# Flat-region mask: a pixel is "flat" when its local gradient in the temporal
# median frame is below this. Read noise + shot noise are the only things that
# should vary in such a region, so temporal variance there is a pure noise
# measurement (motion through a uniform region contributes almost nothing).
FLAT_GRAD = 6.0

# Fit the photon-transfer curve over intensity bins; skip the darkest/brightest
# bins where the sensor clips and the codec saturates.
_INT_BINS = 20
_MIN_PIX_PER_BIN = 200


def _to_gray(frame: Any) -> np.ndarray:
    """uint8 grayscale, accepting PIL frames or OpenCV BGR/gray arrays."""
    if isinstance(frame, Image.Image):
        return np.asarray(frame.convert("L"), dtype=np.uint8)
    a = np.asarray(frame)
    if a.ndim == 3:
        if a.shape[2] == 4:
            a = a[..., :3]
        # OpenCV convention: BGR.
        a = 0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2]
    return np.clip(a, 0, 255).astype(np.uint8)


def _flat_mask(med: np.ndarray, grad_thresh: float = FLAT_GRAD) -> np.ndarray:
    """Boolean mask of flat, unsaturated pixels in the temporal-median frame."""
    g = med.astype(np.float32)
    gx = np.abs(np.diff(g, axis=1, append=g[:, -1:]))
    gy = np.abs(np.diff(g, axis=0, append=g[-1:, :]))
    grad = np.hypot(gx, gy)
    return (grad < grad_thresh) & (g > 8.0) & (g < 248.0)


def _sensor_noise_curve(grays: List[np.ndarray]) -> Dict[str, float]:
    """Photon-transfer curve: temporal noise variance vs pixel intensity.

    Uses consecutive frame differences (an Allan-variance-like estimator) so a
    slow exposure drift does not masquerade as noise, then bins flat pixels by
    intensity and fits `var = a*I + b`. A camera gives a>0, b>0 and a tight
    linear fit; a diffusion render + codec gives a flat or non-linear curve.
    """
    arr = np.stack([g.astype(np.float32) for g in grays])  # (N,H,W)
    med = np.median(arr, axis=0)
    # Per-pixel temporal variance from consecutive diffs (/2: diff of two
    # independent samples doubles the variance).
    if arr.shape[0] < 2:
        return {}
    diffs = np.diff(arr, axis=0)
    var = np.mean(diffs * diffs, axis=0) * 0.5

    flat = _flat_mask(med)
    I = med[flat].ravel()
    v = var[flat].ravel()
    n_flat = int(I.size)
    if n_flat < 2000:
        return {"noise_n_flat_px": float(n_flat)}

    edges = np.linspace(0.0, 256.0, _INT_BINS + 1)
    idx = np.clip(np.digitize(I, edges) - 1, 0, _INT_BINS - 1)
    bin_i = np.bincount(idx, weights=I, minlength=_INT_BINS)
    bin_v = np.bincount(idx, weights=v, minlength=_INT_BINS)
    bin_n = np.bincount(idx, minlength=_INT_BINS).astype(np.float32)

    use = bin_n >= _MIN_PIX_PER_BIN
    I_bin = bin_i[use] / bin_n[use]
    v_bin = bin_v[use] / bin_n[use]
    w_bin = bin_n[use]
    if I_bin.size < 5:
        return {"noise_n_flat_px": float(n_flat)}

    # Weighted least-squares: var = a*I + b.
    W = w_bin / w_bin.sum()
    mI = float(np.sum(W * I_bin))
    mV = float(np.sum(W * v_bin))
    sII = float(np.sum(W * (I_bin - mI) ** 2))
    sIV = float(np.sum(W * (I_bin - mI) * (v_bin - mV)))
    slope = sIV / sII if sII > 1e-9 else 0.0
    intercept = mV - slope * mI

    fit = slope * I_bin + intercept
    resid = v_bin - fit
    # Normalized residual: fraction of the variance magnitude not explained by
    # the linear photon-transfer model. A camera's curve is close to linear, so
    # this is small; a codec/render curve is not, so it is large.
    resid_norm = float(np.sqrt(np.sum(W * resid ** 2)) / (np.sqrt(np.sum(W * v_bin ** 2)) + 1e-9))
    # Coefficient of determination (weighted).
    ss_tot = float(np.sum(W * (v_bin - mV) ** 2))
    rsq = 1.0 - float(np.sum(W * resid ** 2)) / (ss_tot + 1e-9)

    # Bright-vs-dark noise ratio: shot noise makes bright regions noisier.
    order = np.argsort(I_bin)
    half = max(1, I_bin.size // 3)
    dark = I_bin[order[:half]]
    bright = I_bin[order[-half:]]
    v_dark = float(np.mean(v_bin[order[:half]]))
    v_bright = float(np.mean(v_bin[order[-half:]]))
    bright_dark = v_bright / (v_dark + 1e-9)

    # Spearman rank correlation between intensity and noise variance (a
    # monotonicity check that is robust to the exact curve shape).
    if I_bin.size >= 3:
        rI = np.argsort(np.argsort(I_bin)).astype(np.float64)
        rV = np.argsort(np.argsort(v_bin)).astype(np.float64)
        rc = np.corrcoef(rI, rV)[0, 1]
        spearman = float(rc) if np.isfinite(rc) else 0.0
    else:
        spearman = 0.0

    return {
        "noise_n_flat_px": float(n_flat),
        "noise_slope": round(slope, 6),
        "noise_intercept": round(intercept, 6),
        "noise_rsq": round(rsq, 6),
        "noise_resid_norm": round(resid_norm, 6),
        "noise_spearman": round(spearman, 6),
        "noise_bright_dark": round(bright_dark, 6),
        "noise_v_min": round(float(np.min(v_bin)), 6),
        "noise_v_max": round(float(np.max(v_bin)), 6),
    }


def _fixed_pattern_noise(grays: List[np.ndarray]) -> Dict[str, float]:
    """Fixed-pattern-noise ratio: how much of the temporal noise is FIXED
    across frames (a camera's per-pixel sensitivity pattern) vs independent
    per frame (a generator's independent per-frame synthesis)."""
    arr = np.stack([g.astype(np.float32) for g in grays])  # (N,H,W)
    med = np.median(arr, axis=0)
    noise = arr - med  # (N,H,W): temporal residual around the static scene

    per_pixel_var = np.mean(noise * noise, axis=0)  # (H,W)
    fixed = np.mean(noise, axis=0)  # (H,W): temporal-mean residual (FPN field)
    fixed_var = float(np.var(fixed))
    mean_var = float(np.mean(per_pixel_var))

    # Frame-difference correlation: with a fixed component `f` plus independent
    # per-frame noise, consecutive diffs are negatively correlated; with pure
    # independent noise they are uncorrelated.
    if arr.shape[0] >= 3:
        d0 = (arr[1] - arr[0]).astype(np.float64).ravel()
        d1 = (arr[2] - arr[1]).astype(np.float64).ravel()
        step = max(1, d0.size // 200000)  # subsample for speed
        c = np.corrcoef(d0[::step], d1[::step])[0, 1]
        diff_corr = float(c) if np.isfinite(c) else 0.0
    else:
        diff_corr = 0.0

    return {
        "fpn_ratio": round(fixed_var / (mean_var + 1e-9), 6),
        "fpn_fixed_var": round(fixed_var, 6),
        "fpn_mean_var": round(mean_var, 6),
        "fpn_diff_corr": round(diff_corr, 6),
    }


def _residual_spectrum(grays: List[np.ndarray]) -> Dict[str, float]:
    """Two complementary residual statistics in flat regions.

    1. Noise whiteness (`noise_ac1_*`): lag-1 autocorrelation of the PER-FRAME
       noise residual (frame minus local box mean). Camera sensor noise is
       spatially white; a diffusion render's per-frame residual is smooth.

    2. Texture smoothness (`tex_ac1_*`): lag-1 autocorrelation of the
       TEMPORAL-MEDIAN frame's high-pass residual. The median removes sensor
       noise but keeps the static texture (skin pores, fabric, foliage). A
       photoreal render's static texture is smoother/cleaner than a camera's,
       so its residual is more autocorrelated.

    Flat regions come from the temporal-median gradient so the mask is stable
    across frames.
    """
    arr = np.stack([g.astype(np.float32) for g in grays])  # (N,H,W)
    med = np.median(arr, axis=0)
    flat = _flat_mask(med)
    n_flat = int(flat.sum())
    if n_flat < 2000:
        return {"resid_n_flat_px": float(n_flat)}

    from numpy.lib.stride_tricks import sliding_window_view  # noqa: PLC0415

    def _ac1(resid: np.ndarray) -> tuple:
        rf = resid.astype(np.float64)
        fh = flat[:, :-1] & flat[:, 1:]
        fv = flat[:-1, :] & flat[1:, :]
        num_h = np.sum(rf[:, :-1][fh] * rf[:, 1:][fh])
        num_v = np.sum(rf[:-1, :][fv] * rf[1:, :][fv])
        den_h = np.sum(rf[:, :-1][fh] ** 2) + np.sum(rf[:, 1:][fh] ** 2) + 1e-9
        den_v = np.sum(rf[:-1, :][fv] ** 2) + np.sum(rf[1:, :][fv] ** 2) + 1e-9
        return float(num_h / den_h), float(num_v / den_v)

    # 1. Per-frame noise residual (3x3 box removes the smooth signal).
    k3 = np.ones((3, 3), dtype=np.float32) / 9.0
    pad3 = np.pad(arr, ((0, 0), (1, 1), (1, 1)), mode="reflect")
    win3 = sliding_window_view(pad3, (1, 3, 3)).reshape(arr.shape[0], arr.shape[1], arr.shape[2], 9)
    low3 = np.tensordot(win3, k3.ravel(), axes=([3], [0]))
    noise = arr - low3  # (N,H,W)
    noise_ac_h = []
    noise_ac_v = []
    for t in range(noise.shape[0]):
        ah, av = _ac1(noise[t])
        noise_ac_h.append(ah)
        noise_ac_v.append(av)

    # 2. Median-frame texture residual (5x5 box removes the smooth signal).
    k5 = np.ones((5, 5), dtype=np.float32) / 25.0
    pad5 = np.pad(med, ((2, 2), (2, 2)), mode="reflect")
    win5 = sliding_window_view(pad5, (5, 5)).reshape(med.shape[0], med.shape[1], 25)
    low5 = np.tensordot(win5, k5.ravel(), axes=([2], [0]))
    tex = med - low5
    tex_ac_h, tex_ac_v = _ac1(tex)

    return {
        "resid_n_flat_px": float(n_flat),
        "noise_ac1_h": round(float(np.mean(noise_ac_h)), 6),
        "noise_ac1_v": round(float(np.mean(noise_ac_v)), 6),
        "noise_ac1": round(float(np.mean(noise_ac_h + noise_ac_v)), 6),
        "tex_ac1_h": round(tex_ac_h, 6),
        "tex_ac1_v": round(tex_ac_v, 6),
        "tex_ac1": round(0.5 * (tex_ac_h + tex_ac_v), 6),
    }


def analyze_camera_physics(frames: List[Any]) -> Dict[str, Any]:
    """Measure camera-sensor physics over a contiguous native-resolution window.

    Returns a dict with `score` (None = metrics-only until calibrated),
    `active`, `metrics`, `reasons` and `detail`. Never raises.
    """
    try:
        grays = [_to_gray(f) for f in frames if f is not None]
        if len(grays) < MIN_FRAMES:
            return {
                "score": None,
                "active": False,
                "metrics": {},
                "reasons": [
                    f"Camera-physics probe inactive: {len(grays)} usable frame(s), "
                    f"needs at least {MIN_FRAMES}."
                ],
                "detail": {},
            }

        metrics: Dict[str, float] = {
            "frames": float(len(grays)),
            "resolution": float(grays[0].shape[0] * grays[0].shape[1]),
        }
        metrics.update(_sensor_noise_curve(grays))
        metrics.update(_fixed_pattern_noise(grays))
        metrics.update(_residual_spectrum(grays))

        reasons = [
            f"Camera-physics probe (native {grays[0].shape[1]}x{grays[0].shape[0]}, "
            f"{len(grays)} frames): photon-transfer slope {metrics.get('noise_slope', float('nan')):.4f}, "
            f"intercept {metrics.get('noise_intercept', float('nan')):.4f}, "
            f"fit residual {metrics.get('noise_resid_norm', float('nan')):.4f}, "
            f"bright/dark noise ratio {metrics.get('noise_bright_dark', float('nan')):.3f}, "
            f"fixed-pattern ratio {metrics.get('fpn_ratio', float('nan')):.4f}, "
            f"noise lag-1 autocorr {metrics.get('noise_ac1', float('nan')):.4f}, "
            f"texture lag-1 autocorr {metrics.get('tex_ac1', float('nan')):.4f}."
        ]

        # METRICS-ONLY until calibrated (see the module note). No score is
        # emitted, so this layer never votes on a verdict yet.
        return {
            "score": None,
            "active": False,
            "metrics": {k: round(v, 6) if isinstance(v, float) else v for k, v in metrics.items()},
            "reasons": reasons,
            "detail": {"frames_sampled": len(grays)},
        }
    except Exception as e:  # noqa: BLE001 - metrics layer must never break a verdict
        return {
            "score": None,
            "active": False,
            "metrics": {},
            "reasons": [f"Camera-physics probe unavailable: {e}"],
            "detail": {},
        }
