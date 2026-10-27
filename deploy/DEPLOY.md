# Deploying RINSE

This is the **real backend** (all forensic layers) hosted as a public REST API.
Nothing here is a demo mock.

Azure is the tightest fit of these targets: App Service's free tier and the
free 12-month VMs are 1 GiB RAM, so only Container Apps can hold the torch
stack — see [`azure/README.md`](azure/README.md) before choosing it.

## Deployment targets

| Target | Cost | Guide |
|---|---|---|
| Hugging Face Space (ZeroGPU) | free | this file |
| Render.com (Docker) | from $7/mo | [`render/README.md`](render/README.md) |
| Oracle Cloud free-tier VM | free | [`oracle/README.md`](oracle/README.md) |
| Azure Container Apps (Azure for Students) | free grant + $100 credit | [`azure/README.md`](azure/README.md) |

---

# Hugging Face Space

## What a free account can host (verified 2026-09-27)

Docker Spaces and `cpu-basic` hardware **require a paid plan**. A free
personal account can host up to **2 ZeroGPU Spaces**, and ZeroGPU works for
CPU-only apps: the app must define at least one `@spaces.GPU`-decorated
function, which ours does (`_zerogpu_keepalive` in app.py — a no-op that
burns no quota). All detection runs on CPU exactly like locally.

The staged package also carries `packages.txt` (ffmpeg, plus libglib2.0-0 for
`opencv-python-headless`) and the 282 MB DetectZoo CNNSpot weight, so a boot
never has to download a model.

## One-time setup: authenticate the hf CLI

```bash
export PATH="$HOME/.local/bin:$PATH"   # if hf was installed via the install script
hf auth login                          # opens a URL + code; complete in your browser
hf auth whoami                         # confirm
```

## Create the Space and push

```bash
# 1. Stage the backend (server.py, forensics/, fingerprints/, storyscope/
#    are copied into deploy/space_stage/, the 282 MB CNNSpot weight is baked
#    in, then everything is byte-compiled as a check)
.venv/bin/python scripts/build_space_package.py

# 2. Create the Space (ZeroGPU flavor is REQUIRED on a free account)
hf repos create <your-username>/rinse-detector --type space \
  --space-sdk gradio --flavor zero-a10g --public --exist-ok

# 3. Require the Bearer token (scans are CPU-bound; do not run this open)
hf spaces secrets set <your-username>/rinse-detector API_KEY=<choose-a-long-random-string>

# 4. Upload the staged package (~297 MB: code + the baked weight, stored via
#    LFS; unchanged files are skipped on later uploads)
hf upload <your-username>/rinse-detector deploy/space_stage/. --repo-type space \
  --exclude "**/__pycache__/**"
```

Watch the build: `hf spaces logs <your-username>/rinse-detector --follow`
(first build installs torch + the ML stack — the weights are already in the
repo, so there is nothing to fetch at boot; expect several minutes).

## Verify (do not trust RUNNING alone)

```bash
hf spaces info <your-username>/rinse-detector --expand runtime
hf spaces logs <your-username>/rinse-detector --tail 200   # look for "DetectZoo successfully loaded!"

# The API must answer, and /health must report the neural layer as loaded:
#   "detectzoo_loaded": true
# false means the baked weight did not load and every scan is silently running
# without the CNNSpot classifier (the server still answers 200s in that state).
curl -s https://<your-username>-rinse-detector.hf.space/health
curl -s https://<your-username>-rinse-detector.hf.space/predict/image/deep \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d "{\"image_url\": \"https://example.com/photo.jpg\", \"no_cache\": true}"
```

The UI lives at `/gradio_api/` (Image and Video tabs, same detectors).

## Point the Chrome extension at it

Settings → API URL: `https://<your-username>-rinse-detector.hf.space`
(the extension normalizes bare hosts automatically) → API key: the same
`API_KEY` value. Every endpoint/payload shape is unchanged.

## Updating after changes

```bash
.venv/bin/python scripts/build_space_package.py
hf upload <your-username>/rinse-detector deploy/space_stage/. --repo-type space \
  --exclude "**/__pycache__/**"
```

The weight is re-staged on every build but only re-uploaded when it changed.

## Honest limitations

- **Cold start**: on zero traffic the Space sleeps; the next request pays a
  ~1–2 min model load. For ~100 users this is fine (keep-alive pings are an
  option but are against the spirit of the free tier — only add one if
  cold starts actually annoy users).
- **Weights**: only the default `cnnspot` weights are baked. Switching
  `MODEL_NAME` to `univfd` (1.7 GB) makes the Space download them at boot —
  add the file to `WEIGHT_FILES` in `scripts/build_space_package.py` to bake it
  too.
- **Instagram login walls**: the Space has no browser cookies, so yt-dlp
  cannot resolve IG posts that require login. YouTube/direct URLs work.
- **Ephemeral cache**: the SQLite scan cache resets on restart/rebuild.
- **Throughput**: 2 vCPU, ~2–5 s per image, ~10–20 s per video. Gradio
  queues concurrent requests; at 100 users this is comfortably enough —
  if it ever is not, the fix is paid `cpu-basic` hardware, not code changes.
- **Page-context provenance** (captions/alt text) only arrives when a client
  sends it; the extension does, the demo UI does not.
