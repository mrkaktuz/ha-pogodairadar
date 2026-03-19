"""Constants for PogodaiRadar integration."""

DOMAIN = "pogodairadar"

CONF_SLUG = "slug"
CONF_SCAN_INTERVAL = "scan_interval"

SCAN_15_MIN = "15"
SCAN_30_MIN = "30"
SCAN_1_HOUR = "60"
SCAN_2_HOURS = "120"

SCAN_INTERVAL_OPTIONS = {
    SCAN_15_MIN: 15 * 60,
    SCAN_30_MIN: 30 * 60,
    SCAN_1_HOUR: 60 * 60,
    SCAN_2_HOURS: 2 * 60 * 60,
}

DEFAULT_SCAN = SCAN_30_MIN

BASE_URL = "https://www.pogodairadar.com.ua/storinka-pohody"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)
