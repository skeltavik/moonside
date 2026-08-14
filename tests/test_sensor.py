"""Tests for Moonside sensor platform."""

from datetime import UTC
from unittest.mock import AsyncMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from custom_components.moonside.sensor import (
    MoonsideRssiSensor,
    MoonsideConnectionSensor,
    MoonsideLastUpdateSensor,
)
from custom_components.moonside.moonside import MoonsideInstance


class TestMoonsideRssiSensor:
    """Test RSSI sensor."""

    def test_rssi_sensor_initialization(self, mock_moonside_instance):
        """Test RSSI sensor initialization."""
        sensor = MoonsideRssiSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.unique_id == "AA:BB:CC:DD:EE:FF_rssi"
        assert sensor.name == "Signal Strength"
        assert sensor.device_class == SensorDeviceClass.SIGNAL_STRENGTH
        assert sensor.native_unit_of_measurement == SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    def test_rssi_native_value(self, mock_moonside_instance):
        """Test RSSI value."""
        mock_moonside_instance.rssi = -65
        sensor = MoonsideRssiSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.native_value == -65

    def test_rssi_extra_state_attributes(self, mock_moonside_instance):
        """Test RSSI extra attributes."""
        sensor = MoonsideRssiSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        attrs = sensor.extra_state_attributes
        assert attrs["device_identifier"] == "AA:BB:CC:DD:EE:FF"

    def test_rssi_sensor_device_info_uses_instance_model(self, mock_moonside_instance):
        """Test sensor device info model follows the instance model."""
        mock_moonside_instance.model = "Neon"
        sensor = MoonsideRssiSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.device_info["model"] == "Neon"


class TestMoonsideConnectionSensor:
    """Test connection sensor."""

    def test_connection_sensor_connected(self, mock_moonside_instance):
        """Test connection sensor when the device is reachable."""
        mock_moonside_instance.is_connected = True
        mock_moonside_instance.available = True
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.native_value == "connected"

    def test_connection_sensor_disconnected(self, mock_moonside_instance):
        """Test connection sensor when the device is unreachable."""
        mock_moonside_instance.is_connected = False
        mock_moonside_instance.available = False
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.native_value == "disconnected"

    def test_connection_sensor_reports_connected_when_recently_seen(
        self, mock_moonside_instance
    ):
        """Reachable devices should not show as disconnected just because no active session is open."""
        mock_moonside_instance.is_connected = False
        mock_moonside_instance.available = True
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.native_value == "connected"

    def test_sensor_availability_stays_visible_when_instance_is_unavailable(
        self, mock_moonside_instance
    ):
        """Diagnostic sensors should stay visible even when the lamp is unreachable."""
        mock_moonside_instance.available = False
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.available is True

    def test_sensors_are_push_updated(self, mock_moonside_instance):
        """Diagnostic sensors should not poll independently."""
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.should_poll is False

    async def test_sensor_registers_and_unregisters_state_listener(
        self, mock_moonside_instance
    ):
        """Sensors should subscribe to shared instance state updates."""
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        with (
            patch(
                "custom_components.moonside.sensor.SensorEntity.async_added_to_hass",
                new=AsyncMock(),
            ),
            patch(
                "custom_components.moonside.sensor.SensorEntity.async_will_remove_from_hass",
                new=AsyncMock(),
            ),
        ):
            await sensor.async_added_to_hass()
            mock_moonside_instance.register_state_listener.assert_called_once_with(
                sensor.async_write_ha_state
            )

            await sensor.async_will_remove_from_hass()
            mock_moonside_instance.unregister_state_listener.assert_called_once_with(
                sensor.async_write_ha_state
            )


class TestMoonsideLastUpdateSensor:
    """Test last update sensor."""

    def test_last_update_sensor(self, mock_moonside_instance):
        """Test last update sensor."""
        from datetime import datetime

        now = datetime.now()
        mock_moonside_instance.last_update = now
        sensor = MoonsideLastUpdateSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.native_value == now
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP

    def test_last_update_sensor_provides_timezone_aware_timestamp(self):
        """Timestamp sensors must provide timezone-aware datetimes to Home Assistant."""
        instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Test")
        instance.apply_cloud_state({"controlData": "LEDON"})
        sensor = MoonsideLastUpdateSensor(instance, "test_entry_id")
        sensor.entity_id = "sensor.moonside_last_update"

        assert sensor.native_value is not None
        assert sensor.native_value.tzinfo is UTC
        assert sensor.state.endswith("+00:00")
