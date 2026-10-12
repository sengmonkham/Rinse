---
title: RINSE AI Image & Video Detector
emoji: 🔍
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.28.0
app_file: app.py
short_description: Real forensic ensemble for AI image/video detection
startup_duration_timeout: 30m
python_version: "3.12"
---

# RINSE — AI image & video detector (real backend, hosted)

This Space runs the **complete RINSE forensic ensemble** — the same code that
powers the RINSE Chrome extension — as a public REST API plus a small demo UI.

**It is CPU-only by design.** The Space runs on ZeroGPU hardware (the only
compute a free HF account can host), but never touches CUDA: the single
`@spaces.GPU` function is a no-op keepalive that consumes no GPU quota. All
detection runs on CPU (DetectZoo CNNSpot, numpy/PIL forensics, OpenCV/ffmpeg
video decoding).

## What the detectors see

| signal | layer |
|---|---|
| SynthID-style watermark carriers | spectral probe + file metadata |
| C2PA / Content Credentials manifests | signed provenance assertions |
| AI-provenance metadata | file markers, captions, alt text, page context |
| frequency forensics | GAN-grid / spectral-deficit analysis |
| DetectZoo (CNNSpot) | trained spatial classifier |
| SPAI (CVPR 2025) | spectral artifact analysis |
| pixel forensics | flat-render / document / collage signatures + fingerprint DB |
| PwTF-DVD (ICCV 2025) | pixel-wise temporal frequency for video |

The rPPG (remote photoplethysmography) heartbeat-consistency layer is
included on the video path. It is face-gated (MediaPipe BlazeFace full-range),
auto-detects whether a video frame contains a face, and is inactive
(score None, contributes 0 to fusion) on non-face videos and images. It is
confidence-weighted and fusion-only — never decisive alone — because modern
high-quality fakes can synthesize a heartbeat (Seibold et al., Frontiers in
Imaging 2025).

Runtime dependency added: `mediapipe==1.1.0` in `requirements.txt`. The face
model asset (`forensics/models/blaze_face_full_range.tflite`, ~1.08 MB) is
bundled in the repo and ships inside the Space package via
`scripts/build_space_package.py` (it is copied from `forensics/`). That model
is NOT inside the mediapipe wheel — it must be present at
`forensics/models/blaze_face_full_range.tflite` relative to this module, or the
rPPG layer becomes inactive with a clear reason.

Calibration caveat: the gating thresholds and the cardiac-band scoring in
`forensics/rppg.py` are calibrated on a small internal face-video corpus. Do not
quote any accuracy number (including the commonly-seen "96% rPPG" headline)
until it is pinned to a specific detector/dataset/source. The 96%/NVIDIA figure
is not cleanly attributable to a single NVIDIA detector in available sources;
treat it as unconfirmed until sourced. Real dataset-specific numbers exist in the
broader rPPG/face-forensics literature (FaceForensics++ papers report 91–99%
depending on method and manipulation; a rounded ~96% AUC figure appears for
other deepfake-detection methods).

Calibrated behavior (see `tests/last_regression_results.json` in the repo):
8/8 on the regression corpus; AI images that are flat renders / collages are
caught as stills; photorealistic AI stills without page context read
UNCERTAIN rather than being falsely accused; video verdicts use shot-aware
native-rate temporal analysis.

## REST API (mounted at the Space root — same shapes as the repo's server)

All endpoints accept and return JSON. Set the Space secret `API_KEY` and send
`Authorization: Bearer <key>` to require auth (recommended — scans are CPU-bound).

- `GET /health` → layer status JSON
- `POST /predict/image/fast` — `{ "image_url" }` or `{ "image_base64" }` (data URL ok)
- `POST /predict/image/deep` — same payload; optional page context:
  `source_caption`, `alt_text`, `page_title`, `page_url`, `page_context`, `no_cache`
- `POST /predict/video/deep` — `{ "video_url" }` (YouTube/IG/TikTok resolved
  server-side via yt-dlp) or `{ "video_base64" }` or `{ "frames_base64": [...] }`;
  optional `frame_interval_seconds` for client-extracted frames, `no_cache`
- `POST /predict` — auto-routes video payloads to the video path, images to
  the deep image path

Verdict shape: `{ score: 0-100, tier, confidence, breakdown: {layer: score},
reasons: [...], ... }` with tiers `SYNTHETIC_AI / SUSPICIOUS / UNCERTAIN /
INCONCLUSIVE / AUTHENTIC_HUMAN`.

Example:

```bash
curl -s https://<your-space-subdomain>.hf.space/predict/image/deep \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"image_base64": "data:image/png;base64,...", "no_cache": true}'
```

## Notes & limitations

- The Space is stateless: the SQLite scan cache lives in the container and
  resets on rebuild/restart. Set `no_cache: true` to bypass it entirely.
- Instagram strongly login-walls anonymous downloads; some reels will fail
  to resolve via yt-dlp without cookies. Direct URLs and YouTube work best.
- First request after a cold start pays the model-load time (~1–2 min).
- Image deep scans run in ~2–5 s; video scans ~10–20 s per clip on 2 vCPU.
