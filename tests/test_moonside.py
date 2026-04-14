"""Tests for Moonside BLE communication."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.moonside import (
    DOMAIN,
    SERVICE_COLOR_CYCLE,
    SERVICE_PULSE,
    SERVICE_SET_PIXEL,
    SERVICE_STROBE,
    _validate_color_cycle_colors,
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.moonside.config_flow import (
    MoonsideConfigFlow,
    _is_valid_manual_identifier,
)
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

    def test_is_on_is_unknown_when_power_state_is_unverified(self):
        """Remembered power state should not be exposed as live state until verified."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        instance._is_on = True

        assert instance.is_on is None

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
        listener = MagicMock()
        instance.register_state_listener(listener)

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
        listener.assert_called_once_with()
        assert instance.last_update is not None

    @pytest.mark.asyncio
    async def test_send_command_notifies_listeners_on_failure(self):
        """BLE command failures should still refresh subscribed entities."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        instance._lock = asyncio.Lock()
        instance._client = MagicMock()
        instance._client.is_connected = True
        instance._client.services.get_service.return_value = None
        instance._is_on = True
        instance._last_update = object()
        listener = MagicMock()
        instance.register_state_listener(listener)

        with patch.object(
            instance, "_ensure_connected", new=AsyncMock(return_value=True)
        ):
            result = await instance._send_command("LEDON")

        assert result is False
        assert instance.is_connected is False
        assert instance.is_on is None
        assert instance.last_update is None
        listener.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_send_command_notifies_listeners_when_reconnect_fails(self):
        """Reconnect failures should still refresh subscribed entities."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        instance._lock = asyncio.Lock()
        instance._is_on = True
        instance._last_update = object()
        listener = MagicMock()
        instance.register_state_listener(listener)

        with patch.object(
            instance, "_ensure_connected", new=AsyncMock(return_value=False)
        ):
            result = await instance._send_command("LEDON")

        assert result is False
        assert instance.is_on is None
        assert instance.last_update is None
        listener.assert_called_once_with()

    def test_state_listener_registration_and_notification(self):
        """Shared instance should notify registered entity listeners."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        listener = MagicMock()

        instance.register_state_listener(listener)
        instance._notify_state_listeners()

        listener.assert_called_once_with()

        instance.unregister_state_listener(listener)
        listener.reset_mock()
        instance._notify_state_listeners()

        listener.assert_not_called()

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
        instance._is_on = True
        instance._last_update = object()

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
            assert instance.is_on is None
            assert instance.last_update is None

    @pytest.mark.asyncio
    async def test_update_notifies_listeners_when_uart_service_is_missing(self):
        """State listeners should refresh when update detects a disconnected device."""
        hass = MagicMock()
        service_info = MagicMock(rssi=-55, time=100)
        listener = MagicMock()
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test", hass)
        instance._is_on = True
        instance._last_update = object()
        instance.register_state_listener(listener)

        client = MagicMock()
        client.services.get_service.return_value = None
        instance._client = client

        with (
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                side_effect=[service_info, service_info],
            ),
            patch(
                "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=120
            ),
            patch.object(
                instance, "_ensure_connected", new=AsyncMock(return_value=True)
            ),
        ):
            result = await instance.update()

        assert result is True
        assert instance.is_connected is False
        assert instance.is_on is None
        assert instance.last_update is None
        listener.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_update_marks_power_state_unknown_after_successful_poll(self):
        """Poll success should not preserve an unverified remembered power state."""
        hass = MagicMock()
        service_info = MagicMock(rssi=-55, time=100)
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test", hass)
        instance._is_on = True
        instance._power_state_known = True

        client = MagicMock()
        client.services.get_service.return_value = MagicMock()
        instance._client = client

        with (
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                side_effect=[service_info, service_info],
            ),
            patch(
                "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=120
            ),
            patch.object(
                instance, "_ensure_connected", new=AsyncMock(return_value=True)
            ),
        ):
            result = await instance.update()

        assert result is True
        assert instance.last_update is not None
        assert instance.is_on is None

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

    def test_model_detects_lamp_one_from_o101_ble_name(self):
        """MOONSIDE-O101 devices should be classified as Lamp One."""
        instance = MoonsideInstance(
            "AA:BB:CC:DD:EE:FF", "Test", ble_name="MOONSIDE-O101"
        )

        assert instance.model == "Lamp One"

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

    def test_update_advertisement_state_falls_back_to_fresh_nonconnectable_record(self):
        """Fresh non-connectable advertisements should be used after stale connectable ones."""
        hass = MagicMock()
        stale_connectable = MagicMock(rssi=-90, time=100)
        fresh_nonconnectable = MagicMock(rssi=-52, time=980)
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test", hass)

        with (
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                side_effect=[stale_connectable, fresh_nonconnectable],
            ),
            patch(
                "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=1000
            ),
        ):
            assert instance._update_advertisement_state() is True
            assert instance.available is True

        assert instance.rssi == -52
        assert instance._last_seen_monotonic == 980


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
    async def test_manual_step_rejects_invalid_identifier(self):
        """Manual setup should reject obviously invalid identifiers."""
        flow = MoonsideConfigFlow()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_show_form = MagicMock(return_value={"type": "form"})

        result = await flow.async_step_manual(
            {CONF_MAC: "bad identifier!", CONF_NAME: "Bedroom Lamp"}
        )

        assert result == {"type": "form"}
        _, kwargs = flow.async_show_form.call_args
        assert kwargs["errors"] == {"base": "invalid_identifier"}
        flow.async_set_unique_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_manual_step_accepts_non_mac_ble_identifier(self):
        """Manual setup should still allow non-MAC BLE identifiers used by this integration."""
        flow = MoonsideConfigFlow()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        await flow.async_step_manual(
            {CONF_MAC: "UUID-DEVICE-1", CONF_NAME: "Bedroom Lamp"}
        )

        _, kwargs = flow.async_create_entry.call_args
        assert kwargs["data"] == {
            CONF_MAC: "UUID-DEVICE-1",
            CONF_NAME: "Bedroom Lamp",
        }

    @pytest.mark.asyncio
    async def test_user_step_filters_discovery_and_falls_back_to_manual(self):
        """Only Moonside discoveries should be offered; otherwise the flow should fall back to manual."""
        flow = MoonsideConfigFlow()
        flow.hass = MagicMock()
        flow.async_show_form = MagicMock(return_value={"type": "form"})

        moonside = MagicMock()
        moonside.address = "UUID-1"
        moonside.name = "MOONSIDE-O101"
        other = MagicMock()
        other.address = "UUID-2"
        other.name = "Other Device"

        with patch(
            "custom_components.moonside.config_flow.async_discovered_service_info",
            return_value=[moonside, other],
        ):
            await flow.async_step_user()

        _, kwargs = flow.async_show_form.call_args
        options = kwargs["data_schema"].schema[vol.Required(CONF_MAC)].container
        assert options == {"UUID-1": "MOONSIDE-O101"}

        flow = MoonsideConfigFlow()
        flow.hass = MagicMock()
        flow.async_step_manual = AsyncMock(return_value={"type": "manual"})

        with patch(
            "custom_components.moonside.config_flow.async_discovered_service_info",
            return_value=[other],
        ):
            result = await flow.async_step_user()

        assert result == {"type": "manual"}
        flow.async_step_manual.assert_awaited_once()

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
        entry.title = "Bedroom Lamp"
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

    @pytest.mark.asyncio
    async def test_migrate_entry_backfills_ble_name_from_legacy_name(self):
        """Legacy discovery entries should recover the device BLE name from CONF_NAME."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.entry_id = "entry-3"
        entry.version = 1
        entry.title = "Moonside Light"
        entry.data = {
            CONF_MAC: "UUID-2",
            CONF_NAME: "MOONSIDE-L1",
        }

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry,
            data={
                CONF_MAC: "UUID-2",
                CONF_NAME: "MOONSIDE-L1",
                CONF_BLE_NAME: "MOONSIDE-L1",
            },
            version=2,
        )

    @pytest.mark.asyncio
    async def test_migrate_entry_backfills_ble_name_from_legacy_title(self):
        """Legacy discovery entries should recover the device BLE name from the entry title."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.entry_id = "entry-4"
        entry.version = 1
        entry.title = "MOONSIDE-O101"
        entry.data = {
            CONF_MAC: "UUID-4",
            CONF_NAME: "Bedroom Lamp",
        }

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry,
            data={
                CONF_MAC: "UUID-4",
                CONF_NAME: "Bedroom Lamp",
                CONF_BLE_NAME: "MOONSIDE-O101",
            },
            version=2,
        )

    @pytest.mark.asyncio
    async def test_migrate_entry_does_not_promote_generic_moonside_title(self):
        """Generic Moonside display labels should not be promoted to BLE identity."""
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.entry_id = "entry-5"
        entry.version = 1
        entry.title = "Moonside Light"
        entry.data = {
            CONF_MAC: "UUID-5",
            CONF_NAME: "Bedroom Lamp",
        }

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry,
            data={
                CONF_MAC: "UUID-5",
                CONF_NAME: "Bedroom Lamp",
            },
            version=2,
        )


class TestIntegrationLifecycle:
    """Test config-entry lifecycle and service registration."""

    @pytest.mark.asyncio
    async def test_setup_and_unload_registers_and_removes_services(self):
        """Setup should register services once; unload should stop the instance and remove services for the last entry."""
        hass = MagicMock()
        hass.data = {}
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        hass.bus.async_listen_once = MagicMock(return_value=MagicMock())
        hass.services.has_service = MagicMock(return_value=False)
        hass.services.async_register = MagicMock()
        hass.services.async_remove = MagicMock()

        entry = MagicMock()
        entry.entry_id = "entry-1"
        entry.data = {CONF_MAC: "UUID-1", CONF_NAME: "Bedroom Lamp"}
        entry.add_update_listener = MagicMock(return_value=MagicMock())
        entry.async_on_unload = MagicMock()

        instance = MagicMock()
        instance.stop = AsyncMock()

        with patch(
            "custom_components.moonside.MoonsideInstance", return_value=instance
        ):
            result = await async_setup_entry(hass, entry)

        assert result is True
        assert hass.data[DOMAIN][entry.entry_id] is instance
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()
        assert hass.services.async_register.call_count == 4

        registered_services = [
            call.args[1] for call in hass.services.async_register.call_args_list
        ]
        assert registered_services == [
            SERVICE_SET_PIXEL,
            SERVICE_PULSE,
            SERVICE_STROBE,
            SERVICE_COLOR_CYCLE,
        ]

        unload_result = await async_unload_entry(hass, entry)

        assert unload_result is True
        instance.stop.assert_awaited_once()
        assert entry.entry_id not in hass.data[DOMAIN]
        removed_services = [
            call.args[1] for call in hass.services.async_remove.call_args_list
        ]
        assert removed_services == [
            SERVICE_SET_PIXEL,
            SERVICE_PULSE,
            SERVICE_STROBE,
            SERVICE_COLOR_CYCLE,
        ]


class TestValidationHelpers:
    """Test service and identifier validators."""

    def test_validate_color_cycle_colors(self):
        """Color-cycle service input should be parsed into RGB tuples."""
        assert _validate_color_cycle_colors("[[255,0,0],[0,255,0]]") == [
            (255, 0, 0),
            (0, 255, 0),
        ]

    @pytest.mark.parametrize(
        "value",
        [
            "not-json",
            "[]",
            "{}",
            "[[255,0]]",
            '[[255,0,"0"]]',
            "[[255,0,256]]",
        ],
    )
    def test_validate_color_cycle_colors_rejects_invalid_input(self, value):
        """Invalid color-cycle payloads should fail before service execution."""
        with pytest.raises(vol.Invalid):
            _validate_color_cycle_colors(value)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("AA:BB:CC:DD:EE:FF", True),
            ("UUID-DEVICE-1", True),
            ("  UUID-DEVICE-1  ", True),
            ("", False),
            ("   ", False),
            ("bad identifier!", False),
        ],
    )
    def test_is_valid_manual_identifier(self, value, expected):
        """Manual identifier validation should reject obvious junk but allow plausible BLE IDs."""
        assert _is_valid_manual_identifier(value) is expected
