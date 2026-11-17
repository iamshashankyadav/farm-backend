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

**V2 and orders (run after V1 in the same command):** 1 to 3 plots per farmer (square plots a few acres
each, with a Kharif and a Rabi season), reservations taken to different stages (waiting, accepted,
active with deposit paid and a few crop updates), and produce orders (`--orders`, default 200; use
`--orders 2000` for the full demo set). `--skip-v2` seeds V1 only. Plots are created only for farmers
who have none yet, so re-running does not duplicate them. Orders are placed again on every run
(each order needs a fresh payment), so run with `--orders 0` when re-running.

Not seeded yet: photos (media needs object storage), inspections and delivery pools (quality and
logistics flows are driven by the apps and the pooling job, issue #21 stays open for those).
Reservations become ACTIVE only once RabbitMQ delivers the deposit event, so crop updates for a
just-paid reservation can be skipped by the API; the seeder ignores that.
