"""Tests for Moonside sensor platform."""

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from custom_components.moonside.sensor import (
    MoonsideRssiSensor,
    MoonsideConnectionSensor,
    MoonsideLastUpdateSensor,
)


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
        """Test connection sensor when connected."""
        mock_moonside_instance.is_connected = True
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.native_value == "connected"

    def test_connection_sensor_disconnected(self, mock_moonside_instance):
        """Test connection sensor when disconnected."""
        mock_moonside_instance.is_connected = False
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.native_value == "disconnected"

    def test_sensor_availability_follows_instance(self, mock_moonside_instance):
        """Sensor availability should follow the shared instance state."""
        mock_moonside_instance.available = False
        sensor = MoonsideConnectionSensor(
            instance=mock_moonside_instance,
            entry_id="test_entry_id",
        )

        assert sensor.available is False


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
