# RINSE — Crash Course

RINSE (**R**emove **I**nauthentic **N**oise) is a **Chrome extension + Python forensic backend** that detects AI-generated **text, images, and video** on any web page — and an AI-written-fiction detector (**StoryScope**) for long-form narrative text.

The one-sentence version: *a content script watches pages, a service worker relays media to a Flask server, five independent forensic layers score the media, and a weighted voter fuses them into one honest verdict — if the backend is unreachable, the extension says "not connected" instead of guessing.*

---

## 1. The 30-second architecture

```
┌────────────────────────── CHROME EXTENSION ──────────────────────────┐
│                                                                       │
│  content.js (runs in EVERY page)                                      │
│   • finds text/images/video in the DOM                                │
│   • draws badges, highlights, hover tooltips, side drawer             │
│   • NEVER analyzes media itself → asks background.js                  │
│                                                                       │
│  background.js (MV3 service worker)                                   │
│   • single relay to the backend (all fetches to the API live here)    │
│   • health-gates every scan (30s cache)                               │
│   • relays image bytes when the server can't download a URL           │
│                                                                       │
│  React UI (Vite build → dist/, popup + dashboard + settings)          │
└──────────────┬────────────────────────────────────────────────────────┘
               │ HTTP (JSON) — /predict, /predict/video/deep, /health …
               ▼
┌────────────────────────── PYTHON BACKEND ────────────────────────────┐
│  server.py (Flask) — payload parsing, URL resolution, routing         │
│                                                                       │
│  forensics/ — image & video science (5 layers + voter)                │
│    synthid → c2pa → frequency → neural → spai  (+ temporal video)     │
│    voter.py — weighted fusion into the final verdict                  │
│                                                                       │
│  storyscope/ — AI-fiction detection for long narrative text           │
│    (taxonomy → feature extraction → XGBoost classifier)               │
└───────────────────────────────────────────────────────────────────────┘
```

**The golden rule of this codebase:** the extension *locates and displays*; the backend *analyzes and decides*. There is deliberately **no local image scanning** — when the backend is down, every surface reports "not connected" rather than inventing a score.

---

## 2. Repo map

| Path | What it is |
|---|---|
| `public/manifest.json` | MV3 manifest. `<all_urls>` host permission; content script at `document_end`. |
| `public/content.js` (~3.1k lines) | Injected into every page: DOM scanning, badges, hover tooltip, side drawer, page integrity score. |
| `public/background.js` (~690 lines) | Service worker: all backend fetches, health gate, context menus, subscription check. |
| `src/` | React UI (Vite + TypeScript). Popup, Playground (paste text/image/video), Settings, PageHistory. |
| `server.py` (~1.7k lines) | Flask API. Payload handling, video shot detection, image URL resolution. |
| `forensics/` | One file per forensic layer + the voter. Pure numpy/PIL. |
| `storyscope/` | Narrative-AI detector (heuristic engine default, optional LLM engine). |
| `dist/` | Built extension — load THIS folder in `chrome://extensions`. |
| `PLAN.md` | Future web-app/monetization plan (separate repo). |

---

## 3. The backend: five layers + a voter

Every image and video goes through independent detectors; `forensics/voter.py` fuses them.

| # | Layer (file) | Looks for | Weight (image) |
|---|---|---|---|
| 1 | **SynthID** `synthid.py` | Google DeepMind's invisible watermark via spectral-residual correlation + metadata | 0.25 |
| 2 | **C2PA** `c2pa.py` | Signed Content Credentials, `trainedAlgorithmicMedia` claims, generator EXIF tags | 0.20 |
| 3 | **Frequency** `frequency.py` | GAN upsampling grid spikes, diffusion high-frequency deficit, unnatural 1/f noise | 0.12 |
| 4 | **Neural** `neural.py` | Trained classifiers (CNNSpot / UnivFD via DetectZoo) + CLIP stats + 16×16 patch heatmap | 0.20 |
| 5 | **SPAI** `spai.py` (CVPR 2025) | Spectral reconstruction error — real images have characteristic 1/f spectra; AI deviates | 0.15 |
| — | **Temporal** `temporal.py`, **PwTF** `pwtf.py` (ICCV 2025), **D3** `d3.py` | Video-only: micro-flicker, pixel-wise temporal frequency, second-order motion smoothness | video: 0.07 / 0.14 / 0 |

**Fusion logic (voter.py):**
- Only layers that actually ran (`score != None`) vote; weights are renormalized over the available set.
- **Hard overrides win outright**: a verified SynthID watermark or C2PA `trainedAlgorithmicMedia` manifest → ~99 regardless of other layers.
- **Video escalation guard**: a lone high temporal score on compressed thumbnails can never escalate the verdict by itself — temporal layers must agree with a spatial layer (this killed a real bug where an AI reel and a real reel both came back "62 / SUSPICIOUS").
- Output shape: `{ score, tier, confidence, reasons[], breakdown{layer:score}, ... }` where tier ∈ `SYNTHETIC_AI / SUSPICIOUS / UNCERTAIN / INCONCLUSIVE / AUTHENTIC_HUMAN`.

**Calibration lessons baked into comments** (read them — they're the real education here):
- Temporal layers need **contiguous native-fps frames**; uniformly-spaced samples alias real motion into high temporal bins and *invert* the signal.
- D3's direction: **smooth second-order motion ⇒ AI**, spiky ⇒ real (frequently mis-stated in papers' summaries).
- The flat-render pixel signature detects cartoon *style*, not generation — it's barred from voting on video frames.

---

## 4. StoryScope (AI-fiction detection)

Detects AI-written **fiction by narrative structure** (plot shape, character agency, temporal structure, theme handling) instead of surface style — from Russell et al. 2026.

Flow: `text → 304-feature taxonomy vector → XGBoost classifier → AI probability + per-dimension tells`.

Two engines feed the same classifier:
- **heuristic (default)** — ~90 hand-built text statistics map onto 204/304 taxonomy features in milliseconds, stdlib only, no API key. Fast screening-grade.
- **llm (`STORYSCOPE_MODE=llm`)** — the paper's pipeline; an LLM annotates all 10 dimensions. Research-grade, needs `STORYSCOPE_LLM_API_KEY`.

Short texts (<80 chars) route to **DNA-DetectLLM** (`/predict/text/dna`) instead — zero-shot, works from 20 chars, measures how far the text sits from an "ideal LLM output" statistical reference (mutation-repair paradigm, NeurIPS 2025).

---

## 5. The extension: request lifecycle

### Page scan (toolbar → "Scan page")
```
content.js performPageScan()
  ├─ text    → analyzeTextHeuristics()        (in-page, keyword/cadence rules — text is cheap)
  ├─ images  → inspectImageMetadata(img.src)  ──chrome.runtime.sendMessage──▶ background
  │             background: ensureBackendConnected() → POST {base}/predict {image_url}
  │             server can't fetch the URL? → browser fetches bytes → resend {image_base64}
  └─ videos  → capture contiguous frames in-page → background → POST /predict/video/deep
                {frames_base64, frame_interval_seconds}
```
Results stream into: inline **badges** (`AI IMAGE 87%`), red/amber **highlights**, the **side drawer** (per-item reasons), and a page **integrity score**. Anything unscanned (backend offline, blob: URL, oversized) is recorded `score: null / unscanned` and counts as a **scan failure** in the integrity score — unscanned content is never silently counted as "clean".

### Hover + hotkey (Option/Alt, or Ctrl)
1. `mousemove`/`mouseover` track the deepest element under the cursor (`hoveredElement`).
2. Keydown (Alt/Option, Ctrl, or Alt+A/Ctrl+A) → `triggerLocalScan(element)`.
3. Images → backend scan → **solid-background tooltip** pinned at the cursor (viewport-clamped so it can't render off-screen). Text → in-page heuristic tooltip. Known AI-workbench domains (chatgpt.com, claude.ai, …) short-circuit to a 99% host audit.

### Right-click scan
Context-menu items (`Scan selection for AI patterns`, `Scan image for AI markers`) send messages into the same `inspectImageMetadata` / text pipeline.

### Health gate
`ensureBackendConnected()` (background.js) probes `{base}/health`, caches the result for 30 s, and **gates every image/video scan**. Offline ⇒ responses carry `status: "backend_offline"` ⇒ the UI prints *"Not connected to the internet — the detection backend at … is unreachable. No local scanning is performed."*

---

## 6. HTTP API (Flask, port 5001)

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Probe: uptime, which layers/models are loaded. |
| `/predict` (also `/predict/image/deep`, `/v1/predict`) | POST | Full image ensemble. Body: `{image_url}` or `{image_base64}`. Also transparently handles video payloads (`frames_base64`/`video_url`/`video_base64`). |
| `/predict/image/fast` | POST | Layers 1–3 only (<100 ms path). |
| `/predict/video/deep` | POST | Full spatio-temporal video ensemble. |
| `/predict/storyscope` | POST | `{text}` → narrative AI-fiction verdict. |
| `/predict/text/dna` | POST | `{text}` → DNA-DetectLLM zero-shot verdict. |

Optional bearer auth: set `API_KEY` env; extension sends `Authorization: Bearer …` from Settings.

**Image URL handling inside the server** (`_load_image_from_payload`): accepts `image_base64` or `image_url`; hotlink-protected proxies (search CDNs like `imgs.search.brave.com`) block server fetches with 403, so the server **decodes the original URL embedded in the proxy path** and tries it first, then the proxy URL as given.

**Video shot-aware sampling** (`server.py`): decodes at native fps, finds hard cuts, analyzes a contiguous window inside the richest shot (skips fade-ins, dedupes overlapping windows) — because the temporal layers are only meaningful on contiguous frames. `ffmpeg` first, OpenCV fallback; honest 503 if neither exists. Social-page URLs (YouTube/Instagram/TikTok…) resolve via optional `yt-dlp`.

---

## 7. Frontend (React) & settings

- **Popup** — connection status (live `/health` latency), quick toggles, mini results.
- **Playground** — paste text / image URL / video URL and scan directly against the backend.
- **Settings** — `apiMode` (`local` = heuristics-only text mode; `cloud` = backend), `apiUrl`, `apiKey`, feature toggles, sensitivity, `webAppUrl` + auth token for subscription checks (`GET /api/v1/me`).
- **PageHistory** — recent scans from `chrome.storage.local`.

Settings live in `chrome.storage.local` under `settings`; enable-state syncs to content scripts via `chrome.storage.onChanged`.

---

## 8. Day-to-day workflow

```bash
# backend
.venv/bin/pip install flask flask-cors requests pillow numpy detectzoo opencv-python-headless yt-dlp
.venv/bin/python server.py                # http://localhost:5001

# extension
npm install
npm run build                             # → dist/
# chrome://extensions → Developer mode → "Load unpacked" → select dist/
# after ANY change to public/ or src/: rebuild + hit Reload on the extension card
# + refresh open tabs (old content scripts keep running otherwise!)

npm run dev                               # popup/dashboard dev server (http://localhost:5173)
```

> **DetectZoo matters.** Without it the neural layer is inactive and photorealistic verdicts lean on frequency+SPAI only (typically "UNCERTAIN" for subtle AI images). Install `detectzoo` and restart the server; weights download on first load (`MODEL_NAME=cnnspot` default, `univfd` = stronger/1.7 GB).

### Debug checklist
| Symptom | Where to look |
|---|---|
| POST 404 flood on server start | Old extension build loaded in Chrome — rebuild + reload the extension + refresh tabs. |
| "Failed to load image: 403" in server log | Hotlink-protected CDN; server auto-retries embedded original URL; browser relay is the second line. |
| `detectzoo_loaded: false` in `/health` | Model not installed — see above. |
| Tooltip invisible on a dark page | Should be fixed (solid `#1E293B`); check you're on a fresh build. |
| Option-key scan does nothing | Fixed by mousemove hover tracking; ensure the tab was refreshed after reloading the extension. |

---

## 9. Design principles (the "why")

1. **No fabricated verdicts.** A `null` score means unscanned, and unscanned is *visible* (badges absent, integrity score penalized). This rule shapes content.js, background.js and voter.py alike.
2. **One analyzer.** All media analysis lives server-side. The extension's job is UX, not judgment.
3. **Honest degradation.** Offline, missing ffmpeg, missing yt-dlp, oversized files → specific error messages, never a made-up number.
4. **Research-grounded layers.** SPAI (CVPR 2025), PwTF-DVD (ICCV 2025), D3 (ICCV 2025), DNA-DetectLLM (NeurIPS 2025), StoryScope (2026) — each implemented as a training-free numpy approximation or with the paper's own released artifacts, with calibration lessons documented inline.
5. **Layer independence.** Any layer can be inactive (no DetectZoo, no watermark, no valid frame interval) and the voter renormalizes instead of pretending.
