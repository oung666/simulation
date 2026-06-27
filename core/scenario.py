from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from simulation.core.geo import LonLat
from simulation.core.db import get_unit_attributes, get_weapon_attributes
from simulation.core.mission import Mission, PatrolMission, ReferencePoint, StrikeMission, make_reference_point
from simulation.core.weapon import FlyingWeapon, WeaponTemplate


@dataclass(frozen=True)
class UnitRoute:
    points: list[LonLat]


@dataclass
class CombatUnit:
    unit_id: str
    name: str
    side: str
    unit_type: str
    route: UnitRoute
    route_id: str
    motion: str
    position: LonLat | None
    speed: float  # 速度，单位：节 (knots)
    range_nm: float
    altitude_ft: float = 0.0
    heading: float = 0.0
    detection_range_nm: float = 0.0
    weapons: list[WeaponTemplate] = field(default_factory=list)
    target_id: str = ""
    alive: bool = True
    current_fuel: float = 10000.0
    max_fuel: float = 10000.0
    fuel_rate: float = 1.0
    class_name: str = ""
    radar_on: bool = True
    rcs: float = 1.0
    jammer_power: float = 0.0
    jammer_range_nm: float = 0.0
    ew_resistance: float = 0.0
    comms_on: bool = True
    comms_range_nm: float = 0.0
    datalink: bool = True
    command_node: bool = False
    comms_power: float = 1.0
    comms_resistance: float = 0.0
    contact_share_delay_s: float = 0.0


@dataclass
class Scenario:
    name: str
    units: list[CombatUnit]
    flying_weapons: list[FlyingWeapon] = field(default_factory=list)
    reference_points: list[ReferencePoint] = field(default_factory=list)
    missions: list[Mission] = field(default_factory=list)
    start_time: float = 0.0
    duration: float = 14400.0
    time_compression: int = 1


def _read_point(raw: list[float]) -> LonLat:
    return LonLat(float(raw[0]), float(raw[1]))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_weapon(raw_weapon: dict[str, Any]) -> WeaponTemplate:
    weapon_class = str(raw_weapon.get("weapon_class", raw_weapon.get("class_name", raw_weapon.get("className", ""))))
    defaults = get_weapon_attributes(weapon_class)
    return WeaponTemplate(
        weapon_class=str(raw_weapon.get("weapon_class", raw_weapon.get("class_name", raw_weapon.get("className", defaults.get("weapon_class", ""))))),
        name=str(raw_weapon.get("name", defaults.get("name", raw_weapon.get("weapon_class", "Weapon")))),
        speed=float(raw_weapon.get("speed", raw_weapon.get("speed_knots", defaults.get("speed", 0.0)))),
        range_nm=float(raw_weapon.get("range_nm", raw_weapon.get("range", defaults.get("range_nm", 0.0)))),
        lethality=float(raw_weapon.get("lethality", defaults.get("lethality", 0.0))),
        max_quantity=int(raw_weapon.get("max_quantity", raw_weapon.get("maxQuantity", raw_weapon.get("current_quantity", raw_weapon.get("currentQuantity", 0))))),
        current_quantity=int(raw_weapon.get("current_quantity", raw_weapon.get("currentQuantity", raw_weapon.get("max_quantity", raw_weapon.get("maxQuantity", 0))))),
    )


def _read_reference_point(raw_point: dict[str, Any]) -> ReferencePoint:
    position_raw = raw_point.get("position", raw_point.get("coordinates", [raw_point.get("lon", 0.0), raw_point.get("lat", 0.0)]))
    return make_reference_point(
        _read_point(position_raw),
        str(raw_point.get("name", raw_point.get("id", "Reference Point"))),
        str(raw_point.get("id", raw_point.get("reference_id", raw_point.get("referenceId", "")))) or None,
    )


def _read_mission_area(raw_area: list[Any], reference_points_by_id: dict[str, ReferencePoint]) -> list[ReferencePoint]:
    area: list[ReferencePoint] = []
    for index, raw_point in enumerate(raw_area):
        if isinstance(raw_point, str):
            reference_point = reference_points_by_id.get(raw_point)
            if reference_point is not None:
                area.append(reference_point)
        elif isinstance(raw_point, dict):
            area.append(_read_reference_point(raw_point))
        elif isinstance(raw_point, list) and len(raw_point) >= 2:
            area.append(make_reference_point(_read_point(raw_point), f"Area Point {index + 1}"))
    return area


def _read_missions(payload: dict[str, Any], reference_points: list[ReferencePoint]) -> list[Mission]:
    missions: list[Mission] = []
    reference_points_by_id = {point.reference_id: point for point in reference_points}
    for raw_mission in payload.get("missions", []):
        mission_type = str(raw_mission.get("type", raw_mission.get("mission_type", raw_mission.get("missionType", "")))).lower()
        mission_id = str(raw_mission.get("id", raw_mission.get("mission_id", raw_mission.get("missionId", ""))))
        name = str(raw_mission.get("name", mission_id or mission_type or "Mission"))
        assigned_units = [str(unit_id) for unit_id in raw_mission.get("assigned_unit_ids", raw_mission.get("assignedUnitIds", []))]
        active = bool(raw_mission.get("active", True))
        if mission_type == "patrol":
            area = _read_mission_area(
                raw_mission.get("assigned_area", raw_mission.get("assignedArea", [])),
                reference_points_by_id,
            )
            missions.append(
                PatrolMission(
                    mission_id=mission_id or name,
                    name=name,
                    assigned_unit_ids=assigned_units,
                    active=active,
                    assigned_area=area,
                )
            )
        elif mission_type == "strike":
            missions.append(
                StrikeMission(
                    mission_id=mission_id or name,
                    name=name,
                    assigned_unit_ids=assigned_units,
                    active=active,
                    assigned_target_ids=[
                        str(target_id)
                        for target_id in raw_mission.get("assigned_target_ids", raw_mission.get("assignedTargetIds", []))
                    ],
                )
            )
    return missions


def _read_unit(raw_unit: dict[str, Any]) -> CombatUnit:
    unit_type = str(raw_unit.get("type", "aircraft")).lower()
    requested_class_name = _unit_class_name(raw_unit)
    defaults = get_unit_attributes(unit_type, requested_class_name)
    max_fuel = float(_get_with_default(raw_unit, defaults, "max_fuel", "maxFuel", fallback=10000.0))
    altitude_ft = float(_get_with_default(raw_unit, defaults, "altitude_ft", "altitude", "altitudeFt", fallback=0.0))
    return CombatUnit(
        unit_id=str(raw_unit["id"]),
        name=str(raw_unit.get("name", raw_unit["id"])),
        side=str(raw_unit.get("side", "blue")).lower(),
        unit_type=unit_type,
        route=UnitRoute([_read_point(point) for point in raw_unit.get("route", [])]),
        route_id=str(raw_unit.get("route_id", raw_unit.get("routeId", ""))),
        motion=str(raw_unit.get("motion", "route_loop")).lower(),
        position=_read_point(raw_unit["position"]) if "position" in raw_unit else None,
        altitude_ft=altitude_ft,
        speed=float(_get_with_default(raw_unit, defaults, "speed", fallback=1.0)),
        range_nm=float(_get_with_default(raw_unit, defaults, "range_nm", "range", fallback=80.0)),
        heading=float(raw_unit.get("heading", 0.0)),
        detection_range_nm=float(_get_with_default(raw_unit, defaults, "detection_range_nm", "detectionRangeNm", fallback=0.0)),
        weapons=[_read_weapon(weapon) for weapon in raw_unit.get("weapons", [])],
        target_id=str(raw_unit.get("target_id", raw_unit.get("targetId", ""))),
        alive=bool(raw_unit.get("alive", True)),
        current_fuel=float(_get_with_default(raw_unit, defaults, "current_fuel", "currentFuel", fallback=max_fuel)),
        max_fuel=max_fuel,
        fuel_rate=float(_get_with_default(raw_unit, defaults, "fuel_rate", "fuelRate", fallback=1.0)),
        class_name=str(defaults.get("class_name", requested_class_name)),
        radar_on=_read_bool(_get_with_default(raw_unit, defaults, "radar_on", "radarOn", fallback=True)),
        rcs=float(_get_with_default(raw_unit, defaults, "rcs", fallback=1.0)),
        jammer_power=float(_get_with_default(raw_unit, defaults, "jammer_power", "jammerPower", fallback=0.0)),
        jammer_range_nm=float(_get_with_default(raw_unit, defaults, "jammer_range_nm", "jammerRangeNm", fallback=0.0)),
        ew_resistance=float(_get_with_default(raw_unit, defaults, "ew_resistance", "ewResistance", fallback=0.0)),
        comms_on=_read_bool(_get_with_default(raw_unit, defaults, "comms_on", "commsOn", fallback=True)),
        comms_range_nm=float(_get_with_default(raw_unit, defaults, "comms_range_nm", "commsRangeNm", fallback=0.0)),
        datalink=_read_bool(_get_with_default(raw_unit, defaults, "datalink", fallback=True)),
        command_node=_read_bool(_get_with_default(raw_unit, defaults, "command_node", "commandNode", fallback=False)),
        comms_power=float(_get_with_default(raw_unit, defaults, "comms_power", "commsPower", fallback=1.0)),
        comms_resistance=float(_get_with_default(raw_unit, defaults, "comms_resistance", "commsResistance", fallback=0.0)),
        contact_share_delay_s=float(_get_with_default(raw_unit, defaults, "contact_share_delay_s", "contactShareDelayS", fallback=0.0)),
    )


def _read_units(payload: dict[str, Any], base_path: Path) -> list[CombatUnit]:
    units: list[CombatUnit] = []
    unit_files = payload.get("unit_files", payload.get("unitFiles", []))
    if unit_files:
        for raw_path in unit_files:
            unit_path = (base_path / str(raw_path)).resolve()
            units.append(_read_unit(_load_json(unit_path)))
        return units

    for raw_unit in payload.get("units", []):
        units.append(_read_unit(raw_unit))
    return units


def load_scenario(path: Path) -> Scenario:
    payload: dict[str, Any] = _load_json(path)
    reference_points = [
        _read_reference_point(raw_point)
        for raw_point in payload.get("reference_points", payload.get("referencePoints", []))
    ]
    units = _read_units(payload, path.parent)
    return Scenario(
        name=str(payload.get("name", path.stem)),
        units=units,
        reference_points=reference_points,
        missions=_read_missions(payload, reference_points),
        start_time=float(payload.get("startTime", payload.get("start_time", 0.0))),
        duration=float(payload.get("duration", 14400.0)),
        time_compression=int(payload.get("timeCompression", payload.get("time_compression", 1))),
    )


def save_scenario(path: Path, scenario: Scenario, split_units: bool | None = None) -> None:
    """Save a scenario back to JSON using an atomic replace for each touched file."""
    path = Path(path)
    existing_payload: dict[str, Any] = {}
    if path.exists():
        existing_payload = _load_json(path)
    should_split_units = bool(existing_payload.get("unit_files")) if split_units is None else split_units

    payload = _scenario_metadata_to_dict(scenario)
    payload["missions"] = [_mission_to_dict(mission) for mission in scenario.missions]
    if scenario.reference_points:
        payload["reference_points"] = [_reference_point_to_dict(point) for point in scenario.reference_points]

    if should_split_units:
        units_dir = path.parent / "units"
        units_dir.mkdir(parents=True, exist_ok=True)
        unit_files: list[str] = []
        for unit in scenario.units:
            unit_file = units_dir / f"{_safe_file_stem(unit.unit_id)}.json"
            _write_json_atomic(unit_file, _unit_to_dict(unit))
            unit_files.append(str(unit_file.relative_to(path.parent)).replace("\\", "/"))
        payload["unit_files"] = unit_files
    else:
        payload["units"] = [_unit_to_dict(unit) for unit in scenario.units]

    _write_json_atomic(path, payload)


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    """Return a single-file JSON-compatible representation of a scenario."""
    payload = _scenario_metadata_to_dict(scenario)
    if scenario.reference_points:
        payload["reference_points"] = [_reference_point_to_dict(point) for point in scenario.reference_points]
    payload["units"] = [_unit_to_dict(unit) for unit in scenario.units]
    payload["missions"] = [_mission_to_dict(mission) for mission in scenario.missions]
    return payload


def _scenario_metadata_to_dict(scenario: Scenario) -> dict[str, Any]:
    return {
        "name": scenario.name,
        "start_time": scenario.start_time,
        "duration": scenario.duration,
        "time_compression": scenario.time_compression,
    }


def _unit_to_dict(unit: CombatUnit) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": unit.unit_id,
        "name": unit.name,
        "side": unit.side,
        "type": unit.unit_type,
        "motion": unit.motion,
        "altitude_ft": unit.altitude_ft,
        "range_nm": unit.range_nm,
        "speed": unit.speed,
        "detection_range_nm": unit.detection_range_nm,
        "heading": unit.heading,
        "current_fuel": unit.current_fuel,
        "max_fuel": unit.max_fuel,
        "fuel_rate": unit.fuel_rate,
        "alive": unit.alive,
        "radar_on": unit.radar_on,
        "rcs": unit.rcs,
        "jammer_power": unit.jammer_power,
        "jammer_range_nm": unit.jammer_range_nm,
        "ew_resistance": unit.ew_resistance,
        "comms_on": unit.comms_on,
        "comms_range_nm": unit.comms_range_nm,
        "datalink": unit.datalink,
        "command_node": unit.command_node,
        "comms_power": unit.comms_power,
        "comms_resistance": unit.comms_resistance,
        "contact_share_delay_s": unit.contact_share_delay_s,
    }
    if unit.class_name:
        payload["class_name"] = unit.class_name
    if unit.route_id:
        payload["route_id"] = unit.route_id
    if unit.position is not None:
        payload["position"] = _point_to_list(unit.position)
    if unit.route.points:
        payload["route"] = [_point_to_list(point) for point in unit.route.points]
    if unit.target_id:
        payload["target_id"] = unit.target_id
    if unit.weapons:
        payload["weapons"] = [_weapon_to_dict(weapon) for weapon in unit.weapons]
    return payload


def _weapon_to_dict(weapon: WeaponTemplate) -> dict[str, Any]:
    return {
        "weapon_class": weapon.weapon_class,
        "name": weapon.name,
        "speed": weapon.speed,
        "range_nm": weapon.range_nm,
        "lethality": weapon.lethality,
        "max_quantity": weapon.max_quantity,
        "current_quantity": weapon.current_quantity,
    }


def _mission_to_dict(mission: Mission) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": mission.mission_id,
        "name": mission.name,
        "type": mission.mission_type,
        "active": mission.active,
        "assigned_unit_ids": list(mission.assigned_unit_ids),
    }
    if isinstance(mission, PatrolMission):
        payload["assigned_area"] = [_point_to_list(point.position) for point in mission.assigned_area]
    elif isinstance(mission, StrikeMission):
        payload["assigned_target_ids"] = list(mission.assigned_target_ids)
    return payload


def _reference_point_to_dict(point: ReferencePoint) -> dict[str, Any]:
    return {
        "id": point.reference_id,
        "name": point.name,
        "position": _point_to_list(point.position),
    }


def _point_to_list(point: LonLat) -> list[float]:
    return [round(float(point.lon), 6), round(float(point.lat), 6)]


def _safe_file_stem(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return safe or "unit"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _unit_class_name(raw_unit: dict[str, Any]) -> str:
    for key in ("class_name", "className", "model", "platform", "equipment"):
        value = raw_unit.get(key)
        if value:
            return str(value)
    return str(raw_unit.get("name", ""))


def _get_with_default(
    raw: dict[str, Any],
    defaults: dict[str, Any],
    *keys: str,
    fallback: Any,
) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    for key in keys:
        if key in defaults:
            return defaults[key]
    return fallback


def _read_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)
