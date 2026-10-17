"""Number output pin setup tests."""

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


async def test_output_pin_setup_skips_objects_without_config(
    hass, get_default_api_response
):
    """Objects that are not plain output pins must not abort number setup."""
    response = {
        **get_default_api_response,
        "objects": [
            *get_default_api_response["objects"],
            # Vendor firmware object that merely contains "output_pin".
            "smart_output_pin caselight",
            # Real output pin that is missing from configfile settings.
            "output_pin unconfigured",
        ],
    }

    with patch("moonraker_api.MoonrakerClient.call_method", return_value=response):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # The remaining number entities are still created.
    assert hass.states.get("number.mainsail_output_pin_pwm") is not None
    assert hass.states.get("number.mainsail_speed_factor") is not None
    assert hass.states.get("number.mainsail_bed_target") is not None
    assert hass.states.get("number.mainsail_smart_output_pin_caselight") is None
    assert hass.states.get("number.mainsail_output_pin_unconfigured") is None
