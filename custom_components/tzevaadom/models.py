"""Data models for the Tzeva Adom integration."""

from __future__ import annotations

from dataclasses import dataclass, field

from .const import INFORMATIONAL_TITLES, OREF_CAT_EVENT_ENDED, OREF_TITLE_EVENT_ENDED


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
        - Early Warning messages
        - Other informational titles
        """
        # Oref-specific: cat 13 with "Event Ended" title
        if self.cat == OREF_CAT_EVENT_ENDED and self.title == OREF_TITLE_EVENT_ENDED:
            return False
        # General: filter by known informational titles
        if self.title in INFORMATIONAL_TITLES:
            return False
        return True


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
