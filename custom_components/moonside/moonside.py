"""Moonside BLE communication module."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

from bleak import BleakClient, BleakScanner
from homeassistant.components.bluetooth import (
    MONOTONIC_TIME,
    async_ble_device_from_address,
    async_last_service_info,
)
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
    MAX_BRIGHTNESS,
    NUM_PIXELS,
    get_theme_command,
)

LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 30
DISCONNECT_TIMEOUT = 5
COMMAND_TIMEOUT = 10
ADVERTISEMENT_GRACE_PERIOD = timedelta(minutes=5)
ADVERTISEMENT_GRACE_PERIOD_SECONDS = ADVERTISEMENT_GRACE_PERIOD.total_seconds()

SERVICE_PULSE = "pulse"
SERVICE_STROBE = "strobe"
SERVICE_COLOR_CYCLE = "color_cycle"


def get_display_name_from_ble_name(ble_name: str | None) -> str:
    """Return a human-readable display name for a BLE-advertised name."""
    normalized_name = ble_name.upper() if ble_name else ""

    # User-confirmed mapping: MOONSIDE-O101 / HALO names are Halo Lamp devices.
    if "O101" in normalized_name or "HALO" in normalized_name:
        return "Halo Lamp"
    # Issue-tracker-confirmed mapping: users reported model L1 as Lamp One.
    if "L1" in normalized_name:
        return "Lamp One"
    # Public product naming supports "Neon Lighthouse", but BLE-name matching
    # for this branch is still inferred from the advertised name.
    if "LIGHTHOUSE" in normalized_name:
        return "Neon Lighthouse"
    # Other Neon-family products exist, so this remains a broad best-effort label
    # rather than a verified single-device mapping.
    if "NEON" in normalized_name:
        return "Moonside Neon"
    # Unknown identifiers stay generic until a concrete product mapping is verified.
    return "Moonside"


class MoonsideInstance:
    """Moonside BLE device instance."""

    def __init__(
        self,
        mac_address: str,
        name: str,
        hass: HomeAssistant | None = None,
        ble_name: str | None = None,
    ) -> None:
        """Initialize the Moonside instance.

        Args:
            mac_address: Stored BLE identifier of the device
            name: Display name of the device
            hass: Home Assistant instance (used for RSSI lookups)
            ble_name: Bluetooth advertised name used for metadata only
        """
        self._mac = mac_address
        self._name = name
        self._hass = hass
        self._ble_name = ble_name
        self._client: BleakClient | None = None
        self._connected = False

        # Device state
        self._is_on: bool | None = None
        self._power_state_known = False
        self._brightness: int = 255  # 0-255 (mapped to 0-120 for device)
        self._rgb_color: tuple[int, int, int] = (255, 255, 255)
        self._effect: str | None = None

        self._rssi: int | None = None
        self._last_seen_monotonic: float | None = None
        self._last_connected: datetime | None = None
        self._last_update: datetime | None = None
        self._state_listeners: set[Callable[[], None]] = set()

        self._lock = asyncio.Lock()

    def register_state_listener(self, listener: Callable[[], None]) -> None:
        """Register an entity state listener."""
        self._state_listeners.add(listener)

    def unregister_state_listener(self, listener: Callable[[], None]) -> None:
        """Unregister an entity state listener."""
        self._state_listeners.discard(listener)

    def _notify_state_listeners(self) -> None:
        """Notify subscribed entities that shared state changed."""
        for listener in tuple(self._state_listeners):
            listener()

    @property
    def address(self) -> str:
        """Return the stored BLE identifier."""
        return self._mac

    @property
    def ble_name(self) -> str | None:
        """Return the Bluetooth advertised name."""
        return self._ble_name

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._name

    @property
    def is_on(self) -> bool | None:
        """Return True if the light is on."""
        if not self._power_state_known:
            return None
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
        if self._connected:
            return True

        if self._last_seen_monotonic is None:
            return False

        return (
            MONOTONIC_TIME() - self._last_seen_monotonic
            <= ADVERTISEMENT_GRACE_PERIOD_SECONDS
        )

    @property
    def model(self) -> str:
        """Return the device model based on BLE name."""
        return get_display_name_from_ble_name(self._ble_name)

    def _update_advertisement_state(self) -> bool:
        """Refresh cached Bluetooth advertisement data."""
        if not self._hass:
            return False

        for connectable in (True, False):
            service_info = async_last_service_info(
                self._hass, self._mac, connectable=connectable
            )
            if not service_info:
                continue

            monotonic_age = MONOTONIC_TIME() - service_info.time
            if monotonic_age > ADVERTISEMENT_GRACE_PERIOD_SECONDS:
                continue

            self._rssi = service_info.rssi
            self._last_seen_monotonic = service_info.time
            return True

        return False

    def _convert_brightness_to_device(self, brightness: int) -> int:
        """Convert Home Assistant brightness (0-255) to device brightness (0-120)."""
        return int((brightness / 255) * MAX_BRIGHTNESS)

    def _convert_brightness_from_device(self, brightness: int) -> int:
        """Convert device brightness (0-120) to Home Assistant brightness (0-255)."""
        return int((brightness / MAX_BRIGHTNESS) * 255)

    async def _ensure_connected(self) -> bool:
        """Ensure connection to the device."""
        if self._client and self._client.is_connected:
            self._connected = True
            return True

        self._update_advertisement_state()

        try:
            LOGGER.debug("Connecting to %s (%s)", self._name, self._mac)
            ble_device = None
            if self._hass:
                ble_device = async_ble_device_from_address(
                    self._hass, self._mac, connectable=True
                )

            self._client = await establish_connection(
                BleakClient,
                ble_device or self._mac,
                self._name,
                max_attempts=3,
            )

            self._connected = True
            self._last_connected = datetime.now()
            LOGGER.debug("Connected to %s", self._name)
            return True

        except Exception as ex:
            LOGGER.error("Failed to connect to %s: %s", self._name, ex)
            self._connected = False
            self._is_on = None
            self._power_state_known = False
            self._last_update = None
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
                self._is_on = None
                self._power_state_known = False
                self._last_update = None
                self._notify_state_listeners()
                return False

            try:
                # Get the RX characteristic
                service = self._client.services.get_service(UART_SERVICE_UUID)
                if not service:
                    LOGGER.error("UART service not found")
                    self._connected = False
                    self._is_on = None
                    self._power_state_known = False
                    self._last_update = None
                    self._notify_state_listeners()
                    return False

                rx_char = service.get_characteristic(UART_RX_CHAR_UUID)
                if not rx_char:
                    LOGGER.error("UART RX characteristic not found")
                    self._connected = False
                    self._is_on = None
                    self._power_state_known = False
                    self._last_update = None
                    self._notify_state_listeners()
                    return False

                # Encode and send command
                data = command.encode("utf-8")
                LOGGER.debug("Sending command: %s", command)

                await self._client.write_gatt_char(rx_char, data, response=True)

                # Small delay to ensure command is processed
                await asyncio.sleep(0.1)
                self._last_update = datetime.now()
                self._notify_state_listeners()

                return True

            except BLEAK_RETRY_EXCEPTIONS as ex:
                LOGGER.debug("BLE error sending command: %s", ex)
                self._connected = False
                self._is_on = None
                self._power_state_known = False
                self._last_update = None
                self._notify_state_listeners()
                return False
            except Exception as ex:
                LOGGER.error("Error sending command: %s", ex)
                self._connected = False
                self._is_on = None
                self._power_state_known = False
                self._last_update = None
                self._notify_state_listeners()
                return False

    async def turn_on(self) -> bool:
        """Turn on the light."""
        if await self._send_command(CMD_LED_ON):
            self._is_on = True
            self._power_state_known = True
            self._notify_state_listeners()
            return True
        return False

    async def turn_off(self) -> bool:
        """Turn off the light."""
        if await self._send_command(CMD_LED_OFF):
            self._is_on = False
            self._power_state_known = True
            self._notify_state_listeners()
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
            self._notify_state_listeners()
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
            self._notify_state_listeners()

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
            self._notify_state_listeners()
            return True
        return False

    async def set_pixel(self, pixel_id: int, brightness: int) -> bool:
        """Set individual pixel brightness (Neon Lighthouse only).

        Args:
            pixel_id: Pixel ID (0-89)
            brightness: Brightness value (0-120)
        """
        if self.model != "Neon Lighthouse":
            LOGGER.warning(
                "set_pixel is only supported on Neon Lighthouse devices (device is %s)",
                self.model,
            )
            return False

        if pixel_id < 0 or pixel_id >= NUM_PIXELS:
            LOGGER.error("Invalid pixel ID: %d", pixel_id)
            return False

        if brightness < 0 or brightness > MAX_BRIGHTNESS:
            LOGGER.error("Invalid brightness: %d", brightness)
            return False

        command = f"{CMD_PIXEL},{pixel_id},{brightness}"
        return await self._send_command(command)

    async def apply_pixels(self) -> bool:
        """Apply pixel settings (Neon Lighthouse only)."""
        if self.model != "Neon Lighthouse":
            LOGGER.warning(
                "apply_pixels is only supported on Neon Lighthouse devices (device is %s)",
                self.model,
            )
            return False
        return await self._send_command(CMD_MODE_PIXEL)

    async def update(self) -> bool:
        """Update device state by attempting connection.

        Returns:
            True if device is connected and responsive
        """
        async with self._lock:
            seen_recently = self._update_advertisement_state()

            if not await self._ensure_connected():
                self._is_on = None
                self._power_state_known = False
                self._last_update = None
                self._notify_state_listeners()
                return seen_recently

            # Try to read the service to verify device is responsive
            try:
                service = self._client.services.get_service(UART_SERVICE_UUID)
                if not service:
                    LOGGER.debug("UART service not available during update")
                    self._connected = False
                    self._is_on = None
                    self._power_state_known = False
                    self._last_update = None
                    self._notify_state_listeners()
                    return seen_recently

                self._power_state_known = False
                self._last_update = datetime.now()
                self._last_connected = self._last_update
                self._notify_state_listeners()

                return True

            except Exception as ex:
                LOGGER.debug("Error during update: %s", ex)
                self._connected = False
                self._is_on = None
                self._power_state_known = False
                self._last_update = None
                self._notify_state_listeners()
                return seen_recently

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
        scanner = BleakScanner(detection_callback=device_found)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        LOGGER.debug("Scan complete. Found %d devices", len(devices_found))
    except Exception as ex:
        LOGGER.error("Error during device discovery: %s", ex)

    return devices_found
