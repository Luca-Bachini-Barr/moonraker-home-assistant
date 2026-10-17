"""Number heater_generic setup tests."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_heater_generic_without_config_section(hass, get_default_api_response):
    """A heater_generic missing from configfile settings still gets a target."""
    heater = "heater_generic runtime_heater"
    response = {
        **get_default_api_response,
        "objects": [*get_default_api_response["objects"], heater],
        "status": {
            **get_default_api_response["status"],
            heater: {"temperature": 29.9, "target": 40.0, "power": 0.0},
        },
    }

    with patch("moonraker_api.MoonrakerClient.call_method", return_value=response):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_runtime_heater_target")
    assert state is not None
    assert state.state == "40.0"
    assert state.attributes["min"] == 0.0
    assert state.attributes["max"] == 100.0
    # Entities defined by a config section keep their configured limits.
    assert (
        hass.states.get("number.mainsail_my_super_heater_target").attributes["max"]
        == 90.0
    )
