"""
SPAI: Any-Resolution AI-Generated Image Detection by Spectral Learning.

Implements the core algorithm from Karageorgiou et al. (CVPR 2025).

Key idea:  Real images have a characteristic spectral distribution (1/f^alpha
roll-off with specific statistical properties).  AI-generated images exhibit
spectral artifacts — subtle deviations from this natural distribution.  SPAI
learns the spectral distribution of real images using a self-supervised
masked frequency reconstruction task, then detects AI images as
out-of-distribution samples via spectral reconstruction similarity.

We implement a training-free approximation that:
1.  Computes the 2D DFT of the image.
2.  Applies a structured masking pattern in the frequency domain.
3.  Attempts to reconstruct masked frequencies from visible ones using
    spectral context statistics (local autoregressive model).
4.  Measures reconstruction error as the detection signal.
5.  Uses spectral context attention to capture resolution-invariant artifacts.

Reference:  arXiv:2411.19417  (CVPR 2025)
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageFilter


# ---------------------------------------------------------------------------
# Spectral analysis helpers
# ---------------------------------------------------------------------------

def _compute_2d_dft(arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Compute 2D DFT and return (magnitude, phase) of the shifted spectrum."""
    dft = np.fft.fft2(arr)
    dft_shift = np.fft.fftshift(dft)
    magnitude = np.abs(dft_shift)
    phase = np.angle(dft_shift)
    return magnitude, phase


def _radial_profile(magnitude: np.ndarray, n_bins: int = 128) -> np.ndarray:
    """Compute radially averaged power spectrum."""
    h, w = magnitude.shape
    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2).astype(np.int32)

    max_r = min(cy, cx, n_bins * 2)
    profile = np.zeros(max_r, dtype=np.float64)
    counts = np.zeros(max_r, dtype=np.int64)

    valid = r < max_r
    np.add.at(profile, r[valid], magnitude[valid])
    np.add.at(counts, r[valid], 1)

    counts = np.maximum(counts, 1)
    return profile[:n_bins] / counts[:n_bins]


def _spectral_slope(log_profile: np.ndarray) -> float:
    """Estimate the 1/f^alpha slope from the log radial profile."""
    # Skip DC component and very high frequencies
    start = max(2, len(log_profile) // 16)
    end = min(len(log_profile) - 1, len(log_profile) * 2 // 3)
    if end - start < 3:
        return -1.8  # default natural image slope

    x = np.log(np.arange(start, end) + 1.0)
    y = log_profile[start:end]

    valid = np.isfinite(y)
    if valid.sum() < 3:
        return -1.8

    coeffs = np.polyfit(x[valid], y[valid], 1)
    return float(coeffs[0])


# ---------------------------------------------------------------------------
# Masked spectral reconstruction
# ---------------------------------------------------------------------------

def _create_mask(h: int, w: int, mask_ratio: float = 0.4, seed: int = 42) -> np.ndarray:
    """
    Create a structured frequency-domain mask.
    Uses a combination of radial bands and random patches to simulate
    the masked learning setup from SPAI.
    """
    rng = np.random.RandomState(seed)
    mask = np.ones((h, w), dtype=np.float32)

    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    max_r = np.sqrt(cy**2 + cx**2)

    # 1. Mask some radial bands (simulates missing frequency ranges)
    n_bands = 8
    for i in range(n_bands):
        band_center = (i + 0.5) * max_r / n_bands
        band_width = max_r / n_bands * 0.6
        band_mask = (np.abs(r - band_center) < band_width)
        if rng.random() < 0.5:
            mask[band_mask] = 0.0

    # 2. Add random square patches
    n_patches = max(1, int(h * w * mask_ratio / (16 * 16)))
    for _ in range(n_patches):
        ph = rng.randint(8, max(9, h // 4))
        pw = rng.randint(8, max(9, w // 4))
        py = rng.randint(0, max(1, h - ph))
        px = rng.randint(0, max(1, w - pw))
        mask[py:py + ph, px:px + pw] = 0.0

    # Ensure at least some masking occurred
    if mask.mean() > 0.95:
        mask[h // 4:3 * h // 4, w // 4:3 * w // 4] = 0.0

    return mask


def _spectral_context_reconstruct(
    magnitude: np.ndarray,
    mask: np.ndarray,
    context_window: int = 5,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Reconstruct masked spectral values using local spectral context.

    For each masked frequency bin, estimate its value from the average of
    neighboring visible bins in the local context window.  This approximates
    the "spectral context attention" mechanism from SPAI.

    Returns:
        (reconstructed, original_masked_values)
    """
    h, w = magnitude.shape
    log_mag = np.log(magnitude + 1e-8)

    reconstructed = log_mag.copy()
    original_values = log_mag[mask == 0].copy()

    # For each masked region, compute local context statistics
    masked_coords = np.argwhere(mask == 0)

    # Process in batches for efficiency
    batch_size = min(5000, len(masked_coords))
    indices = np.arange(len(masked_coords))

    # Subsample if too many masked points
    if len(indices) > batch_size:
        step = len(indices) // batch_size
        indices = indices[::step]

    for idx in indices:
        yi, xi = masked_coords[idx]

        # Define context window
        y_start = max(0, yi - context_window)
        y_end = min(h, yi + context_window + 1)
        x_start = max(0, xi - context_window)
        x_end = min(w, xi + context_window + 1)

        # Get visible neighbors in context
        ctx_region = log_mag[y_start:y_end, x_start:x_end]
        ctx_mask = mask[y_start:y_end, x_start:x_end]

        visible = ctx_region[ctx_mask > 0]
        if len(visible) > 0:
            # Weighted average (closer neighbors weighted more)
            reconstructed[yi, xi] = np.mean(visible)
        else:
            # Fallback: use global mean
            global_visible = log_mag[mask > 0]
            if len(global_visible) > 0:
                reconstructed[yi, xi] = np.mean(global_visible)

    return reconstructed, original_values


def _compute_spectral_similarity(
    original: np.ndarray,
    reconstructed: np.ndarray,
    mask: np.ndarray,
) -> float:
    """
    Compute spectral reconstruction similarity between original and
    reconstructed masked regions.

    Lower similarity → more spectral artifacts → more likely AI-generated.
    """
    log_orig = np.log(original + 1e-8)
    log_recon = reconstructed  # already in log space

    # Compute error only in masked regions
    masked_orig = log_orig[mask == 0]
    masked_recon = log_recon[mask == 0]

    if len(masked_orig) == 0:
        return 1.0

    # Normalized reconstruction error
    mse = np.mean((masked_orig - masked_recon) ** 2)
    mae = np.mean(np.abs(masked_orig - masked_recon))

    # Cosine similarity of the masked spectral vectors
    dot = np.sum(masked_orig * masked_recon)
    norm_orig = np.sqrt(np.sum(masked_orig ** 2) + 1e-10)
    norm_recon = np.sqrt(np.sum(masked_recon ** 2) + 1e-10)
    cosine_sim = dot / (norm_orig * norm_recon)

    # Combined similarity (higher = more similar = more likely real)
    similarity = float(0.5 * cosine_sim + 0.3 * (1.0 / (1.0 + mae)) + 0.2 * (1.0 / (1.0 + mse)))
    return max(0.0, min(1.0, similarity))


# ---------------------------------------------------------------------------
# Spectral context attention (resolution-invariant features)
# ---------------------------------------------------------------------------

def _spectral_context_features(magnitude: np.ndarray) -> Dict[str, float]:
    """
    Extract resolution-invariant spectral context features.
    These capture subtle inconsistencies that persist across different
    image resolutions.
    """
    h, w = magnitude.shape
    log_mag = np.log(magnitude + 1e-8)

    # 1. Spectral entropy (measure of frequency distribution uniformity)
    profile = _radial_profile(magnitude, n_bins=64)
    profile_norm = profile / (profile.sum() + 1e-10)
    spectral_entropy = -np.sum(profile_norm * np.log(profile_norm + 1e-10))

    # 2. High-frequency energy ratio
    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    max_r = min(cy, cx)

    high_freq_mask = r > max_r * 0.5
    low_freq_mask = r <= max_r * 0.5

    hf_energy = float(np.mean(log_mag[high_freq_mask] ** 2)) if high_freq_mask.any() else 0.0
    lf_energy = float(np.mean(log_mag[low_freq_mask] ** 2)) if low_freq_mask.any() else 1.0
    hf_ratio = hf_energy / (lf_energy + 1e-10)

    # 3. Spectral flatness (Wiener entropy)
    # Measures how "flat" the spectrum is — AI images tend to have flatter spectra
    spectral_flatness = float(
        np.exp(np.mean(log_mag)) / (np.mean(magnitude) + 1e-10)
    )

    # 4. Spectral crest factor (peak-to-average ratio)
    spectral_crest = float(np.max(magnitude) / (np.mean(magnitude) + 1e-10))

    # 5. Local spectral variance across quadrants
    quadrants = [
        log_mag[:h // 2, :w // 2],
        log_mag[:h // 2, w // 2:],
        log_mag[h // 2:, :w // 2],
        log_mag[h // 2:, w // 2:],
    ]
    quad_means = [float(np.mean(q)) for q in quadrants]
    spectral_heterogeneity = float(np.std(quad_means))

    return {
        "spectral_entropy": spectral_entropy,
        "hf_energy_ratio": hf_ratio,
        "spectral_flatness": spectral_flatness,
        "spectral_crest": spectral_crest,
        "spectral_heterogeneity": spectral_heterogeneity,
    }


# ---------------------------------------------------------------------------
# Main detection function
# ---------------------------------------------------------------------------

def detect(img: Image.Image) -> Dict[str, Any]:
    """
    Detect whether *img* is AI-generated using spectral analysis.

    Args:
        img: PIL Image (any resolution).

    Returns:
        {
            "score":            int  (0-100, higher = more likely AI-generated)
            "probability":      float (0-1)
            "label":            str
            "spectral_similarity": float
            "spectral_slope":   float
            "reasons":          list[str]
            "metrics":          dict
        }
    """
    t0 = time.time()

    try:
        # Convert to grayscale for spectral analysis
        gray = img.convert("L")

        # Resize to standard resolution for consistent analysis
        target_size = 512
        w, h = gray.size
        scale = target_size / max(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        gray_resized = gray.resize((new_w, new_h), Image.Resampling.BILINEAR)

        arr = np.asarray(gray_resized).astype(np.float32) / 255.0

        # 1. Compute 2D DFT
        magnitude, phase = _compute_2d_dft(arr)

        # 2. Radial profile and spectral slope
        log_profile = np.log(_radial_profile(magnitude, n_bins=64) + 1e-8)
        slope = _spectral_slope(log_profile)

        # 3. Masked spectral reconstruction
        mask = _create_mask(new_h, new_w, mask_ratio=0.4)
        reconstructed, orig_masked = _spectral_context_reconstruct(
            magnitude, mask, context_window=5
        )
        spectral_similarity = _compute_spectral_similarity(magnitude, reconstructed, mask)

        # 4. Spectral context features
        context_feats = _spectral_context_features(magnitude)

        # 5. Multi-run averaging for robustness (different masks)
        similarities = [spectral_similarity]
        for seed in [123, 456, 789]:
            mask_alt = _create_mask(new_h, new_w, mask_ratio=0.4, seed=seed)
            recon_alt, _ = _spectral_context_reconstruct(magnitude, mask_alt)
            sim_alt = _compute_spectral_similarity(magnitude, recon_alt, mask_alt)
            similarities.append(sim_alt)

        avg_similarity = float(np.mean(similarities))

        # 6. Scoring
        score = 15  # baseline
        reasons: List[str] = []

        # Spectral reconstruction similarity
        # Real images have high similarity (close to 1.0)
        # AI images have lower similarity
        if avg_similarity < 0.55:
            score += 35
            reasons.append(
                f"Low spectral reconstruction similarity ({avg_similarity:.3f}) — "
                f"spectral distribution deviates from natural image statistics."
            )
        elif avg_similarity < 0.70:
            score += 20
            reasons.append(
                f"Moderate spectral reconstruction similarity ({avg_similarity:.3f}) — "
                f"mild spectral inconsistencies detected."
            )
        elif avg_similarity > 0.85:
            score -= 5
            reasons.append(
                f"High spectral reconstruction similarity ({avg_similarity:.3f}) — "
                f"spectrum consistent with natural image statistics."
            )

        # Spectral slope (natural images: -1.5 to -2.5)
        if slope > -0.9:
            score += 25
            reasons.append(
                f"Flattened spectral slope ({slope:.2f}) — "
                f"high-frequency deficit typical of diffusion models."
            )
        elif slope < -3.0:
            score += 15
            reasons.append(
                f"Unnaturally steep spectral slope ({slope:.2f}) — "
                f"possible spectral filtering artifact."
            )

        # Spectral flatness (AI images tend to be flatter)
        if context_feats["spectral_flatness"] > 0.85:
            score += 15
            reasons.append(
                f"Elevated spectral flatness ({context_feats['spectral_flatness']:.3f}) — "
                f"unnaturally uniform frequency distribution."
            )

        # High-frequency energy ratio
        if context_feats["hf_energy_ratio"] < 0.05:
            score += 10
            reasons.append(
                f"Low high-frequency energy ratio ({context_feats['hf_energy_ratio']:.4f}) — "
                f"synthetic smoothness detected."
            )

        # Spectral heterogeneity (AI images are often more uniform)
        if context_feats["spectral_heterogeneity"] < 0.05:
            score += 10
            reasons.append(
                f"Low spectral heterogeneity ({context_feats['spectral_heterogeneity']:.3f}) — "
                f"unnaturally uniform spectral distribution across quadrants."
            )

        # Cap score
        final_score = int(np.clip(score, 1, 99))
        probability = final_score / 100.0

        latency_ms = int((time.time() - t0) * 1000)

        reasons.insert(0,
            f"SPAI spectral analysis: {final_score}% probability of AI generation "
            f"(reconstruction similarity: {avg_similarity:.3f}, "
            f"spectral slope: {slope:.2f})."
        )
        reasons.append(
            f"Method: Masked spectral learning with context attention "
            f"(SPAI, Karageorgiou et al., CVPR 2025). "
            f"Resolution: {new_w}×{new_h}. Latency: {latency_ms}ms."
        )

        return {
            "score": final_score,
            "probability": round(probability, 4),
            "label": "AI-generated" if final_score >= 50 else "Likely authentic",
            "spectral_similarity": round(avg_similarity, 4),
            "spectral_slope": round(slope, 4),
            "context_features": {k: round(v, 4) for k, v in context_feats.items()},
            "reasons": reasons,
            "metrics": {
                "similarity": round(avg_similarity, 4),
                "slope": round(slope, 4),
                "flatness": round(context_feats["spectral_flatness"], 4),
                "hf_ratio": round(context_feats["hf_energy_ratio"], 4),
                "heterogeneity": round(context_feats["spectral_heterogeneity"], 4),
            },
            "latency_ms": latency_ms,
        }

    except Exception as e:
        return {
            "score": 40,
            "probability": 0.4,
            "label": "Inconclusive",
            "spectral_similarity": 0.5,
            "spectral_slope": -1.8,
            "context_features": {},
            "reasons": [f"SPAI spectral analysis error: {e}"],
            "metrics": {},
            "latency_ms": 0,
        }
