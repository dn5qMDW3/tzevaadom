"""Constants for the Tzeva Adom integration."""

from __future__ import annotations

DOMAIN = "tzevaadom"

# Oref API endpoints
OREF_BASE_URL = "https://www.oref.org.il"
OREF_ALERTS_URL = f"{OREF_BASE_URL}/WarningMessages/alert/alerts.json"
OREF_HISTORY_URL = f"{OREF_BASE_URL}/WarningMessages/alert/History/AlertsHistory.json"
OREF_DISTRICTS_URL = f"{OREF_BASE_URL}/districts/districts_heb.json"

# Required headers for Oref API
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}

# Config keys
CONF_AREAS = "areas"
CONF_CITIES = "cities"
CONF_CATEGORIES = "categories"
CONF_POLL_INTERVAL = "poll_interval"
CONF_WEEKLY_RESET_DAY = "weekly_reset_day"
CONF_ENABLE_NATIONWIDE = "enable_nationwide"
CONF_PROXY_URL = "proxy_url"

# Defaults
DEFAULT_POLL_INTERVAL = 2  # seconds
DEFAULT_WEEKLY_RESET_DAY = 6  # Sunday (0=Monday in Python, 6=Sunday)
DEFAULT_ENABLE_NATIONWIDE = True

# Alert categories
ALERT_CATEGORIES: dict[int, dict[str, str]] = {
    1: {
        "he": "ירי רקטות וטילים",
        "en": "Rockets and Missiles",
        "icon": "mdi:rocket-launch",
    },
    2: {
        "he": "חדירת כלי טיס עוין",
        "en": "Hostile Aircraft Intrusion",
        "icon": "mdi:airplane-alert",
    },
    3: {
        "he": "רעידת אדמה",
        "en": "Earthquake",
        "icon": "mdi:earth-box",
    },
    4: {
        "he": "צונאמי",
        "en": "Tsunami",
        "icon": "mdi:waves",
    },
    5: {
        "he": "חומרים מסוכנים",
        "en": "Hazardous Materials",
        "icon": "mdi:hazard-lights",
    },
    6: {
        "he": "חדירת מחבלים",
        "en": "Terrorist Infiltration",
        "icon": "mdi:account-alert",
    },
    7: {
        "he": "אירוע רדיולוגי",
        "en": "Radiological Event",
        "icon": "mdi:radioactive",
    },
    8: {
        "he": "תרגיל ירי רקטות וטילים",
        "en": "Drill - Rockets and Missiles",
        "icon": "mdi:rocket-launch-outline",
    },
    9: {
        "he": "תרגיל חדירת כלי טיס עוין",
        "en": "Drill - Hostile Aircraft",
        "icon": "mdi:airplane-clock",
    },
    10: {
        "he": "תרגיל רעידת אדמה",
        "en": "Drill - Earthquake",
        "icon": "mdi:earth-box-minus",
    },
    11: {
        "he": "תרגיל צונאמי",
        "en": "Drill - Tsunami",
        "icon": "mdi:waves-arrow-up",
    },
    12: {
        "he": "תרגיל חומרים מסוכנים",
        "en": "Drill - Hazardous Materials",
        "icon": "mdi:hazard-lights",
    },
    13: {
        "he": "תרגיל חדירת מחבלים",
        "en": "Drill - Terrorist Infiltration",
        "icon": "mdi:account-alert-outline",
    },
    14: {
        "he": "הודעה מיוחדת",
        "en": "Special Announcement",
        "icon": "mdi:alert-circle",
    },
}

# Platforms
PLATFORMS = ["binary_sensor", "sensor"]
