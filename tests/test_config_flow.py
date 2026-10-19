"""Exercise setup transitions through Home Assistant's flow manager."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.moonside.const import CONF_BLE_NAME, CONF_MAC, CONF_NAME, DOMAIN


@pytest.mark.parametrize("source", ["manual", "user", "bluetooth"])
async def test_setup_can_finish_without_cloud(hass, enable_custom_integrations, tmp_path, source):
    """Every setup route must reach and submit the optional cloud form."""
    hass.config.config_dir = str(tmp_path)
    components = Path(hass.config.path("custom_components"))
    components.mkdir(exist_ok=True)
    (components / DOMAIN).symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN,
        target_is_directory=True,
    )
    discovery = MagicMock(address="AA:BB:CC:DD:EE:FF")
    discovery.name = "MOONSIDE-L1"

    with (
        patch("homeassistant.config_entries.async_process_deps_reqs", new=AsyncMock()),
        patch("custom_components.moonside.async_setup_entry", new=AsyncMock(return_value=True)),
        patch(
            "custom_components.moonside.config_flow.async_discovered_service_info",
            return_value=[discovery],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": source},
            data=discovery if source == "bluetooth" else None,
        )
        assert result["type"] is FlowResultType.FORM
        selection = {CONF_NAME: "Lamp One"}
        if source == "manual":
            selection["device_identifier"] = discovery.address
        elif source == "user":
            selection[CONF_MAC] = discovery.address

        result = await hass.config_entries.flow.async_configure(result["flow_id"], selection)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "cloud"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    expected = {CONF_MAC: discovery.address, CONF_NAME: "Lamp One"}
    if source != "manual":
        expected[CONF_BLE_NAME] = discovery.name
    assert result["result"].data == expected
    assert result["result"].options == {}
