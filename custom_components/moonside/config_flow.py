"""Config flow for Moonside integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_BLE_NAME,
    CONF_CLOUD_DEVICE_ID,
    CONF_CLOUD_EMAIL,
    CONF_CLOUD_PASSWORD,
    CONF_CLOUD_WRITE_GRACE_SECONDS,
    DEFAULT_CLOUD_WRITE_GRACE_SECONDS,
    DEFAULT_NAME,
    DOMAIN,
)
from .moonside import get_display_name_from_ble_name

LOGGER = logging.getLogger(__name__)

MANUAL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]*$")


def _is_valid_manual_identifier(value: str) -> bool:
    """Return whether a manually entered BLE identifier looks plausible."""
    if not isinstance(value, str):
        return False

    candidate = value.strip()
    return bool(candidate) and bool(MANUAL_IDENTIFIER_PATTERN.fullmatch(candidate))


class MoonsideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Moonside."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        LOGGER.debug(
            "Discovered Moonside device: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None

        discovery_info = self._discovery_info
        default_name = get_display_name_from_ble_name(discovery_info.name)

        if user_input is not None:
            data = {
                CONF_MAC: discovery_info.address,
                CONF_NAME: user_input.get(CONF_NAME, default_name),
            }
            if discovery_info.name:
                data[CONF_BLE_NAME] = discovery_info.name

            return self.async_create_entry(
                title=user_input.get(CONF_NAME, default_name),
                data=data,
            )

        self._set_confirm_only()

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": discovery_info.name or DEFAULT_NAME,
                "address": discovery_info.address,
            },
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=default_name): str,
                }
            ),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_MAC]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            discovery_info = self._discovered_devices[address]
            default_name = get_display_name_from_ble_name(discovery_info.name)
            data = {
                CONF_MAC: address,
                CONF_NAME: user_input.get(CONF_NAME, default_name),
            }
            if discovery_info.name:
                data[CONF_BLE_NAME] = discovery_info.name

            return self.async_create_entry(
                title=user_input.get(CONF_NAME, default_name),
                data=data,
            )

        current_addresses = self._async_current_ids()

        for discovery_info in async_discovered_service_info(self.hass):
            address = discovery_info.address

            if address in current_addresses:
                continue

            if not discovery_info.name or not discovery_info.name.startswith(
                "MOONSIDE"
            ):
                continue

            LOGGER.debug(
                "Found Moonside device during scan: %s (%s)",
                discovery_info.name,
                address,
            )

            self._discovered_devices[address] = discovery_info

        if not self._discovered_devices:
            return await self.async_step_manual()

        mac_addresses = {
            address: info.name for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): vol.In(mac_addresses),
                    vol.Optional(CONF_NAME): str,
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual device entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac_address = user_input[CONF_MAC].strip()

            if not _is_valid_manual_identifier(mac_address):
                errors["base"] = "invalid_identifier"
            else:
                await self.async_set_unique_id(mac_address)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data={
                        CONF_MAC: mac_address,
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): str,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MoonsideOptionsFlowHandler:
        """Get the options flow for this handler."""
        return MoonsideOptionsFlowHandler(config_entry)


class MoonsideOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Moonside options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            if not user_input.get(CONF_CLOUD_EMAIL) or not user_input.get(
                CONF_CLOUD_PASSWORD
            ):
                user_input = {}
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CLOUD_EMAIL,
                        default=self._config_entry.options.get(CONF_CLOUD_EMAIL, ""),
                    ): str,
                    vol.Optional(
                        CONF_CLOUD_PASSWORD,
                        default=self._config_entry.options.get(CONF_CLOUD_PASSWORD, ""),
                    ): str,
                    vol.Optional(
                        CONF_CLOUD_DEVICE_ID,
                        default=self._config_entry.options.get(
                            CONF_CLOUD_DEVICE_ID, ""
                        ),
                    ): str,
                    vol.Optional(
                        CONF_CLOUD_WRITE_GRACE_SECONDS,
                        default=self._config_entry.options.get(
                            CONF_CLOUD_WRITE_GRACE_SECONDS,
                            DEFAULT_CLOUD_WRITE_GRACE_SECONDS,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                }
            ),
        )
