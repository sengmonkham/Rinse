"""Cheap, dependency-light pixel-statistics features for the learned image layer.

Everything here is computed from the decoded pixels only (no file metadata), at a
fixed 256x256 working size so images from different sources are directly
comparable. The vector feeds the linear/GBM classifier trained by
``scripts/train_image_classifier.py`` (see forensics/learned_image.py).

Design constraints:

* numpy + PIL only - no torch, no scikit-learn at inference time.
* deterministic and fast enough for the /predict/image/fast path (<100 ms).
* resolution/format shortcuts are limited by resizing every image to the same
  size before measuring, and by pooling AI sources that differ in format (the
  brainrot corpus is JPEG, the Ai_generated_dataset is PNG).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
from PIL import Image, ImageFilter

WORK_SIZE = 256
_FEATURE_NAMES: List[str] | None = None


def feature_names() -> List[str]:
    """Stable, ordered feature names (defined by extracting a dummy image)."""
    global _FEATURE_NAMES
    if _FEATURE_NAMES is None:
        dummy = Image.new("RGB", (WORK_SIZE, WORK_SIZE), (127, 127, 127))
        _FEATURE_NAMES = sorted(extract_features(dummy).keys())
    return list(_FEATURE_NAMES)


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a.ravel().astype(np.float64)
    b = b.ravel().astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if denom < 1e-12:
        return 0.0
    return float((a * b).sum() / denom)


def _radial_spectrum(luma: np.ndarray, bins: int = 8) -> np.ndarray:
    """Normalized log radial power spectrum of the mean-subtracted luma."""
    f = np.fft.fftshift(np.fft.fft2(luma - luma.mean()))
    power = (f.real ** 2 + f.imag ** 2)
    h, w = power.shape
    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    r = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    r_max = float(r.max())
    out = np.zeros(bins, dtype=np.float64)
    total = float(power.sum()) or 1.0
    for i in range(bins):
        lo = r_max * i / bins
        hi = r_max * (i + 1) / bins
        mask = (r >= lo) & (r < hi) if i < bins - 1 else (r >= lo)
        out[i] = float(power[mask].sum()) / total
    return out


def _spectral_flatness(luma: np.ndarray) -> float:
    f = np.fft.fftshift(np.fft.fft2(luma - luma.mean()))
    power = (f.real ** 2 + f.imag ** 2).ravel()
    power = power[power > 0]
    if power.size == 0:
        return 0.0
    return float(np.exp(np.log(power).mean()) / (power.mean() + 1e-12))


def _azimuthal_peak(power_map: np.ndarray) -> float:
    """Max energy concentration along one angle (GAN upsampling grid tell)."""
    h, w = power_map.shape
    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    ang = np.arctan2(y - cy, x - cx)
    r = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    ring = (r > 4) & (r < min(h, w) * 0.45)
    if not ring.any():
        return 0.0
    nb = 36
    idx = ((ang[ring] + np.pi) / (2 * np.pi) * nb).astype(np.int32) % nb
    vals = power_map[ring]
    prof = np.zeros(nb)
    np.add.at(prof, idx, vals)
    mean = float(prof.mean()) + 1e-12
    return float(prof.max() / mean)


def _jpeg_blockiness(luma: np.ndarray) -> float:
    """Ratio of 8x8 block-boundary energy to interior high-frequency energy."""
    dh = np.abs(np.diff(luma, axis=1))
    dv = np.abs(np.diff(luma, axis=0))
    bh = dh[:, 7::8].mean() if dh.shape[1] > 8 else 0.0
    bv = dv[7::8, :].mean() if dv.shape[0] > 8 else 0.0
    ih = dh.mean() + 1e-6
    iv = dv.mean() + 1e-6
    return float(((bh / ih) + (bv / iv)) / 2.0)


def _kurtosis(x: np.ndarray) -> float:
    x = x.ravel().astype(np.float64)
    sd = float(x.std())
    if sd < 1e-9:
        return 0.0
    z = (x - x.mean()) / sd
    return float((z ** 4).mean())


def extract_features(img: Image.Image) -> Dict[str, float]:
    """Extract the feature dict for one image (RGB or any PIL mode)."""
    rgb = img.convert("RGB").resize((WORK_SIZE, WORK_SIZE), Image.Resampling.LANCZOS)
    arr = np.asarray(rgb).astype(np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    luma = 0.299 * r + 0.587 * g + 0.114 * b

    feats: Dict[str, float] = {}

    # --- Global color / luminance statistics ---
    for name, ch in (("r", r), ("g", g), ("b", b), ("luma", luma)):
        feats[f"{name}_mean"] = float(ch.mean()) / 255.0
        feats[f"{name}_std"] = float(ch.std()) / 255.0

    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    feats["sat_mean"] = float(sat.mean())
    feats["sat_std"] = float(sat.std())
    feats["sat_p10"] = float(np.percentile(sat, 10))
    feats["sat_p90"] = float(np.percentile(sat, 90))

    # Hasler-Suesstrunk colorfulness
    rg = r - g
    yb = 0.5 * (r + g) - b
    feats["colorfulness"] = float(
        (np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)) / 255.0
    )

    # Distinct quantized colors and histogram entropy
    quant = (arr.astype(np.uint8) >> 4).reshape(-1, 3)
    uniq = np.unique(quant, axis=0)
    feats["unique_colors"] = float(len(uniq)) / 4096.0
    hist, _ = np.histogram(luma, bins=32, range=(0, 256))
    p = hist.astype(np.float64)
    p = p / (p.sum() + 1e-12)
    feats["luma_entropy"] = float(-(p[p > 0] * np.log2(p[p > 0])).sum())

    hsv = np.asarray(rgb.convert("HSV")).astype(np.float32)
    hh, _ = np.histogram(hsv[..., 0], bins=24, range=(0, 256))
    ph = hh.astype(np.float64)
    ph = ph / (ph.sum() + 1e-12)
    feats["hue_entropy"] = float(-(ph[ph > 0] * np.log2(ph[ph > 0])).sum())
    feats["val_mean"] = float(hsv[..., 2].mean()) / 255.0

    # --- Edges / gradients ---
    edges = np.asarray(rgb.convert("L").filter(ImageFilter.FIND_EDGES)).astype(np.float32)
    feats["edge_mean"] = float(edges.mean()) / 255.0
    feats["edge_std"] = float(edges.std()) / 255.0
    feats["edge_density_30"] = float((edges > 30).mean())
    feats["edge_density_60"] = float((edges > 60).mean())
    feats["edge_density_120"] = float((edges > 120).mean())

    gy, gx = np.gradient(luma)
    grad = np.sqrt(gx ** 2 + gy ** 2)
    feats["grad_mean"] = float(grad.mean()) / 255.0
    feats["grad_std"] = float(grad.std()) / 255.0
    feats["grad_p90"] = float(np.percentile(grad, 90)) / 255.0
    feats["grad_p99"] = float(np.percentile(grad, 99)) / 255.0

    lap = (
        -4.0 * luma[1:-1, 1:-1]
        + luma[:-2, 1:-1] + luma[2:, 1:-1]
        + luma[1:-1, :-2] + luma[1:-1, 2:]
    )
    feats["lap_var"] = float(lap.var()) / (255.0 ** 2)
    feats["lap_kurtosis"] = _kurtosis(lap) / 100.0

    # --- Local smoothness (8x8 patches) ---
    patch = luma.reshape(WORK_SIZE // 8, 8, WORK_SIZE // 8, 8).transpose(0, 2, 1, 3)
    patch_std = patch.std(axis=(2, 3))
    feats["patch_std_mean"] = float(patch_std.mean()) / 255.0
    feats["patch_std_std"] = float(patch_std.std()) / 255.0
    feats["patch_std_p10"] = float(np.percentile(patch_std, 10)) / 255.0
    feats["patch_std_p25"] = float(np.percentile(patch_std, 25)) / 255.0
    feats["patch_std_p50"] = float(np.percentile(patch_std, 50)) / 255.0
    feats["patch_std_p90"] = float(np.percentile(patch_std, 90)) / 255.0
    feats["flat_ratio_3"] = float((patch_std < 3.0).mean())
    feats["flat_ratio_8"] = float((patch_std < 8.0).mean())

    # --- Spectrum ---
    rad = _radial_spectrum(luma)
    for i, v in enumerate(rad):
        feats[f"spec_band_{i}"] = float(v)
    feats["spec_flatness"] = _spectral_flatness(luma)
    feats["spec_hf_ratio"] = float(rad[-2:].sum())
    feats["spec_mid_ratio"] = float(rad[2:5].sum())

    f = np.fft.fftshift(np.fft.fft2(luma - luma.mean()))
    feats["spec_azimuthal_peak"] = _azimuthal_peak(f.real ** 2 + f.imag ** 2) / 100.0

    # --- Noise residual (high-pass) ---
    blur = np.asarray(rgb.filter(ImageFilter.GaussianBlur(1.0))).astype(np.float32)
    resid = arr - blur
    feats["resid_std"] = float(resid.std()) / 255.0
    feats["resid_absmean"] = float(np.abs(resid).mean()) / 255.0
    feats["resid_kurtosis"] = _kurtosis(resid) / 100.0
    feats["resid_sparse"] = float((np.abs(resid) > 6).mean())
    rr, rg_r, rb_r = resid[..., 0], resid[..., 1], resid[..., 2]
    feats["resid_corr_rg"] = _safe_corr(rr, rg_r)
    feats["resid_corr_rb"] = _safe_corr(rr, rb_r)
    feats["resid_ac1_h"] = _safe_corr(resid[:, 1:], resid[:, :-1])
    feats["resid_ac1_v"] = _safe_corr(resid[1:, :], resid[:-1, :])

    # --- Compression / sampling tells ---
    feats["jpeg_blockiness"] = _jpeg_blockiness(luma)
    feats["luma_range"] = float(np.percentile(luma, 99) - np.percentile(luma, 1)) / 255.0
    feats["dark_frac"] = float((luma < 24).mean())
    feats["bright_frac"] = float((luma > 231).mean())

    return feats
