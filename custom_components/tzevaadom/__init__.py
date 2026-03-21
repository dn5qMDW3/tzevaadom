"""Tzeva Adom - Home Assistant integration for Oref alerts."""

from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
import shutil

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import AlertApiClient, OrefApiClient, TzofarApiClient
from .const import (
    CONF_DATA_SOURCE,
    CONF_PROXY_URL,
    DATA_SOURCE_OREF,
    DATA_SOURCE_OREF_PROXY,
    DATA_SOURCE_TZOFAR,
    DOMAIN,
)
from .coordinator import OrefDataUpdateCoordinator
from .definitions import DefinitionsManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS_LIST: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


def create_api_client(
    session: ClientSession,
    data_source: str,
    proxy_url: str | None = None,
) -> AlertApiClient:
    """Create the appropriate API client based on data source.

    Shared factory used by both __init__ and config_flow.
    """
    if data_source == DATA_SOURCE_TZOFAR:
        return TzofarApiClient(session)
    return OrefApiClient(session, proxy_url)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry from older versions."""
    if config_entry.version < 2:
        _LOGGER.info(
            "Migrating config entry %s from version %d to 2",
            config_entry.entry_id,
            config_entry.version,
        )
        new_data = {**config_entry.data}
        # Determine data source from existing config
        if new_data.get(CONF_PROXY_URL):
            new_data[CONF_DATA_SOURCE] = DATA_SOURCE_OREF_PROXY
        else:
            new_data[CONF_DATA_SOURCE] = DATA_SOURCE_OREF

        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=2
        )
        _LOGGER.info(
            "Migration complete: data_source=%s", new_data[CONF_DATA_SOURCE]
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tzeva Adom from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client based on configured data source
    session = async_get_clientsession(hass)
    data_source = entry.data.get(CONF_DATA_SOURCE, DATA_SOURCE_OREF)
    proxy_url = entry.data.get(CONF_PROXY_URL) or None
    client = create_api_client(session, data_source, proxy_url)

    # Create definitions manager and load stored data
    definitions_manager = DefinitionsManager(hass)
    await definitions_manager.async_load()

    # Create coordinator (needs definitions_manager for shelter time lookups)
    coordinator = OrefDataUpdateCoordinator(hass, client, entry, definitions_manager)

    # Store references
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
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

    # Install bundled automation blueprints
    await hass.async_add_executor_job(_install_blueprints, hass)

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
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _install_blueprints(hass: HomeAssistant) -> None:
    """Copy bundled blueprints into HA's blueprints directory.

    Only copies if the source is newer or the destination doesn't exist,
    so user customizations to existing blueprints are not overwritten
    unless the integration ships an update.
    """
    source_dir = Path(__file__).parent / "blueprints" / "automation"
    if not source_dir.is_dir():
        return

    dest_dir = Path(hass.config.path("blueprints")) / "automation" / DOMAIN
    dest_dir.mkdir(parents=True, exist_ok=True)

    for src_file in source_dir.glob("*.yaml"):
        dst_file = dest_dir / src_file.name
        # Only copy if new or updated
        if not dst_file.exists() or src_file.stat().st_mtime > dst_file.stat().st_mtime:
            shutil.copy2(src_file, dst_file)
            _LOGGER.info("Installed blueprint: %s", src_file.name)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    if hass.services.has_service(DOMAIN, "force_refresh"):
        return

    async def handle_force_refresh(call: ServiceCall) -> None:
        """Force an immediate data refresh."""
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if isinstance(entry_data, dict) and "coordinator" in entry_data:
                await entry_data["coordinator"].async_request_refresh()
        _LOGGER.debug("Forced data refresh")

    hass.services.async_register(DOMAIN, "force_refresh", handle_force_refresh)
