"""API clients for alert data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    ALERT_CATEGORIES,
    OREF_ALERTS_URL,
    OREF_DISTRICTS_URL,
    OREF_HEADERS,
    OREF_HISTORY_ASPX_URL,
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

    async def _fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Fetch data from the API and return raw text."""
        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()
                return (await response.text()).strip()
        except ClientError as err:
            raise OrefApiError(f"Error fetching {url}: {err}") from err
        except TimeoutError as err:
            raise OrefApiError(f"Timeout fetching {url}") from err


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

    async def _fetch(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        """Fetch data from Oref API with BOM stripping."""
        text = await super()._fetch(
            self._build_url(url), headers=headers or OREF_HEADERS
        )
        # Remove UTF-8 BOM if present
        if text.startswith("\ufeff"):
            text = text[1:]
        return text

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

        Primary: ASPX endpoint (24h, up to 3000 entries, works worldwide).
        Fallback: AlertsHistory.json (~1h, requires Israel/proxy).
        """
        # Try ASPX endpoint first (better data, works worldwide)
        try:
            result = await self._fetch_history_aspx()
            if result:
                return result
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "ASPX history fetch failed, trying legacy endpoint", exc_info=True
            )

        # Fallback to legacy AlertsHistory.json
        return await self._fetch_history_legacy()

    async def _fetch_history_aspx(self) -> list[dict[str, Any]]:
        """Fetch from the ASPX history endpoint (24h, up to 3000 entries).

        This endpoint is on alerts-history.oref.org.il (different domain),
        requires no special headers, and works worldwide.
        Response: {data, date, time, alertDate, category, category_desc,
                   matrix_id, rid}
        NOTE: 'category' here is Oref's internal catId, NOT matrix_id.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        url = f"{OREF_HISTORY_ASPX_URL}?lang=he&mode=1"
        try:
            async with self._session.get(
                url, timeout=REQUEST_TIMEOUT
            ) as response:
                response.raise_for_status()
                text = await response.text()
        except ClientError as err:
            raise OrefApiError(f"Error fetching ASPX history: {err}") from err
        except TimeoutError as err:
            raise OrefApiError("Timeout fetching ASPX history") from err

        if text.startswith("\ufeff"):
            text = text[1:]
        text = text.strip()
        if not text or text == "null":
            return []

        data = json.loads(text)
        if not isinstance(data, list):
            return []

        israel_tz = ZoneInfo("Asia/Jerusalem")
        result: list[dict[str, Any]] = []
        for item in data:
            # Use matrix_id (NOT category — that's Oref's internal catId)
            cat = int(item.get("matrix_id", 0))
            cat_info = ALERT_CATEGORIES.get(cat, {})

            cities = item.get("data", "")
            if isinstance(cities, str):
                cities = [cities] if cities else []

            # alertDate is Israel local time with no timezone info
            timestamp = 0
            alert_date = item.get("alertDate", "")
            if alert_date:
                try:
                    dt = datetime.fromisoformat(alert_date)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=israel_tz)
                    timestamp = int(dt.timestamp())
                except (ValueError, TypeError):
                    pass

            result.append({
                "id": str(item.get("rid", timestamp)),
                "cat": cat,
                "title": item.get("category_desc", cat_info.get("he", "")),
                "desc": cat_info.get("en", ""),
                "data": cities,
                "timestamp": timestamp,
            })
        return result

    async def _fetch_history_legacy(self) -> list[dict[str, Any]]:
        """Fetch from legacy AlertsHistory.json (fallback, ~1h of data).

        Response: {alertDate, title, data (single string), category}
        NOTE: 'category' in this endpoint IS effectively the matrix_id
        (despite the confusing name — it matches matrix_id values).
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

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

        israel_tz = ZoneInfo("Asia/Jerusalem")
        result: list[dict[str, Any]] = []
        for item in data:
            # In AlertsHistory.json, 'category' holds matrix_id values
            cat = int(
                item.get("matrix_id", item.get("cat", item.get("category", 0)))
            )
            cat_info = ALERT_CATEGORIES.get(cat, {})

            cities = item.get("data", "")
            if isinstance(cities, str):
                cities = [cities] if cities else []

            timestamp = 0
            alert_date = item.get("alertDate", "")
            if alert_date:
                try:
                    dt = datetime.fromisoformat(
                        alert_date.replace(" ", "T")
                    )
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=israel_tz)
                    timestamp = int(dt.timestamp())
                except (ValueError, TypeError):
                    pass

            result.append({
                "id": str(item.get("rid", item.get("id", timestamp))),
                "cat": cat,
                "title": item.get("title", cat_info.get("he", "")),
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
        self._feed_cache: tuple[list[dict[str, Any]], set[str]] | None = None

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
        return [
            self._notification_to_alert_dict(n)
            for n in data
            if isinstance(n, dict)
        ]

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
            alerts = group.get("alerts", [])
            if not isinstance(alerts, list):
                continue
            for alert in alerts:
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
        warnings, _ = await self._get_feed_data()
        return warnings

    async def get_event_ended_cities(self) -> set[str]:
        """Fetch cities with explicit all-clear from Tzofar feed instructions.

        Tzofar delivers "Event Ended" via SYSTEM_MESSAGE instructions
        (instructionType=1) on the /ios/feed endpoint.
        """
        _, ended = await self._get_feed_data()
        return ended

    async def _get_feed_data(
        self,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """Fetch and parse the /ios/feed endpoint once.

        Returns (early_warnings, event_ended_cities) from a single HTTP call.
        Both get_early_warnings() and get_event_ended_cities() delegate here
        so the feed is only fetched once per coordinator update cycle.
        """
        # Return cached result if available for this cycle
        if self._feed_cache is not None:
            return self._feed_cache

        early_warnings: list[dict[str, Any]] = []
        ended_cities: set[str] = set()

        try:
            text = await self._fetch(TZOFAR_FEED_URL)
        except OrefApiError:
            return early_warnings, ended_cities
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse Tzofar feed response")
            return early_warnings, ended_cities

        instructions = data.get("instructions", [])
        if not instructions:
            return early_warnings, ended_cities

        await self._ensure_city_map()
        if not self._city_id_map:
            _LOGGER.debug("No city map available, skipping feed parsing")
            return early_warnings, ended_cities

        now = time.time()

        for inst in instructions:
            inst_type = inst.get("instructionType")

            if inst_type == TZOFAR_INSTRUCTION_EARLY_WARNING:
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
                early_warnings.append({
                    "id": str(inst.get("id", "")),
                    "cat": 14,
                    "title": OREF_TITLE_EARLY_WARNING_ALT,
                    "desc": inst.get("titleEn", "Early Warning"),
                    "data": city_names,
                })

            elif inst_type == TZOFAR_INSTRUCTION_END_EVENT:
                # Only consider recent event-ended (within 15 min)
                inst_time = inst.get("time", 0)
                if now - inst_time > 15 * 60:
                    continue
                city_ids = inst.get("citiesIds", [])
                for cid in city_ids:
                    name = self._city_id_map.get(cid)
                    if name:
                        ended_cities.add(name)

        _LOGGER.debug(
            "Tzofar feed: %d early warnings, %d event-ended cities from %d instructions",
            len(early_warnings),
            len(ended_cities),
            len(instructions),
        )

        # Cache for the current update cycle
        self._feed_cache = (early_warnings, ended_cities)
        return early_warnings, ended_cities

    def clear_feed_cache(self) -> None:
        """Clear the feed cache. Called by coordinator at start of each update."""
        self._feed_cache = None

    async def test_connection(self) -> bool:
        """Test if the Tzofar API is reachable."""
        try:
            await self._fetch(TZOFAR_ALERTS_URL)
            return True
        except OrefApiError:
            return False
