# Overhaul roadmap (November 2026)

Goal: web, apps and backend behave as one product; no fake data anywhere; one curated demo
dataset; a clean, consistent UI on web and mobile; every planned feature (HLD section 5, F1 to F15)
verified end to end.

## Status

| Phase | What | State |
| --- | --- | --- |
| 0 | Sync repos to `main`, clean stack on an empty volume | Done |
| 1 | Live audit of every feature against the real backend | Done: findings below |
| 2 | Sync: fix client bugs, regenerate API types, working photos | Done for the website (farm-web #27) and backend (#64, #66). Mobile fakes are in [android-handoff.md](android-handoff.md) |
| 3 | Curated demo seed, [DEMO.md](DEMO.md), `scripts/reset-demo.sh` | Done (#65); local stack and the team VM reseeded |
| 4 | Web redesign, direction C "Ledger" | Done and merged (farm-web #28 to #31); checked at 390 and 1440 px for every role |
| 5 | Mobile redesign: Kotlin app, handed to the Android session | Brief and copy-paste prompt written ([android-prompt.md](android-prompt.md)), direction C tokens included |
| 6 | End-to-end tests (Playwright, API flows), screenshots, VM deploy, demo script | Done except the VM deploy: `pnpm e2e` (31 tests, web #30), `farm_seed.journeys` V1 and V2 (backend #68, closes #22), [DEMO-SCRIPT.md](DEMO-SCRIPT.md). All merged on 2026-11-22; VM deploy still to do |
| 7 | New features | P1 and P2 merged: farm ratings, low-stock alerts with auto sold-out, Hindi and English. P3 open |
| 8 | End-to-end audit (2026-11-23) | Quality gate removed, 15 defects fixed, VM seed data removed (see below). Android follow-ups in [android-handoff.md](android-handoff.md) section 12 |

## End-to-end audit, 2026-11-23

Every flow was replayed on an empty stack (probe scripts, `farm_seed.journeys`, a new website journey
`e2e/journey.spec.ts` that needs no demo data). Decisions taken with the team lead:

- **The quality gate is removed** (inspections, inspector role, listing grades, the quality service).
  Packing makes an order ready for dispatch; a harvest becomes an order when the farmer records its weight.
  Quality is judged by the customer's rating after delivery (the admin dashboard shows the average).
- **The team VM holds no demo data**: the seeded people and everything linked to them were deleted
  (backups in `~/backups` on the VM); the admin and the accounts people registered themselves were kept.

Defects found and fixed (each has a test):

| Area | Defect | Fix |
| --- | --- | --- |
| Identity, catalog, land | Unverified farmers could open farms, list produce and offer land | Token claim `fv`; 403 `FARMER_NOT_VERIFIED`; the website hides the forms until verified |
| Logistics | The delivery OTP was never generated, so any code was accepted; the customer never saw a code | 4-digit code per drop, shown only to the order's customer, hidden from partners and admins, checked on delivery |
| Logistics | Any signed-in user could track any order (partner name, phone, live location) | Tracking answers 404 to anyone but the order's customer or an admin |
| Logistics | The partner had no phone number for the customer | The dispatch feed carries the contact phone |
| Logistics | Running pooling twice put the same order on two routes | Runs are serialised (advisory lock) and orders already on a route are skipped |
| Logistics | Vehicle capacity was 50 kg (HLD: 500 kg); a quintal counted as 1 kg | 500 kg; weights converted per unit |
| Logistics | The 02:00 IST nightly job pooled the UTC date, i.e. yesterday | India dates for the job and the route defaults |
| Logistics | A drop could be delivered before its pickup; a delivered stop could be skipped | 409 `PICKUP_FIRST`, 409 `STOP_DONE` |
| Land | Overlapping seasons let the same land to two customers (the demo seed itself did this) | Exclusion constraint + 409 `SEASON_OVERLAP` |
| Land | Ended seasons were offered in search; a farmer could reserve their own plot | Hidden from search; 422 `OWN_PLOT` |
| Land | An expired request kept the season for up to a minute and nobody was told | Expired at once on a new request; `reservation.expired` tells both sides |
| Land | Reservations never reached COMPLETED after delivery or buy-back | Land follows the harvest order (FULFILLING, COMPLETED, CANCELLED) |
| Order | Buy-back credited 90 % of the harvest while only the 20 % deposit was paid | The balance is charged first; the farmer keeps 10 % as a payout |
| Notification | No notice for new, rejected, cancelled or expired land requests, deposits paid, crop updates or verification; a harvest told the farmer "New order to pack" | Events from land and identity, notices to the right side |
| Website | The harvest choice was shown at HARVEST_READY (when the API refuses it) and hidden at FULFILLING (when it is due) | Shown while the harvest order waits for a choice, with the amounts |

Still open after the audit:

- Android: the screens listed in [android-handoff.md](android-handoff.md) section 12 (rail stage "Graded",
  grade filter, harvest texts). The app works against the new backend; those texts are out of date.
- Gateway: tokens are checked in each service, not by Traefik forward-auth (identity already serves
  `/internal/auth/verify`). Equivalent security, one less hop; switch if the course requires it.
- Pooling clusters in Python (haversine DBSCAN) rather than `ST_ClusterDBSCAN`; fine at this size.
- A skipped drop stays on its route; there is no re-pooling of skipped orders yet.
- Crop updates show the day they were posted, not the photo's capture time.

## Fixed earlier

- **Photos were silently lost** (backend #64): the media and logistics workers shared arq's default queue,
  so the logistics worker took about half of the media jobs and dropped them. 11 of 40 test uploads stuck,
  now 0 of 60.
- **Photo URLs answered 403** after a slow storage start (backend #66): the public-read policy was applied
  once at startup. It now retries until storage answers.
- **Wrong season could be reserved** (web #27): plot-season ids were not used for selection.
- Farmer payouts now come from the payouts endpoint; Leaflet is bundled instead of loaded from a CDN.

## Still open

- Reserving an ended season: fixed in backend #69, pooling plural fixed in web #31.
- ~~Reservation requests send no notification to the farmer~~ fixed in the 2026-11-23 audit (`reservation.requested`).
- The admin dashboard computes its numbers in the browser from the order list; add a stats endpoint if orders grow into the thousands.
- Running `farm_seed.journeys` on the demo stack adds "Journey" people and plots; reseed to clear them before presenting.
- Crop updates show the day they were created, not the photo's capture time.
- Hindi: the website covers the shell, sign-in, home, notifications, farmer listings, orders and earnings; plots, crop updates, reservation forms, customer land search and the admin page bodies still read English. Server text (notification bodies, errors) is English; sending a language with the request would fix that.
- Low-stock lines are one number per unit in `catalog_service/service.py` (`LOW_STOCK_THRESHOLD`); a per-listing threshold needs a column.
- Farm ratings only count ratings made after the catalog migration `0002_farm_ratings`; older ratings stay in the order service.
- Mobile apps: fake-data fallbacks, mock logins, fabricated reservations (android-handoff.md section 5).

## Phase 1 findings so far

- All eight services report healthy behind the gateway on a fresh database.
- The existing seed (6 farmers, 12 customers, 30 orders) completes in about 45 s: 46 listings,
  12 plots, 10 reservations, 34 orders packed, 26 inspections reported, 7 pools, 3 delivered.
- Seeded reservations produce **no crop updates** (`crop_updates=0`): a reservation only becomes
  ACTIVE after the deposit event round trip, and the seeder does not wait for it. The demo seed
  must wait for ACTIVE and then post updates, otherwise the crop timeline is empty everywhere.
- No photos are seeded, so inspection reports, listings and delivery proof carry none. Needs object
  storage on every environment, and real photos in the demo seed.
- `GET /catalog/listings/search` rejects `radius_km` above 100 (422): clients must clamp.
- Client problems found by reading code: silent fallbacks to bundled fake data in both mobile
  stacks, a reservation that is fabricated locally when the API call fails (Kotlin), mock login
  buttons, hard-coded placeholder text ("Local Village", "Assigned Farmer"), no call to the crop
  updates endpoint, and a gateway URL hard-coded in `gradle.properties`.

## Phase 2: sync (clients and backend agree)

1. Delete every fake-data path and mock login in web and mobile (see android-handoff.md section 5).
2. Run `pnpm gen:api` in the web repo against the current specs (payouts and agreements landed in
   backend #62) and fix payload drift.
3. Object storage on the team VM (MinIO community build), then verify upload, thumbnail and GPS
   verification end to end from the web.
4. Add typed error and empty states everywhere a request can fail.
5. Fix each defect from Phase 1 in the owning repo, one PR per issue.

## Phase 3: demo seed

A small curated story instead of Faker volume: about 10 farmers with believable names in 2 to 3
districts, real crop photos (openly licensed, credited), about 25 customers, 3 inspectors, 4
delivery partners, orders and reservations spread over every status, easy-to-remember demo logins
per role, and a `--volume` flag for load and geo-search tests. Wipe databases, object storage and
RabbitMQ queues first (the VM wipe is approved).

## Phase 4 and 5: UI

Design tokens, a small shared component set, and rebuilt screens per role, with loading, empty and
error states and layouts from 360 px up. Web first (React, Tailwind, Motion for transitions only
where they explain a change). The Android session follows the same direction.

## Phase 6: verification

Playwright journeys per role, two scripted API journeys (V1: listing, order, pack, inspection,
pool, delivery, rating. V2: plot, reservation, deposit, crop updates, harvest, inspection,
delivery or buy-back), screenshots at 390 px and 1440 px, deploy to the VM, written demo script.
Closes backend #22 and #26.

## Phase 7: new features

| Priority | Feature |
| --- | --- |
| P1 | Farmer earnings ledger page (payouts endpoint exists since #62) |
| P1 | Notification inbox with unread badge on web |
| P1 | Admin dashboard with real numbers: orders per day, sales, customer rating (was inspection pass rate), km saved by pooling |
| P1 | Admin orders view with dispute and refund action |
| P2 | Farm ratings shown on listings |
| P2 | Low-stock alert, auto-pause listing at zero stock |
| P2 | Hindi and English |
| P2 | Inspector screens usable on a phone browser (built, then dropped with the quality gate) |
| P3 | Receipts and agreement PDFs, reorder and favourite farms, partner earnings, weather on the crop timeline |
