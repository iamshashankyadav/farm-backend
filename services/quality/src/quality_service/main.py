from farm_common.app import create_app
from quality_service import __version__

app = create_app(service_name="quality", version=__version__)
