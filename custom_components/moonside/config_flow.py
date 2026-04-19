"""Config flow for Moonside integration."""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import MoonsideCloudAuthError, MoonsideCloudClient, MoonsideCloudError
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
from .moonside import discover_devices, get_display_name_from_ble_name

LOGGER = logging.getLogger(__name__)

MANUAL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]*$")
CONF_DEVICE_IDENTIFIER = "device_identifier"
CONF_CLOUD_AUTH_ACTION = "cloud_auth_action"

ACTION_SIGN_IN = "sign_in"
ACTION_CREATE_ACCOUNT = "create_account"
ACTION_RESET_PASSWORD = "reset_password"

CLOUD_AUTH_ACTIONS = {
    ACTION_SIGN_IN: "Sign in to existing account",
    ACTION_CREATE_ACCOUNT: "Create cloud account",
    ACTION_RESET_PASSWORD: "Send password reset email",
}


def _is_valid_manual_identifier(value: str) -> bool:
    """Return whether a manually entered BLE identifier looks plausible."""
    if not isinstance(value, str):
        return False

    candidate = value.strip()
    return bool(candidate) and bool(MANUAL_IDENTIFIER_PATTERN.fullmatch(candidate))


class MoonsideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Moonside."""

    VERSION = 4

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, Any] = {}
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._entry_data: dict[str, Any] | None = None
        self._cloud_status_message = ""

    def _get_cloud_description_placeholders(self) -> dict[str, str]:
        """Return description placeholders for the cloud forms."""
        return {"status_message": self._cloud_status_message}

    def _build_cloud_schema(
        self,
        *,
        defaults: dict[str, Any] | None = None,
        options_data: dict[str, Any] | None = None,
    ) -> vol.Schema:
        """Return the shared cloud auth form schema."""
        defaults = defaults or {}
        options_data = options_data or {}
        return vol.Schema(
            {
                vol.Optional(
                    CONF_CLOUD_AUTH_ACTION,
                    default=defaults.get(CONF_CLOUD_AUTH_ACTION, ACTION_SIGN_IN),
                ): vol.In(CLOUD_AUTH_ACTIONS),
                vol.Optional(
                    CONF_CLOUD_EMAIL,
                    default=defaults.get(
                        CONF_CLOUD_EMAIL, options_data.get(CONF_CLOUD_EMAIL, "")
                    ),
                ): str,
                vol.Optional(
                    CONF_CLOUD_PASSWORD,
                    default=defaults.get(
                        CONF_CLOUD_PASSWORD, options_data.get(CONF_CLOUD_PASSWORD, "")
                    ),
                ): str,
                vol.Optional(
                    CONF_CLOUD_DEVICE_ID,
                    default=defaults.get(
                        CONF_CLOUD_DEVICE_ID, options_data.get(CONF_CLOUD_DEVICE_ID, "")
                    ),
                ): str,
                vol.Optional(
                    CONF_CLOUD_WRITE_GRACE_SECONDS,
                    default=defaults.get(
                        CONF_CLOUD_WRITE_GRACE_SECONDS,
                        options_data.get(
                            CONF_CLOUD_WRITE_GRACE_SECONDS,
                            DEFAULT_CLOUD_WRITE_GRACE_SECONDS,
                        ),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
            }
        )

    async def _async_validate_cloud_input(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """Validate and normalize optional cloud credentials."""
        action = user_input.get(CONF_CLOUD_AUTH_ACTION, ACTION_SIGN_IN)
        email = user_input.get(CONF_CLOUD_EMAIL, "").strip()
        password = user_input.get(CONF_CLOUD_PASSWORD, "")
        device_id = user_input.get(CONF_CLOUD_DEVICE_ID, "").strip()
        grace_seconds = int(
            user_input.get(
                CONF_CLOUD_WRITE_GRACE_SECONDS, DEFAULT_CLOUD_WRITE_GRACE_SECONDS
            )
        )

        if action == ACTION_RESET_PASSWORD:
            if not email:
                return None, "cloud_email_required", None

            cloud_client = MoonsideCloudClient(
                async_get_clientsession(self.hass),
                email,
                password,
            )
            try:
                await cloud_client.async_send_password_reset_email()
            except MoonsideCloudAuthError as err:
                return None, _map_cloud_auth_error(str(err)), None
            except MoonsideCloudError:
                return None, "cannot_connect", None

            return None, None, "Password reset email sent."

        if action == ACTION_SIGN_IN and not email and not password:
            return {}, None, None

        if not email or not password:
            return None, "incomplete_cloud_auth", None

        cloud_client = MoonsideCloudClient(
            async_get_clientsession(self.hass),
            email,
            password,
        )

        try:
            if action == ACTION_CREATE_ACCOUNT:
                await cloud_client.async_create_account()
            else:
                await cloud_client.async_fetch_devices()
        except MoonsideCloudAuthError as err:
            return None, _map_cloud_auth_error(str(err)), None
        except MoonsideCloudError:
            return None, "cannot_connect", None

        return {
            CONF_CLOUD_EMAIL: email,
            CONF_CLOUD_PASSWORD: password,
            CONF_CLOUD_DEVICE_ID: device_id,
            CONF_CLOUD_WRITE_GRACE_SECONDS: grace_seconds,
        }, None, (
            "Cloud account created. Use the Moonside app to bind devices if needed."
            if action == ACTION_CREATE_ACCOUNT
            else None
        )

    async def _async_step_cloud(
        self,
        entry_data: dict[str, Any],
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Collect optional cloud credentials before creating the entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._cloud_status_message = ""
            cloud_options, error, status_message = await self._async_validate_cloud_input(
                user_input
            )
            if error is None:
                if cloud_options is None:
                    self._cloud_status_message = status_message or ""
                    return self.async_show_form(
                        step_id="cloud",
                        description_placeholders=self._get_cloud_description_placeholders(),
                        data_schema=self._build_cloud_schema(defaults=user_input),
                    )
                return self.async_create_entry(
                    title=entry_data[CONF_NAME],
                    data=entry_data,
                    options=cloud_options,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="cloud",
            description_placeholders=self._get_cloud_description_placeholders(),
            data_schema=self._build_cloud_schema(defaults=user_input),
            errors=errors,
        )

    async def _async_collect_discovered_devices(self) -> None:
        """Populate discovered Moonside devices from HA cache, then active scan."""
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
                "Found Moonside device during cached scan: %s (%s)",
                discovery_info.name,
                address,
            )
            self._discovered_devices[address] = discovery_info

        if self._discovered_devices:
            return

        for address, name in await discover_devices(self.hass, timeout=3.0):
            if address in current_addresses:
                continue

            LOGGER.debug(
                "Found Moonside device during active scan: %s (%s)",
                name,
                address,
            )
            self._discovered_devices[address] = SimpleNamespace(
                address=address,
                name=name,
            )

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
            self._entry_data = {
                CONF_MAC: discovery_info.address,
                CONF_NAME: user_input.get(CONF_NAME, default_name),
            }
            if discovery_info.name:
                self._entry_data[CONF_BLE_NAME] = discovery_info.name

            return await self._async_step_cloud(self._entry_data)

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
            self._entry_data = {
                CONF_MAC: address,
                CONF_NAME: user_input.get(CONF_NAME, default_name),
            }
            if discovery_info.name:
                self._entry_data[CONF_BLE_NAME] = discovery_info.name

            return await self._async_step_cloud(self._entry_data)

        await self._async_collect_discovered_devices()

        if not self._discovered_devices:
            return await self.async_step_manual()

        mac_addresses = {
            address: info.name for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            description_placeholders={
                "identifier_type": "Bluetooth device identifier",
            },
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
            mac_address = user_input[CONF_DEVICE_IDENTIFIER].strip()

            if not _is_valid_manual_identifier(mac_address):
                errors["base"] = "invalid_identifier"
            else:
                await self.async_set_unique_id(mac_address)
                self._abort_if_unique_id_configured()

                self._entry_data = {
                    CONF_MAC: mac_address,
                    CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                }
                return await self._async_step_cloud(self._entry_data)

        return self.async_show_form(
            step_id="manual",
            description_placeholders={
                "identifier_type": "Bluetooth device identifier",
            },
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_IDENTIFIER): str,
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
        self._cloud_status_message = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        options_data = dict(self._config_entry.data)
        options_data.update(self._config_entry.options)

        if user_input is not None:
            self._cloud_status_message = ""
            cloud_options, error, status_message = (
                await MoonsideConfigFlow._async_validate_cloud_input(self, user_input)
            )
            if error is None:
                if cloud_options is None:
                    self._cloud_status_message = status_message or ""
                    return self.async_show_form(
                        step_id="init",
                        description_placeholders={
                            "status_message": self._cloud_status_message
                        },
                        data_schema=MoonsideConfigFlow._build_cloud_schema(
                            self,
                            defaults=user_input,
                            options_data=options_data,
                        ),
                    )
                return self.async_create_entry(title="", data=cloud_options)
            errors["base"] = error

        return self.async_show_form(
            step_id="init",
            description_placeholders={"status_message": self._cloud_status_message},
            data_schema=MoonsideConfigFlow._build_cloud_schema(
                self,
                defaults=user_input,
                options_data=options_data,
            ),
            errors=errors,
        )


def _map_cloud_auth_error(details: str) -> str:
    """Map Firebase error payloads to config-flow error keys."""
    normalized = details.strip().upper()
    if "EMAIL_EXISTS" in normalized or "EMAIL-ALREADY-IN-USE" in normalized:
        return "email_already_exists"
    if "EMAIL_NOT_FOUND" in normalized:
        return "email_not_found"
    if "INVALID_LOGIN_CREDENTIALS" in normalized or "INVALID_PASSWORD" in normalized:
        return "invalid_auth"
    if "INVALID_EMAIL" in normalized:
        return "invalid_email"
    return "invalid_auth"
