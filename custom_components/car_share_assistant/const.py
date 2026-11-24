"""Constants for Car share assistant."""

from homeassistant.const import Platform

DOMAIN = "car_share_assistant"
PLATFORMS = [Platform.CALENDAR, Platform.SENSOR, Platform.BINARY_SENSOR]
CONF_KEY_ID = "key_id"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 5
