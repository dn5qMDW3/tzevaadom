"""Binary sensor platform for Tzeva Adom."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ALERT_CATEGORIES,
    CONF_ENABLE_NATIONWIDE,
    DEFAULT_ENABLE_NATIONWIDE,
    DOMAIN,
    ENABLED_BY_DEFAULT_CATEGORIES,
)
from .coordinator import OrefDataUpdateCoordinator
from .entity import TzevaadomEntity
from .helpers import get_entry_option


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tzeva Adom binary sensors."""
    coordinator: OrefDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]

    entities: list[BinarySensorEntity] = [
        TzevaadomAlertBinarySensor(coordinator, filtered=True),
        TzevaadomEarlyWarningBinarySensor(coordinator),
    ]

    enable_nationwide = get_entry_option(
        config_entry, CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE
    )
    if enable_nationwide:
        entities.append(TzevaadomAlertBinarySensor(coordinator, filtered=False))

    # Per-category binary sensors (cat 1 & 2 enabled by default, rest disabled)
    for cat_id in ALERT_CATEGORIES:
        entities.append(
            TzevaadomCategoryBinarySensor(
                coordinator,
                cat_id,
                enabled_default=cat_id in ENABLED_BY_DEFAULT_CATEGORIES,
            )
        )

    async_add_entities(entities)


class TzevaadomAlertBinarySensor(TzevaadomEntity, BinarySensorEntity):
    """Binary sensor for active Oref alerts."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(
        self,
        coordinator: OrefDataUpdateCoordinator,
        filtered: bool,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._filtered = filtered
        suffix = "alert" if filtered else "alert_all"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_translation_key = suffix

    def _get_alerts(self) -> list:
        """Return the relevant alerts list."""
        if self.coordinator.data is None:
            return []
        return (
            self.coordinator.data.active_alerts
            if self._filtered
            else self.coordinator.data.all_alerts
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if alert is active."""
        if self.coordinator.data is None:
            return None
        if self._filtered:
            return self.coordinator.data.is_active
        return self.coordinator.data.is_active_all

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional alert details."""
        alerts = self._get_alerts()
        if not alerts:
            return {"alert_count": 0, "cities": [], "cities_count": 0}

        attrs = alerts[0].to_state_attributes()
        all_cities = []
        for a in alerts:
            all_cities.extend(a.data)
        attrs["alert_count"] = len(alerts)
        attrs["cities_count"] = len(all_cities)

        # For nationwide sensor, include total active cities count
        if not self._filtered and self.coordinator.data:
            attrs["active_cities_count"] = self.coordinator.data.active_cities_count

        return attrs

    @property
    def icon(self) -> str:
        """Return icon based on alert category."""
        alerts = self._get_alerts()
        if not alerts:
            return "mdi:shield-check"
        return alerts[0].category_icon


class TzevaadomEarlyWarningBinarySensor(TzevaadomEntity, BinarySensorEntity):
    """Binary sensor for early warning alerts."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(
        self,
        coordinator: OrefDataUpdateCoordinator,
    ) -> None:
        """Initialize the early warning binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_early_warning"
        self._attr_translation_key = "early_warning"

    @property
    def is_on(self) -> bool | None:
        """Return true if early warning is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.is_early_warning_active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return early warning details."""
        if self.coordinator.data is None:
            return {}

        warnings = self.coordinator.data.early_warnings
        if not warnings:
            return {"alert_count": 0, "cities": []}

        all_cities = []
        for w in warnings:
            all_cities.extend(w.data)

        return {
            "alert_count": len(warnings),
            "cities": all_cities,
            "title": warnings[0].title,
            "description": warnings[0].desc,
        }

    @property
    def icon(self) -> str:
        """Return icon based on early warning state."""
        if self.coordinator.data and self.coordinator.data.is_early_warning_active:
            return "mdi:alert-octagon"
        return "mdi:alert-octagon-outline"


class TzevaadomCategoryBinarySensor(TzevaadomEntity, BinarySensorEntity):
    """Binary sensor for a specific alert category."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(
        self,
        coordinator: OrefDataUpdateCoordinator,
        cat_id: int,
        enabled_default: bool,
    ) -> None:
        """Initialize the category binary sensor."""
        super().__init__(coordinator)
        self._cat_id = cat_id
        self._category_info = ALERT_CATEGORIES.get(cat_id, {})
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_alert_cat_{cat_id}"
        self._attr_translation_key = f"alert_cat_{cat_id}"
        self._attr_entity_registry_enabled_default = enabled_default
        self._cached_alerts: list = []

    @callback
    def _handle_coordinator_update(self) -> None:
        """Cache category alerts on coordinator update."""
        if self.coordinator.data is not None:
            self._cached_alerts = [
                a for a in self.coordinator.data.active_alerts
                if a.cat == self._cat_id
            ]
        else:
            self._cached_alerts = []
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if alert of this category is active."""
        if self.coordinator.data is None:
            return None
        return len(self._cached_alerts) > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return category alert details."""
        base: dict[str, Any] = {
            "alert_count": len(self._cached_alerts),
            "category_id": self._cat_id,
            "category_name_he": self._category_info.get("he", ""),
            "category_name_en": self._category_info.get("en", ""),
            "is_drill": self._cat_id >= 100,
        }
        if not self._cached_alerts:
            base["cities"] = []
            base["cities_count"] = 0
            return base

        all_cities = []
        for alert in self._cached_alerts:
            all_cities.extend(alert.data)
        base["cities"] = all_cities
        base["cities_count"] = len(all_cities)
        base["title"] = self._cached_alerts[0].title
        base["description"] = self._cached_alerts[0].desc
        if self._cached_alerts[0].shelter_time is not None:
            base["shelter_time"] = self._cached_alerts[0].shelter_time
        return base

    @property
    def icon(self) -> str:
        """Return icon for this category."""
        return self._category_info.get("icon", "mdi:alert")
