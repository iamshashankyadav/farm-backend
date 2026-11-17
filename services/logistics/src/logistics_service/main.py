from farm_common.app import create_app
from logistics_service import __version__, routes
from logistics_service.events_runtime import lifespan
from logistics_service.settings import get_logistics_settings

app = create_app(
    service_name="logistics",
    version=__version__,
    settings=get_logistics_settings(),
    lifespan=lifespan,
)

app.include_router(routes.router)
