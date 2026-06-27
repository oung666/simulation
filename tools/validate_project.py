from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "simulation"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.core.db import (  # noqa: E402
    AirbaseDb,
    AircraftCnDb,
    AircraftDb,
    FacilityDb,
    GroundVehicleDb,
    ShipDb,
    WeaponDb,
)
from simulation.core.paths import get_default_layers_path, get_default_scenario_path  # noqa: E402
from simulation.core.scenario import load_scenario, save_scenario  # noqa: E402
from simulation.core.layers import load_layer_document  # noqa: E402


SUSPICIOUS_TEXT_MARKERS = [
    "\ufffd",
    "\ue046",
    "\u3221",
    "钃",
    "鏆",
    "闆",
    "楂",
    "鑸",
    "閫",
    "鐕",
    "娌",
    "鎺",
    "骞",
    "绾㈡",
    "鍧",
    "鏄?",
    "鍚?",
    "娴风孩",
    "????",
]


def main() -> int:
    issues: list[str] = []
    issues.extend(_check_text_encoding())
    issues.extend(_check_scenario())
    issues.extend(_check_scenario_save_roundtrip())
    issues.extend(_check_layers())
    issues.extend(_check_databases())

    if issues:
        print("Project validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Project validation passed.")
    return 0


def _check_text_encoding() -> list[str]:
    issues: list[str] = []
    roots = [
        PACKAGE_ROOT / "data",
        PACKAGE_ROOT / "ui",
        PACKAGE_ROOT / "controllers",
        PACKAGE_ROOT / "engine",
        PACKAGE_ROOT / "core" / "db",
        PACKAGE_ROOT / "docs",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".py", ".json", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            for marker in SUSPICIOUS_TEXT_MARKERS:
                if marker in text:
                    issues.append(f"{_rel(path)} contains possible mojibake marker {marker!r}")
                    break
    return issues


def _check_scenario() -> list[str]:
    issues: list[str] = []
    scenario_path = get_default_scenario_path()
    try:
        scenario = load_scenario(scenario_path)
    except Exception as exc:  # noqa: BLE001
        return [f"{_rel(scenario_path)} failed to load: {exc}"]

    seen_ids: set[str] = set()
    for unit in scenario.units:
        if unit.unit_id in seen_ids:
            issues.append(f"duplicate unit id {unit.unit_id!r}")
        seen_ids.add(unit.unit_id)
        if unit.side not in {"blue", "red"}:
            issues.append(f"{unit.unit_id}: invalid side {unit.side!r}")
        if unit.speed < 0:
            issues.append(f"{unit.unit_id}: negative speed {unit.speed}")
        if unit.range_nm < 0 or unit.detection_range_nm < 0:
            issues.append(f"{unit.unit_id}: negative range/detection range")
        for weapon in unit.weapons:
            if weapon.max_quantity < 0 or weapon.current_quantity < 0:
                issues.append(f"{unit.unit_id}/{weapon.weapon_class}: negative weapon quantity")
            if weapon.current_quantity > weapon.max_quantity:
                issues.append(f"{unit.unit_id}/{weapon.weapon_class}: current quantity exceeds max")

    known_unit_ids = {unit.unit_id for unit in scenario.units}
    for mission in scenario.missions:
        for unit_id in mission.assigned_unit_ids:
            if unit_id not in known_unit_ids:
                issues.append(f"mission {mission.mission_id}: unknown assigned unit {unit_id!r}")
        target_ids = getattr(mission, "assigned_target_ids", [])
        for target_id in target_ids:
            if target_id not in known_unit_ids:
                issues.append(f"mission {mission.mission_id}: unknown target {target_id!r}")
    return issues


def _check_scenario_save_roundtrip() -> list[str]:
    issues: list[str] = []
    scenario_path = get_default_scenario_path()
    try:
        scenario = load_scenario(scenario_path)
        with TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            split_path = tmp / "scene.json"
            save_scenario(split_path, scenario, split_units=True)
            split_loaded = load_scenario(split_path)
            if len(split_loaded.units) != len(scenario.units):
                issues.append("split scenario save/load changed unit count")
            single_path = tmp / "single.json"
            save_scenario(single_path, scenario, split_units=False)
            single_loaded = load_scenario(single_path)
            if len(single_loaded.units) != len(scenario.units):
                issues.append("single-file scenario save/load changed unit count")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"scenario save/load roundtrip failed: {exc}")
    return issues


def _check_layers() -> list[str]:
    issues: list[str] = []
    layers_path = get_default_layers_path()
    try:
        layer_document = load_layer_document(layers_path)
    except Exception as exc:  # noqa: BLE001
        return [f"{_rel(layers_path)} failed to load: {exc}"]

    seen_ids: set[str] = set()
    for route in layer_document.routes:
        if route.route_id in seen_ids:
            issues.append(f"duplicate route id {route.route_id!r}")
        seen_ids.add(route.route_id)
        if route.side not in {"blue", "red"}:
            issues.append(f"route {route.route_id}: invalid side {route.side!r}")
        if len(route.points) < 2:
            issues.append(f"route {route.route_id}: needs at least 2 points")
    return issues


def _check_databases() -> list[str]:
    issues: list[str] = []
    issues.extend(_check_weapon_db())
    for label, entries in [
        ("AircraftDb", AircraftDb),
        ("AircraftCnDb", AircraftCnDb),
        ("ShipDb", ShipDb),
        ("FacilityDb", FacilityDb),
        ("AirbaseDb", AirbaseDb),
        ("GroundVehicleDb", GroundVehicleDb),
    ]:
        issues.extend(_check_unit_db(label, entries))
    return issues


def _check_weapon_db() -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(WeaponDb):
        name = str(entry.get("class_name", "")).strip()
        label = name or f"WeaponDb[{index}]"
        if not name:
            issues.append(f"{label}: missing class_name")
        if name in seen:
            issues.append(f"{label}: duplicate class_name")
        seen.add(name)
        for field in ["speed", "range", "lethality"]:
            value = entry.get(field)
            if not _is_non_negative_number(value):
                issues.append(f"{label}: invalid {field}={value!r}")
        lethality = entry.get("lethality")
        if isinstance(lethality, (int, float)) and not 0 <= float(lethality) <= 1:
            issues.append(f"{label}: lethality must be 0..1")
    return issues


def _check_unit_db(label: str, entries: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        name = str(entry.get("class_name", entry.get("className", entry.get("name", "")))).strip()
        item_label = f"{label}[{index}]" if not name else f"{label}/{name}"
        if not name:
            issues.append(f"{item_label}: missing class_name/name")
        if name in seen:
            issues.append(f"{item_label}: duplicate class_name/name")
        seen.add(name)
        if "speed" in entry and not _is_non_negative_number(entry.get("speed")):
            issues.append(f"{item_label}: invalid speed={entry.get('speed')!r}")
        if "range" in entry and not _is_non_negative_number(entry.get("range")):
            issues.append(f"{item_label}: invalid range={entry.get('range')!r}")
        if "detection_range_nm" in entry and not _is_non_negative_number(entry.get("detection_range_nm")):
            issues.append(f"{item_label}: invalid detection_range_nm={entry.get('detection_range_nm')!r}")
    return issues


def _is_non_negative_number(value: object) -> bool:
    if not isinstance(value, (int, float)):
        return False
    return float(value) >= 0


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PACKAGE_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
