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

from .api import OrefApiClient
from .const import (
    ALERT_CATEGORIES,
    CONF_AREAS,
    CONF_CATEGORIES,
    CONF_ENABLE_NATIONWIDE,
    CONF_POLL_INTERVAL,
    CONF_PROXY_URL,
    CONF_WEEKLY_RESET_DAY,
    DEFAULT_ENABLE_NATIONWIDE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_WEEKLY_RESET_DAY,
    DOMAIN,
)
from .definitions import DefinitionsManager

_LOGGER = logging.getLogger(__name__)

WEEKDAYS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


class TzevaadomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Tzeva Adom."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._proxy_url: str | None = None
        self._selected_areas: list[str] = []
        self._selected_categories: list[int] = []
        self._definitions: DefinitionsManager | None = None

    async def _get_definitions(self) -> DefinitionsManager:
        """Get or create definitions manager."""
        if self._definitions is None:
            self._definitions = DefinitionsManager(self.hass)
            await self._definitions.async_load()
            # Try to fetch fresh definitions
            session = async_get_clientsession(self.hass)
            client = OrefApiClient(session, self._proxy_url)
            await self._definitions.async_update(client)
        return self._definitions

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the connection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._proxy_url = user_input.get(CONF_PROXY_URL) or None

            # Test connection
            session = async_get_clientsession(self.hass)
            client = OrefApiClient(session, self._proxy_url)
            if await client.test_connection():
                return await self.async_step_areas()

            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PROXY_URL, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "note": "Leave proxy URL empty for direct connection (Israel only)."
            },
        )

    async def async_step_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle area selection step."""
        if user_input is not None:
            self._selected_areas = user_input.get(CONF_AREAS, [])
            return await self.async_step_categories()

        definitions = await self._get_definitions()
        districts = definitions.get_districts()

        options = [{"label": d, "value": d} for d in districts]

        return self.async_show_form(
            step_id="areas",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_AREAS, default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=False,
                        )
                    ),
                }
            ),
            description_placeholders={
                "note": "Select districts to monitor. Leave empty for all areas."
            },
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

            data = {
                CONF_PROXY_URL: self._proxy_url or "",
                CONF_AREAS: resolved_areas,
                CONF_CATEGORIES: self._selected_categories,
                CONF_POLL_INTERVAL: int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)),
                CONF_WEEKLY_RESET_DAY: int(user_input.get(CONF_WEEKLY_RESET_DAY, DEFAULT_WEEKLY_RESET_DAY)),
                CONF_ENABLE_NATIONWIDE: user_input.get(CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE),
                "selected_districts": self._selected_areas,
            }

            title = "Tzeva Adom"
            if self._selected_areas:
                title = f"Tzeva Adom - {', '.join(self._selected_areas[:3])}"
                if len(self._selected_areas) > 3:
                    title += "..."

            return self.async_create_entry(title=title, data=data)

        weekday_options = [
            {"label": name, "value": str(day)} for day, name in WEEKDAYS.items()
        ]

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=2, max=10, step=1, mode=NumberSelectorMode.SLIDER
                        )
                    ),
                    vol.Optional(
                        CONF_WEEKLY_RESET_DAY,
                        default=str(DEFAULT_WEEKLY_RESET_DAY),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=weekday_options,
                            mode=SelectSelectorMode.DROPDOWN,
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
        """Handle the initial options step (areas)."""
        if user_input is not None:
            self._selected_areas = user_input.get(CONF_AREAS, [])
            return await self.async_step_categories()

        definitions = await self._get_definitions()
        districts = definitions.get_districts()
        options = [{"label": d, "value": d} for d in districts]

        current_districts = self._config_entry.data.get("selected_districts", [])

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_AREAS, default=current_districts): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
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
                    CONF_CATEGORIES: self._selected_categories,
                    CONF_POLL_INTERVAL: int(
                        user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
                    ),
                    CONF_WEEKLY_RESET_DAY: int(
                        user_input.get(CONF_WEEKLY_RESET_DAY, DEFAULT_WEEKLY_RESET_DAY)
                    ),
                    CONF_ENABLE_NATIONWIDE: user_input.get(
                        CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE
                    ),
                    "selected_districts": self._selected_areas,
                }
            )

        weekday_options = [
            {"label": name, "value": str(day)} for day, name in WEEKDAYS.items()
        ]

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_POLL_INTERVAL,
                            self._config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=2, max=10, step=1, mode=NumberSelectorMode.SLIDER
                        )
                    ),
                    vol.Optional(
                        CONF_WEEKLY_RESET_DAY,
                        default=str(
                            self._config_entry.options.get(
                                CONF_WEEKLY_RESET_DAY,
                                self._config_entry.data.get(CONF_WEEKLY_RESET_DAY, DEFAULT_WEEKLY_RESET_DAY),
                            )
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=weekday_options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_ENABLE_NATIONWIDE,
                        default=self._config_entry.options.get(
                            CONF_ENABLE_NATIONWIDE,
                            self._config_entry.data.get(CONF_ENABLE_NATIONWIDE, DEFAULT_ENABLE_NATIONWIDE),
                        ),
                    ): bool,
                }
            ),
        )
