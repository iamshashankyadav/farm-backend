from uuid import uuid4

from catalog_service.consumers import make_handler
from farm_common.events import Event, InMemoryEventBus


async def test_order_cancelled_releases_stock_once(api, session_factory):
    listing = await api.listing(qtyAvailable=10)
    order_id = uuid4()
    await api.reserve(order_id, (listing["id"], 4))
    handle = make_handler(session_factory)
    event = Event(type="order.cancelled", producer="order", payload={"orderId": str(order_id)})

    await handle(event)
    await handle(event)  # redelivered: ignored

    assert (await api.get(listing["id"]))["qtyAvailable"] == 10


async def test_quality_graded_sets_listing_grade(api, session_factory, outbox):
    a = await api.listing()
    b = await api.listing()
    handle = make_handler(session_factory)

    await handle(
        Event(
            type="quality.graded",
            producer="quality",
            payload={"subjectType": "LISTING", "subjectId": a["id"], "grade": "B"},
        )
    )
    await handle(
        Event(
            type="quality.graded",
            producer="quality",
            payload={
                "subjectType": "ORDER",
                "subjectId": str(uuid4()),
                "grade": "A",
                "listingIds": [b["id"]],
            },
        )
    )

    assert (await api.get(a["id"]))["grade"] == "B"
    assert (await api.get(b["id"]))["grade"] == "A"
    graded = [e.payload for e in await outbox("listing.updated")]
    assert {(p["listingId"], p["grade"]) for p in graded} == {(a["id"], "B"), (b["id"], "A")}


async def test_failed_grade_leaves_listing_alone(api, session_factory):
    listing = await api.listing()
    handle = make_handler(session_factory)

    await handle(
        Event(
            type="quality.graded",
            producer="quality",
            payload={"subjectType": "LISTING", "subjectId": listing["id"], "grade": "FAIL"},
        )
    )
    assert (await api.get(listing["id"]))["grade"] is None


async def test_handler_works_on_the_bus(api, session_factory):
    listing = await api.listing(qtyAvailable=5)
    order_id = uuid4()
    await api.reserve(order_id, (listing["id"], 5))
    bus = InMemoryEventBus()
    await bus.subscribe(["order.cancelled", "quality.graded"], make_handler(session_factory))

    await bus.publish(
        Event(type="order.cancelled", producer="order", payload={"orderId": str(order_id)})
    )

    assert (await api.get(listing["id"]))["qtyAvailable"] == 5


async def test_order_rated_builds_the_farm_average(api, session_factory, client):
    listing = await api.listing()
    handle = make_handler(session_factory)
    assert listing["farmRating"] is None and listing["farmRatingCount"] == 0

    for score in (5, 4, 4):
        await handle(
            Event(
                type="order.rated",
                producer="order",
                payload={"farmId": listing["farmId"], "score": score, "orderId": str(uuid4())},
            )
        )
    repeated = Event(
        type="order.rated",
        producer="order",
        payload={"farmId": listing["farmId"], "score": 1, "orderId": str(uuid4())},
    )
    await handle(repeated)
    await handle(repeated)  # redelivered: counted once

    after = await api.get(listing["id"])
    assert after["farmRatingCount"] == 4
    assert after["farmRating"] == 3.5  # (5 + 4 + 4 + 1) / 4
    farm = (await client.get(f"/farms/{listing['farmId']}")).json()
    assert farm["rating"] == 3.5 and farm["ratingCount"] == 4


async def test_unusable_rating_events_are_ignored(api, session_factory):
    listing = await api.listing()
    handle = make_handler(session_factory)
    for payload in (
        {"farmId": listing["farmId"], "score": 9},
        {"farmId": listing["farmId"], "score": "5"},
        {"score": 5},
    ):
        await handle(Event(type="order.rated", producer="order", payload=payload))

    assert (await api.get(listing["id"]))["farmRating"] is None
