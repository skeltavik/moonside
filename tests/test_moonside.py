"""Tests for Moonside BLE communication."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.moonside.moonside import MoonsideInstance, discover_devices
from custom_components.moonside.const import MAX_BRIGHTNESS


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


class TestDiscoverDevices:
    """Test device discovery."""

    @pytest.mark.asyncio
    async def test_discover_devices(self):
        """Test device discovery."""
        mock_hass = MagicMock()

        # Mock BleakScanner
        mock_scanner = MagicMock()
        mock_scanner.start = AsyncMock()
        mock_scanner.stop = AsyncMock()

        with patch(
            "custom_components.moonside.moonside.BleakScanner",
            return_value=mock_scanner,
        ):
            devices = await discover_devices(mock_hass, timeout=0.1)

            # Scanner should be started and stopped
            mock_scanner.start.assert_called_once()
            mock_scanner.stop.assert_called_once()
