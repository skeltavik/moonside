"""The Moonside integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_MAC,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import CONF_BLE_NAME, CONF_NAME, DEFAULT_NAME, DOMAIN
from .moonside import MoonsideInstance

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SENSOR,
]

SERVICE_SET_PIXEL = "set_pixel"
SERVICE_PULSE = "pulse"
SERVICE_STROBE = "strobe"
SERVICE_COLOR_CYCLE = "color_cycle"

SET_PIXEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required("pixel_id"): vol.All(vol.Coerce(int), vol.Range(min=0, max=89)),
        vol.Required("brightness"): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
    }
)

PULSE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional("duration", default=0.5): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=5.0)
        ),
    }
)

STROBE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional("count", default=3): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=10)
        ),
        vol.Optional("duration", default=0.2): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=1.0)
        ),
    }
)

COLOR_CYCLE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required("colors"): cv.string,
        vol.Optional("duration", default=2.0): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=10.0)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Moonside from a config entry."""
    mac_address = entry.data[CONF_MAC]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    ble_name = entry.data.get(CONF_BLE_NAME)

    LOGGER.debug("Setting up Moonside device: %s (%s)", name, mac_address)

    instance = MoonsideInstance(mac_address, name, hass, ble_name=ble_name)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = instance

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _async_stop(event: Event) -> None:
        """Handle Home Assistant stop event."""
        await instance.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    # Register services only once
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PIXEL):

        async def async_handle_set_pixel(call: ServiceCall) -> None:
            entity_ids = call.data[ATTR_ENTITY_ID]
            pixel_id = call.data["pixel_id"]
            brightness = call.data["brightness"]

            for entry_id, instance in hass.data[DOMAIN].items():
                from homeassistant.helpers import entity_registry as er

                ent_reg = er.async_get(hass)
                entity_entries = [
                    entry
                    for entry in ent_reg.entities.values()
                    if entry.config_entry_id == entry_id
                    and entry.entity_id in entity_ids
                ]

                if entity_entries:
                    await instance.set_pixel(pixel_id, brightness)
                    await instance.apply_pixels()
                    LOGGER.debug(
                        "Set pixel %d to brightness %d for %s",
                        pixel_id,
                        brightness,
                        instance.name,
                    )
                    break

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PIXEL,
            async_handle_set_pixel,
            schema=SET_PIXEL_SCHEMA,
        )

        async def async_handle_pulse(call: ServiceCall) -> None:
            entity_ids = call.data[ATTR_ENTITY_ID]
            duration = call.data["duration"]

            for entry_id, instance in hass.data[DOMAIN].items():
                from homeassistant.helpers import entity_registry as er

                ent_reg = er.async_get(hass)
                entity_entries = [
                    entry
                    for entry in ent_reg.entities.values()
                    if entry.config_entry_id == entry_id
                    and entry.entity_id in entity_ids
                ]

                if entity_entries:
                    await instance.pulse(duration)
                    LOGGER.debug("Pulse executed for %s", instance.name)
                    break

        hass.services.async_register(
            DOMAIN,
            SERVICE_PULSE,
            async_handle_pulse,
            schema=PULSE_SCHEMA,
        )

        async def async_handle_strobe(call: ServiceCall) -> None:
            entity_ids = call.data[ATTR_ENTITY_ID]
            count = call.data["count"]
            duration = call.data["duration"]

            for entry_id, instance in hass.data[DOMAIN].items():
                from homeassistant.helpers import entity_registry as er

                ent_reg = er.async_get(hass)
                entity_entries = [
                    entry
                    for entry in ent_reg.entities.values()
                    if entry.config_entry_id == entry_id
                    and entry.entity_id in entity_ids
                ]

                if entity_entries:
                    await instance.strobe(count, duration)
                    LOGGER.debug("Strobe executed for %s", instance.name)
                    break

        hass.services.async_register(
            DOMAIN,
            SERVICE_STROBE,
            async_handle_strobe,
            schema=STROBE_SCHEMA,
        )

        async def async_handle_color_cycle(call: ServiceCall) -> None:
            entity_ids = call.data[ATTR_ENTITY_ID]
            colors_str = call.data["colors"]
            duration = call.data["duration"]

            import json

            try:
                colors = json.loads(colors_str)
                if not isinstance(colors, list):
                    LOGGER.error("Colors must be a list of RGB tuples")
                    return
                colors = [tuple(c) for c in colors]
            except json.JSONDecodeError:
                LOGGER.error("Invalid colors format: %s", colors_str)
                return

            for entry_id, instance in hass.data[DOMAIN].items():
                from homeassistant.helpers import entity_registry as er

                ent_reg = er.async_get(hass)
                entity_entries = [
                    entry
                    for entry in ent_reg.entities.values()
                    if entry.config_entry_id == entry_id
                    and entry.entity_id in entity_ids
                ]

                if entity_entries:
                    await instance.color_cycle(colors, duration)
                    LOGGER.debug("Color cycle executed for %s", instance.name)
                    break

        hass.services.async_register(
            DOMAIN,
            SERVICE_COLOR_CYCLE,
            async_handle_color_cycle,
            schema=COLOR_CYCLE_SCHEMA,
        )

    LOGGER.debug("Moonside device setup complete: %s", name)
    return True


def _is_device_ble_name(value: str | None) -> bool:
    """Return whether a stored BLE name looks like a real Moonside device name."""
    return bool(value and value.upper().startswith("MOONSIDE"))


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the latest version."""
    if entry.version >= 2:
        return True

    LOGGER.debug(
        "Migrating Moonside config entry %s from version %s",
        entry.entry_id,
        entry.version,
    )

    data: dict[str, Any] = dict(entry.data)
    ble_name = data.get(CONF_BLE_NAME)

    if not _is_device_ble_name(ble_name):
        data.pop(CONF_BLE_NAME, None)

    hass.config_entries.async_update_entry(entry, data=data, version=2)

    LOGGER.debug(
        "Migration of Moonside config entry %s to version 2 successful", entry.entry_id
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.debug("Unloading Moonside device: %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        instance = hass.data[DOMAIN][entry.entry_id]
        await instance.stop()
        hass.data[DOMAIN].pop(entry.entry_id)

    # Unregister services if no more entries
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_SET_PIXEL)
        hass.services.async_remove(DOMAIN, SERVICE_PULSE)
        hass.services.async_remove(DOMAIN, SERVICE_STROBE)
        hass.services.async_remove(DOMAIN, SERVICE_COLOR_CYCLE)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry."""
    LOGGER.debug("Removing Moonside device: %s", entry.entry_id)
