from farm_common.app import create_app
from notification_service import __version__

app = create_app(service_name="notification", version=__version__)
