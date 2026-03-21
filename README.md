# Tzeva Adom - Home Assistant Integration

[![HACS Validation](https://github.com/dn5qMDW3/tzevaadom/actions/workflows/hacs-validate.yml/badge.svg)](https://github.com/dn5qMDW3/tzevaadom/actions/workflows/hacs-validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/dn5qMDW3/tzevaadom?style=flat-square)](https://github.com/dn5qMDW3/tzevaadom/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz)

[עברית](README.he.md)

A native Home Assistant custom integration for Israel's civil defense alert system. Provides real-time rocket alerts, early warnings, hostile aircraft intrusions, earthquake warnings, and other civil defense alerts.

## Data Sources

| Source | Coverage | Notes |
|--------|----------|-------|
| **Tzofar** (tzevaadom.co.il) | Worldwide | No extra setup required. Recommended for users outside Israel. |
| **Oref Direct** (oref.org.il) | Israel only | Direct connection to Pikud HaOref API. |
| **Oref via Proxy** | Worldwide | Uses your own proxy server for Oref API access. |

## Features

- **Real-time alerts** — Polls every 2-3 seconds (configurable)
- **Early Warning sensor** — Separate binary sensor for early warning alerts (`התרעה מקדימה`)
- **Event Ended detection** — Alert sensor resets immediately when Oref publishes "Event Ended"
- **Area filtering** — Monitor specific districts or cities
- **Category filtering** — Choose which alert types to track (rockets, drones, earthquakes, etc.)
- **Per-category sensors** — Individual binary sensors for each alert category
- **Alert history** — Sensor with up to 24 hours of alert history from the API
- **Nationwide sensor** — Optional sensors for all alerts across Israel (unfiltered)
- **Event-driven** — Fires `tzevaadom_alert`, `tzevaadom_early_warning`, and `tzevaadom_all_clear` events for automations
- **Bundled blueprints** — Ready-to-use automation blueprints for notifications, lights, and TTS
- **Auto-updating definitions** — Area/district/city lists update automatically
- **Bilingual** — Full Hebrew and English UI support
- **Diagnostics** — Built-in diagnostics for easy troubleshooting
- **HACS compatible** — Easy installation via HACS

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu > **Custom repositories**
3. Add `https://github.com/dn5qMDW3/tzevaadom` with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/tzevaadom` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **Tzeva Adom**
3. Follow the setup wizard:
   - **Data Source** — Choose between Tzofar (worldwide), Oref Direct (Israel), or Oref via Proxy
   - **Location Filter** — Select districts and/or specific cities (leave empty for nationwide)
   - **Categories** — Select alert types to monitor (leave empty for all)
   - **Settings** — Configure poll interval and nationwide sensor

## Entities

### Binary Sensors

| Entity | Description |
|--------|-------------|
| `binary_sensor.tzeva_adom_alert` | ON when an alert matches your area/category filters |
| `binary_sensor.tzeva_adom_alert_all` | ON when any alert is active nationwide (optional) |
| `binary_sensor.tzeva_adom_early_warning` | ON when an early warning is active for your areas |
| `binary_sensor.tzeva_adom_alert_cat_1` | ON for rockets and missiles alerts |
| `binary_sensor.tzeva_adom_alert_cat_6` | ON for hostile aircraft intrusion alerts |
| `binary_sensor.tzeva_adom_alert_cat_*` | Per-category sensors for all other alert types (disabled by default) |

**Alert attributes**: `alert_id`, `category`, `category_name_he`, `category_name_en`, `title`, `description`, `cities`, `cities_count`, `alert_count`, `is_drill`, `priority`, `shelter_time`

**Early warning attributes**: `alert_count`, `cities`, `title`, `description`

### Sensors

| Entity | Description |
|--------|-------------|
| `sensor.tzeva_adom_last_alert` | Details of the most recent alert |
| `sensor.tzeva_adom_alert_type` | Category of the currently active alert (filtered) |
| `sensor.tzeva_adom_alert_type_nationwide` | Category of the currently active alert (nationwide, optional) |
| `sensor.tzeva_adom_alerts_history` | Recent alerts history with timestamps (filtered) |
| `sensor.tzeva_adom_alerts_history_nationwide` | Recent alerts history (nationwide, optional) |

**Last alert attributes**: `alert_id`, `category`, `category_name_he`, `category_name_en`, `title`, `description`, `cities`, `is_drill`, `priority`, `shelter_time`, `time_in_shelter_seconds`

**Alert type attributes**: `category_id`, `category_name_he`, `category_name_en`, `is_drill`, `priority`, `active_categories`, `cities_count`, `shelter_time`

**Alerts history**: State is the number of alerts. History entries are in the `entries` attribute with timestamps, categories, and cities.

## Blueprints

The integration includes ready-to-use automation blueprints, automatically available under **Settings** > **Automations** > **Blueprints**:

| Blueprint | Description |
|-----------|-------------|
| **Mobile Notification** | Sends a mobile notification with alert details, cities, and shelter time. Supports iOS critical notifications. |
| **Flash Lights on Alert** | Flashes lights during an alert with color by category (red=rockets, orange=aircraft, yellow=earthquake). Restores previous state when alert clears. |
| **TTS Alert Announcement** | Announces alert details via text-to-speech on a media player. |

## Services

| Service | Description |
|---------|-------------|
| `tzevaadom.force_refresh` | Force an immediate data refresh |

## Events

### `tzevaadom_alert`

Fired for each new alert matching your filters:

```yaml
event_type: tzevaadom_alert
data:
  id: "133456789"
  cat: 1
  title: "ירי רקטות וטילים"
  desc: "היכנסו למרחב המוגן..."
  cities:
    - "תל אביב - מרכז העיר"
    - "חולון"
  is_drill: false
  category_name_he: "ירי רקטות וטילים"
  category_name_en: "Rockets and Missiles"
  priority: 120
  shelter_time: 15
```

### `tzevaadom_all_clear`

Fired when cities are cleared from alert (event ended / all clear):

```yaml
event_type: tzevaadom_all_clear
data:
  cities:
    - "תל אביב - מרכז העיר"
    - "חולון"
  cities_count: 2
```

### `tzevaadom_early_warning`

Fired when early warning alerts are detected for your areas:

```yaml
event_type: tzevaadom_early_warning
data:
  id: "133456790"
  cat: 1
  title: "התרעה מקדימה"
  desc: "..."
  cities:
    - "אשדוד"
  is_drill: false
  category_name_he: "ירי רקטות וטילים"
  category_name_en: "Rockets and Missiles"
  priority: 120
```

## Automation Examples

### Alert Notification

```yaml
automation:
  - alias: "Red Alert Notification"
    trigger:
      - platform: event
        event_type: tzevaadom_alert
    action:
      - service: notify.mobile_app
        data:
          title: "{{ trigger.event.data.title }}"
          message: "Areas: {{ trigger.event.data.cities | join(', ') }}"
```

### Early Warning — Prepare Shelter

```yaml
automation:
  - alias: "Early Warning - Prepare"
    trigger:
      - platform: event
        event_type: tzevaadom_early_warning
    action:
      - service: notify.mobile_app
        data:
          title: "Early Warning"
          message: "Prepare shelter: {{ trigger.event.data.cities | join(', ') }}"
```

### Flash Lights on Alert

```yaml
automation:
  - alias: "Flash lights on alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.tzeva_adom_alert
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.living_room
        data:
          color_name: red
          brightness: 255
```

## Alert Categories

| ID | Hebrew | English |
|----|--------|---------|
| 1 | ירי רקטות וטילים | Rockets and Missiles |
| 2 | ירי לא קונבנציונלי | Non-conventional Missiles |
| 3 | רעידת אדמה | Earthquake |
| 4 | אירוע רדיולוגי | Radiological Event |
| 5 | צונאמי | Tsunami |
| 6 | חדירת כלי טיס עוין | Hostile Aircraft Intrusion |
| 7 | חומרים מסוכנים | Hazardous Materials |
| 8 | אזהרה | Warning |
| 13 | חדירת מחבלים | Terrorist Infiltration |
| 101+ | תרגילים | Drills (real category ID + 100) |

## Reducing Database Size

The history sensors store up to 500 alert entries in their attributes. If your Home Assistant database is growing too large, you can exclude these sensors from the recorder:

```yaml
# configuration.yaml
recorder:
  exclude:
    entity_globs:
      - sensor.tzeva_adom_alerts_history*
```

## Multiple Instances

You can add the integration multiple times with different area/category filters to create separate monitoring groups (e.g., home vs. office).

## Diagnostics

For troubleshooting, go to **Settings** > **Devices & Services** > **Tzeva Adom** > **3 dots menu** > **Download diagnostics**. Sensitive data (proxy URLs) is automatically redacted.

## License

MIT
