# infra

| Path | What |
| --- | --- |
| `../docker-compose.yml` | The whole backend: Postgres + PostGIS, RabbitMQ, Redis, MinIO, Traefik gateway, 8 services, media worker |
| `postgres/init-db.sh` | Runs once on a fresh database volume: enables PostGIS, then creates one schema and one login role (`farm_<service>`) per service |
| `traefik/traefik.yml`, `traefik/dynamic.yml` | Gateway config: routing, CORS, rate limits |

## Run everything

```bash
cp .env.example .env
uv run python scripts/gen_jwt_keys.py        # writes secrets/jwt_private.pem and jwt_public.pem
docker compose up --build
```

Each service container runs its Alembic migrations (in its own schema) and then starts the API.

| URL | What |
| --- | --- |
| `http://localhost/api/v1/<service>/...` | API through the gateway, e.g. `/api/v1/identity/login` |
| `http://localhost/api/v1/<service>/docs` | Swagger UI of that service |
| `http://localhost:15672` | RabbitMQ management (user/password from `.env`) |
| `http://localhost:9001` | MinIO console |
| `localhost:5432` | Postgres (use the `farm` user from `.env`) |

First admin, then demo data:

```bash
docker compose exec identity python -m identity_service.cli create-admin \
    --name "Platform Admin" --phone +919999999999 --password "change-me-please"
SEED_ADMIN_PHONE=+919999999999 SEED_ADMIN_PASSWORD=change-me-please \
    uv run --package farm-seed python -m farm_seed
```

To wipe all data: `docker compose down -v`.

## Gateway rules

- `/api/v1/<service>/...` goes to that service with the prefix removed; `ROOT_PATH` makes its Swagger UI links work.
- `/api/v1/<service>/internal/...` is answered with 404: internal routes exist only on the Docker network.
- Rate limits: 50 requests/second per client in general, 5/second on login, register, refresh and OTP.
- CORS allows the Vite dev and preview servers (`localhost:5173`, `localhost:4173`). Add the staging site's origin in `traefik/dynamic.yml` when it exists.
- Token checks: every service verifies the JWT itself with the public key (`farm_common.auth`), so the gateway does not call identity on each request. `GET /internal/auth/verify` stays available for any route that needs a check at the gateway.
