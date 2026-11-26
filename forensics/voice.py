"""Voice / synthetic-speech detection (training-free, evidence-weighted).

This is the scored sibling of ``forensics/audio_track.py``. The audio-track
layer reports measurements on a separate axis and never votes; this module
turns the same measurements into a **voice** verdict, which is what you want
when the input IS the voice: an uploaded recording, a voice note, or the audio
track of a video (a real clip with a TTS voiceover is an audio-AI finding, so
the voice verdict stays separate from the video tier).

Evidence used (each one a documented lead, not proof):

  * **Band-limited spectrum** - neural vocoders and TTS pipelines synthesize
    at 16/22.05/24 kHz, so the 99% bandwidth sits far below a microphone
    recording's and almost nothing survives above those edges.
  * **Low-pass cliff** - a hard synthesis/codec edge (energy in the 500 Hz
    below the edge vs above it) rather than the gradual acoustic rolloff of a
    real room + microphone.
  * **Digital-silence gaps** - TTS rendered to PCM has exact-zero gaps between
    words; a microphone always records a noise floor, breath and room tone.
  * **Flattened pitch** - concatenative/neural TTS is often markedly flatter
    than expressive human speech; a strongly flattened autocorrelation pitch
    track contributes, a wide one counts against synthesis.
  * **Wideband + expressive delivery + audible floor** count as HUMAN-sounding
    evidence and subtract from the score.

The score is a transparent sum over those signals (base + weighted evidence),
clamped to 2-98. It is NOT a trained classifier and is not calibrated against
a real-vs-TTS corpus yet; the README says so plainly. Non-speech audio and
silence abstain with ``score: null`` instead of inventing a verdict, and the
result always carries the per-signal breakdown so the number is auditable.

Environment:
  VOICE_DETECTION=0   disable the layer (endpoint answers 503, video audio
                      block keeps its measurements but gets no voice score)
  VOICE_MAX_SECONDS   decoded-audio cap (default 120, from audio_track)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from forensics import audio_track as _audio

VOICE_DETECTION = os.environ.get("VOICE_DETECTION", "1") not in ("0", "false", "no")

_BASE_SCORE = 30.0
_MIN_SPEECH_SECONDS = 1.0

# Thresholds for the individual signals. Kept as module constants so the
# numbers in the README and the code cannot drift apart silently.
_NARROW_BAND_HZ = 8000.0
_NARROW_HF_SHARE = 0.01
_MID_BAND_HZ = 12000.0
_MID_HF_SHARE = 0.005
_EDGE_RATIO_STRONG = 40.0
_EDGE_MAX_BAND_HZ = 16000.0
_SILENCE_SHARE_STRONG = 0.10
_SILENCE_SHARE_WEAK = 0.03
_MONOTONE_STD_STRONG = 1.5
_MONOTONE_STD_WEAK = 2.5
_LOW_FLOOR_DBFS = -65.0
_WIDEBAND_HZ = 12000.0
_WIDEBAND_HF_SHARE = 0.02
_EXPRESSIVE_STD = 3.5

_TIER_THRESHOLDS = (
    (80, "SYNTHETIC_AI"),
    (69, "SUSPICIOUS"),
    (55, "UNCERTAIN"),
    (35, "INCONCLUSIVE"),
)


def _abstain(reason: str, kind: str = "unavailable", **extra: Any) -> Dict[str, Any]:
    out = {
        "score": None,
        "label": "No voice verdict",
        "tier": "INCONCLUSIVE",
        "confidence": "LOW",
        "active": False,
        "kind": kind,
        "has_speech": None,
        "duration_s": None,
        "signals": [],
        "metrics": {},
        "reasons": [reason],
    }
    out.update(extra)
    return out


def _tier(score: int) -> str:
    for threshold, tier in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "AUTHENTIC_HUMAN"


def _label(score: int) -> str:
    if score >= 80:
        return "Synthetic voice (high confidence)"
    if score >= 69:
        return "Synthetic voice likely"
    if score >= 55:
        return "Leaning synthetic"
    if score >= 35:
        return "Inconclusive"
    return "Human-sounding voice"


def _signal(
    signals: List[Dict[str, Any]],
    cid: str,
    label: str,
    value: Any,
    contribution: float,
    detail: str,
) -> None:
    """Record one piece of evidence (positive = synthetic, negative = human)."""
    signals.append({
        "id": cid,
        "label": label,
        "value": value,
        "contribution": round(contribution, 1),
        "detail": detail,
    })


def _fmt_hz(value: float) -> str:
    return f"{value / 1000.0:.1f} kHz"


def score_layer(layer: Dict[str, Any]) -> Dict[str, Any]:
    """Score an already-measured audio layer (see audio_track.analyze_track).

    Pure function of the metrics dict, so the video path can add a voice
    verdict without decoding the track a second time.
    """
    if not VOICE_DETECTION:
        return _abstain("Voice detection disabled (VOICE_DETECTION=0).")

    if not layer or not layer.get("applies"):
        reason = (layer or {}).get("reasons", ["No decodable audio track."])[0]
        return _abstain(reason, kind="unavailable")

    duration = float(layer.get("duration_s") or 0.0)
    if layer.get("kind") == "silence":
        return _abstain(
            f"Audio track is silent ({duration:.1f} s), so there is no voice to judge.",
            kind="silence", has_speech=False, duration_s=round(duration, 2),
        )

    if not layer.get("has_speech"):
        return _abstain(
            "No clear speech was found in this audio, so no voice score is drawn "
            "(music, ambience and non-speech audio are out of scope for this layer).",
            kind=str(layer.get("kind") or "nonspeech"),
            has_speech=False,
            duration_s=round(duration, 2),
        )

    if duration < _MIN_SPEECH_SECONDS:
        return _abstain(
            f"Speech segment is too short to judge ({duration:.1f} s; need "
            f"{_MIN_SPEECH_SECONDS:.0f} s or more).",
            kind="speech", has_speech=True, duration_s=round(duration, 2),
        )

    metrics = layer.get("metrics") or {}
    signals: List[Dict[str, Any]] = []
    notes: List[str] = []

    bandwidth = float(metrics.get("bandwidth_hz_99") or 0.0)
    hf8 = float(metrics.get("hf_share_8k") or 0.0)
    edge = float(metrics.get("lowpass_edge_ratio") or 0.0)
    digital_silence = float(metrics.get("digital_silence_fraction") or 0.0)
    noise_floor = metrics.get("noise_floor_dbfs")
    f0_std = metrics.get("f0_std_semitones")
    voiced = float(metrics.get("voiced_fraction") or 0.0)

    # 1. Bandwidth. TTS/vocoder output is synthesized at a low sample rate.
    if bandwidth and bandwidth < _NARROW_BAND_HZ and hf8 < _NARROW_HF_SHARE:
        _signal(signals, "band_limited", "Band-limited spectrum", round(bandwidth, 1), 18,
                f"99% of the energy ends at {_fmt_hz(bandwidth)} with only "
                f"{hf8 * 100:.2f}% above 8 kHz - typical of vocoder/TTS synthesis "
                f"(48 kHz source material would keep energy there).")
    elif bandwidth and bandwidth < _MID_BAND_HZ and hf8 < _MID_HF_SHARE:
        _signal(signals, "band_limited", "Band-limited spectrum", round(bandwidth, 1), 10,
                f"99% of the energy ends at {_fmt_hz(bandwidth)} with "
                f"{hf8 * 100:.2f}% above 8 kHz - a synthesis/codec-style ceiling, "
                f"though lossy encoding can also do this.")

    # 2. Hard low-pass edge rather than natural rolloff.
    if edge >= _EDGE_RATIO_STRONG and bandwidth and bandwidth < _EDGE_MAX_BAND_HZ:
        _signal(signals, "lowpass_edge", "Hard low-pass cliff", round(edge, 1), 12,
                f"Energy just below the {_fmt_hz(bandwidth)} edge is {edge:.0f}x the "
                f"energy just above it - a synthesis/codec cliff, not a room "
                f"rolloff.")

    # 3. Digital-silence gaps.
    if digital_silence >= _SILENCE_SHARE_STRONG:
        _signal(signals, "digital_silence", "Digital-silence gaps",
                round(digital_silence, 4), 16,
                f"{digital_silence * 100:.0f}% of frames are below -70 dBFS. A "
                f"microphone always records room tone/breath between words; exact "
                f"zeros are a rendered-file signature.")
    elif digital_silence >= _SILENCE_SHARE_WEAK:
        _signal(signals, "digital_silence", "Digital-silence gaps",
                round(digital_silence, 4), 8,
                f"{digital_silence * 100:.0f}% of frames are below -70 dBFS - some "
                f"silence is gated rather than recorded.")

    # 4. Flattened pitch track.
    if f0_std is not None and voiced >= 0.35:
        if float(f0_std) < _MONOTONE_STD_STRONG:
            _signal(signals, "flat_pitch", "Flattened pitch contour",
                    round(float(f0_std), 2), 16,
                    f"Pitch varies only {float(f0_std):.2f} semitones over "
                    f"{voiced * 100:.0f}% voiced frames - delivery flatter than "
                    f"expressive human speech, which often swings several semitones.")
        elif float(f0_std) < _MONOTONE_STD_WEAK:
            _signal(signals, "flat_pitch", "Narrow pitch contour",
                    round(float(f0_std), 2), 8,
                    f"Pitch varies {float(f0_std):.2f} semitones - on the flat side "
                    f"for spontaneous speech, but not conclusive.")

    # 5. Implausibly low noise floor for a microphone recording.
    if noise_floor is not None and float(noise_floor) <= _LOW_FLOOR_DBFS:
        _signal(signals, "low_floor", "No audible room/mic floor",
                round(float(noise_floor), 1), 10,
                f"The quietest frames sit at {float(noise_floor):.1f} dBFS - below "
                f"what a microphone in a real room records.")

    # Human-sounding countersignals.
    if bandwidth >= _WIDEBAND_HZ and hf8 >= _WIDEBAND_HF_SHARE:
        _signal(signals, "wideband", "Full-bandwidth audio", round(bandwidth, 1), -14,
                f"Energy extends to {_fmt_hz(bandwidth)} with {hf8 * 100:.1f}% above "
                f"8 kHz - consistent with microphone capture.")
    if f0_std is not None and float(f0_std) >= _EXPRESSIVE_STD:
        _signal(signals, "expressive_pitch", "Expressive pitch range",
                round(float(f0_std), 2), -14,
                f"Pitch swings {float(f0_std):.2f} semitones - natural prosody, and "
                f"evidence against a flat synthesized delivery.")
    if (noise_floor is not None
            and -60.0 < float(noise_floor) < -30.0
            and digital_silence < _SILENCE_SHARE_WEAK):
        _signal(signals, "natural_floor", "Audible recording floor",
                round(float(noise_floor), 1), -8,
                f"A stable {float(noise_floor):.1f} dBFS floor runs through the "
                f"gaps - room tone/breath, i.e. a real recording.")

    positive = sum(1 for s in signals if s["contribution"] > 0)
    score = int(round(max(2.0, min(98.0, _BASE_SCORE + sum(
        s["contribution"] for s in signals)))))
    synthetic_evidence = sum(s["contribution"] for s in signals if s["contribution"] > 0)
    human_evidence = -sum(s["contribution"] for s in signals if s["contribution"] < 0)

    if positive >= 3 and duration >= 3.0:
        confidence = "HIGH"
    elif positive >= 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    notes.append(
        f"Voice verdict from {len(signals)} signal(s) over {duration:.1f} s of "
        f"speech: synthetic evidence +{synthetic_evidence:.0f}, human evidence "
        f"-{human_evidence:.0f}, base {_BASE_SCORE:.0f} -> {score}/100 "
        f"({_label(score)})."
    )
    for s in signals:
        notes.append(
            f"{'+' if s['contribution'] > 0 else ''}{s['contribution']:.0f} "
            f"{s['label']}: {s['detail']}"
        )
    notes.append(
        "This layer is an evidence-weighted heuristic, not a trained "
        "speaker/TTS classifier, and it is not yet calibrated on a real-vs-TTS "
        "corpus: treat the score as a documented lead, not proof."
    )

    return {
        "score": score,
        "label": _label(score),
        "tier": _tier(score),
        "confidence": confidence,
        "active": True,
        "kind": "speech",
        "has_speech": True,
        "duration_s": round(duration, 2),
        "signals": signals,
        "metrics": {
            "bandwidth_hz_99": bandwidth or None,
            "hf_share_8k": hf8,
            "lowpass_edge_ratio": edge,
            "digital_silence_fraction": digital_silence,
            "noise_floor_dbfs": noise_floor,
            "f0_median_hz": metrics.get("f0_median_hz"),
            "f0_std_semitones": f0_std,
            "f0_range_semitones": metrics.get("f0_range_semitones"),
            "voiced_fraction": voiced,
            "speech_band_share": metrics.get("speech_band_share"),
            "syllabic_energy_share": metrics.get("syllabic_energy_share"),
        },
        "reasons": notes,
    }


def analyze_voice(
    audio_bytes: Optional[bytes],
    max_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Full voice-detection entry point for audio bytes (any container).

    ``audio_bytes`` may be an audio file or a video file - ffmpeg extracts the
    first audio stream, so "listen to the voice in this video" is the same
    call. Returns a verdict dict; abstains (``score: null``) when there is no
    decodable audio, no speech, or the layer is disabled.
    """
    if not VOICE_DETECTION:
        return _abstain("Voice detection disabled (VOICE_DETECTION=0).")

    track, reason = _audio.extract_audio_detailed(audio_bytes, max_seconds=max_seconds)
    if track is None:
        return _abstain(reason or "No decodable audio track.")

    try:
        layer = _audio.analyze_track(track)
    except Exception as e:  # noqa: BLE001 - measurement failure must not 500
        return _abstain(f"Voice analysis failed while measuring the track ({e}).")

    verdict = score_layer(layer)
    # Keep the layer's own measurement lines (speech/non-speech estimate,
    # bandwidth notes) alongside the voice score's signal lines.
    verdict["reasons"] = list(layer.get("reasons", []) or []) + list(verdict.get("reasons", []) or [])
    if verdict.get("metrics"):
        verdict["metrics"] = {**layer.get("metrics", {}), **verdict["metrics"]}
    return verdict
