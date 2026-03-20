"""Data update coordinator for Tzeva Adom."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OrefApiClient, OrefApiError
from .const import (
    CONF_AREAS,
    CONF_CATEGORIES,
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
        client: OrefApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self._selected_areas: set[str] = set(
            config_entry.options.get(CONF_AREAS, config_entry.data.get(CONF_AREAS, []))
        )
        self._selected_categories: set[int] = {
            int(c)
            for c in config_entry.options.get(
                CONF_CATEGORIES, config_entry.data.get(CONF_CATEGORIES, [])
            )
        }
        self._seen_alert_ids: set[str] = set()
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
        categories: list[int] | None = None,
    ) -> None:
        """Update area and category filters."""
        if areas is not None:
            self._selected_areas = set(areas)
        if categories is not None:
            self._selected_categories = set(categories)

    def _filter_alert(self, alert: OrefAlert) -> bool:
        """Check if an alert matches the configured filters."""
        # If no categories selected, accept all
        if self._selected_categories and alert.cat not in self._selected_categories:
            return False
        # If no areas selected, accept all
        if self._selected_areas and not any(
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

        # Parse all alerts
        all_alerts = [OrefAlert.from_dict(a) for a in raw_alerts]

        # Apply filters
        filtered_alerts = [a for a in all_alerts if self._filter_alert(a)]

        # Detect new alerts (not seen before)
        current_ids = {a.id for a in filtered_alerts}
        new_alert_ids = current_ids - self._seen_alert_ids
        new_alerts = [a for a in filtered_alerts if a.id in new_alert_ids]

        # Fire events for new alerts
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
        else:
            # No active alerts - clear seen IDs so next batch is detected as new
            self._seen_alert_ids.clear()

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
        )

        self._last_data = data
        return data
