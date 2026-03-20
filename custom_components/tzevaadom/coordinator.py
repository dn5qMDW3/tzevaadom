"""Data update coordinator for Tzeva Adom."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AlertApiClient, OrefApiError
from .const import (
    CONF_AREAS,
    CONF_CATEGORIES,
    CONF_CITIES,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .models import OrefAlert, OrefAlertData

_LOGGER = logging.getLogger(__name__)


class OrefDataUpdateCoordinator(DataUpdateCoordinator[OrefAlertData]):
    """Coordinator to poll Oref alerts and apply filters."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: AlertApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self._selected_areas: set[str] = set(
            config_entry.options.get(CONF_AREAS, config_entry.data.get(CONF_AREAS, []))
        )
        self._selected_cities: set[str] = set(
            config_entry.options.get(CONF_CITIES, config_entry.data.get(CONF_CITIES, []))
        )
        self._selected_categories: set[int] = {
            int(c)
            for c in config_entry.options.get(
                CONF_CATEGORIES, config_entry.data.get(CONF_CATEGORIES, [])
            )
        }
        self._seen_alert_ids: set[str] = set()
        self._seen_alert_ids_all: set[str] = set()
        self._last_data: OrefAlertData = OrefAlertData()

        poll_interval = config_entry.options.get(
            CONF_POLL_INTERVAL,
            config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
            config_entry=config_entry,
        )

    def update_filters(
        self,
        areas: list[str] | None = None,
        cities: list[str] | None = None,
        categories: list[int] | None = None,
    ) -> None:
        """Update area, city, and category filters."""
        if areas is not None:
            self._selected_areas = set(areas)
        if cities is not None:
            self._selected_cities = set(cities)
        if categories is not None:
            self._selected_categories = set(categories)

    def _filter_alert(self, alert: OrefAlert) -> bool:
        """Check if an alert matches the configured filters."""
        # If no categories selected, accept all
        if self._selected_categories and alert.cat not in self._selected_categories:
            return False

        # City filter takes precedence: if specific cities are selected,
        # match only those cities (most granular)
        if self._selected_cities:
            if not any(city in self._selected_cities for city in alert.data):
                return False
        # Otherwise fall back to area/district-level filtering
        elif self._selected_areas and not any(
            area in self._selected_areas for area in alert.data
        ):
            return False

        return True

    async def _async_update_data(self) -> OrefAlertData:
        """Fetch and process alert data."""
        try:
            raw_alerts = await self.client.get_alerts()
        except OrefApiError as err:
            raise UpdateFailed(f"Error fetching alerts: {err}") from err

        # Parse all alerts and separate real alerts from informational ones
        all_alerts_raw = [OrefAlert.from_dict(a) for a in raw_alerts]
        # Keep informational alerts for display but track them separately
        all_alerts = [a for a in all_alerts_raw if a.is_real_alert]

        # Apply filters
        filtered_alerts = [a for a in all_alerts if self._filter_alert(a)]

        # Detect new filtered alerts (not seen before)
        current_ids = {a.id for a in filtered_alerts}
        new_alert_ids = current_ids - self._seen_alert_ids
        new_alerts = [a for a in filtered_alerts if a.id in new_alert_ids]

        # Detect new nationwide alerts (for nationwide counter)
        current_ids_all = {a.id for a in all_alerts}
        new_alert_ids_all = current_ids_all - self._seen_alert_ids_all
        new_alerts_all = [a for a in all_alerts if a.id in new_alert_ids_all]

        # Fire events for new filtered alerts
        for alert in new_alerts:
            self.hass.bus.async_fire(
                f"{DOMAIN}_alert",
                {
                    "id": alert.id,
                    "cat": alert.cat,
                    "title": alert.title,
                    "desc": alert.desc,
                    "cities": alert.data,
                },
            )

        # Update seen IDs - keep only current + recent to avoid unbounded growth
        if all_alerts:
            self._seen_alert_ids = current_ids
            self._seen_alert_ids_all = current_ids_all
        else:
            # No active alerts - clear seen IDs so next batch is detected as new
            self._seen_alert_ids.clear()
            self._seen_alert_ids_all.clear()

        # Determine last alert
        last_alert = self._last_data.last_alert
        if filtered_alerts:
            last_alert = filtered_alerts[0]

        data = OrefAlertData(
            active_alerts=filtered_alerts,
            all_alerts=all_alerts,
            is_active=len(filtered_alerts) > 0,
            is_active_all=len(all_alerts) > 0,
            last_alert=last_alert,
            new_alerts=new_alerts,
            new_alerts_all=new_alerts_all,
        )

        self._last_data = data
        return data
