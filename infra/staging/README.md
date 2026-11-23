# Staging Infrastructure & Auto-Deployment (Issue #15)

This directory contains the complete staging deployment setup for the **Farm Direct** backend on a single 4 GB RAM virtual machine with automated HTTPS and GitHub Actions CD.

---

## 1. Architecture & Memory Management (4 GB VM)

Running 14 containers on a single 4 GB VM requires strict memory limits and a swap buffer to avoid Out-Of-Memory (OOM) kills. Images are built entirely on GitHub Actions runners and pushed to **GitHub Container Registry (GHCR)**; the VM only pulls pre-built images.

### Memory Allocation Breakdown

| Service / Container | Role | Memory Limit | Memory Reservation |
|---------------------|------|--------------|-------------------|
| **postgres**        | PostGIS 16 (shared schemas) | 512 MB | 256 MB |
| **rabbitmq**        | AMQP 3.13 Event Bus | 384 MB | 192 MB |
| **minio**           | S3 Object Storage | 256 MB | 128 MB |
| **redis**           | Media job queue (arq) & cache | 128 MB | 64 MB |
| **gateway**         | Traefik v3.1 + Let's Encrypt | 128 MB | 64 MB |
| **identity**        | Auth, JWT, OTP service | 256 MB | 128 MB |
| **catalog**         | Crops, pricing, listings | 256 MB | 128 MB |
| **land**            | Plots, soil, leasing | 256 MB | 128 MB |
| **media**           | Image upload & metadata API | 256 MB | 128 MB |
| **media-worker**    | Thumbnail generator (arq) | 256 MB | 128 MB |
| **order**           | Escrow & payments | 256 MB | 128 MB |
| **logistics**       | Delivery routes & tracking | 256 MB | 128 MB |
| **notification**    | Push notifications & alerts | 256 MB | 128 MB |
| **Host OS + Buffer**| Linux kernel, Docker daemon | ~500 MB | - |
| **Total Allocation**| | **~3,712 MB** | **~1,856 MB** |

> **Swap Buffer:** The provisioning script sets up a **2 GB swap file** (`/swapfile`) with `vm.swappiness=20`. This protects the system against memory spikes during migrations and container updates.

---

## 2. Automated HTTPS with Traefik & Let's Encrypt

- **HTTP Challenge:** Port `80` redirects permanently to Port `443` (HTTPS) while handling ACME HTTP-01 challenges for Let's Encrypt.
- **TLS Automation:** Traefik v3 (`infra/traefik/traefik.staging.yml`) automatically issues and renews certificates for the domain defined in `STAGING_DOMAIN` using email `ACME_EMAIL`.
- **Cert Persistence:** Stored in a Docker volume `traefik_acme` mapped to `/etc/traefik/acme/acme.json` (chmod 600) so renewals persist across container updates.
- **CORS:** Pre-configured in `infra/traefik/dynamic.staging.yml` to allow access from web frontend applications, mobile emulators, and local development environments.
- **Security:** Microservice `/internal/...` endpoints are routed to a 404 block middleware and never exposed to the public Internet.

---

## 3. GitHub Actions Auto-Deploy Pipeline

Workflow file: [`.github/workflows/deploy-staging.yml`](file:///.github/workflows/deploy-staging.yml)

### Workflow Steps
1. **Trigger:** Push to `main` branch or manual trigger (`workflow_dispatch`).
2. **Matrix Build:** GitHub Actions builds Docker images for all 8 services simultaneously using Docker Buildx and GitHub layer cache.
3. **Registry Push:** Images are tagged with both `latest` and the commit SHA (`${{ github.sha }}`) and pushed to GHCR (`ghcr.io/lakshayg2005/farm-backend/<service>`).
4. **Deploy Step:**
   - Connects to the Staging VM via SSH.
   - Syncs `docker-compose.staging.yml`, `infra/traefik/`, and deployment scripts to `/opt/farm-backend`.
   - Runs `infra/staging/deploy.sh` on the VM.
   - Pulls images, applies Alembic migrations, restarts containers, and performs automated health checks across all services.
   - Prunes old Docker images (`docker image prune -f --filter "until=72h"`) to prevent disk bloat.

### Required GitHub Repository Secrets

Configure the following secrets in **GitHub Repository Settings > Secrets and variables > Actions**:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `STAGING_SSH_HOST` | Public IP or hostname of the Staging VM | `198.51.100.25` or `staging.farm-direct.app` |
| `STAGING_SSH_USER` | Deploy user on the VM | `ubuntu` |
| `STAGING_SSH_KEY`  | Private OpenSSH key for authentication | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `STAGING_SSH_PORT` | *(Optional)* SSH port (default: 22) | `22` |

> Note: Image push and pull authentication uses the built-in `GITHUB_TOKEN`. Make sure package permissions are set to read/write under **Settings > Actions > General > Workflow permissions**.

---

## 4. Initial VM Provisioning (One-Time Setup)

1. **DNS Setup:**
   Create an **A Record** pointing your domain (e.g. `staging.farm-direct.app`) to your VM's public IP address.

2. **Run the Provisioning Script on the VM:**
   ```bash
   # Clone the repository or copy setup-vm.sh to the VM
   curl -fsSL https://raw.githubusercontent.com/lakshayg2005/farm-backend/main/infra/staging/setup-vm.sh -o setup-vm.sh
   chmod +x setup-vm.sh
   sudo ./setup-vm.sh ubuntu
   ```
   This script:
   - Configures 2 GB swap space.
   - Installs Docker Engine & Compose plugin.
   - Sets up UFW firewall (allowing only ports 22, 80, 443).
   - Generates RSA 2048 keypair in `/opt/farm-backend/secrets/` for JWT signing.
   - Generates `/opt/farm-backend/.env` with secure random passwords.

3. **Verify `.env` on the VM:**
   Review `/opt/farm-backend/.env` and update `ACME_EMAIL` and `STAGING_DOMAIN` with your registered domain:
   ```bash
   sudo nano /opt/farm-backend/.env
   ```

4. **First Deployment:**
   Run the deploy script manually or push a commit to `main`:
   ```bash
   cd /opt/farm-backend
   sudo ./infra/staging/deploy.sh
   ```

---

## 5. Client Endpoint Reference (Mobile & Web)

Both the mobile application and frontend point to this staging endpoint:

| Service | Staging URL | Swagger UI Docs |
|---------|-------------|-----------------|
| **Gateway HTTPS Base** | `https://staging.farm-direct.app` | - |
| **Identity Service** | `https://staging.farm-direct.app/api/v1/identity` | `.../api/v1/identity/docs` |
| **Catalog Service** | `https://staging.farm-direct.app/api/v1/catalog` | `.../api/v1/catalog/docs` |
| **Land Service** | `https://staging.farm-direct.app/api/v1/land` | `.../api/v1/land/docs` |
| **Media Service** | `https://staging.farm-direct.app/api/v1/media` | `.../api/v1/media/docs` |
| **Order Service** | `https://staging.farm-direct.app/api/v1/order` | `.../api/v1/order/docs` |
| **Logistics Service** | `https://staging.farm-direct.app/api/v1/logistics` | `.../api/v1/logistics/docs` |
| **Notification Service**| `https://staging.farm-direct.app/api/v1/notification` | `.../api/v1/notification/docs` |
| **Media Storage (MinIO)** | `https://staging.farm-direct.app/farm-media/<path>` | - |

---

## 6. Operations & Troubleshooting

### Check Container Status
```bash
docker compose -f /opt/farm-backend/docker-compose.staging.yml ps
```

### View Live Logs
```bash
# View all logs
docker compose -f /opt/farm-backend/docker-compose.staging.yml logs -f

# View a specific service log
docker compose -f /opt/farm-backend/docker-compose.staging.yml logs -f identity
```

### Monitor Memory and CPU Usage
```bash
docker stats --no-stream
```

### Test Service Health
```bash
curl -k https://127.0.0.1/api/v1/identity/health
```

### Manual Rollback
To roll back to a specific commit SHA without running a new build:
```bash
cd /opt/farm-backend
IMAGE_TAG=<commit-sha> ./infra/staging/deploy.sh
```
