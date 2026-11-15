"""Factory that gives every service the same FastAPI setup."""

from fastapi import FastAPI

from farm_common.settings import ServiceSettings


def create_app(service_name: str, version: str, settings: ServiceSettings | None = None) -> FastAPI:
    """Create a FastAPI app with the routes and behaviour shared by all services.

    Middleware for auth, correlation IDs and the error format is added here by issue #4.
    """
    settings = settings or ServiceSettings()
    app = FastAPI(
        title=f"{service_name} service",
        version=version,
        root_path=settings.root_path,
    )

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": service_name, "version": version}

    return app
