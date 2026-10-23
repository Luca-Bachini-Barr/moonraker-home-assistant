"""Test send_gcode error reporting and wait=False for long commands."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import _gcode_error, _log_gcode_result
from custom_components.moonraker.const import DOMAIN, METHODS

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
async def device_id(hass):
    """Set up a Moonraker entry and return its device id."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="gcode")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return list(hass.data["device_registry"].devices.keys())[0]


async def _send(hass, device_id, **extra):
    await hass.services.async_call(
        DOMAIN,
        "send_gcode",
        {"device_id": device_id, "gcode": "LOAD_FILAMENT_CONTROL SLOT=2", **extra},
        blocking=True,
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({"code": 400, "message": "unable to parse slot2"}, "unable to parse slot2"),
        ("Klippy Disconnected", "Klippy Disconnected"),
    ],
)
async def test_send_gcode_raises_klipper_error(hass, device_id, error, expected):
    """A Klipper error in the RPC result is raised with its message."""
    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            return_value={"error": error},
        ),
        pytest.raises(HomeAssistantError, match=expected),
    ):
        await _send(hass, device_id)


async def test_send_gcode_success_returns(hass, device_id):
    """A normal "ok" result does not raise."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        new_callable=AsyncMock,
        return_value="ok",
    ) as mock_call:
        await _send(hass, device_id)
    mock_call.assert_awaited_once_with(
        METHODS.PRINTER_GCODE_SCRIPT.value, script="LOAD_FILAMENT_CONTROL SLOT=2"
    )


async def test_send_gcode_timeout_message(hass, device_id):
    """The request timeout is reported as "did not finish in time"."""
    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError,
        ),
        pytest.raises(HomeAssistantError, match="did not finish in time"),
    ):
        await _send(hass, device_id)


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        (RuntimeError("socket closed"), "failed: socket closed"),
        (RuntimeError(), "could not be sent to Moonraker"),
    ],
)
async def test_send_gcode_exception_message(hass, device_id, side_effect, expected):
    """Other exceptions keep their message, or get a generic one."""
    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=side_effect,
        ),
        pytest.raises(HomeAssistantError, match=expected),
    ):
        await _send(hass, device_id)


async def test_send_gcode_no_wait_reports_fast_error(hass, device_id):
    """With wait=False an error returned straight away is still raised."""
    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            return_value={"error": {"message": "unable to parse slot2"}},
        ),
        pytest.raises(HomeAssistantError, match="unable to parse slot2"),
    ):
        await _send(hass, device_id, wait=False)


@pytest.mark.parametrize(
    ("outcome", "level", "logged"),
    [
        ("ok", logging.DEBUG, "finished"),
        ({"error": {"message": "Filament runout"}}, logging.ERROR, "Filament runout"),
    ],
)
async def test_send_gcode_no_wait_returns_before_long_command(
    hass, device_id, caplog, outcome, level, logged
):
    """With wait=False a long command returns early and its outcome is logged."""
    release = asyncio.Event()

    async def slow_call(*_args, **_kwargs):
        await release.wait()
        return outcome

    caplog.set_level(logging.DEBUG, logger="custom_components.moonraker")
    with (
        patch("custom_components.moonraker.GCODE_ACCEPT_TIMEOUT", 0.01),
        patch("moonraker_api.MoonrakerClient.call_method", side_effect=slow_call),
    ):
        await _send(hass, device_id, wait=False)
        assert not release.is_set()
        release.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert any(r.levelno == level and logged in r.getMessage() for r in caplog.records)


def test_gcode_error_timeout_and_plain_exceptions():
    """_gcode_error maps a timeout to None and keeps other messages."""
    timeout = UpdateFailed()
    timeout.__cause__ = asyncio.TimeoutError()
    assert _gcode_error("G28", timeout) is None
    assert _gcode_error("G28", ValueError("bad")) == "G-code 'G28' failed: bad"


async def test_log_gcode_result_exceptions(caplog):
    """Late failures are logged: timeouts at debug, other errors at error."""
    caplog.set_level(logging.DEBUG, logger="custom_components.moonraker")

    async def fail(exc):
        raise exc

    timeout = UpdateFailed()
    timeout.__cause__ = asyncio.TimeoutError()
    broken = UpdateFailed()
    broken.__cause__ = RuntimeError("socket closed")
    for exc in (timeout, broken):
        task = asyncio.ensure_future(fail(exc))
        with pytest.raises(UpdateFailed):
            await task
        _log_gcode_result("G28", task)

    messages = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert (
        logging.DEBUG,
        "G-code 'G28' still running after the request timed out",
    ) in messages
    assert (logging.ERROR, "G-code 'G28' failed: socket closed") in messages


async def test_log_gcode_result_cancelled(caplog):
    """A cancelled task (e.g. on shutdown) is not logged."""
    task = asyncio.ensure_future(asyncio.sleep(10))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    _log_gcode_result("G28", task)
    assert not caplog.records
