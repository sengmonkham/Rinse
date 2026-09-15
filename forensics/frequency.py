"""
Layer 3: Frequency-Domain Forensic Analysis.

Extracts spectral signatures from the 2D Discrete Fourier Transform (DFT) and
Haar Discrete Wavelet Transform (DWT) to identify GAN upsampling grid spikes,
diffusion high-frequency deficits, and deviations from natural 1/f sensor noise.
"""

from typing import Dict, Any, List, Tuple
import numpy as np
from PIL import Image


def _radial_average_spectrum(log_mag: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Calculate the radially averaged power spectral density."""
    h, w = log_mag.shape
    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2).astype(np.int32)
    max_r = min(cy, cx)
    
    radial_profile = np.zeros(max_r, dtype=np.float32)
    counts = np.zeros(max_r, dtype=np.int32)
    
    valid_mask = r < max_r
    np.add.at(radial_profile, r[valid_mask], log_mag[valid_mask])
    np.add.at(counts, r[valid_mask], 1)
    
    counts = np.maximum(counts, 1)
    return np.arange(max_r), radial_profile / counts


def _haar_dwt_2d(arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Single-level 2D Haar Discrete Wavelet Transform."""
    # Rows
    h = (arr[:, 0::2] + arr[:, 1::2]) / np.sqrt(2.0)
    l = (arr[:, 0::2] - arr[:, 1::2]) / np.sqrt(2.0)
    
    # Columns
    ll = (h[0::2, :] + h[1::2, :]) / np.sqrt(2.0)
    lh = (h[0::2, :] - h[1::2, :]) / np.sqrt(2.0)
    hl = (l[0::2, :] + l[1::2, :]) / np.sqrt(2.0)
    hh = (l[0::2, :] - l[1::2, :]) / np.sqrt(2.0)
    return ll, lh, hl, hh


def analyze_frequency_domain(img: Image.Image, include_grid_peaks: bool = True) -> Dict[str, Any]:
    """
    Perform 2D DFT and DWT frequency-domain forensic evaluation.

    Args:
        img: PIL image to analyze.
        include_grid_peaks: Include the GAN-checkerboard grid-peak rule. This
            rule CANNOT be used on video frames: the 512x512 bilinear upscale
            of an H.264-encoded frame rings periodically in the DFT, producing
            grid-peak energies of ~10 on essentially every video (real or AI),
            which flagged all video as synthetic. Callers analyzing decoded
            video frames must pass include_grid_peaks=False; still-image
            analysis keeps the rule (default).

    Returns:
        {
            "score": int, # 0 to 100
            "spectral_roll_off": float, # slope of radial power roll-off
            "grid_peak_energy": float,  # periodicity indicator (GAN checkerboard)
            "wavelet_high_freq_ratio": float, # DWT high/low energy
            "reasons": list[str],
            "metrics": dict
        }
    """
    try:
        # Standardize size for spectral calibration (512x512)
        gray = img.convert("L")
        size = 512
        gray_norm = gray.resize((size, size), Image.Resampling.BILINEAR)
        arr = np.asarray(gray_norm).astype(np.float32) / 255.0

        # 1. 2D Discrete Fourier Transform
        dft = np.fft.fft2(arr)
        dft_shift = np.fft.fftshift(dft)
        mag = np.abs(dft_shift)
        eps = 1e-8
        log_mag = np.log(mag + eps)

        # 2. Radial Spectral Roll-Off Slope (Natural images follow ~ 1 / f^alpha where alpha in [1.5, 2.5])
        radii, profile = _radial_average_spectrum(log_mag)
        # Avoid DC center and extreme corners
        mid_band = slice(size // 16, size // 3)
        r_band = np.log(radii[mid_band] + 1e-5)
        p_band = profile[mid_band]
        
        if len(r_band) > 2:
            slope, intercept = np.polyfit(r_band, p_band, 1)
        else:
            slope = -1.8

        # 3. Azimuthal Autocorrelation / Grid Peak Energy (detects GAN periodic upsampling checkerboard)
        # High-pass filter log magnitude to isolate peak residuals
        cy, cx = size // 2, size // 2
        y, x = np.ogrid[:size, :size]
        dist_from_center = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        high_pass_mask = (dist_from_center > size * 0.12) & (dist_from_center < size * 0.48)

        # Z-scores must be computed over ring pixels ONLY. Multiplying by the
        # boolean mask first (the old behavior) injected thousands of zeroed
        # pixels, so the mean/std were pulled toward the mask floor and the
        # zeroed pixels came back as extreme "peaks" — flagging nearly every
        # photo (real or AI) with the GAN-grid signature.
        ring_vals = log_mag[high_pass_mask]
        mean_hp = np.mean(ring_vals)
        std_hp = np.std(ring_vals) + eps
        peaks = (ring_vals - mean_hp) / std_hp
        grid_peak_energy = float(np.mean(peaks[peaks > 3.0] ** 2) if np.any(peaks > 3.0) else 0.0)

        # 4. 2D Haar Wavelet Subband Energy Ratios
        ll, lh, hl, hh = _haar_dwt_2d(arr)
        e_ll = float(np.sum(ll ** 2))
        e_lh = float(np.sum(lh ** 2))
        e_hl = float(np.sum(hl ** 2))
        e_hh = float(np.sum(hh ** 2))
        high_freq_energy = (e_lh + e_hl + e_hh)
        wavelet_ratio = float(high_freq_energy / max(e_ll, eps))

        # 5. Composite Analytic Scoring
        score = 15
        reasons: List[str] = []

        # Check periodic grid spikes (GAN signature) - still images only, see
        # the include_grid_peaks docstring above.
        if include_grid_peaks and grid_peak_energy > 4.5:
            score += 45
            reasons.append(f"Periodic spectral grid peaks detected (peak energy {grid_peak_energy:.2f}) — characteristic of deconvolution / GAN upsampling.")
        elif include_grid_peaks and grid_peak_energy > 2.0:
            score += 20
            reasons.append(f"Mild frequency-domain harmonic peaks (peak energy {grid_peak_energy:.2f}).")

        # Check spectral roll-off deviation (natural photos are typically -1.4 to -2.3)
        if slope > -0.9:
            score += 30
            reasons.append(f"High-frequency energy deficit / flattened spectral slope ({slope:.2f}) — typical of diffusion model spatial interpolation.")
        elif slope < -2.9:
            score += 25
            reasons.append(f"Unnaturally steep spectral attenuation (slope {slope:.2f}).")

        # Check wavelet high-frequency energy ratio
        if wavelet_ratio < 0.008:
            score += 20
            reasons.append(f"Wavelet high-frequency energy deficit (ratio {wavelet_ratio:.4f}) — synthetic smoothness.")
        elif wavelet_ratio > 0.09:
            score += 15
            reasons.append(f"Elevated high-frequency subband noise (ratio {wavelet_ratio:.4f}).")

        final_score = int(np.clip(score, 5, 96))
        if not reasons:
            reasons.append("Frequency-domain power distribution matches natural optical camera sensor roll-off.")

        return {
            "score": final_score,
            "spectral_roll_off": float(slope),
            "grid_peak_energy": float(grid_peak_energy),
            "wavelet_high_freq_ratio": float(wavelet_ratio),
            "reasons": reasons,
            "metrics": {
                "slope": round(float(slope), 3),
                "grid_peaks": round(float(grid_peak_energy), 3),
                "wavelet_ratio": round(float(wavelet_ratio), 4)
            }
        }
    except Exception as e:
        return {
            "score": 40,
            "spectral_roll_off": -1.8,
            "grid_peak_energy": 0.0,
            "wavelet_high_freq_ratio": 0.02,
            "reasons": [f"Frequency analysis encountered error: {e}"],
            "metrics": {}
        }
