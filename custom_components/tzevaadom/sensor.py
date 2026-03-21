"""Sensor platform for Tzeva Adom."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE, DOMAIN
from .coordinator import OrefDataUpdateCoordinator
from .entity import TzevaadomEntity
from .helpers import get_entry_option


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


class TzevaadomLastAlertSensor(TzevaadomEntity, SensorEntity):
    """Sensor showing details of the last alert."""

    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: OrefDataUpdateCoordinator) -> None:
        """Initialize the last alert sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_last_alert"
        )
        self._attr_translation_key = "last_alert"

    @property
    def native_value(self) -> str | None:
        """Return the category title of the last alert."""
        if self.coordinator.data is None or self.coordinator.data.last_alert is None:
            return None
        return self.coordinator.data.last_alert.category_name_he or self.coordinator.data.last_alert.title

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return last alert details."""
        if self.coordinator.data is None or self.coordinator.data.last_alert is None:
            return {}
        return self.coordinator.data.last_alert.to_state_attributes()


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

        return {
            "category_id": alert.cat,
            "category_name_he": alert.category_name_he,
            "category_name_en": alert.category_name_en,
            "active_categories": active_cats,
        }


class TzevaadomAlertsHistorySensor(TzevaadomEntity, SensorEntity):
    """Sensor exposing recent alerts history from the API.

    State: number of alerts in history.
    Attributes: list of recent alerts with timestamps, categories, and cities.
    Users can build template sensors/automations from this data.
    """

    _attr_icon = "mdi:history"

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
        self._history: list[dict[str, Any]] = []

    @callback
    def _handle_coordinator_update(self) -> None:
        """Accumulate alerts into history on each coordinator update."""
        if self.coordinator.data is None:
            self.async_write_ha_state()
            return

        new_alerts = (
            self.coordinator.data.new_alerts_all
            if self._nationwide
            else self.coordinator.data.new_alerts
        )

        if new_alerts:
            for alert in new_alerts:
                self._history.append(alert.to_state_attributes())

            # Cap history to last 100 entries
            if len(self._history) > 100:
                self._history = self._history[-100:]

        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return count of alerts in history."""
        return len(self._history)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full alerts history list."""
        return {
            "alerts": self._history,
            "count": len(self._history),
        }
