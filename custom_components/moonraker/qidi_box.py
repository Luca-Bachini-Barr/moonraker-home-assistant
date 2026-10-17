"""Helpers for the QIDI Box multi-filament feeder exposed through Moonraker.

The QIDI Box adds ``box_stepper slotN`` and ``box_extras`` objects to Klipper
and stores the per-slot filament selection in ``save_variables`` as numeric
codes. The lookup tables below mirror the printer's own
``officiall_filas_list.cfg`` (``[filaN]``, ``[colordict]`` and
``[vendor_list]`` sections) and are only used to turn those codes into
readable values.
"""

import re
from typing import Any

FILAMENTS = {
    1: "PLA Rapido",
    2: "PLA Matte",
    3: "PLA Metal",
    4: "PLA Silk",
    5: "PLA-CF",
    6: "PLA-Wood",
    7: "PLA Basic",
    8: "PLA Matte Basic",
    10: "Support For PLA",
    11: "ABS Rapido",
    12: "ABS-GF",
    13: "ABS-Metal",
    14: "ABS-Odorless",
    15: "TPU-GF",
    18: "ASA",
    19: "ASA-Aero",
    20: "ASA-CF",
    23: "PC",
    24: "UltraPA",
    25: "PA6-CF",
    26: "UltraPA-CF25",
    27: "PA12-CF",
    30: "PAHT-CF",
    31: "PAHT-GF",
    32: "Support For PAHT",
    33: "Support For PET/PA",
    34: "PC/ABS-FR",
    35: "TPEE",
    36: "PEBA",
    37: "PET-CF",
    38: "PET-GF",
    39: "PETG Basic",
    40: "PETG-Tough",
    41: "PETG Rapido",
    42: "PETG-CF",
    43: "PETG-GF",
    44: "PPS-CF",
    45: "PETG Translucent",
    46: "PPS-GF",
    47: "PVA",
    48: "TPU-AERO 64D",
    49: "TPU-Aero",
    50: "TPU 95A-HF",
}
COLORS = {
    1: "#FAFAFA",
    2: "#060606",
    3: "#D9E3ED",
    4: "#5CF30F",
    5: "#63E492",
    6: "#2850FF",
    7: "#FE98FE",
    8: "#DFD628",
    9: "#228332",
    10: "#99DEFF",
    11: "#1714B0",
    12: "#CEC0FE",
    13: "#CADE4B",
    14: "#1353AB",
    15: "#5EA9FD",
    16: "#A878FF",
    17: "#FE717A",
    18: "#FF362D",
    19: "#E2DFCD",
    20: "#898F9B",
    21: "#6E3812",
    22: "#CAC59F",
    23: "#F28636",
    24: "#B87F2B",
}
VENDORS = {
    0: "Generic",
    1: "QIDI",
}


_SLOT_RE = re.compile(r"^box_stepper slot(\d+)$")
_BOX_RE = re.compile(r"^box(\d+)$")


def slot_index(obj: str) -> int | None:
    """Return the slot number for a ``box_stepper slotN`` object, else None."""
    match = _SLOT_RE.match(obj)
    return int(match.group(1)) if match else None


def box_label(box_key: str) -> str:
    """Return a readable label such as ``Box 1`` for a ``box1`` key."""
    match = _BOX_RE.match(box_key)
    if match:
        return f"Box {match.group(1)}"
    return box_key.replace("_", " ").title()


def _variables(status: dict[str, Any]) -> dict[str, Any]:
    save_variables = status.get("save_variables")
    variables = (
        save_variables.get("variables") if isinstance(save_variables, dict) else None
    )
    return variables if isinstance(variables, dict) else {}


def slot_is_empty(status: dict[str, Any], index: int) -> bool:
    """Return True when the slot's runout switch reports no filament."""
    stepper = status.get(f"box_stepper slot{index}")
    return isinstance(stepper, dict) and stepper.get("runout_button") == 1


def slot_filament(status: dict[str, Any], index: int) -> str | None:
    """Return the filament name loaded in a slot, or ``Empty``."""
    if slot_is_empty(status, index):
        return "Empty"
    code = _variables(status).get(f"filament_slot{index}")
    if code is None:
        return None
    return FILAMENTS.get(code, f"Unknown ({code})")


def slot_attributes(status: dict[str, Any], index: int) -> dict[str, Any]:
    """Return decoded slot details for use as entity attributes."""
    variables = _variables(status)
    color_id = variables.get(f"color_slot{index}")
    vendor_id = variables.get(f"vendor_slot{index}")
    return {
        "color": COLORS.get(color_id),
        "vendor": VENDORS.get(vendor_id),
        "filament_id": variables.get(f"filament_slot{index}"),
        "color_id": color_id,
        "slot_state": variables.get(f"slot{index}"),
        "runout": slot_is_empty(status, index),
    }


def drying_active(status: dict[str, Any], box_key: str) -> bool:
    """Return True when the box reports a non-idle drying state."""
    extras = status.get("box_extras")
    drying = extras.get("box_drying_state") if isinstance(extras, dict) else None
    state = drying.get(box_key) if isinstance(drying, dict) else None
    return isinstance(state, dict) and bool(state.get("dry_state"))
