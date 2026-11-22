# Demo script (about 12 minutes)

Run `scripts/reset-demo.sh` (or `~/reset-demo.sh` plus the seed on the team VM) **on the day you present**: the orders
are due today, so the delivery partners have a route and the pooling page has data. Logins are in [DEMO.md](DEMO.md).
Open the website in a desktop window and, for the mobile moments, a 390 px wide window (browser dev tools).

Two stories, told in the order the platform was designed for (HLD section 5).

## V1: from the farmer's field to the table (6 minutes)

1. **Customer (app).** Sign in as Aarav, +919200000001. Browse produce near Bhilai, add tomato from Sahu Krishi Farm and
   cauliflower from a second farm, pay. Two orders appear, one per farm. *Say:* one checkout, one order per farm.
2. **Farmer (web).** Sign in as Ramesh, +919100000001. **Orders → To pack** shows the new order and the stage bar at 2 of 8.
   Open **Notifications**: "New order to pack". Press **Mark packed**; the bar moves to 3.
3. **Inspector (web, 390 px).** Sign in as Asha, +919300000001. **Inspections → Waiting for an inspector**: claim the packed
   order, report grade A with a photo. *Say:* the photo keeps its GPS and capture time; the badge says whether it was taken
   at the farm. Show the listing photo from Verma Organic Farm that is **Unverified** on purpose (6 km away).
4. **Admin (web).** Sign in as +919999999999 (password in DEMO.md). **Dashboard**: orders per day, sales, inspection pass
   rate. **Pooling**: pick today, **Run pooling**; routes appear on the map with kilometres saved against separate trips.
   **Orders → Needs a step**: where anything is stuck. *Say:* an admin can cancel and refund from here.
5. **Delivery partner (app).** Deepak, +919400000001: today's route, pickups, then a drop with the OTP and a photo.
6. **Customer and farmer again.** The order reads Delivered, the customer rates it, the farmer's **Earnings** page lists the
   payout under the month.

## V2: reserve a field and follow the crop (6 minutes)

1. **Customer (web).** Sanjay, +919200000005, **Find land**: search the map, open a plot, see seasons and the price per kg.
   Try to reserve a season that has ended: the API refuses it ("This season has already ended").
2. **Farmer (web).** Dinesh, +919100000005, **Requests**: accept the waiting request; the 48 hour timer is visible. The
   customer pays the deposit and the reservation turns **Active** (this crosses land, order and notification services).
3. **Crops (farmer).** **Crops**: stage bar Sown, Growing, Flowering, Harvest ready; **Post an update** with a photo.
4. **Customer.** **My reservations → Growing**: the same timeline with the farmer's photos. *Say:* the customer follows the
   crop from a phone without calling anyone.
5. **Harvest.** Open Ritu's finished rice reservation (+919200000008): harvest ready, inspected by Asha, the customer chose
   delivery and the order joined a pooled route. The alternative, **buy-back**, is a one-click choice on **My reservations**.

## If something goes wrong

- A page says "Could not load": every list has a Try again button; check `GET /api/v1/<service>/health`.
- No photos: the media worker or object storage is down (`docker compose ps`; on the VM `~/start-minio.sh`).
- Pooling shows nothing: the orders are not due today. Reseed.
- An order did not move after packing: RabbitMQ is the hand-off between services; check its queues for a backlog.

## Proof that it works without you

- `uv run --package farm-seed python -m farm_seed.journeys` walks V1 and V2 through the API with an assertion at every
  status change (about 30 seconds), and runs in CI on an empty stack.
- `pnpm e2e` in farm-web drives every role's pages at 390 and 1440 px, and fails on any console error or 5xx.
