"""
Audio-track decode + rough analysis for video clips (A0).

Phase A0 of docs/audio-and-lip-sync-plan.md. This module is the *foundation*
for the audio/AV-sync family: it decodes the container's audio track from the
raw video bytes the server already downloaded (no second download) and reports
honest, training-free measurements about that track.

Scope discipline (this is what keeps the layer honest):

  * METRICS-ONLY. `score` is always None. Nothing here votes on the video
    tier. A synthetic voice over real footage is an *audio-AI* finding, not a
    deepfake video, so audio must stay a separate axis (plan section 3). The
    vote, if any, arrives only after calibration on a real-vs-TTS corpus
    (phases A3/A4).
  * It ABSTAINS when there is nothing to decode: client-frame payloads carry
    no bytes, and video-only / silent containers have no audio stream. It never
    fabricates a reading.
  * "speech" here is a rough energy + zero-crossing heuristic, NOT a speech
    classifier, and "narrow bandwidth" is a LEAD (vocoder/TTS re-synthesis
    shows it, but so do lossy music and older recordings), not proof.

Decodes mono float32 via ffmpeg. Sample rate defaults to 48 kHz rather than the
16 kHz of the plan's model path so the 8-16 kHz band - where vocoder and
resampling artifacts show - actually exists in the spectrum.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

try:
    import numpy as np
    _NP_AVAILABLE = True
except ImportError:  # pragma: no cover - degrades to inactive
    np = None  # type: ignore[assignment]
    _NP_AVAILABLE = False

# Layer gate. ON by default because the layer never votes - it only reports
# metrics (and stays out of the fusion entirely). Set AUDIO_TRACK=0 to skip the
# decode work altogether.
AUDIO_TRACK = os.environ.get("AUDIO_TRACK", "1") not in ("0", "false", "no")

# 48 kHz keeps the 8-16 kHz band; 16 kHz (the plan's model rate) would make any
# ">8 kHz" measurement meaningless. Env-overridable for the future torch path.
_SAMPLE_RATE = int(os.environ.get("AUDIO_SAMPLE_RATE", "48000"))
_MAX_SECONDS = float(os.environ.get("AUDIO_MAX_SECONDS", "120"))
_TIMEOUT_S = float(os.environ.get("AUDIO_FFMPEG_TIMEOUT", "120"))

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")

# VAD-ish frame geometry (25 ms frames, 10 ms hop) and the speech heuristic.
#
# The heuristic is deliberately CONSERVATIVE and documented as a heuristic: a
# constant tone and pink noise must NOT read as speech. It needs three things
# together - active (non-silent) frames, envelope dynamics (a talking voice has
# a strongly varying loudness envelope, a tone/steady noise does not), and
# modulation energy in the 2-8 Hz syllable band relative to the wider 0.5-50 Hz
# envelope band.
_FRAME_S = 0.025
_HOP_S = 0.010
_SILENCE_REL_DB = -45.0          # relative to the loudest frame
_SILENCE_ABS_DB = -55.0          # absolute floor: below this a frame is inactive
_SILENCE_RMS_DBFS = -60.0        # whole-track floor: below this the track is silence
_VOICED_MIN_FRACTION = 0.15      # of all frames
_SYLLABIC_BAND_HZ = (2.0, 8.0)
_ENVELOPE_BAND_HZ = (0.5, 50.0)  # denominator for the modulation share
_MIN_MOD_SHARE = 0.20            # envelope energy in 2-8 Hz / energy in 0.5-50 Hz
_MIN_ENV_CV = 0.25               # loudness-envelope coefficient of variation
_MIN_SPEECH_BAND_SHARE = 0.10    # energy share in the 300-3400 Hz speech band
_SPEECH_BAND_HZ = (300.0, 3400.0)  # classic telephony speech band
_MAX_SPECTRAL_FRAMES = 300       # cap on FFT windows for the spectral stats
_FFT_SIZE = 1024
_NARROW_BAND_HZ = 4000.0         # below this the "narrow-band" lead is stated
_NARROW_HF_SHARE = 0.005         # and only when almost nothing sits above 8 kHz

# Pitch tracking (autocorrelation) and the two TTS-lead measurements used by
# forensics/voice.py. All are measurements, not a synthetic-speech verdict.
_PITCH_FRAME_S = 0.040
_PITCH_HOP_S = 0.020
_PITCH_MAX_FRAMES = 1500         # ~30 s at a 20 ms hop; longer tracks sample evenly
_F0_MIN_HZ = 60.0
_F0_MAX_HZ = 500.0
_PITCH_MIN_DBFS = -45.0          # frames quieter than this are unvoiced
_MIN_PITCH_CORR = 0.35           # normalized autocorrelation peak for a voiced frame
_DIGITAL_SILENCE_DBFS = -70.0    # decoded PCM silence (TTS gaps) has no noise floor
_EDGE_PROBE_HZ = 500.0           # energy just below vs just above the 99% bandwidth


@dataclass
class AudioTrack:
    """A decoded mono audio track (float32, -1..1) plus its provenance."""

    samples: "np.ndarray"
    sample_rate: int
    duration: float

    def __len__(self) -> int:
        return int(self.samples.size)


def _abstain(reason: str, kind: str = "unavailable", **extra: Any) -> Dict[str, Any]:
    """Layer dict for 'nothing to analyze' - never a fabricated score."""
    out = {
        "score": None,
        "active": False,
        "applies": False,
        "kind": kind,
        "has_speech": None,
        "duration_s": None,
        "sample_rate_hz": None,
        "metrics": {},
        "reasons": [reason],
    }
    out.update(extra)
    return out


def _probe_audio_stream(video_path: str) -> Optional[str]:
    """Codec name of the first audio stream, or None when the container has no
    audio. Used only on the ffmpeg-failure path, to tell 'no audio stream' from
    'decode failed' without paying an extra probe on the common success path."""
    if not _FFPROBE:
        return None
    try:
        probe = subprocess.run(
            [_FFPROBE, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode != 0:
            return None
        codec = probe.stdout.strip().splitlines()
        return codec[0].strip() if codec else None
    except Exception:  # noqa: BLE001 - probe is best-effort classification
        return None


def extract_audio_detailed(
    video_bytes: Optional[bytes],
    max_seconds: Optional[float] = None,
) -> Tuple[Optional[AudioTrack], str]:
    """Decode the first audio stream to mono float32. Returns (track, reason).

    track is None when there is nothing usable, and reason explains why in
    user-facing language (no audio stream vs. no decoder vs. malformed input).
    `-map 0:a:0` makes ffmpeg fail loudly on a video-only container instead of
    emitting silence, which is the whole point: abstain, never fabricate.
    """
    if not video_bytes:
        return None, "Audio layer inactive: no video bytes on this request (client-extracted frames carry no container audio)."
    if not _NP_AVAILABLE:
        return None, "Audio layer inactive: numpy is not installed on this server."
    if not _FFMPEG:
        return None, "Audio layer inactive: ffmpeg is not installed on this server, so the audio track cannot be decoded."

    max_seconds = float(max_seconds or _MAX_SECONDS)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp = f.name

        run = subprocess.run(
            [_FFMPEG, "-v", "error", "-nostdin", "-i", tmp,
             "-vn", "-map", "0:a:0", "-ac", "1", "-ar", str(_SAMPLE_RATE),
             "-t", f"{max_seconds:.3f}", "-f", "f32le", "-"],
            capture_output=True, timeout=_TIMEOUT_S,
        )
        if run.returncode != 0 or not run.stdout:
            codec = _probe_audio_stream(tmp)
            if codec:
                return None, (f"Audio layer inactive: the audio stream ({codec}) could not be "
                              f"decoded with ffmpeg.")
            return None, ("Audio layer inactive: this container has no audio stream "
                          "(video-only download or a silent clip).")

        samples = np.frombuffer(run.stdout, dtype="<f4").astype(np.float32)
        if samples.size == 0:
            return None, "Audio layer inactive: the decoded audio track is empty."
        # Replace non-finite samples defensively so later statistics stay real.
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
        return (
            AudioTrack(samples=samples, sample_rate=_SAMPLE_RATE,
                       duration=float(samples.size) / _SAMPLE_RATE),
            "",
        )
    except subprocess.TimeoutExpired:
        return None, "Audio layer inactive: ffmpeg timed out while decoding the audio track."
    except Exception as e:  # noqa: BLE001 - decoding is best-effort, never fatal
        return None, f"Audio layer inactive: audio decode failed ({e})."
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def extract_audio(
    video_bytes: Optional[bytes],
    max_seconds: Optional[float] = None,
) -> Optional[AudioTrack]:
    """Decode the first audio stream to mono float32, or None when absent.

    Simple API used by the AV-sync / synthetic-speech layers (phases A1/A3);
    the server path uses `extract_audio_detailed` so it can report *why* the
    layer abstained.
    """
    track, _reason = extract_audio_detailed(video_bytes, max_seconds=max_seconds)
    return track


# ---------------------------------------------------------------------------
# Measurement helpers (training-free)
# ---------------------------------------------------------------------------

def _frame_stats(x: "np.ndarray", sample_rate: int) -> Dict[str, "np.ndarray"]:
    """Per-frame (25 ms / 10 ms hop) RMS energy and zero-crossing rate.

    Computed with cumulative sums rather than a sliding-window view so a long
    track never allocates an O(frames x frame_len) matrix.
    """
    frame_len = max(8, int(_FRAME_S * sample_rate))
    hop = max(1, int(_HOP_S * sample_rate))
    n = x.size
    if n <= 0:
        return {"rms": np.zeros(0, dtype=np.float64),
                "zcr": np.zeros(0, dtype=np.float64)}
    if n < frame_len:
        frame_len = n
        hop = max(1, n)
    n_frames = 1 + max(0, (n - frame_len) // hop)
    if n_frames <= 0:
        return {"rms": np.zeros(1, dtype=np.float64),
                "zcr": np.zeros(1, dtype=np.float64)}

    sq = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
    starts = np.arange(n_frames) * hop
    energy = sq[starts + frame_len] - sq[starts]
    rms = np.sqrt(np.maximum(energy, 0.0) / frame_len)

    sign_change = np.concatenate(([0.0], (x[:-1] * x[1:] < 0).astype(np.float64).cumsum()))
    zcr = (sign_change[starts + frame_len - 1] - sign_change[starts]) / max(1, frame_len - 1)
    return {"rms": rms, "zcr": zcr}


def _spectral_stats(x: "np.ndarray", sample_rate: int) -> Dict[str, float]:
    """Mean-spectrum statistics over up to _MAX_SPECTRAL_FRAMES Hann windows."""
    n = x.size
    n_fft = min(_FFT_SIZE, n)
    if n_fft < 32:
        return {}
    hop = max(1, (n - n_fft) // _MAX_SPECTRAL_FRAMES) if n > n_fft else 1
    starts = list(range(0, max(1, n - n_fft + 1), hop))[:_MAX_SPECTRAL_FRAMES]
    window = np.hanning(n_fft)
    frames = np.stack([x[s:s + n_fft] * window for s in starts])
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    mean_power = power.mean(axis=0) + 1e-12
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    total = float(mean_power.sum())
    if total <= 0:
        return {}

    cumulative = np.cumsum(mean_power)
    idx = int(np.searchsorted(cumulative, 0.99 * total))
    idx = min(idx, freqs.size - 1)
    bandwidth_99 = float(freqs[idx])

    # Spectral flatness (geometric mean / arithmetic mean of the frame power
    # spectra): near 1 = noise-like/white, near 0 = tonal/harmonic.
    flatness = np.exp(np.mean(np.log(power + 1e-12), axis=1)) / (
        np.mean(power, axis=1) + 1e-12
    )
    centroid = float((freqs * mean_power).sum() / total)

    def _share_above(hz: float) -> float:
        mask = freqs > hz
        return float(mean_power[mask].sum() / total) if mask.any() else 0.0

    def _share_between(low: float, high: float) -> float:
        mask = (freqs >= low) & (freqs <= high)
        return float(mean_power[mask].sum() / total) if mask.any() else 0.0

    # Low-pass edge ratio: energy in the 500 Hz just BELOW the 99% bandwidth
    # against the 500 Hz just ABOVE it. A codec/vocoder low-pass leaves a
    # cliff (ratio >> 1); a natural recording rolls off gradually. Measured,
    # reported, never scored on its own.
    edge_ratio = 0.0
    lo = (freqs >= max(0.0, bandwidth_99 - _EDGE_PROBE_HZ)) & (freqs < bandwidth_99)
    hi = (freqs >= bandwidth_99) & (freqs <= bandwidth_99 + _EDGE_PROBE_HZ)
    if lo.any() and hi.any():
        edge_ratio = float(mean_power[lo].sum() / max(mean_power[hi].sum(), 1e-12))

    return {
        "bandwidth_hz_99": round(bandwidth_99, 1),
        "lowpass_edge_ratio": round(min(edge_ratio, 999.0), 2),
        "hf_share_8k": round(_share_above(8000.0), 5),
        "hf_share_16k": round(_share_above(16000.0), 5),
        "speech_band_share": round(_share_between(300.0, 3400.0), 4),
        "spectral_centroid_hz": round(centroid, 1),
        "spectral_flatness_mean": round(float(np.mean(flatness)), 4),
    }


def _envelope_stats(rms: "np.ndarray") -> Dict[str, float]:
    """Loudness-envelope dynamics + syllable-rate (2-8 Hz) modulation.

    Speech amplitude is modulated by syllables at roughly 2-8 Hz AND swings
    widely (strong envelope dynamics), whereas a steady tone or stationary
    noise has a nearly constant envelope. Reporting both the modulation share
    (relative to the 0.5-50 Hz envelope band) and the envelope coefficient of
    variation is what keeps this heuristic from calling a sine wave "speech".
    It is still only a heuristic, not a speech classifier.
    """
    hop_rate = 1.0 / _HOP_S
    env = rms.astype(np.float64)
    if env.size < 32 or float(env.max()) <= 0:
        return {}
    mean = float(env.mean())
    out: Dict[str, float] = {
        "envelope_cv": round(float(env.std() / mean) if mean > 0 else 0.0, 4),
    }
    centered = env - mean
    if float(np.abs(centered).max()) <= 0:
        return out
    spectrum = np.abs(np.fft.rfft(centered * np.hanning(centered.size))) ** 2
    freqs = np.fft.rfftfreq(centered.size, d=1.0 / hop_rate)
    total_mask = (freqs >= _ENVELOPE_BAND_HZ[0]) & (freqs <= _ENVELOPE_BAND_HZ[1])
    band_mask = (freqs >= _SYLLABIC_BAND_HZ[0]) & (freqs <= _SYLLABIC_BAND_HZ[1])
    total = float(spectrum[total_mask].sum())
    if total <= 0:
        return out
    band = spectrum[band_mask]
    out["syllabic_energy_share"] = round(float(band.sum() / total), 4)
    out["syllabic_peak_hz"] = round(
        float(freqs[band_mask][int(np.argmax(band))]) if band.size else 0.0, 2)
    return out


def _pitch_stats(x: "np.ndarray", sample_rate: int) -> Dict[str, float]:
    """Autocorrelation pitch track: how much pitch range does the voice show?

    Expressive human speech swings across several semitones; concatenative /
    neural TTS is often markedly flatter. That is a LEAD (monotone delivery
    exists in real speech too), so the value is reported, and only a strongly
    flattened track contributes to the voice score in forensics/voice.py.

    Each frame is mean-removed and autocorrelated through an FFT (n_fft is
    twice the frame so the circular wrap never reaches the lags we read).
    """
    frame_len = int(_PITCH_FRAME_S * sample_rate)
    hop = int(_PITCH_HOP_S * sample_rate)
    n = x.size
    if n < frame_len or frame_len <= 0:
        return {}
    starts = list(range(0, n - frame_len + 1, hop))
    if len(starts) > _PITCH_MAX_FRAMES:
        stride = len(starts) / _PITCH_MAX_FRAMES
        starts = [starts[int(i * stride)] for i in range(_PITCH_MAX_FRAMES)]

    lag_min = max(1, int(sample_rate / _F0_MAX_HZ))
    lag_max = min(frame_len - 1, int(sample_rate / _F0_MIN_HZ))
    if lag_max <= lag_min:
        return {}

    n_fft = 1
    while n_fft < 2 * frame_len:
        n_fft <<= 1

    f0s = []
    for s in starts:
        frame = x[s:s + frame_len].astype(np.float64)
        if float(np.sqrt(np.mean(frame ** 2))) <= 10.0 ** (_PITCH_MIN_DBFS / 20.0):
            continue
        frame = frame - frame.mean()
        spectrum = np.fft.rfft(frame, n=n_fft)
        ac = np.fft.irfft(np.abs(spectrum) ** 2, n=n_fft)[:frame_len]
        if ac[0] <= 1e-12:
            continue
        ac = ac / ac[0]
        lag = lag_min + int(np.argmax(ac[lag_min:lag_max + 1]))
        if ac[lag] < _MIN_PITCH_CORR:
            continue
        f0s.append(sample_rate / lag)

    frames = len(starts)
    if not f0s or frames == 0:
        return {"voiced_fraction": 0.0}
    f0 = np.asarray(f0s, dtype=np.float64)
    median = float(np.median(f0))
    semitones = 12.0 * np.log2(np.maximum(f0, 1e-6) / max(median, 1e-6))
    return {
        "voiced_fraction": round(len(f0s) / frames, 4),
        "f0_median_hz": round(median, 1),
        "f0_std_semitones": round(float(np.std(semitones)), 3),
        "f0_range_semitones": round(
            float(np.percentile(semitones, 95) - np.percentile(semitones, 5)), 3),
    }


def analyze_track(track: AudioTrack) -> Dict[str, Any]:
    """Training-free measurements for a decoded track (metrics-only layer)."""
    x = track.samples.astype(np.float64)
    sr = track.sample_rate
    n = x.size
    duration = float(track.duration)

    peak = float(np.max(np.abs(x))) if n else 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) if n else 0.0
    rms_dbfs = round(20.0 * float(np.log10(max(rms, 1e-6))), 1)
    peak_dbfs = round(20.0 * float(np.log10(max(peak, 1e-6))), 1)

    frame = _frame_stats(x, sr)
    frame_rms = frame["rms"]
    frame_zcr = frame["zcr"]
    frame_db = 20.0 * np.log10(np.maximum(frame_rms, 1e-6))
    loudest_db = float(frame_db.max()) if frame_db.size else -120.0

    metrics: Dict[str, Any] = {
        "duration_s": round(duration, 2),
        "sample_rate_hz": sr,
        "rms_dbfs": rms_dbfs,
        "peak_dbfs": peak_dbfs,
        "frames_analyzed": int(frame_rms.size),
    }

    # Whole-track silence: an absolute floor, not a relative one - a fully
    # digital-silent track has no loudest frame to be relative to, so a
    # relative-only threshold would call every silent frame "active" (and then
    # run spectral stats on nothing but float noise).
    if duration < 0.2 or rms_dbfs <= _SILENCE_RMS_DBFS or loudest_db <= _SILENCE_ABS_DB or not frame_db.size:
        metrics["silence_fraction"] = 1.0
        metrics["active_fraction"] = 0.0
        return {
            "score": None,  # metrics-only until calibrated (phases A3/A4)
            "active": True,
            "applies": True,
            "kind": "silence",
            "has_speech": False,
            "duration_s": round(duration, 2),
            "sample_rate_hz": sr,
            "metrics": metrics,
            "reasons": [
                f"Audio track present but silent: {duration:.1f} s, {sr} Hz mono, "
                f"mean loudness {rms_dbfs:.1f} dBFS.",
                "No meaningful audio content was found (near-silence); no audio-side "
                "reading is drawn from this clip.",
            ],
        }

    active_mask = (frame_db > (loudest_db + _SILENCE_REL_DB)) & (frame_db > _SILENCE_ABS_DB)
    active_fraction = float(np.mean(active_mask)) if active_mask.size else 0.0
    silence_fraction = round(1.0 - active_fraction, 4)
    zcr_active = float(np.mean(frame_zcr[active_mask])) if active_mask.any() else 0.0

    # Noise floor + digital-silence share. A real recording has an audible
    # floor in the gaps between words; TTS rendered to PCM often has exact
    # zeros, and a gated/cleaned studio voice has a floor far below anything
    # a microphone produces. Both are leads for forensics/voice.py.
    metrics.update({
        "active_fraction": round(active_fraction, 4),
        "silence_fraction": silence_fraction,
        "zero_crossing_rate_mean": round(zcr_active, 4),
        "noise_floor_dbfs": round(float(np.percentile(frame_db, 5)), 1),
        "digital_silence_fraction": round(float(np.mean(frame_db < _DIGITAL_SILENCE_DBFS)), 4),
    })
    metrics.update(_spectral_stats(x, sr))
    metrics.update(_envelope_stats(frame_rms))
    metrics.update(_pitch_stats(x, sr))

    env_cv = float(metrics.get("envelope_cv") or 0.0)
    mod_share = float(metrics.get("syllabic_energy_share") or 0.0)
    band_share = float(metrics.get("speech_band_share") or 0.0)
    # Three independent conditions, all required: sound is present, the
    # loudness envelope actually swings (a steady tone or stationary noise does
    # not), it swings at syllable rate, and there is meaningful energy in the
    # 300-3400 Hz speech band (a low tremolo tone with no harmonics is
    # rhythmic but not speech-like). Rhythmic music can still satisfy all of
    # these - hence "heuristic", reported as a hint and never scored.
    has_speech = bool(
        duration >= 0.8
        and active_fraction >= _VOICED_MIN_FRACTION
        and mod_share >= _MIN_MOD_SHARE
        and env_cv >= _MIN_ENV_CV
        and band_share >= _MIN_SPEECH_BAND_SHARE
    )
    kind = "speech" if has_speech else "nonspeech"

    reasons = [
        f"Audio track (reported on its own axis, never scored against the video "
        f"tier): {duration:.1f} s, {sr} Hz mono, mean loudness {rms_dbfs:.1f} dBFS, "
        f"peak {peak_dbfs:.1f} dBFS, {silence_fraction * 100:.0f}% of frames near-silent."
    ]
    if has_speech:
        reasons.append(
            f"Rough voice-activity estimate: speech-likely - {active_fraction * 100:.0f}% of "
            f"frames carry sound, the loudness envelope swings widely (variation "
            f"{env_cv:.2f}) at syllable rate ({mod_share * 100:.0f}% of its modulation energy "
            f"in the 2-8 Hz band, ~{metrics.get('syllabic_peak_hz', 0.0):.1f} Hz), and "
            f"{band_share * 100:.0f}% of the spectral energy sits in the 300-3400 Hz speech "
            f"band. These are energy/periodicity heuristics, not a speech classifier - "
            f"strongly rhythmic music can also satisfy them - and they say nothing about "
            f"whether the speech is synthetic."
        )
    else:
        reasons.append(
            f"Rough voice-activity estimate found no clear speech (envelope variation "
            f"{env_cv:.2f}, 2-8 Hz modulation share {mod_share * 100:.0f}%, 300-3400 Hz "
            f"energy share {band_share * 100:.0f}%). This may be music, ambience or "
            f"non-speech audio, so no audio-side reading is drawn."
        )

    bandwidth = float(metrics.get("bandwidth_hz_99") or 0.0)
    hf_share = float(metrics.get("hf_share_8k") or 0.0)
    if bandwidth:
        line = (f"Effective audio bandwidth {bandwidth / 1000.0:.1f} kHz (99% of energy) with "
                f"{hf_share * 100:.1f}% of energy above 8 kHz.")
        if bandwidth < _NARROW_BAND_HZ and hf_share < _NARROW_HF_SHARE:
            line += (" Narrow-band audio is common in vocoder/TTS re-synthesis, but lossy "
                     "music and older recordings share the signature - a lead only, never a vote.")
        reasons.append(line)

    return {
        "score": None,  # metrics-only until calibrated (phases A3/A4)
        "active": True,
        "applies": True,
        "kind": kind,
        "has_speech": has_speech,
        "duration_s": round(duration, 2),
        "sample_rate_hz": sr,
        "metrics": metrics,
        "reasons": reasons,
    }


def analyze_audio_track(
    video_bytes: Optional[bytes],
    max_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Full A0 entry point: decode the container audio and measure it.

    Always returns a layer dict. When the layer is gated off (`AUDIO_TRACK=0`)
    or there is nothing to decode it returns the honest abstain shape with
    `score=None`, `active=False` and a reason explaining why - the video
    verdict is never affected either way.
    """
    if not AUDIO_TRACK:
        return _abstain("Audio layer disabled (AUDIO_TRACK=0).")
    track, reason = extract_audio_detailed(video_bytes, max_seconds=max_seconds)
    if track is None:
        return _abstain(reason or "Audio layer inactive: no decodable audio track.")
    try:
        return analyze_track(track)
    except Exception as e:  # noqa: BLE001 - a metrics failure must never break a scan
        return _abstain(f"Audio layer inactive: measurement failed ({e}).")
