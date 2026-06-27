from __future__ import annotations

from copy import deepcopy
from typing import Any

from simulation.core.db._airbases import AirbaseDb
from simulation.core.db._aircraft import AircraftDb
from simulation.core.db._aircraft_cn import AircraftCnDb
from simulation.core.db._facilities import FacilityDb
from simulation.core.db._ground_vehicles import GroundVehicleDb
from simulation.core.db._ships import ShipDb
from simulation.core.db._weapons import WeaponDb


AllAircraftDb = AircraftDb + AircraftCnDb

_UNIT_DBS: dict[str, list[dict[str, Any]]] = {
    "aircraft": AllAircraftDb,
    "ship": ShipDb,
    "facility": FacilityDb,
    "airbase": AirbaseDb,
    "ground_vehicle": GroundVehicleDb,
}

_CATEGORY_FALLBACKS = {
    "aircraft": "F-35A Lightning II",
    "ship": "Destroyer",
    "facility": "HQ-9",
    "ground_vehicle": "HIMARS",
}

_MPH_TO_KNOTS = 0.868976

_CATEGORY_EM_DEFAULTS: dict[str, dict[str, Any]] = {
    "aircraft": {
        "radar_on": True,
        "rcs": 1.0,
        "jammer_power": 0.0,
        "jammer_range_nm": 0.0,
        "ew_resistance": 0.15,
    },
    "ship": {
        "radar_on": True,
        "rcs": 8.0,
        "jammer_power": 0.2,
        "jammer_range_nm": 40.0,
        "ew_resistance": 0.2,
    },
    "facility": {
        "radar_on": True,
        "rcs": 5.0,
        "jammer_power": 0.15,
        "jammer_range_nm": 30.0,
        "ew_resistance": 0.25,
    },
    "airbase": {
        "radar_on": False,
        "rcs": 10.0,
        "jammer_power": 0.0,
        "jammer_range_nm": 0.0,
        "ew_resistance": 0.1,
    },
    "ground_vehicle": {
        "radar_on": False,
        "rcs": 2.0,
        "jammer_power": 0.0,
        "jammer_range_nm": 0.0,
        "ew_resistance": 0.12,
    },
}

_CATEGORY_COMMS_DEFAULTS: dict[str, dict[str, Any]] = {
    "aircraft": {
        "comms_on": True,
        "comms_range_nm": 120.0,
        "datalink": True,
        "command_node": False,
        "comms_power": 1.0,
        "comms_resistance": 0.15,
        "contact_share_delay_s": 2.0,
    },
    "ship": {
        "comms_on": True,
        "comms_range_nm": 220.0,
        "datalink": True,
        "command_node": True,
        "comms_power": 1.2,
        "comms_resistance": 0.25,
        "contact_share_delay_s": 1.0,
    },
    "facility": {
        "comms_on": True,
        "comms_range_nm": 180.0,
        "datalink": True,
        "command_node": True,
        "comms_power": 1.1,
        "comms_resistance": 0.3,
        "contact_share_delay_s": 1.0,
    },
    "airbase": {
        "comms_on": True,
        "comms_range_nm": 260.0,
        "datalink": True,
        "command_node": True,
        "comms_power": 1.3,
        "comms_resistance": 0.35,
        "contact_share_delay_s": 1.0,
    },
    "ground_vehicle": {
        "comms_on": True,
        "comms_range_nm": 90.0,
        "datalink": True,
        "command_node": False,
        "comms_power": 1.0,
        "comms_resistance": 0.15,
        "contact_share_delay_s": 2.0,
    },
}


def get_unit_attributes(unit_type: str, class_name: str | None = None) -> dict[str, Any]:
    entry = _find_unit_entry(unit_type, class_name)
    if entry is None:
        defaults = _category_em_defaults(unit_type)
        defaults.update(_category_comms_defaults(unit_type))
        return defaults
    return _normalize_unit_entry(unit_type, entry)


def get_weapon_attributes(class_name: str | None) -> dict[str, Any]:
    if not class_name:
        return {}
    entry = _find_entry(WeaponDb, class_name)
    if entry is None:
        return {}
    return _normalize_weapon_entry(entry)


def _find_unit_entry(unit_type: str, class_name: str | None) -> dict[str, Any] | None:
    normalized_type = (unit_type or "").lower()
    entries = _UNIT_DBS.get(normalized_type, [])
    if not entries:
        return None
    entry = _find_entry(entries, class_name)
    if entry is not None:
        return entry
    fallback = _CATEGORY_FALLBACKS.get(normalized_type)
    return _find_entry(entries, fallback)


def _find_entry(entries: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    needle = _normalize_name(name)
    for entry in entries:
        candidate = entry.get("class_name", entry.get("className", entry.get("name", "")))
        if _normalize_name(str(candidate)) == needle:
            return entry
    for entry in entries:
        candidate = str(entry.get("class_name", entry.get("className", entry.get("name", ""))))
        candidate_norm = _normalize_name(candidate)
        if needle in candidate_norm or candidate_norm in needle:
            return entry
    return None


def _normalize_name(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _normalize_unit_entry(unit_type: str, entry: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(entry)
    class_name = normalized.get("class_name", normalized.get("className", normalized.get("name", "")))
    result: dict[str, Any] = {
        "class_name": class_name,
    }
    result.update(_category_em_defaults(unit_type))
    result.update(_category_comms_defaults(unit_type))
    if "speed" in normalized:
        speed = float(normalized["speed"])
        if _speed_unit(normalized) == "mph":
            speed *= _MPH_TO_KNOTS
        result["speed"] = speed
    if "max_fuel" in normalized:
        result["max_fuel"] = float(normalized["max_fuel"])
    if "maxFuel" in normalized:
        result["max_fuel"] = float(normalized["maxFuel"])
    if "fuel_rate" in normalized:
        result["fuel_rate"] = float(normalized["fuel_rate"])
    if "fuelRate" in normalized:
        result["fuel_rate"] = float(normalized["fuelRate"])
    if "range" in normalized:
        range_nm = float(normalized["range"])
        result["range_nm"] = range_nm
        result["detection_range_nm"] = range_nm
    _copy_float_field(normalized, result, "detection_range_nm", "detectionRangeNm")
    _copy_bool_field(normalized, result, "radar_on", "radarOn")
    _copy_float_field(normalized, result, "rcs")
    _copy_float_field(normalized, result, "jammer_power", "jammerPower")
    _copy_float_field(normalized, result, "jammer_range_nm", "jammerRangeNm")
    _copy_float_field(normalized, result, "ew_resistance", "ewResistance")
    _copy_bool_field(normalized, result, "comms_on", "commsOn")
    _copy_float_field(normalized, result, "comms_range_nm", "commsRangeNm")
    _copy_bool_field(normalized, result, "datalink")
    _copy_bool_field(normalized, result, "command_node", "commandNode")
    _copy_float_field(normalized, result, "comms_power", "commsPower")
    _copy_float_field(normalized, result, "comms_resistance", "commsResistance")
    _copy_float_field(normalized, result, "contact_share_delay_s", "contactShareDelayS")
    if unit_type == "airbase":
        result.setdefault("speed", 0.0)
        result.setdefault("range_nm", 0.0)
        result.setdefault("detection_range_nm", 0.0)
    return result


def _category_em_defaults(unit_type: str) -> dict[str, Any]:
    return dict(_CATEGORY_EM_DEFAULTS.get((unit_type or "").lower(), {}))


def _category_comms_defaults(unit_type: str) -> dict[str, Any]:
    return dict(_CATEGORY_COMMS_DEFAULTS.get((unit_type or "").lower(), {}))


def _copy_float_field(source: dict[str, Any], target: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if key in source:
            target[keys[0]] = float(source[key])
            return


def _copy_bool_field(source: dict[str, Any], target: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if key in source:
            target[keys[0]] = _read_bool(source[key])
            return


def _read_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _normalize_weapon_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(entry)
    result: dict[str, Any] = {
        "weapon_class": normalized.get("class_name", normalized.get("className", "")),
        "name": normalized.get("class_name", normalized.get("className", "Weapon")),
    }
    if "speed" in normalized:
        result["speed"] = float(normalized["speed"])
    if "range" in normalized:
        result["range_nm"] = float(normalized["range"])
    if "range_nm" in normalized:
        result["range_nm"] = float(normalized["range_nm"])
    if "lethality" in normalized:
        result["lethality"] = float(normalized["lethality"])
    return result


def _speed_unit(entry: dict[str, Any]) -> str:
    units = entry.get("units", {})
    if not isinstance(units, dict):
        return ""
    return str(units.get("speed_unit", units.get("speedUnit", ""))).lower()


__all__ = [
    "AircraftDb",
    "AircraftCnDb",
    "AllAircraftDb",
    "ShipDb",
    "FacilityDb",
    "AirbaseDb",
    "GroundVehicleDb",
    "WeaponDb",
    "get_unit_attributes",
    "get_weapon_attributes",
]
