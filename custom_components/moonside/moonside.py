"""Moonside BLE communication module."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS, establish_connection
from homeassistant.components.bluetooth import (
    MONOTONIC_TIME,
    async_ble_device_from_address,
    async_last_service_info,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import (
    MoonsideCloudAuthError,
    MoonsideCloudClient,
    MoonsideCloudError,
    infer_brightness,
    infer_effect,
    infer_power_state,
    infer_rgb_color,
)
from .const import (
    CMD_BRIGHTNESS,
    CMD_COLOR,
    CMD_LED_OFF,
    CMD_LED_ON,
    CMD_MODE_PIXEL,
    CMD_PIXEL,
    DEFAULT_CLOUD_WRITE_GRACE_SECONDS,
    MAX_BRIGHTNESS,
    NUM_PIXELS,
    UART_RX_CHAR_UUID,
    UART_SERVICE_UUID,
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
        cloud_email: str | None = None,
        cloud_password: str | None = None,
        cloud_device_id: str | None = None,
        cloud_write_grace_seconds: int = DEFAULT_CLOUD_WRITE_GRACE_SECONDS,
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
        self._cloud_email = cloud_email.strip() if cloud_email else None
        self._cloud_password = cloud_password if cloud_password else None
        self._cloud_device_id = cloud_device_id.strip() if cloud_device_id else None
        self._cloud_client: MoonsideCloudClient | None = None
        self._cloud_write_grace_period = timedelta(
            seconds=max(0, int(cloud_write_grace_seconds))
        )

        # Device state
        self._is_on: bool | None = None
        self._power_state_known = False
        self._power_state_source = "unknown"
        self._brightness: int = 255  # 0-255 (mapped to 0-120 for device)
        self._rgb_color: tuple[int, int, int] = (255, 255, 255)
        self._effect: str | None = None

        self._rssi: int | None = None
        self._last_seen_monotonic: float | None = None
        self._last_connected: datetime | None = None
        self._last_update: datetime | None = None
        self._local_write_grace_until: datetime | None = None
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
    def power_state_source(self) -> str:
        """Return the source for the current power-state view."""
        return self._power_state_source

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

    @property
    def cloud_enabled(self) -> bool:
        """Return whether cloud-backed state is configured."""
        return bool(self._cloud_email and self._cloud_password and self._hass)

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

    def _mark_local_write_pending(self) -> None:
        """Delay cloud reconciliation briefly after a successful local write."""
        self._local_write_grace_until = (
            datetime.now(UTC) + self._cloud_write_grace_period
        )

    def _ensure_cloud_client(self) -> MoonsideCloudClient | None:
        """Create the cloud client lazily when configured."""
        if not self.cloud_enabled:
            return None

        if self._cloud_client is None:
            self._cloud_client = MoonsideCloudClient(
                async_get_clientsession(self._hass),
                self._cloud_email,
                self._cloud_password,
            )

        return self._cloud_client

    async def _resolve_cloud_device_id(self) -> str | None:
        """Resolve the Moonside cloud device id for this entry."""
        if self._cloud_device_id:
            return self._cloud_device_id

        cloud_client = self._ensure_cloud_client()
        if cloud_client is None:
            return None

        devices = await cloud_client.async_fetch_devices()
        if not devices:
            return None

        if len(devices) == 1:
            self._cloud_device_id = next(iter(devices))
            return self._cloud_device_id

        preferred_names = {
            value.strip().casefold()
            for value in (self._name, self._ble_name, self.model)
            if isinstance(value, str) and value.strip()
        }

        matches = [
            device_id
            for device_id, state in devices.items()
            if str(state.get("deviceName", "")).strip().casefold() in preferred_names
            or str(state.get("deviceModel", "")).strip().casefold() in preferred_names
            or str(state.get("subModel", "")).strip().casefold() in preferred_names
        ]

        if len(matches) == 1:
            self._cloud_device_id = matches[0]
            return self._cloud_device_id

        return None

    def apply_cloud_state(self, device_state: dict[str, object]) -> None:
        """Apply normalized cloud state into the shared instance cache."""
        if (
            self._local_write_grace_until is not None
            and datetime.now(UTC) < self._local_write_grace_until
        ):
            self._last_update = datetime.now(UTC)
            return

        inferred_power = infer_power_state(device_state)
        if inferred_power is not None:
            self._is_on = inferred_power
            self._power_state_known = True
            self._power_state_source = "cloud"

        if (brightness := infer_brightness(device_state)) is not None:
            self._brightness = brightness

        if (rgb_color := infer_rgb_color(device_state)) is not None:
            self._rgb_color = rgb_color

        inferred_effect = infer_effect(device_state)
        if inferred_effect is not None:
            self._effect = inferred_effect
        elif str(device_state.get("controlData", "")).upper().startswith("COLOR"):
            self._effect = None

        self._last_update = datetime.now(UTC)

    async def _refresh_cloud_state(self) -> None:
        """Refresh authoritative state from the Moonside cloud when configured."""
        cloud_client = self._ensure_cloud_client()
        if cloud_client is None:
            return

        device_id = await self._resolve_cloud_device_id()
        if not device_id:
            LOGGER.debug("Unable to resolve Moonside cloud device for %s", self._name)
            return

        state = await cloud_client.async_get_device_state(device_id)
        self.apply_cloud_state(state)

    async def _disconnect_client(self) -> None:
        """Disconnect and clear the cached BLE client."""
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception as ex:  # noqa: BLE001 - cleanup must not escape
                LOGGER.debug("Error disconnecting: %s", ex)

        self._connected = False
        self._client = None

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
            self._last_connected = datetime.now(UTC)
            LOGGER.debug("Connected to %s", self._name)
            return True

        except Exception as ex:  # noqa: BLE001 - connector errors vary by backend
            LOGGER.error("Failed to connect to %s: %s", self._name, ex)
            self._connected = False
            return False

    async def _send_command(self, command: str) -> bool:
        """Send a single command to the device."""
        return await self._send_commands([(command, 0.1)])

    async def _send_commands(self, commands: list[tuple[str, float]]) -> bool:
        """Send a command sequence over one BLE connection."""
        async with self._lock:
            if not await self._ensure_connected():
                self._notify_state_listeners()
                return False

            commands_sent = 0
            try:
                # Get the RX characteristic
                client = self._client
                if client is None:
                    LOGGER.error("BLE client missing after connection")
                    self._connected = False
                    self._notify_state_listeners()
                    return False

                service = client.services.get_service(UART_SERVICE_UUID)
                if not service:
                    LOGGER.error("UART service not found")
                    self._connected = False
                    self._notify_state_listeners()
                    return False

                rx_char = service.get_characteristic(UART_RX_CHAR_UUID)
                if not rx_char:
                    LOGGER.error("UART RX characteristic not found")
                    self._connected = False
                    self._notify_state_listeners()
                    return False

                for command, delay_after in commands:
                    LOGGER.debug("Sending command: %s", command)
                    await client.write_gatt_char(
                        rx_char,
                        command.encode("utf-8"),
                        response=True,
                    )
                    commands_sent += 1
                    if delay_after > 0:
                        await asyncio.sleep(delay_after)

                self._last_update = datetime.now(UTC)
                self._notify_state_listeners()

                return True

            except asyncio.CancelledError:
                if commands_sent:
                    self._mark_partial_write_uncertain()
                self._notify_state_listeners()
                raise
            except BLEAK_RETRY_EXCEPTIONS as ex:
                LOGGER.debug("BLE error sending command: %s", ex)
                if commands_sent:
                    self._mark_partial_write_uncertain()
                self._notify_state_listeners()
                return False
            except Exception as ex:  # noqa: BLE001 - normalize unexpected BLE errors
                LOGGER.error("Error sending command: %s", ex)
                if commands_sent:
                    self._mark_partial_write_uncertain()
                self._notify_state_listeners()
                return False
            finally:
                await self._disconnect_client()

    def _mark_partial_write_uncertain(self) -> None:
        """Invalidate cached power state after a partially accepted command batch."""
        self._power_state_known = False
        self._power_state_source = "unknown"
        self._local_write_grace_until = None
        self._last_update = datetime.now(UTC)

    async def turn_on(self) -> bool:
        """Turn on the light."""
        if await self._send_command(CMD_LED_ON):
            self._is_on = True
            self._power_state_known = True
            self._power_state_source = "local"
            self._mark_local_write_pending()
            self._notify_state_listeners()
            return True
        return False

    async def turn_off(self) -> bool:
        """Turn off the light."""
        if await self._send_command(CMD_LED_OFF):
            self._is_on = False
            self._power_state_known = True
            self._power_state_source = "local"
            self._mark_local_write_pending()
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
            self._is_on = True
            self._power_state_known = True
            self._power_state_source = "local"
            self._mark_local_write_pending()
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
        color_command = f"{CMD_COLOR}{r:03d}{g:03d}{b:03d}"
        target_brightness = brightness if brightness is not None else self._brightness
        device_brightness = self._convert_brightness_to_device(target_brightness)
        brightness_command = f"{CMD_BRIGHTNESS}{device_brightness:03d}"

        if await self._send_commands([(color_command, 0.1), (brightness_command, 0.1)]):
            self._rgb_color = rgb_color
            self._brightness = target_brightness
            self._effect = None
            self._is_on = True
            self._power_state_known = True
            self._power_state_source = "local"
            self._mark_local_write_pending()
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
            self._is_on = True
            self._power_state_known = True
            self._power_state_source = "local"
            self._mark_local_write_pending()
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

    async def set_and_apply_pixel(self, pixel_id: int, brightness: int) -> bool:
        """Set and apply one pixel over a single BLE connection."""
        if self.model != "Neon Lighthouse":
            LOGGER.warning(
                "Pixel control is only supported on Neon Lighthouse devices (device is %s)",
                self.model,
            )
            return False
        if pixel_id < 0 or pixel_id >= NUM_PIXELS:
            LOGGER.error("Invalid pixel ID: %d", pixel_id)
            return False
        if brightness < 0 or brightness > MAX_BRIGHTNESS:
            LOGGER.error("Invalid brightness: %d", brightness)
            return False

        return await self._send_commands(
            [
                (f"{CMD_PIXEL},{pixel_id},{brightness}", 0.1),
                (CMD_MODE_PIXEL, 0),
            ]
        )

    async def update(self) -> bool:
        """Refresh device availability from Bluetooth advertisements.

        Returns:
            True if the device is recently reachable over Bluetooth
        """
        async with self._lock:
            self._update_advertisement_state()
            try:
                await self._refresh_cloud_state()
            except MoonsideCloudAuthError as ex:
                LOGGER.warning(
                    "Moonside cloud authentication failed for %s: %s", self._name, ex
                )
            except MoonsideCloudError as ex:
                LOGGER.debug("Moonside cloud refresh failed for %s: %s", self._name, ex)
            self._notify_state_listeners()
            return self.available

    async def pulse(self, duration: float = 0.5) -> bool:
        if not await self._send_commands([(CMD_LED_ON, duration), (CMD_LED_OFF, 0)]):
            return False
        self._is_on = False
        self._power_state_known = True
        self._power_state_source = "local"
        self._mark_local_write_pending()
        self._notify_state_listeners()
        return True

    async def strobe(self, count: int = 3, duration: float = 0.2) -> bool:
        commands: list[tuple[str, float]] = []
        for index in range(count):
            commands.append((CMD_LED_ON, duration))
            commands.append((CMD_LED_OFF, duration if index < count - 1 else 0))
        if not await self._send_commands(commands):
            return False
        self._is_on = False
        self._power_state_known = True
        self._power_state_source = "local"
        self._mark_local_write_pending()
        self._notify_state_listeners()
        return True

    async def color_cycle(
        self, colors: list[tuple[int, int, int]], duration: float = 2.0
    ) -> bool:
        if not colors:
            return False

        delay = duration / len(colors)
        device_brightness = self._convert_brightness_to_device(self._brightness)
        commands: list[tuple[str, float]] = []
        for color in colors:
            r, g, b = color
            commands.extend(
                [
                    (f"{CMD_COLOR}{r:03d}{g:03d}{b:03d}", 0.1),
                    (
                        f"{CMD_BRIGHTNESS}{device_brightness:03d}",
                        round(0.1 + delay, 6),
                    ),
                ]
            )

        if not await self._send_commands(commands):
            return False
        self._rgb_color = colors[-1]
        self._effect = None
        self._is_on = True
        self._power_state_known = True
        self._power_state_source = "local"
        self._mark_local_write_pending()
        self._notify_state_listeners()
        return True

    async def stop(self) -> None:
        async with self._lock:
            await self._disconnect_client()


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

    scanner: BleakScanner | None = None
    scanner_started = False
    try:
        LOGGER.debug("Starting Bluetooth scan for Moonside devices...")
        scanner = BleakScanner(detection_callback=device_found)
        await scanner.start()
        scanner_started = True
        await asyncio.sleep(timeout)
        LOGGER.debug("Scan complete. Found %d devices", len(devices_found))
    except Exception as ex:  # noqa: BLE001 - scanner backends raise varied errors
        LOGGER.error("Error during device discovery: %s", ex)
    finally:
        if scanner is not None and scanner_started:
            try:
                await scanner.stop()
            except Exception as ex:  # noqa: BLE001 - cleanup must not escape
                LOGGER.debug("Error stopping Bluetooth scan: %s", ex)

    return devices_found
