from farm_common.app import create_app
from identity_service import __version__

app = create_app(service_name="identity", version=__version__)
