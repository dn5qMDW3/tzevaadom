"""API client for Oref alerts."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import OREF_ALERTS_URL, OREF_DISTRICTS_URL, OREF_HEADERS, OREF_HISTORY_URL

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=10)


class OrefApiError(Exception):
    """Exception for Oref API errors."""


class OrefApiClient:
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
