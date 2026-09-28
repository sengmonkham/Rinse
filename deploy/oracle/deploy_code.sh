#!/usr/bin/env bash
# Deploy/update the RINSE backend on the Oracle VM.
# Run from the repo root on your Mac:
#   bash deploy/oracle/deploy_code.sh ubuntu@VM_PUBLIC_IP
set -euo pipefail
HOST="${1:?usage: deploy_code.sh ubuntu@VM_PUBLIC_IP}"
cd "$(dirname "$0")/../.."

echo "==> staging backend package"
python3 scripts/build_space_package.py

echo "==> rsync to $HOST:/opt/rinse/app/"
rsync -av --delete \
  --exclude '__pycache__' --exclude '.compile_cache' \
  deploy/space_stage/ "$HOST:/opt/rinse/app/"

echo "==> install deps + restart service"
ssh "$HOST" 'set -e
  cd /opt/rinse/app
  /opt/rinse/venv/bin/pip install -q -r requirements.txt
  sudo systemctl restart rinse
  sleep 2
  systemctl is-active rinse && echo "rinse service is up"'
