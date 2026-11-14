# farm-backend

Shared microservice backend for the Farm Platform: **V1** (selling farm produce) and **V2** (farmland reservation).
Both teams commit here; the website ([farm-web](https://github.com/lakshayg2005/farm-web)) and the apps ([farm-mobile](https://github.com/lakshayg2005/farm-mobile)) consume its APIs.

## Stack

Python 3.12 + FastAPI per service, SQLAlchemy 2 + GeoAlchemy2 + Alembic, PostgreSQL 16 + PostGIS 3 (one schema per service),
RabbitMQ for events, Redis, MinIO (S3) for photos, Traefik as the API gateway, uv for packages, Docker Compose to run everything.

## Services

| Service | Owner | Responsibility |
| --- | --- | --- |
| `identity` | Joint | Users, roles, phone OTP, JWT issue and refresh, farmer verification |
| `catalog` | Team 2 | V1 farms and produce listings, geo search, stock reserve/release |
| `land` | Team 2 | V2 plots, seasons, reservations, crop updates, harvest flow |
| `media` | Team 2 | Signed photo uploads, EXIF/GPS verification, thumbnails |
| `quality` | Team 2 | Inspections and grades for produce batches and harvests |
| `order` | Team 1 | Cart, checkout saga, V1 and V2 orders, mock payments |
| `logistics` | Team 1 | Delivery pooling, routes, partner app API, tracking, proof of delivery |
| `notification` | Team 1 | Push, email and in-app inbox, driven by events |

The gateway (Traefik) routes `/api/v1/<service>/...` to each service. Routes under `/internal/...` are never exposed.

## Layout

```text
services/<service>/      one FastAPI app each: own pyproject.toml, Dockerfile, schema and migrations
contracts/openapi/       OpenAPI spec per service, exported from FastAPI by CI
contracts/events/        JSON Schema per event (e.g. order.placed)
libs/common/             shared Python package: JWT check, logging, errors, event bus + outbox
seed/                    dummy data simulator (calls the gateway API)
infra/                   Traefik and other infrastructure config
docs/                    architecture notes and decisions
```

## Rules between services

- A service reads and writes **only its own schema**. Other services keep IDs, never cross-schema foreign keys.
- Every state change publishes an event through the **outbox** table; consumers dedupe by `event_id`.
- Synchronous calls between services only through `/internal/...` routes, and only when the answer is needed immediately (e.g. stock reserve at checkout).
- **Contracts first:** before building an endpoint, open a PR with the Pydantic models and a stub route. A member of the other team approves the contract diff.

## Workflow (all repos)

- `main` is protected: changes go in only through a pull request with 1 approval.
- One issue per branch: `feat/<area>-<short-name>` or `fix/<area>-<short-name>`. Merge within 2 to 3 days.
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`.
- Squash-merge PRs and write `Closes #<issue>` in the PR description.
- Never commit `.env`; copy `.env.example` instead.
- Issues are labelled by team (`team-app` = Team 1, `team-web` = Team 2, `team-joint`) and by member slot (`M1`–`M4` Team 1, `M5`–`M8` Team 2). Pick your slot and assign yourself.

## Getting started

Setup instructions (Docker Compose, uv) are added by the Sprint 1 infrastructure issues.
