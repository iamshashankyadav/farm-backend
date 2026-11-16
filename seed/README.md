# seed

Dummy data simulator. Uses a fixed random seed and calls the gateway API with an admin token, so
seeded data passes the same validation and publishes the same events as real traffic. Running it
twice is safe: existing accounts and farms are reused.

**V1 (this version):** 20 verified farmers in 8 districts, their farms, 3 to 6 produce listings per
farm, and 40 customers. Every account's password is `Farm@12345` (dev only); phones are
`+919000100000...` (farmers) and `+919000200000...` (customers).

```bash
# the stack must be running (docker-compose, issue #2) and an admin must exist:
#   uv run --package farm-identity python -m identity_service.cli create-admin ...
export SEED_ADMIN_PHONE=+919999999999 SEED_ADMIN_PASSWORD=change-me-please
uv run --package farm-seed python -m farm_seed                 # defaults to http://localhost/api/v1
uv run --package farm-seed python -m farm_seed --farmers 5 --customers 10
```

Photos are not seeded yet (media needs object storage); listings show without images.
V2 data (plots, reservations, orders) is added in Sprint 3 (issue #21).
