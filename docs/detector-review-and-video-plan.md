# RINSE Detector — Codebase Review & Video Improvement Plan

> Review date 2026-10-12. Scope: `server.py`, `forensics/*`, `storyscope/*`,
> `tests/`, `scripts/`. Text and image are in good shape; video is the weak
> modality and this document is weighted to fixing it.

## Implementation log (2026-10-12) — first slice shipped

### IMAGE — `verify` end-to-end via `scripts/eval_local.py --compare`
- **Fixed the frequency-layer GAN-grid rule (`forensics/frequency.py`).**
  `grid_peak_energy` averaged the > 3-sigma tail of the log-spectrum, which is a
  heavy-tail artifact of *any* image: measured it read **9.0-12.0 for every real
  photo AND every AI asset alike**, so the 4.5 threshold fired on everything and
  pushed real photos into the voter's `strongest >= 70 -> 62` escalation floor.
  Root cause is not JPEG — PNG roundtrip, blur and downscale all keep `grid ~ 9.8`,
  and a blurred real photo still scored 96. Real separation exists only at an
  extreme sigma.
  - New metric: count-gated spikes above **6 sigma**, requiring **>= 8** of them
    (constants `_GRID_SPIKE_SIGMA`, `_GRID_SPIKE_MIN_COUNT`). Measured: corpus
    max ring z is 3.0-4.1 with **zero** pixels > 5 sigma; a synthetic checkerboard
    reaches **max z 62.9** with ~0.027% of ring pixels > 8 sigma.
  - Result: corpus `grid` = 0.0 for every image; synthetic checkerboard still
    scores 96. **Real photos moved 62 UNCERTAIN -> AUTHENTIC_HUMAN (12-38); AI
    renders held at 70 SUSPICIOUS (fortnite, guardian) and the collage poster at
    92 SYNTHETIC_AI.** Net: real-image false positives eliminated, AI stills
    recall preserved.
  - Tradeoff (honest): single frames extracted from *photorealistic* AI reels
    (`reel*_frame.jpg`, corpus extras, not asserted) fell 62 UNCERTAIN ->
    AUTHENTIC/INCONCLUSIVE. Their old 62 was the same broken rule, so this is the
    known photoreal-still gap being exposed, not a lost detection — the fix path
    remains CLIP-OOD (original Phase 3b).
- **Fixed the latent `Optional` import in `forensics/c2pa.py`** (would be an
  import-time `NameError` on Python < 3.14).

### VIDEO
- **`forensics/voter.py`: the temporal-residual layer (`tr`) is now an EXPLICIT
  metrics-only layer** (`METRICS_ONLY_LAYERS` filter) instead of an accidental
  silent weight-lookup drop. Behavior unchanged (it never voted); the intent is
  now robust and documented.
- **`forensics/pwtf.py` + `forensics/temporal.py`: resolution is now
  `TEMPORAL_RES`-configurable; the DEFAULT STAYS 128.** This is a deliberate
  anti-change backed by measurement: raising to 256 on the local clips did **not**
  help and actively hurt — a real clip whose p05 floor held at 0.51 (128) and 0.48
  (192) **collapsed to 0.00 at 256**, flipping a real video into a full
  coherence-collapse false positive. Higher resolution pulls in per-pixel
  sensor/compression noise that decorrelates the 5th-percentile coherence. The
  plan's earlier "raise res = biggest win" assumption (B1) is **falsified on this
  sample**; any future bump needs a real-reel corpus + a grain/noise
  compensation step.
- **`forensics/rppg.py`: face gates are now `RPPG_*`-configurable; DEFAULTS
  UNCHANGED.** Measured: a real 900x720 clip with faces detected at 67-92px /
  conf 0.72-0.88 is rejected only by the 0.04 area-fraction gate (~0.0095 of the
  frame), so on landscape video the gate demands a very large face. Loosening it
  was NOT done because the analysis window is one shot window (32 frames ~= 1.3s
  at 24fps) while a cardiac estimate needs several seconds — the real fix is a
  longer dedicated rPPG window, not a looser gate.

### VIDEO — P1 SHIPPED: promote `tr` to a guarded vote (2026-10-12)
- **`forensics/voter.py`:** the temporal-residual layer (`tr`) is promoted from
  metrics-only to a **guarded vote** behind the `TR_VOTE` env flag (default ON).
  It joins the weighted average at weight 0.10 and can escalate to the
  SUSPICIOUS band, but temporal-only evidence is **capped at 79** so it can never
  reach SYNTHETIC_AI on its own; a corroborating spatial layer (>= 70) raises the
  floor to 79, no support floors to 69. `tr >= 60` also counts as decisive for
  the 55-68 tier band (like `total_collapse`). Set `TR_VOTE=0` to disable.
- **Measured effect (case-study clips, raw pipeline, cache bypassed):**
  `DeT-QbTIUSB` **20 AUTHENTIC_HUMAN -> 69 SUSPICIOUS**, `DeAzNILRS_m`
  **14 AUTHENTIC_HUMAN -> 69 SUSPICIOUS**. Local clips unchanged (vid1 66
  SUSPICIOUS, vid2/3 15 AUTHENTIC_HUMAN); all 22 corpus images unchanged;
  `scripts/smoke_cache.py` passes; forced cache entries intact.
- **Honest caveat:** the separation is measured on only 2 AI + 3 local clips.
  `TR_VOTE` exists precisely so this can be disabled until the expanded
  real-reel corpus confirms the `temporal_residual.py` thresholds
  (`_RESIDUAL_ENERGY_HIGH=0.018`, `_RESIDUAL_WHITE_FRAC=0.45`).

### Harness
- Added **`scripts/eval_local.py`** — a network-free, in-process (Flask test
  client) before/after gate over `tests/calibration_corpus/` and `test videos/`.
  This is the local stand-in until the Phase-0 remote corpus lands.
- **`scripts/smoke_cache.py` now runs against an isolated temp DB**
  (`SCAN_CACHE_DIR`) — it calls `cache_clear()` by design and previously wiped
  the real `cache/scan_cache.db` (including forced verdicts). It asserts the
  isolation before touching anything.

**Verification:** baseline `/tmp/rinse_before.json` vs after `/tmp/rinse_after.json`:
19 image verdicts changed (all in the intended direction), 0 video verdicts
changed, AI stills recall preserved. Modules import cleanly; `WORK_RES`/`
`TEMPORAL_RES` both read 128 by default.

## 0. How the system is wired (one paragraph)

`server.py` (Flask, port 5001) exposes `/predict` (auto-routes image vs video),
`/predict/image/fast`, `/predict/image/deep`, `/predict/video/deep`, and the
storyscope/text endpoints. Images fuse up to six layers (synthid, c2pa,
metadata, frequency, neural, spai) plus a color-structure pixel-forensics
signature; video fuses those same spatial layers (run on the first + strongest-
pwtf window's middle frame) with temporal layers (pwtf, temporal, d3, rppg) over
contiguous native-fps shot windows. Everything lands in `forensics/voter.py`,
which does weighted fusion, hard overrides, escalation guards, confidence
tiers, and a two-axis `alteration` / `ai_artifact` output. A SQLite
`scan_cache` (exact sha256 + near-dup dHash) wraps all scan paths.

---

## 1. Strengths

### 1.1 Cross-cutting (all modalities)
- **Calibration discipline is the strongest asset in the repo.** Almost every
  layer docstring records the measured corpus result that justified its
  threshold, and several explicitly document *retired* rules that
  anti-correlated on real social footage (pwtf entropy/hf-share, frequency
  grid-peaks on video, D3 pixel-space voting, flat-render vote on video). This
  "calibrated or it doesn't ship" culture is rare and is the main thing keeping
  false positives down.
- **Honest abstention everywhere.** Layers return `score=None` instead of a
  fabricated number when they cannot validly run (no frame interval, no face,
  model missing, non-contiguous frames). The voter refuses to emit
  `AUTHENTIC_HUMAN` on a spatial-only video scan (`temporal_ran` guard), and
  rPPG returns not-applicable rather than a fake pulse. This is exactly right
  for a consumer-facing detector.
- **Provenance vs pixel-evidence separation.** `ai_metadata.py` and the voter
  keep "the caption names a generator" (provenance) distinct from "the pixels
  are synthetic" (forensics), and never let page prose alone produce a
  synthetic-band verdict. Two-axis `alteration` vs `ai_artifact` output is a
  genuinely useful product distinction.
- **Robust ingestion.** yt-dlp resolution with layered format selectors,
  bot-wall detection + browser-cookie fallback, shot-boundary detection,
  memory-safe streaming decode, and a working exact + near-dup cache. The
  failure taxonomy (`botwall`/`auth`/`gone`/`format`/`transient`) with
  actionable advice is good.
- **Kill switches and guards.** `include_grid_peaks=False` on video,
  `allow_flat_render_vote=False` on video, the video `weights_floor`
  temporal-only cap, the `total_collapse` structural floor — each isolates a
  known measured failure mode.

### 1.2 Text (StoryScope) — strongest modality
- Trained 304-feature narrative classifier (paper-derived) with a
  **dependency-free pure-Python XGBoost scorer** validated to 1e-9 against the
  native library. No libxgboost/OpenMP needed — big deployment win.
- **Honest accuracy reporting**: heuristic mode is documented as retaining
  ~60–95% of LLM-mode accuracy, probability is dampened toward 50% in
  heuristic mode so borderline verdicts don't look certain, and the README
  states "fast screening signal, not research-grade."
- A second, independent zero-shot engine (DNA-DetectLLM mutation-repair) for
  short texts below the 80-char StoryScope minimum.

### 1.3 Images — good, with a real remaining gap
- Six complementary layers with hard overrides only from genuinely hard
  evidence (in-file SynthID/C2PA metadata, not the uncalibrated spectral
  probe).
- **Structural color-structure signatures** (`_pixel_forensics_img`): the
  saturated 3/3, muted 4/4, and tile-uniformity collage signatures are the
  best example in the repo of hand-built, calibrated, explainable rules that
  catch a class the trained CNNSpot model structurally misses (stylized
  toon/3D renders like meme characters). The `pf_strong` voter floor correctly
  converts them into the suspicious band without overreaching into synthetic.
- Neural layer degrades gracefully: without DetectZoo weights it reports
  inactive rather than scoring every dark-background frame at 98% (the old
  bug).

---

## 2. Weaknesses

### 2.1 Video (the priority) — root causes
1. **Temporal resolution starvation.** Both temporal layers run at
   **128×128 grayscale BILINEAR** (`pwtf.py` `WORK_RES=128`, `temporal.py`
   thumb 128²). The high-frequency per-pixel temporal artifacts PwTF-DVD
   targets are largely destroyed at that resolution — we run an ICCV-2025
   detector far below its operating point.
2. **One or two spatial frames per video.** Even after the Phase-1.5 fix,
   spatial layers run on at most 2 frames (first window + strongest-pwtf
   window middle frame). A single frame is a coin flip for the neural layer;
   a regenerated face in an unselected window is invisible to every spatial
   layer.
3. **The temporal layer that could generalize is dropped.** `temporal.py`
   fires only at `jitter_index > 0.40` — a top-decile outlier gate that real
   motion rarely crosses and smooth full-scene generation often doesn't
   either. `pwtf` only escalates on a *coherence-floor collapse* (p05), which
   is the **partial-regeneration** signature. **Full-scene generation that is
   temporally self-consistent (the hardest and increasingly common class) has
   no voting layer at all.**
4. **Two computed layers are dead weight.** `forensics/temporal_residual.py`
   (`tr`) is threaded into the fusion dict but has **no weight in
   `voter.weights`**, so it is silently filtered out — it can never vote.
   D3 and trajectory are metrics-only *by design* and correctly documented as
   needing semantic-encoder features. Net: a lot of temporal code computes
   numbers that don't influence the verdict.
5. **rPPG is gated out exactly when it matters.** On the reels we tested it
   returned `face_too_small`. Its own gates (`_FACE_MIN_SIZE_PX=48`,
   `_FACE_MIN_SIZE_FRAC=0.04`, `_FACE_CONFIDENCE=0.40`) exclude precisely the
   off-axis / small-face talking-head deepfakes that are the common social
   case. rPPG is also weight 0.05 and capped at 60, so even when it fires it
   barely moves the needle.
6. **Metadata dependency for the "pass" cases.** In the last regression the
   AI reels pass largely because of provenance (e.g. reel-03 via a caption
   naming `higgsfield`), not pixel evidence. Strip the caption and the pixel
   recall drops. This is honest but it means the *pixel* detector is weaker
   than the headline 4/4 suggests.
7. **Tiny, non-representative eval set.** `tests/detector_assets.json` has 9
   assets — 5 videos (4 AI + **1** human) and 4 images. There is exactly one
   real video in the whole regression harness. Any video threshold is
   effectively validated against a single negative sample, so the false-
   positive rate is unknown. `tests/calibration_corpus/real` is photos only.
8. **No codec/generation-provenance layer.** Double-compression (social
   re-encode vs fresh upload), encoder/muxer strings, and generator
   frame-rate/resolution conventions are unmodeled — cheap orthogonal signals
   left on the table.
9. **Serial latency.** Decode + spatial + temporal run serially; no
   parallelism, no adaptive "cheap probe first" mode.

### 2.2 Images — remaining gaps
- Photorealistic AI **stills without page context** read ~62 UNCERTAIN (no
  false accusation, but missed). The fix path is a CLIP-OOD / semantic
  classifier, not yet wired.
- The neural layer's real strength depends on DetectZoo weights being
  installed; the ViT patch map is a *relative anomaly* map, not an absolute
  synthetic probability (correctly documented, but easy to misread).
- Generator-level attribution (`generator_hint`) is planned (`docs/generator-
  fingerprints...`) but unimplemented; C2PA is still a keyword grep, not a real
  manifest parse.
- `forensics/c2pa.py` annotates two functions `-> Optional[str]` without
  importing `Optional`. It only imports on Python ≥ 3.14 (lazy annotations);
  on 3.12/3.13 this is an **import-time NameError** that would take down the
  whole forensics stack. Cheap latent bug.

### 2.3 Text
- Both engines are stylometric/statistical; heavy humanization or paraphrasing
  defeats them. This is inherent and honestly disclosed (there's a
  `HUMANIZER_README` and evasion samples — good self-awareness). No structural
  weakness beyond that; text is genuinely the mature modality.

### 2.4 Harness / hygiene
- `tests/` contains only JSON artifacts and image corpora — **no runnable
  Python test files** (`tests/*.py` is empty). Verification lives in
  `scripts/regression_check.py` + `scripts/smoke_cache.py`. The regression JSON
  stores only final score/tier, not the per-layer evidence, which makes a
  failure hard to diagnose without a re-run.
- No CI gating; nothing forces the eval table to be attached to a threshold
  change.

---

## 3. Video improvement plan

Ordered by expected recall gain per unit of effort, with the eval gate first.
Asterisked items are cheap and can land immediately.

### Phase 0 — Build the eval harness FIRST (the gate for everything below)
- Expand `tests/detector_assets.json` to **150+ real + 150+ generated clips**
  with a recompression matrix (720p q-high/low, crop-to-9:16, platform
  watermark burn-in), across Sora/Veo/Kling/Runway/Luma/Pika/Wan + camera
  phone/DSLR. Populate `tests/calibration_corpus/real` with **videos**, not
  just photos.
- Add `forensics/eval_video.py` (follow the `eval_d3.py` pattern): per-layer
  ROC/AP, fused ROC, per-generator breakdown, INCONCLUSIVE rate, latency
  p50/p95. Persist **per-layer evidence** in the regression JSON, not just the
  final score, so failures are diagnosable.
- Rule: no threshold in this plan ships without a before/after table on this
  harness. This is already the repo's stated culture — just not yet enforced by
  CI.

### Phase 1 — Cheap correctness + wiring fixes (days)
- **\*Fix the `forensics/c2pa.py` `Optional` import** (add it to the `typing`
  import). One line; removes a latent import-time crash on Python < 3.14.
- **\*Decide `temporal_residual`'s fate.** Either (a) give `tr` a calibrated
  weight in `voter.weights` and keep it as one more temporal vote, or (b) stop
  threading it into the fusion and label it metrics-only like D3. Right now it
  runs on every window and is silently discarded — the worst of both worlds.
- **\*Raise temporal working resolution** 128 → **256** (config-gated
  `TEMPORAL_RES`; benchmark 192/256/320). 256²×32 float32 ≈ 8 MB/window —
  trivial memory; FFT cost scales linearly in pixels. This is likely the single
  largest recall gain because it restores the artifacts PwTF was designed for.
- **\*Switch temporal resampling BILINEAR → LANCZOS** and re-verify the
  shot-cut probe threshold (keep the 64px probe, which is tuned).
- **\*Add chroma to the temporal stacks** (downsampled Cb/Cr alongside luma):
  generators leave chroma-specific flicker that a luma-only stack cannot see.
  Luma-only fallback for grayscale sources.
- Extend the **rPPG gate** to accept smaller/off-axis faces (lower
  `_FACE_MIN_SIZE_PX`/`_FACE_MIN_SIZE_FRAC`, keep the confidence floor), and
  **raise its weight** so a clean/absent pulse actually contributes. Calibrate
  the new floor on the Phase-0 talking-head negatives.

### Phase 2 — Cover the full-scene-generation gap (the core investment)
The audit's honest conclusion: the current stack targets *partial
regeneration* (coherence-floor collapse). Self-consistent full-scene generation
has no voting layer. Two training-free additions attack this directly:
- **2a `forensics/face_temporal.py` (highest value).** Face-box (MediaPipe/
  OpenCV) → crop native-res face region → per-region PwTF at full face
  resolution → emit the **contrast** `bg_p05 − face_p05`, not absolute face
  coherence. Emit inactive when no face / face < 64px / < 10 frames contain a
  face (full-scene generation may be faceless — don't fabricate a vote).
  Calibrate against talking-head vlogs, the main FP risk. This simultaneously
  fixes the "one spatial frame" blind spot for the most forensically relevant
  region.
- **2b `forensics/codec.py` (cheap, orthogonal).** Double-compression detector
  (P-frame quality ladder / quantization ghosting) + container/muxer audit
  (Lavf/GPU-encoder strings, GOP regularity, known generator resolution/fps
  conventions). Real social video is re-encoded ≥2×; fresh-uploaded AI is
  usually 1×. Report as a **context layer** (small weight, never decisive) and
  monitor per-platform — the signal can invert on platforms that re-encode AI
  uploads.
- **2c Learned temporal layer (B3).** A lightweight temporal transformer /
  3D-CNN over frame-difference stacks at 128–256px, trained on
  DeepfakeBench/GenVideo + collected Sora/Veo/Kling samples vs recompressed
  real, served via ONNX (~1–2 s/window CPU). This is the only thing that
  reliably generalizes to full-scene generation. Start data collection early;
  it is the long pole. Preserve the honesty invariant: never escalates alone.
- **2d Metrics-only probe first for optical flow.** Compute divergence +
  photometric-consistency stats and log them for one cycle **before** granting
  a vote — earn the vote with data (same discipline that retired the pwtf
  entropy rules).

### Phase 3 — Multi-frame spatial voting + fusion
- Run the spatial stack on **5 spread frames per selected window** (10/30/50/
  70/90%), aggregate by median, add `neural_spread` to `extra_data`, cap
  confidence at MEDIUM when spread > 25. Run fingerprint matching on all 5
  frames. Control latency with Phase-4 parallelism and an optional 3-frame
  mode for `/predict`.
- **Recalibrate fusion AFTER** Phases 1–2 change the score distributions
  (logistic confidence calibration + video tier review fit on the expanded
  Phase-0 corpus). Do not recalibrate first.

### Phase 4 — Latency + protocol
- **Parallelize** independent spatial layers with `ThreadPoolExecutor`
  (numpy/torch release the GIL) → ~2–3× wall-clock cut on deep scans.
- **Adaptive mode**: `/predict/video/deep` runs the cheap temporal probe first;
  only runs the expensive spatial+learned stack when the temporal reading is
  ambiguous (30–70).
- **Client-frame protocol v2** (extension): require `frame_interval_seconds` +
  native-res frames + per-frame CRCs so the server can validate contiguity and
  the temporal layers activate on user uploads (today sparse client frames
  abstain → frequent INCONCLUSIVE).

### Phase 5 — Attribution (shared with the image plan)
- Implement the `generator_hint` registry from
  `docs/generator-fingerprints-and-video-overhaul-plan.md` (provenance = hint,
  never a verdict) and replace the C2PA keyword grep with a real manifest
  parse. Lowers the detector's reliance on captions and gives the product a
  "looks like Kling/Veo" line.

---

## 4. Honest projection

| Modality | Now | After Phase 1 | After Phase 2 |
|---|---|---|---|
| Text | mature (statistical ceiling, honestly disclosed) | — | — |
| Image | good; photoreal-without-context misses | + import fix | CLIP-OOD closes photoreal gap |
| Video | partial-regeneration only; full-scene relies on provenance; FP rate unmeasured | res/chroma/rPPG/wiring fixes | full-scene recall via face-temporal + codec + learned temporal |

**The one structural limitation to state plainly:** pixel-level video recall is
weaker than the regression headline, because the "passing" full-scene clips
currently pass on caption provenance. Phase 0 (a real negative corpus) and
Phase 2 (a full-scene voting layer) are what convert video from "works when the
caption confesses" to "works on the pixels."

## 5. Case study — two undetected Instagram videos (2026-10-12)

Two user-known-AI videos (`instagram.com/p/DeT-QbTIUSB/` = deepfake,
`instagram.com/p/DeAzNILRS_m/` = generated) were re-scanned on the **current**
stack with the cache bypassed (raw `_run_video_deep`, `cached=None`). Neither is
detected — both read `AUTHENTIC_HUMAN` (score 20 and 14). The forced cache
entries were confirmed untouched.

Measured evidence (per analyzed window):

| signal | V1 deepfake | V2 generated (win0) | V2 win1 | local real clips |
|---|---|---|---|---|
| pwtf p05 coherence | 0.635 (healthy) | 0.828 | 0.762 | vid2/3 = 0.51 |
| pwtf spectral_flatness | 0.9065 | **0.9898** | 0.8006 | 0.62 |
| pwtf residual_ac1 | 0.390 | **0.177** | 0.721 | 0.81 |
| pwtf score | 12 | 27 | 5 | 5 |
| **temporal-residual (`tr`) score** | **62** | **62** | None | **None (all)** |
| `tr` residual_white_frac | 0.473 | 0.926 | 0.100 | 0.034 / 0.103 |
| face | 181px (2.2% of frame) | none | 114px (1.4%) | — |
| face-crop pwtf | 0.8038 p05, flat 0.995, ac1 0.142 -> 27 | — | — | — |

### Diagnosis
1. **Both are temporally SELF-CONSISTENT** — pwtf's core escalation path
   (coherence-floor collapse, p05 < 0.25) never fires. V1 is a face swap on a
   temporally coherent clip; V2 is a self-consistent full-scene generation.
   This is exactly the "no voting layer for full-scene generation" gap.
2. **The signal that DOES separate them already exists but was deliberately not
   voting.** The temporal-residual probe (`forensics/temporal_residual.py`,
   layer key `tr`) scores **62 on BOTH** missed videos and **None on all real
   local clips**, with `residual_white_frac` 0.47/0.93 (AI) vs 0.03/0.10
   (real). I had registered it as metrics-only (`METRICS_ONLY_LAYERS` in
   `voter.py`) because its thresholds are documented as uncalibrated — but the
   measured separation on this sample is clean.
3. **The pwtf whiteness rule fires but cannot escalate.** V1 (flat 0.91) and
   V2-win0 (flat 0.99, ac1 0.18) hit the whiteness bonus (+15 -> score 27), but
   the voter only escalates pwtf at score >= 60 AND p05 < 0.25. Worthy signal,
   no escalation path.
4. **Face-region temporal gives the deepfake's face a white-residual signature**
   (face-crop flat 0.995 / ac1 0.142 vs full-frame 0.906 / 0.390) but still only
   reaches 27 — the face shows *whiteness*, not collapse.
5. **rPPG is gated out on workable faces**: V1's face is 181px / 2.2% of frame,
   rejected by the 0.04 area-fraction gate, and a 32-frame window (~1.1s at
   30fps) is too short for a cardiac estimate anyway.

### Detection plan for this class (in order of evidence strength)

- **P1 — Promote `tr` to a calibrated vote (highest ROI; layer already exists).**
  It scores 62 on both missed clips and silent on the real locals. Steps:
  (a) calibrate/re-confirm `_RESIDUAL_ENERGY_HIGH` (0.018) and
  `_RESIDUAL_WHITE_FRAC` (0.45) on an expanded real-reel corpus so `white_frac`
  (a clean 0.03-0.10 real vs 0.47-0.93 AI margin) is the primary gate;
  (b) wire it into `voter.weights` with a modest temporal weight and the SAME
  corroboration guard as pwtf (never escalate alone past the suspicious band);
  (c) regression-gate on the remote corpus. Expected: both clips -> SUSPICIOUS+.
- **P2 — Add a whiteness escalation path to pwtf/voter.** flat >= 0.85 AND
  ac1 <= 0.20 (independent per-pixel temporal noise = semi-independent frame
  synthesis) is the full-scene-generation analog of the coherence collapse.
  Escalate to the suspicious band only when corroborated (>= 1 spatial layer
  OR `tr` agreeing). Catches V2-win0 without touching p05.
- **P3 — Face-region temporal layer (`face_temporal.py`, plan Phase 2a).**
  Native-res face-crop pwtf, emitting the CONTRAST (bg - face) and the face
  whiteness. Required for face-swap deepfakes (V1) where the manipulation is
  localized to the face; abstain when no face.
- **P4 — rPPG: dedicated longer window + relaxed area gate.** A 181px face is
  usable if the layer analyzes several seconds (not one 32-frame window);
  lower `_FACE_MIN_SIZE_FRAC` once a real face-video corpus validates it.
- **P5 — Learned temporal layer / CLIP-OOD (plan Phases 2c/3b).** The general
  fix for self-consistent generation; needs training data, not thresholds.

Honest note: P1-P2 are threshold/implementation work verifiable on the existing
harness; P3-P5 need data collection. The plan does NOT claim these two clips
will be caught by any single change until P1 is measured on an expanded corpus.

## 6. Video STRICT mode (2026-10-12) — recall-first

Goal from the user: "much more strict - not a single AI video should get past."

**Honest framing first:** no statistical detector can guarantee zero AI misses.
It is an open-set problem - a detector is calibrated against the generators and
editing pipelines it has seen; a novel or adversarially-processed clip can
always slip through, and every threshold that raises recall also raises the
false-positive rate on real video. There is no setting that catches literally
every AI clip without also flagging many real ones. What strict mode does is
maximize recall and convert near-misses into explicit "needs review" verdicts.

### What strict mode adds (all behind `VIDEO_STRICT`, default ON)
1. **Whiteness escalation** (`voter.py`): temporally white residuals
   (`spectral_flatness >= 0.85` AND `residual_ac1 <= 0.35`) -> floor 66.
2. **Lowered pwtf gate** (`voter.py`): pwtf >= 45 (was 60) with p05 < 0.35.
3. **Anti-false-authentic floor** (`voter.py`): a video with ANY elevated
   temporal reading (pwtf >= 25, or `tr` fires, or flat >= 0.80 && ac1 <= 0.45)
   is never returned as confident AUTHENTIC_HUMAN - it is at least INCONCLUSIVE.
4. **Lowered temporal-residual gate** (`temporal_residual.py`): strict uses
   energy > 0.014 and white-fraction > 0.30 (was 0.018 / 0.45).
All strict escalations cap at 79, so a weak temporal hint alone never reaches
SYNTHETIC_AI. `VIDEO_STRICT=0` restores the calibrated behavior.

### Measured (2026-10-12, cache bypassed)

| clip | truth | score | tier | tr | tr energy | tr white-frac |
|---|---|---|---|---|---|---|
| DeT-QbTIUSB | AI deepfake | 69 | SUSPICIOUS | 62 | 0.072 | 0.473 |
| DeAzNILRS_m | AI generated | 69 | SUSPICIOUS | 62 | 0.136 | 0.926 |
| DeXOxKHs-Us (3rd reels) | unknown | 69 | SUSPICIOUS | 62 | 0.097 | 0.617 |
| human post DdgYCT5B6mn | REAL | 12 | AUTHENTIC_HUMAN | None | 0.018 | **0.016** |
| local vid2 / vid3 | REAL | 15 | AUTHENTIC_HUMAN | None | 0.022 | **0.103** |
| local vid1 | AI | 66 | SUSPICIOUS | None | 0.011 | 0.034 |

**Key margin:** real clips read `residual_white_frac` 0.016-0.103, AI clips read
0.47-0.93 - the strict 0.30 gate sits in a wide gap on this sample. Note the
human post's residual *energy* (0.018) is ABOVE the strict energy floor, so the
**white-fraction is the load-bearing gate**, not the energy.

**Tradeoff disclosure:** the human post and 15 real photos, plus local vid2/3,
were left correctly un-flagged, and `scripts/eval_local.py` shows **0 verdicts
changed** on the local corpus. But that corpus has only 2-3 real videos. Strict
mode WILL produce false positives on real video that shares these statistics
(high-motion, heavy-compression, low-texture footage); that cost is unmeasured
at scale and is exactly why `VIDEO_STRICT` is a flag, not a hard-coded constant.

### To actually catch *your* specific missed videos
Provide the URLs/files that still slip through. Recall can only be pushed
further by calibrating against real examples; the honest path is
`VIDEO_STRICT` levels + a real-reel corpus, not a promise of zero misses.

## 7. File map

| file | change |
|---|---|
| `forensics/c2pa.py` | Phase 1 import fix |
| `forensics/pwtf.py` / `temporal.py` | Phase 1 res 128→256, LANCZOS, chroma |
| `forensics/voter.py` | Phase 1 `tr` weight decision; Phase 3/5 recalibration |
| `forensics/rppg.py` | Phase 1 smaller/off-axis face gate + weight |
| `forensics/face_temporal.py` | Phase 2a (new) |
| `forensics/codec.py` | Phase 2b (new) |
| `forensics/temporal_learned.py` | Phase 2c (new, ONNX) |
| `server.py` | Phase 3 five-frame spatial; Phase 4 parallelism/adaptive |
| `tests/detector_assets.json`, `tests/calibration_corpus/real/` | Phase 0 corpus (videos) |
| `forensics/eval_video.py` | Phase 0 harness (new) |
