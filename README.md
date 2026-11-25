# RINSE

<img src="animals_1.jpg" height="280" alt="Real photograph: polar bear standing in snow"> <img src="image.png" height="280" alt="Synthetic image: temple courtyard with stone path">

Real photograph → **11 · `AUTHENTIC_HUMAN`** (HIGH) &nbsp;|&nbsp; Synthetic image → **72 · `SUSPICIOUS`** (MEDIUM). Full verdict breakdown: [worked example](#worked-example-one-real-photograph-one-synthetic-image).

RINSE (**R**emove **I**nauthentic **N**oise) is a Flask API server that decides whether text, images and video were produced by a human or by a generative model. It covers the endpoints, the forensic layers, the trained models, how each score is fused, where the evidence for the thresholds came from, and what the detector honestly cannot do.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
# tested pin set (the Dockerfile additionally installs CPU-only torch wheels)
pip install -r requirements-render.txt
python server.py                            # http://localhost:5001
```

`PORT` overrides the port (default `5001`). Set `API_KEY` (or `BEARER_TOKEN`) to require `Authorization: Bearer <key>` on every endpoint; leave it unset for an open local instance. Verify the neural layer actually loaded before trusting any verdict:

```bash
curl -s http://localhost:5001/health | jq '{detectzoo_loaded, mode, layers}'
# "detectzoo_loaded": true   — false means the neural layer fell back to
#                              simulation mode and is not voting for real.
```

Video needs `ffmpeg` on `PATH` (`pip install -U yt-dlp` as well for social links); the optional rPPG layer needs `mediapipe`. Everything else is numpy/PIL/OpenCV.

## Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health`, `/v1/health` | GET | Server identity, uptime, engine mode, `detectzoo_loaded`, `auth_required`, active layers |
| `/predict/image/fast` | POST | Cheap image path (<100 ms): SynthID, C2PA, AI-metadata, frequency forensics |
| `/predict/image/deep`, `/predict`, `/v1/predict` | POST | Full image fusion: every spatial layer + the dataset-trained heads |
| `/predict/video/deep` | POST | Full video fusion: spatial + temporal + pixel-wise temporal frequency + audio axis |
| `/predict/storyscope` | POST | Narrative-structure AI-fiction detection (`{"text": "..."}`) |
| `/predict/text/dna` | POST | DNA-DetectLLM zero-shot AI-text detection (`{"text": "..."}`) |
| `/predict/synthid/probe` | GET/POST | Layer-1 watermark probe in isolation |
| `/cache/stats`, `/cache/clear` | GET/POST | Scan-cache inspection and reset |
| `/scans/stats`, `/scans/recent`, `/scans/export` | GET | Scan-log queries (see [Scan log](#scan-log-every-scan-in-sqlite)) |

Image payloads accept `image_base64` (data URI or bare base64) or `image_url`. Video payloads accept `video_base64`, `video_url` (direct file **or** a social-platform link resolved with yt-dlp), or `frames_base64` with a mandatory `frame_interval_seconds`. Pass `"no_cache": true` to force a fresh computation.

```bash
curl -s -X POST http://localhost:5001/predict/image/deep \
  -H 'Content-Type: application/json' \
  -d "{\"image_base64\": \"$(base64 -i photo.jpg)\", \"no_cache\": true}" | jq '{score, tier, confidence, breakdown}'
```

## Reading a verdict

Every media verdict carries the same shape:

```json
{
  "score": 72,
  "tier": "SUSPICIOUS",
  "confidence": "MEDIUM",
  "short_label": "Has AI artifacts",
  "breakdown": {"frequency": 35, "neural": 5, "spai": 20, "learned": 71},
  "layers_active": ["frequency", "neural", "spai", "learned"],
  "reasons": ["...", "..."],
  "metadata_source": "none"
}
```

`score` is the fused 0–100 probability of AI involvement; `breakdown` is each layer's own 0–100 reading (only layers that actually voted appear in `layers_active` — an abstaining layer is absent, never 0); `reasons` is the human-readable evidence trail.

| Score | Tier | Meaning |
| --- | --- | --- |
| ≥ 80 | `SYNTHETIC_AI` | Multiple corroborating layers, or a hard provenance override (verified watermark / C2PA / generator metadata) |
| 69–79 | `SUSPICIOUS` | Structural evidence found; review the media. 55–68 readings reach this band only with corroboration (or a confirmed collapse) |
| 55–68 | `UNCERTAIN` | Escalated-but-unconfirmed (single layer, one window, layer disagreement) |
| 35–54 | `INCONCLUSIVE` | Nothing decisive either way |
| < 35 | `AUTHENTIC_HUMAN` | No AI evidence. On video this additionally requires the temporal layers to have actually run |

A few rules keep the top band honest: temporal evidence from a 128 px thumbnail can never reach `SYNTHETIC_AI` (cap 79), a photoreal-vs-real classifier reading (an overlapping problem) is capped at `SUSPICIOUS`, and a video with no temporal vote reads `INCONCLUSIVE` rather than `AUTHENTIC_HUMAN` no matter how clean the spatial layers look.

## Worked example: one real photograph, one synthetic image

The two images at the top of this README are in this repository (`animals_1.jpg`, `image.png`) and were submitted to `POST /predict/image/deep` with `"no_cache": true`. Nothing was tuned for them.

| Real photograph | Synthetic image |
| --- | --- |
| `animals_1.jpg` — 1080×720 JPEG, 67 KB | `image.png` — 720×1280 PNG, 1.36 MB |

### Verdicts

| | Real (`animals_1.jpg`) | Synthetic (`image.png`) |
| --- | --- | --- |
| **Score** | **11** | **72** |
| **Tier** | `AUTHENTIC_HUMAN` | `SUSPICIOUS` |
| **Confidence** | `HIGH` | `MEDIUM` |
| **Short label** | No clear alteration or AI artifacts detected | Has AI artifacts |
| Layers active | frequency, neural, spai, learned | frequency, neural, spai, learned |

### What each layer said

| Layer | Real photograph | Synthetic image | Reading |
| --- | --- | --- | --- |
| C2PA / SynthID / metadata | no manifest, no watermark, `metadata_source: none` | identical — no manifest, no watermark | Both are stripped of provenance, so nothing is decided here |
| Frequency forensics | wavelet high-frequency ratio **0.0003** | **0.0043** | Both read as smooth by the wavelet rule, so this layer lands on the same neutral 35 for each — a texture deficit alone does not separate them |
| DetectZoo (CNNSpot) | **0%** | **0%** | The off-the-shelf detector is silent on both — the reason the dataset-trained heads exist |
| ViT patch anomaly map | 0/256 patches inconsistent (mean deviation **0.14**) | 0/256 patches (mean deviation **0.26**) | No localized editing region in either image |
| SPAI spectral analysis | 10% (similarity 0.965, slope −1.56, heterogeneity 0.060) | 20% (similarity 0.971, slope −1.24, heterogeneity **0.041**) | The synthetic image has the unnaturally uniform quadrant spectrum SPAI looks for, but 20% is not a vote on its own |
| Dataset-trained `render` head | 6.0% | 9.1% | Neither is a brainrot-style render |
| Dataset-trained `photoreal` head | **0.3%** | **89.1%** | This is the layer that decided the synthetic image |

### How the fused scores were reached

**Real (11, `AUTHENTIC_HUMAN`, HIGH).** Four independent layers read low and they agree: frequency 35, neural 5, SPAI 10, learned 8. The strongest single signal is the `photoreal` head at 0.3% — the classifier calibrated on modern diffusion output is confident this is camera output, and its held-out operating point has a ~5% false-positive rate at the threshold the layer uses.

**Synthetic (72, `SUSPICIOUS`, MEDIUM).** The `photoreal` head reads **89.1%** AI (breakdown `learned: 71` after the calibrated curve), which independently corroborates SPAI's low spectral heterogeneity (0.041) and the more-than-10× higher wavelet high-frequency deficit. That corroboration lifts the score into the suspicious band — but deliberately no further:

> `"Photoreal-AI classifier: the dataset-trained photoreal head reads 89% AI on this image. … Photoreal-vs-real is an overlapping problem, so it is reported as SUSPICIOUS (review), not as a SYNTHETIC_AI claim."`

The detector is right about the *origin* of this image and honest about its *certainty*: 72/MEDIUM, not 95/HIGH. That gap is the point of the whole layer design — a detectable-but-overlapping signal gets a review flag, and only corroborated or provenance-backed evidence is allowed to accuse.

## Detection stack

| Layer | Module | Media | Votes? |
| --- | --- | --- | --- |
| SynthID watermark probe | `forensics/synthid.py` | image, video | Yes (hard override ≥ 90) |
| C2PA Content Credentials | `forensics/c2pa.py` | image, video | Yes (hard override) |
| AI provenance metadata (container/EXIF/caption/page claims) | `forensics/ai_metadata.py` | image, video | Yes |
| Capture-origin probe (rendered pixel grid) | `forensics/capture_origin.py` | video (native resolution) | Yes |
| Camera-physics probe | `forensics/camera_physics.py` | video (native resolution) | No — metrics only (no separable margin) |
| Frequency forensics (wavelet, spectral slope, GAN grid) | `forensics/frequency.py` | image, video | Yes |
| SPAI spectral learning (Karageorgiou et al., CVPR 2025) | `forensics/spai.py` | image, video | Yes |
| DetectZoo CNNSpot + ViT patch map | `forensics/neural.py` | image, video | Yes |
| Dataset-trained render / photo / photoreal heads | `forensics/learned_image.py` | image only | Yes (capped 79) |
| Embedding consistency (one-class DINOv2 distance) | `forensics/embedding_consistency.py` | video | Yes (capped 79) |
| Temporal coherence (flicker, jitter) | `forensics/temporal.py` | video | Yes |
| PwTF-DVD pixel-wise temporal frequency (ICCV 2025) | `forensics/pwtf.py` | video | Yes |
| Temporal residual (neighbor-mean prediction) | `forensics/temporal_residual.py` | video | Guarded vote (`TR_VOTE`) |
| rPPG pulse consistency | `forensics/rppg.py` | video (faces) | Yes, when a face is found |
| D3 second-order dynamics (ICCV 2025) | `forensics/d3.py` | video | No — metrics only (weight 0.0) |
| Representation trajectory / ReStraV geometry | `forensics/trajectory.py` | video | No — metrics only |
| Audio track analysis | `forensics/audio_track.py` | video | **Never** — separate axis |
| Character fingerprint matching | `forensics/characters.py` | image, video | Feeds the SynthID override |
| StoryScope narrative structure | `storyscope/` | text | Yes |
| DNA-DetectLLM | `storyscope/dna_detect.py` | text | Yes |

### Fusion weights

Each active layer's score is folded into the fused score with a fixed weight (image / video):

| Layer | Image | Video |
| --- | --- | --- |
| `synthid` | 0.25 | 0.25 |
| `c2pa` | 0.20 | 0.20 |
| `metadata` | 0.22 | 0.18 |
| `neural` | 0.20 | 0.20 |
| `spai` | 0.15 | 0.15 |
| `learned` | 0.18 | — (image-only) |
| `frequency` | 0.12 | 0.12 |
| `capture_origin` | — | 0.16 |
| `embedding` | — | 0.14 |
| `pwtf` | — | 0.14 |
| `tr` (temporal residual) | — | 0.10 |
| `temporal` | — | 0.07 |
| `rppg` | — | 0.05 |
| `d3` | — | 0.0 (metrics only) |

The dataset heads are excluded from video fusion because the `render` head scores 0.80+ on 4 of 5 frames of a confirmed-real reel — it cannot vote there without accusing real footage (`forensics/voter.py`).

## Dataset-trained image classifier (viral brainrot / AI-vs-real)

The off-the-shelf CNNSpot checkpoint does not recognize viral AI image styles: measured on the local corpus it labels **every** brainrot render and every photoreal AI image `human` with ~1.0 confidence — visible in the example above, where DetectZoo reads 0% on both images. The image path therefore adds classifiers trained on `Dataset/`:

| Head | Features | Trained on | Held-out AUC | Recall / FPR |
| --- | --- | --- | --- | --- |
| `render` | CLIP ViT-B/32 embedding | brainrot renders vs real photos | **0.9955** | 95.5% at 1% FPR, 97.6% at 5% |
| `photo` | 60 pixel statistics | photoreal AI vs real photos | 0.8917 | 50.4% at 1% FPR, 65.4% at 5% |
| `photoreal` | CLIP ViT-B/32 embedding | modern photoreal diffusion vs real photos | 0.8007 | 30.0% at 1% FPR, 46.1% at 5% |

Held-out means grouped cross-validation: unseen AI/real categories and unseen contiguous brainrot clip blocks (consecutive frames are near-duplicates, so a random split would leak). The layer reports as `learned` in `breakdown`, maps its probability through a calibrated curve that only lets high-confidence readings escalate (≥ 0.85 → the 62–95 band; below that it stays under 62), and **abstains when the model file or CLIP weights are unavailable instead of voting**. The photoreal head is the one that fired in the worked example; it is capped at `SUSPICIOUS` because photoreal-vs-real is an overlapping problem.

On the 120-image evaluation sample (`scripts/eval_image_dataset.py --per-group 40`), brainrot images called AI rose from **17.5% to 100%** (95% `SYNTHETIC_AI`), the photoreal AI set from 12.5% to 32.5%, and the real-photo false-positive set was **unchanged** (17.5%, the same seven photos as before).

Retrain/export with:

```bash
.venv/bin/python scripts/train_image_classifier.py   # writes forensics/models/image_classifier.json
```

Inference is numpy-only (`forensics/learned_image.py`); CLIP is loaded lazily on the first deep image scan (~10 s) and cached, adding ~0.1 s per image. Set `LEARNED_IMAGE_CLIP=0` to run with the pixel-statistics head alone, or `LEARNED_IMAGE_MODEL=/path/to/model.json` to override the weights path. The image-only layer does not vote on video.

## Image path

`/predict/image/deep` runs the provenance layers first (SynthID, C2PA, declared metadata: caption, alt text, page title/URL). A verified watermark, a C2PA manifest, or a generator-named caption is a hard override — it is provenance evidence, not a pixel guess. Otherwise the spatial layers vote: capture-origin and camera-physics (native-resolution lens/sensor evidence), frequency forensics (wavelet high-frequency deficit, spectral slope, GAN grid peaks), SPAI, DetectZoo CNNSpot with the ViT patch anomaly map, and the dataset-trained heads. `/predict/image/fast` stops after the provenance and frequency layers for sub-100 ms scans.

The page-context inputs are why the API accepts `source_caption`, `alt_text`, `page_title` and `page_url` alongside the bytes; they are weak voters on their own (never a synthetic-band verdict from context alone) but a caption naming the generator is treated as strong provenance. The cache key is context-sensitive, so the same bytes with a different caption are not a cache hit.

## Video path

### PwTF-DVD: pixel-wise temporal frequency detection (ICCV 2025)

Video deep scans include **PwTF-DVD** (Kim et al., ICCV 2025, [arXiv:2507.02398](https://arxiv.org/abs/2507.02398)), the "Beyond Spatial Frequency" detector. Spatial-frequency detectors only see how each *frame* deviates from natural images; generated videos are instead betrayed by how individual *pixels* behave over time, because each frame of a generated video is synthesized semi-independently and texture does not persist physically across frames.

The detector follows the paper's core pipeline, implemented as a training-free numpy layer in the style of the other research layers (SPAI, frequency forensics) — no weights, CPU-only:

1. Per frame, keep the **high-frequency residual** `R_t = frame_t − medianBlur(frame_t, 5)` (the texture/detail layer).
2. **Compensate coherent camera motion** first (phase-correlation global shift estimation, the training-free stand-in for the motion invariance the paper's I3D encoder learns): a steady pan/tilt is aligned back to frame 0 so real motion collapses to low temporal frequencies instead of masquerading as flicker. Irregular motion (cuts, heavy handheld) skips alignment conservatively.
3. Stack residuals over the clip and take a **1D FFT along the time axis per pixel** → pixel-wise temporal magnitude spectrum (positive bins, scaled by 1/T).
4. Score the map with hand-built statistics encoding the paper's evidence, **calibrated against real social-media footage** (Instagram reels, 30 fps H.264): the discriminative signals are the **coherence floor** (the least-coherent 5% of pixels — a regenerated region shares *no* temporal model with the scene, collapsing p05 toward 0; real footage keeps a floor ≥ 0.31) and **residual whiteness** (spectral flatness + lag-1 autocorrelation of the temporal residual — regeneration leaves white, i.e. noise-like, residuals; real motion leaves structured ones). Entropy / high-band share / hotspot rules were measured to *anti-correlate* on real footage and are no longer scored: fast real motion populates high temporal bins more than slow generated footage does.

### Video payloads

`POST /predict/video/deep` accepts **three payload shapes** (priority order):

| Payload | Use case | Who samples the frames |
| --- | --- | --- |
| `{"video_base64": "<base64 of video file>"}` | Device upload | Server (ffmpeg, or OpenCV fallback) |
| `{"video_url": "https://.../clip.mp4"}` | Direct file link — or a social-platform link resolved via yt-dlp | Server downloads, then ffmpeg/OpenCV |
| `{"frames_base64": ["<b64 frame>", ...], "frame_interval_seconds": 0.0333}` | Client-extracted frames (contiguous, native-rate) | Client |

The temporal layers require **contiguous frames at native frame rate**: uniformly-spaced samples stretched across a clip alias real motion into the high temporal bins and span scene cuts, which fabricates exactly the artifacts the detector looks for (measured: uniform sampling scored a real reel *higher* on temporal-artifact signals than a generated one). So for `video_base64` / `video_url` the server decodes the clip itself, splits it into camera shots, and analyzes up to 3 contiguous 32-frame windows at native fps (150 MB cap; requires `pip install opencv-python-headless`), taking the strongest temporal evidence across windows — AI artifacts are often localized to one scene. Client frames **without** a valid `frame_interval_seconds` are treated as a sparse gallery: spatial layers still run, but both temporal layers stay inactive instead of voting on sampling noise — and the verdict reads `INCONCLUSIVE`, not "authentic". The verdict includes `pwtf_metrics` (spectrum statistics), `pwtf_spectrum_bins`, `pwtf_frames_analyzed`, and `window_details` (per-window temporal scores and coherence floors).

### Social-media links (yt-dlp)

Instagram Reels, TikTok, YouTube and X serve page HTML rather than a video file, so the server resolves them with [yt-dlp](https://github.com/yt-dlp/yt-dlp) (300+ extractors) and downloads the underlying clip. Known social hosts skip the plain HTTP fetch entirely (YouTube resets non-browser connections); direct `.mp4`/`.webm` links are streamed in with a plain fetch, with yt-dlp as fallback.

```bash
pip install -U yt-dlp
```

Without yt-dlp the endpoint returns an honest HTTP 415 advisory telling you to upload the file or paste a direct `.mp4`/`.webm`/`.mov` URL. Private, age-restricted or login-walled posts cannot be resolved — download and upload the file in that case. yt-dlp must be kept current; the overwhelming majority of real download failures are stale extractors, so the final error reports the server's yt-dlp version and the exact fix. The layer stack never invents a reading for a stream it could not download: when a platform only yields a **video-only** stream, the frame layers analyze it and the audio layer abstains with a reason.

**Download robustness (measured on real Instagram Reels and YouTube Shorts).** YouTube's modern pages offer no pre-merged A+V file, so a single `best` selector fails with `Requested format is not available`. The downloader walks a layered selector chain, each a fallback in itself:

1. `best[ext=mp4]/best` — pre-merged A+V (Instagram, most direct sites)
2. `bv*+ba/b` — A+V **merge** via ffmpeg, only when a working ffmpeg is detected (YouTube DASH)
3. `bestvideo[ext=mp4]/bestvideo` — video-only, no merge needed (the universal fallback)
4. `b` — last resort

The merge step passes `ffmpeg_location` explicitly (server processes often don't inherit a PATH containing ffmpeg) and downloads run with `noprogress` so logs stay readable.

### Escalation for confirmed temporal collapse

A PwTF-DVD coherence-floor collapse (p05 < 0.25) is the strongest structural regeneration signature this pipeline has, but the fused verdict was hard-capped at 58 — known-AI reels with a *total* collapse (p05 = 0.00, measured) read as an unbadged `UNCERTAIN`. Escalation now scales with corroboration while the no-spatial-agreement cap stays conservative (the layer only sees a 128 px grayscale thumbnail):

| Temporal collapse evidence | Escalation cap | Tier band |
| --- | --- | --- |
| collapse + ≥ 2 spatial layers ≥ 70 | 82 | `SYNTHETIC_AI` territory |
| collapse + 1 confident spatial layer ≥ 70 | 75 | `SUSPICIOUS` (badged) |
| **total** collapse (p05 < 0.10), any spatial | 66 | `SUSPICIOUS` (badged) |
| partial collapse (p05 0.10–0.25), no spatial | 58 | `UNCERTAIN` (unchanged) |

A total collapse is decisive on its own: real footage measured p05 ≥ 0.31 across every calibration shot window, so a near-zero floor is not something motion or compression produces. Measured case: a confirmed-AI YouTube Short with p05 = 0.00 and no confident spatial layer was stuck at 58 `UNCERTAIN`; it now reads 66 `SUSPICIOUS`.

Scores of 69–79 always read `SUSPICIOUS` regardless of confidence (escalations into that band are corroboration-backed by construction).

### No more false "authentic" on video

A video verdict below 35 now requires the temporal ensemble to have actually voted (or a hard authenticity override such as a camera C2PA signature). Previously, a spatial-only scan — client frame extraction without a usable frame interval, or a decode failure — could read `AUTHENTIC_HUMAN` on the strength of spatial layers alone, exactly when the only layers that can see generation were silent; that case now reads `INCONCLUSIVE` and is excluded from both flagging and any clean-score maths.

Several failure modes were fixed in the video ensemble so two different videos can no longer produce identical verdicts: the SynthID probe no longer emits a fabricated hard-coded 68 from spectral noise; the per-frame score trajectory runs real frequency forensics instead of a seeded RNG; the GAN-grid frequency rule is disabled for video frames (every H.264-decoded frame rings periodically after the 512×512 upscale, so the rule fired ~10 on *all* video); the flat-render/cel-shaded signature no longer votes on video frames (it detects saturated cartoon *style* — it fired on 74% of frames of a real hand-drawn animation reel and 0 frames of a generated photorealistic clip); and on video, a lone strong temporal reading can no longer escalate the fused score without spatial agreement (video escalation cap: 55 unless spatial layers corroborate).

The layer is deliberately conservative: mild compression or a moving camera does not trip it on its own — it is one weighted vote in the ensemble (`pwtf` weight 0.14, active only for video).

### Temporal coverage sweep: where the artifact was hiding (2026-10-16)

Two known-AI Instagram reels were reading `AUTHENTIC_HUMAN` (19 and 16). Tiling each clip into **all** of its consecutive 32-frame windows and scoring every one with the same layers the verdict uses showed the detector was not blind — it was **looking in the wrong place**: one reel collapses its coherence floor to `0.00` (the calibrated 62 signature) in 5 of its 8 windows, while the single shot-aware window the pipeline analyzed happened to be one of the healthy ones (`p05 = 0.65`); the other fires the temporal-residual probe in 9 of its 14 windows.

Every server-side video scan now also runs a **coverage sweep**: up to 8 consecutive windows across the first 384 frames (`VIDEO_COVERAGE_MAX_FRAMES`, `VIDEO_COVERAGE_MAX_WINDOWS`), each scored by PwTF-DVD and the temporal-residual probe. The result is reported in the verdict as `temporal_coverage` (per-window records plus `flagged` / `analyzed` / `flagged_frac` / `collapse_windows` / `tr_windows`), and the sweep deliberately does **not** feed the existing escalation paths, so previously calibrated verdicts do not move.

**The honest limit, measured at the same time:** repeated *partial* collapse is not unique to generated clips. The clip then believed to be the repo's real reference (`test videos/vid2.mp4`) collapsed in 6 of its 15 windows and fired the residual probe in 4 (67% of windows) — more than any other negative — and a window-by-window comparison of coherence floor, spectral flatness, residual autocorrelation, residual whiteness, temporal variance, D3 volatility and interframe motion found **no statistic that separated the two missed reels from it**. So escalation from repeated *partial* coverage stayed opt-in:

| `COVERAGE_MODE` | repeated partial evidence (≥ 3 windows and ≥ 50%) | measured cost |
| --- | --- | --- |
| `review` (**default**) | floors the verdict at **`INCONCLUSIVE`** — no longer "authentic", not accused of being AI | none on the real clips (they stay authentic) |
| `flag` | floors at **69 `SUSPICIOUS`** (capped 79, never `SYNTHETIC_AI`) | any clip with that partial signature, including `vid2` |
| `off` | rule disabled | — |

### Two stricter coverage signatures are scored by default (2026-10-22)

The 2026-10-22 batch added 20 more AI reels; three of them read `40 INCONCLUSIVE` with HIGH confidence, and re-measuring exposed both a second discriminator and a bad label:

- **`vid2`/`vid3` are generated, not real.** They are the same file byte for byte (identical SHA-256) — the "two real reference clips" were one clip counted twice — and it is generated footage: the pigeon in the subject's hand morphs into a pastry/rock between frames 83–154 while the hand pose is unchanged, the motorcycle/chair/vacuum props sit in the scene without contact shadows or consistent perspective, the render is 24 fps, and it carries burned-in "believe anything / can be fake / get tricked" captions. They are now labelled AI in `tests/test_videos.py`, which removes the only negative that made repeated collapse unusable.
- **Two signatures never occur on the authentic reels in the corpus**, measured on 32-frame windows over the first 384 frames: a **total** collapse (`p05 < 0.10`) repeated in **≥ 2 windows** (AI 4/12 and 2/12; authentic 0/7 and 1/7), and a temporal-residual fire whose **residual white-fraction ≥ 0.55** (AI 0.73 / 0.59; authentic at most 0.42). Both now floor the verdict at **69 `SUSPICIOUS`** (cap 79, never `SYNTHETIC_AI`), independent of `COVERAGE_MODE` and still skipped for a confirmed camera/watermark override. The sweep reports the counts as `deep_collapse_windows` and `white_windows`, and each window record carries `white`, `deep_collapse` and `tr_score`.

Measured effect on the three misses (defaults, cache bypassed): `ig-DeeYNdsMiqC` 40 → **69 `SUSPICIOUS`**, `ig-DeTtabsthXY` 40 → **69 `SUSPICIOUS`**, `ig-DeppmpCtSnZ` 40 → **69 `SUSPICIOUS`**; the two confirmed-authentic reels are unchanged (`ig-DecK8wQPTM7` 24, `ig-human-post-01` 12, both `AUTHENTIC_HUMAN`).

The sweep costs extra temporal work per scan (~+15–25 s on a 720×1280 15 s reel with the shipped defaults); lower `VIDEO_COVERAGE_MAX_WINDOWS` or use `COVERAGE_MODE=off` on a latency-constrained deployment.

### Audio track: a separate axis, reported and never scored

Video scans also decode and measure the clip's **audio track** (`forensics/audio_track.py`, phase A0 of the audio/lip-sync design plan). It decodes mono float32 at 48 kHz with ffmpeg — from the **same bytes the frames came from**, so a link scan never downloads the clip twice — and reports the result in the verdict as an `audio` block plus plain-language lines in `reasons`.

**It never votes.** A synthetic voice over real footage is an *audio-AI* finding, not a deepfake video, so audio is a separate axis: `audio.score` is always `null`, it never appears in `breakdown`/`layers_active`, and no audio condition can move the video tier. It abstains with a reason when there is nothing to decode (client-extracted frames carry no container audio; a video-only download or a silent clip has no stream).

What it reports: duration, sample rate, loudness (RMS/peak dBFS), active/silent frame fractions, zero-crossing rate, **effective bandwidth** (99% energy), high-frequency share above 8/16 kHz, spectral centroid and flatness, loudness-envelope dynamics, and syllable-rate (2–8 Hz) modulation. `audio.kind` is `speech` / `nonspeech` / `silence` / `unavailable`.

**Honest limits, by design:** `speech` comes from energy/periodicity heuristics (a swinging loudness envelope, 2–8 Hz modulation, energy in the 300–3400 Hz speech band), not a speech classifier — strongly rhythmic music can satisfy it, which is why a low tremolo tone with no speech-band energy is correctly reported as `nonspeech`. And a **narrow bandwidth is a lead, not evidence**: it is common in vocoder/TTS re-synthesis, but lossy music and older recordings share the signature (measured: a real local clip reads 3.2 kHz while an AI reel reads 1.4 kHz). Synthetic-speech *detection* and AV lip-sync are not implemented yet; they arrive behind flags after calibration on a real-vs-TTS corpus. Check the layer with `.venv/bin/python scripts/check_audio_track.py`.

### D3 second-order dynamics: metrics layer (ICCV 2025, direction-corrected)

Video deep scans also run **D3** (Zheng et al., ICCV 2025, [arXiv:2508.00701](https://arxiv.org/abs/2508.00701)) — **"Detection by Difference of Differences"** — which measures the **second-order temporal dynamics** of the video's feature trajectory: the first-order feature is the feature-space distance between consecutive frames ("velocity"), the second-order feature is the central difference of that sequence ("acceleration").

**Direction warning:** popular summaries frequently state this backwards. The paper's finding is that **real** videos have **chaotic, spiky** second-order dynamics (sensors, optics and codecs keep perturbing frame distances), while generated videos are **too smooth** — motion interpolation produces nearly linear velocity sequences and a nearly flat acceleration profile. Low volatility ⇒ generation-like; high volatility ⇒ physical. (On GenVideo the method reaches 98.46% mAP, +10.39% over the prior state of the art.)

On this server D3 ships as a **metrics layer, not a voting layer** (verdict fields `d3_metrics`, `straighten_metrics`, plus a per-window `d3_volatility` in `window_details`). The reason is a measured negative calibration result, in the same spirit as the PwTF entropy/hf-share rules that had to be retired: the paper's statistic is computed on features from a **semantic encoder** (XCLIP-B/16; DINOv2/MobileNet-v3 also validated), and in that space "too smooth" is separable. This stack is numpy/PIL-only (detectzoo exposes classifier scores, not embeddings), and in pixel/patch feature space every variant tested **overlaps or anti-correlates** — `python -m forensics.eval_d3` reproduces the table:

| Candidate statistic | Real-like range | Generation-like range | Verdict |
| --- | --- | --- | --- |
| global volatility `std(accel)/mean(vel)` | 0.10 – 0.59 | 0.05 – 0.42 | overlap |
| scale-invariant `std(accel)/std(vel)` | 0.74 – 1.72 | 1.47 – 1.66 | overlap |
| per-region second-order volatility | 0.15 – 1.08 | 0.99 – 1.04 | overlap (motion-dependent) |

A tripod pan of real footage (velocity dominated by codec noise → high *relative* volatility) is indistinguishable from, or smoother than, locally regenerated content. Voting on any of these would false-positive ordinary real motion — so the layer reports the statistics and abstains (`score: None`), and the fusion treats a hypothetical `d3` vote as temporal-family evidence that can never escalate alone. The same module reports **ReStraV-style trajectory geometry** (Internò et al. 2025, [arXiv:2507.00583](https://arxiv.org/abs/2507.00583)) for the same reason: the published straightening property holds in DINOv2 space.

**Upgrade path:** provide semantic frame embeddings (e.g. torch + DINOv2/XCLIP on the space deployment) via `analyze_second_order_dynamics(..., encoder_embeddings=Z)` and calibrate per-encoder thresholds on real social footage with the `forensics/eval_d3.py` harness before enabling the vote.

Not implemented on purpose: heuristic "physics" checks (shadow direction, lighting coherence, contact physics). The published physics-driven detector (Zhang et al., NeurIPS 2025, arXiv:2510.08073) uses learned models; hand-built shadow heuristics would repeat this repo's documented anti-correlation failures (the retired flat-render rule fired on 74% of frames of a real hand-drawn animation reel). It belongs on the roadmap behind trained models, not in this numpy stack.

## Text path

### StoryScope: narrative-structure AI-fiction detection

StoryScope (implemented from Russell et al. 2026, [arXiv:2604.03136](https://arxiv.org/abs/2604.03136)) detects AI-written fiction by reading **narrative structure** — plot shape, character agency, temporal structure, theme handling — instead of surface style that models can paper over. The published 304-feature taxonomy (10 NarraBench dimensions) and the LLM extraction prompts are used as released; an XGBoost classifier is trained on the paper's own 61,575-story feature matrix and scored through a dependency-free pure-Python model reader.

**Accuracy (trained on the paper's released features, prompt-grouped held-out folds):**

| Model | Macro-F1 | AUPRC | Accuracy |
| --- | --- | --- | --- |
| Full (304 features) | **0.962** | 0.999 | 0.979 |
| Narrative only (style dropped) | 0.943 | 0.998 | 0.969 |

The narrative-only variant retains **98%** of full-model performance — reproducing the paper's "narrative features retain >97%" finding. The paper reports 93.2% macro-F1 on its held-out test split.

#### How it works

1. The story text is turned into the 304 taxonomy features (plot, agents, temporal structure, revelation, style, ...) by one of two engines:
   - **LLM engine** (`STORYSCOPE_MODE=llm`): the paper's pipeline — an LLM literary analyst annotates the story (10 per-dimension calls). Most accurate; needs an API key.
   - **Heuristic engine** (`STORYSCOPE_MODE=heuristic`, **default**): pure rule-based analysis of the text (stdlib only) — no API key, no network, ~10 ms per story. Covers 204 of the 304 features with word-list/statistic proxies; features that need literary judgment are left as `n/a`.
2. Values are normalized onto the taxonomy's canonical categories and one-hot encoded (categories derived from the training data, so no hidden label mappings).
3. The XGBoost binary classifier (human vs AI) scores the vector; the API returns the AI probability plus a per-dimension breakdown and the strongest narrative tells, e.g. "Thematic explicitness = high", "Conflict resolution = tidy" — the patterns the paper found most predictive.

#### Offline heuristic engine (no API key)

**Heuristic is the default.** It reads the same narrative tells the paper identified (plot structure, character agency, temporal shape, thematic explicitness, dialogue proportion, style statistics) using ~90 hand-built text statistics and word lists — no LLM, no API, no slowdown.

**Honest accuracy bounds** — measured on the paper's released 61,575-story feature matrix with the shipped model (see `python -m storyscope.eval_heuristic`):

| Scenario | Macro-F1 | AUPRC | Accuracy |
| --- | --- | --- | --- |
| Full LLM extraction (in-sample upper bound) | 0.999 | 1.000 | 0.9996 |
| Heuristic coverage, covered features as released | **0.958** | 0.999 | 0.976 |
| Heuristic covered features ~60% accurate (middle estimate) | 0.600 | 0.966 | — |
| Heuristic covered features contribute no signal (floor) | 0.455 | 0.833 | — |

Heuristic mode retains **96% of full-model macro-F1 when its estimates are right**, and 84% of the model's split nodes sit in features the heuristic can reach. Real-world performance sits between the middle estimate and the upper bound — treat heuristic verdicts as a **fast screening signal, not research-grade**: borderline scores are inconclusive, and short texts (well under the ~5,000-word training length) are unreliable. For high-stakes checks, switch to `STORYSCOPE_MODE=llm`.

```bash
# Extraction engine: heuristic (default, offline, no key) | llm
STORYSCOPE_MODE=heuristic

# --- LLM engine only ---
STORYSCOPE_LLM_PROVIDER=openai           # openai | anthropic | gemini
STORYSCOPE_LLM_MODEL=gpt-4o-mini         # provider default if unset
STORYSCOPE_LLM_API_KEY=sk-...            # falls back to OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY
STORYSCOPE_LLM_BASE_URL=https://api.openai.com/v1   # OpenAI-compatible endpoints (DeepSeek, OpenRouter, vLLM, ...)
```

Endpoint: `POST /predict/storyscope` with body `{"text": "...", "mode": "heuristic"}` (`mode` is optional; defaults to `STORYSCOPE_MODE`). The response includes `"mode"` and `"feature_source"` so clients can tell which engine produced the verdict.

#### Retraining (optional)

The shipped classifier was trained from `storyscope/data/storyscope_features.parquet` (the paper's released per-story feature matrix). To retrain:

```bash
pip install xgboost pandas pyarrow scikit-learn   # training only
python -m storyscope.train --self-test            # cross-validates, saves model + stats
```

On macOS, xgboost needs the OpenMP runtime (`brew install libomp`) — the shipped model and server do **not**.

#### Attribution

StoryScope's taxonomy, extraction prompts and dataset are by Jenna Russell, Rishanth Rajendhran, Chau Minh Pham, Mohit Iyyer and John Wieting (University of Maryland / Google DeepMind), released under MIT. This implementation ports the extraction pipeline and retrains the classifier on the released feature matrix.

### DNA-DetectLLM

`POST /predict/text/dna` runs the zero-shot DNA-DetectLLM detector (NeurIPS 2025 Spotlight): it measures how closely a text matches the reference model's ideal "mutation–repair" sequence. It is independent of StoryScope (different evidence, different failure modes) and is the more useful of the two on short non-narrative text — on the repo's `demo-samples/texts/human-written.txt`, StoryScope's heuristic reads ~79 (AI) while DNA reads ~23 (human), exactly the short-post case the heuristic caveats warn about.

## Fusion, confidence and tiers

- **`UNCERTAIN` tier:** fused scores of 55–68 with non-HIGH confidence read `UNCERTAIN` instead of `SUSPICIOUS`. These are the escalated-but-unconfirmed readings (a lone strong layer, single-window temporal evidence, layer disagreement) where a decisive-sounding tier misled users; a HIGH-confidence 55–68 (several agreeing layers) still reads `SUSPICIOUS`, and 69–79 always does.
- **Single-window outlier downgrade:** when temporal evidence is strong in exactly one shot window while every other window reads clean, confidence drops one level — localized artifacts are plausible, but a lone window should not carry a confident verdict.
- **Extreme layer disagreement** (spread ≥ 70) downgrades confidence to LOW instead of stopping at MEDIUM.
- **Weighted voting:** each layer contributes its score with a fixed weight (`pwtf` 0.14, and so on) and only active layers are averaged — abstention lowers coverage, not the score. Hard overrides (verified watermark, C2PA manifest, confirmed camera capture) short-circuit the average entirely.

## Configuration

| Variable | Default | Effect |
| --- | --- | --- |
| `PORT` | `5001` | HTTP port |
| `API_KEY` / `BEARER_TOKEN` | unset (open) | Require `Authorization: Bearer` |
| `STORYSCOPE_MODE` | `heuristic` | `heuristic` \| `llm` text engine |
| `LEARNED_IMAGE_CLIP` | `1` | Set `0` to run the dataset heads without CLIP |
| `LEARNED_IMAGE_MODEL` | `forensics/models/image_classifier.json` | Trained-head weights path |
| `TR_VOTE` | `1` | Temporal-residual vote on/off |
| `COVERAGE_MODE` | `review` | `review` \| `flag` \| `off` — repeated-partial-collapse policy |
| `VIDEO_STRICT` | `1` | Recall-biased video escalation; `0` restores calibrated behaviour |
| `VIDEO_COVERAGE_MAX_FRAMES` | `384` | Coverage-sweep frame budget |
| `VIDEO_COVERAGE_MAX_WINDOWS` | `8` | Coverage-sweep window cap |

## Scan log: every scan in SQLite

The scan cache answers "have I seen this before?". The scan log answers the other question: *what has the detector been asked to judge, and what did it say?* Every text, image and video scan the server serves — cache hit or miss, success or detector failure — is recorded in SQLite by [`forensics/scan_log.py`](forensics/scan_log.py).

**Storage.** Stdlib `sqlite3`, one file: `cache/scan_log.db` (override the directory with `SCAN_LOG_DIR`). WAL journal mode, one short-lived connection per operation, no new dependency and no extra service. It sits next to `cache/scan_cache.db` and follows the same rules: the write path is best-effort and a logging failure can never turn a good scan into an error response.

**What a row holds.**

| column | contents |
| --- | --- |
| `kind`, `source`, `status`, `cached` | `text`/`image`/`video`, endpoint, HTTP status, `exact`/`near` cache hit |
| `score`, `tier`, `label`, `confidence` | normalized verdict fields, whichever shape the detector returned |
| `human_likely` | 1 when the verdict cleared the content (`AUTHENTIC_HUMAN` for media, `Human-written` for text) |
| `content_sha256`, `content_chars` | hash + size of what was scanned |
| `excerpt` | text scans only, bounded (default 4,000 chars) |
| `source_host`, `source_sha256` | image/video URL host + URL hash — never the full URL |
| `ip_hash`, `user_agent`, `latency_ms` | salted 16-char IP hash (abuse clustering without storing addresses) |
| `verdict` | compact verdict JSON — base64 overlays, frames and inline media are dropped |

**Retention** is biased toward the human corpus, because that is the part worth keeping (false-positive evidence and a whitelist corpus): non-human scans live 90 days, human-likely scans 365, and the row cap trims non-human rows first. A burst of AI scans can never push human samples out.

| env var | default |
| --- | --- |
| `SCAN_LOG` | `1` (set `0` to disable) |
| `SCAN_LOG_DIR` | `<repo>/cache` |
| `SCAN_LOG_EXCERPT_CHARS` | `4000` |
| `SCAN_LOG_RETENTION_DAYS` | `90` |
| `SCAN_LOG_HUMAN_RETENTION_DAYS` | `365` |
| `SCAN_LOG_MAX_ROWS` | `200000` |
| `SCAN_LOG_SALT` | `rinse-scan-log` — set it in production |

**Getting at the log.** On the machine that holds the DB:

```bash
.venv/bin/python scripts/scan_log_cli.py stats
.venv/bin/python scripts/scan_log_cli.py recent --human --text
.venv/bin/python scripts/scan_log_cli.py export --out human-corpus.jsonl --human-only

sqlite3 cache/scan_log.db "SELECT kind, label, score, datetime(created_at,'unixepoch')
  FROM scans WHERE human_likely = 1 ORDER BY id DESC LIMIT 20;"
```

From anywhere over HTTP with the same Bearer token:

```bash
BASE=https://<your-host>
AUTH="Authorization: Bearer $API_KEY"

curl -s -H "$AUTH" "$BASE/scans/stats" | jq
curl -s -H "$AUTH" "$BASE/scans/recent?human=1&kind=text&include_text=1&limit=20" | jq '.scans[] | {created_at, score, label, excerpt}'
curl -s -H "$AUTH" "$BASE/scans/export?human=1" -o human-corpus.jsonl
```

**Durability.** `cache/` lives on the instance's local disk, so it survives restarts on a machine with a persistent volume and does *not* survive an ephemeral one. `scripts/scan_log_cli.py export`, or the HTTP export on a schedule, is the escape hatch — the log is a record, not a source of truth; exports are the durable artifact.

## Deployment

The backend ships as a **Gradio-SDK Space** with the Flask API mounted on the Space root — the only shape a free account can host (ZeroGPU Spaces; Docker and `cpu-basic` hardware need a paid plan). Everything runs on CPU; the single `@spaces.GPU` function is a no-op that exists only to satisfy the ZeroGPU runtime and never burns quota.

```bash
# Stage the package (also bakes the 282 MB CNNSpot weights into it)
.venv/bin/python scripts/build_space_package.py

hf auth login
hf repos create <user>/rinse-detector --type space --space-sdk gradio \
  --flavor zero-a10g --public --exist-ok
export API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
hf spaces secrets add <user>/rinse-detector -s API_KEY   # reads $API_KEY
hf upload <user>/rinse-detector deploy/space_stage/. --repo-type space \
  --exclude "**/__pycache__/**"
```

`packages.txt` installs ffmpeg (video decode, yt-dlp merges, audio track) and libglib2.0-0 (required by `opencv-python-headless`).

Verify, don't trust a green RUNNING badge:

```bash
curl -s https://<user>-rinse-detector.hf.space/health | jq .detectzoo_loaded
# true — false means the neural layer fell back to simulation mode and every
# scan is running without it.
```

Full guide plus Render / Oracle / Azure targets: [`deploy/DEPLOY.md`](deploy/DEPLOY.md). The `Dockerfile` at the repo root builds the same server for any container host.

## Testing and evaluation

Four runnable files exercise the real detector code over the repo's own corpus and print the score every layer returns:

```bash
.venv/bin/python tests/test_text.py     # StoryScope + DNA-DetectLLM scores
.venv/bin/python tests/test_images.py   # /predict/image/deep fused score + tier
.venv/bin/python tests/test_videos.py   # /predict/video/deep score + tier + PwTF p05
.venv/bin/python tests/test_scan_log.py # scan-log write/query/retention
```

Each runs **in-process by default** — it imports the Flask app and drives it through its test client, so no server process is needed — or against a running instance with `--live http://localhost:5001` (and `--key` / `$RINSE_API_KEY` for a keyed server). Useful flags: `--ids <id,id>` for a subset, `--audit` (video: print the per-window temporal evidence), `--skip-instagram` (local clips only), `--remote-images`, and `--use-cache` (the default sends `no_cache=true`, so every verdict is freshly computed).

Corpus: `demo-samples/texts/` + the StoryScope evasion samples + the humanizer outputs (text), `tests/calibration_corpus/{ai,real}/` (images), and `test videos/` plus the Instagram posts registered in `tests/detector_assets.json` and `tests/media_test_assets.json` (videos). Each run prints a per-asset score line and a `SCORES` recap, and merges the raw evidence into `tests/media_test_results.json`. The exit status is 0 only when no labeled asset FAILs and nothing errored; assets that are deliberately unasserted or unlabeled are reported **score-only**.

Measurement harnesses for changing a threshold:

| Script | What it measures |
| --- | --- |
| `scripts/eval_image_dataset.py` | Recall / FPR by group over `Dataset/` for the image path |
| `scripts/eval_mnw.py` | The MNW benchmark (AI media in the wild) |
| `scripts/regression_check.py` | Full regression across the registered asset sets |
| `python -m forensics.eval_d3` | The D3 second-order statistics table (real vs generation-like ranges) |
| `python -m storyscope.eval_heuristic` | StoryScope heuristic accuracy bounds |
| `scripts/check_audio_track.py` | Audio-track layer on a real clip vs an AI reel |
| `scripts/train_image_classifier.py` | Retrains and exports the dataset heads |

Current known reds, kept visible on purpose:

- `demo-samples/texts/human-written.txt` reads ~79 (AI) under StoryScope's offline heuristic while DNA-DetectLLM reads ~23 (human) — a short, non-narrative post, i.e. the input the heuristic caveats above warn about.
- **No video reds as of 2026-10-22** — the full video suite is 59/59 with the default settings and the cache bypassed. The five reels that used to read `40 INCONCLUSIVE` now read `69 SUSPICIOUS` on the repeated total-collapse / residual-whiteness rules, and both confirmed-authentic reels stay `AUTHENTIC_HUMAN` (24 and 12).

## Honest limits

- **The dataset heads are trained on a local corpus** (`Dataset/`, ~7,400 images drawn from AI-vs-real sets and viral render styles). Their held-out numbers are grouped by category and clip, but a distribution shift in the wild still costs recall; the photoreal head is capped at `SUSPICIOUS` for exactly that reason.
- **A stripped image carries no provenance.** Both images in the worked example had no C2PA manifest, no SynthID carrier and no metadata, so the verdict rested entirely on pixel statistics. Watermarked or credentials-bearing media is decided far more decisively.
- **Detection is asymmetric by design.** The thresholds were tuned to keep real footage out of the AI bands even at the cost of missed AI — measured false positives on the real-photo set were left explicitly unchanged when the brainrot recall went from 17.5% to 100%.
- **Temporal layers need contiguous native-rate frames.** Sparse client frames disable them, which is reported as `INCONCLUSIVE`, not as a clean bill.
- **Audio is reported, never scored.** There is no synthetic-speech detector here yet.
- **Short text is unreliable** under the heuristic engine — see the StoryScope bounds table.

## Datasets and attribution

The README sample images are tracked at the repo root (real: `animals_1.jpg`; synthetic: `image.png`). Detection corpora used for training and evaluation — `Dataset/`, `MNW/`, `tests/calibration_corpus/`, `test videos/` — are git-ignored local data and are **not** part of this repository; see `.gitignore`. Research layers cite their papers inline; StoryScope's taxonomy and dataset are MIT-licensed by their authors.
