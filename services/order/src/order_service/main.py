from farm_common.app import create_app
from order_service import __version__

app = create_app(service_name="order", version=__version__)
