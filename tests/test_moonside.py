"""Tests for Moonside BLE communication."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.moonside import async_migrate_entry
from custom_components.moonside.config_flow import MoonsideConfigFlow
from custom_components.moonside.const import CONF_BLE_NAME, CONF_MAC, CONF_NAME
from custom_components.moonside.moonside import MoonsideInstance, discover_devices


class TestMoonsideInstance:
    """Test MoonsideInstance."""

    def test_initialization(self):
        """Test instance initialization."""
        instance = MoonsideInstance(
            mac_address="AA:BB:CC:DD:EE:FF",
            name="Test Lamp",
        )

        assert instance.address == "AA:BB:CC:DD:EE:FF"
        assert instance.name == "Test Lamp"
        assert instance.is_on is None
        assert instance.brightness == 255
        assert instance.rgb_color == (255, 255, 255)
        assert instance.rssi is None
        assert instance.is_connected is False

    def test_brightness_conversion(self):
        """Test brightness conversion."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        # Test HA brightness (0-255) to device (0-120)
        assert instance._convert_brightness_to_device(0) == 0
        assert instance._convert_brightness_to_device(255) == 120
        assert instance._convert_brightness_to_device(128) == 60

        # Test device brightness (0-120) to HA (0-255)
        assert instance._convert_brightness_from_device(0) == 0
        assert instance._convert_brightness_from_device(120) == 255
        assert instance._convert_brightness_from_device(60) == 127

    def test_available_when_recently_seen_over_bluetooth(self):
        """Recent Bluetooth advertisements should keep the device available."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        with patch(
            "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=100
        ):
            instance._last_seen_monotonic = 40

            assert instance.available is True

    def test_unavailable_when_not_connected_and_not_recently_seen(self):
        """Stale Bluetooth sightings should not keep the device available forever."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        with patch(
            "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=1000
        ):
            instance._last_seen_monotonic = 100

            assert instance.available is False

    @pytest.mark.asyncio
    async def test_turn_on(self):
        """Test turn on command."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        with patch.object(instance, "_send_command", new=AsyncMock(return_value=True)):
            result = await instance.turn_on()
            assert result is True
            assert instance.is_on is True

    @pytest.mark.asyncio
    async def test_turn_off(self):
        """Test turn off command."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        with patch.object(instance, "_send_command", new=AsyncMock(return_value=True)):
            result = await instance.turn_off()
            assert result is True
            assert instance.is_on is False

    @pytest.mark.asyncio
    async def test_set_brightness(self):
        """Test set brightness command."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        with patch.object(instance, "_send_command", new=AsyncMock(return_value=True)):
            result = await instance.set_brightness(128)
            assert result is True
            assert instance.brightness == 128

    @pytest.mark.asyncio
    async def test_set_color(self):
        """Test set color command."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        with patch.object(instance, "_send_command", new=AsyncMock(return_value=True)):
            result = await instance.set_color((255, 0, 0))
            assert result is True
            assert instance.rgb_color == (255, 0, 0)

    @pytest.mark.asyncio
    async def test_pulse(self):
        """Test pulse effect."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        with patch.object(instance, "_send_command", new=AsyncMock(return_value=True)):
            result = await instance.pulse(duration=0.1)
            assert result is True
            # Should call LEDON and LEDOFF
            assert instance._send_command.call_count == 2

    @pytest.mark.asyncio
    async def test_strobe(self):
        """Test strobe effect."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        with patch.object(instance, "_send_command", new=AsyncMock(return_value=True)):
            result = await instance.strobe(count=2, duration=0.1)
            assert result is True
            # Should call LEDON and LEDOFF twice each
            assert instance._send_command.call_count == 4

    @pytest.mark.asyncio
    async def test_color_cycle(self):
        """Test color cycle effect."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")

        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]

        with patch.object(instance, "set_color", new=AsyncMock(return_value=True)):
            result = await instance.color_cycle(colors, duration=0.3)
            assert result is True
            assert instance.set_color.call_count == 3

    @pytest.mark.asyncio
    async def test_send_command_uses_write_with_response(self):
        """Commands should use write-with-response for Moonside RX characteristic."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        instance._lock = asyncio.Lock()
        instance._client = MagicMock()
        instance._client.is_connected = True
        instance._client.write_gatt_char = AsyncMock()
        rx_char = MagicMock()
        service = MagicMock()
        service.get_characteristic.return_value = rx_char
        instance._client.services.get_service.return_value = service

        with patch.object(
            instance, "_ensure_connected", new=AsyncMock(return_value=True)
        ):
            result = await instance._send_command("LEDON")

        assert result is True
        instance._client.write_gatt_char.assert_awaited_once_with(
            rx_char,
            b"LEDON",
            response=True,
        )

    @pytest.mark.asyncio
    async def test_ensure_connected_uses_home_assistant_ble_device(self):
        """Use Home Assistant's discovered BLE device when available."""
        hass = MagicMock()
        ble_device = MagicMock()
        client = MagicMock()
        client.is_connected = True

        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test", hass)

        with (
            patch(
                "custom_components.moonside.moonside.async_ble_device_from_address",
                return_value=ble_device,
            ),
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                return_value=None,
            ),
            patch(
                "custom_components.moonside.moonside.establish_connection",
                new=AsyncMock(return_value=client),
            ) as mock_connect,
        ):
            result = await instance._ensure_connected()

        assert result is True
        assert instance.is_connected is True
        assert instance.last_connected is not None
        args, kwargs = mock_connect.await_args
        assert args[1] is ble_device
        assert args[2] == "Test"
        assert kwargs == {"max_attempts": 3}

    @pytest.mark.asyncio
    async def test_ensure_connected_does_not_fall_back_to_discovered_device_name(self):
        """Do not connect to a different device based on BLE name alone."""
        hass = MagicMock()

        instance = MoonsideInstance(
            "AA:BB:CC:DD:EE:FF", "Bedroom Lamp", hass, ble_name="MOONSIDE-O101"
        )

        with (
            patch(
                "custom_components.moonside.moonside.async_ble_device_from_address",
                return_value=None,
            ),
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                return_value=None,
            ),
            patch(
                "custom_components.moonside.moonside.establish_connection",
                new=AsyncMock(side_effect=AssertionError("Should not connect by name")),
            ) as mock_connect,
        ):
            result = await instance._ensure_connected()

        assert result is False
        args, kwargs = mock_connect.await_args
        assert args[1] == "AA:BB:CC:DD:EE:FF"
        assert args[2] == "Bedroom Lamp"
        assert kwargs == {"max_attempts": 3}

    @pytest.mark.asyncio
    async def test_update_returns_true_when_device_was_recently_advertised(self):
        """Advertisement presence should keep the entity available during a transient poll failure."""
        hass = MagicMock()
        service_info = MagicMock(rssi=-55, time=100)
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test", hass)

        with (
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                side_effect=[service_info, service_info],
            ),
            patch(
                "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=120
            ),
            patch.object(
                instance, "_ensure_connected", new=AsyncMock(return_value=False)
            ),
        ):
            result = await instance.update()
            assert result is True
            assert instance.available is True
            assert instance.rssi == -55

    def test_update_advertisement_state_does_not_fall_back_to_name(self):
        """Advertisement state should not use BLE name as an identity fallback."""
        hass = MagicMock()
        service_info = MagicMock(address="UUID-ADDRESS", rssi=-61)
        service_info.name = "MOONSIDE-O101"
        instance = MoonsideInstance(
            "AA:BB:CC:DD:EE:FF", "Bedroom Lamp", hass, ble_name="MOONSIDE-O101"
        )

        with (
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                side_effect=[None, None],
            ),
        ):
            assert instance._update_advertisement_state() is False

        assert service_info.name == "MOONSIDE-O101"
        assert instance.rssi is None

    def test_update_advertisement_state_ignores_stale_cached_advertisement(self):
        """Stale cached advertisements should not refresh availability."""
        hass = MagicMock()
        service_info = MagicMock(rssi=-61, time=100)
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test", hass)

        with (
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                side_effect=[service_info, service_info],
            ),
            patch(
                "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=1000
            ),
        ):
            assert instance._update_advertisement_state() is False

        assert instance.rssi is None


class TestDiscoverDevices:
    """Test device discovery."""

    @pytest.mark.asyncio
    async def test_discover_devices(self):
        """Test device discovery."""
        mock_hass = MagicMock()

        discovered_device = MagicMock(address="UUID-ADDRESS", name="MOONSIDE-O101")
        advertisement = MagicMock(local_name="MOONSIDE-O101")
        scanner_instances = []

        class FakeScanner:
            def __init__(self, detection_callback, **kwargs):
                self.detection_callback = detection_callback
                self.kwargs = kwargs
                self.start = AsyncMock(side_effect=self._start)
                self.stop = AsyncMock()
                scanner_instances.append(self)

            async def _start(self):
                self.detection_callback(discovered_device, advertisement)

        with patch(
            "custom_components.moonside.moonside.BleakScanner",
            side_effect=FakeScanner,
        ):
            devices = await discover_devices(mock_hass, timeout=0.1)

            scanner = scanner_instances[0]
            scanner.start.assert_called_once()
            scanner.stop.assert_called_once()
            assert scanner.kwargs == {}
            assert devices == [("UUID-ADDRESS", "MOONSIDE-O101")]


class TestConfigFlow:
    """Test config flow identity handling."""

    @pytest.mark.asyncio
    async def test_bluetooth_confirm_stores_real_ble_name(self):
        """Bluetooth discovery should persist the advertised BLE name."""
        flow = MoonsideConfigFlow()
        flow._discovery_info = MagicMock(address="UUID-1")
        flow._discovery_info.name = "MOONSIDE-O101"
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        await flow.async_step_bluetooth_confirm({CONF_NAME: "Bedroom Lamp"})

        _, kwargs = flow.async_create_entry.call_args
        assert kwargs["data"] == {
            CONF_MAC: "UUID-1",
            CONF_BLE_NAME: "MOONSIDE-O101",
            CONF_NAME: "Bedroom Lamp",
        }

    @pytest.mark.asyncio
    async def test_bluetooth_confirm_without_name_does_not_store_ble_name(self):
        """Bluetooth confirm should not synthesize BLE identity when no name exists."""
        flow = MoonsideConfigFlow()
        flow._discovery_info = MagicMock(address="UUID-2")
        flow._discovery_info.name = None
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        await flow.async_step_bluetooth_confirm({CONF_NAME: "Bedroom Lamp"})

        _, kwargs = flow.async_create_entry.call_args
        assert kwargs["data"] == {
            CONF_MAC: "UUID-2",
            CONF_NAME: "Bedroom Lamp",
        }

    @pytest.mark.asyncio
    async def test_manual_step_does_not_store_display_name_as_ble_name(self):
        """Manual setup should keep display name separate from BLE identity metadata."""
        flow = MoonsideConfigFlow()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        await flow.async_step_manual(
            {CONF_MAC: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Bedroom Lamp"}
        )

        _, kwargs = flow.async_create_entry.call_args
        assert kwargs["data"] == {
            CONF_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Bedroom Lamp",
        }

    @pytest.mark.asyncio
    async def test_user_step_without_name_does_not_store_ble_name(self):
        """Discovered-device picker should not fabricate a BLE name when absent."""
        flow = MoonsideConfigFlow()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        discovery_info = MagicMock(address="UUID-3")
        discovery_info.name = None
        flow._discovered_devices = {"UUID-3": discovery_info}

        await flow.async_step_user({CONF_MAC: "UUID-3", CONF_NAME: "Bedroom Lamp"})

        _, kwargs = flow.async_create_entry.call_args
        assert kwargs["data"] == {
            CONF_MAC: "UUID-3",
            CONF_NAME: "Bedroom Lamp",
        }


class TestConfigEntryMigration:
    """Test config entry migration behavior."""

    @pytest.mark.asyncio
    async def test_migrate_entry_removes_display_name_backfill(self):
        """Legacy entries should not treat display name as BLE identity."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.entry_id = "entry-1"
        entry.version = 1
        entry.data = {
            CONF_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Bedroom Lamp",
            CONF_BLE_NAME: "Bedroom Lamp",
        }

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry,
            data={
                CONF_MAC: "AA:BB:CC:DD:EE:FF",
                CONF_NAME: "Bedroom Lamp",
            },
            version=2,
        )

    @pytest.mark.asyncio
    async def test_migrate_entry_keeps_real_moonside_ble_name(self):
        """Migration should preserve a valid discovered BLE name."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.entry_id = "entry-2"
        entry.version = 1
        entry.data = {
            CONF_MAC: "UUID-1",
            CONF_NAME: "Bedroom Lamp",
            CONF_BLE_NAME: "MOONSIDE-O101",
        }

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry,
            data={
                CONF_MAC: "UUID-1",
                CONF_NAME: "Bedroom Lamp",
                CONF_BLE_NAME: "MOONSIDE-O101",
            },
            version=2,
        )
