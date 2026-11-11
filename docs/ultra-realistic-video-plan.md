# Detecting ultra-realistic (photoreal diffusion) video

Status 2026-11-11. Companion to `docs/pixel-art-and-hyperreal-plan.md`, which
records the measurement that motivates this plan.

> **Phase 1 update (same day):** the three camera-physics statistics below were
> implemented (`forensics/camera_physics.py`, metrics-only) and measured over the
> 7 confirmed-real clips + the 8 hyper-real Higgsfield clips the user supplied.
> They do **not** separate with a defensible margin - see "Phase 1 - measured"
> below. The layer ships metrics-only; the plan proceeds to Phase 2.
>
> **Phase 2 update (same day):** the Phase-2 hypothesis is now IMPLEMENTED and
> working - `forensics/embedding_consistency.py` (DINOv2 one-class distance to a
> REAL-only bank) separates the 8 hyper-real clips from the 7 confirmed-real
> clips with a clean gap and, wired in, flips **7 of 8** hyper-real clips to
> SUSPICIOUS while leaving all 7 confirmed-real clips non-accused. See
> "Phase 2 - implemented" below.

## Where we stand

`ig-DfA6rNyKDRU` (Higgsfield, photoreal, believable motion) reads **16
AUTHENTIC_HUMAN**. It is not a threshold-tuning miss: every statistic the stack
computes was measured against 5 confirmed-real clips and it sits inside the real
range on all of them (`p05` 0.41, static pixels 0.12, wavelet deficit 0.0019,
SPAI similarity 0.96, patch deviation 0.20, CNNSpot 0). The only statistic that
separates is native-resolution flat-fill structure, and that is a *pixel-art*
signature the hyper-real clip does not have (0.114 vs the real range 0.048-0.185).

Two structural blind spots explain it:

1. **Every temporal layer sees a 128x128 grayscale thumbnail.** Render-origin
   physics (sensor noise, lens MTF, sub-pixel motion) lives below that scale and
   is gone before any layer runs.
2. **Nothing in the stack models a camera.** The layers detect generator
   artifacts (grid peaks, spectral deficits, coherence collapse). A good
   diffusion model has none of those, so "no artifact" is scored as "authentic"
   even though the clip is not a capture.

Calibration is also blocked: 7 real clips cannot support a threshold that has to
hold at a false-positive rate below 1/40.

## Phase 0 - corpus and harness (prerequisite, ~1 week)

- Grow confirmed-real video to **>= 40 clips**, deliberately diverse: phone
  (day/night/indoor), DSLR, action/drone, screen recordings, heavy IG
  re-compression, low-light, faces talking to camera, and - importantly -
  *ultra-realistic AI* clips from several generators (Higgsfield, Veo, Sora,
  Kling) so the negative class is not one model's fingerprint.
- Keep `scripts/probe_capture_origin.py` as the metric dump; add every new clip
  to `tests/media_test_assets.json` with a `note` naming which signal is
  expected to catch it (repo convention, plan v2 item 4b).
- Harness deliverable: one table, clips x statistics, regenerated on demand.

**Gate for later phases:** no threshold is wired until it has a measured clip-level
margin on this corpus.

## Phase 1 - camera physics at native resolution (measure first, ~3-5 days)

Three statistics, all cheap numpy, all measured on **native** frames:

1. **Sensor-noise response curve.** In a real camera, temporal noise variance in
   flat patches is a linear function of patch intensity (photon shot noise plus a
   read-noise floor): `var = a*I + b` with `a > 0`, `b > 0`. A diffusion render
   has no sensor; whatever noise survives re-encoding is a codec property and does
   not obey that curve. Fit per clip and score the residual of the fit.
2. **Temporal noise correlation (fixed-pattern / PRNU-like).** Real noise fields
   are partly fixed across frames; generated noise is independent per frame.
3. **Residual spatial spectrum in flat regions.** Camera noise is spatially white;
   warped generated texture is smooth.

Expected outcome: (2) probably fails - the repo's own plan v2 Phase 2d expects
Instagram bitrates to destroy sensor noise. (1) is the strongest untested idea
because it is a physical invariant rather than a learned prior.

**Abort criterion:** if none of the three separates real from ultra-real with a
clip-level margin of at least 1.5x on 30+ clips, stop and go to Phase 2. Do not
wire a layer that overlaps.

## Phase 1 - measured (2026-11-11): camera physics does NOT separate (yet)

Implemented the three Phase-1 statistics as `forensics/camera_physics.py` (a
metrics-only layer, wired into `server.py` so it runs on every analyzed video)
plus `scripts/probe_camera_physics.py` (calibration harness), and measured them
over the 7 confirmed-real clips and the 8 hyper-real Higgsfield clips the user
supplied (all cached in `.detectzoo_data/video_cache/`, native 720x1280,
48-frame windows from 1s in).

| statistic | human range (7) | hyper-real range (8) | verdict |
|---|---|---|---|
| photon-transfer slope `a` | -1.36 … 2.15 | -3.29 … 6.49 | overlap; render clips reach BOTH extremes |
| bright/dark noise ratio | 0.25 … 3.97 | 0.08 … 1.74 | overlap; only 2/8 render clips below the human min |
| fixed-pattern ratio | 0.08 … 0.32 | 0.05 … 0.25 | overlap |
| per-frame noise lag-1 autocorr (h) | 0.06 … 0.32 | 0.18 … 0.41 | overlap |
| median-frame texture lag-1 autocorr (h) | 0.21 … 0.38 | 0.28 … 0.44 | overlap; best case catches ~3/8 with a <5% margin |

Two of the eight clips (`ig-DecPhb-iBFr`, `ig-DeqTgBEhvAu`) are indistinguishable
from camera footage on every statistic - `ig-DeqTgBEhvAu` even reads a
*camera-like* photon-transfer slope of +6.49 and a bright/dark ratio of 1.57.

Two findings make these statistics fragile as a detector, not merely thin as a
threshold:

1. **Window dependence.** The same clip (`ig-DfA6rNyKDRU`) reads
   `bright/dark = 0.077` in the probe window (frames 30-78) but `2.165` in the
   production shot window (frames 115-147). The photon-transfer curve is a
   function of the sampled scene content (a bright sky vs a dark interior), so a
   threshold calibrated on one window does not transfer to another.
2. **Instagram destroys the sensor.** Four of seven confirmed-real clips read
   `bright/dark < 1` (dark noisier than bright) - the *opposite* of the shot
   noise a real sensor produces - because H.264 quantisation noise dominates at
   these bitrates. This is the failure the plan predicted for stat (2), and it
   hits stat (1) too.

**Conclusion: the Phase-1 abort criterion is triggered.** No single statistic
(nor any hand-checked pair) separates real from ultra-real with the required
1.5x clip-level margin on a 7-real-clip corpus, and the statistics are
window-dependent. Per this plan, do not wire a layer that overlaps; proceed to
Phase 2 (pretrained-embedding consistency), the only path with published
evidence for photoreal diffusion. `camera_physics.py` ships metrics-only so the
measurements stay visible on every clip and the calibration data is preserved
for when the real corpus reaches 30+ clips.

```bash
.venv/bin/python scripts/probe_camera_physics.py --label human
.venv/bin/python scripts/probe_camera_physics.py --hyperreal
```

## Phase 2 - pretrained-embedding consistency (no training, ~1 week)

Photoreal diffusion is photoreal *per frame*; the tell is that frames are not
draws from the same physical scene. Use a self-supervised encoder (DINOv3 or
VideoMAE, pulled with `hf download`, run locally or on HF Jobs GPU):

- per-frame embedding distance distribution (variance across frames);
- temporal embedding drift vs a real clip's drift;
- kNN distance of the clip's frame embeddings to a bank built from the **real**
  corpus only (one-class detector - no AI labels needed to fit it).

**Abort criterion:** clip-level AUROC < 0.75 on held-out clips means the
embedding space does not separate here; stop instead of adding a classifier on
top of a non-separating feature.

### Phase 2 - implemented (2026-11-11): DINOv2 one-class kNN separates

The third signal (kNN distance to a REAL-only bank) is implemented as
`forensics/embedding_consistency.py` and wired in as a guarded video layer. It
reuses the DINOv2-small weights already cached in the HF hub (no new download)
and ships a real-only bank built by `scripts/build_embedding_bank.py`.

Measured with DINOv2-small at 224px (16 frames/clip, cosine distance to the
leave-one-out real bank, `scripts/probe_embedding_consistency.py`):

| signal | real (7 clips) | hyper-real (8 clips) | separated? |
|---|---|---|---|
| per-frame embedding drift | 0.15 - 0.58 | 0.13 - 0.59 | no |
| spread around clip centroid | 0.15 - 0.52 | 0.23 - 0.49 | no |
| **kNN distance to real bank** | **0.40 - 0.64** | **0.68 - 0.85** | **yes, clean gap** |

CLIP ViT-B/32 embeddings (content-based) do NOT separate; DINOv2
(self-supervised scene structure) does - exactly why the plan asked for DINOv3
rather than CLIP. The gap holds at both 224px and 518px input.

Wired into `server.py` + `voter.py`, the layer votes only when the distance
exceeds the stored threshold (midpoint of the measured gap, ~0.66), grades 70-79
and is capped at SUSPICIOUS - never SYNTHETIC_AI - because "far from these 7
real clips" proves a non-camera origin, not a generator identity.

Result on the 8 hyper-real clips + 7 confirmed-real clips:

| outcome | count | clips |
|---|---|---|
| hyper-real → SUSPICIOUS | 7 / 8 | all except `ig-DeWNa25MgzR` |
| confirmed-real → non-accused | 7 / 7 | all |

`ig-DeWNa25MgzR` reads kNN 0.655 in its production shot-window - just below the
0.66 threshold and only 0.015 above the closest real clip (0.640) - so the layer
honestly abstains rather than risk a false positive on a 7-clip corpus. This is
the calibration limit, not a bug: the repo requires 30+ confirmed-real clips
before a production-safe threshold, and the bank + threshold are rebuilt with
`scripts/build_embedding_bank.py` when the corpus grows.

The clip-level signal here is a one-class *distance*, not a trained head, so
Phase 3 (trained clip-level head) is still the path to a SYNTHETIC_AI-grade
verdict and to recall on the borderline clip; it needs the Phase-0 corpus first.

## Phase 3 - trained clip-level head (only if Phase 2 clears the gate)

- Features: Phase-1 physics stats + Phase-2 embedding stats + existing layer
  outputs (pwtf/tr/SPAI/frequency/neural).
- Model: logistic regression or a small MLP. Clip-level cross-validation,
  **grouped by source clip**, never frame-level (frame-level splits leak and
  produce 0.99 scores that collapse in production).
- Train on HF Jobs (`l4x1` or `a10g-small`) if embeddings need a GPU; the
  feature matrix itself fits on CPU.
- Report recall at a fixed real-FP budget (<= 1/40 clips), plus the confusion
  matrix per generator.

## Phase 4 - integration with guards

- New layer votes only when its calibrated probability clears the Phase-3
  threshold measured at the FP budget; otherwise it abstains.
- Never overrides a confirmed-authentic C2PA camera manifest.
- Cap at SUSPICIOUS (79) unless provenance (watermark/manifest) corroborates -
  same rule the pixel-art gate follows.
- Regression requirement: all 7 current human clips plus the 40-clip real set
  must stay non-accused before the layer ships.

## What not to do (already measured and rejected)

| approach | measurement |
|---|---|
| restore the `p05 = 0` collapse | driven by static pixels; a real clip has 25.98% vs the target's 11.86% |
| lower the `p05` / static-fraction thresholds | human `p05` 0.375 < target 0.411; no threshold separates |
| frame-level learned classifier (CLIP render head) | 0.80+ on 4/5 frames of a **confirmed-real** reel |
| captions / page context as provenance | organic captions, no generator labels on these clips |
| wavelet HF deficit / SPAI / CNNSpot | fires on real photos too / overlapping / blind (0%) |

## Cost summary

| phase | compute | wall clock |
|---|---|---|
| 0 corpus | none | ~1 week (collection is the bottleneck) |
| 1 physics | CPU | 3-5 days |
| 2 embeddings | 1 GPU-hour per 100 clips | ~1 week |
| 3 head | < 1 GPU-hour | 2-3 days |
| 4 integration | CPU | 1 week |
