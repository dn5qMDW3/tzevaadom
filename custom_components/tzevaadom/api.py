"""API clients for alert data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

import time

from .const import (
    ALERT_CATEGORIES,
    OREF_ALERTS_URL,
    OREF_DISTRICTS_URL,
    OREF_HEADERS,
    OREF_HISTORY_URL,
    OREF_TITLE_EARLY_WARNING_ALT,
    TZOFAR_ALERTS_URL,
    TZOFAR_AREA_NAMES,
    TZOFAR_CITIES_URL,
    TZOFAR_DRILL_CAT_OFFSET,
    TZOFAR_FEED_URL,
    TZOFAR_HISTORY_URL,
    TZOFAR_INSTRUCTION_EARLY_WARNING,
    TZOFAR_INSTRUCTION_END_EVENT,
    TZOFAR_THREAT_TO_OREF_CAT,
    TZOFAR_VERSIONS_URL,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=10)


class OrefApiError(Exception):
    """Exception for alert API errors."""


class AlertApiClient(ABC):
    """Abstract base class for alert API clients."""

    @abstractmethod
    async def get_alerts(self) -> list[dict[str, Any]]:
        """Fetch current active alerts.

        Must return dicts compatible with OrefAlert.from_dict():
        {"id": str, "cat": int, "title": str, "desc": str, "data": list[str]}
        """

    @abstractmethod
    async def get_history(self) -> list[dict[str, Any]]:
        """Fetch alert history.

        Must return normalized dicts:
        {"id": str, "cat": int, "title": str, "desc": str,
         "data": list[str], "timestamp": int (unix epoch)}
        """

    @abstractmethod
    async def get_districts(self) -> list[dict[str, Any]]:
        """Fetch district/city definitions.

        Must return dicts compatible with DefinitionsManager._parse_districts():
        [{"label_he": str, "areaname": str, ...}]
        """

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the API is reachable."""

    async def get_early_warnings(self) -> list[dict[str, Any]]:
        """Fetch early warnings from the data source.

        Default: return empty list. Oref delivers early warnings through the
        regular alerts endpoint, so only Tzofar needs to override this.
        """
        return []

    async def get_event_ended_cities(self) -> set[str]:
        """Fetch cities with explicit "Event Ended" (all-clear) from the source.

        Default: return empty set. Oref delivers event-ended through the
        regular alerts endpoint. Only Tzofar needs to override this to
        fetch from the /ios/feed instructions (instructionType=1).
        """
        return set()


class OrefApiClient(AlertApiClient):
    """Client to interact with the Oref alert API."""

    def __init__(
        self,
        session: ClientSession,
        proxy_url: str | None = None,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._proxy_url = proxy_url

    def _build_url(self, default_url: str) -> str:
        """Build URL, replacing base with proxy if configured."""
        if self._proxy_url:
            from .const import OREF_BASE_URL

            return default_url.replace(OREF_BASE_URL, self._proxy_url.rstrip("/"))
        return default_url

    async def _fetch(self, url: str) -> str:
        """Fetch data from the API and return raw text."""
        try:
            async with self._session.get(
                self._build_url(url),
                headers=OREF_HEADERS,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()
                text = await response.text()
                # Remove UTF-8 BOM if present
                if text.startswith("\ufeff"):
                    text = text[1:]
                return text.strip()
        except ClientError as err:
            raise OrefApiError(f"Error fetching {url}: {err}") from err
        except TimeoutError as err:
            raise OrefApiError(f"Timeout fetching {url}") from err

    async def get_alerts(self) -> list[dict[str, Any]]:
        """Fetch current active alerts."""
        text = await self._fetch(OREF_ALERTS_URL)
        if not text or text == "null":
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse alerts response: %s", text[:200])
            return []
        # Response can be a single object or a list
        if isinstance(data, dict):
            return [data] if data else []
        if isinstance(data, list):
            return data
        return []

    async def get_history(self) -> list[dict[str, Any]]:
        """Fetch alert history, normalized to standard format.

        Oref history items have: matrix_id, category, category_desc,
        alertDate (ISO string), data (single city string).
        We normalize to: id, cat, title, desc, data (list), timestamp.
        """
        text = await self._fetch(OREF_HISTORY_URL)
        if not text or text == "null":
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse history response: %s", text[:200])
            return []
        if not isinstance(data, list):
            return []

        from datetime import datetime

        result: list[dict[str, Any]] = []
        for item in data:
            # Normalize category: matrix_id is what we use
            cat = int(item.get("matrix_id", item.get("cat", 0)))
            cat_info = ALERT_CATEGORIES.get(cat, {})

            # Normalize data: history uses single city string
            cities = item.get("data", "")
            if isinstance(cities, str):
                cities = [cities] if cities else []

            # Normalize timestamp from alertDate (ISO string)
            timestamp = 0
            alert_date = item.get("alertDate", "")
            if alert_date:
                try:
                    timestamp = int(datetime.fromisoformat(alert_date).timestamp())
                except (ValueError, TypeError):
                    pass

            result.append({
                "id": str(item.get("rid", item.get("id", timestamp))),
                "cat": cat,
                "title": item.get("category_desc", cat_info.get("he", "")),
                "desc": cat_info.get("en", ""),
                "data": cities,
                "timestamp": timestamp,
            })
        return result

    async def get_districts(self) -> list[dict[str, Any]]:
        """Fetch district/area definitions."""
        text = await self._fetch(OREF_DISTRICTS_URL)
        if not text or text == "null":
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse districts response: %s", text[:200])
            return []
        if isinstance(data, list):
            return data
        return []

    async def test_connection(self) -> bool:
        """Test if the API is reachable."""
        try:
            await self._fetch(OREF_ALERTS_URL)
            return True
        except OrefApiError:
            return False


class TzofarApiClient(AlertApiClient):
    """Client to interact with the Tzofar (tzevaadom.co.il) alert API.

    Works worldwide — no geo-restriction, no special headers needed.
    """

    def __init__(self, session: ClientSession) -> None:
        """Initialize the API client."""
        self._session = session
        self._city_id_map: dict[int, str] | None = None

    async def _fetch(self, url: str) -> str:
        """Fetch data from the API and return raw text."""
        try:
            async with self._session.get(
                url,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()
                return (await response.text()).strip()
        except ClientError as err:
            raise OrefApiError(f"Error fetching {url}: {err}") from err
        except TimeoutError as err:
            raise OrefApiError(f"Timeout fetching {url}") from err

    @staticmethod
    def _map_threat_to_cat(threat: int, is_drill: bool) -> int:
        """Map Tzofar threat ID to Oref matrix_id."""
        base_cat = TZOFAR_THREAT_TO_OREF_CAT.get(threat)
        if base_cat is None:
            _LOGGER.warning("Unknown Tzofar threat value: %d, defaulting to cat 10", threat)
            base_cat = 10
        # Drills add +100 offset (matching Oref's drill system)
        if is_drill and base_cat < 100:
            return base_cat + TZOFAR_DRILL_CAT_OFFSET
        return base_cat

    @staticmethod
    def _notification_to_alert_dict(notification: dict[str, Any]) -> dict[str, Any]:
        """Convert a Tzofar notification to an OrefAlert-compatible dict."""
        threat = notification.get("threat", 0)
        is_drill = notification.get("isDrill", False)
        cat = TzofarApiClient._map_threat_to_cat(threat, is_drill)

        # Generate title from our ALERT_CATEGORIES
        cat_info = ALERT_CATEGORIES.get(cat, {})
        title = cat_info.get("he", "התרעה")

        return {
            "id": str(notification.get("notificationId", notification.get("time", ""))),
            "cat": cat,
            "title": title,
            "desc": cat_info.get("en", "Alert"),
            "data": notification.get("cities", []),
        }

    async def get_alerts(self) -> list[dict[str, Any]]:
        """Fetch current active alerts from Tzofar notifications API."""
        text = await self._fetch(TZOFAR_ALERTS_URL)
        if not text or text == "null":
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse Tzofar alerts response: %s", text[:200])
            return []
        if not isinstance(data, list):
            return []
        return [self._notification_to_alert_dict(n) for n in data if n]

    async def get_history(self) -> list[dict[str, Any]]:
        """Fetch alert history from Tzofar.

        Returns a list of alert dicts, each with a 'timestamp' field (unix epoch).
        Sorted newest-first.
        """
        text = await self._fetch(TZOFAR_HISTORY_URL)
        if not text or text == "null":
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse Tzofar history response: %s", text[:200])
            return []
        if not isinstance(data, list):
            return []
        # Tzofar history is grouped: [{id, alerts: [{time, cities, threat, isDrill}]}]
        # Flatten into dicts with timestamps preserved
        result = []
        for group in data:
            group_id = group.get("id", "")
            for alert in group.get("alerts", []):
                d = self._notification_to_alert_dict(alert)
                d["timestamp"] = alert.get("time", 0)
                d["group_id"] = group_id
                result.append(d)
        return result

    async def get_districts(self) -> list[dict[str, Any]]:
        """Fetch city/district definitions from Tzofar cities.json.

        Transforms Tzofar format into Oref-compatible format so
        DefinitionsManager._parse_districts() works without changes.
        """
        # Optionally fetch current version
        version = ""
        try:
            ver_text = await self._fetch(TZOFAR_VERSIONS_URL)
            ver_data = json.loads(ver_text)
            version = str(ver_data.get("cities", ""))
        except (OrefApiError, json.JSONDecodeError, KeyError):
            _LOGGER.debug("Could not fetch Tzofar versions, using unversioned URL")

        url = f"{TZOFAR_CITIES_URL}?v={version}" if version else TZOFAR_CITIES_URL
        text = await self._fetch(url)
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse Tzofar cities response: %s", text[:200])
            return []

        # Handle both {"cities": {...}} and flat dict formats
        cities = data.get("cities", data) if isinstance(data, dict) else {}

        # Transform to Oref-compatible format: [{"label_he": city, "areaname": district}]
        result = []
        for city_key, info in cities.items():
            if not isinstance(info, dict):
                continue
            area_id = info.get("area", 0)
            district_name = TZOFAR_AREA_NAMES.get(area_id, str(area_id))
            result.append({
                "label_he": info.get("he", city_key),
                "areaname": district_name,
            })
        return result

    async def _ensure_city_map(self) -> None:
        """Lazily load Tzofar city ID → name mapping from cities.json."""
        if self._city_id_map is not None:
            return
        self._city_id_map = {}
        try:
            # Fetch versioned cities.json
            version = ""
            try:
                ver_text = await self._fetch(TZOFAR_VERSIONS_URL)
                ver_data = json.loads(ver_text)
                version = str(ver_data.get("cities", ""))
            except (OrefApiError, json.JSONDecodeError, KeyError):
                pass
            url = f"{TZOFAR_CITIES_URL}?v={version}" if version else TZOFAR_CITIES_URL
            text = await self._fetch(url)
            data = json.loads(text)
            cities = data.get("cities", data) if isinstance(data, dict) else {}
            for city_key, info in cities.items():
                if isinstance(info, dict) and "id" in info:
                    self._city_id_map[info["id"]] = info.get("he", city_key)
            _LOGGER.debug(
                "Loaded Tzofar city ID map: %d cities", len(self._city_id_map)
            )
        except (OrefApiError, json.JSONDecodeError) as err:
            _LOGGER.warning("Failed to load Tzofar city map: %s", err)

    async def get_early_warnings(self) -> list[dict[str, Any]]:
        """Fetch early warnings from Tzofar iOS feed instructions.

        Tzofar delivers early warnings via SYSTEM_MESSAGE instructions
        (instructionType=0), not through the /notifications endpoint.
        The /ios/feed endpoint provides both alerts and instructions.
        """
        try:
            text = await self._fetch(TZOFAR_FEED_URL)
        except OrefApiError:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse Tzofar feed response")
            return []

        instructions = data.get("instructions", [])
        if not instructions:
            return []

        # Ensure we can resolve city IDs to names
        await self._ensure_city_map()
        if not self._city_id_map:
            _LOGGER.debug("No city map available, skipping early warnings")
            return []

        now = time.time()
        results: list[dict[str, Any]] = []
        for inst in instructions:
            if inst.get("instructionType") != TZOFAR_INSTRUCTION_EARLY_WARNING:
                continue
            # Skip expired instructions
            pin_until = inst.get("pinUntil")
            if pin_until and pin_until < now:
                continue
            # Resolve numeric city IDs to Hebrew names
            city_ids = inst.get("citiesIds", [])
            city_names = [
                self._city_id_map[cid]
                for cid in city_ids
                if cid in self._city_id_map
            ]
            if not city_names:
                continue
            results.append({
                "id": str(inst.get("id", "")),
                "cat": 14,
                "title": OREF_TITLE_EARLY_WARNING_ALT,
                "desc": inst.get("titleEn", "Early Warning"),
                "data": city_names,
            })
        _LOGGER.debug(
            "Tzofar early warnings: %d active from %d instructions",
            len(results),
            len(instructions),
        )
        return results

    async def get_event_ended_cities(self) -> set[str]:
        """Fetch cities with explicit all-clear from Tzofar feed instructions.

        Tzofar delivers "Event Ended" via SYSTEM_MESSAGE instructions
        (instructionType=1) on the /ios/feed endpoint.
        """
        try:
            text = await self._fetch(TZOFAR_FEED_URL)
        except OrefApiError:
            return set()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return set()

        instructions = data.get("instructions", [])
        if not instructions:
            return set()

        await self._ensure_city_map()
        if not self._city_id_map:
            return set()

        # Collect cities from recent END_EVENT instructions (last 15 minutes)
        now = time.time()
        ended_cities: set[str] = set()
        for inst in instructions:
            if inst.get("instructionType") != TZOFAR_INSTRUCTION_END_EVENT:
                continue
            # Only consider recent event-ended (within 15 min)
            inst_time = inst.get("time", 0)
            if now - inst_time > 15 * 60:
                continue
            city_ids = inst.get("citiesIds", [])
            for cid in city_ids:
                name = self._city_id_map.get(cid)
                if name:
                    ended_cities.add(name)

        if ended_cities:
            _LOGGER.debug(
                "Tzofar event-ended: %d cities from feed instructions",
                len(ended_cities),
            )
        return ended_cities

    async def test_connection(self) -> bool:
        """Test if the Tzofar API is reachable."""
        try:
            await self._fetch(TZOFAR_ALERTS_URL)
            return True
        except OrefApiError:
            return False
