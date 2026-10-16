# RINSE — Audio & Lip-Sync Detection Plan (video)

> Plan date 2026-10-12. Adds two new evidence families to the video stack:
> **A) audio-visual sync / lip-sync** and **B) audio-only synthetic-speech
> detection**. Companion to `docs/detector-review-and-video-plan.md`.
> Environment check: `ffmpeg`, `torch`, `torchaudio`, `transformers`,
> `librosa`, `scipy`, `soundfile`, `mediapipe` are all installed; the pipeline
> currently analyzes **frames only** ("audio is never analyzed", server.py:385).

---

## 0. Reality check first (what lip-sync actually tells you)

A common misconception: "lip-sync detection = AI-video detection." It is not.

- **What AV-sync / lip-sync actually catches:** a mismatch between mouth
  motion and phonemes — i.e. **dubbed / re-dubbed audio** and poorly
  re-enacted faces. It is a *talking-head deepfake* cue.
- **What it does NOT catch:** full-scene generation, faceless clips, or
  modern audio-driven fakes (Wav2Lip-class, talking-head diffusion) whose sync
  is deliberately near-perfect. A perfectly lip-synced fake *passes* a sync
  check.
- **Therefore** sync is a **corroborating** signal, never a standalone verdict,
  and it abstains whenever there is no face or no speech.

Same discipline for audio: **AI-generated audio ≠ AI-generated video.** A real
camera clip with a synthetic voice is "audio-AI", not a deepfake video. The
audio verdict must be a **separate axis**, not a vote that flips the video tier.

Grounding: sync/AV research — AVForensics, AVoiD-DF, LAV-DF, RealForensics,
SyncNet-style AV sync. Audio spoofing SOTA — AASIST (graph-attention),
RawNet2, Wav2Vec2-AASIST, Whisper+AASIST, VoiceWukong (USENIX 2025).

---

## 1. What we can extract (measured applicability)

All five test clips (the two case-study reels + 3 local videos) carry an AAC
audio track, so audio is usable — but Instagram reels are frequently
music-only or voice-over-music, which changes what a "synthetic audio" verdict
means (music generation is a separate, harder problem; speech is the tractable
target).

New inputs per analyzed window:
- **Audio track** (mono 16 kHz PCM via ffmpeg).
- **Face landmarks** (MediaPipe FaceMesh — MediaPipe is already a dependency
  for BlazeFace in `rppg.py`).
- **Mouth-region frames** (already available from the frame windows).

---

## 2. Proposed layers

### 2a. `forensics/audio_track.py` — decode + gate (foundation)
- `extract_audio(video_bytes) -> AudioTrack | None`: ffmpeg to mono 16 kHz
  float32, duration-capped, returns `None` when there is **no audio stream**
  (abstain, never fabricate).
- Emits `has_speech` (rough VAD via energy + zero-crossing periodicity),
  loudness, sample rate, duration.
- Cheap; no model.

### 2b. `forensics/av_sync.py` — lip-sync / AV consistency
- Per frame: FaceMesh mouth landmarks → **MAR** (mouth-aspect-ratio) trajectory.
- Audio: short-time energy / voicing envelope over the same window.
- Metrics (training-free):
  - cross-correlation **peak lag** between MAR and audio envelope;
  - **peak correlation** at best lag;
  - **lag drift** across sub-windows.
- Interpretation (to be calibrated): a *large constant lag* or *near-zero
  correlation* between mouth motion and speech = dubbed/misaligned; a healthy
  buffered lag (~tens of ms) = natural.
- **Extra, stronger cue:** mouth-region *temporal texture* (route the face ROI
  through `pwtf`/`temporal_residual`) — this is plan **P3** and is where
  reenactment actually leaks artifacts, independent of how good the sync is.
- Abstains when: no face, face too small, no speech, or window < N frames.

### 2c. `forensics/audio_deepfake.py` — synthetic-speech detection
Two tiers, mirroring the repo's "training-free first, learned behind a flag"
pattern.

- **Tier 1 — training-free vocoder/spectral cues (ships first, metrics → then
  vote after calibration):**
  - high-frequency energy deficit / **spectral holes** (vocoder bandwidth
    limits, resampling artifacts);
  - **pitch-track discontinuity** (unnatural jumps / over-smooth F0);
  - **formant flatness** and unnatural harmonic-to-noise ratio;
  - **phase incoherence** across the spectrum;
  - unnatural **silence/sibilance** statistics.
  These are classical and calibration-heavy — same discipline as the retired
  image rules: measure on a real-vs-TTS corpus before any votes.
- **Tier 2 — learned (gated, opt-in):** AASIST or Wav2Vec2-AASIST via a bundled
  torch checkpoint (no `onnxruntime` in the venv, so serve with torch/torchaudio
  directly, CPU). Gate on a license review and a corpus AUC target (>= 0.90 on
  held-out TTS+vocoder models, < 5% FP on real speech) before it votes.
- Abstains on music-only / no-speech windows (report `audio_kind: music|speech|none`).

---

## 3. How it fits the fusion (honesty invariants)

- New layers join `fuse_ensemble_verdict` as `audio` and `av_sync` (and the
  face ROI feeds the existing `tr`/`pwtf` path for `lip_texture`).
- **`audio` is a separate axis, not a video-tier vote.** Add
  `audio_ai: {label, score, reasons}` to the response (sibling of
  `alteration` / `ai_artifact`). A synthetic voice on real footage must not
  return a video `SYNTHETIC_AI`.
- `av_sync` may contribute a **small** weight to the video `ai_artifact` axis,
  under the same corroboration guard as `pwtf`/`tr`, capped below the synthetic
  band on its own.
- Everything abstains (`score=None`) when its inputs are absent; the existing
  "never confident AUTHENTIC_HUMAN without temporal evidence" rule extends to
  "…and audio evidence is reported, never silently ignored."
- All new layers ship behind env flags (`AUDIO_VOTE`, `AVSYNC_VOTE`,
  `AUDIO_MODEL`) defaulting OFF until calibrated, like `VIDEO_STRICT`/`TR_VOTE`.

---

## 4. Implementation phases

| phase | deliverable | gate |
|---|---|---|
| A0 | `forensics/audio_track.py` (ffmpeg decode + VAD), report audio metrics in the verdict | ✅ **implemented 2026-10-12** — decodes all corpus clips; honest `None`/abstain when absent; see §6 |
| A1 | `forensics/av_sync.py` (MAR vs envelope correlation, metrics-only) | report metrics for one cycle; no vote |
| A2 | face-ROI temporal (`lip_texture`) via existing `pwtf`/`tr` on cropped mouth region | P3 in the video plan; calibrate on talking heads |
| A3 | `audio_deepfake.py` Tier-1 training-free cues (metrics-only) | build real-vs-TTS corpus; measure separation |
| A4 | Promote A1/A3 to guarded votes behind flags | AUC + FP targets on held-out corpus |
| A5 | Tier-2 learned AASIST/Wav2Vec2 (torch) behind `AUDIO_MODEL` | license review + AUC ≥ 0.90 / FP < 5% |

New corpus needed (`tests/audio_corpus/{real,tts,vocoder}`): real camera
speech, TTS (ElevenLabs/OpenAI/Xtts/Coqui), vocoder re-syntheses, plus
music-only reels as the FP guard.

---

## 5. Risks & honest limitations

| risk | mitigation |
|---|---|
| Music-only / no-speech reels → audio layer inactive | abstain; `audio_kind` reported; don't imply audio proves anything |
| Loudness normalization / platform re-encode destroys vocoder cues | measure on a recompression matrix; treat as corroborator |
| Modern audio-driven fakes sync perfectly | sync is corroborating only; rely on mouth-region texture + audio-tier-2 |
| Synthetic voice on real video misread as deepfake video | strict separation: `audio_ai` axis, never flips the video tier alone |
| Model licensing (AASIST is research-oriented) | gate Tier-2 on license review; keep Tier-1 training-free |
| Compute (ffmpeg + mel + torch) adds latency | run audio concurrently with spatial layers; cap duration; adaptive mode |

**Bottom line:** audio + lip-sync meaningfully raise recall for the
**talking-head** class and add a genuinely independent modality, but they do
**not** give a zero-miss guarantee, and they do not catch full-scene
generation. They are additive corroboration with their own FP budget — to be
calibrated on a corpus, behind flags, exactly like every other layer here.

---

## 6. A0 implementation record (2026-10-12)

**Shipped:** `forensics/audio_track.py` (`extract_audio` / `extract_audio_detailed`
/ `analyze_track` / `analyze_audio_track`), wired into
`server.py::_analyze_video_frames` behind the `AUDIO_TRACK` env flag (default
ON because the layer never votes), plus `scripts/check_audio_track.py` as its
behavioural gate.

**Decisions that differ from the plan text, and why:**

- **48 kHz, not 16 kHz.** The plan's 16 kHz is the future model rate, but at
  16 kHz Nyquist is 8 kHz, which makes every ">8 kHz" measurement
exactly zero. Training-free spectral stats therefore decode at 48 kHz
  (`AUDIO_SAMPLE_RATE`); the model path (A5) can resample to 16 kHz inside the
  model wrapper.
- **Metrics-only, no `audio_ai` axis yet.** The plan proposed the axis up
  front; the repo discipline is *measure first, vote after calibration*, so A0
  ships `score: None` and an `audio` block, exactly like `d3` and the retired
  image rules. The axis arrives in A3/A4 with a corpus behind it.
- **Report in `reasons`, never in `breakdown`.** The audio lines are surfaced
  in the user-visible reason list (audio is never *silently* ignored) but the
  layer is absent from `layers_active`/`breakdown` and contributes 0 weight, so
  it cannot move a score.
- **Link scans now keep the downloaded bytes.** `_load_video_frames` hands the
  resolved container bytes back to `_run_video_deep`
  (`info["_raw_video_bytes"]`, popped before the verdict) purely so the audio
  layer decodes the same download instead of fetching twice. The container
  **metadata** scan still reads only originally-uploaded bytes: a yt-dlp
  download is a remux whose container tags belong to the downloader, not the
  uploader, so scanning it would be false provenance.

**Speech heuristic (training-free, deliberately conservative):** `kind` is
`speech` only when the track has active (non-silent) frames AND the loudness
envelope swings (`envelope_cv` ≥ 0.25) AND its 2–8 Hz modulation share is ≥ 0.20
AND ≥ 10% of spectral energy sits in the 300–3400 Hz speech band. Measured
(`scripts/check_audio_track.py`):

| signal | kind | env_cv | 2–8 Hz share | speech-band share | bandwidth |
|---|---|---|---|---|---|
| speech (local vid1) | `speech` | 0.90 | 0.48 | 0.88 | 5.7 kHz |
| speech (local vid2/vid3, real) | `speech` | 0.99 | 0.47 | 0.57 | 3.2 kHz |
| steady 440 Hz tone | `nonspeech` | 0.01 | 0.41 | 1.00 | 0.5 kHz |
| rhythmic tone (3.5 Hz tremolo) | `nonspeech` | 0.63 | 1.00 | 0.00 | 0.1 kHz |
| pink noise | `nonspeech` | 0.15 | 0.46 | 0.25 | 15.6 kHz |
| digital silence | `silence` | — | — | — | — |
| no audio stream | `unavailable` | — | — | — | — |

Two findings worth keeping: the **envelope coefficient of variation is the
load-bearing gate** (the 2–8 Hz share alone saturates near 0.4–0.5 even for a
pure tone and is not discriminative), and the **speech-band share is what stops
rhythmic music** from reading as speech.

**Case-study reels (URL path, cache bypassed, audio decoded from the download):**

| clip | video verdict | audio kind | bandwidth (99%) | >8 kHz |
|---|---|---|---|---|
| `DeT-QbTIUSB` (user: deepfake) | 69 SUSPICIOUS | speech | 2.9 kHz | 0.06% |
| `DeAzNILRS_m` (user: generated) | 69 SUSPICIOUS | speech | 1.4 kHz | 0.01% |
| `DeXOxKHs-Us` (third reel) | 69 SUSPICIOUS | nonspeech | 6.3 kHz | 0.31% |
| `DdgYCT5B6mn` (known real) | 12 AUTHENTIC | nonspeech | 5.9 kHz | 0.41% |

**The narrow-band lead is weak — do not promote it as-is.** Two AI clips read
1.4–2.9 kHz against 5.9–6.3 kHz for the real reels, which is the original lead;
but the **real** local clip reads 3.2 kHz, inside the AI range. Bandwidth alone
therefore has no usable threshold on 4 clips, and platform re-encoding plus the
music/speech difference confound it further. It stays a reported metric.

**Verification (all green):** `scripts/eval_local.py --compare` → **0 of 25
verdicts changed** (22 calibration images + 3 local videos) before vs. after;
`scripts/smoke_cache.py` passes against an isolated temp DB;
`scripts/check_audio_track.py` passes; forced cache entries for the two
case-study reels are intact and `pipeline_version()` is unchanged (the layer
adds no vote, so cached verdicts stay valid). `npx tsc -b` passes with the new
`audio` type + readout card in `src/components/Playground.tsx`.

**Next (A1):** `forensics/av_sync.py` — MediaPipe FaceMesh mouth-aspect-ratio
trajectory vs. the audio envelope correlation, metrics-only, abstaining on
no-face / no-speech windows.
