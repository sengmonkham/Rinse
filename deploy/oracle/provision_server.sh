#!/usr/bin/env bash
# Provision a fresh Oracle Cloud Ubuntu ARM VM to host the RINSE backend.
# Run ON the VM as user `ubuntu`:
#   bash provision_server.sh [API_KEY]
# If API_KEY is omitted a random one is generated and printed.
set -euo pipefail

API_KEY="${1:-$(openssl rand -hex 32)}"

echo "==> apt packages"
sudo apt-get update -y
sudo apt-get -y upgrade
sudo apt-get install -y python3-venv python3-dev build-essential ffmpeg git \
  openssl curl debian-keyring debian-archive-keyring apt-transport-https

echo "==> open ports 80/443 in the instance firewall (Oracle ships a locked-down iptables ruleset)"
sudo iptables -I INPUT -p tcp --dport 80  -m state --state NEW -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -m state --state NEW -j ACCEPT
if ! command -v netfilter-persistent >/dev/null 2>&1; then
  sudo apt-get install -y iptables-persistent
fi
sudo netfilter-persistent save

echo "==> Caddy (HTTPS reverse proxy, auto Let's Encrypt)"
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
sudo apt-get update -y && sudo apt-get install -y caddy

echo "==> app dirs + venv"
sudo mkdir -p /opt/rinse
sudo chown ubuntu:ubuntu /opt/rinse
python3 -m venv /opt/rinse/venv
/opt/rinse/venv/bin/pip install --upgrade pip wheel

printf 'API_KEY=%s\n' "$API_KEY" > /opt/rinse/API_KEY
chmod 600 /opt/rinse/API_KEY
echo ""
echo "==================== SAVE THIS ===================="
echo "API_KEY: $API_KEY"
echo "(also stored on the VM at /opt/rinse/API_KEY)"
echo "==================================================="
echo "provision done"
