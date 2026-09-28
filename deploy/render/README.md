# Deploying RINSE to Render.com

The **real backend** (full forensic ensemble) as a public REST API on Render,
built from the repo-root `Dockerfile` with the settings in `render.yaml`.
Same endpoints, payloads, and Bearer-token auth as the HF Space and Oracle VM
targets — clients work unchanged.

## What you get

- **Docker runtime** on `python:3.11-slim` + ffmpeg; CPU-only torch (no CUDA).
- CNNSpot weights (~280MB) **baked into the image** at build time — no
  Dropbox download on cold boot (unlike the HF Space, where first boot pays it).
- **Persistent disk** at `/app/data` for the SQLite scan cache (survives
  deploys, unlike the Space) and temp video files.
- Zero-downtime deploys on every push (`autoDeploy`).

## Requirements

- A Render account (https://dashboard.render.com).
- **`starter` plan ($7/mo) or higher.** The free plan gives 512MB RAM — the
  torch + DetectZoo stack cannot boot in it (expect OOM kills). If you must
  try free anyway, see "Free plan" below.
- The repo pushed to GitHub/GitLab (Render builds from git, not local files).

## One-time deploy

1. Push this repo to GitHub (the `Dockerfile` and `render.yaml` at the root
   are all Render needs).
2. Render dashboard → **New +** → **Blueprint** → select the repo. Render
   reads `render.yaml` and shows the service it will create (`rinse-detector`).
   Click **Apply**.
3. Wait for the first build/deploy (~10–15 min: ML stack + weights + model
   load). Watch the **Events / Logs** tab for `DetectZoo successfully loaded!`.
4. Copy the **API_KEY** value from the service's **Environment** tab — Render
   generated it (`generateValue: true`) and it is the Bearer token clients
   must send.

## Verify (do not trust "Live" alone)

```bash
curl https://rinse-detector.onrender.com/health

curl https://rinse-detector.onrender.com/predict/image/deep \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/photo.jpg", "no_cache": true}'
```

(Your hostname is on the service page — `*.onrender.com` by default, or your
custom domain.)

## Point the Chrome extension at it

Settings → API URL: `https://<your-service>.onrender.com` (the extension
normalizes bare hosts) → API key: the `API_KEY` from the Environment tab.

## Updating after changes

`autoDeploy: true` — push to `master` and Render rebuilds (only paths in
`buildFilter` trigger it). Force a deploy from the dashboard otherwise.
Model weights are baked in, so deploys are much faster than the first build.

## Render specifics worth knowing

- **PORT**: injected by Render; `server.py` already binds `0.0.0.0:$PORT`
  (default 10000). Nothing to configure.
- **Health check**: `healthCheckPath: /health` — Render considers the deploy
  live only when it answers, so a broken model load shows as failed deploy,
  not a silently broken service.
- **Free plan (512MB)**: torch alone is ~590MB on disk and hundreds of MB
  resident at model load. To attempt it: drop `plan: starter` from
  `render.yaml` (free tier), delete the `disk:` block (disks are paid), and
  set `MODEL_NAME` to the smallest available detector. Expect OOM or
  swapping; the honest answer is that the free plan cannot run this stack —
  the HF Space (ZeroGPU) is the free option.
- **Scan cache**: 1GB disk holds the verdict cache. The server degrades
  gracefully to uncached scans if the disk is full or detached.
- **Instagram login walls**: same as every server target — yt-dlp cannot
  resolve IG posts requiring login. YouTube / direct URLs work.
- **Throughput**: starter = 1 CPU, ~2–5 s per image, ~10–20 s per video.
  Concurrency is limited; scale the plan if needed, no code changes.
- **Secrets**: `API_KEY` via `generateValue` is fine for this API. To rotate,
  change it in the Environment tab (Render restarts the service).

## Files added for Render

- `Dockerfile` — image build (deps → sources → weights → CMD `python server.py`)
- `requirements-render.txt` — pinned Python deps (CPU stack, no Space extras)
- `render.yaml` — blueprint (service, disk, env vars, health check)
- `.dockerignore` — keeps the build context small

Nothing in `server.py` or the forensic layers needed changing.
