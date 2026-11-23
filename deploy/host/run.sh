#!/bin/bash
# Runs ON the EC2 host (as root): pulls secrets, builds both images from the unpacked source, (re)starts the containers.
# Idempotent: re-running it is how a new version is deployed (see deploy/update.ps1). Reads non-secret settings from
# /opt/saathi/host.conf (written by the instance's user data). Secret VALUES are only ever written to root-only files
# (mode 600) and are never printed.
set -euo pipefail
exec > >(tee -a /var/log/saathi-run.log) 2>&1
echo "== saathi run.sh $(date -u +%FT%TZ)"

# shellcheck disable=SC1091
source /opt/saathi/host.conf       # REGION SECRET_ARN LOG_GROUP CF_DOMAIN
SRC=/opt/saathi/src
umask 077

# ---- 1. secrets -> root-only env files (nothing is echoed) -------------------------------------------------------------
SECRET_JSON=$(aws secretsmanager get-secret-value --region "$REGION" --secret-id "$SECRET_ARN" --query SecretString --output text)
{
  echo "$SECRET_JSON" | jq -r 'del(.ORIGIN_VERIFY) | to_entries[] | select(.value != "") | "\(.key)=\(.value)"'
  echo "APP_ENV=production"
  echo "ALLOW_SIMULATORS=1"               # explicit: simulated lab partner and log-only emergency alerts
  echo "LAB_BACKEND=simulator"
  echo "LAB_FAILURE_RATE=0"
  echo "FRONTEND_ORIGINS=https://${CF_DOMAIN}"
  echo "DATABASE_URL=sqlite:////data/saathi.db"
  echo "TRACE_FILE=/data/traces.jsonl"
  echo "LANGFUSE_CAPTURE_CONTENT=false"   # health data: only redacted markers leave the host
} > /opt/saathi/backend.env
echo "ORIGIN_VERIFY=$(echo "$SECRET_JSON" | jq -r .ORIGIN_VERIFY)" > /opt/saathi/web.env
echo "BACKEND_HOST=backend:8000" >> /opt/saathi/web.env
unset SECRET_JSON

# ---- 2. images ---------------------------------------------------------------------------------------------------------
docker build -t saathi-backend:latest -f "$SRC/Dockerfile" "$SRC"
docker build -t saathi-web:latest -f "$SRC/Dockerfile.frontend" "$SRC"

# ---- 3. containers (single backend instance by design: ADK sessions live in process memory) ---------------------------
docker network inspect saathi >/dev/null 2>&1 || docker network create saathi
docker volume inspect saathi-data >/dev/null 2>&1 || docker volume create saathi-data
# The backend runs as uid 10001; make sure the named volume is writable by it.
docker run --rm -u 0 -v saathi-data:/data --entrypoint chown saathi-backend:latest -R 10001 /data

LOGOPTS=(--log-driver awslogs --log-opt "awslogs-region=$REGION" --log-opt "awslogs-group=$LOG_GROUP")
docker rm -f web backend >/dev/null 2>&1 || true
docker run -d --name backend --restart unless-stopped --network saathi --stop-timeout 30 \
  --env-file /opt/saathi/backend.env -v saathi-data:/data "${LOGOPTS[@]}" --log-opt awslogs-stream=backend saathi-backend:latest
docker run -d --name web --restart unless-stopped --network saathi --stop-timeout 10 -p 80:80 \
  --env-file /opt/saathi/web.env "${LOGOPTS[@]}" --log-opt awslogs-stream=web saathi-web:latest

# ---- 4. wait until healthy ---------------------------------------------------------------------------------------------
for i in $(seq 1 60); do
  s=$(docker inspect -f '{{.State.Health.Status}}' backend 2>/dev/null || echo starting)
  [ "$s" = healthy ] && break
  sleep 5
done
echo "backend health: $s"
[ "$s" = healthy ] || { docker logs --tail 40 backend || true; exit 1; }
curl -fsS -m 5 http://127.0.0.1/healthz && echo
echo "== memory (MiB) for sizing"; free -m | sed -n 1,2p; docker stats --no-stream --format '{{.Name}}: {{.MemUsage}}'
docker image prune -f >/dev/null 2>&1 || true
echo "== done"
