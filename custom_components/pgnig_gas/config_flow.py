"""Config flow for the PGNiG/ORLEN gas history integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import CONF_METER, DOMAIN
from .statistics import discover_meters


class PgnigGasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick one of the gas meters exposed by pgnig-sensor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        configured = {e.unique_id for e in self._async_current_entries()}
        meters = [m for m in discover_meters(self.hass) if m not in configured]
        if not meters:
            return self.async_abort(reason="no_meters")

        if user_input is not None:
            meter = user_input[CONF_METER]
            await self.async_set_unique_id(meter)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Gaz {meter}", data={CONF_METER: meter}
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_METER, default=meters[0]): SelectSelector(
                        SelectSelectorConfig(options=meters)
                    )
                }
            ),
        )
