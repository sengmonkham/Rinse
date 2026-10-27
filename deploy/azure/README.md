# Deploying RINSE to Azure (Azure for Students)

Short answer: **Azure for Students can host this backend, but only on
Container Apps.** The two "obvious" free Azure targets cannot, because this
backend is a PyTorch/DetectZoo process, not a small web app.

| Azure offer (student account) | Limits | Fits RINSE? |
|---|---|---|
| **App Service — free F1** (always free, 10 apps) | 1 GiB RAM, 1 CPU, 1 GB storage, **60 CPU-minutes/day** | **No.** torch + DetectZoo + opencv sit at ~1 GB RSS (measured during a video scan), which is the whole VM, and one video scan (~20–40 s) eats the daily CPU quota. F1 also cannot run custom containers. |
| **Virtual Machines — free 12 months** (B1s, B2ats_v2, B2pts_v2) | 750 h/month each, but **all three are 1 GiB RAM** | **No.** Same memory wall; the image build alone wants more RAM than the VM has. |
| **Container Apps — consumption** (always-free grant) | 180,000 vCPU-s + 360,000 GiB-s + 2 M requests/month | **Yes** with 2 vCPU / 4 GiB. This is what `deploy.sh` sets up. |
| Container Instances / AKS nodes / pay-as-you-go B2s VM | no free grant (~US$30/mo for B2s: 2 vCPU / 8 GiB) | Yes, and always-warm, but it burns the $100 credit in ~3 months. |

So the honest fit is: **workable for a persistent demo, not cheaper than the
Hugging Face Space** (16 GB RAM for free). Use Azure when you specifically
want an Azure-hosted, always-available HTTPS endpoint and are willing to spend
the credit on it.

## What Container Apps costs you

Container Apps bills per second while a replica is running (active rate while
starting or serving, reduced idle rate if you pin `minReplicas: 1`).

- At 2 vCPU / 4 GiB the always-free grant covers **~25 hours/month**
  (`360,000 GiB-s ÷ 4 GiB = 90,000 s`; the vCPU grant lands on the same 25 h).
- Beyond that it is roughly **US$0.15–0.22/hour** active at list rates
  (vCPU ≈ $0.000012–0.000024/vCPU-s, memory ≈ $0.000003/GiB-s — Microsoft's
  pricing page renders rates dynamically, so confirm in the pricing calculator
  for your region).
- $100 therefore buys **~450–650 hours** of container time across the 12
  months, and the first 25 h of each month are free. With
  `minReplicas: 0` you only spend it while scanning.
- Always-warm (`minReplicas: 1`) is ~$110–160/month — **do not** leave that on
  with this offer; credit exhaustion disables the whole subscription.
- Add Azure Container Registry: Standard tier is free for 12 months on a new
  account; after that ~$20/month (or use Basic, ~$5). Egress: 100 GB/month
  free, and video downloads count against it.
- Note the student-specific rules from the offer: **quota increases require
  upgrading to pay-as-you-go**, the subscription is **disabled when credit
  runs out**, and **resources can be reclaimed after 90 days of inactivity**
  (logging into the portal or hitting the API counts as activity).

## What you need locally

```bash
brew install azure-cli        # macOS; az --version
az login                      # use the account that holds the student subscription
az account show               # confirm the subscription is "Azure for Students"
```

No Docker daemon is required: the image is built **inside** Azure Container
Registry with `az acr build` (the first build installs CPU torch + the ML
stack and bakes the 280 MB CNNSpot weights — expect 10–25 minutes).

## Deploy

```bash
bash deploy/azure/deploy.sh
```

The script:

1. creates the resource group (`rinse-rg`, `eastus` by default — override with
   `RG=… LOCATION=…`),
2. creates the registry `rinseacr<timestamp>` (Standard, admin user enabled so
   the app can pull),
3. builds `rinse-detector:<git-sha>` from the repo-root `Dockerfile`,
4. creates the Container Apps environment, renders `containerapp.yaml`, and
   creates/updates the app, then
5. waits for `https://<fqdn>/health` and prints the URL + API key.

The API key and registry name are stored in `deploy/azure/.azure-state.env`
(gitignored) so re-deploys **do not** rotate the Bearer token. If you lose the
key, read it back with:

```bash
az containerapp secret show -n rinse-detector -g rinse-rg --secret-name api-key
```

### Point the extension at it

Settings → Cloud API mode → API URL `https://<fqdn>`, API key = the printed
value. Endpoints and payload shapes are identical to every other target;
`/health` is unauthenticated so ACA's startup/readiness/liveness probes work
with `API_KEY` set.

### Verify (don't trust "Deployed")

```bash
curl -s https://<fqdn>/health
curl -s https://<fqdn>/predict/image/deep \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"image_url":"https://example.com/photo.jpg","no_cache":true}'
az containerapp logs show -n rinse-detector -g rinse-rg --tail 100
```

`"detectzoo_loaded": true` in `/health` is the line that tells you the model
stack actually came up (a container that merely *starts* is not a working
detector).

## Honest limitations of this target

- **Cold start is real.** Scale-to-zero means the first request after idle
  waits for a replica to be scheduled, the (multi-GB) image pulled, torch
  imported and the DetectZoo weights loaded.Locally it is **6.2 s** with the
weights already on disk; on ACA add a multi-GB image pull and roughly half the
CPU speed, so budget 1–3 minutes. The startup
  probe allows up to ~10 minutes for exactly this reason.
- **No persistent disk on consumption.** The SQLite scan cache lives on the
  replica's ephemeral disk — it accelerates repeat scans within a replica's
  life and disappears on scale-to-zero/restart. Scans still work uncached.
- **Instagram downloads are not guaranteed.** yt-dlp resolves reels from a
  datacenter IP; platforms are more aggressive about rate-limiting/login-walling
  cloud IPs than residential ones. If IG scans start failing with 403s, that is
  the cause — uploads and direct `.mp4` URLs keep working.
- **Video scans are CPU-bound** (~15–40 s each with the coverage sweep on 2
  vCPU), so `concurrentRequests: 5` in the template is a queueing guard, not a
  throughput promise.
- **One replica at a time is enough** for personal use; `maxReplicas: 2` is a
  safety valve, and every extra replica spends the credit faster.

## Tear down

```bash
az group delete --name rinse-rg --yes --no-wait
```

Deleting the resource group removes the app, environment, registry and images;
the (already consumed) credit is not refunded.
