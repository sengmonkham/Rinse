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
