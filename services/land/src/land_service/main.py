from farm_common.app import create_app
from land_service import __version__
from land_service.events_runtime import lifespan
from land_service.internal import router as internal_router
from land_service.routes import router
from land_service.settings import get_land_settings

app = create_app(
    service_name="land",
    version=__version__,
    settings=get_land_settings(),
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(internal_router)
