"""Sensor platform for Tzeva Adom."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import ALERT_CATEGORIES, DOMAIN
from .coordinator import OrefDataUpdateCoordinator
from .counters import AlertCounterManager
from .entity import TzevaadomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tzeva Adom sensors."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: OrefDataUpdateCoordinator = entry_data["coordinator"]
    counter_manager: AlertCounterManager = entry_data["counter_manager"]

    async_add_entities(
        [
            TzevaadomCounterSensor(coordinator, counter_manager, "daily"),
            TzevaadomCounterSensor(coordinator, counter_manager, "weekly"),
            TzevaadomCounterSensor(coordinator, counter_manager, "monthly"),
            TzevaadomCounterSensor(coordinator, counter_manager, "yearly"),
            TzevaadomLastAlertSensor(coordinator),
        ]
    )


class TzevaadomCounterSensor(TzevaadomEntity, RestoreEntity, SensorEntity):
    """Sensor for alert counters (daily/weekly/monthly/yearly)."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: OrefDataUpdateCoordinator,
        counter_manager: AlertCounterManager,
        period: str,
    ) -> None:
        """Initialize the counter sensor."""
        super().__init__(coordinator)
        self._counter_manager = counter_manager
        self._period = period
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{period}_count"
        )
        self._attr_translation_key = f"{period}_alert_count"

    @property
    def native_value(self) -> int:
        """Return the counter value."""
        return getattr(self._counter_manager, f"{self._period}_count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return counter metadata."""
        return {
            "period": self._period,
        }

    async def async_added_to_hass(self) -> None:
        """Restore state on startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            # Counter manager is the source of truth; RestoreEntity is fallback
            try:
                restored = int(last_state.state)
                current = getattr(self._counter_manager, f"{self._period}_count", 0)
                if current == 0 and restored > 0:
                    setattr(self._counter_manager, f"{self._period}_count", restored)
            except (ValueError, TypeError):
                pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data and self.coordinator.data.new_alerts:
            for alert in self.coordinator.data.new_alerts:
                self._counter_manager.record_alert(alert.id)
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
        alert = self.coordinator.data.last_alert
        category_info = ALERT_CATEGORIES.get(alert.cat, {})
        return category_info.get("he", alert.title)

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return last alert details."""
        if self.coordinator.data is None or self.coordinator.data.last_alert is None:
            return {}

        alert = self.coordinator.data.last_alert
        category_info = ALERT_CATEGORIES.get(alert.cat, {})

        return {
            "alert_id": alert.id,
            "category": alert.cat,
            "category_name_he": category_info.get("he", ""),
            "category_name_en": category_info.get("en", ""),
            "title": alert.title,
            "description": alert.desc,
            "cities": alert.data,
        }
