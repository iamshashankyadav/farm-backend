from farm_common.app import create_app
from quality_service import __version__
from quality_service.events_runtime import lifespan
from quality_service.routes import router
from quality_service.settings import get_quality_settings

app = create_app(
    service_name="quality",
    version=__version__,
    settings=get_quality_settings(),
    lifespan=lifespan,
)
app.include_router(router)
