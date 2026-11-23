# seed

Demo data for the platform, built only through the gateway API (so it passes the same validation and
publishes the same events as real traffic). It has two profiles:

| Profile | Command | What it is for |
| --- | --- | --- |
| `demo` (default) | `scripts/reset-demo.sh` | A small, believable story around Durg and Bhilai: named farmers and farms, real openly licensed photos with GPS, plots, reservations at every stage, orders in every status, pooled routes and deliveries made with each customer's delivery code. See [docs/DEMO.md](../docs/DEMO.md) for the logins and the tour. |
| `volume` | `python -m farm_seed --profile volume ...` | Generated people and orders in bulk, for load and geo-search tests. Not meant to be shown. |

The demo profile needs an **empty** database (it refuses to run if the demo farmer already exists):
`scripts/reset-demo.sh` wipes the docker compose volumes, starts the stack, creates the admin and seeds.
Photos live in `seed/assets/photos` with their authors and licences in `seed/assets/CREDITS.md`;
`seed/tools/fetch_photos.py` re-downloads them from Wikimedia Commons.

**Journeys** (`python -m farm_seed.journeys`): two scripted API walks with an assertion at every status change,
using people created for the run. V1 is an unverified farmer refused, then listing, order, pack, pooling, delivery with the customer's code, rating and payout;
V2 is plot, reservation, deposit, crop update, harvest with its weight, then a pooled delivery for one customer and buy-back
for another. Both also check that customers and farmers are notified. They run in CI (`.github/workflows/journeys.yml`)
against an empty stack, and take about 15 seconds each locally:

```bash
SEED_ADMIN_PHONE=+919999999999 SEED_ADMIN_PASSWORD='DemoAdmin@2026' \
  uv run --package farm-seed python -m farm_seed.journeys            # or --journey v1 / v2
```

Pooling gives a route to the least loaded delivery partner, so if the stack already has other idle partners the
V1 journey may stop with a message saying so; run it after `scripts/reset-demo.sh` or on an empty stack.

The rest of this file describes the `volume` profile.

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

**Operations (runs last, `--skip-ops` to leave it out):** takes up to 90 of the placed orders through the
whole flow with API calls only, so every app has data: some stay CONFIRMED, some are cancelled, and the
rest are packed, which makes them READY_FOR_DISPATCH (there is no quality gate). Then it runs the real
pooling job (`POST /logistics/pools/run`) and delivery partners work the pools: some delivered (each
drop with the code its customer reads from their tracking page), some with pickups done (in progress),
some untouched. It also creates 4 delivery partners (`+919000400001` to `04`), same password. The
steps that rely on events poll for up to 90 seconds, so RabbitMQ and the workers must be up. Run it
on a fresh database: it only picks up orders that are still CONFIRMED.

Not seeded yet in this profile: photos (media needs object storage), so proof of delivery carries no
real photo (a random media id).
Reservations become ACTIVE only once RabbitMQ delivers the deposit event, so crop updates for a
just-paid reservation can be skipped by the API; the seeder ignores that.
