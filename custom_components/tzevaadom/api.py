"""API clients for alert data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    ALERT_CATEGORIES,
    OREF_ALERTS_URL,
    OREF_DISTRICTS_URL,
    OREF_HEADERS,
    OREF_HISTORY_URL,
    TZOFAR_ALERTS_URL,
    TZOFAR_AREA_NAMES,
    TZOFAR_CITIES_URL,
    TZOFAR_DRILL_CAT_OFFSET,
    TZOFAR_HISTORY_URL,
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
        """Fetch alert history."""

    @abstractmethod
    async def get_districts(self) -> list[dict[str, Any]]:
        """Fetch district/city definitions.

        Must return dicts compatible with DefinitionsManager._parse_districts():
        [{"label_he": str, "areaname": str, ...}]
        """

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the API is reachable."""


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
        """Fetch alert history."""
        text = await self._fetch(OREF_HISTORY_URL)
        if not text or text == "null":
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse history response: %s", text[:200])
            return []
        if isinstance(data, list):
            return data
        return []

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
        """Map Tzofar threat ID to Oref category ID."""
        base_cat = TZOFAR_THREAT_TO_OREF_CAT.get(threat)
        if base_cat is None:
            _LOGGER.warning("Unknown Tzofar threat value: %d, defaulting to cat 14", threat)
            base_cat = 14
        # Drills shift categories 1-6 to 8-13
        if is_drill and 1 <= base_cat <= 6:
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
        """Fetch alert history from Tzofar."""
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
        # Flatten into OrefAlert-compatible dicts
        result = []
        for group in data:
            for alert in group.get("alerts", []):
                result.append(self._notification_to_alert_dict(alert))
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

    async def test_connection(self) -> bool:
        """Test if the Tzofar API is reachable."""
        try:
            await self._fetch(TZOFAR_ALERTS_URL)
            return True
        except OrefApiError:
            return False
