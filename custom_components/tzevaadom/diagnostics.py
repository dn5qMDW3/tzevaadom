"""Diagnostics support for Tzeva Adom."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_PROXY_URL, DOMAIN

TO_REDACT = {CONF_PROXY_URL, CONF_URL, "proxy_url"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")
    counter_manager = entry_data.get("counter_manager")
    definitions_manager = entry_data.get("definitions_manager")

    # Coordinator state
    coordinator_diag: dict[str, Any] = {}
    if coordinator and coordinator.data:
        data = coordinator.data
        coordinator_diag = {
            "is_active": data.is_active,
            "is_active_all": data.is_active_all,
            "is_early_warning_active": data.is_early_warning_active,
            "active_alerts_count": len(data.active_alerts),
            "all_alerts_count": len(data.all_alerts),
            "early_warnings_count": len(data.early_warnings),
            "event_ended_cities": data.event_ended_cities,
            "last_alert_id": data.last_alert.id if data.last_alert else None,
        }

    # Counter state
    counter_diag: dict[str, Any] = {}
    if counter_manager:
        counter_diag = {
            "daily_count": counter_manager.daily_count,
            "weekly_count": counter_manager.weekly_count,
            "monthly_count": counter_manager.monthly_count,
            "yearly_count": counter_manager.yearly_count,
            "daily_count_nationwide": counter_manager.daily_count_nationwide,
            "weekly_count_nationwide": counter_manager.weekly_count_nationwide,
            "monthly_count_nationwide": counter_manager.monthly_count_nationwide,
            "yearly_count_nationwide": counter_manager.yearly_count_nationwide,
        }

    # Definitions state
    definitions_diag: dict[str, Any] = {}
    if definitions_manager:
        definitions_diag = {
            "districts_count": len(definitions_manager.districts)
            if hasattr(definitions_manager, "districts")
            else 0,
            "cities_count": len(definitions_manager.cities)
            if hasattr(definitions_manager, "cities")
            else 0,
        }

    return {
        "config_entry": async_redact_data(
            {
                "data": dict(entry.data),
                "options": dict(entry.options),
                "version": entry.version,
            },
            TO_REDACT,
        ),
        "coordinator": coordinator_diag,
        "counters": counter_diag,
        "definitions": definitions_diag,
    }
