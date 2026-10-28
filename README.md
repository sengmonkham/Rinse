# RINSE

RINSE (Remove Inauthentic Noise) is a browser extension and dashboard designed to detect AI-generated content in text, images, and video.

## Workings and Details

The application functions by analyzing web content through a dual execution path. By default, it operates offline using heuristic algorithms to identify generative text structures, inspect image metadata signatures, and check video container flags directly in the browser. When switched to cloud mode, it sends requests to a Python API server that runs advanced deep learning classifiers, such as DetectZoo models, to perform structural pixel audits and verify media authenticity. For narrative text, cloud mode also runs **StoryScope**, a research-grade detector that reads plot-level structure instead of wording.

## Getting Started

### Web Application and Extension
1. Install dependencies: npm install
2. Start the dev server: npm run dev
3. Build the project: npm run build
4. Load the build: Open chrome://extensions, enable developer mode, and load the dist folder.

### Python API Server
To connect the extension or sandbox to deep learning models:
1. Install requirements: pip install flask flask-cors requests pillow detectzoo
2. Start the server: python server.py
3. Toggle to Cloud Mode in the settings panel to route scanning requests through this backend.

## StoryScope: narrative-structure AI fiction detection

StoryScope (implemented from Russell et al. 2026, [arXiv:2604.03136](https://arxiv.org/abs/2604.03136)) detects AI-written fiction by reading **narrative structure** — plot shape, character agency, temporal structure, theme handling — instead of surface style that models can paper over. The published 304-feature taxonomy (10 NarraBench dimensions) and the LLM extraction prompts are used as released; an XGBoost classifier is trained on the paper's own 61,575-story feature matrix and scored through a dependency-free pure-Python model reader.

**Accuracy (trained on the paper's released features, prompt-grouped held-out folds):**

| Model | Macro-F1 | AUPRC | Accuracy |
|---|---|---|---|
| Full (304 features) | **0.962** | 0.999 | 0.979 |
| Narrative only (style dropped) | 0.943 | 0.998 | 0.969 |

The narrative-only variant retains **98%** of full-model performance — reproducing the paper's "narrative features retain >97%" finding. The paper reports 93.2% macro-F1 on its held-out test split.

Two extraction engines feed the same classifier — see below.

### How it works

1. The story text is turned into the 304 taxonomy features (plot, agents, temporal structure, revelation, style, ...) by one of two engines:
   - **LLM engine** (`STORYSCOPE_MODE=llm`): the paper's pipeline — an LLM literary analyst annotates the story (10 per-dimension calls). Most accurate; needs an API key.
   - **Heuristic engine** (`STORYSCOPE_MODE=heuristic`, **default**): pure rule-based analysis of the text (stdlib only) — no API key, no network, ~10 ms per story. Covers 204 of the 304 features with word-list/statistic proxies; features that need literary judgment are left as `n/a`.
2. Values are normalized onto the taxonomy's canonical categories and one-hot encoded (categories derived from the training data, so no hidden label mappings).
3. The XGBoost binary classifier (human vs AI) scores the vector; the API returns the AI probability plus a per-dimension breakdown and the strongest narrative tells, e.g. "Thematic explicitness = high", "Conflict resolution = tidy" — the patterns the paper found most predictive.

### Offline heuristic engine (no API key)

**Heuristic is the default.** It reads the same narrative tells the paper identified (plot structure, character agency, temporal shape, thematic explicitness, dialogue proportion, style statistics) using ~90 hand-built text statistics and word lists — no LLM, no API, no slowdown. Run it with the server configured as-is, or call the endpoint directly.

**Honest accuracy bounds** — measured on the paper's released 61,575-story feature matrix with the shipped model (see `python -m storyscope.eval_heuristic`):

| Scenario | Macro-F1 | AUPRC | Accuracy |
|---|---|---|---|
| Full LLM extraction (in-sample upper bound) | 0.999 | 1.000 | 0.9996 |
| Heuristic coverage, covered features as released | **0.958** | 0.999 | 0.976 |
| Heuristic covered features ~60% accurate (middle estimate) | 0.600 | 0.966 | — |
| Heuristic covered features contribute no signal (floor) | 0.455 | 0.833 | — |

Heuristic mode retains **96% of full-model macro-F1 when its estimates are right**, and 84% of the model's split nodes sit in features the heuristic can reach. Real-world performance sits between the middle estimate and the upper bound — treat heuristic verdicts as a **fast screening signal, not research-grade**: borderline scores are inconclusive, and short texts (well under the ~5,000-word training length) are unreliable. For high-stakes checks, switch to `STORYSCOPE_MODE=llm`.

### Server configuration

```bash
# Extraction engine: heuristic (default, offline, no key) | llm
STORYSCOPE_MODE=heuristic

# --- LLM engine only ---
# Provider: openai (default) | anthropic | gemini
STORYSCOPE_LLM_PROVIDER=openai
STORYSCOPE_LLM_MODEL=gpt-4o-mini        # provider default if unset
STORYSCOPE_LLM_API_KEY=sk-...           # falls back to OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY
# Optional, for OpenAI-compatible endpoints (DeepSeek, OpenRouter, vLLM, ...):
STORYSCOPE_LLM_BASE_URL=https://api.openai.com/v1
```

Endpoint: `POST /predict/storyscope` with body `{"text": "...", "mode": "heuristic"}` (`mode` is optional; defaults to `STORYSCOPE_MODE`). The Playground text sandbox calls it automatically when set to Cloud Detector mode. The response includes `"mode"` and `"feature_source"` so clients can tell which engine produced the verdict.

### Retraining (optional)

The shipped classifier was trained from `storyscope/data/storyscope_features.parquet` (the paper's released per-story feature matrix). To retrain:

```bash
pip install xgboost pandas pyarrow scikit-learn   # training only
python -m storyscope.train --self-test            # cross-validates, saves model + stats
```

On macOS, xgboost needs the OpenMP runtime (`brew install libomp`) — the shipped model and server do **not**.

### Attribution

StoryScope's taxonomy, extraction prompts and dataset are by Jenna Russell, Rishanth Rajendhran, Chau Minh Pham, Mohit Iyyer and John Wieting (University of Maryland / Google DeepMind), released under MIT. This implementation ports the extraction pipeline and retrains the classifier on the released feature matrix.

## PwTF-DVD: pixel-wise temporal frequency video detection (ICCV 2025)

Video deep scans include **PwTF-DVD** (Kim et al., ICCV 2025, [arXiv:2507.02398](https://arxiv.org/abs/2507.02398)), the "Beyond Spatial Frequency" detector. Spatial-frequency detectors only see how each *frame* deviates from natural images; generated videos are instead betrayed by how individual *pixels* behave over time, because each frame of a generated video is synthesized semi-independently and texture does not persist physically across frames.

The detector follows the paper's core pipeline, implemented as a training-free numpy layer in the style of the other research layers (SPAI, frequency forensics) — no weights, CPU-only:

1. Per frame, keep the **high-frequency residual** `R_t = frame_t − medianBlur(frame_t, 5)` (the texture/detail layer).
2. **Compensate coherent camera motion** first (phase-correlation global shift estimation, the training-free stand-in for the motion invariance the paper's I3D encoder learns): a steady pan/tilt is aligned back to frame 0 so real motion collapses to low temporal frequencies instead of masquerading as flicker. Irregular motion (cuts, heavy handheld) skips alignment conservatively.
3. Stack residuals over the clip and take a **1D FFT along the time axis per pixel** → pixel-wise temporal magnitude spectrum (positive bins, scaled by 1/T).
4. Score the map with hand-built statistics encoding the paper's evidence, **calibrated against real social-media footage** (Instagram reels, 30fps H.264): the discriminative signals are the **coherence floor** (the least-coherent 5% of pixels — a regenerated region shares *no* temporal model with the scene, collapsing p05 toward 0; real footage keeps a floor ≥ 0.31) and **residual whiteness** (spectral flatness + lag-1 autocorrelation of the temporal residual — regeneration leaves white, i.e. noise-like, residuals; real motion leaves structured ones). Entropy / high-band share / hotspot rules were measured to *anti-correlate* on real footage and are no longer scored: fast real motion populates high temporal bins more than slow generated footage does.

### Video endpoint usage

`POST /predict/video/deep` accepts **three payload shapes** (priority order):

| Payload | Use case | Who samples the frames |
|---|---|---|
| `{"video_base64": "<base64 of video file>"}` | Device upload | Server (ffmpeg, or OpenCV fallback) |
| `{"video_url": "https://.../clip.mp4"}` | Direct file link — or a social-platform link resolved via yt-dlp | Server downloads, then ffmpeg/OpenCV |
| `{"frames_base64": ["<b64 frame>", ...], "frame_interval_seconds": 0.0333}` | Browser-extracted frames (contiguous, native-rate) | Browser (`<video>` + `requestVideoFrameCallback`) |

The temporal layers require **contiguous frames at native frame rate**: uniformly-spaced samples stretched across a clip alias real motion into the high temporal bins and span scene cuts, which fabricates exactly the artifacts the detector looks for (measured: uniform sampling scored a real reel *higher* on temporal-artifact signals than a generated one). So for `video_base64` / `video_url` the server decodes the clip itself, splits it into camera shots, and analyzes up to 3 contiguous 32-frame windows at native fps (150MB cap; requires `pip install opencv-python-headless`), taking the strongest temporal evidence across windows — AI artifacts are often localized to one scene. The extension captures contiguous frames the same way (playing the video muted and grabbing every presented frame) and forwards the real per-frame interval. Client frames **without** a valid `frame_interval_seconds` are treated as a sparse gallery: spatial layers still run, but both temporal layers stay inactive instead of voting on sampling noise. The verdict includes `pwtf_metrics` (spectrum statistics), `pwtf_spectrum_bins`, `pwtf_frames_analyzed`, and `window_details` (per-window temporal scores and coherence floors).

**Social-media links now work when yt-dlp is installed.** Instagram Reels, TikTok, YouTube, X, etc. serve page HTML rather than a video file, so the server resolves them with [yt-dlp](https://github.com/yt-dlp/yt-dlp) (300+ extractors) and downloads the underlying clip. Known social hosts skip the plain HTTP fetch entirely (YouTube resets non-browser connections) and go straight to yt-dlp; direct `.mp4`/`.webm` links are streamed in with a plain fetch, with yt-dlp as fallback. Install yt-dlp server-side with:

```bash
pip install -U yt-dlp
```

Without yt-dlp the endpoint keeps the honest HTTP 415 advisory telling you to upload the file or paste a direct `.mp4`/`.webm`/`.mov` URL. Note that private, age-restricted, or login-walled posts cannot be resolved — download and upload the file in that case (X/Twitter videos in particular are increasingly login-walled; yt-dlp reports this clearly). yt-dlp must be kept up to date (`pip install -U yt-dlp`) because platforms change constantly. The selector chain prefers a pre-merged A+V file (and an ffmpeg merge when a working ffmpeg is present); when a platform only yields a **video-only** stream, the frame layers still analyze the clip and the audio layer abstains honestly with a reason — it never invents a reading for audio that was never downloaded.

**Download robustness (measured on real Instagram Reels and YouTube Shorts).** YouTube's modern pages offer no pre-merged A+V file at all, so the old two-selector chain failed with `Requested format is not available` and the video was never analyzed. The downloader now walks a layered selector chain, each a fallback in itself:

1. `best[ext=mp4]/best` — pre-merged A+V (Instagram, most direct sites)
2. `bv*+ba/b` — A+V **merge** via ffmpeg, only when a working ffmpeg is detected (YouTube DASH)
3. `bestvideo[ext=mp4]/bestvideo` — video-only, no merge needed (the universal fallback; the audio layer abstains when this path is used)
4. `b` — last resort

The merge step passes `ffmpeg_location` explicitly (server processes often don't inherit a PATH containing ffmpeg), downloads run with `noprogress` so server logs stay readable, and a final failure reports the **server's yt-dlp version** plus the exact fix (`pip install -U yt-dlp`) in both the server log and the API error — the overwhelming majority of real download failures are stale yt-dlp extractors, since platforms change constantly. Rebuild the HF Space after bumping yt-dlp so the new version is actually installed.

**Escalation for confirmed temporal collapse.** A PwTF-DVD coherence-floor collapse (p05 < 0.25) is the strongest structural regeneration signature this pipeline has, but the fused verdict was hard-capped at 58 — known-AI reels with a *total* collapse (p05 = 0.00, measured) read as an unbadged UNCERTAIN. Escalation now scales with corroboration while the no-spatial-agreement cap stays conservative (the layer only sees a 128px grayscale thumbnail):

| Temporal collapse evidence | Escalation cap | Tier band |
|---|---|---|
| collapse + ≥ 2 spatial layers ≥ 70 | 82 | SYNTHETIC_AI territory |
| collapse + 1 confident spatial layer ≥ 70 | 75 | SUSPICIOUS (badged) |
| **total** collapse (p05 < 0.10), any spatial | 66 | SUSPICIOUS (badged) |
| partial collapse (p05 0.10–0.25), no spatial | 58 | UNCERTAIN (unchanged) |

A total collapse (p05 < 0.10) is decisive on its own: real footage measured p05 ≥ 0.31 across every calibration shot window, so a near-zero floor is not something motion or compression produces. Measured case: a confirmed-AI YouTube Short with p05 = 0.00 and no confident spatial layer was stuck at 58 UNCERTAIN; it now reads 66 SUSPICIOUS. The 55–68 tier rule counts a total collapse as decisive evidence even when a layer-disagreement downgrade reduced confidence.

Scores of 69–79 now always read SUSPICIOUS regardless of confidence (escalations into that band are corroboration-backed by construction), and the extension badges on the server's tier (`SYNTHETIC_AI`/`SUSPICIOUS`) instead of re-running its own divergent gate.

**No more false 'authentic' on video.** A video verdict below 35 now requires the temporal ensemble to have actually voted (or a hard authenticity override such as a camera C2PA signature). Previously, a spatial-only scan — browser frame extraction without a usable frame interval, or a decode failure — could read `AUTHENTIC_HUMAN` on the strength of spatial layers alone, exactly when the only layers that can see generation were silent; that case now reads INCONCLUSIVE and is excluded from both flagging and the page's clean-score math.

Several failure modes were fixed in the video ensemble so two different videos can no longer produce identical verdicts: the SynthID probe no longer emits a fabricated hard-coded 68 from spectral noise; the per-frame score trajectory runs real frequency forensics instead of a seeded RNG; the GAN-grid frequency rule is disabled for video frames (every H.264-decoded frame rings periodically after the 512×512 upscale, so the rule fired ~10 on *all* video); the flat-render/cel-shaded signature no longer votes on video frames (it detects saturated cartoon *style* — it fired on 74% of frames of a real hand-drawn animation reel and 0 frames of a generated photorealistic clip); and on video, a lone strong temporal reading can no longer escalate the fused score without spatial agreement (video escalation cap: 55 unless spatial layers corroborate; a pwtf ≥ 60 — reachable only via coherence-floor collapse — lifts the verdict to at most the suspicious band).

The layer is deliberately conservative: mild compression or a moving camera does not trip it on its own — it is one weighted vote in the ensemble (`pwtf` weight 0.14, active only for video).

### Temporal coverage sweep: where the artifact was hiding (2026-10-16)

Two known-AI Instagram reels were reading `AUTHENTIC_HUMAN` (19 and 16). Tiling each clip into **all** of its consecutive 32-frame windows and scoring every one with the same layers the verdict uses showed the detector was not blind — it was **looking in the wrong place**: one reel collapses its coherence floor to `0.00` (the calibrated 62 signature) in 5 of its 8 windows, while the single shot-aware window the pipeline analyzed happened to be one of the healthy ones (`p05 = 0.65`); the other fires the temporal-residual probe in 9 of its 14 windows.

Every server-side video scan now also runs a **coverage sweep**: up to 8 consecutive windows across the first 384 frames (`VIDEO_COVERAGE_MAX_FRAMES`, `VIDEO_COVERAGE_MAX_WINDOWS`), each scored by PwTF-DVD and the temporal-residual probe. The result is reported in the verdict as `temporal_coverage` (per-window records plus `flagged` / `analyzed` / `flagged_frac` / `collapse_windows` / `tr_windows`), and the sweep deliberately does **not** feed the existing escalation paths, so previously calibrated verdicts do not move.

**The honest limit, measured at the same time:** repeated *partial* collapse is not unique to generated clips. The clip then believed to be the repo's real reference (`test videos/vid2.mp4`) collapsed in 6 of its 15 windows and fired the residual probe in 4 (67% of windows) — more than any other negative — and a window-by-window comparison of coherence floor, spectral flatness, residual autocorrelation, residual whiteness, temporal variance, D3 volatility and interframe motion found **no statistic that separated the two missed reels from it**. So escalation from repeated *partial* coverage stayed opt-in:

| `COVERAGE_MODE` | repeated partial evidence (≥ 3 windows and ≥ 50%) | measured cost |
|---|---|---|
| `review` (**default**) | floors the verdict at **INCONCLUSIVE** — no longer "authentic", not accused of being AI | none on the real clips (they stay authentic) |
| `flag` | floors at **69 SUSPICIOUS** (capped 79, never SYNTHETIC_AI) | any clip with that partial signature, including `vid2` |
| `off` | rule disabled | — |

### Two stricter coverage signatures are scored by default (2026-10-22)

The 2026-10-22 batch added 20 more AI reels; three of them read `40 INCONCLUSIVE` with HIGH confidence, and re-measuring exposed both a second discriminator and a bad label:

- **`vid2`/`vid3` are generated, not real.** They are the same file byte for byte (identical SHA-256) — the "two real reference clips" were one clip counted twice — and it is generated footage: the pigeon in the subject's hand morphs into a pastry/rock between frames 83–154 while the hand pose is unchanged, the motorcycle/chair/vacuum props sit in the scene without contact shadows or consistent perspective, the render is 24 fps, and it carries burned-in "believe anything / can be fake / get tricked" captions. They are now labelled AI in `tests/test_videos.py`, which removes the only negative that made repeated collapse unusable.
- **Two signatures never occur on the authentic reels in the corpus**, measured on 32-frame windows over the first 384 frames: a **total** collapse (`p05 < 0.10`) repeated in **≥ 2 windows** (AI 4/12 and 2/12; authentic 0/7 and 1/7), and a temporal-residual fire whose **residual white-fraction ≥ 0.55** (AI 0.73 / 0.59; authentic at most 0.42). Both now floor the verdict at **69 SUSPICIOUS** (cap 79, never SYNTHETIC_AI), independent of `COVERAGE_MODE` and still skipped for a confirmed camera/watermark override. The sweep reports the counts as `deep_collapse_windows` and `white_windows`, and each window record carries `white`, `deep_collapse` and `tr_score`.

Measured effect on the three misses (defaults, cache bypassed): `ig-DeeYNdsMiqC` 40 → **69 SUSPICIOUS**, `ig-DeTtabsthXY` 40 → **69 SUSPICIOUS**, `ig-DeppmpCtSnZ` 40 → **69 SUSPICIOUS**; the two confirmed-authentic reels are unchanged (`ig-DecK8wQPTM7` 24, `ig-human-post-01` 12, both `AUTHENTIC_HUMAN`).

The sweep costs extra temporal work per scan (~+15-25 s on a 720×1280 15 s reel with the shipped defaults); lower `VIDEO_COVERAGE_MAX_WINDOWS` or use `COVERAGE_MODE=off` on a latency-constrained deployment.

## Audio track: a separate axis, reported and never scored (A0)

Video scans also decode and measure the clip's **audio track** (`forensics/audio_track.py`, phase A0 of [`docs/audio-and-lip-sync-plan.md`](docs/audio-and-lip-sync-plan.md)). It decodes mono float32 at 48 kHz with ffmpeg — from the **same bytes the frames came from**, so a link scan never downloads the clip twice — and reports the result in the verdict as an `audio` block plus plain-language lines in `reasons`.

**It never votes.** A synthetic voice over real footage is an *audio-AI* finding, not a deepfake video, so audio is a separate axis: `audio.score` is always `null`, it never appears in `breakdown`/`layers_active`, and no audio condition can move the video tier. It abstains with a reason when there is nothing to decode (client-extracted frames carry no container audio; a video-only download or a silent clip has no stream).

What it reports: duration, sample rate, loudness (RMS/peak dBFS), active/silent frame fractions, zero-crossing rate, **effective bandwidth** (99% energy), high-frequency share above 8/16 kHz, spectral centroid and flatness, loudness-envelope dynamics, and syllable-rate (2–8 Hz) modulation. `audio.kind` is `speech` / `nonspeech` / `silence` / `unavailable`.

**Honest limits, by design:** `speech` comes from energy/periodicity heuristics (a swinging loudness envelope, 2–8 Hz modulation, energy in the 300–3400 Hz speech band), not a speech classifier — strongly rhythmic music can satisfy it, which is why a low tremolo tone with no speech-band energy is correctly reported as `nonspeech`. And a **narrow bandwidth is a lead, not evidence**: it is common in vocoder/TTS re-synthesis, but lossy music and older recordings share the signature (measured: a real local clip reads 3.2 kHz while an AI reel reads 1.4 kHz). Synthetic-speech *detection* (A3/A4 of the plan) and AV lip-sync (A1) are not implemented yet; they arrive behind flags after calibration on a real-vs-TTS corpus. Check the layer with `.venv/bin/python scripts/check_audio_track.py`.

## D3 second-order dynamics: metrics layer (ICCV 2025, direction-corrected)

Video deep scans also run **D3** (Zheng et al., ICCV 2025, [arXiv:2508.00701](https://arxiv.org/abs/2508.00701)) — **"Detection by Difference of Differences"** — which measures the **second-order temporal dynamics** of the video's feature trajectory: the first-order feature is the feature-space distance between consecutive frames ("velocity"), the second-order feature is the central difference of that sequence ("acceleration").

**Direction warning:** popular summaries frequently state this backwards. The paper's finding is that **real** videos have **chaotic, spiky** second-order dynamics (sensors, optics and codecs keep perturbing frame distances), while generated videos are **too smooth** — motion interpolation produces nearly linear velocity sequences and a nearly flat acceleration profile. Low volatility ⇒ generation-like; high volatility ⇒ physical. (On GenVideo the method reaches 98.46% mAP, +10.39% over the prior state of the art.)

On this server D3 ships as a **metrics layer, not a voting layer** (verdict fields `d3_metrics`, `straighten_metrics`, plus a per-window `d3_volatility` in `window_details`). The reason is a measured negative calibration result, in the same spirit as the PwTF entropy/hf-share rules that had to be retired: the paper's statistic is computed on features from a **semantic encoder** (XCLIP-B/16; DINOv2/MobileNet-v3 also validated), and in that space "too smooth" is separable. This stack is numpy/PIL-only (detectzoo exposes classifier scores, not embeddings), and in pixel/patch feature space every variant we tested **overlaps or anti-correlates** — `python -m forensics.eval_d3` reproduces the table:

| Candidate statistic | Real-like range | Generation-like range | Verdict |
|---|---|---|---|
| global volatility `std(accel)/mean(vel)` | 0.10 – 0.59 | 0.05 – 0.42 | overlap |
| scale-invariant `std(accel)/std(vel)` | 0.74 – 1.72 | 1.47 – 1.66 | overlap |
| per-region second-order volatility | 0.15 – 1.08 | 0.99 – 1.04 | overlap (motion-dependent) |

A tripod pan of real footage (velocity dominated by codec noise → high *relative* volatility) is indistinguishable from, or smoother than, locally regenerated content. Voting on any of these would false-positive ordinary real motion — so the layer reports the statistics and abstains (`score: None`), and the fusion treats a hypothetical `d3` vote as temporal-family evidence that can never escalate alone.

**Upgrade path:** provide semantic frame embeddings (e.g. torch + DINOv2/XCLIP on the HF Space deployment) via `analyze_second_order_dynamics(..., encoder_embeddings=Z)` and calibrate per-encoder thresholds on real social footage with the `forensics/eval_d3.py` harness before enabling the vote.

The same module also reports **ReStraV-style trajectory geometry** (Internò et al. 2025, [arXiv:2507.00583](https://arxiv.org/abs/2507.00583) — perceptual straightening: stepwise distances and curvature angles of the representation trajectory). Those statistics are informational for the same reason: the published detector's straightening property holds in DINOv2 space (97.17% accuracy on VidProM with a trained classifier), which is again an encoder-space result.

Not implemented on purpose: heuristic "physics" checks (shadow direction, lighting coherence, contact physics). The published physics-driven detector (Zhang et al., NeurIPS 2025, arXiv:2510.08073) uses learned models; hand-built shadow heuristics would repeat this repo's documented anti-correlation failures (the retired flat-render rule fired on 74% of frames of a real hand-drawn animation reel). It belongs on the roadmap behind trained models, not in this numpy stack.

### Fusion & confidence changes

- **UNCERTAIN tier:** fused scores of 55–68 with non-HIGH confidence now read `UNCERTAIN` instead of `SUSPICIOUS`. These are the escalated-but-unconfirmed readings (a lone strong layer, single-window temporal evidence, layer disagreement) where a decisive-sounding tier misled users; a HIGH-confidence 55–68 (several agreeing layers) still reads `SUSPICIOUS`.
- **Single-window outlier downgrade:** when temporal evidence is strong in exactly one shot window while every other window reads clean, confidence drops one level — localized artifacts are plausible, but a lone window should not carry a confident verdict.
- **Extreme layer disagreement** (spread ≥ 70) now downgrades confidence to LOW instead of stopping at MEDIUM.
- The extension's tier fallbacks now mirror the server's exact thresholds (80/55/35) instead of inventing a 75/50 split.

## Deployment Guide

### Chrome Extension Deployment

To load and test the extension locally:
1. Run the build script to generate production assets:
   ```bash
   npm run build
   ```
2. Open Google Chrome and go to `chrome://extensions`.
3. Turn on Developer mode using the switch in the top right corner.
4. Click the Load unpacked button in the top left corner.
5. Select the `dist` folder located in your project directory.

To publish the extension to the public:
1. Compress the contents of the `dist` directory into a ZIP archive.
2. Upload this ZIP archive to the Chrome Developer Dashboard to publish it on the Chrome Web Store.

### Python API Server Deployment (Hugging Face Spaces)

The backend ships as a **Gradio-SDK Space** with the Flask API mounted on the
Space root — the only shape a free account can host (ZeroGPU Spaces; Docker and
`cpu-basic` hardware need a paid plan). Everything runs on CPU; the single
`@spaces.GPU` function is a no-op that exists only to satisfy the ZeroGPU
runtime and never burns quota.

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

`packages.txt` installs ffmpeg (video decode, yt-dlp merges, audio track) and
libglib2.0-0 (required by `opencv-python-headless`).

Verify, don't trust a green RUNNING badge:

```bash
curl -s https://<user>-rinse-detector.hf.space/health
# "detectzoo_loaded": true  — false means the neural layer fell back to
# simulation mode and every scan is running without it.
```

Then set the extension's API URL to `https://<your-username>-<your-space-name>.hf.space`
(the extension accepts the bare host) and the API key to the same `API_KEY`.
Endpoints and payloads are unchanged. Full guide plus Render / Oracle / Azure
targets: [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

## Dev Tools

### Backend health endpoint

`GET /health` (aliased as `GET /v1/health`) is a lightweight probe the extension uses to confirm backend connectivity. It returns server identity, version, uptime, engine mode (`heuristic`/`llm`), whether DetectZoo loaded, whether auth is required, and the active detector layers/endpoints:

```bash
curl http://localhost:5001/health
# {"status":"ok","server":"RINSE Cloud Detector","version":"1.0.0","uptime_seconds":12.4,"mode":"heuristic","layers":["synthid","c2pa","frequency","neural","temporal","pwtf"],...}
```

The extension resolves the base URL from the cloud API setting (a trailing `/predict...` suffix is stripped), so both local (`http://localhost:5001`) and hosted (`https://...hf.space`) deployments work without extra config.

### Detector tests (text / image / video)

Three runnable test files exercise the real detector code over the repo's own corpus and print the score every detector returns:

```bash
.venv/bin/python tests/test_text.py     # StoryScope + DNA-DetectLLM scores
.venv/bin/python tests/test_images.py   # /predict/image/deep fused score + tier
.venv/bin/python tests/test_videos.py   # /predict/video/deep score + tier + PwTF p05
```

Each file runs **in-process by default** — it imports the Flask app and drives it through its test client, so no server process is needed — or against a running server with `--live http://localhost:5001` — pointing `--live` at the deployed Space (`--live https://senkmonkham-rinse-detector.hf.space`) runs the same corpus against production, and `--key`/`$RINSE_API_KEY` supplies the bearer key that server requires. Useful flags: `--ids <id,id>` for a subset, `--audit` (video: print the per-window temporal evidence), `--skip-instagram` (local clips only), `--remote-images` (also scan the registered Brave-proxy image URLs), and `--use-cache` (the default sends `no_cache=true`, so every verdict is freshly computed). `tests/test_text.py` needs no network; `tests/test_videos.py` resolves the Instagram posts with yt-dlp exactly like the extension does (browser-cookie fallback included).

Corpus: `demo-samples/texts/` + the StoryScope evasion samples + the humanizer outputs (text), `tests/calibration_corpus/{ai,real}/` (images), and `test videos/` plus the Instagram posts registered in `tests/detector_assets.json` and `tests/media_test_assets.json` (videos — the latter holds the 30 added links; `ig-DecK8wQPTM7` is labelled `human` there because the user confirmed it is authentic). Each run prints a per-asset score line and a `SCORES` recap, and merges the raw evidence (scores, tiers, PwTF/window metrics, reasons) into `tests/media_test_results.json`. The exit status is 0 only when no labeled asset FAILs and nothing errored; assets that are deliberately unasserted (single frames extracted from generated reels) or unlabeled are reported **score-only**.

Current known reds, kept visible on purpose:

- `demo-samples/texts/human-written.txt` reads ~79 (AI) under StoryScope's offline heuristic engine while DNA-DetectLLM reads ~23 (human) — a short, non-narrative post, i.e. the input the heuristic caveats above warn about.
- **No video reds as of 2026-10-22** — the full video suite is 59/59 with the default settings and the cache bypassed. The five reels that used to read `40 INCONCLUSIVE` (`ig-DecC6x-zvBF`, `ig-DecPhb-iBFr`, `ig-DeeYNdsMiqC`, `ig-DeTtabsthXY`, `ig-DeppmpCtSnZ`) now read `69 SUSPICIOUS` on the repeated total-collapse / residual-whiteness rules, and both confirmed-authentic reels stay `AUTHENTIC_HUMAN` (24 and 12). See the coverage-sweep section for the measured margins behind those rules.

### Extension dev tools

The popup shows a **Dev Tools** card (extension mode only) with:
- **Backend** — live connection status dot, endpoint, latency, server version/mode/uptime, DetectZoo state, and a **Re-test** button that re-pings `/health`.
- **Engine** — `Heuristics (Offline)` vs `Cloud API` + the configured URL.
- **Stats** — cumulative lifetime counters (scans, text/image/video flags) tracked by the service worker on every scan, plus last-scan time.

Stats are stored under `devStats` in `chrome.storage.local` (separate from the 50-entry `scanHistory` cap); backend health lives under `backendStatus`. Both are exposed to the popup via the `getDevStats` / `checkBackend` runtime messages.
