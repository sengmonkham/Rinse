# RINSE — Deepfake Video Detection: Revised Improvement Plan

> **Revision 2 (2026-09-27).** Supersedes the earlier draft. Every Phase-1
> threshold in that draft was designed without the measured temporal metrics
> of the failing assets. This revision is grounded in a per-window audit
> (`scripts/regression_check.py --audit`, now persisted to
> `tests/last_regression_results.json`) of all four known-AI reels plus the
> player's actual scoring code. Several original items were invalidated by
> the data; the ones that survived are re-sequenced and re-scoped.

## 0. Measured evidence (the audit the first plan lacked)

Full-resolution key metrics from `forensics/pwtf.py` on the winning shot
window (strongest pwtf evidence wins; `p05` = coherence floor
`coherence_p05`, `ac1` = `residual_ac1`, `flat` = `spectral_flatness`):

| asset | verdict | windows pwtf (p05) | p05 | ac1 | flat | hotspot frac/cluster |
|---|---|---|---|---|---|---|
| ig-ai-reel-01 | 32 AUTHENTIC_HUMAN **FAIL** | 54 (0.00) | **0.00** | **0.855** | 0.56 | 0.43 / 0.99 |
| ig-ai-reel-02 | 66 SUSPICIOUS PASS | 62 (0.00) | 0.00 | 0.697 | 0.80 | 0.25 / 0.99 |
| ig-ai-reel-03 | 17 AUTHENTIC_HUMAN **FAIL** | 12, 12, 5 (0.67/0.71/0.70) | **0.67** | 0.560 | 0.90 | 0.39 / 0.99 |
| ig-ai-reel-04 | 66 SUSPICIOUS PASS | 62, 44, 44 (all 0.00) | 0.00 | 0.539 | 0.89 | 0.42 / 1.00 |

What this proves, contra the first plan:

1. **reel-01's failure is NOT a voter-threshold problem (item 1a is moot).**
   Its coherence floor is *fully collapsed* (p05 = 0.00) — the paper's core
   regeneration signature. The pwtf scorer correctly noticed (+40 for
   p05 < 0.20, +10 hotspots → 62) but then **subtracted 8** because
   `residual_ac1 = 0.855 > 0.70` hit the "structured residuals are evidence
   FOR real footage" rule. 62 → 54 put it below the voter's ≥ 60 escalation
   gate, and the fused verdict collapsed to 32. The -8 authenticity penalty
   and the +40 regeneration signature cannot both be true at once — this is
   a contradictory-evidence bug inside `_score_from_stats`, not a threshold
   to loosen. (Verified in-process: with pwtf = 62 the existing
   `total_collapse` escalation yields **66 SUSPICIOUS**.)
2. **reel-03 is a different, harder failure.** Across all three shot windows
   the coherence floor is healthy (p05 0.67–0.71 — real footage keeps
   ≥ 0.31) and temporal_flatness 0.90 with ac1 0.56. The clip is fully
   generated but *temporally self-consistent*; the coherence-collapse thesis
   targets partial regeneration, not full-scene generation. No voter
   threshold change can catch it — its fix is new evidence (Phase 2), not
   retuning. Notably its pwtf score is 12 — the layer isn't "silent," it
   actively voted *authentic*.
3. **The plan's 1c weak-consensus rule fires on neither failing reel**
   (reel-01 has one layer ≥ 40; reel-03 has zero). Pure false-positive risk.
4. **1d's premise is wrong:** SPAI/frequency receive the *full-resolution*
   middle frame (`_analyze_video_frames`), not 128px thumbnails; only the
   temporal layers see 128px. And "codec smoothing makes AI frames flatter"
   is backwards — H.264 smooths real video identically (frequency reads a
   flat 35 on everything, which is the codec, not the generator).
5. **1e is already shipped and never targeted the poster.** The muted-band
   signature (sat 0.30–0.50 + banded signals + `pf_strong` voter floor)
   landed 2026-09-27: fortnite/guardian now 70 SUSPICIOUS. The poster is
   sat 0.526 — *above* the original 0.50 gate — and fails because it is a
   dense 15-character collage (1558 colors, edge 0.215). No saturation
   change fixes it; it needs its own collage signature (see Phase 4).
6. **1b is directionally backwards:** lowering the `total_collapse` threshold
   0.10 → 0.08 makes the decisive path *harder* to reach. If anything it
   should rise (data below supports ≤ 0.15), though after fix #1 it matters
   less: reel-01/02/04 all have p05 = 0.00, comfortably under 0.10.

The one structural limitation confirmed as real: **temporal layers analyze
32-frame windows at 128×128 grayscale whole-frame.** Face-region analysis
(Phase 2a) attacks exactly this and remains the highest-value investment.Also noted while auditing: **spatial layers run only on the FIRST window's middle frame** (`if not s1:` guard). With 3 windows, a regenerated face in
window 3 is never seen by any spatial layer. Cheap to fix, real blind spot.
(FIXED 2026-09-27 — Phase 1.5 below.)

## 1. Revised sequence (measure → fix → add evidence → classify)

### Phase 0 — Instrumentation + FP corpus (do first, ~1 day) — UNCHANGED GOAL, EXPANDED
- [x] `--audit` flag in regression_check.py (DONE this revision; persists
      window_details + pwtf_metrics incl. new `residual_ac1`).
- [x] Surface `residual_ac1` in pwtf metrics (DONE; it was computed and
      scored but never exported).
- [ ] Collect **8–10 diverse REAL reels** (high-motion dance, vlog talking
      head, low-light, screen-recorded, heavily re-shared). This is the
      FP guard for every threshold below. Without it, nothing ships.
- [ ] `--audit` already covers it; also record `native_fps` + shot count
      per asset (already in verdict via `_rinse_shot_info`).

### Phase 1 — Correct bug-level fixes in the pwtf scorer + voter (days, code-only)
- **1.1 (replaces 1a) Fix the contradictory-evidence bug in
  `forensics/pwtf.py:_score_from_stats`:** the ac1 > 0.70 → -8
  "structured residuals" penalty must not apply when the coherence floor is
  collapsed (p05 < 0.20). A fully collapsed floor + structured residuals
  means generation *with* persistent detail (stylized/animated generation),
  which is exactly reel-01. Expected: reel-01 32 → 66 SUSPICIOUS (verified
  in-process against the real voter). Guard: only skip the penalty, never
  add a bonus; corpus-verify no real reel regresses.
- **1.2 (replaces 1b) Re-scope `total_collapse`:** after 1.1, keep the
  p05 < 0.10 gate but validate against the Phase-0 real corpus whether 0.15
  is safe; measured AI collapses are 0.00, real floor ≥ 0.31 — the margin
  is huge, so this is a confirm, not a tune.
- **1.3 (replaces 1c) DROP the weak-consensus rule.** Provably does not
  affect either failing asset; adds FP risk on compressed real video.
- **1.4 DROP 1d** (SPAI video mode) — premise contradicted by code.
  Re-evaluate only if Phase-0 audit shows spaI metrics differing between
  real and AI reels (it currently reads 10–20 on *both*).
- **1.5 (new, cheap, real blind spot) Spatial layers per window:** run
  synthid/c2pa/frequency/neural/spai on EVERY window's middle frame (or at
  minimum the strongest-pwtf window), not just the first. Cost: ~4x spatial
  latency on multi-window clips (measure; consider top-2 windows).
  - [x] DONE 2026-09-27, as the top-2 subset: restructured
        `_analyze_video_frames` (server.py) into two passes — temporal layers
        on every window first, then spatial layers on the FIRST window + the
        strongest-pwtf window (dedup when identical; bounded spatial latency,
        measured: no latency regression, reels still 9-14s). Aggregation:
        max for detector-type layers; **c2pa aggregates by claim decisiveness**
        (AI 99 > camera 3 > EXIF 25 > none) because a low c2pa score is an
        authenticity CLAIM, not a miss — a blind max would mask it.
        `window_details` now records `spatial_layers_run` per window.
        Regression after: **7/8** (reels 4/4, human post unchanged at 12
        AUTHENTIC_HUMAN); note reel-03 flipped via caption metadata
        (higgsfield -> metadata 75 -> voter escalation), NOT pixel evidence —
        its full-scene gap still needs Phase 2. Remaining FAIL: the poster
        (Phase 4a).
- **1.6 DROP 1e** — shipped; poster needs Phase 4 instead.

### Phase 2 — New training-free evidence for full-scene generation (the core investment)
- **2a face_temporal.py (KEEP — highest value):** face-box (OpenCV cascade /
  MediaPipe) → crop native-res face region → per-region pwtf →
  face_p05 vs background_p05 contrast. Directly attacks the 128×128
  whole-frame limitation. Design guards the first plan missed:
  - abstain (inactive, weight 0) when no face / face < 64px / < 10 frames
    contain a face — reel-03-style content may be faceless;
  - emit the CONTRAST (bg_p05 − face_p05), not absolute face coherence —
    robust to global codec/motion conditions;
  - calibrate on Phase-0 real reels (talking-head vlogs are the FP risk).
- **2b landmark_drift.py (KEEP, demoted, hard requirement added):** must be
  validated that jitter_signal survives IG H.264 bitrates (sensor-noise
  analog: compression may swamp sub-pixel drift). Ship behind a flag,
  weight 0 until the calibration shows separation on the corpus.
- **2c optical_flow.py (KEEP as metrics-only first):** compute divergence +
  photometric-consistency stats and log them via --audit for one cycle
  BEFORE granting a vote. "Low divergence = real" is physically
  oversimplified (occlusion/rotation/rolling shutter); earn the vote with
  data, like d3 was demoted to metrics-only.
- **2d noise-PSD flatness in frequency.py (KEEP, expectations tempered):**
  sensor noise is largely destroyed at IG bitrates; treat as a secondary
  corroborator, not a primary signal.

### Phase 3 — Neural classifier upgrade (KEEP, re-scoped + licensing gate)
- **3a Xception FF++:** right direction, two flags the first plan missed:
  1. FF++ detects *face manipulation*; full-scene diffusion video
     (reel-03-class) is temporally self-consistent and may not trip it.
     Evaluate on the corpus before trusting the 100% projection.
  2. **FF++ is research-only licensed — a commercial-blocking problem.**
     Gate this item on a license review; otherwise prefer UnivFD (already
     wired in detectzoo, 1.7GB) or a CLIP-OOD approach as the production
     classifier and keep FF++-class models as an internal eval tool.
- **3b CLIP OOD (KEEP):** training-free at inference, ~6KB stats file.
  Validate the real-vs-AI embedding separation ON THE CORPUS before wiring;
  if the distributions overlap on social-media frames, drop it cheaply.

### Phase 4 — Collage/class signatures + regression expansion
- **4a (new, promoted): dense-collage signature** for the poster class
  (1558 colors, edge 0.215, sat 0.526): characterize "many distinct
  character renders packed in a grid" (per-tile palette consistency,
  tile-grid periodicity) vs busy real photos; separate work item.
  - [x] DONE 2026-09-27: the pre-existing 3-axis base gate (sat >= 0.50
        + edge >= 0.17 + colors >= 1100, boost 60) is upgraded to 70 by a
        TILE-UNIFORMITY check (`_collage_tile_stats`, 4x4 grid, 512px):
        every cell of a collage is busy and color-rich alike, a real photo's
        emptiest region collapses. Gates: edge-density CV <= 0.30, emptiest
        tile >= 280 quantized colors, mean tile edge >= 0.15. Corpus margins:
        poster CV 0.22 / c_min 342 vs strawberries CV 0.37 / c_min 197 (the
        closest real challenger misses BOTH tile axes); all other real
        photos CV 0.47-1.78. Boost 70 triggers the pf_strong structural
        floor -> poster 47 INCONCLUSIVE -> 70 SUSPICIOUS HIGH. Full suite
        8/8; no real photo gains any boost (measured across all 11).
- **4b (was 4a) asset expansion:** the JSON shapes proposed are fine; add
  per-asset `notes` and require each new AI asset to state WHICH signal
  should catch it (face_temporal? collage? neural?) so every test is
  diagnosable.
- **4c (was 4b) audit flag:** DONE this revision.

### Phase 5 — Fusion recalibration (KEEP, after evidence exists)
- 5a logistic confidence calibration and 5b video tier review are sensible
  ONLY after Phase 1–2 change the score distributions; recalibrating first
  would just fit today's broken landscape. 5a's coefficients must be fit on
  the expanded corpus (real reels included), not the current 4-reel set.

## 2. Honest projections (revised)

| metric | now | after Phase 1 | after Phase 2a | after Phase 3 |
|---|---|---|---|---|
| AI video recall | 2/4 | **3/4** (reel-01 fix; verified in-process) | 3–4/4 (reel-03 only if face/full-scene evidence bites) | 4/4 possible, not promised |
| real-reel FP | n/a (1 sample) | unchanged expected | MUST be measured on Phase-0 corpus | same |
| AI image recall | 3/4 | unchanged (poster is Phase 4a) | unchanged | unchanged |

Measured update (2026-09-27, after 1.1 + 1.5 shipped): AI reels 4/4 on the
last regression run — but reel-03's pass rides on caption provenance
(metadata 75 from a `higgsfield` source caption), not pixel forensics
(pwtf still 12 with p05 0.67-0.71, temporally self-consistent as audited).
The projection's honest number for pixel-evidence recall remains 3/4 until
Phase 2a lands; treat reel-03's green as resolver-dependent.

Measured update (2026-09-27, after 4a shipped): regression suite 8/8 — AI
images 3/3 as stills (poster via the tile-uniformity collage signature),
AI reels 4/4 (reel-03 still resolver-dependent), human post clean at 12.
Remaining honest gap: photorealistic AI STILLS without page context read
62 UNCERTAIN (no false accusations; fix path is Phase 3b CLIP OOD).

The first plan projected 3/4 after Phase 1 via a rule that (a) targets the
wrong layer, (b) lands in the INCONCLUSIVE band per its own formula, and
(c) misses reel-03 entirely. This revision reaches 3/4 via a verified
scorer bug fix instead, and refuses to promise reel-03 without new evidence.

## 3. Key files (updated)

| file | change |
|---|---|
| forensics/pwtf.py | 1.1 ac1-penalty gate (the reel-01 fix); residual_ac1 export (DONE) |
| forensics/voter.py | 1.2 total_collapse confirm-only; Phase-2 weights later |
| server.py | 1.5 spatial layers per window (DONE 2026-09-27, top-2 subset); wire Phase-2 layers |
| forensics/face_temporal.py | 2a (new) |
| forensics/landmark_drift.py | 2b (new, flag-gated) |
| forensics/optical_flow.py | 2c (new, metrics-only first) |
| forensics/frequency.py | 2d noise PSD |
| forensics/neural.py | 3a/3b (license-gated) |
| tests/detector_assets.json | 4b expansions |
| tests/calibration_corpus/ | real + AI corpus (partially populated) |
| scripts/regression_check.py | --audit (DONE) |
