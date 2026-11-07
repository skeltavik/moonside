"""Regressions for prompt state publication and bounded Bluetooth reuse."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonside import async_setup_entry, async_unload_entry
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


async def test_effect_and_brightness_publish_together(connected_lamp):
    """Scenes selecting an effect must also apply their requested brightness."""
    instance, client, _ = connected_lamp
    instance._is_on = True
    instance._power_state_known = True
    light = MoonsideLight(instance, "Lamp One", "entry")
    states = []
    instance.register_state_listener(
        lambda: states.append((light.effect, light.brightness))
    )
    with patch.object(light, "async_write_ha_state"):
        await light.async_turn_on(effect="Rainbow One", brightness=80)
    assert (light.effect, light.brightness) == ("Rainbow One", 80)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        b"THEME.RAINBOW1.20,",
        b"BRIGH037",
    ]
    assert all(brightness == 80 for effect, brightness in states if effect)


async def test_failed_effect_brightness_batch_does_not_claim_success(connected_lamp):
    """A partially sent scene must surface failure, not a new effect or brightness."""
    instance, client, _ = connected_lamp
    instance._is_on = True
    instance._power_state_known = True
    client.write_gatt_char.side_effect = [None, RuntimeError("link lost")]
    light = MoonsideLight(instance, "Lamp One", "entry")
    with patch.object(light, "async_write_ha_state"), pytest.raises(HomeAssistantError):
        await light.async_turn_on(effect="Rainbow One", brightness=80)
    assert instance.is_on is None
    assert instance.effect is None
    assert instance.brightness == 255


@pytest.mark.parametrize(
    "kwargs",
    [None, {}, {"brightness": 80}, {"rgb_color": (1, 2, 3)}, {"effect": "Rainbow One"}],
)
async def test_failed_light_commands_raise(connected_lamp, kwargs):
    """Automations must receive a failure when the transport rejects a command."""
    instance, client, _ = connected_lamp
    instance._is_on = kwargs is None or bool(kwargs)
    instance._power_state_known = True
    before = instance.is_on
    client.write_gatt_char.side_effect = RuntimeError("link lost")
    light = MoonsideLight(instance, "Lamp One", "entry")
    with patch.object(light, "async_write_ha_state"), pytest.raises(HomeAssistantError):
        if kwargs is None:
            await light.async_turn_off()
        else:
            await light.async_turn_on(**kwargs)
    assert instance.is_on is before
    assert instance.brightness == 255


@pytest.mark.parametrize("grace_seconds", [0, 10])
async def test_slow_cloud_does_not_block_or_undo_local_control(
    connected_lamp, grace_seconds
):
    """A cloud response fetched before a local write cannot roll that write back."""
    instance, _client, _ = connected_lamp
    instance._cloud_write_grace_period = timedelta(seconds=grace_seconds)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch_state(device_id):
        entered.set()
        await release.wait()
        return {"controlData": "LEDOFF", "brightness": 5}

    cloud = MagicMock()
    cloud.async_get_device_state = fetch_state
    instance._cloud_device_id = "device-1"
    with patch.object(instance, "_ensure_cloud_client", return_value=cloud):
        refresh = asyncio.create_task(instance.update())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert await asyncio.wait_for(instance.set_brightness(80), 1)
        finally:
            release.set()
            await refresh
    assert (instance.is_on, instance.brightness) == (True, 80)
    assert instance.power_state_source == "local"


async def test_cloud_cannot_confirm_power_after_partial_local_write(connected_lamp):
    """Old cloud state cannot erase uncertainty created by a partial BLE batch."""
    instance, client, _ = connected_lamp
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch_state(device_id):
        entered.set()
        await release.wait()
        return {"controlData": "LEDOFF"}

    cloud = MagicMock()
    cloud.async_get_device_state = fetch_state
    instance._cloud_device_id = "device-1"
    client.write_gatt_char.side_effect = [None, RuntimeError("link lost")]
    with patch.object(instance, "_ensure_cloud_client", return_value=cloud):
        refresh = asyncio.create_task(instance.update())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not await asyncio.wait_for(instance.set_color((1, 2, 3)), 1)
        finally:
            release.set()
            await refresh
    assert instance.is_on is None
    assert instance.power_state_source == "unknown"


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("set_pixel", {"pixel_id": 0, "brightness": 60}),
        ("pulse", {"duration": 0.1}),
        ("strobe", {"count": 1, "duration": 0.1}),
        ("color_cycle", {"colors": "[[1,2,3]]", "duration": 0.5}),
    ],
)
async def test_failed_custom_actions_raise_through_ha(
    hass, connected_lamp, service, data
):
    """A blocking HA action call must fail when no BLE command was accepted."""
    instance, client, _ = connected_lamp
    instance._ble_name = "MOONSIDE-LIGHTHOUSE"
    client.write_gatt_char.side_effect = RuntimeError("link lost")
    entry = MockConfigEntry(
        domain="moonside",
        data={"mac": instance.address, "name": "Lamp"},
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.moonside.MoonsideInstance", return_value=instance),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ),
    ):
        await async_setup_entry(hass, entry)
    entity = er.async_get(hass).async_get_or_create(
        "light", "moonside", instance.address, config_entry=entry
    )
    try:
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "moonside",
                service,
                {"entity_id": entity.entity_id, **data},
                blocking=True,
            )
    finally:
        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new=AsyncMock(return_value=True),
        ):
            await async_unload_entry(hass, entry)


async def test_manual_lighthouse_recovers_and_persists_ble_model(hass, connected_lamp):
    """Real advertisement metadata unlocks pixels without renaming or reloading."""
    instance, client, _ = connected_lamp
    instance._hass = hass
    entry = MockConfigEntry(
        domain="moonside",
        data={"mac": instance.address, "name": "My desk"},
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.moonside.MoonsideInstance", return_value=instance),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ),
    ):
        await async_setup_entry(hass, entry)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("moonside", instance.address)},
        model="Moonside",
    )
    advertisement = MagicMock(rssi=-55, time=100)
    advertisement.name = "MOONSIDE-LIGHTHOUSE"
    try:
        with (
            patch(
                "custom_components.moonside.moonside.async_last_service_info",
                return_value=advertisement,
            ),
            patch(
                "custom_components.moonside.moonside.MONOTONIC_TIME", return_value=120
            ),
            patch.object(
                hass.config_entries, "async_reload", new=AsyncMock()
            ) as reload,
        ):
            await instance.update()
            await hass.async_block_till_done()
            assert instance.model == "Neon Lighthouse"
            assert entry.data["ble_name"] == "MOONSIDE-LIGHTHOUSE"
            assert entry.data["name"] == "My desk"
            assert dr.async_get(hass).async_get(device.id).model == "Neon Lighthouse"
            reload.assert_not_awaited()
            assert await instance.set_and_apply_pixel(0, 60)
        restored = MoonsideInstance(
            entry.data["mac"], entry.data["name"], ble_name=entry.data["ble_name"]
        )
        assert restored.model == "Neon Lighthouse"
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
            b"PIXEL,0,60",
            b"MODEPIXEL",
        ]
    finally:
        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new=AsyncMock(return_value=True),
        ):
            await async_unload_entry(hass, entry)


async def test_effect_from_off_wakes_lamp_without_changing_brightness(connected_lamp):
    """An effect-only request must wake an off lamp without sending a dim command."""
    instance, client, _ = connected_lamp
    instance._is_on = False
    instance._power_state_known = True
    instance._brightness = 80
    light = MoonsideLight(instance, "Lamp One", "entry")
    with patch.object(light, "async_write_ha_state"):
        await light.async_turn_on(effect="Rainbow One")
    assert (light.is_on, light.effect, light.brightness) == (True, "Rainbow One", 80)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        b"LEDON",
        b"THEME.RAINBOW1.20,",
    ]


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("set_pixel", (0, 60)),
        ("apply_pixels", ()),
        ("set_and_apply_pixel", (0, 60)),
    ],
)
async def test_cloud_cannot_reconcile_over_successful_pixel_write(
    connected_lamp, method, args
):
    """Pixel writes invalidate an in-flight cloud snapshot just like other writes."""
    instance, _client, _ = connected_lamp
    instance._ble_name = "MOONSIDE-LIGHTHOUSE"
    instance._cloud_write_grace_period = timedelta(0)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch_state(device_id):
        entered.set()
        await release.wait()
        return {"controlData": "LEDOFF", "brightness": 5}

    cloud = MagicMock()
    cloud.async_get_device_state = fetch_state
    instance._cloud_device_id = "device-1"
    with patch.object(instance, "_ensure_cloud_client", return_value=cloud):
        refresh = asyncio.create_task(instance.update())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert await asyncio.wait_for(getattr(instance, method)(*args), 1)
        finally:
            release.set()
            await refresh
    assert instance.is_on is None
    assert instance.power_state_source == "unknown"
    assert instance.brightness == 255
