"""Constants for the Tzeva Adom integration."""

from __future__ import annotations

DOMAIN = "tzevaadom"

# --- Data source configuration ---
CONF_DATA_SOURCE = "data_source"
DATA_SOURCE_OREF = "oref"
DATA_SOURCE_TZOFAR = "tzofar"
DATA_SOURCE_OREF_PROXY = "oref_proxy"

# --- Oref API endpoints ---
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

# --- Tzofar API endpoints (tzevaadom.co.il) ---
TZOFAR_API_BASE = "https://api.tzevaadom.co.il"
TZOFAR_ALERTS_URL = f"{TZOFAR_API_BASE}/notifications"
TZOFAR_HISTORY_URL = f"{TZOFAR_API_BASE}/alerts-history/"
TZOFAR_VERSIONS_URL = f"{TZOFAR_API_BASE}/lists-versions"
TZOFAR_CITIES_URL = "https://www.tzevaadom.co.il/static/cities.json"
TZOFAR_FEED_URL = f"{TZOFAR_API_BASE}/ios/feed"

# Tzofar instruction types (from /ios/feed → instructions[].instructionType)
TZOFAR_INSTRUCTION_EARLY_WARNING = 0
TZOFAR_INSTRUCTION_END_EVENT = 1

# Tzofar threat ID → Oref category ID mapping
# Based on THREATS_TITLES in tzevaadom.co.il/tzofar-site/static/js/app.js
TZOFAR_THREAT_TO_OREF_CAT: dict[int, int] = {
    0: 1,   # צבע אדום (Red Alert) → Rockets and Missiles
    1: 5,   # חומרים מסוכנים → Hazardous Materials
    2: 6,   # חדירת מחבלים → Terrorist Infiltration
    3: 3,   # רעידת אדמה → Earthquake
    4: 4,   # צונאמי → Tsunami
    5: 2,   # חדירת כלי טיס עוין → Hostile Aircraft Intrusion
    6: 7,   # אירוע רדיולוגי → Radiological Event
    7: 14,  # ירי בלתי קונבנציונלי (Non-conventional Missile) → Special Announcement
             # NOTE: High severity in Tzofar (priority #2), but Oref has no dedicated category
    8: 14,  # התרעה (General Alert) → Special Announcement
    9: 8,   # תרגיל פיקוד העורף (Home Front Drill) → Drill - Rockets
             # Tzofar's DRILLS_THREAT_ID; visually rendered as threat 0 (rockets drill)
}
# When isDrill=True, shift base categories 1-6 to their drill equivalents 8-13
TZOFAR_DRILL_CAT_OFFSET = 7

# Tzofar area ID → Hebrew district name
# Source: https://www.tzevaadom.co.il/static/cities.json → areas
TZOFAR_AREA_NAMES: dict[int, str] = {
    1: "גליל עליון",       # Upper Galilee
    2: "דרום הנגב",         # Southern Negev
    3: "שפלת יהודה",        # Judean Foothills
    4: "גליל תחתון",        # Lower Galilee
    5: "מנשה",              # Menashe
    6: "קו העימות",         # Confrontation Line
    7: "לכיש",              # Lachish
    9: "שרון",              # Sharon
    10: "דרום הגולן",       # Southern Golan
    11: "שומרון",           # Samaria
    12: "ים המלח",          # Dead Sea
    13: "עוטף עזה",         # Gaza Envelope
    14: "יהודה",            # Judea
    15: "ואדי ערה",         # Wadi Ara
    16: "מרכז הגליל",       # Central Galilee
    17: "מערב הנגב",        # Western Negev
    18: "דן",               # Dan (Tel Aviv, Ramat Gan, Bnei Brak, etc.)
    19: "המפרץ",            # The Bay (Haifa Bay area)
    20: "ירקון",            # Yarkon
    21: "מערב לכיש",        # Western Lachish
    22: "הכרמל",            # Carmel
    23: "השפלה",            # Lowlands
    24: "מרכז הנגב",        # Central Negev
    25: "בקעת בית שאן",     # Beit She'an Valley
    26: "אילת",             # Eilat
    27: "ערבה",             # Arava
    28: "צפון הגולן",       # Northern Golan
    29: "בקעה",             # Jordan Valley
    32: "ירושלים",          # Jerusalem
    34: "העמקים",           # Valleys
}

# Config keys
CONF_AREAS = "areas"
CONF_CITIES = "cities"
CONF_CATEGORIES = "categories"
CONF_POLL_INTERVAL = "poll_interval"
CONF_WEEKLY_RESET_DAY = "weekly_reset_day"
CONF_ENABLE_NATIONWIDE = "enable_nationwide"
CONF_PROXY_URL = "proxy_url"

# Alert retention: keep alerts active until explicit "Event Ended" (all-clear).
# Safety timeout in case we miss the event-ended notification.
ALERT_RETENTION_TIMEOUT = 30 * 60  # 30 minutes

# Defaults
DEFAULT_POLL_INTERVAL = 2  # seconds
DEFAULT_POLL_INTERVAL_TZOFAR = 3  # seconds (matches Tzofar's backup poll rate)
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

# Oref informational alert categories (not real alerts - should not be counted)
# cat=13 with title "האירוע הסתיים" = "Event Ended" notification
OREF_CAT_EVENT_ENDED = 13
OREF_TITLE_EVENT_ENDED = "האירוע הסתיים"

# Early Warning titles - tracked separately as their own binary sensor
# "התרעה מקדימה" = classic early warning title
# "בדקות הקרובות צפויות להתקבל התרעות באזורך" = newer "alerts expected soon" title
OREF_TITLE_EARLY_WARNING = "התרעה מקדימה"
OREF_TITLE_EARLY_WARNING_ALT = "בדקות הקרובות צפויות להתקבל התרעות באזורך"
EARLY_WARNING_TITLES: set[str] = {
    OREF_TITLE_EARLY_WARNING,
    OREF_TITLE_EARLY_WARNING_ALT,
}

# Informational alert titles to exclude from real alert counting
# Note: Early Warning is NOT here — it's tracked as a separate sensor
INFORMATIONAL_TITLES: set[str] = {
    "האירוע הסתיים",  # Event Ended
}

# Per-category binary sensors: only these are enabled by default
ENABLED_BY_DEFAULT_CATEGORIES: set[int] = {1, 2}  # Rockets, Hostile Aircraft

# Event names for Home Assistant bus
EVENT_TZEVAADOM_ALERT = f"{DOMAIN}_alert"
EVENT_TZEVAADOM_EARLY_WARNING = f"{DOMAIN}_early_warning"
