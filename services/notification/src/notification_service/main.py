from __future__ import annotations

from typing import Any

from farm_common.app import create_app
from notification_service import __version__
from notification_service.events_runtime import lifespan
from notification_service.routes import router
from notification_service.settings import get_notification_settings

app = create_app(
    service_name="notification",
    version=__version__,
    settings=get_notification_settings(),
    lifespan=lifespan,
)
app.include_router(router)

# Normalize ValidationError schema across FastAPI/Pydantic versions to match committed contracts
_original_openapi = app.openapi


def _openapi() -> dict[str, Any]:
    schema = _original_openapi()
    schemas = schema.get("components", {}).get("schemas", {})
    if "ValidationError" in schemas:
        props = schemas["ValidationError"].get("properties", {})
        if "ctx" not in props:
            props["ctx"] = {"title": "Context", "type": "object"}
        if "input" not in props:
            props["input"] = {"title": "Input"}
    return schema


app.openapi = _openapi  # type: ignore[method-assign]
