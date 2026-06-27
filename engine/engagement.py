from __future__ import annotations

import math
import random
from collections.abc import Iterable
from uuid import uuid4

from simulation.core.geo import LonLat
from simulation.core.geo_utils import (
    bearing_between,
    haversine_distance_km,
    km_to_nm,
    next_position,
)
from simulation.core.scenario import CombatUnit, Scenario
from simulation.core.weapon import FlyingWeapon, WeaponTemplate


HIT_DISTANCE_KM = 1.0


def _unit_position(unit: CombatUnit) -> LonLat | None:
    if unit.position is not None:
        return unit.position
    route_points = unit.route.points if unit.route else []
    return route_points[0] if route_points else None


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _distance_nm(point_a: LonLat, point_b: LonLat) -> float:
    return km_to_nm(haversine_distance_km(point_a.lat, point_a.lon, point_b.lat, point_b.lon))


def _target_position(target: CombatUnit | LonLat) -> LonLat | None:
    if isinstance(target, LonLat):
        return target
    return _unit_position(target)


def jamming_pressure_against(
    side: str,
    reference_positions: Iterable[LonLat | None],
    units: Iterable[CombatUnit] | None,
) -> float:
    """Return hostile jamming pressure against one or more protected positions."""
    if units is None:
        return 0.0
    positions = [position for position in reference_positions if position is not None]
    if not positions:
        return 0.0

    pressure = 0.0
    for jammer in units:
        if not jammer.alive or jammer.side == side:
            continue
        jammer_range_nm = max(0.0, float(getattr(jammer, "jammer_range_nm", 0.0)))
        jammer_power = max(0.0, float(getattr(jammer, "jammer_power", 0.0)))
        if jammer_range_nm <= 0.0 or jammer_power <= 0.0:
            continue
        jammer_pos = _unit_position(jammer)
        if jammer_pos is None:
            continue
        nearest_distance_nm = min(_distance_nm(jammer_pos, position) for position in positions)
        if nearest_distance_nm > jammer_range_nm:
            continue
        attenuation = 1.0 - 0.5 * (nearest_distance_nm / max(1.0, jammer_range_nm))
        pressure += jammer_power * attenuation
    return clamp(pressure, 0.0, 0.85)


def jammer_pressure(
    detector: CombatUnit,
    target: CombatUnit | LonLat,
    units: Iterable[CombatUnit] | None = None,
) -> float:
    detector_pos = _unit_position(detector)
    target_pos = _target_position(target)
    return jamming_pressure_against(detector.side, [detector_pos, target_pos], units)


def effective_detection_range_nm(
    detector: CombatUnit,
    target: CombatUnit | LonLat,
    units: Iterable[CombatUnit] | None = None,
) -> float:
    """Return radar detection range after target signature and jamming effects."""
    if not bool(getattr(detector, "radar_on", True)):
        return 0.0
    base_range_nm = max(0.0, float(getattr(detector, "detection_range_nm", 0.0)))
    if base_range_nm <= 0.0:
        return 0.0
    target_rcs = max(0.0, float(getattr(target, "rcs", 1.0)))
    rcs_factor = clamp(math.sqrt(target_rcs), 0.35, 1.0)
    pressure = jammer_pressure(detector, target, units)
    ew_resistance = max(0.0, float(getattr(detector, "ew_resistance", 0.0)))
    jammer_factor = clamp(1.0 - pressure + ew_resistance, 0.25, 1.0)
    return base_range_nm * rcs_factor * jammer_factor


def is_detected(
    detector: CombatUnit,
    target: CombatUnit | LonLat,
    units: Iterable[CombatUnit] | None = None,
) -> bool:
    """Return whether target is inside detector effective detection range."""
    detector_pos = _unit_position(detector)
    target_pos = _target_position(target)
    if detector_pos is None or target_pos is None:
        return False
    distance_nm = _distance_nm(detector_pos, target_pos)
    return distance_nm <= effective_detection_range_nm(detector, target, units)


def can_engage(weapon: WeaponTemplate, shooter_pos: LonLat, target_pos: LonLat) -> bool:
    """Return whether a weapon template has enough range to reach target_pos."""
    if weapon.current_quantity <= 0 or weapon.range_nm <= 0:
        return False
    distance_nm = _distance_nm(shooter_pos, target_pos)
    return distance_nm <= weapon.range_nm


def count_weapons_tracking(scenario: Scenario, target_id: str) -> int:
    """Count launched weapons currently tracking the same target."""
    return sum(1 for weapon in scenario.flying_weapons if weapon.target_id == target_id)


def launch_weapon(
    scenario: Scenario,
    shooter: CombatUnit,
    weapon_tpl: WeaponTemplate,
    target: CombatUnit,
    quantity: int = 1,
) -> list[FlyingWeapon]:
    """Launch weapons from shooter inventory and add them to the scenario."""
    shooter_pos = _unit_position(shooter)
    target_pos = _unit_position(target)
    if shooter_pos is None or target_pos is None:
        return []
    if quantity <= 0 or weapon_tpl.current_quantity < quantity:
        return []

    launched: list[FlyingWeapon] = []
    for index in range(quantity):
        heading = bearing_between(shooter_pos.lat, shooter_pos.lon, target_pos.lat, target_pos.lon)
        flight_seconds = (weapon_tpl.range_nm / max(1.0, weapon_tpl.speed)) * 3600.0
        weapon = FlyingWeapon(
            weapon_id=str(uuid4()),
            name=f"{weapon_tpl.name} #{index + 1}",
            side=shooter.side,
            weapon_class=weapon_tpl.weapon_class,
            position=shooter_pos,
            heading=heading,
            speed=weapon_tpl.speed,
            target_id=target.unit_id,
            lethality=weapon_tpl.lethality,
            fuel_remaining_s=flight_seconds,
            trail=[shooter_pos],
        )
        scenario.flying_weapons.append(weapon)
        launched.append(weapon)

    weapon_tpl.current_quantity -= quantity
    return launched


def update_flying_weapon(
    scenario: Scenario,
    weapon: FlyingWeapon,
    units_by_id: dict[str, CombatUnit],
) -> str:
    """Move a launched weapon one simulated second and resolve terminal effects."""
    target = units_by_id.get(weapon.target_id)
    if target is None or not target.alive:
        _remove_weapon(scenario, weapon)
        return "lost_target"

    target_pos = _unit_position(target)
    if target_pos is None:
        _remove_weapon(scenario, weapon)
        return "lost_target"

    distance_km = haversine_distance_km(
        weapon.position.lat,
        weapon.position.lon,
        target_pos.lat,
        target_pos.lon,
    )
    if distance_km <= HIT_DISTANCE_KM:
        hit = weapon_endgame(weapon, target, scenario.units)
        _remove_weapon(scenario, weapon)
        return "hit" if hit else "miss"

    next_lat, next_lon = next_position(
        weapon.position.lat,
        weapon.position.lon,
        target_pos.lat,
        target_pos.lon,
        weapon.speed,
    )
    weapon.trail.append(weapon.position)
    weapon.trail = weapon.trail[-12:]
    weapon.position = LonLat(next_lon, next_lat)
    weapon.heading = bearing_between(next_lat, next_lon, target_pos.lat, target_pos.lon)
    weapon.fuel_remaining_s -= 1.0
    if weapon.fuel_remaining_s <= 0.0:
        _remove_weapon(scenario, weapon)
        return "expired"
    return "flying"


def effective_lethality(
    weapon: FlyingWeapon,
    target: CombatUnit,
    units: Iterable[CombatUnit] | None = None,
) -> float:
    """Return terminal weapon lethality after hostile jamming and EW protection."""
    target_pos = _unit_position(target)
    pressure = jamming_pressure_against(weapon.side, [weapon.position, target_pos], units)
    ew_resistance = max(0.0, float(getattr(target, "ew_resistance", 0.0)))
    weapon_jammer_factor = clamp(1.0 - pressure + ew_resistance, 0.25, 1.0)
    return clamp(weapon.lethality * weapon_jammer_factor, 0.0, 1.0)


def weapon_endgame(
    weapon: FlyingWeapon,
    target: CombatUnit,
    units: Iterable[CombatUnit] | None = None,
) -> bool:
    """Resolve probability of kill and mark target destroyed on hit."""
    if random.random() <= effective_lethality(weapon, target, units):
        target.alive = False
        target.position = _unit_position(target)
        return True
    return False


def _remove_weapon(scenario: Scenario, weapon: FlyingWeapon) -> None:
    if weapon in scenario.flying_weapons:
        scenario.flying_weapons.remove(weapon)

