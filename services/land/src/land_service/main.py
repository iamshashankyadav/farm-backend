from farm_common.app import create_app
from land_service import __version__

app = create_app(service_name="land", version=__version__)
