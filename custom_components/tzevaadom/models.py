"""Data models for the Tzeva Adom integration."""

from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass
class OrefAlertData:
    """Processed alert data from the coordinator."""

    active_alerts: list[OrefAlert] = field(default_factory=list)
    all_alerts: list[OrefAlert] = field(default_factory=list)
    is_active: bool = False
    is_active_all: bool = False
    last_alert: OrefAlert | None = None
    new_alerts: list[OrefAlert] = field(default_factory=list)
