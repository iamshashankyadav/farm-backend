"""Operations seeding: takes the placed orders through packing, pooling and delivery so every part
of the apps has data. Everything goes through the public API (the real pooling job
included); the steps that depend on events poll until the event has been handled.

Orders are split into fixed groups by their position, so the result is the same on every run:

    k % 12 in 0, 2   left CONFIRMED (the farmer still has to pack them)
    k % 12 == 1      cancelled by the farmer
    k % 12 >= 3      packed -> READY_FOR_DISPATCH (there is no quality gate) -> pooled

Pools are then handled in turn: delivered, in progress (pickups done) or left waiting. Each drop is
delivered with the code its customer reads from their tracking page, as in the apps.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import uuid4

from farm_seed.client import Gateway, SeedError
from farm_seed.data import PASSWORD
from farm_seed.v1 import _ensure_user

PARTNERS = [
    ("Rider Deepak", "+919000400001"),
    ("Rider Esha", "+919000400002"),
    ("Rider Farhan", "+919000400003"),
    ("Rider Gauri", "+919000400004"),
]
MAX_LIFECYCLE_ORDERS = 90


@dataclass
class OpsSummary:
    partners: int = 0
    cancelled: int = 0
    packed: int = 0
    pools: int = 0
    pools_delivered: int = 0
    pools_in_progress: int = 0
    notes: list[str] = field(default_factory=list)


def _wait(check: Callable[[], bool], timeout: float, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if check():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def _login(gw: Gateway, cache: dict[str, str], phone: str) -> str:
    if phone not in cache:
        cache[phone] = gw.login(phone, PASSWORD)["accessToken"]
    return cache[phone]


def _staff(
    gw: Gateway,
    summary: OpsSummary,
    partner_phone: dict[str, str],
) -> None:
    """Create the delivery partners."""
    for name, phone in PARTNERS:
        partner = _ensure_user(gw, name, phone, ["delivery"])["user"]
        partner_phone[partner["id"]] = phone
        summary.partners += 1


def _confirmed_orders(
    gw: Gateway, farmer_phones: list[str], tokens: dict[str, str]
) -> list[tuple[str, int]]:
    """(order id, farmer index) of CONFIRMED orders, oldest first, at most MAX_LIFECYCLE_ORDERS."""
    found: list[tuple[str, str, int]] = []
    for f_idx, phone in enumerate(farmer_phones):
        page = gw.call(
            "GET",
            "/order/orders?role=farmer&status=CONFIRMED&limit=100",
            token=_login(gw, tokens, phone),
        ).json()
        rows = page["items"] if isinstance(page, dict) else page
        found += [
            (row["createdAt"], row["id"], f_idx) for row in rows if row["status"] == "CONFIRMED"
        ]
    found.sort()
    return [(order_id, f_idx) for _, order_id, f_idx in found[:MAX_LIFECYCLE_ORDERS]]


def _customer_of(gw: Gateway, tokens: dict[str, str], customer_phones: list[str]) -> dict[str, str]:
    """Order id -> the phone of the customer who placed it (only they can read its delivery code)."""
    owner: dict[str, str] = {}
    for phone in customer_phones:
        token, cursor = _login(gw, tokens, phone), None
        while True:
            query = "/order/orders?role=customer&limit=100" + (
                f"&cursor={cursor}" if cursor else ""
            )
            page = gw.call("GET", query, token=token).json()
            owner.update({row["id"]: phone for row in page["items"]})
            cursor = page.get("nextCursor")
            if not cursor:
                break
    return owner


def _delivery_code(gw: Gateway, token: str, order_id: str) -> str:
    track = gw.call("GET", f"/logistics/orders/{order_id}/track", token=token).json()
    return (track.get("stop") or {}).get("otp") or ""


def seed_operations(
    gw: Gateway,
    farmer_phones: list[str],
    admin_phone: str,
    admin_password: str,
    customer_phones: list[str],
    wait_seconds: float = 90,
) -> OpsSummary:
    """Orders are found through each farmer's order list, so this also works on a later run."""
    summary = OpsSummary()
    tokens: dict[str, str] = {}
    admin = gw.login(admin_phone, admin_password)["accessToken"]
    partner_phone: dict[str, str] = {}
    _staff(gw, summary, partner_phone)
    orders = _confirmed_orders(gw, farmer_phones, tokens)

    # --- cancel and pack ---
    packed: list[str] = []
    group: dict[str, int] = {}
    for k, (order_id, f_idx) in enumerate(orders):
        group[order_id] = k % 12
        token = _login(gw, tokens, farmer_phones[f_idx])
        if k % 12 in (0, 2):
            continue
        if k % 12 == 1:
            done = gw.call(
                "POST",
                f"/order/orders/{order_id}/cancel",
                token=token,
                json={"reason": "Seeded cancellation"},
                ok=(200, 403, 409),
            )
            summary.cancelled += 1 if done.status_code == 200 else 0
            continue
        done = gw.call("POST", f"/order/orders/{order_id}/pack", token=token, ok=(200, 403, 409))
        if done.status_code == 200:
            packed.append(order_id)
            summary.packed += 1

    # --- pooling: the real job over every READY_FOR_DISPATCH order ---
    due = (date.today() + timedelta(days=14)).isoformat()
    pools: list[dict] = []

    def run_pooling() -> bool:
        nonlocal pools
        response = gw.call("POST", f"/logistics/pools/run?pool_date={due}", token=admin).json()
        pools = response["pools"]
        return bool(pools)

    if not _wait(run_pooling, wait_seconds, interval=3):
        summary.notes.append("no orders were ready for dispatch, so no pools were made")
    summary.pools = len(pools)

    # --- delivery: partners work through the pools ---
    customer_of = _customer_of(gw, tokens, customer_phones)
    for i, pool in enumerate(pools):
        # the pooling job assigns a partner; fall back to taking turns if it could not
        phone = partner_phone.get(pool.get("partnerId") or "") or PARTNERS[i % len(PARTNERS)][1]
        token = _login(gw, tokens, phone)
        mode = i % 4  # 0 and 3: delivered, 1: pickups only (in progress), 2: left waiting
        if mode == 2:
            continue
        stops = sorted(pool["stops"], key=lambda s: s["seq"])
        for stop in (s for s in stops if s["stopType"] == "PICKUP"):
            gw.call("POST", f"/logistics/stops/{stop['id']}/pickup", token=token, json={})
        if mode == 1:
            summary.pools_in_progress += 1
            continue
        for stop in (s for s in stops if s["stopType"] == "DROP"):
            buyer = customer_of.get(stop["orderId"])
            if buyer is None:
                summary.notes.append(f"no customer found for order {stop['orderId']}")
                continue
            code = _delivery_code(gw, _login(gw, tokens, buyer), stop["orderId"])
            gw.call(
                "POST",
                f"/logistics/stops/{stop['id']}/deliver",
                token=token,
                json={"photoMediaId": str(uuid4()), "otp": code},
            )
        summary.pools_delivered += 1
    return summary


__all__ = ["OpsSummary", "SeedError", "seed_operations"]
