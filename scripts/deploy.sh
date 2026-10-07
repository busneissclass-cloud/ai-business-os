#!/bin/bash
# One-command production deploy on a fresh Ubuntu VPS.
# 1. Point your domain's A record at this server's IP first.
# 2. Copy this repo to the server (scp/rsync), then run: sudo ./scripts/deploy.sh yourdomain.com
set -euo pipefail
DOMAIN="${1:?usage: deploy.sh yourdomain.com}"
cd "$(dirname "$0")/.."

# Docker
if ! command -v docker >/dev/null; then
  apt-get update -qq && apt-get install -y -qq docker.io docker-compose-plugin
fi

# Secrets (generated once, kept with 600 perms)
if [ ! -f .env ]; then
  POSTGRES_PASSWORD=$(openssl rand -hex 24)
  API_SECRET=$(openssl rand -hex 32)
  printf 'POSTGRES_PASSWORD=%s\nAPI_SECRET=%s\nDOMAIN=%s\nENV=production\n' \
    "$POSTGRES_PASSWORD" "$API_SECRET" "$DOMAIN" > .env
  chmod 600 .env
  echo "secrets generated in .env"
fi

export DOMAIN
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
sleep 15
curl -sf "http://localhost:8000/v1/health" | head -c 200; echo
echo "LIVE: https://$DOMAIN  (dashboard/docs at https://$DOMAIN/docs)"
echo "Shadow mode is ON by default. Review drafts, then disable shadow only after the 2-week review."
