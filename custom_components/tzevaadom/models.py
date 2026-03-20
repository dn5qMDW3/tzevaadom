"""Data models for the Tzeva Adom integration."""

from __future__ import annotations

from dataclasses import dataclass, field

from .const import (
    INFORMATIONAL_TITLES,
    OREF_CAT_EVENT_ENDED,
    OREF_TITLE_EARLY_WARNING,
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
    def from_dict(cls, data: dict) -> OrefAlert:
        """Create an OrefAlert from API response dict."""
        return cls(
            id=str(data.get("id", "")),
            cat=int(data.get("cat", 0)),
            title=data.get("title", ""),
            desc=data.get("desc", ""),
            data=data.get("data", []),
        )

    @property
    def is_real_alert(self) -> bool:
        """Return True if this is a real alert (not informational).

        Filters out:
        - Event Ended notifications (Oref cat=13 + title "האירוע הסתיים")
        - Early Warning messages ("התרעה מקדימה")
        - Other informational titles
        """
        if self.is_event_ended:
            return False
        if self.is_early_warning:
            return False
        if self.title in INFORMATIONAL_TITLES:
            return False
        return True

    @property
    def is_early_warning(self) -> bool:
        """Return True if this is an early warning alert."""
        return self.title == OREF_TITLE_EARLY_WARNING

    @property
    def is_event_ended(self) -> bool:
        """Return True if this is an 'Event Ended' notification."""
        return self.cat == OREF_CAT_EVENT_ENDED and self.title == OREF_TITLE_EVENT_ENDED


@dataclass
class OrefAlertData:
    """Processed alert data from the coordinator."""

    active_alerts: list[OrefAlert] = field(default_factory=list)
    all_alerts: list[OrefAlert] = field(default_factory=list)
    is_active: bool = False
    is_active_all: bool = False
    last_alert: OrefAlert | None = None
    new_alerts: list[OrefAlert] = field(default_factory=list)
    new_alerts_all: list[OrefAlert] = field(default_factory=list)
    # Early warning tracking
    early_warnings: list[OrefAlert] = field(default_factory=list)
    is_early_warning_active: bool = False
    new_early_warnings: list[OrefAlert] = field(default_factory=list)
    # Event ended tracking
    event_ended_cities: list[str] = field(default_factory=list)
