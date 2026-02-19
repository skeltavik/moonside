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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_NAME, DEFAULT_NAME
from .moonside import MoonsideInstance

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
]

SERVICE_SET_PIXEL = "set_pixel"

SET_PIXEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required("pixel_id"): vol.All(vol.Coerce(int), vol.Range(min=0, max=89)),
        vol.Required("brightness"): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Moonside from a config entry."""
    mac_address = entry.data[CONF_MAC]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    LOGGER.debug("Setting up Moonside device: %s (%s)", name, mac_address)

    instance = MoonsideInstance(mac_address, name)

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
            """Handle the set_pixel service call."""
            entity_ids = call.data[ATTR_ENTITY_ID]
            pixel_id = call.data["pixel_id"]
            brightness = call.data["brightness"]

            # Find the instance for the given entity
            for entry_id, instance in hass.data[DOMAIN].items():
                # Get the entity registry to find entity IDs
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

    LOGGER.debug("Moonside device setup complete: %s", name)
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

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry."""
    LOGGER.debug("Removing Moonside device: %s", entry.entry_id)
