"""Test configuration for Moonside integration."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.config_entries = AsyncMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        "mac": "AA:BB:CC:DD:EE:FF",
        "name": "Test Moonside",
    }
    return entry


@pytest.fixture
def mock_moonside_instance():
    """Mock MoonsideInstance."""
    instance = MagicMock()
    instance.address = "AA:BB:CC:DD:EE:FF"
    instance.name = "Test Moonside"
    instance.is_on = True
    instance.brightness = 128
    instance.rgb_color = (255, 0, 0)
    instance.effect = None
    instance.available = True
    instance.model = "Lighthouse"
    instance.rssi = -65
    instance.is_connected = True
    instance.last_connected = None
    instance.last_update = None

    # Mock async methods
    instance.turn_on = AsyncMock(return_value=True)
    instance.turn_off = AsyncMock(return_value=True)
    instance.set_brightness = AsyncMock(return_value=True)
    instance.set_color = AsyncMock(return_value=True)
    instance.set_effect = AsyncMock(return_value=True)
    instance.pulse = AsyncMock(return_value=True)
    instance.strobe = AsyncMock(return_value=True)
    instance.color_cycle = AsyncMock(return_value=True)
    instance.stop = AsyncMock()

    return instance
