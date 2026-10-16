#!/usr/bin/env python3
"""Behavioural check for the A0 audio layer (forensics/audio_track.py).

The audio layer ships as a METRICS-ONLY reporter (docs/audio-and-lip-sync-plan.md
phase A0): it must decode a container's audio track, describe it honestly, and
abstain with a reason when there is nothing to decode. It must never vote.

This script builds synthetic containers with ffmpeg for the cases a real corpus
cannot reliably provide on demand (tone, rhythmic tone, stationary noise,
digital silence, no audio stream) and checks the layer's decisions plus its
no-vote guarantee on the repo's local test videos.

Usage:  .venv/bin/python scripts/check_audio_track.py
Exit 0 when every assertion holds, 1 otherwise. Skips (exit 0) without ffmpeg.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from forensics import audio_track  # noqa: E402

VIDEO_DIR = os.path.join(ROOT, "test videos")
VID_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}

FFMPEG = shutil.which("ffmpeg")
_FAILURES = []


def _fail(msg):
    _FAILURES.append(msg)
    print(f"FAIL {msg}")


def _ok(msg):
    print(f"PASS {msg}")


def _make(path, audio_filter=None):
    """Render a tiny test container, with or without an audio stream."""
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=4"]
    cmd += audio_filter or []
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", path]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def _analyze(path):
    with open(path, "rb") as f:
        return audio_track.analyze_audio_track(f.read())


def _expect(label, result, *, active, kind, has_speech=None):
    ok = result.get("active") is active and result.get("kind") == kind
    if result.get("score") is not None:
        ok = False
    if has_speech is not None and result.get("has_speech") is not has_speech:
        ok = False
    # Every value must survive a JSON round-trip (the verdict is serialized).
    try:
        json.dumps(result)
    except (TypeError, ValueError) as e:
        ok = False
        _fail(f"{label}: not JSON-serializable ({e})")
    if not result.get("reasons"):
        ok = False
    if ok:
        _ok(f"{label}: active={active} kind={kind} has_speech={result.get('has_speech')} "
            f"score=None")
    else:
        _fail(f"{label}: expected active={active} kind={kind}"
              + ("" if has_speech is None else f" has_speech={has_speech}")
              + f", got active={result.get('active')} kind={result.get('kind')} "
                f"has_speech={result.get('has_speech')} score={result.get('score')}")


def main():
    if not FFMPEG:
        print("SKIP: ffmpeg not available, cannot build synthetic audio fixtures.")
        return 0
    if not audio_track.AUDIO_TRACK:
        print("SKIP: AUDIO_TRACK=0 disables the layer.")
        return 0

    tmp = tempfile.mkdtemp(prefix="rinse_audio_check_")
    try:
        no_audio = os.path.join(tmp, "noaudio.mp4")
        _make(no_audio, ["-an"])
        _expect("no audio stream", _analyze(no_audio), active=False, kind="unavailable")

        silence = os.path.join(tmp, "silence.mp4")
        _make(silence, ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-c:a", "aac"])
        _expect("digital silence", _analyze(silence), active=True, kind="silence",
                has_speech=False)

        tone = os.path.join(tmp, "tone.mp4")
        _make(tone, ["-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:a", "aac"])
        _expect("steady tone (steady envelope)", _analyze(tone), active=True,
                kind="nonspeech", has_speech=False)

        # A rhythmic but harmonically empty tone: strong 2-8 Hz envelope
        # modulation (it looks "syllabic") with no speech-band energy. This is
        # the case that keeps the heuristic from calling rhythm speech.
        beat = os.path.join(tmp, "rhythmic_tone.mp4")
        _make(beat, ["-f", "lavfi", "-i", "sine=frequency=110:duration=4",
                     "-af", "tremolo=f=3.5:d=0.95", "-c:a", "aac"])
        _expect("rhythmic tone (rhythm without speech band)", _analyze(beat),
                active=True, kind="nonspeech", has_speech=False)

        noise = os.path.join(tmp, "noise.mp4")
        _make(noise, ["-f", "lavfi", "-i", "anoisesrc=d=4:c=pink:r=48000", "-c:a", "aac"])
        _expect("stationary noise", _analyze(noise), active=True, kind="nonspeech",
                has_speech=False)

        # Real clips from the local corpus: whatever their content, the layer
        # must produce a reading (never crash, never vote) from real container
        # audio; and it must stay silent on the no-vote guarantee.
        checked = 0
        for name in sorted(os.listdir(VIDEO_DIR)) if os.path.isdir(VIDEO_DIR) else []:
            if os.path.splitext(name)[1].lower() not in VID_EXTS:
                continue
            res = _analyze(os.path.join(VIDEO_DIR, name))
            if res.get("score") is not None:
                _fail(f"{name}: audio layer returned a score ({res.get('score')}) "
                      f"- it is metrics-only and must never vote")
            elif not res.get("active"):
                _ok(f"{name}: abstained honestly ({res.get('reasons', [''])[0][:60]}...)")
            else:
                m = res.get("metrics") or {}
                _ok(f"{name}: kind={res.get('kind')} envelope_cv={m.get('envelope_cv')} "
                    f"bandwidth={m.get('bandwidth_hz_99')}Hz score=None")
            checked += 1
        if checked == 0:
            print("NOTE: no local test videos found; synthetic fixtures only.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} AUDIO LAYER CHECK(S) FAILED")
        return 1
    print("ALL AUDIO LAYER CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
