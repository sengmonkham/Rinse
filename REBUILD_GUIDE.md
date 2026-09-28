# RINSE — Rebuild Guide

How to recreate this project **from an empty folder**, with the core logic of every subsystem explained as you build it. Companion to `CRASH_COURSE.md` (which describes the existing code); this file teaches you how to build it again and *why each piece works*.

**Final deliverables**

```
rinse/
├── public/            # extension runtime files (copied verbatim into dist/)
│   ├── manifest.json
│   ├── background.js  # MV3 service worker — the only caller of the backend
│   └── content.js     # injected into every page — DOM scanning + UI
├── src/               # React popup/dashboard (Vite)
│   ├── App.tsx, main.tsx
│   └── components/    # Popup.tsx, Playground.tsx, Settings.tsx, PageHistory.tsx
├── forensics/         # Python forensic layers (one file per layer)
│   ├── synthid.py c2pa.py frequency.py neural.py spai.py
│   ├── temporal.py pwtf.py d3.py        # video layers
│   └── voter.py                         # weighted fusion
├── storyscope/        # narrative AI-fiction detection (optional phase)
├── server.py          # Flask API
└── dist/              # built extension — what Chrome loads
```

**Prerequisites:** Node 20+, Python 3.11+, pip packages `flask flask-cors requests pillow numpy` (optional: `detectzoo opencv-python-headless yt-dlp`), and 30 minutes.

---

## Phase 0 — Scaffolding

```bash
mkdir rinse && cd rinse
npm init -y
npm i react react-dom lucide-react
npm i -D vite @vitejs/plugin-react typescript @types/react @types/react-dom
mkdir -p public src/components forensics storyscope
```

`vite.config.ts` — plain Vite; everything under `public/` is copied to `dist/` automatically, which is how `content.js`, `background.js` and `manifest.json` end up next to the built React bundle:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({ plugins: [react()] })
```

### The manifest (MV3)

```json
{
  "manifest_version": 3,
  "name": "RINSE - Remove Inauthentic Noise",
  "version": "1.0.0",
  "permissions": ["activeTab", "storage", "contextMenus", "alarms"],
  "host_permissions": ["<all_urls>"],
  "action": { "default_popup": "index.html#popup" },
  "background": { "service_worker": "background.js" },
  "content_scripts": [{ "matches": ["<all_urls>"], "js": ["content.js"], "run_at": "document_end" }]
}
```

Core logic notes:
- `<all_urls>` host permission is what lets `background.js` fetch any image URL without CORS problems (extension pages are exempt from page CORS for hosts declared here) — the content script itself should **never** fetch cross-origin media.
- MV3 service workers are **event-driven and killable**: never rely on in-memory state surviving between events; read settings from `chrome.storage.local` inside each handler.

---

## Phase 1 — Backend skeleton

`server.py`:

```python
import os, io, base64, tempfile
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})   # the extension is a browser client

API_KEY = os.environ.get("API_KEY", "")
MAX_IMAGE_BYTES = 20 * 1024 * 1024

def _check_auth():
    if not API_KEY:
        return True
    return request.headers.get("Authorization", "") == f"Bearer {API_KEY}"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "server": "RINSE Cloud Detector"})

@app.route("/predict", methods=["POST"])
def predict():
    if not _check_auth():
        return jsonify({"error": "Unauthorized."}), 401
    data = request.get_json() or {}
    # payload handling — Phase 2
    ...
```

CORS is required because the **React popup** runs on `chrome-extension://<id>` origin and calls the server directly (the content script doesn't fetch; it messages the service worker).

### Payload handling with the proxy-URL trick

This is the function that makes search-result images scannable. Core logic: search CDNs (Brave, Google Images proxying) 403 any non-browser fetch, but they embed the **original URL base64-encoded in the last path segment**. Decode it, prefer the original.

```python
from urllib.parse import urlparse

def _decode_proxy_original_url(url):
    """https://imgs.search.brave.com/<sig>/rs:fit:.../g:ce/aHR0cHM6... → original URL."""
    try:
        parsed = urlparse(url)
        if (parsed.netloc or "").lower() != "imgs.search.brave.com":
            return None
        segments = [s for s in parsed.path.split("/") if s]
        b64 = segments[-1] if segments else ""
        if len(b64) < 16:
            return None
        decoded = base64.urlsafe_b64decode(
            (b64 + "=" * (-len(b64) % 4)).encode("ascii")).decode("utf-8", "strict")
        return decoded if decoded.startswith(("http://", "https://")) else None
    except Exception:
        return None

def _download_image_bytes(url, timeout=15):
    resp = requests.get(url, headers={"User-Agent": "RINSEAuthenticityDetector/2.0"},
                        timeout=timeout, stream=True)
    if not resp.ok:
        resp.close()
        raise requests.HTTPError(f"HTTP {resp.status_code} for {url}")
    chunks, total = [], 0
    for chunk in resp.iter_content(64 * 1024):
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            resp.close(); raise ValueError("too large")
        chunks.append(chunk)
    resp.close()
    return b"".join(chunks)

def _load_image_from_payload(data):
    """Returns (img, raw_bytes, temp_file, error_tuple)."""
    image_url, image_b64 = data.get("image_url"), data.get("image_base64")
    if not image_url and not image_b64:
        return None, None, None, (jsonify({"error": "No image source provided."}), 400)
    raw_bytes, temp_file = b"", None
    try:
        if image_b64:
            if "," in image_b64:
                image_b64 = image_b64.split(",", 1)[1]        # strip data: prefix
            raw_bytes = base64.b64decode(image_b64)
        else:
            if urlparse(image_url).scheme not in ("http", "https"):
                return None, None, None, (jsonify({"error": "Only http(s) URLs."}), 400)
            candidates = []
            decoded = _decode_proxy_original_url(image_url)
            if decoded:
                candidates.append(decoded)                    # original first
            candidates.append(image_url)                      # proxy as fallback
            last_err = None
            for cand in candidates:
                try:
                    raw_bytes = _download_image_bytes(cand); break
                except Exception as e:
                    last_err = e
            else:
                raise last_err
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(raw_bytes); temp_file = f.name
        return Image.open(io.BytesIO(raw_bytes)).convert("RGB"), raw_bytes, temp_file, None
    except Exception as e:
        return None, None, None, (jsonify({"error": f"Failed to load image: {e}"}), 400)
```

Why the User-Agent matters less than you'd think: CDNs fingerprint TLS + header order, so spoofing Chrome usually doesn't beat hotlink protection — decoding the embedded URL is the reliable path, and relaying bytes from the browser (Phase 6) is the second line.

---

## Phase 2 — The five forensic layers (core logic)

**Design contract:** every layer is a pure function `Image → {score: int|None, reason: str, ...}`. `score=None` means "this layer is inconclusive here" and the voter **renormalizes around it** — a layer that can't speak never drags the verdict toward "real" (which a naive 0 default would do).

### Layer 2 — C2PA / metadata provenance (`c2pa.py`) — build this first, it's pure string work

Core logic: signed Content Credentials (C2PA/JUMBF) embed `digitalSourceType: trainedAlgorithmicMedia` claims; generators also leak EXIF/XMP strings. Search raw file bytes:

```python
AI_GENERATOR_KEYWORDS = ["dall-e", "midjourney", "stable diffusion", "firefly",
                         "craiyon", "flux", "sora", "runway", "ideogram", "leonardo"]
CAMERA_MANUFACTURERS  = ["canon", "nikon", "sony", "leica", "fujifilm", "google pixel"]

def probe_c2pa_manifest(img, raw_bytes=b""):
    blob = raw_bytes or b"..."
    low = blob[:64 * 1024].lower()
    if b"c2pa" in low or b"jumb" in low or b"trainedalgorithmicmedia" in low:
        return {"score": 99, "reason": "C2PA Content Credentials manifest claims AI generation."}
    s = str(getattr(img, "info", {})).lower()
    for kw in AI_GENERATOR_KEYWORDS:
        if kw in s:
            return {"score": 98, "reason": f"Generator metadata signature: '{kw}'."}
    for mfr in CAMERA_MANUFACTURERS:
        if mfr in s:
            return {"score": 2, "reason": f"Camera EXIF present ({mfr}) — strong authenticity signal."}
    return {"score": None, "reason": "No C2PA manifest embedded."}
```

Key idea: absence of metadata is **not** evidence of authenticity (everything strips metadata), so no-signal returns `None`, not 0.

### Layer 1 — SynthID probe (`synthid.py`)

Core logic: Google's SynthID is an *imperceptible* watermark — a weak periodic carrier pattern across pixels. You can't decode it without Google's key, but you can detect a **spectral residual correlation**: high-pass the image, fold it across its 2D FFT, and see whether energy concentrates along a lattice the way a tiled carrier would. Metadata mentions ("synthid", "imagen") are the cheap positive; the correlation is the soft positive.

```python
def probe_synthid_watermark(img):
    info = str(getattr(img, "info", {})).lower()
    if "synthid" in info or "google imagen" in info:
        return {"present": True, "score": 99, "reason": "SynthID metadata marker present."}
    arr = np.asarray(img.convert("L").resize((512, 512)), dtype=np.float32) / 255.0
    hp = arr - np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(3)), dtype=np.float32) / 255.0
    spec = np.abs(np.fft.fftshift(np.fft.fft2(hp)))
    folded = spec.reshape(16, 32, 16, 32).sum(axis=(1, 3))       # fold 512→16 lattice
    carrier_strength = float(folded.std() / (folded.mean() + 1e-9))
    present = carrier_strength > THRESHOLD                        # calibrate on real photos!
    return {"present": present,
            "score": 90 if present else None,
            "reason": "Carrier lattice detected." if present else "No watermark carrier."}
```

**Calibration rule:** thresholds must be tuned on real photos, or you flag every JPEG grid as SynthID.

### Layer 3 — Frequency forensics (`frequency.py`)

Core logic — three independent spectral tells:
1. **GAN grid peaks**: upsample layers are deconvolutions with even kernel sizes → periodic checkboard residue → spikes at multiples of the same frequency in the 2D DFT. Measure: fold the spectrum onto a 16×16 grid, look at peak energy vs. neighbors.
2. **Diffusion HF deficit**: diffusion outputs are slightly oversmooth → less high-frequency energy than camera optics/sensors produce. Measure: wavelet ratio = (energy in finest HH band) / (total).
3. **1/f slope**: natural spectra fall off as `1/f^α` with α in a known range. Measure: radial-average log-log slope.

```python
def analyze_frequency_domain(img):
    g = np.asarray(img.convert("L").resize((512, 512)), dtype=np.float32) / 255.0
    spec = np.abs(np.fft.fftshift(np.fft.fft2(g))) + 1e-9
    log_spec = np.log(spec)

    # (1) grid peaks: 32x32 block energy concentration
    blocks = log_spec.reshape(16, 32, 16, 32).mean(axis=(1, 3))
    grid_peaks = float(blocks.max() / (np.median(blocks) + 1e-6))

    # (2) Haar HH-wavelet energy deficit
    coeffs = _haar_hh(g)          # one-level Haar detail band
    wavelet_ratio = float(coeffs.var() / (g.var() + 1e-9))

    # (3) radial 1/f slope
    slope = _radial_loglog_slope(log_spec)     # ~ -1.0..-2.0 natural

    reasons, votes = [], []
    if grid_peaks > 6:   votes.append(80); reasons.append(f"Periodic spectral grid peaks ({grid_peaks:.1f}) — GAN upsampling signature.")
    if wavelet_ratio < 0.005: votes.append(75); reasons.append(f"Wavelet HF deficit ({wavelet_ratio:.4f}) — synthetic smoothness.")
    if slope > -0.8:     votes.append(70); reasons.append(f"Flat spectral slope ({slope:.2f}) — no natural 1/f roll-off.")
    return {"score": max(votes) if votes else None, "reasons": reasons,
            "metrics": {"grid_peaks": grid_peaks, "wavelet_ratio": wavelet_ratio, "slope": slope}}
```

For video frames, **disable the grid-peak rule**: H.264 encodes every frame at 512-aligned macroblocks, so *both* real and generated clips show grid peaks (a measured false positive).

### Layer 5 — SPAI (`spai.py`, CVPR 2025 approximation)

Core logic: train-free spectral reconstruction. Mask part of the 2D spectrum, try to reconstruct the masked bands from the visible ones (local autoregression over the log-spectrum), and measure reconstruction error. Real spectra are *predictable* from their neighbors (natural 1/f structure); AI spectra deviate from that predictability. Resolution-invariance comes from comparing against expected statistics at the same scale.

Minimal scoring: compute the masked-reconstruction error map, standardize it against a natural-image prior, map to 0–100. The shipped version adds quadrant heterogeneity and spectral-slope features. (Full detail in `forensics/spai.py` — ~450 lines, numpy only.)

### Layer 4 — Neural classifier (`neural.py`)

The only layer that needs weights:

```python
from detectzoo import load_detector       # pip install detectzoo
detector = load_detector(os.environ.get("MODEL_NAME", "cnnspot"), device="cpu")
# per image: detector.predict(pil_image) → probability of "synthetic"
```

- `cnnspot` — 280 MB, fast, good on GAN-era and diffusion images.
- `univfd` — 1.7 GB, stronger on modern diffusion output.
- Supplement with a **16×16 ViT-style patch heatmap**: run the classifier on overlapping patches (or CLIP patch embeddings), mark patches that deviate from the image's own texture norm → `heatmap_grid` + `synthetic_patches_count` for the UI. Important honesty rule baked into the code: a patch being *locally* anomalous is "a regional highlight, not an absolute AI verdict" — it feeds reasons, not the headline score, unless the classifier is loaded.
- **If DetectZoo is missing** the layer returns `score=None` with the honest reason "No trained neural classifier available" — and the whole stack drops to frequency+SPAI, i.e. "UNCERTAIN" on photorealistic AI images. This is exactly why installing detectzoo matters.

### The voter (`voter.py`) — where a verdict is born

```python
WEIGHTS = {"synthid": 0.25, "c2pa": 0.20, "frequency": 0.12,
           "neural": 0.20, "spai": 0.15,
           # video-only: "temporal": 0.07, "pwtf": 0.14
           }

def fuse_ensemble_verdict(layers, layer_reasons, is_video=False, extra_data=None):
    available = {k: v for k, v in layers.items() if v is not None}
    if not available:
        return {"score": 50, "tier": "INCONCLUSIVE", "confidence": "LOW",
                "reasons": ["No forensic layer produced a signal."]}
    total_w = sum(WEIGHTS[k] for k in available)
    score = round(sum(v * WEIGHTS[k] for k, v in available.items()) / total_w)

    # hard overrides: a verified watermark/manifest outranks statistics
    if layers.get("synthid") == 99 or layers.get("c2pa") == 99:
        score = 99
    # video guard: lone temporal readings can't escalate (compressed thumbnails lie)
    ...
    tier = ("SYNTHETIC_AI" if score >= 80 else "SUSPICIOUS" if score >= 69 else
            "UNCERTAIN" if score >= 55 else "INCONCLUSIVE" if score >= 35 else "AUTHENTIC_HUMAN")
    confidence = "HIGH" if len(available) >= 4 else "MEDIUM" if len(available) >= 2 else "LOW"
    return {"score": score, "tier": tier, "confidence": confidence,
            "breakdown": available, "reasons": dedupe(layer_reasons), **(extra_data or {})}
```

Wire it up:

```python
@app.route("/predict/image/deep")
@app.route("/predict")
def predict_image_deep():
    data = request.get_json() or {}
    img, raw_bytes, tmp, err = _load_image_from_payload(data)
    if err: return err
    s1 = probe_synthid_watermark(img)
    s2 = probe_c2pa_manifest(img, raw_bytes)
    s3 = analyze_frequency_domain(img)
    s4 = analyze_neural_and_heatmap(tmp, img)
    s5 = spai.detect(img)
    verdict = fuse_ensemble_verdict(
        layers={"synthid": s1["score"], "c2pa": s2["score"], "frequency": s3["score"],
                "neural": s4["score"], "spai": s5["score"]},
        layer_reasons={...})
    return jsonify(verdict)
```

---

## Phase 3 — Video (temporal layers)

The **sampling strategy is half the correctness**. Core logic:

1. Decode at native fps. Grab frames cheaply, build 64×64 thumbnails, detect hard cuts by mean grayscale delta > 0.16.
2. Split into shots; keep shots with ≥32 frames; for each, start the analysis window **20% in** (skips fade-ins).
3. Analyze contiguous windows only — temporal statistics on uniformly-spaced frames spanning cuts are *worse than useless* (measured: they made a real clip look *more* AI than an AI clip).
4. `ffmpeg -vf fps=1/interval -frames:v 32 -f image2pipe` is the extractor; OpenCV `cap.grab()` streaming is the fallback; honest 503 when neither exists.

The two video layers, in one line each:

- **Temporal coherence** (`temporal.py`): per-pixel intensity traces over the window → 1D FFT along time → real footage is low-frequency-dominated and spatially coherent (physics persists); generated footage flickers incoherently. Requires a real `frame_interval_seconds` or it refuses to vote.
- **PwTF-DVD** (`pwtf.py`, ICCV 2025): per frame, keep the high-frequency residual `R_t = frame_t − median5(frame_t)`; stack residuals; per-pixel 1D FFT **along time**; unnatural high-temporal-bin energy in localized regions = generation artifact. The shipped version is a training-free numpy approximation of the paper's encoder.
- **D3** (`d3.py`, ICCV 2025): second-order motion. Feature "velocity" = distance between consecutive frames; "acceleration" = its central difference. **Smooth acceleration ⇒ AI; spiky ⇒ real** (this direction is constantly mis-stated). On this stack it's a metrics-only layer — pixel-space volatility didn't separate on social-media footage, so its voter weight is 0.0.

`/predict/video/deep` = spatial layers on the middle frame of each window + temporal layers per window; strongest window wins. The plain `/predict` also sniffs video payloads (`frames_base64`/`video_url`/`video_base64`) and routes them here, so one endpoint handles both media types. Social-page URLs (YouTube/Instagram/TikTok) resolve through `yt-dlp` with layered format selectors and a browser-cookie fallback for bot-walls.

---

## Phase 4 — Text detection

Two independent engines:

**DNA-DetectLLM** (zero-shot, 20+ chars). Core logic: define a statistical reference for "ideal LLM output" (char entropy ≈3.5–4.0 bits, type-token ratio ≈0.4–0.5, sentence-length CV ≈0.2–0.4, low n-gram novelty), compute the input's distance to that reference — the "repair score." AI text is already at the ideal (low repair); human text is farther. No training data needed, which is the whole point of the paradigm.

**StoryScope** (narrative-level, 80+ chars). Core logic: LLM fiction differs at the *story-structure* level — too-tidy conflict resolution, uniform pacing, explicit theme handling. Pipeline: `text → 304-feature taxonomy vector → XGBoost → probability + tells`. Build order:
1. `taxonomy.json` — the feature list (10 dimensions, categorical values).
2. `heuristic.py` — ~90 stdlib-only text statistics (sentence distributions, pronoun/tense counts, dialogue proportion, per-third intensity curves…) mapped onto canonical taxonomy values; features needing literary judgment → `n/a`.
3. `encoding.py` — one-hot encode categories *as seen in training*.
4. `scorer.py` — a dependency-free pure-Python XGBoost tree reader (`model_full.json`).
5. Optional LLM engine replaces step 2 via 10 per-dimension API calls.

The heuristic engine covers ~204/304 features; measured accuracy on the paper's released matrix and honest bounds are documented in `storyscope/eval_heuristic.py` and the README — treat heuristic verdicts as screening, not research-grade.

The extension's *in-page* text scan (`analyzeTextHeuristics` in content.js) is a separate, much simpler keyword/cadence/em-dash/emoji rule engine — deliberately local because text costs nothing to ship and needs no model. It labels its output "page/context heuristics" and never masquerades as the forensic ensemble.

---

## Phase 5 — Content script (`content.js`)

State: `scanResults` (the page's current verdict store), `extensionEnabled`/`scanSensitivity` (mirrored from `chrome.storage` + `storage.onChanged`), `hoveredElement`/`mouseX`/`mouseY`.

### 5.1 Page scan

```js
const performPageScan = async (options = { text: true, images: true, videos: true }) => {
  // text: run in-page heuristics per block element
  // images: for each <img> ≥50px → inspectImageMetadata(img.src)   [backend]
  // videos: capture contiguous frames from <video> via canvas at real fps
  //         → chrome.runtime.sendMessage({action:"analyzeVideoFrames",
  //              frames, frameIntervalSeconds})
}
```

Every image result funnels through `inspectImageMetadata`, which resolves relative URLs (`new URL(src, location.href)`) and maps the background's answers to three shapes:

```js
{ score: 87, tier, reasons }              // success
{ score: null, unscanned: true, reasons } // backend offline / unscannable
null                                      // scanned clean → DOM-context check may still flag
```

Page-declared AI labels (alt text, captions, URL markers) are gathered separately (`inspectImageDOMContext`) and only ever **max-merged on top** of a server verdict — they are the page's own claims, not forensics.

**Integrity score rule:** start at 100; subtract per flagged item (weighted by score); treat every `unscanned` item as a **scan failure** (cap the score and record it) — silence must never read as "clean."

### 5.2 The floating tooltip (the popup this whole saga was about)

```css
.aegis-floating-tooltip {
  position: absolute; width: 280px;
  background: #1E293B !important;        /* SOLID — blur is invisible on dark pages */
  border: 1px solid rgba(148,163,184,.35);
  border-radius: 12px; z-index: 2147483647;
}
```

Why each property is non-negotiable:
- **Solid background**: the original `background: transparent + backdrop-filter: blur` vanishes over dark images/gradients. If you want a translucent look anyway, keep a floor: `background: rgba(30,41,59,0.97)`.
- **Max z-index**: pages set z-index above 1,000,000,000 in practice; `2147483647` wins.
- **Viewport clamping** (below): at screen edges the tooltip rendered half off-screen — users read that as "the popup didn't appear."

```js
const positionTooltipInViewport = (el, x, y) => {
  const m = 12, w = el.offsetWidth, h = el.offsetHeight;
  const sx = window.pageXOffset, sy = window.pageYOffset;
  let left = x + 14, top = y + 14;
  if (left + w + m > sx + window.innerWidth)  left = Math.max(m, x - w - 14); // flip left
  if (top  + h + m > sy + window.innerHeight) top  = Math.max(m, y - h - 14); // flip up
  el.style.left = `${left}px`; el.style.top = `${top}px`;
};
// append → measure → clamp → THEN add .show (opacity transition)
```

Build the DOM with `createElement`/`textContent` only — the tooltip renders page-derived strings (alt text, reasons); `innerHTML` here would be an XSS hole.

### 5.3 Hover + Option-key scan — the reliability contract

Two bugs to avoid (both were real):
1. **Only listening for `mouseover` on P/SPAN/IMG…** — modern sites put text in DIVs, so hotkey scans silently did nothing. Accept any visible, non-extension element; exclude the extension's own UI (`closest(".aegis-drawer, .aegis-floating-tooltip, …")`) so scanning the tooltip can't loop.
2. **Relying on mouseover alone** — if the mouse stops after entering an element and the user presses Option, no new mouseover fires and your state can be stale. Track `mousemove` too (it's the same assignment, and it keeps `hoveredElement` honest).

```js
document.addEventListener("mousemove", (e) => {
  const el = e.target;
  if (el?.nodeType === 1 && !el.closest(".aegis-drawer, .aegis-floating-tooltip, .aegis-badge")) {
    hoveredElement = el; mouseX = e.pageX; mouseY = e.pageY;
  }
});
document.addEventListener("keydown", (e) => {
  if (e.repeat) return;
  if (e.target.closest?.("input, textarea, select, [contenteditable]")) return;
  const trigger = e.key === "Alt" || e.key === "Control"
               || (e.altKey && e.key.toLowerCase() === "a")
               || (e.ctrlKey && e.key.toLowerCase() === "a");
  if (trigger && hoveredElement) {
    chrome.storage.local.get(["extensionEnabled"], ({ extensionEnabled }) => {
      if (extensionEnabled !== false) triggerLocalScan(hoveredElement);   // read storage live
    });
  }
});
```

Show a *scanning…* tooltip instantly (perceived latency), then swap in the verdict. `e.repeat` guards against key-repeat double-scans; the storage read guards against a stale enabled-flag.

### 5.4 Video capture in-page

```js
const capture = () => {
  ctx.drawImage(video, 0, 0, w, h);
  frames.push(canvas.toDataURL("image/jpeg", 0.8));
};
const grabInterval = setInterval(capture, 33);   // ~30fps, contiguous!
```

Contiguity is the contract with the backend's temporal layers — see Phase 3. Send `frameIntervalSeconds: 1/30`; if you can't compute a real interval, send nothing and let the server disable temporal layers instead of feeding them aliased garbage.

---

## Phase 6 — Service worker (`background.js`)

One message handler per action; **all backend URLs normalized through one helper**:

```js
function resolveBackendBaseUrl(settings) {
  let base = (settings.apiUrl || "http://localhost:5001").trim();
  base = base.replace(/\/predict(\/.*)?$/, "").replace(/\/+$/, "");
  return base || "http://localhost:5001";
}
```

This one regex is the fix for the "flood of POST 404s" — a user setting `http://localhost:5001`, `:5001/`, or `:5001/predict` all end up POSTing to `{base}/predict`, which is the only route that exists.

**Health gate** — every scan checks reachability first, cached 30s:

```js
function ensureBackendConnected(callback) {
  chrome.storage.local.get(["backendStatus"], ({ backendStatus: cached }) => {
    if (cached?.checkedAt && Date.now() - cached.checkedAt < 30000) {
      callback({ connected: !!cached.connected }); return;
    }
    checkBackendHealth((res) => callback({ connected: !!(res?.data?.connected) }));
  });
}
```

**Image scan with browser relay** (hotlink-protected CDNs):

```js
ensureBackendConnected((health) => {
  if (!health.connected) {
    sendResponse({ status: "backend_offline", found: false, connected: false,
      error: `Not connected to the internet — the detection backend at ${base} is unreachable. No local scanning is performed.` });
    return;
  }
  const postPredict = (payload) =>
    fetch(`${base}/predict`, { method: "POST", headers, body: JSON.stringify(payload) })
      .then(async (res) => {
        if (!res.ok) { /* surface the server's JSON error verbatim */ }
        return res.json();
      })
      .then((data) => ({ status: "success", found: true, score: data.score,
                         tier: data.tier, reasons: data.reasons }));

  (async () => {
    try { sendResponse(await postPredict({ image_url: imgUrl })); return; }
    catch (err) {
      if (/failed to load image|forbidden|http 40[134]/i.test(err.message)) {
        const dataUrl = await fetchImageAsDataUrl(imgUrl);   // browser fetches (CORS-exempt host perms)
        if (dataUrl) { sendResponse(await postPredict({ image_base64: dataUrl })); return; }
      }
      sendResponse({ status: "error", found: false, error: err.message });
    }
  })();
});
return true;   // REQUIRED: keeps the message channel open for the async sendResponse
```

Three rules that bite if ignored:
- `return true` from `onMessage` for async responses, or the channel closes and the content script gets `undefined`.
- Server JSON errors are **forwarded verbatim** to the UI — the difference between "403 Forbidden" and "yt-dlp missing, install it" is the whole UX.
- The relay is *transport*, not analysis: the browser only ships bytes; scoring stays 100% server-side.

Context menus (`contextMenus.create` in `onInstalled`, `onClicked` handler), the 6-hourly subscription alarm, and `GET {webAppUrl}/api/v1/me` round out the worker.

---

## Phase 7 — React popup/dashboard

Vite multi-surface conventions:
- `index.html` loads `src/main.tsx`; hash routing picks the surface: `#popup` (compact), default (full dashboard/Playground).
- Read settings via `chrome.storage.local.get` with the same defaults as background.js (`apiMode: "local"`, `apiUrl: ""`…). When unset, the UI must show **"not connected"**, not silently default to localhost and start firing requests at nothing.
- The Playground POSTs directly to the backend (CORS is enabled for exactly this) using the same base-normalization regex as the worker — keep the two in sync or extract to a shared constant.

---

## Phase 8 — Build, load, verify

```bash
npm run build                                   # tsc + vite → dist/
# chrome://extensions → Developer mode → Load unpacked → select dist/
.venv/bin/pip install flask flask-cors requests pillow numpy
.venv/bin/pip install detectzoo                 # optional but decisive
.venv/bin/python server.py                      # :5001

curl -s localhost:5001/health | jq .status      # → "ok"
curl -s -X POST localhost:5001/predict \
  -H 'Content-Type: application/json' \
  -d '{"image_url":"https://pixlr.com/images/generator/photo-generator.webp"}' | jq .score
```

**Regression checklist** (each of these was a real bug — keep testing them):
1. Bare `apiUrl` without `/predict` → no POST 404s (base normalization).
2. Reload the extension after every rebuild — MV3 workers don't hot-reload; refresh tabs so old content scripts die.
3. Brave/Google image-proxy URL → scans via decoded original or browser relay (no "Failed to load image: 403").
4. Backend stopped → every surface says "not connected", integrity score treats items as unscanned, **no badges with made-up %**.
5. Tooltip over a dark hero image → solid background, fully on-screen.
6. Option-hover over a DIV of text → tooltip appears.
7. `detectzoo_loaded: false` in `/health` → photorealistic verdicts capped at UNCERTAIN; installing the model flips tiers.

---

## Appendix — data shapes (keep these stable)

```jsonc
// POST /predict request
{ "image_url": "https://…" }  |  { "image_base64": "data:image/png;base64,…" }
// POST /predict response
{
  "score": 62, "tier": "UNCERTAIN", "confidence": "MEDIUM",
  "breakdown": { "frequency": 80, "spai": 20 },
  "reasons": ["…", "…"],
  "layers_active": ["frequency", "spai"],
  "heatmap_grid": [[0.02,…]], "frequency_metrics": {"grid_peaks": 10.3, "slope": -1.72}
}
// POST /predict/video/deep request
{ "frames_base64": ["data:image/jpeg;base64,…"], "frame_interval_seconds": 0.0333 }
// content script internal result
{ "score": 87, "tier": "…", "reasons": [...] }        // scanned, flagged
{ "score": null, "unscanned": true, "reasons": [...] } // offline / unscannable — honest failure
```

## Appendix — the five calibration lessons (learn them before you write thresholds)

1. **Temporal sampling is load-bearing.** Contiguous native-fps windows or the temporal layers invert reality (measured anti-correlation on Instagram reels).
2. **A lone weak layer never escalates.** Single-layer high readings on compressed thumbnails produced identical "62/SUSPICIOUS" verdicts for real and AI clips → agreement rules in the voter.
3. **Style is not generation.** The flat-render/pixel signature fires on hand-drawn animation (31/61 frames of a real cartoon) — it's gated off video frames entirely.
4. **Direction of D3.** Too-smooth second-order motion = AI. Spiky = real. Get this backwards and the layer inverts.
5. **Absence of evidence ≠ evidence of authenticity.** No metadata, no watermark, inactive model → `None` + renormalize, never 0.
