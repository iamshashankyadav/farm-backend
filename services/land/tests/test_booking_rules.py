"""Booking rules against PostGIS: who may offer land, overlapping seasons, ended and expired
seasons, reserving your own plot, the events each step sends, and the harvest flow without a
quality gate."""

from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import text

from farm_common.events import Event
from land_service.consumers import make_handler
from land_service.events_runtime import expire_pending_reservations
from land_service.routes import today_ist

from .conftest import token_for

FARMER, CUSTOMER, OTHER = uuid4(), uuid4(), uuid4()
FARMER_H = token_for(FARMER, "farmer")
CUSTOMER_H = token_for(CUSTOMER, "customer")
OTHER_H = token_for(OTHER, "customer")


def square(lng: float, lat: float, size: float = 0.003) -> dict:
    ring = [[lng, lat], [lng + size, lat], [lng + size, lat + size], [lng, lat + size], [lng, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


async def plot(client, lng=81.30, lat=21.20) -> dict:
    response = await client.post(
        "/plots", json={"title": "River plot", "boundary": square(lng, lat)}, headers=FARMER_H
    )
    assert response.status_code == 201, response.text
    return response.json()


async def season(client, plot_id, start: date, days: int = 90, name="Rabi", status=201) -> dict:
    response = await client.post(
        f"/plots/{plot_id}/seasons",
        json={
            "season": name,
            "startDate": start.isoformat(),
            "endDate": (start + timedelta(days=days)).isoformat(),
            "price": 30,
            "allowedCrops": ["wheat"],
        },
        headers=FARMER_H,
    )
    assert response.status_code == status, response.text
    return response.json()


async def reserve(client, season_id, headers=CUSTOMER_H, status=201) -> dict:
    response = await client.post(
        "/reservations",
        json={"plotSeasonId": season_id, "cropId": "wheat", "expectedQtyKg": 100},
        headers=headers,
    )
    assert response.status_code == status, response.text
    return response.json()


async def test_an_unverified_farmer_cannot_offer_land(client):
    response = await client.post(
        "/plots",
        json={"title": "Waiting plot", "boundary": square(81.4, 21.3)},
        headers=token_for(uuid4(), "farmer", verified=False),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FARMER_NOT_VERIFIED"


async def test_seasons_of_one_plot_cannot_overlap(client):
    p = await plot(client)
    start = today_ist()
    first = await season(client, p["id"], start)

    clash = await season(client, p["id"], start + timedelta(days=30), name="Again", status=409)
    after = await season(client, p["id"], start + timedelta(days=91), name="Zaid")
    moved = await client.patch(
        f"/plots/{p['id']}/seasons/{after['id']}",
        json={
            "season": "Zaid",
            "startDate": (start + timedelta(days=80)).isoformat(),
            "endDate": (start + timedelta(days=120)).isoformat(),
            "price": 30,
            "allowedCrops": ["wheat"],
        },
        headers=FARMER_H,
    )

    assert clash["error"]["code"] == "SEASON_OVERLAP"
    assert clash["error"]["details"]["seasonId"] == first["id"]
    assert moved.status_code == 409


async def test_the_database_refuses_overlapping_seasons_too(client, session_factory):
    p = await plot(client)
    await season(client, p["id"], date(2030, 1, 1))
    async with session_factory() as session:
        try:
            await session.execute(
                text(
                    "INSERT INTO land.plot_seasons (id, plot_id, season, start_date, end_date, "
                    "price, allowed_crops, created_at) VALUES (:id, :plot, 'X', '2030-02-01', "
                    "'2030-03-01', 10, '{}', now())"
                ),
                {"id": uuid4(), "plot": p["id"]},
            )
            await session.commit()
            refused = False
        except Exception as exc:
            refused = "plot_seasons_no_overlap" in str(exc)
    assert refused


async def test_search_hides_ended_and_taken_seasons(client):
    p = await plot(client)
    today = today_ist()
    await season(client, p["id"], today - timedelta(days=200), days=100, name="Kharif")
    open_season = await season(client, p["id"], today, name="Rabi")
    taken = await season(client, p["id"], today + timedelta(days=100), days=60, name="Zaid")
    await reserve(client, taken["id"])

    found = await client.get("/plots/search", params={"lat": 21.2, "lng": 81.3, "radius_km": 5})

    seasons = [f["properties"]["plotSeasonId"] for f in found.json()["features"]]
    assert seasons == [open_season["id"]]


async def test_a_farmer_cannot_reserve_their_own_plot(client):
    p = await plot(client)
    s = await season(client, p["id"], today_ist())

    both = token_for(FARMER, "farmer", "customer")
    response = await reserve(client, s["id"], headers=both, status=422)

    assert response["error"]["code"] == "OWN_PLOT"


async def test_a_new_request_tells_the_farmer_and_a_rejection_tells_the_customer(client, outbox):
    p = await plot(client)
    s = await season(client, p["id"], today_ist())
    r = await reserve(client, s["id"])

    rejected = await client.post(f"/reservations/{r['id']}/reject", headers=FARMER_H)

    assert rejected.json()["status"] == "REJECTED"
    (requested,) = await outbox("reservation.requested")
    assert requested.payload["farmerId"] == str(FARMER)
    assert requested.payload["plotTitle"] == "River plot"
    (rejection,) = await outbox("reservation.rejected")
    assert rejection.payload["customerId"] == str(CUSTOMER)


async def test_an_expired_request_frees_the_season_at_once(client, session_factory, outbox):
    p = await plot(client)
    s = await season(client, p["id"], today_ist())
    stale = await reserve(client, s["id"])
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE land.reservations SET expires_at = now() - interval '1 hour' WHERE id = :id"
            ),
            {"id": stale["id"]},
        )
        await session.commit()

    fresh = await reserve(client, s["id"], headers=OTHER_H)

    assert fresh["status"] == "PENDING"
    mine = await client.get("/reservations/mine", headers=CUSTOMER_H)
    assert mine.json()[0]["status"] == "EXPIRED"
    (expired,) = await outbox("reservation.expired")
    assert expired.payload["reservationId"] == stale["id"]


async def test_the_expiry_worker_tells_both_sides(client, session_factory, outbox):
    p = await plot(client)
    s = await season(client, p["id"], today_ist())
    r = await reserve(client, s["id"])
    async with session_factory() as session:
        await session.execute(
            text("UPDATE land.reservations SET expires_at = now() - interval '1 minute'")
        )
        await session.commit()

    assert await expire_pending_reservations(session_factory) == 1

    (event,) = await outbox("reservation.expired")
    assert event.payload == {
        "reservationId": r["id"],
        "customerId": str(CUSTOMER),
        "farmerId": str(FARMER),
        "cropId": "wheat",
    }


async def active(client, session_factory) -> dict:
    p = await plot(client)
    s = await season(client, p["id"], today_ist())
    r = await reserve(client, s["id"])
    accepted = (await client.post(f"/reservations/{r['id']}/accept", headers=FARMER_H)).json()
    await make_handler(session_factory)(
        Event(
            type="payment.succeeded",
            producer="order",
            payload={"kind": "DEPOSIT", "referenceId": r["id"], "amount": accepted["deposit"]},
        )
    )
    return r


async def test_accepting_sends_the_agreed_price_and_paying_activates(
    client, session_factory, outbox
):
    r = await active(client, session_factory)

    (accepted,) = await outbox("reservation.accepted")
    assert accepted.payload["total"] == 3000  # 100 kg at 30 a kg
    assert accepted.payload["pricePerKg"] == 30
    assert accepted.payload["expectedQtyKg"] == 100
    (activated,) = await outbox("reservation.activated")
    assert activated.payload["farmerId"] == str(FARMER)
    mine = (await client.get("/reservations/mine", headers=CUSTOMER_H)).json()
    assert [x["status"] for x in mine if x["id"] == r["id"]] == ["ACTIVE"]


async def test_a_crop_update_tells_the_customer(client, session_factory, outbox):
    r = await active(client, session_factory)

    posted = await client.post(
        f"/reservations/{r['id']}/updates",
        json={"stage": "SOWN", "note": "Seeds in"},
        headers=FARMER_H,
    )

    assert posted.status_code == 201, posted.text
    (event,) = await outbox("crop.updated")
    assert event.payload["customerId"] == str(CUSTOMER)
    assert event.payload["stage"] == "SOWN"


async def test_harvest_ready_carries_the_weight_and_the_order_completes_it(
    client, session_factory, outbox
):
    r = await active(client, session_factory)

    ready = await client.post(
        f"/reservations/{r['id']}/harvest-ready", json={"harvestedQtyKg": 92}, headers=FARMER_H
    )

    assert ready.json()["status"] == "HARVEST_READY"
    (event,) = await outbox("harvest.ready")
    assert event.payload["harvestedQtyKg"] == 92
    assert event.payload["total"] == 3000
    handle = make_handler(session_factory)
    for step, expected in (("order.placed", "FULFILLING"), ("order.completed", "COMPLETED")):
        await handle(
            Event(
                type=step,
                producer="order",
                payload={"orderType": "HARVEST", "reservationId": r["id"]},
            )
        )
        mine = (await client.get("/reservations/mine", headers=CUSTOMER_H)).json()
        assert [x["status"] for x in mine if x["id"] == r["id"]] == [expected]


async def test_a_completed_season_is_not_offered_again(client, session_factory):
    r = await active(client, session_factory)
    async with session_factory() as session:
        await session.execute(
            text("UPDATE land.reservations SET status = 'COMPLETED' WHERE id = :id"),
            {"id": r["id"]},
        )
        await session.commit()

    again = await reserve(client, r["plotSeasonId"], headers=OTHER_H, status=409)

    assert again["error"]["code"] == "PLOT_SEASON_ALREADY_RESERVED"
