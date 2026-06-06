from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qt_frontend_v6.core.geo import LonLat


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
    speed: float
    range_nm: float


@dataclass(frozen=True)
class Scenario:
    name: str
    units: list[CombatUnit]


def _read_point(raw: list[float]) -> LonLat:
    return LonLat(float(raw[0]), float(raw[1]))


def load_scenario(path: Path) -> Scenario:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    units: list[CombatUnit] = []
    for raw_unit in payload.get("units", []):
        units.append(
            CombatUnit(
                unit_id=str(raw_unit["id"]),
                name=str(raw_unit.get("name", raw_unit["id"])),
                side=str(raw_unit.get("side", "blue")).lower(),
                unit_type=str(raw_unit.get("type", "aircraft")).lower(),
                route=UnitRoute([_read_point(point) for point in raw_unit.get("route", [])]),
                route_id=str(raw_unit.get("route_id", "")),
                motion=str(raw_unit.get("motion", "route_loop")).lower(),
                position=_read_point(raw_unit["position"]) if "position" in raw_unit else None,
                speed=float(raw_unit.get("speed", 1.0)),
                range_nm=float(raw_unit.get("range_nm", raw_unit.get("range", 80.0))),
            )
        )
    return Scenario(name=str(payload.get("name", path.stem)), units=units)
