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

Without yt-dlp the endpoint keeps the honest HTTP 415 advisory telling you to upload the file or paste a direct `.mp4`/`.webm`/`.mov` URL. Note that private, age-restricted, or login-walled posts cannot be resolved — download and upload the file in that case (X/Twitter videos in particular are increasingly login-walled; yt-dlp reports this clearly). yt-dlp must be kept up to date (`pip install -U yt-dlp`) because platforms change constantly. Because the forensic pipeline analyzes frames only, yt-dlp falls back to a **video-only** stream (e.g. YouTube's anonymous DASH offers no pre-merged A+V file) — no ffmpeg merge is needed, so servers without a working ffmpeg still analyze every platform.

**Download robustness (measured on real Instagram Reels and YouTube Shorts).** YouTube's modern pages offer no pre-merged A+V file at all, so the old two-selector chain failed with `Requested format is not available` and the video was never analyzed. The downloader now walks a layered selector chain, each a fallback in itself:

1. `best[ext=mp4]/best` — pre-merged A+V (Instagram, most direct sites)
2. `bv*+ba/b` — A+V **merge** via ffmpeg, only when a working ffmpeg is detected (YouTube DASH)
3. `bestvideo[ext=mp4]/bestvideo` — video-only, no merge needed (this is the one that always works for a frames-only pipeline)
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

Because deep learning models and PyTorch require significant memory (more than the 512MB limit provided on free tiers of services like Render or Koyeb), Hugging Face Spaces is recommended. It offers a free CPU tier with 16GB of RAM.

Follow these steps to deploy:
1. Create a Hugging Face account and navigate to Spaces.
2. Create a new Space, choose a name, and select Docker as the SDK (use the Blank template). Set hardware to CPU basic (Free) and visibility to Public.
3. Upload your `server.py` file, your `.detectzoo_data` directory containing the model weights, and create the following configuration files in the root of your Space:

#### requirements.txt
```text
flask
flask-cors
requests
pillow
yt-dlp
torch --extra-index-url https://download.pytorch.org/whl/cpu
detectzoo
```

#### Dockerfile
```dockerfile
FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY .detectzoo_data/ /app/.detectzoo_data/
COPY server.py .

ENV PORT=7860
EXPOSE 7860

CMD ["python", "server.py"]
```

4. Once the Space build completes and shows a green Running status, your API is live.
5. In your extension settings dashboard, set the API URL to:
   `https://<your-username>-<your-space-name>.hf.space/predict`

## Dev Tools

### Backend health endpoint

`GET /health` (aliased as `GET /v1/health`) is a lightweight probe the extension uses to confirm backend connectivity. It returns server identity, version, uptime, engine mode (`heuristic`/`llm`), whether DetectZoo loaded, whether auth is required, and the active detector layers/endpoints:

```bash
curl http://localhost:5001/health
# {"status":"ok","server":"RINSE Cloud Detector","version":"1.0.0","uptime_seconds":12.4,"mode":"heuristic","layers":["synthid","c2pa","frequency","neural","temporal","pwtf"],...}
```

The extension resolves the base URL from the cloud API setting (a trailing `/predict...` suffix is stripped), so both local (`http://localhost:5001`) and hosted (`https://...hf.space`) deployments work without extra config.

### Extension dev tools

The popup shows a **Dev Tools** card (extension mode only) with:
- **Backend** — live connection status dot, endpoint, latency, server version/mode/uptime, DetectZoo state, and a **Re-test** button that re-pings `/health`.
- **Engine** — `Heuristics (Offline)` vs `Cloud API` + the configured URL.
- **Stats** — cumulative lifetime counters (scans, text/image/video flags) tracked by the service worker on every scan, plus last-scan time.

Stats are stored under `devStats` in `chrome.storage.local` (separate from the 50-entry `scanHistory` cap); backend health lives under `backendStatus`. Both are exposed to the popup via the `getDevStats` / `checkBackend` runtime messages.
