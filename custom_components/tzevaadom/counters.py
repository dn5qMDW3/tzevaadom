"""Alert counter manager with persistent storage."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEFAULT_WEEKLY_RESET_DAY, DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_TRACKED_IDS = 200


class AlertCounterManager:
    """Manages daily/weekly/monthly/yearly alert counters with persistence."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        weekly_reset_day: int = DEFAULT_WEEKLY_RESET_DAY,
    ) -> None:
        """Initialize the counter manager."""
        self.hass = hass
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}_counters_{entry_id}"
        )
        self._weekly_reset_day = weekly_reset_day
        self._counted_ids: deque[str] = deque(maxlen=MAX_TRACKED_IDS)

        # Counter values
        self.daily_count: int = 0
        self.weekly_count: int = 0
        self.monthly_count: int = 0
        self.yearly_count: int = 0

        # Period tracking
        self._current_date: str = ""
        self._current_week_start: str = ""
        self._current_month: str = ""
        self._current_year: int = 0

    async def async_load(self) -> None:
        """Load counters from storage."""
        data = await self._store.async_load()
        if data is None:
            self._init_periods()
            return

        self.daily_count = data.get("daily_count", 0)
        self.weekly_count = data.get("weekly_count", 0)
        self.monthly_count = data.get("monthly_count", 0)
        self.yearly_count = data.get("yearly_count", 0)
        self._current_date = data.get("current_date", "")
        self._current_week_start = data.get("current_week_start", "")
        self._current_month = data.get("current_month", "")
        self._current_year = data.get("current_year", 0)
        self._counted_ids = deque(
            data.get("counted_ids", []), maxlen=MAX_TRACKED_IDS
        )

        # Check for period rollovers since last save
        self._check_rollovers()

    def _init_periods(self) -> None:
        """Initialize period tracking to current time."""
        now = dt_util.now()
        self._current_date = now.strftime("%Y-%m-%d")
        self._current_week_start = self._get_week_start(now).strftime("%Y-%m-%d")
        self._current_month = now.strftime("%Y-%m")
        self._current_year = now.year

    def _get_week_start(self, dt: datetime) -> datetime:
        """Get the start of the week based on configured reset day."""
        # weekly_reset_day: 0=Monday, 6=Sunday
        days_since_reset = (dt.weekday() - self._weekly_reset_day) % 7
        return dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=days_since_reset
        )

    def _check_rollovers(self) -> None:
        """Check and apply any period rollovers."""
        now = dt_util.now()
        current_date = now.strftime("%Y-%m-%d")
        current_week_start = self._get_week_start(now).strftime("%Y-%m-%d")
        current_month = now.strftime("%Y-%m")
        current_year = now.year

        if current_date != self._current_date:
            _LOGGER.debug("Daily counter rollover: %s -> %s", self._current_date, current_date)
            self.daily_count = 0
            self._current_date = current_date

        if current_week_start != self._current_week_start:
            _LOGGER.debug("Weekly counter rollover")
            self.weekly_count = 0
            self._current_week_start = current_week_start

        if current_month != self._current_month:
            _LOGGER.debug("Monthly counter rollover: %s -> %s", self._current_month, current_month)
            self.monthly_count = 0
            self._current_month = current_month

        if current_year != self._current_year:
            _LOGGER.debug("Yearly counter rollover: %s -> %s", self._current_year, current_year)
            self.yearly_count = 0
            self._current_year = current_year

    def record_alert(self, alert_id: str) -> bool:
        """Record an alert. Returns True if it was a new alert."""
        if alert_id in self._counted_ids:
            return False

        self._check_rollovers()

        self._counted_ids.append(alert_id)
        self.daily_count += 1
        self.weekly_count += 1
        self.monthly_count += 1
        self.yearly_count += 1
        return True

    def reset_all(self) -> None:
        """Reset all counters."""
        self.daily_count = 0
        self.weekly_count = 0
        self.monthly_count = 0
        self.yearly_count = 0
        self._counted_ids.clear()
        self._init_periods()

    async def async_save(self) -> None:
        """Save counters to storage."""
        await self._store.async_save(
            {
                "daily_count": self.daily_count,
                "weekly_count": self.weekly_count,
                "monthly_count": self.monthly_count,
                "yearly_count": self.yearly_count,
                "current_date": self._current_date,
                "current_week_start": self._current_week_start,
                "current_month": self._current_month,
                "current_year": self._current_year,
                "counted_ids": list(self._counted_ids),
            }
        )
