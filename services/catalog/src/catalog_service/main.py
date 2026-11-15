from catalog_service import __version__
from farm_common.app import create_app

app = create_app(service_name="catalog", version=__version__)
