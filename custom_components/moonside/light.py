"""Platform for light integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    get_effect_display_name,
    get_effect_key_from_name,
    get_effect_list,
)
from .moonside import MoonsideInstance

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Moonside light platform."""
    instance = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        [
            MoonsideLight(
                instance,
                config_entry.data.get("name", "Moonside Light"),
                config_entry.entry_id,
            )
        ]
    )


class MoonsideLight(RestoreEntity, LightEntity):
    """Representation of a Moonside light."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        instance: MoonsideInstance,
        name: str,
        entry_id: str,
    ) -> None:
        """Initialize the light."""
        self._instance = instance
        self._entry_id = entry_id
        self._attr_unique_id = instance.address

        # Supported features
        self._attr_supported_color_modes = {ColorMode.RGB}
        self._attr_supported_features = LightEntityFeature.EFFECT
        self._attr_color_mode = ColorMode.RGB
        self._attr_effect_list = get_effect_list()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._instance.available

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._instance.is_on

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        return self._instance.brightness

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color value."""
        return self._instance.rgb_color

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        if self._instance.effect:
            return get_effect_display_name(self._instance.effect)
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._instance.address)},
            name=self._instance.name,
            manufacturer="Moonside",
            model=self._instance.model,
        )

    @property
    def should_poll(self) -> bool:
        """Return the polling state."""
        return True

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to Home Assistant."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            LOGGER.debug(
                "Restoring state for %s: %s", self._instance.name, last_state.state
            )

            # Restore on/off state
            if last_state.state == "on":
                self._instance._is_on = True
            elif last_state.state == "off":
                self._instance._is_on = False

            # Restore brightness
            if ATTR_BRIGHTNESS in last_state.attributes:
                self._instance._brightness = last_state.attributes[ATTR_BRIGHTNESS]

            # Restore RGB color
            if ATTR_RGB_COLOR in last_state.attributes:
                self._instance._rgb_color = tuple(last_state.attributes[ATTR_RGB_COLOR])

            # Restore effect
            if ATTR_EFFECT in last_state.attributes:
                effect_name = last_state.attributes[ATTR_EFFECT]
                self._instance._effect = get_effect_key_from_name(effect_name)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        LOGGER.debug("Turn on called with kwargs: %s", kwargs)

        # Handle brightness
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._instance.brightness)

        # Handle effect
        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            effect_key = get_effect_key_from_name(effect_name)

            if effect_key:
                if not self._instance.is_on:
                    await self._instance.turn_on()
                await self._instance.set_effect(effect_key)
                self.async_write_ha_state()
                return

        # Handle RGB color
        if ATTR_RGB_COLOR in kwargs:
            rgb_color = kwargs[ATTR_RGB_COLOR]

            if not self._instance.is_on:
                await self._instance.turn_on()

            await self._instance.set_color(rgb_color)

            if brightness != self._instance.brightness:
                await self._instance.set_brightness(brightness)

            self.async_write_ha_state()
            return

        # Handle brightness only
        if ATTR_BRIGHTNESS in kwargs:
            if not self._instance.is_on:
                await self._instance.turn_on()
            await self._instance.set_brightness(brightness)
            self.async_write_ha_state()
            return

        # Just turn on
        if not self._instance.is_on:
            await self._instance.turn_on()
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        LOGGER.debug("Turn off called")
        await self._instance.turn_off()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity."""
        await self._instance.update()
