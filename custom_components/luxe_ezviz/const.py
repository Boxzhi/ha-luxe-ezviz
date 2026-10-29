"""Shared constants for Luxe EZVIZ."""

DOMAIN = "luxe_ezviz"
API_BASE = "https://open.ys7.com"
TOKEN_URL = f"{API_BASE}/api/lapp/token/get"
DEVICE_INFO_URL = f"{API_BASE}/api/lapp/device/info"
CHANNEL_LIST_URL = f"{API_BASE}/api/lapp/device/camera/list"
PTZ_CAPACITY_URL = f"{API_BASE}/api/lapp/device/capacity"
PTZ_START_URL = f"{API_BASE}/api/lapp/device/ptz/start"
PTZ_STOP_URL = f"{API_BASE}/api/lapp/device/ptz/stop"

CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"
CONF_DEVICE_SERIAL = "device_serial"
CONF_VERIFY_CODE = "verify_code"
CONF_CHANNEL = "channel"
CONF_IMAGE_UPLOAD = "product_image"
CONF_IMAGE_REMOVE = "remove_product_image"

DEFAULT_CHANNEL = 1
TOKEN_EARLY_REFRESH_MS = 24 * 60 * 60 * 1000
REFRESH_INTERVAL_HOURS = 6
DEVICE_INFO_CACHE_SECONDS = 60

# These are never included in log messages or diagnostics.
SECRET_FIELDS = frozenset({CONF_APP_SECRET, CONF_VERIFY_CODE, "accessToken"})
