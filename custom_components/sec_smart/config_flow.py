from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SecSmartApi, SecSmartAuthError, SecSmartError
from .const import (
    CONF_ALLOW_CONTROL,
    CONF_ALLOW_SETTINGS,
    CONF_BASE_URL,
    CONF_DEVICES,
    CONF_POLL_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> list[dict[str, Any]]:
    api = SecSmartApi(
        data[CONF_BASE_URL],
        data[CONF_TOKEN],
        async_get_clientsession(hass),
    )
    devices = await api.async_get_devices()
    valid = [device for device in devices if device.get("id")]
    if not valid:
        raise SecSmartError("No SEC Smart devices found")
    return valid


class SecSmartConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure SEC Smart."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                devices = await _validate(self.hass, user_input)
            except SecSmartAuthError:
                errors["base"] = "invalid_auth"
            except SecSmartError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id("sec_smart_account")
                self._abort_if_unique_id_configured()
                data = dict(user_input)
                data[CONF_DEVICES] = devices
                return self.async_create_entry(title="SEC Smart Ventilation", data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._reauth_entry is not None:
            candidate = {
                CONF_TOKEN: user_input[CONF_TOKEN],
                CONF_BASE_URL: self._reauth_entry.data.get(
                    CONF_BASE_URL, DEFAULT_BASE_URL
                ),
            }
            try:
                devices = await _validate(self.hass, candidate)
            except SecSmartAuthError:
                errors["base"] = "invalid_auth"
            except SecSmartError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={CONF_TOKEN: user_input[CONF_TOKEN], CONF_DEVICES: devices},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: Any) -> SecSmartOptionsFlow:
        return SecSmartOptionsFlow()


class SecSmartOptionsFlow(OptionsFlow):
    """Configure polling and opt-in control."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
                    ),
                    vol.Required(
                        CONF_ALLOW_CONTROL,
                        default=self.config_entry.options.get(CONF_ALLOW_CONTROL, False),
                    ): bool,
                    vol.Required(
                        CONF_ALLOW_SETTINGS,
                        default=self.config_entry.options.get(CONF_ALLOW_SETTINGS, False),
                    ): bool,
                }
            ),
        )
