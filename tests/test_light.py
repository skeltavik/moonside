"""Tests for Moonside light platform."""

import pytest
from unittest.mock import AsyncMock, patch
from homeassistant.components.light import ColorMode
from homeassistant.core import State
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

    def test_light_reports_assumed_state_when_power_is_unverified(
        self, mock_moonside_light, mock_moonside_instance
    ):
        """The light should expose assumed state when live power state is unknown."""
        mock_moonside_instance.is_on = None

        assert mock_moonside_light.assumed_state is True

        mock_moonside_instance.is_on = True
        assert mock_moonside_light.assumed_state is False

    @pytest.mark.asyncio
    async def test_turn_on(self, mock_moonside_light, mock_moonside_instance):
        """Test turning on the light."""
        mock_moonside_instance.is_on = False

        with patch.object(mock_moonside_light, "async_write_ha_state"):
            await mock_moonside_light.async_turn_on()

        mock_moonside_instance.turn_on.assert_called_once()

    @pytest.mark.asyncio
    async def test_light_registers_and_unregisters_state_listener(
        self, mock_moonside_light, mock_moonside_instance
    ):
        """Light should subscribe to shared instance state updates."""
        with (
            patch(
                "custom_components.moonside.light.RestoreEntity.async_added_to_hass",
                new=AsyncMock(),
            ),
            patch.object(
                mock_moonside_light,
                "async_get_last_state",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "custom_components.moonside.light.RestoreEntity.async_will_remove_from_hass",
                new=AsyncMock(),
            ),
        ):
            await mock_moonside_light.async_added_to_hass()
            mock_moonside_instance.register_state_listener.assert_called_once_with(
                mock_moonside_light.async_write_ha_state
            )

            await mock_moonside_light.async_will_remove_from_hass()
            mock_moonside_instance.unregister_state_listener.assert_called_once_with(
                mock_moonside_light.async_write_ha_state
            )

    @pytest.mark.asyncio
    async def test_restored_power_state_is_marked_unverified(
        self, mock_moonside_light, mock_moonside_instance
    ):
        """Restored power state should not be treated as live device truth."""
        restored_state = State("light.test_moonside", "on", {"brightness": 128})

        with (
            patch(
                "custom_components.moonside.light.RestoreEntity.async_added_to_hass",
                new=AsyncMock(),
            ),
            patch.object(
                mock_moonside_light,
                "async_get_last_state",
                new=AsyncMock(return_value=restored_state),
            ),
        ):
            await mock_moonside_light.async_added_to_hass()

        assert mock_moonside_instance._is_on is True
        assert mock_moonside_instance._power_state_known is False

    @pytest.mark.asyncio
    async def test_restored_attributes_are_replayed_but_power_stays_unverified(
        self, mock_moonside_light, mock_moonside_instance
    ):
        """Remembered attributes should be restored without claiming live power truth."""
        restored_state = State(
            "light.test_moonside",
            "on",
            {
                "brightness": 200,
                "rgb_color": (1, 2, 3),
                "effect": "Rainbow One",
            },
        )

        with (
            patch(
                "custom_components.moonside.light.RestoreEntity.async_added_to_hass",
                new=AsyncMock(),
            ),
            patch.object(
                mock_moonside_light,
                "async_get_last_state",
                new=AsyncMock(return_value=restored_state),
            ),
        ):
            await mock_moonside_light.async_added_to_hass()

        assert mock_moonside_instance._is_on is True
        assert mock_moonside_instance._brightness == 200
        assert mock_moonside_instance._rgb_color == (1, 2, 3)
        assert mock_moonside_instance._effect == "rainbow_one"
        assert mock_moonside_instance._power_state_known is False

    @pytest.mark.asyncio
    async def test_async_update_refreshes_shared_instance(
        self, mock_moonside_light, mock_moonside_instance
    ):
        """Light polling should refresh the shared Moonside instance."""
        await mock_moonside_light.async_update()

        mock_moonside_instance.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, mock_moonside_light, mock_moonside_instance):
        """Test turning off the light."""
        with patch.object(mock_moonside_light, "async_write_ha_state"):
            await mock_moonside_light.async_turn_off()

        mock_moonside_instance.turn_off.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_brightness(self, mock_moonside_light, mock_moonside_instance):
        """Test setting brightness."""
        with patch.object(mock_moonside_light, "async_write_ha_state"):
            await mock_moonside_light.async_turn_on(brightness=200)

        mock_moonside_instance.turn_on.assert_not_called()
        mock_moonside_instance.set_brightness.assert_called_once_with(200)

    @pytest.mark.asyncio
    async def test_set_color(self, mock_moonside_light, mock_moonside_instance):
        """Test setting color."""
        with patch.object(mock_moonside_light, "async_write_ha_state"):
            await mock_moonside_light.async_turn_on(rgb_color=(0, 255, 0))

        mock_moonside_instance.set_color.assert_called_once_with((0, 255, 0))

    @pytest.mark.asyncio
    async def test_set_effect(self, mock_moonside_light, mock_moonside_instance):
        """Test setting effect."""
        with patch.object(mock_moonside_light, "async_write_ha_state"):
            await mock_moonside_light.async_turn_on(effect="Rainbow One")

        mock_moonside_instance.set_effect.assert_called_once_with("rainbow_one")

    def test_device_info(self, mock_moonside_light):
        """Test device info."""
        info = mock_moonside_light.device_info
        assert info["identifiers"] == {(DOMAIN, "AA:BB:CC:DD:EE:FF")}
        assert info["name"] == "Test Moonside"
        assert info["manufacturer"] == "Moonside"
        assert info["model"] == "Moonside"

    def test_device_info_uses_halo_model_when_detected(self, mock_moonside_light):
        """Device info should expose the detected Halo model name."""
        mock_moonside_light._instance.model = "Halo Lamp"

        info = mock_moonside_light.device_info

        assert info["model"] == "Halo Lamp"
