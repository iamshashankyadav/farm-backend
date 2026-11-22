"""Scripted API journeys V1 and V2 (HLD section 5): every step goes through the gateway and every state
change is asserted, so a broken hand-off between two services fails here instead of in the demo.

    V1  listing -> order -> pack -> inspection -> pooling -> delivery -> COMPLETED -> rating
    V2  plot -> reservation -> deposit -> crop update -> harvest -> inspection -> delivery or buy-back

Each run creates its own people (phones carry a run id), so it can run against an empty stack in CI or
against the demo data. Pooling assigns a route to the least loaded delivery partner, so on a stack that
already has idle partners the route may go to one of them; the journey then says so and stops.

    uv run --package farm-seed python -m farm_seed.journeys --admin-phone ... --admin-password ...
"""

import argparse
import os
import random
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from farm_seed import photos
from farm_seed.client import Gateway
from farm_seed.data import PASSWORD
from farm_seed.v1 import _ensure_user, _point
from farm_seed.v2 import _pay_deposit

IST = ZoneInfo("Asia/Kolkata")


class JourneyError(AssertionError):
    pass


def today() -> date:
    return datetime.now(IST).date()


def step(text: str) -> None:
    print(f"  ok  {text}", flush=True)


def expect(condition: object, message: str) -> None:
    if not condition:
        raise JourneyError(message)


def wait_for(check: Callable[[], object], what: str, timeout: float = 90, interval: float = 1.0):
    """Polls until `check` returns something truthy (an event has to be handled first)."""
    deadline = time.monotonic() + timeout
    while True:
        found = check()
        if found:
            return found
        if time.monotonic() >= deadline:
            raise JourneyError(f"timed out after {timeout:.0f}s waiting for {what}")
        time.sleep(interval)


class Run:
    """One journey run: the gateway, the admin, and people made fresh for this run."""

    def __init__(self, gw: Gateway, admin_phone: str, admin_password: str):
        self.gw = gw
        self.admin = gw.login(admin_phone, admin_password)["accessToken"]
        self.id = f"{int(time.time()) % 10**6:06d}"
        self.rng = random.Random(self.id)
        self.crops = {c["id"]: c["defaultUnit"] for c in gw.call("GET", "/catalog/crops").json()}

    def phone(self, prefix: int, n: int) -> str:
        return f"+9199{prefix}{self.id}{n}"  # +91 and ten digits

    def person(
        self, label: str, prefix: int, n: int, roles: list[str], lat: float, lng: float
    ) -> dict:
        """Registers (grants staff roles through the admin) and signs in. Returns user, token, phone."""
        phone = self.phone(prefix, n)
        first = ["customer" if r == "inspector" else r for r in roles]
        tokens = _ensure_user(self.gw, f"Journey {label}", phone, first, lat, lng)
        user = tokens["user"]
        if "farmer" in roles:
            self.gw.call("POST", f"/identity/users/{user['id']}/verify-farmer", token=self.admin)
        if "inspector" in roles:
            self.gw.call(
                "PUT",
                f"/identity/users/{user['id']}/roles",
                token=self.admin,
                json={"roles": ["inspector"]},
            )
        tokens = self.gw.login(phone, PASSWORD)  # a new token carries the new roles
        if "inspector" in roles:
            self.gw.call(
                "PUT",
                "/quality/inspectors/me/location",
                token=tokens["accessToken"],
                json={"location": _point(lat, lng), "available": True},
            )
        return {"id": user["id"], "token": tokens["accessToken"], "phone": phone}

    def get(self, path: str, token: str) -> dict | list:
        return self.gw.call("GET", path, token=token).json()

    def address(self, phone: str, lat: float, lng: float) -> dict:
        return {
            "line1": "12 Journey Lane",
            "city": "Durg",
            "pincode": "491001",
            "contactPhone": phone,
            "location": _point(lat, lng),
        }

    def photo(self, token: str, key: str, owner: str, owner_id: str, lat: float, lng: float) -> str:
        return photos.upload(self.gw, token, key, owner, owner_id, lat, lng, 0)

    def inspection_for(self, subject_type: str, subject_id: str) -> dict:
        def find():
            rows = self.get("/quality/inspections", self.admin)
            return next(
                (
                    r
                    for r in rows
                    if r["subjectType"] == subject_type and r["subjectId"] == subject_id
                ),
                None,
            )

        return wait_for(find, f"the {subject_type.lower()} inspection to be created")

    def report(
        self, inspection: dict, inspector: dict, lat: float, lng: float, weight: float
    ) -> None:
        token = (
            inspector["token"] if inspection.get("inspectorId") == inspector["id"] else self.admin
        )
        media = self.photo(token, "inspection", "INSPECTION", inspection["id"], lat, lng)
        self.gw.call(
            "POST",
            f"/quality/inspections/{inspection['id']}/report",
            token=token,
            json={
                "grade": "A",
                "moisturePct": 11.0,
                "pestFound": False,
                "weightKg": weight,
                "result": "PASS",
                "note": "Journey test: passed.",
                "mediaIds": [media],
            },
        )


def v1(run: Run) -> None:
    """Customer buys produce: order, pack, grade, pool, deliver, complete, rate."""
    gw = run.gw
    lat, lng = 21.19 + run.rng.random() * 0.01, 81.28 + run.rng.random() * 0.01
    farmer = run.person("Farmer V1", 1, 1, ["farmer"], lat, lng)
    customer = run.person("Customer V1", 2, 1, ["customer"], lat + 0.01, lng + 0.01)
    inspector = run.person("Inspector V1", 3, 1, ["inspector"], lat, lng)
    partner = run.person("Partner V1", 4, 1, ["delivery"], lat, lng)
    step("farmer verified by the admin, customer, inspector and delivery partner registered")

    farm = gw.call(
        "POST",
        "/catalog/farms",
        token=farmer["token"],
        json={
            "name": f"Journey Farm {run.id}",
            "district": "Durg",
            "state": "Chhattisgarh",
            "location": _point(lat, lng),
        },
    ).json()
    listing = gw.call(
        "POST",
        "/catalog/listings",
        token=farmer["token"],
        json={
            "farmId": farm["id"],
            "cropId": "tomato",
            "variety": "Hybrid",
            "qtyAvailable": 100,
            "unit": run.crops["tomato"],
            "pricePerUnit": 30,
            "harvestDate": today().isoformat(),
            "isOrganic": False,
        },
    ).json()
    found = run.get(f"/catalog/listings/{listing['id']}", customer["token"])
    expect(found["qtyAvailable"] == 100, "the new listing is not readable by customers")
    step("listing created and visible to a customer")

    intent = gw.call(
        "POST",
        "/order/orders/payments/intent",
        token=customer["token"],
        json={"amount": 1, "kind": "FULL"},
    ).json()
    checkout = gw.call(
        "POST",
        "/order/orders",
        token=customer["token"],
        idempotency_key=f"journey-v1-{run.id}",
        json={
            "items": [{"listingId": listing["id"], "qty": 4}],
            "deliveryAddress": run.address(customer["phone"], lat + 0.01, lng + 0.01),
            "deliveryDate": today().isoformat(),
            "paymentIntentId": intent["id"],
        },
    ).json()
    order = checkout["orders"][0]
    expect(
        order["status"] == "CONFIRMED", f"a paid order should be CONFIRMED, got {order['status']}"
    )
    after = run.get(f"/catalog/listings/{listing['id']}", customer["token"])
    expect(after["qtyAvailable"] == 96, f"stock should drop to 96, is {after['qtyAvailable']}")
    step("order placed and paid: CONFIRMED, stock reduced")

    def notified(user: dict, title: str):
        rows = run.get("/notification/notifications?limit=50", user["token"])["items"]
        return any(n["title"] == title for n in rows)

    wait_for(lambda: notified(customer, "Order Placed Successfully"), "the customer's notification")
    wait_for(lambda: notified(farmer, "New order to pack"), "the farmer's notification", timeout=30)
    step("customer and farmer were both notified")

    gw.call("POST", f"/order/orders/{order['id']}/pack", token=farmer["token"])
    expect(
        run.get(f"/order/orders/{order['id']}", farmer["token"])["status"] == "PACKED",
        "pack failed",
    )
    step("farmer packed the order: PACKED")

    inspection = run.inspection_for("ORDER", order["id"])
    run.report(inspection, inspector, lat, lng, 4)
    wait_for(
        lambda: (
            run.get(f"/order/orders/{order['id']}", customer["token"])["status"]
            == "READY_FOR_DISPATCH"
        ),
        "the order to become READY_FOR_DISPATCH",
    )
    step("inspection passed: READY_FOR_DISPATCH")

    due = today().isoformat()
    pool_stops: list[dict] = []

    def pooled() -> bool:
        pools = gw.call("POST", f"/logistics/pools/run?pool_date={due}", token=run.admin).json()[
            "pools"
        ]
        for pool in pools:
            if any(s["orderId"] == order["id"] for s in pool["stops"]):
                expect(
                    pool.get("partnerId") in (None, partner["id"]),
                    "the route went to another idle delivery partner; run on a stack without other "
                    "idle partners (empty CI stack) or after reset-demo.sh",
                )
                pool_stops[:] = sorted(pool["stops"], key=lambda s: s["seq"])
                return True
        return False

    wait_for(pooled, "the pooling job to include the order", timeout=60, interval=3)
    expect(
        run.get(f"/order/orders/{order['id']}", customer["token"])["status"] == "POOLED"
        or wait_for(
            lambda: (
                run.get(f"/order/orders/{order['id']}", customer["token"])["status"] == "POOLED"
            ),
            "the order to become POOLED",
        ),
        "order is not POOLED",
    )
    step("pooled into a route: POOLED")

    mine = [s for s in pool_stops if s["orderId"] == order["id"]]
    for stop in (s for s in mine if s["stopType"] == "PICKUP"):
        gw.call("POST", f"/logistics/stops/{stop['id']}/pickup", token=partner["token"], json={})
    drop = next(s for s in mine if s["stopType"] == "DROP")
    proof = run.photo(
        partner["token"], "delivery", "DELIVERY", drop["id"], drop["lat"], drop["lng"]
    )
    gw.call(
        "POST",
        f"/logistics/stops/{drop['id']}/deliver",
        token=partner["token"],
        json={"photoMediaId": proof, "otp": drop.get("otp") or "0000", "notes": "Journey test."},
    )
    wait_for(
        lambda: run.get(f"/order/orders/{order['id']}", customer["token"])["status"] == "COMPLETED",
        "the order to become COMPLETED",
        timeout=45,
    )
    step("picked up and delivered with photo proof: COMPLETED")

    gw.call(
        "POST",
        f"/order/orders/{order['id']}/rating",
        token=customer["token"],
        json={"score": 5, "comment": "Journey test."},
    )
    payouts = wait_for(
        lambda: [
            p
            for p in run.get("/order/orders/payouts?limit=50", farmer["token"])["items"]
            if p["orderId"] == order["id"]
        ],
        "the farmer's payout",
        timeout=30,
    )
    expect(payouts[0]["amount"] > 0, "payout amount should be positive")
    wait_for(
        lambda: notified(farmer, "Order delivered"),
        "the farmer's delivery notification",
        timeout=30,
    )
    step("rated; payout recorded and the farmer told")


def v2(run: Run) -> None:
    """Customer reserves land, follows the crop and takes the harvest by delivery or buy-back."""
    gw = run.gw
    lat, lng = 22.1 + run.rng.random() * 0.4, 80.1 + run.rng.random() * 0.4
    farmer = run.person("Farmer V2", 1, 2, ["farmer"], lat, lng)
    customer = run.person("Customer V2", 2, 2, ["customer"], lat + 0.01, lng)
    buyer = run.person("Customer V2b", 2, 3, ["customer"], lat + 0.01, lng)
    inspector = run.person("Inspector V2", 3, 2, ["inspector"], lat, lng)
    step("farmer verified, two customers and an inspector registered")

    seasons: list[tuple[str, dict]] = []
    for n in range(2):
        d_lat, d_lng = lat + n * 0.02, lng
        size = 0.0006
        ring = [
            [d_lng, d_lat],
            [d_lng + size, d_lat],
            [d_lng + size, d_lat + size],
            [d_lng, d_lat + size],
            [d_lng, d_lat],
        ]
        plot = gw.call(
            "POST",
            "/land/plots",
            token=farmer["token"],
            json={
                "title": f"Journey plot {run.id}-{n}",
                "soilType": "Black soil",
                "waterSource": "Borewell",
                "boundary": {"type": "Polygon", "coordinates": [ring]},
            },
        ).json()
        season = gw.call(
            "POST",
            f"/land/plots/{plot['id']}/seasons",
            token=farmer["token"],
            json={
                "season": "Rabi",
                "startDate": (today() + timedelta(days=1)).isoformat(),
                "endDate": (today() + timedelta(days=120)).isoformat(),
                "price": 25,
                "allowedCrops": ["rice"],
            },
        ).json()
        seasons.append((plot["id"], season))
    found = gw.call(
        "GET", f"/land/plots/search?lat={lat}&lng={lng}&radius_km=50", token=customer["token"]
    ).json()
    expect(found, "the new plots do not show in a nearby search")
    step("two plots with a season each, visible in a nearby search")

    def reserve(user: dict, season: dict) -> dict:
        made = gw.call(
            "POST",
            "/land/reservations",
            token=user["token"],
            json={"plotSeasonId": season["id"], "cropId": "rice", "expectedQtyKg": 600},
        ).json()
        expect(made["status"] == "PENDING", f"a new reservation is PENDING, got {made['status']}")
        accepted = gw.call(
            "POST", f"/land/reservations/{made['id']}/accept", token=farmer["token"]
        ).json()
        expect(accepted["status"] == "ACCEPTED", "the farmer's accept did not stick")
        _pay_deposit(gw, user["token"], made["id"], accepted["deposit"])
        wait_for(
            lambda: any(
                r["id"] == made["id"] and r["status"] == "ACTIVE"
                for r in run.get("/land/reservations/mine", user["token"])
            ),
            "the reservation to become ACTIVE after the deposit",
        )
        return made

    delivery = reserve(customer, seasons[0][1])
    buyback = reserve(buyer, seasons[1][1])
    step("both reservations accepted, deposit paid: ACTIVE")

    for made, user in ((delivery, customer), (buyback, buyer)):
        media = run.photo(farmer["token"], "stage_sown", "RESERVATION", made["id"], lat, lng)
        gw.call(
            "POST",
            f"/land/reservations/{made['id']}/updates",
            token=farmer["token"],
            json={
                "stage": "SOWN",
                "note": "Journey sowing.",
                "mediaIds": [media],
                "location": _point(lat, lng),
            },
        )
        updates = run.get(f"/land/reservations/{made['id']}/updates", user["token"])
        expect(
            len(updates) == 1 and updates[0]["mediaIds"] == [media],
            "customer cannot see the crop update",
        )
    step("crop update with a photo posted by the farmer and read by the customer")

    for made in (delivery, buyback):
        gw.call("POST", f"/land/reservations/{made['id']}/harvest-ready", token=farmer["token"])
        inspection = run.inspection_for("HARVEST", made["id"])
        run.report(inspection, inspector, lat, lng, 580)
    step("harvest marked ready and passed by the inspector")

    def harvest_order(user: dict, body: dict) -> dict:
        def attempt():
            r = gw.call(
                "POST",
                "/order/orders/harvest",
                token=user["token"],
                json=body,
                ok=(200, 201, 404, 409, 422),
            )
            return r.json() if r.status_code in (200, 201) else None

        return wait_for(attempt, "the harvest order to be accepted")

    d = harvest_order(
        customer,
        {
            "reservationId": delivery["id"],
            "option": "DELIVERY",
            "deliveryAddress": run.address(customer["phone"], lat + 0.01, lng),
            "deliveryDate": today().isoformat(),
        },
    )
    b = harvest_order(buyer, {"reservationId": buyback["id"], "option": "BUYBACK"})
    for order in (d, b):
        got = run.get(
            f"/order/orders/{order['id']}", customer["token"] if order is d else buyer["token"]
        )
        expect(got["orderType"] == "HARVEST", f"expected a HARVEST order, got {got['orderType']}")
    step("customer chose delivery and the other chose buy-back: both HARVEST orders exist")


JOURNEYS = {"v1": v1, "v2": v2}


def main() -> None:
    parser = argparse.ArgumentParser(prog="farm_seed.journeys", description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default=os.getenv("SEED_BASE_URL", "http://localhost/api/v1"))
    parser.add_argument("--admin-phone", default=os.getenv("SEED_ADMIN_PHONE"))
    parser.add_argument("--admin-password", default=os.getenv("SEED_ADMIN_PASSWORD"))
    parser.add_argument("--journey", choices=("v1", "v2", "all"), default="all")
    args = parser.parse_args()
    if not (args.admin_phone and args.admin_password):
        parser.error(
            "give --admin-phone and --admin-password (or SEED_ADMIN_PHONE / SEED_ADMIN_PASSWORD)"
        )
    names = list(JOURNEYS) if args.journey == "all" else [args.journey]
    failed = False
    for name in names:
        print(f"{name.upper()}: {JOURNEYS[name].__doc__}", flush=True)
        started = datetime.now(UTC)
        try:
            JOURNEYS[name](Run(Gateway(args.base_url), args.admin_phone, args.admin_password))
        except (AssertionError, Exception) as exc:  # noqa: BLE001 - report every kind of failure
            failed = True
            print(f"FAIL {name.upper()}: {exc}", flush=True)
        else:
            print(f"PASS {name.upper()} in {(datetime.now(UTC) - started).seconds}s", flush=True)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
