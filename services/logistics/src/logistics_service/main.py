from farm_common.app import create_app
from logistics_service import __version__

app = create_app(service_name="logistics", version=__version__)
