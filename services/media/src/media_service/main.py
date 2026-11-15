from farm_common.app import create_app
from media_service import __version__

app = create_app(service_name="media", version=__version__)
