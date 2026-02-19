"""Tests for Moonside light platform."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.components.light import ColorMode
from custom_components.moonside.light import MoonsideLight
from custom_components.moonside.const import DOMAIN


@pytest.fixture
def mock_moonside_light(mock_moonside_instance):
    """Create a MoonsideLight entity."""
    light = MoonsideLight(
        instance=mock_moonside_instance,
        name="Test Moonside",
        entry_id="test_entry_id",
    )
    return light


class TestMoonsideLight:
    """Test MoonsideLight entity."""

    def test_light_entity_initialization(self, mock_moonside_instance):
        """Test light entity initialization."""
        light = MoonsideLight(
            instance=mock_moonside_instance,
            name="Test Moonside",
            entry_id="test_entry_id",
        )

        assert light.unique_id == "AA:BB:CC:DD:EE:FF"
        assert light.name is None  # Uses has_entity_name = True
        assert light._attr_has_entity_name is True
        assert ColorMode.RGB in light.supported_color_modes

    def test_light_properties(self, mock_moonside_light, mock_moonside_instance):
        """Test light property getters."""
        assert mock_moonside_light.is_on is True
        assert mock_moonside_light.brightness == 128
        assert mock_moonside_light.rgb_color == (255, 0, 0)
        assert mock_moonside_light.available is True

    @pytest.mark.asyncio
    async def test_turn_on(self, mock_moonside_light, mock_moonside_instance):
        """Test turning on the light."""
        await mock_moonside_light.async_turn_on()
        mock_moonside_instance.turn_on.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, mock_moonside_light, mock_moonside_instance):
        """Test turning off the light."""
        await mock_moonside_light.async_turn_off()
        mock_moonside_instance.turn_off.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_brightness(self, mock_moonside_light, mock_moonside_instance):
        """Test setting brightness."""
        await mock_moonside_light.async_turn_on(brightness=200)
        mock_moonside_instance.turn_on.assert_called_once()
        mock_moonside_instance.set_brightness.assert_called_once_with(200)

    @pytest.mark.asyncio
    async def test_set_color(self, mock_moonside_light, mock_moonside_instance):
        """Test setting color."""
        await mock_moonside_light.async_turn_on(rgb_color=(0, 255, 0))
        mock_moonside_instance.set_color.assert_called_once_with((0, 255, 0))

    @pytest.mark.asyncio
    async def test_set_effect(self, mock_moonside_light, mock_moonside_instance):
        """Test setting effect."""
        await mock_moonside_light.async_turn_on(effect="rainbow_one")
        mock_moonside_instance.set_effect.assert_called_once()

    def test_device_info(self, mock_moonside_light):
        """Test device info."""
        info = mock_moonside_light.device_info
        assert info["identifiers"] == {(DOMAIN, "AA:BB:CC:DD:EE:FF")}
        assert info["name"] == "Test Moonside"
        assert info["manufacturer"] == "Moonside"
        assert info["model"] == "Lighthouse"
