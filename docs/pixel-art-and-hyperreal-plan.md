# Pixel-art video: fixed. Higgsfield hyper-real: measured, still open.

Status 2026-11-11. Companion to `docs/detector-review-and-video-plan.md`.

## 1. What was actually wrong with the hyper-real clip ("it used to detect it")

It was never caught by pixel evidence. It was caught by a **bug**, and the bug is
why real reels were being falsely accused:

* `forensics/pwtf.py` computes `coherence_p05` over every pixel of a 128px gray
  thumbnail. A pixel with zero temporal variance has an all-zero spectrum, so
  its normalised coherence is exactly 0 — indistinguishable from a maximally
  regenerated pixel.
* The Higgsfield clip `ig-DfA6rNyKDRU` has **11.86%** such pixels, so the old
  code read `p05 = 0.00` → `12 + 40 (p05<0.20) + 10 (hotspot, p05<0.30) = 62`
  → over the voter's `>= 60` gate → SUSPICIOUS.
* A **user-confirmed real** clip, `ig-DaAd4iqhbnj`, has **25.98%** static
  pixels — nearly double. The old code collapsed it to 0.00 as well. That is
  the false accusation the static-pixel guard removed.

Conclusion: the earlier detection is not recoverable evidence. Restoring it
re-accuses confirmed-real footage. With the guard in place the clip reads
`p05 = 0.4111`, `pwtf = 14`, `score = 16 AUTHENTIC_HUMAN`.

## 2. Every pre-existing statistic was measured and rejected for this clip

From the recorded full-corpus run, per-clip (humans = 5 user-confirmed clips):

| signal | human range | hyper-real | verdict |
|---|---|---|---|
| `coherence_p05` | 0.3751–0.7449 | 0.4111 | inside human range |
| `static_pixel_fraction` | 0.0034–0.2598 | 0.1186 | inside, human is higher |
| wavelet HF deficit | 0.0002–0.0045 | 0.0019 | **fires on every real photo** (gate 0.008) |
| SPAI similarity | 0.951–0.974 | 0.961 | inside |
| SPAI heterogeneity | 0.015–0.034 | 0.049 | highest human 0.034, margin too thin |
| patch deviation | 0.08–0.28 | 0.20 | inside |
| CNNSpot | 0 | 0 | blind |
| residual ac1 | 0.540–0.764 | 0.8102 | above all humans, 1 sample |

No threshold on these separates the clip without also flagging a confirmed-real
clip. So the layer stack cannot currently see it, and pretending otherwise would
mean coding a threshold that accuses real footage.

## 3. What was fixed: AI pixel-art video

New layer `forensics/capture_origin.py` — the only layer that works at NATIVE
resolution (everything else sees a 128×128 gray thumbnail, which is exactly what
destroys render-origin evidence). It measures the physics a camera cannot fake:

* a camera has read noise → flat fills are never *exactly* flat;
* a camera has optics → two whole image rows are never byte-identical.

Measured by `scripts/probe_capture_origin.py` on 5 confirmed-real clips + 9 AI
clips (contiguous native-rate window, 48 frames from 1s in):

| statistic | human max | AI pixel-art | ratio |
|---|---|---|---|
| exactly-flat 8×8 blocks | 0.1849 | **0.9368** | 5.1× |
| flat pixels | 0.2954 | **0.9494** | 3.2× |
| identical image rows | 0.0226 | **0.6966** | 30× |

Gate = conjunction of `>= 0.60 / 0.60 / 0.10`, placed in the empty gap above the
human maximum. Output is graded 70–79 and **capped below the synthetic tier**: a
rendered pixel grid proves the frames were *rendered*, not that a generator made
them (hand-made pixel art is also a rendered grid).

Result: `ig-DfhvopJP2Bc` 13 AUTHENTIC_HUMAN → **79 SUSPICIOUS**. It was invisible
to every other layer (pwtf 5, neural 5, SPAI 20, 0/8 residual windows).

Verification (9 assets, in-process): 8 pass, 1 fail (the hyper-real one).
All 5 humans non-accused: 22 / 19 / 22 / 48 / 48.

## 4. Next work for hyper-real / photoreal diffusion (not started)

Ranked by expected value, not by ease:

1. **Video-trained head (the real fix).** Frames + a short temporal window into a
   classifier trained on this corpus. Only path with published evidence for
   photoreal diffusion. Blockers: 7 real clips cannot calibrate anything —
   corpus growth is a prerequisite, and cross-validation must be clip-level (not
   frame-level) or the score is leakage.
2. **Grow the real corpus.** Every threshold in this repo is limited by 7 real
   videos. 30–50 confirmed-real clips (varied lighting/compression/devices)
   would let the existing native-resolution statistics be calibrated instead of
   gated at the widest measured margin.
3. **Native-resolution temporal noise correlation (PRNU-like).** Cheap to
   measure, but the repo's own plan (`docs/video-detection-improvement-plan-v2.md`
   Phase 2d) expects Instagram bitrates to destroy sensor noise. Measure before
   proposing a vote.

## 5. Reproduce

```bash
.venv/bin/python scripts/probe_capture_origin.py --label human          # negatives
.venv/bin/python scripts/probe_capture_origin.py --ids ig-DfhvopJP2Bc,ig-DfA6rNyKDRU
.venv/bin/python tests/test_videos.py --ids ig-DfhvopJP2Bc,ig-DfA6rNyKDRU
```

Downloads are cached in `.detectzoo_data/video_cache/`, so re-runs are free.
