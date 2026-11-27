"""Tests for the QIDI Box slot filament sensors."""

import copy
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.moonraker import qidi_box
from custom_components.moonraker.const import DOMAIN
from custom_components.moonraker.binary_sensor import (
    async_setup_qidi_box_binary_sensors,
)
from custom_components.moonraker.sensor import async_setup_qidi_box_sensors

from .const import MOCK_CONFIG

# A real Q2 with one Box (printer/objects/query, trimmed): slots 1-2 empty, slot 3 PLA Basic black, slot 4 PLA Basic
# black, nothing from the Box in the toolhead (loaded_slot slot16).
BOX_STATUS = {
    "box_extras": {
        "last_load_slot": "slot16",
        "loaded_slot": "slot16",
        "boxes": [
            {
                "aht20_humidity": 51,
                "aht20_temp": 21.06,
                "filament_info": [
                    {
                        "vendor_str": "Generic",
                        "filament_str": "PLA",
                        "filament_type": "PLA",
                        "color_rgb_str": ["#F28636"],
                        "min_temp": 190,
                        "max_temp": 240,
                    },
                    {
                        "vendor_str": "QIDI",
                        "filament_str": "PLA Basic",
                        "filament_type": "PLA",
                        "color_rgb_str": ["#FAFAFA"],
                        "min_temp": 190,
                        "max_temp": 240,
                    },
                    {
                        "vendor_str": "QIDI",
                        "filament_str": "PLA Basic",
                        "filament_type": "PLA",
                        "color_rgb_str": ["#060606"],
                        "min_temp": 190,
                        "max_temp": 240,
                    },
                    {
                        "vendor_str": "QIDI",
                        "filament_str": "PLA Basic",
                        "filament_type": "PLA",
                        "color_rgb_str": ["#060606"],
                        "min_temp": 190,
                        "max_temp": 240,
                    },
                ],
            }
        ],
    },
    "save_variables": {
        "variables": {
            "color_slot0": ["F28636"],
            "color_slot1": 3,
            "color_slot2": ["060606"],
            "color_slot3": ["060606"],
            "filament_slot0": "QFA90",
            "filament_slot1": 7,
            "filament_slot2": "QFA00",
            "filament_slot3": "QFA00",
            "slot0": 0,
            "slot1": 0,
            "slot2": 1,
            "slot3": 1,
            "vendor_slot0": 0,
            "vendor_slot1": 1,
            "vendor_slot2": 1,
            "vendor_slot3": 0,
        }
    },
    "box_stepper slot0": {"runout_button": 1},
    "box_stepper slot1": {"runout_button": 1},
    "box_stepper slot2": {"runout_button": 0},
    "box_stepper slot3": {"runout_button": 0},
    "multi_color_controller": {
        "task": {
            "flow_id": None,
            "current_queue": [],
            "current_step": "",
            "is_paused": False,
        },
        "operation": {
            "box_button_state": 0,
            "operate_state": 0,
            "active_slot": "slot16",
        },
        "box_warning_info": [],
    },
}
BOX_STATUS["box_extras"]["is_tool_change"] = 0
BOX_STATUS["box_extras"]["boxes"][0]["is_online"] = 1
BOX_STATUS["box_extras"]["boxes"][0]["dry_state"] = 0
BOX_OBJECTS = ["box_extras", "save_variables", "multi_color_controller"] + [
    f"box_stepper slot{i}" for i in range(4)
]


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


def box_status():
    """Return a copy of the Box status to change in a test."""
    return copy.deepcopy(BOX_STATUS)


# ---- the helpers ----


def test_slot_indices():
    """Slots come from box_stepper objects, and only with box_extras."""
    assert qidi_box.slot_indices(BOX_OBJECTS) == [0, 1, 2, 3]
    assert qidi_box.slot_indices(["box_stepper slot0", "box_stepper slot1"]) == []
    assert qidi_box.slot_indices(["box_extras", "extruder"]) == []
    two_boxes = [*BOX_OBJECTS, "box_stepper slot5", "box_stepper slot4"]
    assert qidi_box.slot_indices(two_boxes) == [0, 1, 2, 3, 4, 5]


def test_slot_filament_and_attributes():
    """An empty slot says Empty with no colour; a loaded one its filament details."""
    status = box_status()
    assert qidi_box.slot_filament(status, 0) == "Empty"
    assert qidi_box.slot_attributes(status, 0)["color"] is None
    assert qidi_box.slot_attributes(status, 0)["runout"] is True
    assert qidi_box.slot_filament(status, 2) == "PLA Basic"
    attributes = qidi_box.slot_attributes(status, 2)
    assert attributes["color"] == "#060606"
    assert attributes["vendor"] == "QIDI"
    assert attributes["filament_type"] == "PLA"
    assert attributes["min_temp"] == 190
    assert attributes["max_temp"] == 240
    assert attributes["active"] is False
    assert attributes["runout"] is False


def test_active_slot():
    """loaded_slot decides which slot feeds the toolhead; slot16 is none."""
    status = box_status()
    assert not any(qidi_box.slot_is_active(status, i) for i in range(4))
    status["box_extras"]["loaded_slot"] = "slot3"
    assert qidi_box.slot_is_active(status, 3)
    # a stale save_variables marker does not win over loaded_slot
    status["save_variables"]["variables"]["slot2"] = 2
    assert not qidi_box.slot_is_active(status, 2)
    # an empty slot never feeds the toolhead
    status["box_extras"]["loaded_slot"] = "slot0"
    assert not qidi_box.slot_is_active(status, 0)
    # firmware without loaded_slot: the save_variables marker
    del status["box_extras"]["loaded_slot"]
    assert qidi_box.slot_is_active(status, 2)


def test_old_firmware_codes():
    """Older firmware stores numeric codes in save_variables only."""
    status = {
        "save_variables": {
            "variables": {
                "filament_slot0": 7,
                "color_slot0": 18,
                "vendor_slot0": 1,
                "filament_slot1": 99,
                "filament_slot2": "QFA00",
            }
        },
        "box_stepper slot0": {"runout_button": 0},
    }
    assert qidi_box.slot_filament(status, 0) == "PLA Basic"
    attributes = qidi_box.slot_attributes(status, 0)
    assert attributes["color"] == "#FF362D"
    assert attributes["vendor"] == "QIDI"
    assert qidi_box.slot_filament(status, 1) == "Unknown (99)"
    assert qidi_box.slot_filament(status, 2) == "QFA00"
    assert qidi_box.slot_filament(status, 3) == "Unknown"


def test_change_state():
    """A change reports its step; idle without one; changing while is_tool_change."""
    status = box_status()
    assert qidi_box.change_state(status) == "idle"
    status["box_extras"]["is_tool_change"] = 1
    assert qidi_box.change_state(status) == "changing"
    task = status["multi_color_controller"]["task"]
    task["flow_id"] = 3
    assert qidi_box.change_state(status) == "starting"
    task["current_step"] = "BOX_UNLOAD"
    assert qidi_box.change_state(status) == "unloading"
    task["current_step"] = "BOX_PURGE"
    assert qidi_box.change_state(status) == "purge"
    task["is_paused"] = True
    assert qidi_box.change_state(status) == "paused"
    del status["multi_color_controller"]
    with pytest.raises(KeyError):
        qidi_box.change_state(status)


def test_change_attributes():
    """The target slot shows only while a change runs; slots are 1-based."""
    status = box_status()
    assert qidi_box.change_attributes(status) == {
        "target_slot": None,
        "loaded_slot": None,
        "steps": [],
    }
    controller = status["multi_color_controller"]
    controller["task"].update(
        flow_id=7,
        current_step="BOX_LOAD",
        current_queue=["BOX_CUT", "BOX_UNLOAD", "BOX_LOAD", "BOX_EXTRA", 5],
    )
    controller["operation"]["active_slot"] = "slot2"
    status["box_extras"]["loaded_slot"] = "slot0"
    assert qidi_box.change_attributes(status) == {
        "target_slot": 3,
        "loaded_slot": 1,
        "steps": ["cutting", "unloading", "loading", "extra"],
    }
    controller["task"]["current_queue"] = None
    controller["operation"] = None
    assert qidi_box.change_attributes(status)["steps"] == []
    assert qidi_box.change_attributes(status)["target_slot"] is None


def test_box_warnings():
    """Warnings are passed through; a missing controller raises KeyError."""
    status = box_status()
    assert qidi_box.box_warnings(status) == []
    status["multi_color_controller"]["box_warning_info"] = [{"code": 1}]
    assert qidi_box.box_warnings(status) == [{"code": 1}]
    status["multi_color_controller"]["box_warning_info"] = "x"
    assert qidi_box.box_warnings(status) == []
    del status["multi_color_controller"]
    with pytest.raises(KeyError):
        qidi_box.box_warnings(status)


def test_box_drying():
    """dry_state turns drying on; a Box without it raises KeyError."""
    assert qidi_box.box_numbers([0, 1, 2, 3, 4, 7]) == [0, 1]
    status = box_status()
    assert qidi_box.box_is_drying(status, 0) is False
    status["box_extras"]["boxes"][0]["dry_state"] = 1
    assert qidi_box.box_is_drying(status, 0) is True
    with pytest.raises(KeyError):
        qidi_box.box_is_drying(status, 1)
    del status["box_extras"]["boxes"][0]["dry_state"]
    with pytest.raises(KeyError):
        qidi_box.box_is_drying(status, 0)
    with pytest.raises(KeyError):
        qidi_box.box_is_drying({"box_extras": {}}, 0)


# ---- the sensors ----


async def _setup(hass, get_default_api_response, objects, status):
    get_default_api_response["objects"] = [
        *get_default_api_response["objects"],
        *objects,
    ]
    get_default_api_response["status"].update(status)
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def test_box_slot_sensors(hass, get_default_api_response):
    """A printer with a Box gets one filament sensor per slot."""
    await _setup(hass, get_default_api_response, BOX_OBJECTS, box_status())

    state = hass.states.get("sensor.mainsail_box_slot_1_filament")
    assert state.state == "Empty"
    assert state.attributes["color"] is None
    state = hass.states.get("sensor.mainsail_box_slot_3_filament")
    assert state.state == "PLA Basic"
    assert state.attributes["color"] == "#060606"
    assert state.attributes["vendor"] == "QIDI"
    assert state.attributes["filament_type"] == "PLA"
    assert state.attributes["active"] is False
    assert state.attributes["min_temp"] == 190
    assert state.attributes["max_temp"] == 240
    assert state.attributes["runout"] is False
    assert hass.states.get("sensor.mainsail_box_slot_1_filament").attributes["runout"]
    assert hass.states.get("sensor.mainsail_box_slot_4_filament").state == "PLA Basic"
    assert hass.states.get("sensor.mainsail_box_slot_5_filament") is None


async def test_no_box_no_sensors(hass, get_default_api_response):
    """A printer without a Box gets no slot sensors, and the rest as before."""
    config_entry = await _setup(hass, get_default_api_response, [], {})

    entries = er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )
    assert not [e for e in entries if "_box_slot" in e.unique_id]
    assert hass.states.get("sensor.mainsail_bed_temperature") is not None


async def test_box_off_is_unavailable(hass, get_default_api_response):
    """A Box that is off reports an empty box_extras: its slots are unavailable."""
    status = box_status()
    status["box_extras"] = {}
    await _setup(hass, get_default_api_response, BOX_OBJECTS, status)

    state = hass.states.get("sensor.mainsail_box_slot_3_filament")
    assert state.state == "unavailable"


async def test_two_boxes(hass, get_default_api_response):
    """A second Box adds slots 5 to 8."""
    status = box_status()
    second = copy.deepcopy(status["box_extras"]["boxes"][0])
    second["filament_info"][0]["filament_str"] = "PETG Basic"
    second["filament_info"][0]["filament_type"] = "PETG"
    status["box_extras"]["boxes"].append(second)
    status["box_extras"]["loaded_slot"] = "slot4"
    objects = [*BOX_OBJECTS] + [f"box_stepper slot{i}" for i in range(4, 8)]
    for i in range(4, 8):
        status[f"box_stepper slot{i}"] = {"runout_button": 0}
    await _setup(hass, get_default_api_response, objects, status)

    state = hass.states.get("sensor.mainsail_box_slot_5_filament")
    assert state.state == "PETG Basic"
    assert state.attributes["filament_type"] == "PETG"
    assert state.attributes["active"] is True
    assert hass.states.get("sensor.mainsail_box_slot_8_filament") is not None


async def test_box_setup_skipped_when_object_list_fails():
    """A failing object list skips the Box sensors instead of failing the platform."""
    coordinator = MagicMock()
    coordinator.async_get_printer_objects_list = AsyncMock(side_effect=UpdateFailed)
    add_entities = MagicMock()

    await async_setup_qidi_box_sensors(coordinator, MagicMock(), add_entities)

    add_entities.assert_not_called()
    coordinator.load_sensor_data.assert_not_called()


async def test_box_change_and_drying_sensors(hass, get_default_api_response):
    """A Box with multi_color_controller gets change, warnings and drying sensors."""
    status = box_status()
    controller = status["multi_color_controller"]
    controller["task"].update(flow_id=2, current_step="BOX_LOAD")
    controller["operation"]["active_slot"] = "slot3"
    controller["box_warning_info"] = ["Slot 4 filament tangled"]
    status["box_extras"]["boxes"][0]["dry_state"] = 1
    await _setup(hass, get_default_api_response, BOX_OBJECTS, status)

    state = hass.states.get("sensor.mainsail_box_filament_change")
    assert state.state == "loading"
    assert state.attributes["target_slot"] == 4
    state = hass.states.get("sensor.mainsail_box_warnings")
    assert state.state == "1"
    assert state.attributes["warnings"] == ["Slot 4 filament tangled"]
    assert hass.states.get("binary_sensor.mainsail_box_1_drying").state == "on"


async def test_box_without_controller(hass, get_default_api_response):
    """Older Box firmware without multi_color_controller: no change or warnings sensors."""
    status = box_status()
    del status["multi_color_controller"]
    objects = [o for o in BOX_OBJECTS if o != "multi_color_controller"]
    await _setup(hass, get_default_api_response, objects, status)

    assert hass.states.get("sensor.mainsail_box_filament_change") is None
    assert hass.states.get("sensor.mainsail_box_warnings") is None
    assert hass.states.get("binary_sensor.mainsail_box_1_drying").state == "off"


async def test_controller_missing_from_status(hass, get_default_api_response):
    """A listed controller that reports nothing leaves its sensors unavailable."""
    status = box_status()
    del status["multi_color_controller"]
    status["box_extras"] = {}
    await _setup(hass, get_default_api_response, BOX_OBJECTS, status)

    state = hass.states.get("sensor.mainsail_box_warnings")
    assert state.state == "unavailable"
    assert "warnings" not in state.attributes
    assert hass.states.get("sensor.mainsail_box_filament_change").state == "unavailable"
    assert hass.states.get("binary_sensor.mainsail_box_1_drying").state == "unavailable"


async def test_box_binary_setup_skipped_when_object_list_fails():
    """A failing object list skips the drying sensors instead of failing the platform."""
    coordinator = MagicMock()
    coordinator.async_get_printer_objects_list = AsyncMock(side_effect=UpdateFailed)
    add_entities = MagicMock()

    await async_setup_qidi_box_binary_sensors(coordinator, MagicMock(), add_entities)

    add_entities.assert_not_called()
