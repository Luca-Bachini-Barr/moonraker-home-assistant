"""Test fast polling during QIDI Box filament changes and after send_gcode."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, PRINTSTATES

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


@pytest.fixture
async def coordinator(hass, get_data):
    """Set up a Moonraker entry in standby and return its coordinator."""
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="fast")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][config_entry.entry_id]


async def test_fast_polling_during_box_filament_change(coordinator, get_data):
    """A running Box filament change (printer in standby) polls every 2 s."""
    assert coordinator.update_interval == timedelta(seconds=30)

    with patch.object(coordinator, "_schedule_refresh") as mock_refresh:
        get_data["status"]["multi_color_controller"] = {
            "task": {"flow_id": "f1", "current_step": "BOX_LOAD"}
        }
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=2)
        assert mock_refresh.called

        mock_refresh.reset_mock()
        get_data["status"]["multi_color_controller"] = {
            "task": {"flow_id": None, "current_step": ""}
        }
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=30)
        assert mock_refresh.called


async def test_poll_fast_for_window(coordinator):
    """poll_fast_for polls every 2 s until the window ends."""
    with (
        patch.object(coordinator, "_schedule_refresh") as mock_refresh,
        patch("custom_components.moonraker.time.monotonic", return_value=100.0),
    ):
        coordinator.poll_fast_for(30)
        assert coordinator.update_interval == timedelta(seconds=2)
        assert mock_refresh.call_count == 1

        # Already polling fast: just extends the window.
        coordinator.poll_fast_for(30)
        assert mock_refresh.call_count == 1

        # Still inside the window: stays fast.
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=2)

    with (
        patch.object(coordinator, "_schedule_refresh"),
        patch("custom_components.moonraker.time.monotonic", return_value=200.0),
    ):
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=30)


async def test_send_gcode_starts_fast_polling(hass, coordinator):
    """Sending G-code switches to fast polling so the action shows promptly."""
    device_id = list(hass.data["device_registry"].devices.keys())[0]
    with (
        patch.object(coordinator, "_schedule_refresh"),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {"device_id": device_id, "gcode": "LOAD_FILAMENT_CONTROL SLOT=0"},
            blocking=True,
        )
    assert coordinator.update_interval == timedelta(seconds=2)
