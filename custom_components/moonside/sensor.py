"""Sensor platform for Moonside integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .moonside import MoonsideInstance

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Moonside sensor platform."""
    instance = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        MoonsideRssiSensor(instance, config_entry.entry_id),
        MoonsideConnectionSensor(instance, config_entry.entry_id),
        MoonsideLastUpdateSensor(instance, config_entry.entry_id),
    ]

    async_add_entities(entities)


class MoonsideSensorBase(SensorEntity):
    """Base class for Moonside sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        instance: MoonsideInstance,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        self._instance = instance
        self._entry_id = entry_id

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
    def available(self) -> bool:
        """Keep diagnostics visible even when the lamp is unreachable."""
        return True

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        self._instance.register_state_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from Home Assistant."""
        self._instance.unregister_state_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()


class MoonsideRssiSensor(MoonsideSensorBase):
    """Representation of Moonside RSSI sensor."""

    _attr_name = "Signal Strength"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_icon = "mdi:signal-variant"

    def __init__(
        self,
        instance: MoonsideInstance,
        entry_id: str,
    ) -> None:
        """Initialize the RSSI sensor."""
        super().__init__(instance, entry_id)
        self._attr_unique_id = f"{instance.address}_rssi"

    @property
    def native_value(self) -> int | None:
        """Return the RSSI value."""
        return self._instance.rssi

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "device_identifier": self._instance.address,
        }


class MoonsideConnectionSensor(MoonsideSensorBase):
    """Representation of Moonside connection status sensor."""

    _attr_name = "Connection Status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(
        self,
        instance: MoonsideInstance,
        entry_id: str,
    ) -> None:
        """Initialize the connection sensor."""
        super().__init__(instance, entry_id)
        self._attr_unique_id = f"{instance.address}_connection"

    @property
    def native_value(self) -> str:
        """Return the connection status."""
        if self._instance.available:
            return "connected"
        return "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "device_identifier": self._instance.address,
            "last_connected": self._instance.last_connected.isoformat()
            if self._instance.last_connected
            else None,
        }


class MoonsideLastUpdateSensor(MoonsideSensorBase):
    """Representation of Moonside last update sensor."""

    _attr_name = "Last Update"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        instance: MoonsideInstance,
        entry_id: str,
    ) -> None:
        """Initialize the last update sensor."""
        super().__init__(instance, entry_id)
        self._attr_unique_id = f"{instance.address}_last_update"

    @property
    def native_value(self) -> datetime | None:
        """Return the last update timestamp."""
        return self._instance.last_update
