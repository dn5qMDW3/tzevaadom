"""Data models for the Tzeva Adom integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    ALERT_CATEGORIES,
    EARLY_WARNING_TITLES,
    INFORMATIONAL_TITLES,
    OREF_CAT_UPDATE,
    OREF_TITLE_EVENT_ENDED,
)


@dataclass
class OrefAlert:
    """Represents a single Oref alert."""

    id: str
    cat: int
    title: str
    desc: str
    data: list[str] = field(default_factory=list)
    # Minimum shelter time in seconds across alerting cities (None if unknown)
    shelter_time: int | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> OrefAlert:
        """Create an OrefAlert from a normalized API response dict.

        All API clients normalize to: {id, cat, title, desc, data: list[str]}
        The 'cat' field always contains the Oref matrix_id.
        """
        cat = int(raw.get("cat", 0))
        cities = raw.get("data") or []
        if isinstance(cities, str):
            cities = [cities] if cities else []
        return cls(
            id=str(raw.get("id", "")),
            cat=cat,
            title=raw.get("title", ""),
            desc=raw.get("desc", ""),
            data=cities,
        )

    @property
    def is_real_alert(self) -> bool:
        """Return True if this is a real alert (not informational/drill)."""
        if self.is_event_ended:
            return False
        if self.is_early_warning:
            return False
        if self.title in INFORMATIONAL_TITLES:
            return False
        # matrix_id 10 = update/flash (event-ended, instructions, etc.)
        if self.cat == OREF_CAT_UPDATE:
            return False
        return True

    @property
    def is_drill(self) -> bool:
        """Return True if this is a drill alert (matrix_id >= 100)."""
        return self.cat >= 100

    @property
    def is_early_warning(self) -> bool:
        """Return True if this is an early warning alert."""
        return self.title in EARLY_WARNING_TITLES

    @property
    def is_event_ended(self) -> bool:
        """Return True if this is an 'Event Ended' notification.

        Uses 'in' rather than '==' to catch category-specific variants like
        "ירי רקטות וטילים - האירוע הסתיים" and "חדירת כלי טיס עוין - האירוע הסתיים".
        """
        return OREF_TITLE_EVENT_ENDED in self.title

    @property
    def category_info(self) -> dict[str, str]:
        """Return category metadata from ALERT_CATEGORIES."""
        return ALERT_CATEGORIES.get(self.cat, {})

    @property
    def category_name_he(self) -> str:
        """Return Hebrew category name."""
        return self.category_info.get("he", "")

    @property
    def category_name_en(self) -> str:
        """Return English category name."""
        return self.category_info.get("en", "")

    @property
    def category_icon(self) -> str:
        """Return MDI icon for this category."""
        return self.category_info.get("icon", "mdi:alert")

    @property
    def priority(self) -> int:
        """Return alert priority (higher = more severe). From Oref alertCategories.json."""
        return self.category_info.get("priority", 0)

    def to_event_data(self) -> dict[str, Any]:
        """Return dict suitable for firing as an HA event."""
        data: dict[str, Any] = {
            "id": self.id,
            "cat": self.cat,
            "title": self.title,
            "desc": self.desc,
            "cities": self.data,
            "is_drill": self.is_drill,
            "category_name_he": self.category_name_he,
            "category_name_en": self.category_name_en,
            "priority": self.priority,
        }
        if self.shelter_time is not None:
            data["shelter_time"] = self.shelter_time
        return data

    def to_state_attributes(self) -> dict[str, Any]:
        """Return dict suitable for entity extra_state_attributes."""
        attrs: dict[str, Any] = {
            "alert_id": self.id,
            "category": self.cat,
            "category_name_he": self.category_name_he,
            "category_name_en": self.category_name_en,
            "title": self.title,
            "description": self.desc,
            "cities": self.data,
            "is_drill": self.is_drill,
            "priority": self.priority,
        }
        if self.shelter_time is not None:
            attrs["shelter_time"] = self.shelter_time
        return attrs


@dataclass
class OrefAlertData:
    """Processed alert data from the coordinator."""

    active_alerts: list[OrefAlert] = field(default_factory=list)
    all_alerts: list[OrefAlert] = field(default_factory=list)
    last_alert: OrefAlert | None = None
    new_alerts: list[OrefAlert] = field(default_factory=list)
    new_alerts_all: list[OrefAlert] = field(default_factory=list)
    # Early warning tracking
    early_warnings: list[OrefAlert] = field(default_factory=list)
    new_early_warnings: list[OrefAlert] = field(default_factory=list)
    # Event ended tracking
    event_ended_cities: list[str] = field(default_factory=list)
    # Time in shelter (seconds since oldest retained alert started)
    time_in_shelter_seconds: int | None = None
    # Count of cities with retained (active) alerts
    retained_cities_count: int = 0

    @property
    def is_active(self) -> bool:
        """Return True if filtered alerts are active."""
        return bool(self.active_alerts)

    @property
    def is_active_all(self) -> bool:
        """Return True if any nationwide alerts are active."""
        return bool(self.all_alerts)

    @property
    def is_early_warning_active(self) -> bool:
        """Return True if early warnings are active."""
        return bool(self.early_warnings)

    @staticmethod
    def collect_cities(alerts: list[OrefAlert]) -> list[str]:
        """Collect all city names from a list of alerts."""
        cities: list[str] = []
        for a in alerts:
            cities.extend(a.data)
        return cities

    @property
    def active_cities_count(self) -> int:
        """Return total number of cities under alert nationwide."""
        return len(self.collect_cities(self.all_alerts))

    @property
    def filtered_cities_count(self) -> int:
        """Return number of filtered cities under alert."""
        return len(self.collect_cities(self.active_alerts))
