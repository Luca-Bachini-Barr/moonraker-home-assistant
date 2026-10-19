"""QIDI Box tests."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN
from custom_components.moonraker.qidi_box import (
    box_label,
    drying_active,
    drying_box_keys,
    slot_attributes,
    slot_filament,
    slot_index,
)

from .const import MOCK_CONFIG

SLOT_OBJECTS = [f"box_stepper slot{i}" for i in range(4)]


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


def _box_response(base, *, objects=None, variables=None, dry_state=0, runout=None):
    """Return an API response with a QIDI Box attached (values from a Q2)."""
    runout = runout or {1: 1}
    default_variables = {
        "filament_slot0": 7,
        "filament_slot1": 7,
        "filament_slot2": 7,
        "filament_slot3": 7,
        "color_slot0": 18,
        "color_slot1": 3,
        "color_slot2": 2,
        "color_slot3": 2,
        "vendor_slot0": 0,
        "vendor_slot1": 1,
        "vendor_slot2": 1,
        "vendor_slot3": 0,
        "slot0": 1,
        "slot1": 0,
        "slot2": 3,
        "slot3": 1,
    }
    status = {
        **base["status"],
        "save_variables": {"variables": variables or default_variables},
        "box_extras": {
            "box_drying_state": {"box1": {"dry_state": dry_state, "end_time": 0}},
            "buffer_state": 1,
        },
    }
    for i in range(4):
        status[f"box_stepper slot{i}"] = {
            "runout_button": runout.get(i, 0),
            "rfid_state": 0,
        }
    return {
        **base,
        "objects": [
            *base["objects"],
            *(
                objects
                if objects is not None
                else ["save_variables", "box_extras", *SLOT_OBJECTS]
            ),
        ],
        "status": status,
    }


async def _setup(hass, response):
    with patch("moonraker_api.MoonrakerClient.call_method", return_value=response):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_slot_filament_sensors(hass, get_default_api_response):
    """Each slot reports the decoded filament, colour and vendor."""
    await _setup(hass, _box_response(get_default_api_response))

    slot1 = hass.states.get("sensor.mainsail_box_slot_1_filament")
    assert slot1.state == "PLA Basic"
    assert slot1.attributes["color"] == "#FF362D"
    assert slot1.attributes["vendor"] == "Generic"
    assert slot1.attributes["filament_id"] == 7
    assert slot1.attributes["color_id"] == 18
    assert slot1.attributes["slot_state"] == 1
    assert slot1.attributes["runout"] is False

    slot2 = hass.states.get("sensor.mainsail_box_slot_2_filament")
    assert slot2.state == "Empty"
    assert slot2.attributes["runout"] is True
    assert slot2.attributes["vendor"] == "QIDI"

    slot3 = hass.states.get("sensor.mainsail_box_slot_3_filament")
    assert slot3.state == "PLA Basic"
    assert slot3.attributes["color"] == "#060606"
    assert slot3.attributes["slot_state"] == 3

    assert hass.states.get("sensor.mainsail_box_slot_4_filament") is not None
    assert hass.states.get("sensor.mainsail_box_slot_5_filament") is None


async def test_slot_filament_unknown_codes(hass, get_default_api_response):
    """Codes missing from the lookup tables stay visible and do not crash."""
    variables = {"filament_slot0": 99, "color_slot0": 99, "vendor_slot0": 99}
    response = _box_response(
        get_default_api_response,
        variables=variables,
        objects=["save_variables", "box_stepper slot0"],
    )
    await _setup(hass, response)

    slot = hass.states.get("sensor.mainsail_box_slot_1_filament")
    assert slot.state == "Unknown (99)"
    assert slot.attributes["color"] is None
    assert slot.attributes["vendor"] is None
    assert slot.attributes["filament_id"] == 99


async def test_slot_sensors_need_save_variables(hass, get_default_api_response):
    """Without save_variables there is nothing to decode, so no sensors."""
    response = _box_response(
        get_default_api_response, objects=["box_stepper slot0", "box_stepper slot1"]
    )
    await _setup(hass, response)

    assert hass.states.get("sensor.mainsail_box_slot_1_filament") is None


@pytest.mark.parametrize(("dry_state", "expected"), [(0, "off"), (1, "on")])
async def test_box_drying_binary_sensor(
    hass, get_default_api_response, dry_state, expected
):
    """The drying binary sensor follows box_extras.box_drying_state."""
    await _setup(hass, _box_response(get_default_api_response, dry_state=dry_state))

    assert hass.states.get("binary_sensor.mainsail_box_1_drying").state == expected


async def test_box_extras_without_drying_state(hass, get_default_api_response):
    """A box_extras object without drying data creates no binary sensor."""
    response = _box_response(get_default_api_response)
    response["status"]["box_extras"] = {"buffer_state": 1}
    await _setup(hass, response)

    assert hass.states.get("binary_sensor.mainsail_box_1_drying") is None


def test_slot_index():
    """Only box_stepper slot objects have a slot index."""
    assert slot_index("box_stepper slot3") == 3
    assert slot_index("box_stepper slot12") == 12
    assert slot_index("stepper_x") is None
    assert slot_index("box_stepper other") is None


def test_box_label():
    """Box keys are turned into readable labels."""
    assert box_label("box1") == "Box 1"
    assert box_label("front_box") == "Front Box"


def test_helpers_handle_missing_data():
    """Missing or malformed status never raises."""
    assert slot_filament({}, 0) is None
    assert slot_filament({"save_variables": {"variables": None}}, 0) is None
    assert slot_filament({"save_variables": "bad"}, 0) is None
    assert slot_attributes({}, 0) == {
        "color": None,
        "vendor": None,
        "filament_id": None,
        "filament_type": None,
        "min_temp": None,
        "max_temp": None,
        "color_id": None,
        "slot_state": None,
        "runout": False,
    }
    assert drying_active({}, "box1") is False
    assert drying_active({"box_extras": "bad"}, "box1") is False
    assert drying_active({"box_extras": {"box_drying_state": "bad"}}, "box1") is False
    assert (
        drying_active({"box_extras": {"box_drying_state": {"box1": 1}}}, "box1")
        is False
    )
    assert (
        drying_active({"box_extras": {"box_drying_state": {"box1": {}}}}, "box1")
        is False
    )
    assert (
        drying_active(
            {"box_extras": {"box_drying_state": {"box1": {"dry_state": None}}}}, "box1"
        )
        is False
    )


def _info(filament, colour, vendor="QIDI", filament_type="PLA"):
    return {
        "index": 0,
        "filament_id": "QFA00",
        "vendor_str": vendor,
        "filament_str": filament,
        "filament_type": filament_type,
        "color_rgb_str": [colour],
        "min_temp": 190,
        "max_temp": 240,
    }


def _new_firmware_response(base, *, dry_state=0):
    """Return a response in the newer QIDI firmware format (values from a Q2)."""
    response = _box_response(
        base,
        variables={
            "filament_slot0": "QFA00",
            "filament_slot1": 7,
            "filament_slot2": "QFA00",
            "filament_slot3": 7,
            "color_slot0": ["F28636"],
            "color_slot1": 3,
            "color_slot2": ["060606"],
            "color_slot3": 2,
            "vendor_slot0": 0,
            "vendor_slot1": 1,
            "vendor_slot2": 1,
            "vendor_slot3": 0,
            "slot0": 2,
            "slot1": 0,
            "slot2": 1,
            "slot3": 1,
        },
    )
    offline = {"is_online": 0, "dry_state": 0, "filament_info": []}
    response["status"]["box_extras"] = {
        "loaded_slot": "slot0",
        "boxes": [
            {
                "is_online": 1,
                "dry_state": dry_state,
                "filament_info": [
                    _info("PLA Basic", "#F28636"),
                    _info("PLA Basic", "#FAFAFA"),
                    _info("PLA Matte", "#060606"),
                    _info("PETG Basic", "#FAFAFA", "Generic", "PETG"),
                ],
            },
            offline,
            offline,
            offline,
        ],
    }
    return response


async def test_slot_sensors_new_firmware(hass, get_default_api_response):
    """Newer firmware reports list colours and string codes without crashing."""
    await _setup(hass, _new_firmware_response(get_default_api_response))

    slot1 = hass.states.get("sensor.mainsail_box_slot_1_filament")
    assert slot1.state == "PLA Basic"
    assert slot1.attributes["color"] == "#F28636"
    assert slot1.attributes["vendor"] == "QIDI"
    assert slot1.attributes["filament_id"] == "QFA00"
    assert slot1.attributes["filament_type"] == "PLA"
    assert slot1.attributes["min_temp"] == 190
    assert slot1.attributes["max_temp"] == 240
    assert slot1.attributes["color_id"] == ["F28636"]

    assert hass.states.get("sensor.mainsail_box_slot_2_filament").state == "Empty"

    slot3 = hass.states.get("sensor.mainsail_box_slot_3_filament")
    assert slot3.state == "PLA Matte"
    assert slot3.attributes["color"] == "#060606"

    slot4 = hass.states.get("sensor.mainsail_box_slot_4_filament")
    assert slot4.state == "PETG Basic"
    assert slot4.attributes["vendor"] == "Generic"


@pytest.mark.parametrize(("dry_state", "expected"), [(0, "off"), (1, "on")])
async def test_box_drying_new_firmware(
    hass, get_default_api_response, dry_state, expected
):
    """Drying state is read from box_extras.boxes; offline boxes are skipped."""
    await _setup(
        hass, _new_firmware_response(get_default_api_response, dry_state=dry_state)
    )

    assert hass.states.get("binary_sensor.mainsail_box_1_drying").state == expected
    assert hass.states.get("binary_sensor.mainsail_box_2_drying") is None


def test_new_firmware_helpers_fallbacks():
    """String codes and hex colours without filament_info still decode safely."""
    status = {
        "save_variables": {
            "variables": {
                "filament_slot0": "QFA00",
                "color_slot0": ["F28636"],
                "vendor_slot0": "odd",
                "filament_slot1": 7,
                "color_slot1": "#060606",
                "color_slot2": [],
                "color_slot3": None,
            }
        },
        "box_extras": {"boxes": "bad"},
    }
    assert slot_filament(status, 0) == "QFA00"
    attributes = slot_attributes(status, 0)
    assert attributes["color"] == "#F28636"
    assert attributes["vendor"] is None
    assert slot_filament(status, 1) == "PLA Basic"
    assert slot_attributes(status, 1)["color"] == "#060606"
    assert slot_attributes(status, 2)["color"] is None
    assert slot_attributes(status, 3)["color"] is None


def test_new_firmware_drying_helpers():
    """Drying helpers handle the boxes list and malformed entries."""
    status = {
        "box_extras": {
            "boxes": [
                {"is_online": 1, "dry_state": 1},
                {"is_online": 0, "dry_state": 1},
                "bad",
                {"is_online": 1},
            ]
        }
    }
    assert drying_box_keys(status) == ["box1"]
    assert drying_active(status, "box1") is True
    assert drying_active(status, "box2") is True
    assert drying_active(status, "box3") is False
    assert drying_active(status, "box9") is False
    assert drying_active(status, "front_box") is False
    assert drying_box_keys({}) == []
    assert drying_box_keys(
        {"box_extras": {"box_drying_state": {"box1": {"dry_state": 0}}}}
    ) == ["box1"]
    assert (
        slot_filament({"box_extras": {"boxes": [{"filament_info": "bad"}]}}, 0) is None
    )
    assert (
        slot_filament({"box_extras": {"boxes": [{"filament_info": ["bad"]}]}}, 0)
        is None
    )
