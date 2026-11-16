"""Connect quality event consumers and transactional outbox publisher."""
import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from farm_common.events import RabbitEventBus
from farm_common.outbox import run_relay
from quality_service.consumers import make_handler
from quality_service.database import get_session_factory
from quality_service.db import OutboxEvent
from quality_service.settings import get_quality_settings


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_quality_settings()
    if not settings.events_enabled:
        yield
        return
    session_factory = get_session_factory()
    bus = RabbitEventBus(settings.rabbitmq_url, service_name="quality")
    await bus.connect()
    await bus.subscribe(["order.packed", "harvest.ready"], make_handler(session_factory))
    relay = asyncio.create_task(run_relay(session_factory, OutboxEvent, bus))
    try:
        yield
    finally:
        relay.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay
        await bus.close()
