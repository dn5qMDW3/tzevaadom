"""Area and category definitions with auto-update from Oref."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import OrefApiClient, OrefApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# Bundled fallback district data: maps area_name -> district_name
# This is updated by the CI/CD pipeline and serves as fallback when API is unavailable
BUNDLED_DISTRICTS: dict[str, list[dict[str, str]]] = {
    # District groupings - will be populated by update_definitions.py
    # Format: {"label": "district_name", "areas": ["city1", "city2", ...]}
}

# Common district names for initial fallback
DEFAULT_DISTRICTS: list[str] = [
    "אילת",
    "אשדוד",
    "אשקלון",
    "באר שבע",
    "בקעת הירדן",
    "גוש דן",
    "גליל עליון",
    "גליל תחתון",
    "דרום הנגב",
    "הכרמל",
    "המפרץ",
    "העמקים",
    "השפלה",
    "חדרה",
    "חיפה",
    "ירושלים",
    "ירקון",
    "לכיש",
    "מנשה",
    "מערב הנגב",
    "מרכז הנגב",
    "נתניה",
    "עוטף עזה",
    "שומרון",
    "שפלת יהודה",
    "שרון",
    "תל אביב",
]


class DefinitionsManager:
    """Manages area/category definitions with runtime auto-update."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the definitions manager."""
        self.hass = hass
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}_definitions"
        )
        self._districts: list[dict[str, Any]] = []
        self._area_to_district: dict[str, str] = {}

    async def async_load(self) -> None:
        """Load definitions from storage, falling back to bundled data."""
        data = await self._store.async_load()
        if data and "districts" in data:
            self._districts = data["districts"]
            self._build_area_map()
            _LOGGER.debug("Loaded %d districts from storage", len(self._districts))
            return

        # Try loading bundled data from CI/CD-generated file
        bundled_path = Path(__file__).parent / "bundled_districts.json"
        if bundled_path.exists():
            try:
                bundled = json.loads(bundled_path.read_text(encoding="utf-8"))
                if "districts" in bundled:
                    self._districts = bundled["districts"]
                    self._build_area_map()
                    _LOGGER.debug(
                        "Loaded %d districts from bundled data", len(self._districts)
                    )
            except (json.JSONDecodeError, OSError) as exc:
                _LOGGER.warning("Failed to load bundled districts: %s", exc)

    async def async_update(self, client: OrefApiClient) -> bool:
        """Fetch fresh definitions from Oref. Returns True if updated."""
        try:
            raw_districts = await client.get_districts()
        except OrefApiError:
            _LOGGER.warning("Failed to fetch district definitions from Oref")
            return False

        if not raw_districts:
            return False

        # Parse district data
        # Oref districts.json format: list of {label, value, id, areaid, ...}
        new_districts = self._parse_districts(raw_districts)

        if new_districts and new_districts != self._districts:
            old_count = len(self._districts)
            self._districts = new_districts
            self._build_area_map()
            await self._store.async_save({"districts": new_districts})
            _LOGGER.info(
                "Updated district definitions: %d -> %d entries",
                old_count,
                len(new_districts),
            )
            return True

        return False

    def _parse_districts(
        self, raw_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Parse raw district data from Oref API."""
        district_map: dict[str, list[str]] = {}

        for item in raw_data:
            area_name = item.get("label_he") or item.get("label") or item.get("name", "")
            district = item.get("areaname") or item.get("areaid", "")

            if not area_name:
                continue

            if district not in district_map:
                district_map[district] = []
            district_map[district].append(area_name)

        return [
            {"district": district, "areas": sorted(areas)}
            for district, areas in sorted(district_map.items())
            if district
        ]

    def _build_area_map(self) -> None:
        """Build area-to-district lookup."""
        self._area_to_district.clear()
        for entry in self._districts:
            for area in entry.get("areas", []):
                self._area_to_district[area] = entry["district"]

    def get_districts(self) -> list[str]:
        """Get list of district names."""
        if self._districts:
            return [d["district"] for d in self._districts]
        return DEFAULT_DISTRICTS

    def get_areas_for_district(self, district: str) -> list[str]:
        """Get city/area names for a district."""
        for entry in self._districts:
            if entry["district"] == district:
                return entry.get("areas", [])
        return []

    def get_all_areas(self) -> list[str]:
        """Get all known area names."""
        areas = []
        for entry in self._districts:
            areas.extend(entry.get("areas", []))
        return sorted(areas)

    def get_areas_for_districts(self, districts: list[str]) -> list[str]:
        """Get all areas belonging to the given districts."""
        areas = []
        for entry in self._districts:
            if entry["district"] in districts:
                areas.extend(entry.get("areas", []))
        return sorted(areas)
