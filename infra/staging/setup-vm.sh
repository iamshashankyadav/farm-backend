#!/usr/bin/env bash
# Provision a fresh Ubuntu 22.04 / 24.04 VM (4 GB RAM) for Farm Direct Staging.
# Run with root or sudo:  sudo bash setup-vm.sh [DEPLOY_USER]
set -euo pipefail

TARGET_USER="${1:-${SUDO_USER:-ubuntu}}"
DEPLOY_DIR="/opt/farm-backend"

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: This script must be run as root (or via sudo)."
  exit 1
fi

echo "=========================================================="
echo " Farm Direct Staging Provisioning Script"
echo " Target user: $TARGET_USER"
echo " Deploy dir : $DEPLOY_DIR"
echo "=========================================================="

echo "--> [1/6] Configuring 2 GB swap space for 4 GB RAM VM..."
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
  sysctl vm.swappiness=20
  sysctl vm.vfs_cache_pressure=50
  echo 'vm.swappiness=20' >> /etc/sysctl.d/99-farm-staging.conf
  echo 'vm.vfs_cache_pressure=50' >> /etc/sysctl.d/99-farm-staging.conf
  echo "Swap configured successfully."
else
  echo "Swapfile already exists."
fi

echo "--> [2/6] Installing prerequisites and official Docker Engine..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release ufw openssl jq

install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable and start Docker service
systemctl enable docker
systemctl start docker

# Add deploy user to docker group
if id "$TARGET_USER" &>/dev/null; then
  usermod -aG docker "$TARGET_USER"
fi

echo "--> [3/6] Setting up UFW Firewall (ports 22, 80, 443)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP (Let Encrypt / Redirect)'
ufw allow 443/tcp comment 'HTTPS (Traefik Gateway)'
ufw --force enable

echo "--> [4/6] Creating deployment directory structure..."
mkdir -p "$DEPLOY_DIR/secrets"
mkdir -p "$DEPLOY_DIR/infra/traefik"
mkdir -p "$DEPLOY_DIR/infra/staging"
mkdir -p "$DEPLOY_DIR/infra/postgres"

echo "--> [5/6] Generating JWT keys and initial secrets..."
if [ ! -f "$DEPLOY_DIR/secrets/jwt_private.pem" ]; then
  openssl genpkey -algorithm RSA -out "$DEPLOY_DIR/secrets/jwt_private.pem" -pkeyopt rsa_keygen_bits:2048
  openssl rsa -pubout -in "$DEPLOY_DIR/secrets/jwt_private.pem" -out "$DEPLOY_DIR/secrets/jwt_public.pem"
  chmod 600 "$DEPLOY_DIR"/secrets/jwt_*.pem
fi

if [ ! -f "$DEPLOY_DIR/.env" ]; then
  PG_PASS=$(openssl rand -hex 16)
  RMQ_PASS=$(openssl rand -hex 16)
  MINIO_PASS=$(openssl rand -hex 16)

  cat <<ENV > "$DEPLOY_DIR/.env"
ENVIRONMENT=staging
LOG_LEVEL=INFO

# Database
POSTGRES_USER=farm
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=farm

# RabbitMQ
RABBITMQ_DEFAULT_USER=farm
RABBITMQ_DEFAULT_PASS=${RMQ_PASS}

# MinIO S3
MINIO_ROOT_USER=farm
MINIO_ROOT_PASSWORD=${MINIO_PASS}
S3_BUCKET=farm-media
S3_PUBLIC_ENDPOINT=https://staging.farm-direct.app

# Traefik & ACME SSL
ACME_EMAIL=admin@farm-direct.app
STAGING_DOMAIN=staging.farm-direct.app

# Identity service
OTP_DEV_MODE=false
EVENTS_ENABLED=true
JOBS_ENABLED=true
ENV
  chmod 600 "$DEPLOY_DIR/.env"
  echo "Generated new $DEPLOY_DIR/.env with secure random credentials."
fi

echo "--> [6/6] Adjusting file permissions for $TARGET_USER..."
chown -R "$TARGET_USER:$TARGET_USER" "$DEPLOY_DIR"

echo "=========================================================="
echo " Staging VM provisioning completed successfully!"
echo " Deployment directory: $DEPLOY_DIR"
echo " Docker version     : $(docker --version)"
echo " Compose version    : $(docker compose version)"
echo " Memory status      : $(free -h | grep Mem | awk '{print $2}') RAM + $(free -h | grep Swap | awk '{print $2}') Swap"
echo "=========================================================="
