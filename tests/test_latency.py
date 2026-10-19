"""Regressions for prompt state publication and bounded Bluetooth reuse."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.moonside.light import MoonsideLight
from custom_components.moonside.moonside import MoonsideInstance


@pytest.fixture
async def connected_lamp():
    instance = MoonsideInstance("AA:BB:CC:DD:EE:FF", "Lamp One")
    client = MagicMock()
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    disconnected = asyncio.Event()

    async def disconnect():
        client.is_connected = False
        disconnected.set()

    client.disconnect = AsyncMock(side_effect=disconnect)
    instance._client = client
    instance._connected = True
    yield instance, client, disconnected
    await instance.stop()


async def test_color_and_brightness_publish_together_from_off(connected_lamp):
    instance, client, _ = connected_lamp
    instance._is_on = False
    instance._power_state_known = True
    light = MoonsideLight(instance, "Lamp One", "entry")
    states = []
    instance.register_state_listener(
        lambda: states.append((light.is_on, light.rgb_color, light.brightness))
    )
    with patch.object(light, "async_write_ha_state"):
        await light.async_turn_on(rgb_color=(20, 40, 60), brightness=80)
    assert (light.is_on, light.rgb_color, light.brightness) == (True, (20, 40, 60), 80)
    assert all(
        brightness == 80 for on, color, brightness in states if color == (20, 40, 60)
    )
    assert client.is_connected


async def test_successive_commands_do_not_wait_for_disconnect(connected_lamp):
    instance, client, disconnected = connected_lamp
    assert await instance.set_brightness(80)
    assert await instance.set_color((20, 40, 60), brightness=96)
    assert instance.is_on is True
    assert instance.brightness == 96
    assert instance.rgb_color == (20, 40, 60)
    assert client.is_connected
    assert not disconnected.is_set()
    await instance.stop()
    assert disconnected.is_set()
    assert instance._idle_disconnect_task is None


async def test_idle_cleanup_releases_connection_and_notifies(
    connected_lamp, monkeypatch
):
    instance, _client, disconnected = connected_lamp
    monkeypatch.setattr(
        "custom_components.moonside.moonside.IDLE_DISCONNECT_SECONDS", 0
    )
    states = []
    instance.register_state_listener(lambda: states.append(instance.is_connected))
    assert await instance.turn_on()
    await asyncio.wait_for(disconnected.wait(), 1)
    assert instance.is_connected is False
    assert instance.is_on is True
    assert states[-1] is False


async def test_failed_write_discards_connection_without_claiming_new_state(
    connected_lamp,
):
    instance, client, disconnected = connected_lamp
    assert await instance.set_brightness(80)
    client.write_gatt_char.side_effect = RuntimeError("link lost")
    assert await instance.set_brightness(96) is False
    assert instance.brightness == 80
    assert disconnected.is_set()
    assert instance._idle_disconnect_task is None
