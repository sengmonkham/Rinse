"""
Layer: Remote photoplethysmography (rPPG) pulse-consistency analysis (video only).

Background
----------
Each heartbeat changes facial skin color by an imperceptible amount (the
blood-volume pulse), strongest in the green channel. Remote photoplethysmography
(rPPG) recovers a cardiac-frequency signal from a face video by tracking those
sub-perceptual color changes. Because face-manipulation pipelines disrupt the
natural periodic pulse signal, rPPG has been used as a deepfake cue in a real
cited body of work (Ciftci et al. / FakeCatcher; Ciftci et al.; Boccignone et
al. "DeepFakes Have No Heart", ICIAP 2022; DeepRhythm; Wu et al. 2023 survey).

Caveats we design around
------------------------
1. "High-quality deepfakes can now have a heart" (Seibold et al., Frontiers in
   Imaging, 2025): a present pulse is no longer proof of real footage, and an
   absent pulse is no longer proof of a fake. This layer is therefore
   confidence-weighted and fusion-only, never decisive on its own.
2. Instagram/social H.264 compression and off-axis/small faces destroy the
   weakest rPPG signals. The layer must abstain rather than vote on garbage.
3. This is a FACE cue. Non-face videos and images get not_applicable.

Design
------
Face-gated: a MediaPipe BlazeFace FULL-RANGE detector finds face(s) on the
analyzed window. If there is no face / the face is too small / too few usable
frames contain a face, the layer is not_applicable (contributes 0 to fusion,
reported in window_details).

On a passing face window we extract a per-frame green-channel average over the
face ROI and analyze the resulting 1D signal in the cardiac band with simple,
deterministic, reproducible signal processing (DFT-based band energy ratio +
spectral concentration). No trained classifier in the first cut - this keeps it
calibratable and consistent with the existing PwTF-DVD temporal layer.

Return contract (matches other temporal layers in this stack):
  {
      "score": int | None,     # None when not_applicable / inactive
      "active": bool,
      "applies": bool,         # True when a real face ROI was analyzed
      "pulse_present": bool,   # strongest periodic cardiac-band signal detected
      "pulse_score": int,      # confidence-weighted 0-100 (mirrors "score" when active)
      "estimated_hr": float | None,
      "band_energy": float,
      "spectral_concentration": float,
      "reasons": list[str],
      "not_applicable_reason": str | None,
  }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
import numpy as np
from PIL import Image

# MediaPipe Tasks Vision face detector + model asset.
# The wheel (mediapipe) is an optional dependency; the model asset is bundled
# under forensics/models/ and resolved relative to this module.
#
# Full-range BlazeFace is the better choice for forensics on varied video (vs the
# short-range model, which is tuned for close-up mobile faces and can miss faces
# that are small/off-axis). The model asset is bundled under forensics/models/.
_RPPG_FACE_MODEL = os.path.join(os.path.dirname(__file__), "models", "blaze_face_full_range.tflite")

_MEDIAPIPE_AVAILABLE = False
_mp = None
_vision = None
_FaceDetector = None
_FaceDetectorOptions = None
_BaseOptions = None
_RunningMode = None
_Image = None
_ImageFormat = None

try:
    import mediapipe as mp  # noqa: F401
    from mediapipe.tasks import python as _mp_tasks
    from mediapipe.tasks.python import vision as _mp_vision

    _mp = mp
    _vision = _mp_vision
    _FaceDetector = _mp_vision.FaceDetector
    _FaceDetectorOptions = _mp_vision.FaceDetectorOptions
    _BaseOptions = _mp_tasks.BaseOptions
    _RunningMode = _mp_vision.RunningMode
    _Image = mp.Image
    _ImageFormat = mp.ImageFormat
    _MEDIAPIPE_AVAILABLE = True
except Exception:  # noqa: BLE001 - rPPG simply becomes inactive if MP is missing
    _MEDIAPIPE_AVAILABLE = False

# Cardiac band (Hz). Human resting heart rate ~ 0.5-4 Hz (30-240 bpm); we use a
# slightly wider analysis band and a tighter "dominant pulse" sub-band so that a
# real pulse (usually 0.8-2.5 Hz for the kinds of clips we see) concentrates in
# a narrow peak while noise/faked periodic signals tend not to.
_CARDIAC_BAND_LO = 0.6   # Hz
_CARDIAC_BAND_HI = 3.5   # Hz
# A real pulse tends to concentrate its energy in a narrow band; we measure that
# concentration relative to a surrounding "noise" band.
_PULSE_PEAK_BAND_LO = 0.8   # Hz
_PULSE_PEAK_BAND_HI = 2.8   # Hz

# Gating thresholds. Configurable for experiments; the DEFAULTS ARE UNCHANGED
# because there is not yet a real face-video corpus to calibrate a looser gate
# against. Measured 2026-10-12 on the local clips: a real 900x720 clip with
# clearly detected faces (67-92px, MediaPipe conf 0.72-0.88) is rejected here
# purely by the 0.04 AREA-FRACTION gate (its faces are ~0.0095 of the frame),
# so on landscape video the gate effectively demands a very large face. Lowering
# it would activate rPPG on such clips, BUT the analysis window is only the shot
# window (32 frames ~= 1.3s at 24fps) while a usable cardiac estimate needs
# several seconds, so a looser gate would mostly produce noisy votes. The real
# fix is a longer dedicated rPPG window, not a looser gate - see
# docs/detector-review-and-video-plan.md. Exposed as env knobs to enable that
# experiment without changing production behavior.
_FACE_MIN_FRAMES = int(os.environ.get("RPPG_FACE_MIN_FRAMES", "10"))  # min frames containing a face
_FACE_MIN_SIZE_PX = int(os.environ.get("RPPG_FACE_MIN_PX", "48"))    # face box min side (px)
_FACE_MIN_SIZE_FRAC = float(os.environ.get("RPPG_FACE_MIN_FRAC", "0.04"))  # ...or min area fraction
_FACE_CONFIDENCE = float(os.environ.get("RPPG_FACE_CONFIDENCE", "0.40"))   # min detection score
_ROI_MIN_FRAC = 0.01           # face ROI must be at least this fraction of the frame


def _face_detector_image_mode() -> Optional[Any]:
    """Build a one-shot IMAGE-mode MediaPipe FaceDetector for a single frame.

    Returns None (and leaves the layer inactive) when MediaPipe or the model
    asset is unavailable, or when construction fails for any reason.
    """
    if not _MEDIAPIPE_AVAILABLE:
        return None
    if not os.path.exists(_RPPG_FACE_MODEL):
        return None
    try:
        opts = _FaceDetectorOptions(
            base_options=_BaseOptions(model_asset_path=_RPPG_FACE_MODEL),
            min_detection_confidence=_FACE_CONFIDENCE,
            min_suppression_threshold=0.3,
            running_mode=_RunningMode.IMAGE,
        )
        return _FaceDetector.create_from_options(opts)
    except Exception:  # noqa: BLE001
        return None


def _detect_faces_on_frame(
    frame: Image.Image,
) -> List[Dict[str, Any]]:
    """Return a list of face boxes (in PIL/frame pixel coords) on a single frame.

    Each entry: {x, y, w, h, score}.
    """
    if not _MEDIAPIPE_AVAILABLE:
        return []
    det = _face_detector_image_mode()
    if det is None:
        return []
    try:
        w, h = frame.size
        mp_img = _Image(image_format=_ImageFormat.SRGB, data=np.asarray(frame))
        res = det.detect(mp_img)
        out: List[Dict[str, Any]] = []
        for d in res.detections:
            bb = d.bounding_box
            sc = d.categories[0].score if d.categories else 0.0
            out.append({
                "x": int(bb.origin_x),
                "y": int(bb.origin_y),
                "w": int(bb.width),
                "h": int(bb.height),
                "score": float(sc),
            })
        return out
    except Exception:  # noqa: BLE001
        return []
    finally:
        try:
            det.close()
        except Exception:  # noqa: BLE001
            pass


def _choose_face_box(boxes: List[Dict[str, Any]], frame_w: int, frame_h: int) -> Optional[Tuple[int, int, int, int]]:
    """Pick the best face box for rPPG ROI (largest, confident, not tiny)."""
    if not boxes:
        return None
    best = None
    best_area = -1
    for b in boxes:
        if b["score"] < _FACE_CONFIDENCE:
            continue
        area = b["w"] * b["h"]
        if area < best_area:
            continue
        # hard tiny-face gate
        if b["w"] < _FACE_MIN_SIZE_PX or b["h"] < _FACE_MIN_SIZE_PX:
            continue
        if area < _FACE_MIN_SIZE_FRAC * (frame_w * frame_h):
            continue
        best = b
        best_area = area
    return (best["x"], best["y"], best["w"], best["h"]) if best else None


def _face_roi_signal(
    frames: List[Image.Image],
    box: Tuple[int, int, int, int],
) -> Optional[np.ndarray]:
    """Green-channel mean over the (integer-clipped) face ROI for each frame.

    Returns a 1D float32 array of length len(frames), or None on any problem.
    """
    if not frames:
        return None
    x, y, w, h = box
    signal: List[float] = []
    for f in frames:
        try:
            arr = np.asarray(f.convert("RGB"), dtype=np.float32)
            h_img, w_img = arr.shape[:2]
            # clip box to image bounds
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(w_img, x + w)
            y1 = min(h_img, y + h)
            if x1 <= x0 or y1 <= y0:
                return None
            roi = arr[y0:y1, x0:x1, 1]  # green channel
            if roi.size == 0:
                return None
            signal.append(float(roi.mean()))
        except Exception:  # noqa: BLE001
            return None
    if len(signal) < 3:
        return None
    return np.asarray(signal, dtype=np.float32)


def _band_energy_dft(signal: np.ndarray, fps: float, lo: float, hi: float) -> float:
    """Total spectral energy in [lo, hi] Hz via DFT (real signal)."""
    n = len(signal)
    if n < 2 or fps <= 0:
        return 0.0
    if hi <= lo:
        return 0.0
    f = np.fft.rfftfreq(n, d=1.0 / fps)
    mag = np.abs(np.fft.rfft(signal))
    mask = (f >= lo) & (f <= hi)
    if not np.any(mask):
        return 0.0
    return float(np.sum(mag[mask] ** 2))


def _dominant_peak_in_band(signal: np.ndarray, fps: float, lo: float, hi: float) -> Tuple[float, float]:
    """Return (peak_frequency_hz, peak_to_total_ratio_in_band).

    peak_to_total_ratio is the fraction of the band's energy concentrated at the
    single strongest frequency bin - a simple concentration / "periodic vs noise"
    measure.
    """
    n = len(signal)
    if n < 2 or fps <= 0 or hi <= lo:
        return (0.0, 0.0)
    f = np.fft.rfftfreq(n, d=1.0 / fps)
    mag = np.abs(np.fft.rfft(signal))
    mask = (f >= lo) & (f <= hi)
    if not np.any(mask):
        return (0.0, 0.0)
    band_mag = mag[mask]
    total = float(np.sum(band_mag ** 2))
    if total <= 0:
        return (0.0, 0.0)
    idx = int(np.argmax(band_mag))
    peak_freq = float(f[mask][idx]) if mask[idx] else 0.0
    peak_frac = float((band_mag[idx] ** 2) / total)
    return (peak_freq, peak_frac)


def analyze_face_pulse(
    frames: List[Image.Image],
    frame_interval_seconds: Optional[float],
) -> Dict[str, Any]:
    """rPPG pulse-consistency analysis on a contiguous native-fps face window.

    Args:
        frames: Contiguous PIL RGB frames (e.g. a 32-frame window from one shot).
        frame_interval_seconds: Real per-frame interval. The layer refuses to vote
            when this is missing/invalid, because non-contiguous sampling fabricates
            temporal signals (mirrors temporal.py's contract).

    Returns dict with keys documented in the module docstring.
    """
    reasons: List[str] = []

    if not frames or len(frames) < 3:
        return {
            "score": None,
            "active": False,
            "applies": False,
            "pulse_present": False,
            "pulse_score": 12,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": ["Insufficient frames for rPPG analysis (minimum 3 required)."],
            "not_applicable_reason": "insufficient_frames",
        }

    if frame_interval_seconds is None or frame_interval_seconds <= 0 or frame_interval_seconds > 0.5:
        return {
            "score": None,
            "active": False,
            "applies": False,
            "pulse_present": False,
            "pulse_score": 12,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": [
                "rPPG inactive: frames were not a contiguous, regularly-spaced native-frame-rate "
                "sequence (no valid frame interval), so any pulse readout would be a sampling artifact."
            ],
            "not_applicable_reason": "non_contiguous_frames",
        }

    fps = 1.0 / frame_interval_seconds

    # 1. Face detection gating (automatic: figure out whether there is a face).
    if not _MEDIAPIPE_AVAILABLE or not os.path.exists(_RPPG_FACE_MODEL):
        return {
            "score": None,
            "active": False,
            "applies": False,
            "pulse_present": False,
            "pulse_score": 12,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": [
                "rPPG inactive: face detection (MediaPipe BlazeFace) unavailable or model asset missing "
                "(expected at forensics/models/blaze_face_full_range.tflite)."
            ],
            "not_applicable_reason": "face_detector_unavailable",
        }

    # Detect faces on a representative subset of frames (not every frame - cheap).
    sample_idx = _sample_frame_indices(len(frames), max_samples=12)
    face_counts_per_frame: List[int] = []
    best_box: Optional[Tuple[int, int, int, int]] = None
    best_box_count = 0
    frame_w = frames[0].size[0]
    frame_h = frames[0].size[1]

    for i in sample_idx:
        boxes = _detect_faces_on_frame(frames[i])
        face_counts_per_frame.append(len([b for b in boxes if b["score"] >= _FACE_CONFIDENCE]))
        box = _choose_face_box(boxes, frame_w, frame_h)
        if box is not None:
            best_box = box
            best_box_count += 1

    n_with_face = sum(1 for c in face_counts_per_frame if c > 0)

    if n_with_face < 3:
        return {
            "score": None,
            "active": False,
            "applies": False,
            "pulse_present": False,
            "pulse_score": 12,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": [
                f"rPPG inactive: no reliable face detected - only {n_with_face} of {len(sample_idx)} "
                "sampled frames contained a confident face."
            ],
            "not_applicable_reason": "no_face",
        }

    if best_box is None:
        return {
            "score": None,
            "active": False,
            "applies": False,
            "pulse_present": False,
            "pulse_score": 12,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": [
                "rPPG inactive: faces were detected but none were large/confident enough for a usable ROI."
            ],
            "not_applicable_reason": "face_too_small",
        }

    # require the chosen box to appear on enough frames to trust the ROI tracking
    if best_box_count < _FACE_MIN_FRAMES:
        return {
            "score": None,
            "active": False,
            "applies": False,
            "pulse_present": False,
            "pulse_score": 12,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": [
                f"rPPG inactive: the detected face ROI was present on only {best_box_count} of "
                f"{len(sample_idx)} sampled frames - too unstable for a pulse readout."
            ],
            "not_applicable_reason": "face_unstable",
        }

    x, y, w, h = best_box
    roi_frac = (w * h) / (frame_w * frame_h)
    if roi_frac < _ROI_MIN_FRAC:
        return {
            "score": None,
            "active": False,
            "applies": False,
            "pulse_present": False,
            "pulse_score": 12,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": [
                f"rPPG inactive: face ROI is only {roi_frac:.3f} of the frame (below {_ROI_MIN_FRAC}), "
                "too small for a reliable pulse signal."
            ],
            "not_applicable_reason": "face_too_small",
        }

    reasons.append(
        f"rPPG applied: face ROI {w}x{h} px ({roi_frac*100:.1f}% of frame) tracked on "
        f"{best_box_count}/{len(sample_idx)} sampled frames at {fps:.1f} fps."
    )

    # 2. Extract green-channel ROI pulse signal across the full window.
    signal = _face_roi_signal(frames, best_box)
    if signal is None or len(signal) < 3:
        return {
            "score": None,
            "active": True,
            "applies": True,
            "pulse_present": False,
            "pulse_score": 35,
            "estimated_hr": None,
            "band_energy": 0.0,
            "spectral_concentration": 0.0,
            "reasons": ["rPPG applied but ROI signal extraction failed (degenerate ROI)."],
            "not_applicable_reason": None,
        }

    # Detrend (remove slow illumination/exposure drift - not cardiac).
    sig = signal - signal.mean()

    band_energy = _band_energy_dft(sig, fps, _CARDIAC_BAND_LO, _CARDIAC_BAND_HI)
    total_energy = _band_energy_dft(sig, fps, 0.2, 8.0)
    band_share = band_energy / (total_energy + 1e-9)

    peak_freq, conc = _dominant_peak_in_band(sig, fps, _PULSE_PEAK_BAND_LO, _PULSE_PEAK_BAND_HI)

    # Estimate HR from the strongest peak in the wider cardiac band (if confident).
    hr = None
    if peak_freq > 0:
        hr = round(peak_freq * 60.0, 1)

    # Decision: a credible pulse is (a) a meaningful amount of energy in the cardiac
    # band AND (b) that energy is concentrated (a narrow dominant peak) rather than
    # flat noise. A single hard threshold would be too brittle across compression /
    # lighting / fps - so we score confidence-weighted and let fusion decide.
    pulse_present = bool(band_share > 0.12 and conc > 0.25 and band_energy > 1e-6)

    reasons.append(
        f"Cardiac-band ({_CARDIAC_BAND_LO}-{_CARDIAC_BAND_HI} Hz) energy share {band_share:.2f}, "
        f"peak concentration {conc:.2f} at {peak_freq:.2f} Hz"
        + (f" (~{hr:.0f} bpm)" if hr else "") + "."
    )

    # Confidence-weighted score. This is deliberately moderate: even a clean pulse is
    # only mild evidence of real footage given modern fakes can synthesize a heartbeat,
    # and an absent pulse is mild evidence of a fake only on a clearly-face video.
    score = 12
    if pulse_present:
        # stronger when both band energy share and peak concentration are high
        conc_comp = min(1.0, conc / 0.5)
        share_comp = min(1.0, band_share / 0.5)
        conf = 0.5 * conc_comp + 0.5 * share_comp
        score = int(round(12 + conf * 34))  # 12 -> up to ~46
        if score < 30:
            score = 30
    else:
        # no credible pulse, but we did analyze a real face -> mild "odd for a real face"
        score = 32

    # cap so rPPG never dominates the ensemble on its own
    score = int(max(12, min(60, score)))

    return {
        "score": score,
        "active": True,
        "applies": True,
        "pulse_present": pulse_present,
        "pulse_score": score,
        "estimated_hr": hr,
        "band_energy": round(float(band_energy), 4),
        "spectral_concentration": round(float(conc), 4),
        "reasons": reasons,
        "not_applicable_reason": None,
    }


def _sample_frame_indices(n_frames: int, max_samples: int = 12) -> List[int]:
    """Evenly spaced frame indices (inclusive of first and last)."""
    if n_frames <= max_samples:
        return list(range(n_frames))
    out = []
    for k in range(max_samples):
        out.append(int(round(k * (n_frames - 1) / (max_samples - 1))))
    seen = set()
    res: List[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            res.append(i)
    return res


def analyze_video_rppg(
    frames: List[Image.Image],
    frame_interval_seconds: Optional[float],
) -> Dict[str, Any]:
    """Public entry point used by server.py for the video rPPG layer.

    Mirrors the contract of analyze_video_temporal_coherence(): accepts a contiguous
    native-fps frame window and a real frame interval, returns a dict with a 'score'
    (None when inactive) plus reasons. Image-path / non-face video callers get an
    inactive result (score None) rather than a fake vote.
    """
    if not frames:
        return {
            "score": None,
            "active": False,
            "reasons": ["No frames provided for rPPG analysis."],
        }
    return analyze_face_pulse(frames, frame_interval_seconds)
