"""Sensor platform for Tzeva Adom."""

from __future__ import annotations

from datetime import datetime
import logging
import time
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE, DOMAIN
from .coordinator import OrefDataUpdateCoordinator
from .entity import TzevaadomEntity
from .helpers import get_entry_option
from .models import OrefAlert, OrefAlertData

_LOGGER = logging.getLogger(__name__)

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# How often to refresh history from the API (seconds)
HISTORY_REFRESH_INTERVAL = 5 * 60  # 5 minutes

# Group alerts within this window into one incident (seconds)
INCIDENT_GROUP_WINDOW = 120  # 2 minutes

# Max entries stored in state attributes to stay under HA's 16KB recorder limit
MAX_HISTORY_ATTR_ALERTS = 30
MAX_HISTORY_ATTR_INCIDENTS = 20


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tzeva Adom sensors."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: OrefDataUpdateCoordinator = entry_data["coordinator"]

    entities: list[SensorEntity] = [
        TzevaadomLastAlertSensor(coordinator),
        TzevaadomAlertTypeSensor(coordinator, nationwide=False),
        TzevaadomAlertsHistorySensor(coordinator, nationwide=False),
    ]

    # Add nationwide sensors if enabled
    enable_nationwide = get_entry_option(
        config_entry, CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE
    )
    if enable_nationwide:
        entities.append(TzevaadomAlertTypeSensor(coordinator, nationwide=True))
        entities.append(TzevaadomAlertsHistorySensor(coordinator, nationwide=True))

    async_add_entities(entities)


class TzevaadomLastAlertSensor(TzevaadomEntity, RestoreEntity, SensorEntity):
    """Sensor showing details of the last alert.

    Implements RestoreEntity so that the last alert state survives HA restarts.
    """

    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: OrefDataUpdateCoordinator) -> None:
        """Initialize the last alert sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_last_alert"
        )
        self._attr_translation_key = "last_alert"
        self._restored_value: str | None = None
        self._restored_attrs: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Restore last alert state on startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            self._restored_value = last_state.state
            self._restored_attrs = dict(last_state.attributes)

    @property
    def native_value(self) -> str | None:
        """Return the category title of the last alert."""
        if self.coordinator.data is None or self.coordinator.data.last_alert is None:
            return self._restored_value
        return (
            self.coordinator.data.last_alert.category_name_he
            or self.coordinator.data.last_alert.title
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return last alert details including time since alert."""
        if self.coordinator.data is None or self.coordinator.data.last_alert is None:
            # Return restored attributes if available (after HA restart)
            return self._restored_attrs
        attrs = self.coordinator.data.last_alert.to_state_attributes()
        # Add time_since from retention tracking (if alert is retained)
        if self.coordinator.data.time_in_shelter_seconds is not None:
            attrs["time_in_shelter_seconds"] = (
                self.coordinator.data.time_in_shelter_seconds
            )
        return attrs


class TzevaadomAlertTypeSensor(TzevaadomEntity, SensorEntity):
    """Sensor showing the type/category of the currently active alert."""

    def __init__(
        self,
        coordinator: OrefDataUpdateCoordinator,
        *,
        nationwide: bool = False,
    ) -> None:
        """Initialize the alert type sensor."""
        super().__init__(coordinator)
        self._nationwide = nationwide
        suffix = "alert_type_nationwide" if nationwide else "alert_type"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_translation_key = suffix

    def _get_alerts(self) -> list:
        """Return the relevant alerts list."""
        if self.coordinator.data is None:
            return []
        return (
            self.coordinator.data.all_alerts
            if self._nationwide
            else self.coordinator.data.active_alerts
        )

    def _get_primary_alert(self):
        """Return the first active alert, or None."""
        alerts = self._get_alerts()
        return alerts[0] if alerts else None

    @property
    def native_value(self) -> str | None:
        """Return the category name of the active alert."""
        alert = self._get_primary_alert()
        if alert is None:
            return None
        return alert.category_name_en or alert.title

    @property
    def icon(self) -> str:
        """Return icon based on active alert category."""
        alert = self._get_primary_alert()
        if alert is not None:
            return alert.category_icon
        return "mdi:alert-circle-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return alert type details."""
        alert = self._get_primary_alert()
        if alert is None:
            return {}

        alerts = self._get_alerts()
        active_cats = sorted({a.cat for a in alerts})
        all_cities = OrefAlertData.collect_cities(alerts)

        attrs: dict[str, Any] = {
            "category_id": alert.cat,
            "category_name_he": alert.category_name_he,
            "category_name_en": alert.category_name_en,
            "is_drill": alert.is_drill,
            "priority": alert.priority,
            "active_categories": active_cats,
            "cities_count": len(all_cities),
        }
        if alert.shelter_time is not None:
            attrs["shelter_time"] = alert.shelter_time
        return attrs


class TzevaadomAlertsHistorySensor(TzevaadomEntity, RestoreEntity, SensorEntity):
    """Sensor exposing recent alerts history from the API.

    Fetches from the API history endpoint (last ~24h of alerts) every 5 minutes.
    Supplements with live alerts seen between refreshes.

    State: number of alerts in history.
    Attributes: list of recent alerts with timestamps, categories, and cities.
    Users can build template sensors/automations from this data.
    """

    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OrefDataUpdateCoordinator,
        *,
        nationwide: bool = False,
    ) -> None:
        """Initialize the alerts history sensor."""
        super().__init__(coordinator)
        self._nationwide = nationwide
        suffix = "alerts_history_nationwide" if nationwide else "alerts_history"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_translation_key = suffix
        self._api_history: list[dict[str, Any]] = []
        self._last_fetch: float = 0.0
        self._fetch_in_progress: bool = False

    async def async_added_to_hass(self) -> None:
        """Restore history state on startup so it's not empty until first API fetch."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            # Restore the alert count
            try:
                restored_count = int(last_state.state)
            except (ValueError, TypeError):
                restored_count = 0
            # Restore the history list from attributes
            restored_alerts = last_state.attributes.get("alerts")
            if isinstance(restored_alerts, list) and restored_alerts:
                self._api_history = restored_alerts
                _LOGGER.debug(
                    "Restored %d history entries (state=%d)",
                    len(self._api_history),
                    restored_count,
                )

    async def _refresh_history(self) -> None:
        """Fetch history from the API (throttled)."""
        now = time.monotonic()
        if now - self._last_fetch < HISTORY_REFRESH_INTERVAL:
            return
        if self._fetch_in_progress:
            return

        self._fetch_in_progress = True
        try:
            raw = await self.coordinator.client.get_history()
            if raw:
                self._api_history = self._process_history(raw)
                self._last_fetch = now
                _LOGGER.debug(
                    "Refreshed alerts history: %d entries", len(self._api_history)
                )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to fetch alerts history", exc_info=True)
        finally:
            self._fetch_in_progress = False

    def _process_history(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process normalized API history into a clean list of alert summaries.

        Both API clients normalize to: {id, cat, title, desc, data, timestamp}.
        For filtered variant (not nationwide), applies user's location/category
        filters to only show history relevant to their configured areas.
        """
        result: list[dict[str, Any]] = []
        for item in raw:
            alert = OrefAlert.from_dict(item)
            if not alert.is_real_alert:
                continue

            # For filtered variant, apply user's location/category filters
            # and narrow cities to only those matching the user's selection
            if not self._nationwide:
                if not self.coordinator.filter_alert(alert):
                    continue
                alert = self.coordinator.narrow_alert_to_filter(alert)

            ts = item.get("timestamp", 0)

            entry: dict[str, Any] = {
                "id": alert.id,
                "category_id": alert.cat,
                "category_he": alert.category_name_he or alert.title,
                "category_en": alert.category_name_en or alert.desc,
                "title": alert.title,
                "cities": alert.data,
                "cities_count": len(alert.data),
                "is_drill": alert.is_drill,
                "timestamp": ts,
            }

            # Include group_id if available (Tzofar)
            group_id = item.get("group_id")
            if group_id:
                entry["group_id"] = group_id

            if ts:
                try:
                    entry["datetime"] = datetime.fromtimestamp(
                        ts, tz=ISRAEL_TZ
                    ).isoformat()
                except (OSError, ValueError):
                    pass

            result.append(entry)

        return result

    def _group_into_incidents(
        self, alerts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Group flat alert list into incidents.

        Tzofar alerts are grouped by group_id.
        Oref alerts are grouped by time proximity (within INCIDENT_GROUP_WINDOW).
        """
        if not alerts:
            return []

        incidents: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        for entry in alerts:
            ts = entry.get("timestamp", 0)
            group_id = entry.get("group_id")

            # Determine if this belongs to the current incident
            belongs = False
            if current is not None:
                if group_id and current.get("group_id") == group_id:
                    belongs = True
                elif (
                    not group_id
                    and abs(ts - current["timestamp"]) <= INCIDENT_GROUP_WINDOW
                ):
                    belongs = True

            if belongs and current is not None:
                current["cities"].extend(entry.get("cities", []))
                current["cities_count"] = len(current["cities"])
                current["alerts_count"] += 1
                if entry["category_id"] not in current["categories"]:
                    current["categories"].append(entry["category_id"])
            else:
                # Start new incident
                current = {
                    "timestamp": ts,
                    "datetime": entry.get("datetime", ""),
                    "categories": [entry["category_id"]],
                    "category_he": entry.get("category_he", ""),
                    "category_en": entry.get("category_en", ""),
                    "cities": list(entry.get("cities", [])),
                    "cities_count": entry.get("cities_count", 0),
                    "alerts_count": 1,
                    "is_drill": entry.get("is_drill", False),
                }
                if group_id:
                    current["group_id"] = group_id
                incidents.append(current)

        return incidents

    @callback
    def _handle_coordinator_update(self) -> None:
        """Trigger history refresh on coordinator update."""
        # Schedule async history fetch (non-blocking, tracked for cleanup on unload)
        self.coordinator.config_entry.async_create_background_task(
            self.hass, self._refresh_history(), "tzevaadom_history_refresh"
        )
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return count of alerts in history."""
        return len(self._api_history)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return alerts history data.

        Attributes:
            alerts_today: count of individual alerts from today (Israel time)
            incidents_today: count of grouped incidents from today
            total: total alerts in history
            last_alert: most recent alert summary (or None)
            incidents: alerts grouped by incident (time proximity / group_id)
            alerts: full flat list of alert summaries (newest first)
        """
        # Calculate today's start in Israel time (not UTC!)
        now_israel = datetime.now(ISRAEL_TZ)
        today_start = now_israel.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_start_ts = int(today_start.timestamp())

        today_count = 0
        for entry in self._api_history:
            ts = entry.get("timestamp", 0)
            if ts >= today_start_ts:
                today_count += 1

        incidents = self._group_into_incidents(self._api_history)
        incidents_today = sum(
            1 for inc in incidents if inc.get("timestamp", 0) >= today_start_ts
        )

        return {
            "alerts_today": today_count,
            "incidents_today": incidents_today,
            "total": len(self._api_history),
            "last_alert": self._api_history[0] if self._api_history else None,
            "incidents": incidents[:MAX_HISTORY_ATTR_INCIDENTS],
            "incidents_total": len(incidents),
            "alerts": self._api_history[:MAX_HISTORY_ATTR_ALERTS],
        }
