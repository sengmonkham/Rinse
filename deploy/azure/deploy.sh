#!/usr/bin/env bash
# Deploy the RINSE backend to Azure Container Apps (runs on Azure for Students).
#
#   bash deploy/azure/deploy.sh
#
# Re-running the script redeploys the current working tree: it rebuilds the
# image in Azure Container Registry (no local Docker needed) and updates the
# existing Container App in place. The API key and registry name are kept in
# deploy/azure/.azure-state.env so re-deploys do not rotate the Bearer token.
#
# Override anything with environment variables, e.g.:
#   LOCATION=westeurope RG=rinse-rg API_KEY=$(openssl rand -hex 24) \
#     bash deploy/azure/deploy.sh
#
# Cost/limits and the "is Azure for Students a good fit" answer live in
# deploy/azure/README.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

RG="${RG:-rinse-rg}"
LOCATION="${LOCATION:-eastus}"
APP="${APP:-rinse-detector}"
ENV_NAME="${ENV_NAME:-rinse-env}"
STATE_FILE="${STATE_FILE:-$HERE/.azure-state.env}"
IMAGE_REPO="rinse-detector"

command -v az >/dev/null || { echo "Azure CLI not found: brew install azure-cli (or see https://aka.ms/azure-cli)"; exit 1; }
az account show >/dev/null 2>&1 || { echo "Not logged in. Run: az login"; exit 1; }

# Keep the registry name + API token stable across re-deploys.
if [ -f "$STATE_FILE" ]; then
  # shellcheck disable=SC1090
  . "$STATE_FILE"
fi
ACR="${ACR:-rinseacr$(date +%y%m%d%H%M)}"        # globally unique, lowercase alphanumeric
API_KEY="${API_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)}"
printf 'ACR=%s\nAPI_KEY=%s\n' "$ACR" "$API_KEY" > "$STATE_FILE"
chmod 600 "$STATE_FILE"

echo "==> Resource group $RG ($LOCATION)"
az group create --name "$RG" --location "$LOCATION" --output none

echo "==> Container registry $ACR (Standard is free for 12 months on a new account)"
az acr show --name "$ACR" --resource-group "$RG" --output none 2>/dev/null \
  || az acr create --name "$ACR" --resource-group "$RG" --sku Standard --admin-enabled true --output none

echo "==> Building $IMAGE_REPO:$IMAGE_TAG in ACR (torch + ML stack: 10-25 min the first time)"
az acr build --registry "$ACR" --image "$IMAGE_REPO:$IMAGE_TAG" \
  --file "$ROOT/Dockerfile" "$ROOT"

echo "==> Container Apps environment $ENV_NAME"
az containerapp env show --name "$ENV_NAME" --resource-group "$RG" --output none 2>/dev/null \
  || az containerapp env create --name "$ENV_NAME" --resource-group "$RG" \
       --location "$LOCATION" --logs-destination none --output none

ACR_LOGIN_SERVER="$(az acr show --name "$ACR" --resource-group "$RG" --query loginServer -o tsv)"
ACR_USERNAME="$(az acr credential show --name "$ACR" --query username -o tsv)"
ACR_PASSWORD="$(az acr credential show --name "$ACR" --query 'passwords[0].value' -o tsv)"
ENV_ID="$(az containerapp env show --name "$ENV_NAME" --resource-group "$RG" --query id -o tsv)"

RENDERED="$(mktemp -t rinse-aca.XXXXXX.yaml)"
trap 'rm -f "$RENDERED"' EXIT
APP_NAME="$APP" LOCATION="$LOCATION" RESOURCE_GROUP="$RG" ENV_ID="$ENV_ID" \
IMAGE="$ACR_LOGIN_SERVER/$IMAGE_REPO:$IMAGE_TAG" \
ACR_LOGIN_SERVER="$ACR_LOGIN_SERVER" ACR_USERNAME="$ACR_USERNAME" \
ACR_PASSWORD="$ACR_PASSWORD" API_KEY="$API_KEY" \
python3 - "$HERE/containerapp.yaml" "$RENDERED" <<'PY'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
keys = ("APP_NAME", "LOCATION", "RESOURCE_GROUP", "ENV_ID", "IMAGE",
        "ACR_LOGIN_SERVER", "ACR_USERNAME", "ACR_PASSWORD", "API_KEY")
for key in keys:
    text = text.replace(f"__{key}__", os.environ[key])
leftover = [k for k in keys if f"__{k}__" in text]
if leftover:
    sys.exit(f"unsubstituted placeholders: {leftover}")
open(dst, "w", encoding="utf-8").write(text)
PY

echo "==> Applying the Container App ($APP)"
if az containerapp show --name "$APP" --resource-group "$RG" --output none 2>/dev/null; then
  az containerapp update --name "$APP" --resource-group "$RG" --yaml "$RENDERED" --output none
else
  az containerapp create --name "$APP" --resource-group "$RG" --yaml "$RENDERED" --output none
fi

FQDN="$(az containerapp show --name "$APP" --resource-group "$RG" \
        --query properties.configuration.ingress.fqdn -o tsv)"

echo "==> Waiting for /health (cold start loads torch + DetectZoo: allow a few minutes)"
for _ in $(seq 1 60); do
  if curl -fsS "https://$FQDN/health" -o /tmp/rinse-health.json 2>/dev/null; then
    python3 -c 'import json;d=json.load(open("/tmp/rinse-health.json"));print("healthy:",d["status"],"| detectzoo:",d["detectzoo_loaded"],"| auth:",d["auth_required"],"| uptime:",d["uptime_seconds"],"s")'
    break
  fi
  sleep 10
done

cat <<EOF

Backend:  https://$FQDN
Health:   https://$FQDN/health
API key:  $API_KEY   (also in ${STATE_FILE#$ROOT/})

Extension settings -> Cloud API URL: https://$FQDN
                      API key:        $API_KEY

Smoke test:
curl -s https://$FQDN/predict/image/deep \\
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \\
  -d '{"image_url":"https://example.com/photo.jpg","no_cache":true}'
EOF
