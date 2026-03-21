"""Config flow for Tzeva Adom integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AlertApiClient
from .const import (
    ALERT_CATEGORIES,
    CONF_AREAS,
    CONF_CATEGORIES,
    CONF_CITIES,
    CONF_DATA_SOURCE,
    CONF_ENABLE_NATIONWIDE,
    CONF_POLL_INTERVAL,
    CONF_PROXY_URL,
    DATA_SOURCE_OREF,
    DATA_SOURCE_OREF_PROXY,
    DATA_SOURCE_TZOFAR,
    DEFAULT_ENABLE_NATIONWIDE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL_TZOFAR,
    DOMAIN,
)
from .definitions import DefinitionsManager
from .helpers import get_entry_option, validate_proxy_url

_LOGGER = logging.getLogger(__name__)

DATA_SOURCE_OPTIONS = [
    {"label": "Tzofar / tzevaadom.co.il (Worldwide)", "value": DATA_SOURCE_TZOFAR},
    {"label": "Oref API (Direct - Israel only)", "value": DATA_SOURCE_OREF},
    {"label": "Oref API via Proxy", "value": DATA_SOURCE_OREF_PROXY},
]


class TzevaadomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Tzeva Adom."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data_source: str = DATA_SOURCE_TZOFAR
        self._proxy_url: str | None = None
        self._selected_areas: list[str] = []
        self._selected_cities: list[str] = []
        self._selected_categories: list[int] = []
        self._definitions: DefinitionsManager | None = None

    def _create_api_client(self) -> AlertApiClient:
        """Create API client based on current config."""
        from . import create_api_client  # noqa: C0415

        session = async_get_clientsession(self.hass)
        return create_api_client(session, self._data_source, self._proxy_url)

    async def _get_definitions(self) -> DefinitionsManager:
        """Get or create definitions manager."""
        if self._definitions is None:
            self._definitions = DefinitionsManager(self.hass)
            await self._definitions.async_load()
            # Try to fetch fresh definitions using the selected source
            client = self._create_api_client()
            await self._definitions.async_update(client)
        return self._definitions

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle data source selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data_source = user_input.get(CONF_DATA_SOURCE, DATA_SOURCE_TZOFAR)

            if self._data_source == DATA_SOURCE_OREF_PROXY:
                # Need proxy URL — go to proxy step
                return await self.async_step_proxy()

            # Test connection directly
            client = self._create_api_client()
            if await client.test_connection():
                return await self.async_step_areas()

            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DATA_SOURCE, default=DATA_SOURCE_TZOFAR
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=DATA_SOURCE_OPTIONS,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_proxy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle proxy URL input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._proxy_url = user_input.get(CONF_PROXY_URL) or None

            if not self._proxy_url:
                errors[CONF_PROXY_URL] = "proxy_required"
            else:
                # Validate URL scheme before attempting connection
                url_error = validate_proxy_url(self._proxy_url)
                if url_error:
                    errors[CONF_PROXY_URL] = url_error
                else:
                    # Test connection via proxy
                    client = self._create_api_client()
                    if await client.test_connection():
                        return await self.async_step_areas()
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="proxy",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROXY_URL, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle location selection step (districts + cities on one screen)."""
        if user_input is not None:
            self._selected_areas = user_input.get(CONF_AREAS, [])
            self._selected_cities = user_input.get(CONF_CITIES, [])
            return await self.async_step_categories()

        definitions = await self._get_definitions()
        districts = definitions.get_districts()

        district_options = [{"label": d, "value": d} for d in districts]
        city_options = definitions.get_all_cities()

        return self.async_show_form(
            step_id="areas",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_AREAS, default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=district_options,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=False,
                        )
                    ),
                    vol.Optional(CONF_CITIES, default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=city_options,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=False,
                        )
                    ),
                }
            ),
        )

    async def async_step_categories(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle category selection step."""
        if user_input is not None:
            self._selected_categories = [
                int(c) for c in user_input.get(CONF_CATEGORIES, [])
            ]
            return await self.async_step_options()

        options = [
            {"label": f"{info['he']} / {info['en']}", "value": str(cat_id)}
            for cat_id, info in ALERT_CATEGORIES.items()
        ]

        # Default: rockets and hostile aircraft
        defaults = ["1", "2"]

        return self.async_show_form(
            step_id="categories",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CATEGORIES, default=defaults): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                            custom_value=False,
                        )
                    ),
                }
            ),
            description_placeholders={
                "note": "Select alert categories to monitor. Leave empty for all."
            },
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options step."""
        if user_input is not None:
            # Resolve areas from districts
            definitions = await self._get_definitions()
            resolved_areas = []
            if self._selected_areas:
                resolved_areas = definitions.get_areas_for_districts(
                    self._selected_areas
                )

            # Choose default poll interval based on data source
            default_interval = (
                DEFAULT_POLL_INTERVAL_TZOFAR
                if self._data_source == DATA_SOURCE_TZOFAR
                else DEFAULT_POLL_INTERVAL
            )

            data = {
                CONF_DATA_SOURCE: self._data_source,
                CONF_PROXY_URL: self._proxy_url or "",
                CONF_AREAS: resolved_areas,
                CONF_CITIES: self._selected_cities,
                CONF_CATEGORIES: self._selected_categories,
                CONF_POLL_INTERVAL: int(user_input.get(CONF_POLL_INTERVAL, default_interval)),
                CONF_ENABLE_NATIONWIDE: user_input.get(CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE),
                "selected_districts": self._selected_areas,
            }

            title = "Tzeva Adom"
            if self._selected_cities:
                title = f"Tzeva Adom - {', '.join(self._selected_cities[:3])}"
                if len(self._selected_cities) > 3:
                    title += "..."
            elif self._selected_areas:
                title = f"Tzeva Adom - {', '.join(self._selected_areas[:3])}"
                if len(self._selected_areas) > 3:
                    title += "..."

            return self.async_create_entry(title=title, data=data)

        # Choose default poll interval based on data source
        default_interval = (
            DEFAULT_POLL_INTERVAL_TZOFAR
            if self._data_source == DATA_SOURCE_TZOFAR
            else DEFAULT_POLL_INTERVAL
        )
        min_interval = 3 if self._data_source == DATA_SOURCE_TZOFAR else 2

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL, default=default_interval
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=min_interval, max=10, step=1, mode=NumberSelectorMode.SLIDER
                        )
                    ),
                    vol.Optional(
                        CONF_ENABLE_NATIONWIDE, default=DEFAULT_ENABLE_NATIONWIDE
                    ): bool,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TzevaadomOptionsFlow:
        """Get the options flow."""
        return TzevaadomOptionsFlow(config_entry)


class TzevaadomOptionsFlow(OptionsFlow):
    """Options flow for Tzeva Adom."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._selected_areas: list[str] = []
        self._selected_cities: list[str] = []
        self._selected_categories: list[int] = []
        self._definitions: DefinitionsManager | None = None

    async def _get_definitions(self) -> DefinitionsManager:
        """Get or create definitions manager."""
        if self._definitions is None:
            self._definitions = DefinitionsManager(self.hass)
            await self._definitions.async_load()
        return self._definitions

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial options step (districts + cities)."""
        if user_input is not None:
            self._selected_areas = user_input.get(CONF_AREAS, [])
            self._selected_cities = user_input.get(CONF_CITIES, [])
            return await self.async_step_categories()

        definitions = await self._get_definitions()
        districts = definitions.get_districts()
        district_options = [{"label": d, "value": d} for d in districts]
        city_options = definitions.get_all_cities()

        current_districts = self._config_entry.data.get("selected_districts", [])
        current_cities = get_entry_option(self._config_entry, CONF_CITIES, [])

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_AREAS, default=current_districts): SelectSelector(
                        SelectSelectorConfig(
                            options=district_options,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=False,
                        )
                    ),
                    vol.Optional(CONF_CITIES, default=current_cities): SelectSelector(
                        SelectSelectorConfig(
                            options=city_options,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=False,
                        )
                    ),
                }
            ),
        )

    async def async_step_categories(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle category selection in options."""
        if user_input is not None:
            self._selected_categories = [
                int(c) for c in user_input.get(CONF_CATEGORIES, [])
            ]
            return await self.async_step_settings()

        options = [
            {"label": f"{info['he']} / {info['en']}", "value": str(cat_id)}
            for cat_id, info in ALERT_CATEGORIES.items()
        ]

        current = [str(c) for c in self._config_entry.data.get(CONF_CATEGORIES, [])]

        return self.async_show_form(
            step_id="categories",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CATEGORIES, default=current): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                            custom_value=False,
                        )
                    ),
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle settings in options."""
        if user_input is not None:
            definitions = await self._get_definitions()
            resolved_areas = []
            if self._selected_areas:
                resolved_areas = definitions.get_areas_for_districts(
                    self._selected_areas
                )

            return self.async_create_entry(
                data={
                    CONF_AREAS: resolved_areas,
                    CONF_CITIES: self._selected_cities,
                    CONF_CATEGORIES: self._selected_categories,
                    CONF_POLL_INTERVAL: int(
                        user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
                    ),
                    CONF_ENABLE_NATIONWIDE: user_input.get(
                        CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE
                    ),
                    "selected_districts": self._selected_areas,
                }
            )

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=get_entry_option(
                            self._config_entry, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=2, max=10, step=1, mode=NumberSelectorMode.SLIDER
                        )
                    ),
                    vol.Optional(
                        CONF_ENABLE_NATIONWIDE,
                        default=get_entry_option(
                            self._config_entry, CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE
                        ),
                    ): bool,
                }
            ),
        )
