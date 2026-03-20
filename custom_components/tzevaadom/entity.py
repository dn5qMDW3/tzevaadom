"""Base entity for Tzeva Adom."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OrefDataUpdateCoordinator


class TzevaadomEntity(CoordinatorEntity[OrefDataUpdateCoordinator]):
    """Base entity for Tzeva Adom integration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OrefDataUpdateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="Tzeva Adom",
            manufacturer="Pikud HaOref",
            entry_type=DeviceEntryType.SERVICE,
        )
