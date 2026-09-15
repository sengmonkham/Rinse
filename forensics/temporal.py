"""
Layer 5: Temporal Coherence Analysis (Video only).

Analyzes frame sequences for AI temporal inconsistency signatures:
- Inter-frame difference residual variance (motion jitter)
- Pixel-wise 1D temporal FFT (micro-texture flicker on static surfaces)

IMPORTANT SAMPLING REQUIREMENT
------------------------------
The flicker/jitter statistics are only physically meaningful when the frames
form a CONTIGUOUS, regularly-spaced sequence at (near) native frame rate.
Uniformly-spaced samples stretched across a whole clip alias real motion into
the high temporal bins and span scene cuts, which measured *higher* on real
social-media footage than on generated clips (calibrated on Instagram reels:
uniform sampling gave the human clip entropy 0.96 / hf-share 0.48 vs the AI
clip's 0.94 / 0.46 - i.e. the signal was anti-correlated). Callers must pass
the real per-frame interval; without one the layer reports inactive instead of
voting on garbage.
"""

from typing import Dict, Any, List, Optional
import numpy as np
from PIL import Image

try:
    from forensics.frequency import analyze_frequency_domain
except ImportError:  # pragma: no cover - direct module import layout
    from frequency import analyze_frequency_domain


def analyze_video_temporal_coherence(
    frames: List[Image.Image],
    compute_frame_scores: bool = True,
    frame_interval_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Perform temporal coherence and flicker analysis over a contiguous frame sequence.

    Args:
        frames: Contiguous PIL frames captured at (near) native frame rate
            (e.g. a 32-frame window from one camera shot).
        compute_frame_scores: Also run per-frame frequency forensics for the
            score-trajectory chart (adds ~24 extra FFT passes; disable when
            only the temporal score is needed).
        frame_interval_seconds: Real per-frame interval of the sequence. The
            layer refuses to vote when this is missing/invalid, because
            non-contiguous sampling fabricates temporal artifacts.

    Returns:
        {
            "score": int | None,   # None when the layer is inactive
            "active": bool,
            "temporal_flicker_energy": float,
            "motion_residual_variance": float,
            "frame_scores": list[int],
            "reasons": list[str]
        }
    """
    if not frames or len(frames) < 3:
        return {
            "score": None,
            "active": False,
            "temporal_flicker_energy": 0.0,
            "motion_residual_variance": 0.0,
            "frame_scores": [],
            "reasons": ["Insufficient frames for temporal coherence analysis (minimum 3 required)."]
        }

    if frame_interval_seconds is None or frame_interval_seconds <= 0 or frame_interval_seconds > 0.5:
        return {
            "score": None,
            "active": False,
            "temporal_flicker_energy": 0.0,
            "motion_residual_variance": 0.0,
            "frame_scores": [],
            "reasons": [
                "Temporal coherence inactive: frames were not a contiguous, regularly-spaced "
                "native-frame-rate sequence (no valid frame interval provided), so flicker/jitter "
                "statistics would be sampling artifacts rather than evidence."
            ]
        }

    try:
        # Resize frames for efficient temporal matrix processing (e.g. 128x128)
        thumb_size = (128, 128)
        gray_stack = []

        for f in frames:
            g = f.convert("L").resize(thumb_size, Image.Resampling.BILINEAR)
            gray_stack.append(np.asarray(g).astype(np.float32) / 255.0)

        # 3D Tensor: (Time, Height, Width)
        video_tensor = np.stack(gray_stack, axis=0)

        # Inter-frame difference residuals & motion jitter variance
        diffs = np.diff(video_tensor, axis=0)
        diff_var = float(np.var(diffs))
        diff_mean = float(np.mean(np.abs(diffs)))
        jitter_index = float(diff_var / (diff_mean + 1e-6))

        # Pixel-wise temporal flicker ratio (high-band vs low-band energy)
        fft_temporal = np.fft.rfft(video_tensor, axis=0)
        mag_temporal = np.abs(fft_temporal)
        if mag_temporal.shape[0] > 2:
            high_freq_temporal = np.mean(mag_temporal[2:, ...])
            low_freq_temporal = np.mean(mag_temporal[:2, ...]) + 1e-6
            flicker_ratio = float(high_freq_temporal / low_freq_temporal)
        else:
            flicker_ratio = 0.05

        # Score: the jitter gate is intentionally conservative (top-decile
        # only). Calibrated on Instagram reels: a generated clip measured
        # jitter 0.36-0.38 while real clips measured 0.23-0.30 - real content
        # motion produces large inter-frame residuals, so only extreme
        # outliers may vote. The 0.40 threshold sits above everything real we
        # measured while still catching full-frame generation drift.
        score: Optional[int] = None
        reasons: List[str] = []

        if jitter_index > 0.40:
            score = 70
            reasons.append(
                f"Extreme inter-frame motion residual variance (jitter index {jitter_index:.3f} on "
                f"contiguous {frame_interval_seconds * 1000:.1f}ms frames) - generative "
                f"frame-to-frame drift rather than physical motion."
            )
        else:
            reasons.append(
                f"Inter-frame motion residuals are within the range produced by physical camera/"
                f"scene motion (jitter index {jitter_index:.3f}, contiguous "
                f"{frame_interval_seconds * 1000:.1f}ms frames) - no generative drift signature."
            )

        frame_scores = []
        if compute_frame_scores:
            for f in frames:
                try:
                    # Grid-peak rule is H.264-blind on video frames - see
                    # analyze_frequency_domain's include_grid_peaks docstring.
                    fs = analyze_frequency_domain(f, include_grid_peaks=False)["score"]
                except Exception:
                    fs = 15
                frame_scores.append(int(np.clip(fs, 1, 99)))

        return {
            "score": score,
            "active": score is not None,
            "temporal_flicker_energy": round(flicker_ratio, 4),
            "motion_residual_variance": round(jitter_index, 4),
            "frame_scores": frame_scores,
            "reasons": reasons
        }
    except Exception as e:
        return {
            "score": None,
            "active": False,
            "temporal_flicker_energy": 0.0,
            "motion_residual_variance": 0.0,
            "frame_scores": [],
            "reasons": [f"Temporal video analysis error: {e}"]
        }
