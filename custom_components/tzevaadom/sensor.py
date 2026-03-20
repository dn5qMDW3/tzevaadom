"""Sensor platform for Tzeva Adom."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE, DOMAIN
from .coordinator import OrefDataUpdateCoordinator
from .counters import AlertCounterManager
from .entity import TzevaadomEntity
from .helpers import get_entry_option

COUNTER_PERIODS = ("daily", "weekly", "monthly", "yearly")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tzeva Adom sensors."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: OrefDataUpdateCoordinator = entry_data["coordinator"]
    counter_manager: AlertCounterManager = entry_data["counter_manager"]

    entities: list[SensorEntity] = [
        TzevaadomCounterSensor(coordinator, counter_manager, period, nationwide=False)
        for period in COUNTER_PERIODS
    ]
    entities.append(TzevaadomLastAlertSensor(coordinator))
    entities.append(TzevaadomAlertTypeSensor(coordinator))

    # Add nationwide counters if enabled
    enable_nationwide = get_entry_option(
        config_entry, CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE
    )
    if enable_nationwide:
        entities.extend(
            TzevaadomCounterSensor(
                coordinator, counter_manager, period, nationwide=True
            )
            for period in COUNTER_PERIODS
        )

    async_add_entities(entities)


class TzevaadomCounterSensor(TzevaadomEntity, RestoreEntity, SensorEntity):
    """Sensor for alert counters (daily/weekly/monthly/yearly), filtered or nationwide."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: OrefDataUpdateCoordinator,
        counter_manager: AlertCounterManager,
        period: str,
        *,
        nationwide: bool = False,
    ) -> None:
        """Initialize the counter sensor."""
        super().__init__(coordinator)
        self._counter_manager = counter_manager
        self._period = period
        self._nationwide = nationwide

        suffix = f"{period}_count_nationwide" if nationwide else f"{period}_count"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_translation_key = (
            f"{period}_alert_count_nationwide" if nationwide else f"{period}_alert_count"
        )

    @property
    def _counter_attr(self) -> str:
        """Return the counter manager attribute name for this sensor."""
        return (
            f"{self._period}_count_nationwide"
            if self._nationwide
            else f"{self._period}_count"
        )

    @property
    def native_value(self) -> int:
        """Return the counter value."""
        return getattr(self._counter_manager, self._counter_attr, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return counter metadata."""
        attrs: dict[str, Any] = {"period": self._period}
        if self._nationwide:
            attrs["scope"] = "nationwide"
        return attrs

    async def async_added_to_hass(self) -> None:
        """Restore state on startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                restored = int(last_state.state)
                current = getattr(self._counter_manager, self._counter_attr, 0)
                if current == 0 and restored > 0:
                    setattr(self._counter_manager, self._counter_attr, restored)
            except (ValueError, TypeError):
                pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            new_alerts = (
                self.coordinator.data.new_alerts_all
                if self._nationwide
                else self.coordinator.data.new_alerts
            )
            if new_alerts:
                record = (
                    self._counter_manager.record_alert_nationwide
                    if self._nationwide
                    else self._counter_manager.record_alert
                )
                for alert in new_alerts:
                    record(alert.id)
                self.hass.async_create_task(self._counter_manager.async_save())
        self.async_write_ha_state()


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

    def __init__(self, coordinator: OrefDataUpdateCoordinator) -> None:
        """Initialize the alert type sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_alert_type"
        )
        self._attr_translation_key = "alert_type"

    def _get_primary_alert(self):
        """Return the first active alert, or None."""
        if self.coordinator.data and self.coordinator.data.active_alerts:
            return self.coordinator.data.active_alerts[0]
        return None

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

        active_cats = sorted({a.cat for a in self.coordinator.data.active_alerts})

        return {
            "category_id": alert.cat,
            "category_name_he": alert.category_name_he,
            "category_name_en": alert.category_name_en,
            "active_categories": active_cats,
        }
