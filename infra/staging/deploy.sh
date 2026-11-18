#!/usr/bin/env bash
# Deploy or update the Staging environment on the VM.
# Usage: [IMAGE_TAG=sha] [IMAGE_REGISTRY=ghcr.io/org/repo] ./infra/staging/deploy.sh
set -euo pipefail

DEPLOY_DIR="/opt/farm-backend"
cd "$DEPLOY_DIR"

echo "=== [1/5] Checking environment and secrets ==="
if [ ! -f .env ]; then
  if [ -f infra/staging/.env.staging.example ]; then
    echo "Warning: .env not found. Creating from infra/staging/.env.staging.example..."
    cp infra/staging/.env.staging.example .env
  else
    echo "Error: No .env found in $DEPLOY_DIR. Please create one before deploying."
    exit 1
  fi
fi

# Ensure secrets directory and RSA keys for JWT exist
mkdir -p secrets
if [ ! -f secrets/jwt_private.pem ] || [ ! -f secrets/jwt_public.pem ]; then
  echo "Generating RSA 2048 keypair for JWT..."
  openssl genpkey -algorithm RSA -out secrets/jwt_private.pem -pkeyopt rsa_keygen_bits:2048
  openssl rsa -pubout -in secrets/jwt_private.pem -out secrets/jwt_public.pem
  chmod 600 secrets/jwt_private.pem secrets/jwt_public.pem
fi

# Ensure Let's Encrypt acme volume mount or file permissions
mkdir -p infra/traefik

export IMAGE_TAG="${IMAGE_TAG:-latest}"
export IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/lakshayg2005/farm-backend}"

echo "Deploying with IMAGE_REGISTRY=${IMAGE_REGISTRY}, IMAGE_TAG=${IMAGE_TAG}"

echo "=== [2/5] Pulling latest container images ==="
docker compose -f docker-compose.staging.yml pull --ignore-pull-failures

echo "=== [3/5] Starting staging infrastructure and services ==="
# Database, message queue and redis will spin up first; migrations execute before each service starts.
docker compose -f docker-compose.staging.yml up -d --remove-orphans

echo "=== [4/5] Waiting for services to become healthy ==="
SERVICES=(identity catalog land media quality order logistics notification)

MAX_RETRIES=30
RETRY_INTERVAL=3

for svc in "${SERVICES[@]}"; do
  echo -n "Checking health of $svc... "
  passed=false
  for ((i=1; i<=MAX_RETRIES; i++)); do
    # Verify through local gateway endpoint with TLS skip-verify for local IP
    HTTP_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" "https://127.0.0.1/api/v1/${svc}/health" 2>/dev/null || true)
    if [ "$HTTP_CODE" = "200" ]; then
      echo "OK (HTTP 200)"
      passed=true
      break
    fi
    # Fallback check directly inside container
    CONTAINER_HEALTH=$(docker inspect --format='{{json .State.Health.Status}}' "farm-backend-${svc}-1" 2>/dev/null || echo "\"unknown\"")
    if [ "$CONTAINER_HEALTH" = "\"healthy\"" ]; then
      echo "OK (container healthy)"
      passed=true
      break
    fi
    sleep "$RETRY_INTERVAL"
  done

  if [ "$passed" = false ]; then
    echo "FAILED"
    echo "Logs for $svc:"
    docker compose -f docker-compose.staging.yml logs --tail=50 "$svc"
    echo "Service $svc failed health checks after $((MAX_RETRIES * RETRY_INTERVAL))s."
    exit 1
  fi
done

echo "=== [5/5] Pruning dangling Docker images to preserve disk space ==="
docker image prune -f --filter "until=72h" || true

echo "=== Staging deployment succeeded! ==="
