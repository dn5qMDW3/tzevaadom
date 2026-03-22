#!/usr/bin/env python3
"""Fetch district/city definitions and update the bundled fallback data.

This script is run by the CI/CD pipeline to keep the bundled district
definitions up to date. It fetches from Tzofar (works worldwide) and
falls back to Oref (Israel only) if needed.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import aiohttp

# Tzofar — works worldwide, no geo-restrictions
TZOFAR_CITIES_URL = "https://www.tzevaadom.co.il/static/cities.json"

# Oref — Israel-only fallback
OREF_DISTRICTS_URL = "https://www.oref.org.il/districts/districts_heb.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}

OUTPUT_FILE = (
    Path(__file__).parent.parent
    / "custom_components"
    / "tzevaadom"
    / "bundled_districts.json"
)


async def fetch_from_tzofar(
    session: aiohttp.ClientSession,
) -> list[dict[str, Any]] | None:
    """Fetch district/city data from Tzofar cities.json."""
    try:
        async with session.get(
            TZOFAR_CITIES_URL,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
    except Exception as exc:
        print(f"Tzofar fetch failed: {exc}", file=sys.stderr)
        return None

    areas: dict[str, dict[str, str]] = data.get("areas", {})
    cities: dict[str, dict[str, Any]] = data.get("cities", {})

    if not areas or not cities:
        print("Tzofar response missing areas or cities", file=sys.stderr)
        return None

    # Build area_id -> Hebrew name lookup
    area_id_to_name: dict[str, str] = {}
    for area_id, area_info in areas.items():
        he_name = area_info.get("he", "") if isinstance(area_info, dict) else str(area_info)
        if he_name:
            area_id_to_name[area_id] = he_name

    # Group cities by district
    district_map: dict[str, list[str]] = {}
    for _city_key, city_info in cities.items():
        area_id = str(city_info.get("area", ""))
        city_name = city_info.get("he", "")
        district = area_id_to_name.get(area_id, "")

        if not city_name or not district:
            continue

        if district not in district_map:
            district_map[district] = []
        if city_name not in district_map[district]:
            district_map[district].append(city_name)

    print(f"Tzofar: {len(cities)} cities in {len(district_map)} districts")
    return [
        {"district": district, "areas": sorted(areas_list)}
        for district, areas_list in sorted(district_map.items())
    ]


async def fetch_from_oref(
    session: aiohttp.ClientSession,
) -> list[dict[str, Any]] | None:
    """Fetch district data from Oref (Israel-only fallback)."""
    try:
        async with session.get(
            OREF_DISTRICTS_URL,
            headers=OREF_HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            text = await resp.text()
            # Remove BOM if present
            if text.startswith("\ufeff"):
                text = text[1:]
            raw_data = json.loads(text)
    except Exception as exc:
        print(f"Oref fetch failed: {exc}", file=sys.stderr)
        return None

    district_map: dict[str, list[str]] = {}
    for item in raw_data:
        area_name = (
            item.get("label_he")
            or item.get("label")
            or item.get("name")
            or item.get("heb", "")
        )
        district = (
            item.get("areaname")
            or item.get("area")
            or item.get("areaid", "")
        )

        if not area_name or not district:
            continue

        if district not in district_map:
            district_map[district] = []
        if area_name not in district_map[district]:
            district_map[district].append(area_name)

    print(f"Oref: {len(raw_data)} entries in {len(district_map)} districts")
    return [
        {"district": district, "areas": sorted(areas_list)}
        for district, areas_list in sorted(district_map.items())
    ]


async def main() -> int:
    """Main entry point."""
    async with aiohttp.ClientSession() as session:
        # Try Tzofar first (works worldwide)
        print("Fetching definitions from Tzofar...")
        districts = await fetch_from_tzofar(session)

        # Fall back to Oref (Israel-only)
        if not districts:
            print("Falling back to Oref...")
            districts = await fetch_from_oref(session)

    if not districts:
        print("ERROR: All sources failed", file=sys.stderr)
        return 1

    total_areas = sum(len(d["areas"]) for d in districts)
    print(f"Parsed {len(districts)} districts with {total_areas} total areas")

    # Write output
    output = {"districts": districts}
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"Written to {OUTPUT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
