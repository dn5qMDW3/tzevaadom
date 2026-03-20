#!/usr/bin/env python3
"""Fetch Oref district definitions and update the bundled fallback data.

This script is run by the CI/CD pipeline to keep the bundled district
definitions up to date. It fetches the latest data from Oref's API
and writes it to the definitions module.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import aiohttp

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


async def fetch_districts() -> list[dict[str, Any]]:
    """Fetch district data from Oref."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            OREF_DISTRICTS_URL, headers=OREF_HEADERS, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            text = await resp.text()
            # Remove BOM if present
            if text.startswith("\ufeff"):
                text = text[1:]
            return json.loads(text)


def parse_districts(raw_data: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Parse raw district data into district -> areas mapping."""
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

    # Sort areas within each district
    return {k: sorted(v) for k, v in sorted(district_map.items())}


async def main() -> int:
    """Main entry point."""
    print("Fetching district definitions from Oref...")

    try:
        raw_data = await fetch_districts()
    except Exception as exc:
        print(f"Error fetching districts: {exc}", file=sys.stderr)
        return 1

    print(f"Fetched {len(raw_data)} raw entries")

    districts = parse_districts(raw_data)
    total_areas = sum(len(areas) for areas in districts.values())
    print(f"Parsed {len(districts)} districts with {total_areas} total areas")

    # Write output
    output = {
        "districts": [
            {"district": district, "areas": areas}
            for district, areas in districts.items()
        ]
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"Written to {OUTPUT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
