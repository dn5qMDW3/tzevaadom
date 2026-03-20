"""Binary sensor platform for Tzeva Adom."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

    enable_nationwide = config_entry.options.get(
        CONF_ENABLE_NATIONWIDE,
        config_entry.data.get(CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE),
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

    @property
    def is_on(self) -> bool | None:
        """Return true if alert is active."""
        if self.coordinator.data is None:
            return None
        if self._filtered:
            return self.coordinator.data.is_active
        return self.coordinator.data.is_active_all

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return additional alert details."""
        if self.coordinator.data is None:
            return {}

        alerts = (
            self.coordinator.data.active_alerts
            if self._filtered
            else self.coordinator.data.all_alerts
        )

        if not alerts:
            return {
                "alert_count": 0,
                "cities": [],
            }

        alert = alerts[0]
        category_info = ALERT_CATEGORIES.get(alert.cat, {})

        return {
            "alert_id": alert.id,
            "category": alert.cat,
            "category_name_he": category_info.get("he", ""),
            "category_name_en": category_info.get("en", ""),
            "title": alert.title,
            "description": alert.desc,
            "cities": alert.data,
            "alert_count": len(alerts),
        }

    @property
    def icon(self) -> str:
        """Return icon based on alert category."""
        if self.coordinator.data is None or not (
            self.coordinator.data.active_alerts
            if self._filtered
            else self.coordinator.data.all_alerts
        ):
            return "mdi:shield-check"

        alerts = (
            self.coordinator.data.active_alerts
            if self._filtered
            else self.coordinator.data.all_alerts
        )
        cat = alerts[0].cat
        return ALERT_CATEGORIES.get(cat, {}).get("icon", "mdi:alert")


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
    def extra_state_attributes(self) -> dict[str, any]:
        """Return early warning details."""
        if self.coordinator.data is None:
            return {}

        warnings = self.coordinator.data.early_warnings
        if not warnings:
            return {
                "alert_count": 0,
                "cities": [],
            }

        # Collect all cities from all early warnings
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

    def _get_category_alerts(self) -> list:
        """Return active alerts matching this category."""
        if self.coordinator.data is None:
            return []
        return [a for a in self.coordinator.data.active_alerts if a.cat == self._cat_id]

    @property
    def is_on(self) -> bool | None:
        """Return true if alert of this category is active."""
        if self.coordinator.data is None:
            return None
        return len(self._get_category_alerts()) > 0

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return category alert details."""
        alerts = self._get_category_alerts()
        if not alerts:
            return {
                "alert_count": 0,
                "cities": [],
                "category_id": self._cat_id,
                "category_name_he": self._category_info.get("he", ""),
                "category_name_en": self._category_info.get("en", ""),
            }

        all_cities = []
        for alert in alerts:
            all_cities.extend(alert.data)

        return {
            "alert_count": len(alerts),
            "cities": all_cities,
            "category_id": self._cat_id,
            "category_name_he": self._category_info.get("he", ""),
            "category_name_en": self._category_info.get("en", ""),
            "title": alerts[0].title,
            "description": alerts[0].desc,
        }

    @property
    def icon(self) -> str:
        """Return icon for this category."""
        return self._category_info.get("icon", "mdi:alert")
