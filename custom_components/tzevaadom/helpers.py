"""Shared helpers for the Tzeva Adom integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry


def get_entry_option(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Get a config value from options, falling back to data, then default."""
    return entry.options.get(key, entry.data.get(key, default))


def validate_proxy_url(url: str) -> str | None:
    """Validate proxy URL scheme. Returns error key or None if valid."""
    if not url:
        return "proxy_required"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "proxy_invalid_scheme"
    return None
