# Tzeva Adom - Home Assistant Integration

A native Home Assistant custom integration for Israel's Oref (Pikud HaOref / פיקוד העורף) alert system. Provides real-time rocket alerts, hostile aircraft intrusions, earthquake warnings, and other civil defense alerts.

## Features

- **Real-time alerts** - Polls Oref API every 2 seconds (configurable)
- **Area filtering** - Monitor specific districts or cities
- **Category filtering** - Choose which alert types to track (rockets, drones, earthquakes, etc.)
- **Alert counters** - Daily, weekly, monthly, and yearly alert counts with persistence
- **Nationwide sensor** - Optional sensor for all alerts across Israel
- **Event-driven** - Fires `tzevaadom_alert` events for automations
- **Auto-updating definitions** - Area/district lists update automatically from Oref
- **Bilingual** - Hebrew and English UI support
- **HACS compatible** - Easy installation via HACS

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/dn5qMDW3/tzevaadom` with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/tzevaadom` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Tzeva Adom**
3. Follow the setup wizard:
   - **Connection**: Leave proxy URL empty for direct connection (Israel only)
   - **Areas**: Select districts to monitor (or leave empty for all)
   - **Categories**: Select alert types to monitor
   - **Settings**: Configure poll interval and counter options

## Entities

### Binary Sensors

| Entity | Description |
|--------|-------------|
| `binary_sensor.tzevaadom_alert` | ON when an alert matches your area/category filters |
| `binary_sensor.tzevaadom_alert_all` | ON when any alert is active nationwide |

**Attributes**: `alert_id`, `category`, `category_name_he`, `category_name_en`, `title`, `description`, `cities`, `alert_count`

### Sensors

| Entity | Description |
|--------|-------------|
| `sensor.tzevaadom_daily_alert_count` | Alert count today (resets at midnight) |
| `sensor.tzevaadom_weekly_alert_count` | Alert count this week (resets Sunday) |
| `sensor.tzevaadom_monthly_alert_count` | Alert count this month |
| `sensor.tzevaadom_yearly_alert_count` | Alert count this year |
| `sensor.tzevaadom_last_alert` | Details of the most recent alert |

## Services

| Service | Description |
|---------|-------------|
| `tzevaadom.reset_counters` | Reset all alert counters to zero |
| `tzevaadom.force_refresh` | Force an immediate data refresh |

## Events

The integration fires `tzevaadom_alert` events for each new alert:

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
```

### Automation Example

```yaml
automation:
  - alias: "Alert notification"
    trigger:
      - platform: event
        event_type: tzevaadom_alert
    action:
      - service: notify.mobile_app
        data:
          title: "{{ trigger.event.data.title }}"
          message: "Areas: {{ trigger.event.data.cities | join(', ') }}"
```

## Alert Categories

| ID | Hebrew | English |
|----|--------|---------|
| 1 | ירי רקטות וטילים | Rockets and Missiles |
| 2 | חדירת כלי טיס עוין | Hostile Aircraft Intrusion |
| 3 | רעידת אדמה | Earthquake |
| 4 | צונאמי | Tsunami |
| 5 | חומרים מסוכנים | Hazardous Materials |
| 6 | חדירת מחבלים | Terrorist Infiltration |
| 7 | אירוע רדיולוגי | Radiological Event |
| 8-13 | תרגילים | Drills (various types) |
| 14 | הודעה מיוחדת | Special Announcement |

## API Access

The Oref API is officially accessible only from within Israel. If you need access from outside Israel, you can configure a proxy URL in the integration settings.

## Multiple Instances

You can add the integration multiple times with different area/category filters to create separate monitoring groups.

## License

MIT
