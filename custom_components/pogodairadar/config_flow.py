"""Config flow for PogodaiRadar."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SLUG,
    DEFAULT_SCAN,
    DOMAIN,
    SCAN_15_MIN,
    SCAN_1_HOUR,
    SCAN_2_HOURS,
    SCAN_30_MIN,
)


def _slug_title(slug: str) -> str:
    return slug.strip("/").replace("/", " - ")


def _scan_choices() -> dict[str, str]:
    return {
        SCAN_15_MIN: "15 хвилин",
        SCAN_30_MIN: "30 хвилин",
        SCAN_1_HOUR: "1 година",
        SCAN_2_HOURS: "2 години",
    }


class PogodaIRadarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle UI config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            slug = user_input[CONF_SLUG].strip().strip("/")
            if not slug or "/" not in slug:
                errors["base"] = "invalid_slug"
            else:
                await self.async_set_unique_id(slug.lower().replace("/", "_"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_slug_title(slug),
                    data={
                        CONF_SLUG: slug,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SLUG, default=""): str,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN): vol.In(_scan_choices()),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return PogodaIRadarOptionsFlow()


class PogodaIRadarOptionsFlow(OptionsFlow):
    """Change scan interval after setup."""

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        cur = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=cur): vol.In(_scan_choices()),
                }
            ),
        )
