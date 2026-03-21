"""Data update coordinator for Tzeva Adom."""

from __future__ import annotations

from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AlertApiClient, OrefApiError
from .const import (
    ALERT_RETENTION_TIMEOUT,
    CONF_AREAS,
    CONF_CATEGORIES,
    CONF_CITIES,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_TZEVAADOM_ALERT,
    EVENT_TZEVAADOM_EARLY_WARNING,
)
from .helpers import get_entry_option
from .models import OrefAlert, OrefAlertData

_LOGGER = logging.getLogger(__name__)


class OrefDataUpdateCoordinator(DataUpdateCoordinator[OrefAlertData]):
    """Coordinator to poll Oref alerts and apply filters.

    Alert retention policy:
        Alerts are retained as active until an explicit "Event Ended"
        (all-clear) notification is received for those cities, OR until
        a safety timeout expires. This matches real-world behavior where
        people must stay in shelter until the all-clear is given — not
        just until the alert disappears from the live API feed.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: AlertApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        # Note: _selected_areas contains city-level names resolved from districts
        # (resolved during config flow via definitions.get_areas_for_districts)
        self._selected_areas: set[str] = set(
            get_entry_option(config_entry, CONF_AREAS, [])
        )
        self._selected_cities: set[str] = set(
            get_entry_option(config_entry, CONF_CITIES, [])
        )
        self._selected_categories: set[int] = {
            int(c)
            for c in get_entry_option(config_entry, CONF_CATEGORIES, [])
        }

        # Seen IDs for deduplication (prevent re-firing events)
        self._seen_alert_ids: set[str] = set()
        self._seen_alert_ids_all: set[str] = set()
        self._seen_early_warning_ids: set[str] = set()

        # Alert retention: keep alerts active until explicit all-clear.
        # Maps city name → (alert, first_seen_timestamp)
        self._retained_cities: dict[str, tuple[OrefAlert, float]] = {}

        self._last_data: OrefAlertData = OrefAlertData()

        poll_interval = get_entry_option(
            config_entry, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
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

    def filter_alert(self, alert: OrefAlert) -> bool:
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
        # (areas are resolved to city names during config flow)
        elif self._selected_areas and not any(
            area in self._selected_areas for area in alert.data
        ):
            return False

        return True

    def _get_retained_alerts(self) -> list[OrefAlert]:
        """Build deduplicated alert list from retained cities.

        Groups retained cities back into their original alert objects,
        keeping only cities that are still retained (some may have been
        cleared by event-ended while others in the same alert are still active).
        """
        # Group retained cities by alert ID
        alert_cities: dict[str, tuple[OrefAlert, list[str]]] = {}
        for city, (alert, _ts) in self._retained_cities.items():
            if alert.id not in alert_cities:
                alert_cities[alert.id] = (alert, [])
            alert_cities[alert.id][1].append(city)

        # Rebuild alerts with only their still-retained cities
        result: list[OrefAlert] = []
        for alert_id, (alert, cities) in alert_cities.items():
            result.append(
                OrefAlert(
                    id=alert.id,
                    cat=alert.cat,
                    title=alert.title,
                    desc=alert.desc,
                    data=sorted(cities),
                )
            )
        return result

    async def _async_update_data(self) -> OrefAlertData:
        """Fetch and process alert data.

        Pipeline:
        1. Fetch alerts from API + early warnings (Tzofar) + event-ended (Tzofar)
        2. Classify into real alerts, early warnings, event-ended cities
        3. Update retained state: add new alerts, remove event-ended cities
        4. Auto-expire stale retained alerts (safety timeout)
        5. Build active alerts from retained state (NOT just current poll)
        6. Apply filters, detect new alerts, fire events
        """
        try:
            raw_alerts = await self.client.get_alerts()
        except OrefApiError as err:
            raise UpdateFailed(f"Error fetching alerts: {err}") from err

        # Fetch early warnings from source-specific endpoint (Tzofar only)
        try:
            ew_from_source = await self.client.get_early_warnings()
            if ew_from_source:
                raw_alerts.extend(ew_from_source)
                _LOGGER.debug(
                    "Merged %d early warnings from source", len(ew_from_source)
                )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Early warnings fetch failed, continuing without")

        # Fetch event-ended cities from source-specific endpoint (Tzofar only)
        # For Oref, event-ended comes through the regular alerts endpoint
        source_ended_cities: set[str] = set()
        try:
            source_ended_cities = await self.client.get_event_ended_cities()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Event-ended fetch failed, continuing without")

        # Parse all alerts and sort into 3 buckets
        all_alerts_raw = [OrefAlert.from_dict(a) for a in raw_alerts]

        new_real_alerts: list[OrefAlert] = []
        early_warnings: list[OrefAlert] = []
        event_ended_cities: set[str] = set(source_ended_cities)

        for alert in all_alerts_raw:
            if alert.is_event_ended:
                event_ended_cities.update(alert.data)
            elif alert.is_early_warning:
                early_warnings.append(alert)
            elif alert.is_real_alert:
                new_real_alerts.append(alert)

        _LOGGER.debug(
            "Parsed %d raw alerts: %d real, %d early warnings, %d event-ended cities",
            len(all_alerts_raw),
            len(new_real_alerts),
            len(early_warnings),
            len(event_ended_cities),
        )

        # --- Update retained alert state ---
        now = time.time()

        # 1. Add new real alerts to retention
        for alert in new_real_alerts:
            for city in alert.data:
                if city not in self._retained_cities:
                    self._retained_cities[city] = (alert, now)

        # 2. Remove event-ended cities from retention (the ALL CLEAR)
        if event_ended_cities:
            cleared = []
            for city in event_ended_cities:
                if city in self._retained_cities:
                    cleared.append(city)
                    del self._retained_cities[city]
            if cleared:
                _LOGGER.debug(
                    "Event-ended cleared %d cities from retention: %s",
                    len(cleared),
                    cleared[:10],
                )

        # 3. Auto-expire stale retained alerts (safety timeout)
        expired = [
            city for city, (_alert, ts) in self._retained_cities.items()
            if now - ts > ALERT_RETENTION_TIMEOUT
        ]
        for city in expired:
            del self._retained_cities[city]
        if expired:
            _LOGGER.debug(
                "Safety timeout expired %d retained cities: %s",
                len(expired),
                expired[:10],
            )

        # --- Build active alerts from retained state ---
        # This is the key difference: active_alerts comes from retention,
        # not just the current poll. Alerts stay active until all-clear.
        real_alerts = self._get_retained_alerts()

        # Apply location/category filters
        filtered_alerts = [a for a in real_alerts if self.filter_alert(a)]

        filtered_early_warnings = [
            a for a in early_warnings if self.filter_alert(a)
        ]

        if filtered_alerts:
            _LOGGER.debug(
                "Active alerts: %d filtered, %d nationwide, %d retained cities",
                len(filtered_alerts),
                len(real_alerts),
                len(self._retained_cities),
            )

        # Detect new filtered alerts (not seen before)
        current_ids = {a.id for a in filtered_alerts}
        new_alert_ids = current_ids - self._seen_alert_ids
        new_alerts = [a for a in filtered_alerts if a.id in new_alert_ids]

        # Detect new nationwide alerts
        current_ids_all = {a.id for a in real_alerts}
        new_alert_ids_all = current_ids_all - self._seen_alert_ids_all
        new_alerts_all = [a for a in real_alerts if a.id in new_alert_ids_all]

        # Detect new early warnings
        current_ew_ids = {a.id for a in filtered_early_warnings}
        new_ew_ids = current_ew_ids - self._seen_early_warning_ids
        new_early_warnings = [
            a for a in filtered_early_warnings if a.id in new_ew_ids
        ]

        # Fire events for new filtered alerts
        for alert in new_alerts:
            _LOGGER.info("New alert: cat=%d, cities=%s", alert.cat, alert.data)
            self.hass.bus.async_fire(EVENT_TZEVAADOM_ALERT, alert.to_event_data())

        # Fire events for new early warnings
        for alert in new_early_warnings:
            _LOGGER.info("New early warning: cities=%s", alert.data)
            self.hass.bus.async_fire(
                EVENT_TZEVAADOM_EARLY_WARNING, alert.to_event_data()
            )

        # Update seen IDs
        self._seen_alert_ids = current_ids
        self._seen_alert_ids_all = current_ids_all
        if filtered_early_warnings:
            self._seen_early_warning_ids = current_ew_ids
        else:
            self._seen_early_warning_ids.clear()

        # Determine last alert
        last_alert = self._last_data.last_alert
        if filtered_alerts:
            last_alert = filtered_alerts[0]

        data = OrefAlertData(
            active_alerts=filtered_alerts,
            all_alerts=real_alerts,
            last_alert=last_alert,
            new_alerts=new_alerts,
            new_alerts_all=new_alerts_all,
            early_warnings=filtered_early_warnings,
            new_early_warnings=new_early_warnings,
            event_ended_cities=sorted(event_ended_cities) if event_ended_cities else [],
        )

        self._last_data = data
        return data
