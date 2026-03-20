"""Tzeva Adom - Home Assistant integration for Oref alerts."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import OrefApiClient
from .const import (
    CONF_PROXY_URL,
    CONF_WEEKLY_RESET_DAY,
    DEFAULT_WEEKLY_RESET_DAY,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import OrefDataUpdateCoordinator
from .counters import AlertCounterManager
from .definitions import DefinitionsManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS_LIST: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tzeva Adom from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client
    session = async_get_clientsession(hass)
    proxy_url = entry.data.get(CONF_PROXY_URL) or None
    client = OrefApiClient(session, proxy_url)

    # Create coordinator
    coordinator = OrefDataUpdateCoordinator(hass, client, entry)

    # Create counter manager
    weekly_reset_day = entry.options.get(
        CONF_WEEKLY_RESET_DAY,
        entry.data.get(CONF_WEEKLY_RESET_DAY, DEFAULT_WEEKLY_RESET_DAY),
    )
    counter_manager = AlertCounterManager(hass, entry.entry_id, int(weekly_reset_day))
    await counter_manager.async_load()

    # Create definitions manager and schedule updates
    definitions_manager = DefinitionsManager(hass)
    await definitions_manager.async_load()

    # Store references
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "counter_manager": counter_manager,
        "definitions_manager": definitions_manager,
        "client": client,
    }

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_LIST)

    # Schedule periodic definitions update (every 24h)
    async def _update_definitions(_now=None) -> None:
        await definitions_manager.async_update(client)

    entry.async_on_unload(
        async_track_time_interval(hass, _update_definitions, timedelta(hours=24))
    )

    # Schedule periodic counter rollover check (every 60s)
    async def _check_rollovers(_now=None) -> None:
        counter_manager._check_rollovers()
        await counter_manager.async_save()

    entry.async_on_unload(
        async_track_time_interval(hass, _check_rollovers, timedelta(seconds=60))
    )

    # Register services
    _register_services(hass)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Trigger initial definitions update in background
    entry.async_create_background_task(
        hass, _update_definitions(), "tzevaadom_initial_definitions_update"
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS_LIST)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        # Save counters before unloading
        await entry_data["counter_manager"].async_save()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    if hass.services.has_service(DOMAIN, "reset_counters"):
        return

    async def handle_reset_counters(call: ServiceCall) -> None:
        """Reset all alert counters."""
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if isinstance(entry_data, dict) and "counter_manager" in entry_data:
                entry_data["counter_manager"].reset_all()
                await entry_data["counter_manager"].async_save()
        _LOGGER.info("All alert counters have been reset")

    async def handle_force_refresh(call: ServiceCall) -> None:
        """Force an immediate data refresh."""
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if isinstance(entry_data, dict) and "coordinator" in entry_data:
                await entry_data["coordinator"].async_request_refresh()
        _LOGGER.debug("Forced data refresh")

    hass.services.async_register(DOMAIN, "reset_counters", handle_reset_counters)
    hass.services.async_register(DOMAIN, "force_refresh", handle_force_refresh)
