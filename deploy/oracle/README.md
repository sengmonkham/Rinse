# Deploying RINSE to an Oracle Cloud free-tier ARM VM

The Oracle always-free tier gives **4 ARM cores + 24GB RAM** — plenty for the
full forensic ensemble (torch CPU + ffmpeg + yt-dlp). This guide takes a bare
Oracle account to a public HTTPS API in ~30 minutes.

Files in this directory:
- `provision_server.sh` — run ON the VM once (packages, firewall, Caddy, venv)
- `deploy_code.sh` — run from the Mac to push code + restart the service
- `rinse.service` — systemd unit (copied to the VM in step 6)
- `Caddyfile` — HTTPS reverse-proxy config (copied to the VM in step 6)

## 1. Create the Oracle account
Sign up at https://www.oracle.com/cloud/free/ (card required for identity
verification only; the Always Free tier is not charged). Pick a **home
region close to you** — it cannot be changed later.

## 2. Create the VM (Compute → Instances → Create instance)
- Image: **Ubuntu 24.04** (or 22.04)
- Shape: **Ampere A1** — set 4 OCPU / 24 GB RAM
- SSH keys: paste `~/.ssh/id_ed25519.pub`
- Boot volume: 50–100 GB (the ML stack + model weights want the room)
- Click **Create**

> If creation fails with "Out of capacity", retry at a quieter time (early
> morning local) or try a different AD (availability domain). This is the
> one flaky step on the free tier.

## 3. Open the ports in the CLOUD firewall
Networking → Virtual Cloud Networks → your VCN → Security Lists →
Default Security List → **Add Ingress Rule**:
- Source CIDR `0.0.0.0/0`, IP protocol `TCP`, destination port `80`
- Repeat for port `443`

(The OS-level iptables firewall is handled by `provision_server.sh`.)

## 4. Get a DNS name
Caddy obtains a Let's Encrypt certificate automatically, which needs a
hostname. Easiest free option: create an A record on
https://www.duckdns.org pointing at the VM's **public IP**
(instance details page). Note the name, e.g. `rinse-xxxx.duckdns.org`.

## 5. Provision the VM (~5 min)
```bash
ssh ubuntu@VM_PUBLIC_IP
curl -fsSL https://raw.githubusercontent.com/.../provision_server.sh -o provision_server.sh  # or scp it:
#   scp deploy/oracle/provision_server.sh ubuntu@VM_PUBLIC_IP:
bash provision_server.sh            # generates + prints a random API_KEY
# or: bash provision_server.sh YOUR_CHOSEN_KEY
```
**Save the printed API_KEY.**

## 6. Install the service + proxy config
Still on the VM:
```bash
# env file (the systemd unit reads it):
printf 'PORT=5001\n' | sudo tee /opt/rinse/env >/dev/null
sudo cat /opt/rinse/API_KEY | sudo tee -a /opt/rinse/env >/dev/null
sudo chmod 600 /opt/rinse/env

# from your Mac (second terminal):
scp deploy/oracle/rinse.service ubuntu@VM_PUBLIC_IP:/tmp/
scp deploy/oracle/Caddyfile       ubuntu@VM_PUBLIC_IP:/tmp/
# back on the VM:
sudo cp /tmp/rinse.service /etc/systemd/system/rinse.service
sudo sed -i 's/<DOMAIN>/rinse-xxxx.duckdns.org/' /tmp/Caddyfile && sudo cp /tmp/Caddyfile /etc/caddy/Caddyfile
sudo systemctl daemon-reload && sudo systemctl enable --now rinse
sudo systemctl reload caddy
```

## 7. Deploy the code (from the Mac)
```bash
bash deploy/oracle/deploy_code.sh ubuntu@VM_PUBLIC_IP
```
This stages the backend, rsyncs it to `/opt/rinse/app/`, installs the Python
deps (first run: torch etc., several minutes), and restarts the service.
Model weights download on first boot — watch with:
```bash
ssh ubuntu@VM_PUBLIC_IP journalctl -u rinse -f
```
Wait for `DetectZoo successfully loaded!` in the log.

## 8. Verify
```bash
curl https://rinse-xxxx.duckdns.org/health
curl https://rinse-xxxx.duckdns.org/predict/image/deep \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/photo.jpg", "no_cache": true}'
```

## 9. Point the Chrome extension at it
Settings → API URL: `https://rinse-xxxx.duckdns.org` (the extension
normalizes bare hosts) → API key: the `API_KEY` from step 5.

## Updating after code changes
```bash
bash deploy/oracle/deploy_code.sh ubuntu@VM_PUBLIC_IP
```

## Notes
- The VM has 24GB RAM — no memory pressure, unlike the 512MB free tiers.
- The SQLite scan cache persists across restarts (unlike the HF Space).
- Always-free resources do **not** expire, but idle **AMPERE A1 capacity is
  reclaimed** only if the tenancy exceeds its free quota — a single 4-OCPU
  instance stays within it.
- `STORYSCOPE_MODE` defaults to heuristic. To enable LLM extraction later,
  add `STORYSCOPE_LLM_API_KEY=...` to `/opt/rinse/env` and restart.
