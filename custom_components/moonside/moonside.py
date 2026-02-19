"""Moonside BLE communication module."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from bleak import BleakClient, BleakScanner
from homeassistant.core import HomeAssistant
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS, establish_connection

from .const import (
    CMD_COLOR,
    CMD_LED_OFF,
    CMD_LED_ON,
    CMD_BRIGHTNESS,
    CMD_PIXEL,
    CMD_MODE_PIXEL,
    UART_SERVICE_UUID,
    UART_RX_CHAR_UUID,
    UART_TX_CHAR_UUID,
    MAX_BRIGHTNESS,
    NUM_PIXELS,
    get_theme_command,
)

LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 30
DISCONNECT_TIMEOUT = 5
COMMAND_TIMEOUT = 10

SERVICE_PULSE = "pulse"
SERVICE_STROBE = "strobe"
SERVICE_COLOR_CYCLE = "color_cycle"


class MoonsideInstance:
    """Moonside BLE device instance."""

    def __init__(
        self,
        mac_address: str,
        name: str,
    ) -> None:
        """Initialize the Moonside instance.

        Args:
            mac_address: BLE MAC address of the device
            name: Name of the device
        """
        self._mac = mac_address
        self._name = name
        self._client: BleakClient | None = None
        self._connected = False

        # Device state
        self._is_on: bool | None = None
        self._brightness: int = 255  # 0-255 (mapped to 0-120 for device)
        self._rgb_color: tuple[int, int, int] = (255, 255, 255)
        self._effect: str | None = None

        self._rssi: int | None = None
        self._last_connected: datetime | None = None
        self._last_update: datetime | None = None

        self._lock = asyncio.Lock()

    @property
    def address(self) -> str:
        """Return the MAC address."""
        return self._mac

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._name

    @property
    def is_on(self) -> bool | None:
        """Return True if the light is on."""
        return self._is_on

    @property
    def brightness(self) -> int:
        """Return current brightness (0-255)."""
        return self._brightness

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return current RGB color."""
        return self._rgb_color

    @property
    def effect(self) -> str | None:
        return self._effect

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def rssi(self) -> int | None:
        return self._rssi

    @property
    def last_connected(self) -> datetime | None:
        return self._last_connected

    @property
    def last_update(self) -> datetime | None:
        return self._last_update

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return self._is_on is not None

    def _convert_brightness_to_device(self, brightness: int) -> int:
        """Convert Home Assistant brightness (0-255) to device brightness (0-120)."""
        return int((brightness / 255) * MAX_BRIGHTNESS)

    def _convert_brightness_from_device(self, brightness: int) -> int:
        """Convert device brightness (0-120) to Home Assistant brightness (0-255)."""
        return int((brightness / MAX_BRIGHTNESS) * 255)

    async def _ensure_connected(self) -> bool:
        """Ensure connection to the device."""
        if self._client and self._client.is_connected:
            return True

        try:
            LOGGER.debug("Connecting to %s (%s)", self._name, self._mac)

            self._client = await establish_connection(
                BleakClient,
                self._mac,
                self._name,
                max_attempts=3,
            )

            self._connected = True
            LOGGER.debug("Connected to %s", self._name)
            return True

        except Exception as ex:
            LOGGER.error("Failed to connect to %s: %s", self._name, ex)
            self._connected = False
            return False

    async def _send_command(self, command: str) -> bool:
        """Send a command to the device.

        Args:
            command: Command string to send

        Returns:
            True if command was sent successfully
        """
        async with self._lock:
            if not await self._ensure_connected():
                return False

            try:
                # Get the RX characteristic
                service = self._client.services.get_service(UART_SERVICE_UUID)
                if not service:
                    LOGGER.error("UART service not found")
                    return False

                rx_char = service.get_characteristic(UART_RX_CHAR_UUID)
                if not rx_char:
                    LOGGER.error("UART RX characteristic not found")
                    return False

                # Encode and send command
                data = command.encode("utf-8")
                LOGGER.debug("Sending command: %s", command)

                await self._client.write_gatt_char(rx_char, data, response=False)

                # Small delay to ensure command is processed
                await asyncio.sleep(0.1)

                return True

            except BLEAK_RETRY_EXCEPTIONS as ex:
                LOGGER.debug("BLE error sending command: %s", ex)
                self._connected = False
                return False
            except Exception as ex:
                LOGGER.error("Error sending command: %s", ex)
                self._connected = False
                return False

    async def turn_on(self) -> bool:
        """Turn on the light."""
        if await self._send_command(CMD_LED_ON):
            self._is_on = True
            return True
        return False

    async def turn_off(self) -> bool:
        """Turn off the light."""
        if await self._send_command(CMD_LED_OFF):
            self._is_on = False
            return True
        return False

    async def set_brightness(self, brightness: int) -> bool:
        """Set brightness (0-255).

        Args:
            brightness: Brightness value (0-255)
        """
        device_brightness = self._convert_brightness_to_device(brightness)
        command = f"{CMD_BRIGHTNESS}{device_brightness:03d}"

        if await self._send_command(command):
            self._brightness = brightness
            return True
        return False

    async def set_color(
        self, rgb_color: tuple[int, int, int], brightness: int | None = None
    ) -> bool:
        """Set RGB color.

        Args:
            rgb_color: RGB tuple (0-255, 0-255, 0-255)
            brightness: Optional brightness override (0-255)
        """
        r, g, b = rgb_color
        command = f"{CMD_COLOR}{r:03d}{g:03d}{b:03d}"

        if await self._send_command(command):
            self._rgb_color = rgb_color
            self._effect = None

            target_brightness = (
                brightness if brightness is not None else self._brightness
            )
            await self.set_brightness(target_brightness)

            return True
        return False

    async def set_effect(self, effect_key: str) -> bool:
        """Set effect/theme.

        Args:
            effect_key: Effect key from THEMES dict
        """
        command = get_theme_command(effect_key)
        if not command:
            LOGGER.error("Unknown effect: %s", effect_key)
            return False

        if await self._send_command(command):
            self._effect = effect_key
            return True
        return False

    async def set_pixel(self, pixel_id: int, brightness: int) -> bool:
        """Set individual pixel brightness.

        Args:
            pixel_id: Pixel ID (0-89)
            brightness: Brightness value (0-120)
        """
        if pixel_id < 0 or pixel_id >= NUM_PIXELS:
            LOGGER.error("Invalid pixel ID: %d", pixel_id)
            return False

        if brightness < 0 or brightness > MAX_BRIGHTNESS:
            LOGGER.error("Invalid brightness: %d", brightness)
            return False

        command = f"{CMD_PIXEL},{pixel_id},{brightness}"
        return await self._send_command(command)

    async def apply_pixels(self) -> bool:
        return await self._send_command(CMD_MODE_PIXEL)

    async def update(self) -> bool:
        async with self._lock:
            if not await self._ensure_connected():
                return False
            self._last_update = datetime.now()
            return True

    async def pulse(self, duration: float = 0.5) -> bool:
        if not await self._send_command(CMD_LED_ON):
            return False
        await asyncio.sleep(duration)
        if not await self._send_command(CMD_LED_OFF):
            return False
        return True

    async def strobe(self, count: int = 3, duration: float = 0.2) -> bool:
        for _ in range(count):
            if not await self._send_command(CMD_LED_ON):
                return False
            await asyncio.sleep(duration)
            if not await self._send_command(CMD_LED_OFF):
                return False
            await asyncio.sleep(duration)
        return True

    async def color_cycle(
        self, colors: list[tuple[int, int, int]], duration: float = 2.0
    ) -> bool:
        delay = duration / len(colors)
        for color in colors:
            if not await self.set_color(color):
                return False
            await asyncio.sleep(delay)
        return True

    async def stop(self) -> None:
        async with self._lock:
            if self._client and self._client.is_connected:
                try:
                    await self._client.disconnect()
                except Exception as ex:
                    LOGGER.debug("Error disconnecting: %s", ex)
            self._connected = False
            self._client = None


async def discover_devices(
    hass: HomeAssistant,
    timeout: float = 10.0,
) -> list[tuple[str, str]]:
    """Discover Moonside devices via Bluetooth.

    Args:
        hass: Home Assistant instance
        timeout: Scan timeout in seconds

    Returns:
        List of tuples (mac_address, device_name)
    """
    devices_found: list[tuple[str, str]] = []

    def device_found(
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> None:
        """Handle discovered device."""
        name = advertisement_data.local_name or device.name
        if name and name.startswith("MOONSIDE"):
            LOGGER.debug("Found Moonside device: %s (%s)", device.address, name)
            devices_found.append((device.address, name))

    try:
        LOGGER.debug("Starting Bluetooth scan for Moonside devices...")
        scanner = BleakScanner(
            detection_callback=device_found,
            service_uuids=[UART_SERVICE_UUID],
        )
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        LOGGER.debug("Scan complete. Found %d devices", len(devices_found))
    except Exception as ex:
        LOGGER.error("Error during device discovery: %s", ex)

    return devices_found
