"""
PwTF-DVD: Pixel-wise Temporal Frequency-based Deepfake Video Detection.

Implements the core algorithm from Kim, Choi, Jeong, Noh, Yoo, Baek & Choi,
"Beyond Spatial Frequency: Pixel-wise Temporal Frequency-based Deepfake Video
Detection" (ICCV 2025, arXiv:2507.02398).

Paper idea:  Spatial-frequency detectors stack 2D frame-wise spectra, which
only sees how each *frame* deviates from natural images.  Deepfake videos are
instead betrayed by how individual *pixels* behave over time:  each frame of a
generated video is synthesized semi-independently, so texture does not persist
physically across frames.  The paper extracts, for every pixel, the 1D temporal
frequency spectrum of its intensity trace and detects the temporal artifacts
that spatial analysis misses:

    1. Per frame, keep the high-frequency residual  R_t = frame_t - median5(frame_t)
       (detail / texture layer left after removing the smooth base).
    2. Stack the residuals over the clip and take a 1D FFT along the *time*
       axis, per pixel:  S(x, y) = |FFT_t( R_t(x, y) )|  (positive half).
    3. A learned encoder + Attention Proposal Module locate regions whose
       pixel-wise temporal spectra are incoherent (unnatural micro-flicker),
       and a joint transformer fuses global + part frequency signals.

We ship a training-free numpy approximation in the style of the repo's other
research layers (SPAI, frequency forensics):  the pixel-wise temporal frequency
map is computed exactly as above, then scored with hand-built statistics that
encode the paper's core evidence - real footage has spatially coherent,
low-frequency-dominated temporal spectra (physical persistence), while
generated footage leaks energy into high temporal bins and flickers
incoherently pixel-to-pixel, concentrated in localized regions.

Reference pipeline (official repo: rama0126/PwTF-DVD):
    - clip of T aligned frames  ->  residual stack R (T, H, W)
    - spectrum map             ->  ft = |fft(R, axis=time)[:T/2]| / T
    - RGB clip + ft map        ->  I3D8x8 encoder + APN ResNet (attention
                                   proposals) + spatial/temporal transformers
                                   -> sigmoid = fake probability per clip.

CPU-only, numpy + PIL, no weights, no network.  Latency ~tens of ms for
12-30 frames at 128x128.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageFilter

MIN_FRAMES = 6        # fewer frames => too few temporal bins for a reliable FFT

# Working resolution (square) for the temporal-frequency map. Configurable for
# experiments only; the DEFAULT STAYS 128 because the coherence-floor statistic
# this scorer keys on is resolution-calibrated. Measured 2026-10-12 on the local
# test clips: raising to 256 did NOT help and actively hurt - a real clip whose
# p05 floor held at 0.51 (128) and 0.48 (192) COLLAPSED to 0.00 at 256, flipping
# a real video into a full coherence-collapse false positive. Higher resolution
# pulls in per-pixel sensor/compression noise that decorrelates the 5th-
# percentile coherence. Do not raise the default without a real-reel corpus and
# a noise/grain compensation step (see docs/detector-review-and-video-plan.md).
WORK_RES = int(os.environ.get("TEMPORAL_RES", "128"))
MEDIAN_K = 5          # median-filter kernel for the residual (paper: medianBlur 5)


# ---------------------------------------------------------------------------
# Temporal-frequency map (exact paper representation)
# ---------------------------------------------------------------------------

def _gray_stack(frames: List[Image.Image], res: int = WORK_RES) -> np.ndarray:
    """Downscale the clip to square grayscale float32 (T, res, res)."""
    stack = []
    for f in frames:
        g = f.convert("L").resize((res, res), Image.Resampling.BILINEAR)
        stack.append(np.asarray(g, dtype=np.float32))
    return np.stack(stack, axis=0)


def _estimate_global_shifts(grays: np.ndarray) -> List[tuple]:
    """
    Estimate the integer global translation between consecutive frames with
    phase correlation (cross-power spectrum peak).  Used only to *compensate*
    real camera motion before the temporal FFT - a training-free stand-in for
    the motion invariance the paper's I3D encoder learns.  Frames are
    Hann-windowed and mildly blurred first so texture noise does not dominate
    the correlation peak.

    Returns [(dx, dy), ...] for pairs (0,1) .. (T-2,T-1), with the sign such
    that rolling frame t by -dx/-dy brings it into registration with frame t-1.
    """
    T, H, W = grays.shape
    win = np.hanning(H)[:, None] * np.hanning(W)[None, :]
    win = win.astype(np.float32)

    def prep(g: np.ndarray) -> np.ndarray:
        # mild 3x3 box blur so high-frequency texture does not drown the shift peak
        g = np.pad(g, 1, mode="edge")
        blurred = (
            g[:-2, :-2] + g[:-2, 1:-1] + g[:-2, 2:] +
            g[1:-1, :-2] + g[1:-1, 1:-1] + g[1:-1, 2:] +
            g[2:, :-2] + g[2:, 1:-1] + g[2:, 2:]
        ) / 9.0
        return blurred * win

    shifts = []
    for t in range(1, T):
        a, b = prep(grays[t - 1]), prep(grays[t])
        A = np.fft.fft2(a)
        B = np.fft.fft2(b)
        cross = A * np.conj(B)
        cross /= (np.abs(cross) + 1e-6)
        r = np.fft.ifft2(cross).real
        idx = np.unravel_index(int(np.argmax(r)), r.shape)
        dy = idx[0] if idx[0] <= H // 2 else idx[0] - H
        dx = idx[1] if idx[1] <= W // 2 else idx[1] - W
        shifts.append((int(dx), int(dy)))
    return shifts


def _motion_compensate(grays: np.ndarray) -> "tuple[np.ndarray, Optional[Dict[str, float]]]":
    """
    Align frames to frame 0 when the clip shows coherent global motion (a
    steady camera pan/tilt).  Returns (aligned_stack, motion_info) where
    motion_info is None when there is no significant coherent motion.

    Coherence gate: the per-pair shifts must be tightly clustered (std <= 1px)
    and large enough to matter (median >= 1px on either axis).  If the clip
    cuts, shakes erratically, or each frame is independently regenerated, the
    gate fails and the original stack is returned unchanged - conservative for
    clips we cannot model.
    """
    T, H, W = grays.shape
    shifts = _estimate_global_shifts(grays)
    dxs = np.array([s[0] for s in shifts], dtype=np.float64)
    dys = np.array([s[1] for s in shifts], dtype=np.float64)
    med_dx, med_dy = float(np.median(dxs)), float(np.median(dys))
    std_dx, std_dy = float(np.std(dxs)), float(np.std(dys))

    if max(abs(med_dx), abs(med_dy)) < 1.0:
        return grays, None                      # no significant global motion
    if std_dx > 1.0 or std_dy > 1.0:
        return grays, None                      # irregular / incoherent motion

    aligned = np.empty_like(grays)
    for t in range(T):
        # phase correlation reports the shift that turns frame t-1 into frame t,
        # so frame t is brought back to frame 0 by rolling by the *same* sign.
        cx = int(round(med_dx * t))
        cy = int(round(med_dy * t))
        g = np.roll(np.roll(grays[t], cy, axis=0), cx, axis=1)
        aligned[t] = g

    info = {
        "motion_compensated": True,
        "dx_per_frame": round(med_dx, 3),
        "dy_per_frame": round(med_dy, 3),
    }
    return aligned, info


def _residual_stack(grays: np.ndarray) -> np.ndarray:
    """
    Build the per-frame high-frequency residual stack used by the paper:
        R_t = aligned_grayscale(frame_t) - median5(aligned_grayscale(frame_t))
    Returns float32 array of shape (T, res, res).
    """
    stack = []
    for g in grays:
        base = np.asarray(
            Image.fromarray(g.astype(np.uint8)).filter(ImageFilter.MedianFilter(size=MEDIAN_K)),
            dtype=np.float32,
        )
        stack.append(g - base)
    return np.stack(stack, axis=0)


def _temporal_spectrum_map(stack: np.ndarray) -> np.ndarray:
    """
    Per-pixel 1D FFT along the time axis (paper step 2).

    Args:
        stack: (T, H, W) residual stack.

    Returns:
        (K, H, W) non-negative magnitude spectrum over the positive temporal
        frequency bins K = T // 2, scaled by 1 / T like the official code.
    """
    T = stack.shape[0]
    spec = np.fft.fft(stack.astype(np.float64), axis=0)
    mag = np.abs(spec[: T // 2]) / T  # DC at bin 0 .. Nyquist-ish at bin T/2 - 1
    return mag


# ---------------------------------------------------------------------------
# Hand-built scoring statistics
# ---------------------------------------------------------------------------

def _spectrum_statistics(spec: np.ndarray) -> Dict[str, float]:
    """
    Derive scalar statistics from the per-pixel temporal frequency map that
    separate physically-persistent footage from generated micro-flicker.

    spec: (K, H, W) magnitude spectrum, K = number of positive bins.
    """
    K, H, W = spec.shape
    energy = spec.sum(axis=0)                             # energy per pixel
    total = energy + 1e-9
    p = spec / total[None, :, :]                          # per-pixel freq distribution

    bins = np.arange(K, dtype=np.float64)
    norm_bins = bins / max(K - 1, 1)

    # --- per-pixel frequency centroid (0 = pure DC, 1 = Nyquist) ---
    centroid = (norm_bins[:, None, None] * p).sum(axis=0)  # (H, W)

    # --- high temporal-band share (upper half of the spectrum) ---
    cut = max(1, K // 2)
    hf_share = p[cut:].sum(axis=0)                         # (H, W) in [0, 1]

    # --- spectral entropy of each pixel's temporal distribution ---
    log_p = np.log(p + 1e-12)
    entropy = -(p * log_p).sum(axis=0) / np.log(K)         # (H, W) in [0, 1]

    # --- coherence to the global (spatial-mean) spectrum ---
    # Real footage: neighbouring pixels share one coherent motion/texture
    # model, so per-pixel spectra resemble the scene-mean spectrum.  Generated
    # flicker decorrelates pixels from that mean.
    #
    # STATIC-PIXEL GUARD (measured 2026-11-10). A pixel with no temporal
    # variance has an all-zero spectrum, so its normalised distribution is 0/0
    # and the clipped cosine similarity is exactly 0 - the same value as a
    # maximally incoherent, regenerated pixel. Counting those pixels in the
    # percentile makes the floor collapse to 0.00 whenever >5% of the frame is
    # static (letterbox bars, a still background, painted-over regions).
    # Measured: a real dance reel with 6.1% static pixels read p05 0.00 in 7 of
    # 12 windows and this layer scored it 62 "synthetic"; restricting the
    # percentile to pixels that carry temporal energy read 0.59-0.79 on the
    # same windows. A static pixel has no temporal model to be incoherent
    # with, so it is excluded from the floor rather than treated as evidence.
    g = spec.mean(axis=(1, 2))
    g_norm = g / (np.linalg.norm(g) + 1e-9)                # (K,)
    pix_norms = np.linalg.norm(p.reshape(K, -1), axis=0) + 1e-9
    cos_sim = (g_norm[:, None] * p.reshape(K, -1)).sum(axis=0) / pix_norms
    cos_sim = np.clip(cos_sim.reshape(H, W), 0.0, 1.0)
    lacks_energy = energy <= 1e-6
    if np.count_nonzero(~lacks_energy) >= 100:
        coh_valid = cos_sim[~lacks_energy]
    else:
        coh_valid = cos_sim.ravel()

    # --- anomaly map & spatial concentration (Attention-Proposal analog) ---
    # A pixel whose spectrum decorrelates from the scene-mean carries a
    # temporal anomaly.  Generated artifacts are localized (a regenerated
    # mouth/eye/hair patch), so the anomaly mass concentrates in a few
    # regions; camera noise is diffuse.
    anomaly = np.clip(1.0 - cos_sim, 0.0, 1.0)             # (H, W)
    flat = anomaly.ravel()
    sorted_a = np.sort(flat)
    top10_mass = sorted_a[int(len(sorted_a) * 0.9):].sum()
    anomaly_mass = float(flat.sum())
    concentration = float(top10_mass / (anomaly_mass + 1e-9))  # in [0, 1]

    # --- spatial incoherence of the high-band share ---
    # Generated flicker is per-pixel: adjacent pixels flicker independently,
    # so the local variance of hf_share is high.  Real motion changes slowly
    # across space.
    hf_pad = np.pad(hf_share, 1, mode="edge")
    local_mean = (
        hf_pad[:-2, 1:-1] + hf_pad[2:, 1:-1] +
        hf_pad[1:-1, :-2] + hf_pad[1:-1, 2:]
    ) / 4.0
    local_dev = np.abs(hf_share - local_mean)              # per-pixel deviation
    spatial_std_hf = float(local_dev.mean())

    # --- temporal residual whiteness (spectral flatness of the mean spectrum) ---
    # AI regeneration leaves temporally WHITE residuals (energy spread evenly
    # across bins), while real motion leaves colored, structured spectra
    # concentrated on motion frequencies. Wiener-like flatness: 1 = white.
    g = spec.mean(axis=(1, 2)) + 1e-12
    spectral_flatness = float(np.exp(np.mean(np.log(g))) / np.mean(g))

    # --- temporal-variance hotspots (localized regenerated regions) ---
    # By Parseval, the per-pixel temporal variance is 2*T*sum(|spec[k]|^2)
    # over the positive bins (DC excluded).  A regenerated region has extreme
    # per-pixel variance - tens of times the scene's median - and those pixels
    # form one compact cluster instead of scattering like camera noise.
    T = K * 2
    var_map = 2.0 * T * (spec[1:] ** 2).sum(axis=0)
    med_var = float(np.median(var_map))
    if med_var > 0.0:
        hot = var_map > 3.0 * med_var
        hot_frac = float(hot.mean())
        hp = np.pad(hot.astype(np.uint8), 1, mode="constant")
        nbr = (
            hp[:-2, 1:-1] + hp[2:, 1:-1] + hp[1:-1, :-2] + hp[1:-1, 2:]
        )
        if hot_frac > 0:
            hot_cluster = float((nbr[hot] > 0).mean())
        else:
            hot_cluster = 0.0
    else:
        hot_frac = 0.0
        hot_cluster = 0.0

    return {
        "spectral_flatness": spectral_flatness,
        "centroid_mean": float(centroid.mean()),
        "centroid_max": float(centroid.max()),
        "hf_share_mean": float(hf_share.mean()),
        "hf_share_p95": float(np.percentile(hf_share, 95)),
        "entropy_mean": float(entropy.mean()),
        "coherence_mean": float(coh_valid.mean()),
        "coherence_p05": float(np.percentile(coh_valid, 5)),
        "static_pixel_fraction": float(lacks_energy.mean()),
        "anomaly_mean": float(anomaly.mean()),
        "anomaly_mass": anomaly_mass,
        "anomaly_concentration": concentration,
        "hf_spatial_std": spatial_std_hf,
        "temporal_var_p95": float(np.percentile(var_map, 95)),
        "hotspot_fraction": hot_frac,
        "hotspot_cluster": hot_cluster,
    }


# ---------------------------------------------------------------------------
# Score mapping
# ---------------------------------------------------------------------------

def _score_from_stats(
    s: Dict[str, float],
    residual_ac1: Optional[float] = None,
) -> "tuple[int, List[str]]":
    """
    Map the spectrum statistics to a 0-100 deepfake-likelihood score.

    Recalibrated on real social-media footage (Instagram reels, 30fps, 720p,
    H.264) vs a generated clip. Key finding: the previously used statistics
    ANTI-CORRELATE on native-rate contiguous windows of real footage - real
    clips measured HIGHER entropy (0.90-0.96 vs 0.80), higher hf-share (0.38-
    0.44 vs 0.24-0.30), higher coherence_mean, and higher hotspot fractions
    than the generated clip. Entropy / hf-share / hotspot / anomaly / spatial-
    std rules therefore flag ordinary real motion (action scenes, camera pans,
    animation) as AI while letting slow generated footage through.

    The signals that survived calibration:
      1. Coherence FLOOR (p05): a regenerated region shares NO temporal model
         with the scene, collapsing the 5th-percentile per-pixel coherence
         toward 0. Real footage keeps a floor (measured 0.31-0.76 on real
         reels across all shots) even when heavily compressed; the generated
         clip collapsed to 0.00. This is the paper's core localized-
         regeneration case and the strongest discriminator.
      2. Residual whiteness (spectral flatness of the scene-mean temporal
         spectrum + lag-1 autocorrelation of the residual stack): full-frame
         regeneration produces temporally WHITE residuals (flat spectrum,
         ac1 ~ 0), while real motion leaves colored, structured residuals
         concentrated on motion frequencies.
      3. Hotspots only escalate in combination with a collapsed floor -
         alone they fire on ordinary fast motion.
    """
    score = 12.0  # baseline (authentic-leaning)
    reasons: List[str] = []

    # 1. Coherence floor (the paper's localized-regeneration evidence).
    p05 = s["coherence_p05"]
    if p05 < 0.20:
        score += 40
        reasons.append(
            f"The coherence floor is missing: the least-coherent 5% of pixels share "
            f"almost no temporal model with the scene (p05 coherence {p05:.2f}) - "
            f"a frame-regenerated region (PwTF-DVD, ICCV 2025)."
        )
    elif p05 < 0.35:
        score += 22
        reasons.append(
            f"Weak coherence floor (p05 {p05:.2f}): a minority of pixels are "
            f"weakly coupled to the scene's temporal model."
        )
    elif p05 < 0.50:
        score += 10

    # 2. Residual whiteness: flat scene-mean spectrum + low lag-1 residual
    #    autocorrelation = pixel traces resemble independent noise. Real
    #    motion leaves structured (colored) residuals, so both must agree.
    flat = s.get("spectral_flatness", 0.0)
    ac1 = residual_ac1
    if flat >= 0.85 and ac1 is not None and ac1 <= 0.20:
        score += 15
        reasons.append(
            f"Temporal residuals are spectrally white (flatness {flat:.2f}, lag-1 "
            f"autocorrelation {ac1:.2f}) - pixel traces behave like independent "
            f"per-frame noise rather than physical motion."
        )

    # Structured residuals are evidence FOR real footage: strong positive
    # autocorrelation means the residual content persists across frames.
    #
    # CONTRADICTION GUARD (measured 2026-09-27, ig-ai-reel-01): the penalty
    # must NOT apply when the coherence floor is collapsed. A collapsed floor
    # (p05 -> 0) is the localized-REGENERATION signature - some pixels share
    # no temporal model with the scene - and generated detail can absolutely
    # persist frame-to-frame (stylized/animated generation, temporally stable
    # diffusion decoders). Penalizing persistence there suppresses the very
    # evidence that found the regeneration: measured p05 0.00 + ac1 0.855
    # scored 54 instead of 62, dropping the reel below the voter's >= 60
    # escalation gate and flipping the fused verdict to AUTHENTIC_HUMAN.
    # Both signals cannot simultaneously mean "real".
    if ac1 is not None and ac1 > 0.70 and p05 >= 0.20:
        score -= 8
        reasons.append(
            f"Residual texture persists across frames (lag-1 autocorrelation "
            f"{ac1:.2f}) - structured, physically persistent detail."
        )

    # 3. Temporal-variance hotspots escalate ONLY with a collapsed floor:
    #    fast real motion also produces hotspots, but real hotspots stay
    #    coupled to the scene's temporal model.
    hf_ = s["hotspot_fraction"]
    hc = s["hotspot_cluster"]
    if p05 < 0.30 and hf_ > 0.10 and hc > 0.7:
        score += 10
        reasons.append(
            f"A compact cluster of {hf_ * 100:.1f}% of pixels combines extreme "
            f"temporal variance with a collapsed coherence floor (cluster {hc:.2f}) "
            f"- a regenerated region rather than camera noise."
        )

    final = int(np.clip(score, 5, 98))
    return final, reasons


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_pixel_temporal_frequency(
    frames: List[Image.Image],
    res: int = WORK_RES,
    min_frames: int = MIN_FRAMES,
) -> Dict[str, Any]:
    """
    PwTF-DVD (ICCV 2025) pixel-wise temporal frequency analysis on a frame clip.

    Args:
        frames: CONTIGUOUS PIL frames at (near) native frame rate (>= min_frames).
            Uniformly-spaced samples stretched across a clip alias real motion
            into the high temporal bins and span scene cuts, which fabricates
            the very artifacts this detector looks for. See the module
            docstring of forensics.temporal for the measured calibration.
        res:    square working resolution for the frequency map.
        min_frames: minimum clip length for a meaningful temporal FFT.

    Returns:
        {
            "score": int | None,     # None when the clip is too short
            "probability": float | None,
            "label": str,
            "reasons": list[str],
            "metrics": dict,         # spectrum statistics (see _spectrum_statistics)
            "spectrum_bins": int,
            "frames_analyzed": int,
            "active": bool,
        }
    """
    t0 = time.time()
    if not frames or len(frames) < min_frames:
        return {
            "score": None,
            "probability": None,
            "label": "Inactive",
            "reasons": [
                f"Insufficient frames for pixel-wise temporal frequency analysis "
                f"({len(frames) if frames else 0} provided, minimum {min_frames})."
            ],
            "metrics": {},
            "spectrum_bins": 0,
            "frames_analyzed": len(frames) if frames else 0,
            "active": False,
        }

    try:
        grays = _gray_stack(frames, res=res)                 # (T, H, W) float32
        # Motion compensation is only valid on a contiguous sequence (the
        # phase-correlation shifts must be a coherent per-frame drift).
        aligned, _motion = _motion_compensate(grays)         # cancel coherent camera motion
        stack = _residual_stack(aligned)
        spec = _temporal_spectrum_map(stack)                 # (K, H, W)
        stats = _spectrum_statistics(spec)

        # Lag-1 autocorrelation of the residual stack (whiteness evidence).
        r = stack - stack.mean(axis=0, keepdims=True)
        denom = float(np.mean(r * r)) + 1e-12
        residual_ac1 = float(np.mean(r[:-1] * r[1:])) / denom

        score, reasons = _score_from_stats(stats, residual_ac1=residual_ac1)

        if not reasons:
            reasons.append(
                "Pixel-wise temporal spectra are low-frequency-dominated, spatially "
                "coherent, and consistent with physical temporal persistence."
            )

        latency_ms = int((time.time() - t0) * 1000)
        reasons.insert(
            0,
            f"PwTF-DVD temporal-frequency scan ({len(frames)} frames, "
            f"{spec.shape[0]} temporal bins @ {res}x{res}): {score}% "
            f"synthetic confidence. Method: 1D FFT per pixel along time of the "
            f"median-filter residual (Kim et al., ICCV 2025). Latency: {latency_ms}ms.",
        )

        metrics = {k: round(v, 4) for k, v in stats.items()}
        # Lag-1 residual autocorrelation is a scored signal (whiteness rule)
        # but was not surfaced; expose it so audits/regressions can review the
        # exact evidence the score was built from.
        metrics["residual_ac1"] = round(residual_ac1, 4)

        return {
            "score": score,
            "probability": round(score / 100.0, 4),
            "label": "AI-generated" if score >= 50 else "Likely authentic",
            "reasons": reasons,
            "metrics": metrics,
            "spectrum_bins": int(spec.shape[0]),
            "frames_analyzed": len(frames),
            "active": True,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "score": None,
            "probability": None,
            "label": "Inactive",
            "reasons": [f"PwTF-DVD temporal frequency analysis error: {e}"],
            "metrics": {},
            "spectrum_bins": 0,
            "frames_analyzed": len(frames),
            "active": False,
        }
