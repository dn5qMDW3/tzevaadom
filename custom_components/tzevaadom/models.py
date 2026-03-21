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

        Oref usually sends these as cat=13, but has been observed with other
        categories too (e.g. cat=10). Match by title alone to be safe.
        """
        return self.title == OREF_TITLE_EVENT_ENDED

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

    def to_event_data(self) -> dict[str, Any]:
        """Return dict suitable for firing as an HA event."""
        return {
            "id": self.id,
            "cat": self.cat,
            "title": self.title,
            "desc": self.desc,
            "cities": self.data,
        }

    def to_state_attributes(self) -> dict[str, Any]:
        """Return dict suitable for entity extra_state_attributes."""
        return {
            "alert_id": self.id,
            "category": self.cat,
            "category_name_he": self.category_name_he,
            "category_name_en": self.category_name_en,
            "title": self.title,
            "description": self.desc,
            "cities": self.data,
        }


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
