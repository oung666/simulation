from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from simulation.core.contact import ContactTrack
from simulation.core.geo import LonLat
from simulation.core.geo_utils import (
    bearing_between,
    get_terminal_coordinates_from_distance_and_bearing,
    haversine_distance_km,
    km_to_nm,
)
from simulation.core.mission import PatrolMission, ReferencePoint, StrikeMission, make_reference_point
from simulation.core.scenario import CombatUnit, Scenario, UnitRoute
from simulation.engine.engagement import (
    can_engage,
    count_weapons_tracking,
    effective_detection_range_nm,
    effective_lethality,
    jammer_pressure,
    is_detected,
    launch_weapon,
    update_flying_weapon,
)
from simulation.engine.communications import communication_link


MAX_WEAPONS_TRACKING_TARGET = 2
TAIL_CHASE_DISTANCE_NM = 5.0
STRIKE_POSITION_FACTOR = 0.85


@dataclass
class CombatEvent:
    """Combat event shown in the UI battle log."""

    time: float
    event_type: str
    source_id: str
    target_id: str
    weapon_class: str = ""
    message: str = ""
    position: LonLat | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class CombatController:
    """Automatic engagement and Panopticon-style mission controller."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.combat_log: list[CombatEvent] = []
        self.current_time = 0.0
        self._detected_pairs: set[tuple[str, str]] = set()
        self.contact_tracks: dict[str, dict[str, ContactTrack]] = {}
        self._shared_contact_keys: set[tuple[str, str, str]] = set()
        self._previous_positions: dict[str, LonLat] = {}
        self._weapon_attackers: dict[str, tuple[str, str]] = {}

    def set_scenario(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.combat_log.clear()
        self._detected_pairs.clear()
        self.contact_tracks.clear()
        self._shared_contact_keys.clear()
        self._previous_positions.clear()
        self._weapon_attackers.clear()
        self.current_time = 0.0

    def step(self, units_positions: dict[str, LonLat], simulation_time: float = 0.0) -> None:
        """Execute one simulated second of combat and mission logic."""
        self.current_time = simulation_time
        self._sync_unit_positions(units_positions)
        self._update_units_on_patrol_mission()
        self.clear_completed_strike_missions()
        self._expire_contacts()

        units_by_id = {unit.unit_id: unit for unit in self.scenario.units}
        alive_units = [unit for unit in self.scenario.units if unit.alive]

        self._update_local_detections(alive_units)
        self._update_units_on_strike_mission()

        for shooter in alive_units:
            if not shooter.weapons:
                continue
            shooter_pos = shooter.position
            if shooter_pos is None:
                continue
            for target in alive_units:
                if not self._can_target(shooter, target):
                    continue
                target_pos = target.position
                if target_pos is None:
                    continue
                if not is_detected(shooter, target, alive_units):
                    continue
                weapon = self._best_weapon_for(shooter, shooter_pos, target_pos)
                if weapon is None:
                    if shooter.unit_type == "aircraft" and target.unit_type == "aircraft":
                        self._aircraft_pursuit(shooter, target)
                    continue
                if count_weapons_tracking(self.scenario, target.unit_id) >= MAX_WEAPONS_TRACKING_TARGET:
                    continue
                self._launch_and_log(shooter, target, weapon)

        for weapon in list(self.scenario.flying_weapons):
            target = units_by_id.get(weapon.target_id)
            hit_probability = effective_lethality(weapon, target, self.scenario.units) if target else weapon.lethality
            result = update_flying_weapon(self.scenario, weapon, units_by_id)
            if result == "flying":
                continue
            target_name = target.name if target else weapon.target_id
            event_extra = self._weapon_event_extra(weapon)
            if result == "hit":
                self._add_event(
                    "hit",
                    weapon.weapon_id,
                    weapon.target_id,
                    weapon.weapon_class,
                    f"{weapon.name} 命中并摧毁 {target_name}（结算命中率 {hit_probability:.0%}）",
                    target.position if target else weapon.position,
                    extra=event_extra,
                )
                if target is not None and not target.alive:
                    self._add_event(
                        "unit_destroyed",
                        weapon.weapon_id,
                        target.unit_id,
                        weapon.weapon_class,
                        f"{target.name} 宸茶鎽ф瘉",
                        target.position,
                        extra=event_extra,
                    )
                self._weapon_attackers.pop(weapon.weapon_id, None)
            elif result == "miss":
                self._add_event(
                    "miss",
                    weapon.weapon_id,
                    weapon.target_id,
                    weapon.weapon_class,
                    f"{weapon.name} 未命中 {target_name}（结算命中率 {hit_probability:.0%}）",
                    weapon.position,
                    extra=event_extra,
                )
                self._weapon_attackers.pop(weapon.weapon_id, None)
            elif result == "expired":
                self._add_event(
                    "expired",
                    weapon.weapon_id,
                    weapon.target_id,
                    weapon.weapon_class,
                    f"{weapon.name} 燃料耗尽",
                    weapon.position,
                    extra=event_extra,
                )
                self._weapon_attackers.pop(weapon.weapon_id, None)
            elif result == "lost_target":
                self._add_event(
                    "lost_target",
                    weapon.weapon_id,
                    weapon.target_id,
                    weapon.weapon_class,
                    f"{weapon.name} 丢失目标",
                    weapon.position,
                    extra=event_extra,
                )
                self._weapon_attackers.pop(weapon.weapon_id, None)

    def refresh_mission_routes(self, units_positions: dict[str, LonLat], simulation_time: float = 0.0) -> None:
        """Recalculate mission-driven routes without advancing combat resolution."""
        self.current_time = simulation_time
        self._sync_unit_positions(units_positions)
        self._update_units_on_patrol_mission()
        self.clear_completed_strike_missions()
        self._update_units_on_strike_mission()

    def _update_local_detections(self, alive_units: list[CombatUnit]) -> None:
        for observer in alive_units:
            for target in alive_units:
                if observer.unit_id == target.unit_id or observer.side == target.side:
                    continue
                target_pos = target.position
                if target_pos is None:
                    continue
                if is_detected(observer, target, alive_units):
                    self._log_detection(observer, target, target_pos, alive_units)

    def add_reference_point(self, name: str, lat: float, lon: float) -> ReferencePoint:
        reference_point = make_reference_point(LonLat(float(lon), float(lat)), name)
        self.scenario.reference_points.append(reference_point)
        return reference_point

    def remove_reference_point(self, reference_id: str) -> bool:
        before = len(self.scenario.reference_points)
        self.scenario.reference_points = [
            point for point in self.scenario.reference_points if point.reference_id != reference_id
        ]
        for mission in self.scenario.missions:
            if isinstance(mission, PatrolMission):
                mission.assigned_area = [
                    point for point in mission.assigned_area if point.reference_id != reference_id
                ]
        return len(self.scenario.reference_points) != before

    def move_aircraft(self, aircraft_id: str, new_coordinates: list[Any]) -> CombatUnit | None:
        unit = self._unit_by_id(aircraft_id)
        if unit is None or unit.unit_type != "aircraft":
            return None
        self._set_dynamic_route(unit, self._coerce_points(new_coordinates))
        return unit

    def move_ship(self, ship_id: str, new_coordinates: list[Any]) -> CombatUnit | None:
        unit = self._unit_by_id(ship_id)
        if unit is None or unit.unit_type != "ship":
            return None
        self._set_dynamic_route(unit, self._coerce_points(new_coordinates))
        return unit

    def create_patrol_mission(
        self,
        name: str,
        assigned_units: list[str],
        assigned_area: list[Any],
    ) -> PatrolMission | None:
        area = self._coerce_reference_points(assigned_area)
        if len(area) < 3:
            return None
        mission = PatrolMission(
            mission_id=str(uuid4()),
            name=name,
            assigned_unit_ids=[str(unit_id) for unit_id in assigned_units],
            assigned_area=area,
            active=True,
        )
        self.scenario.missions.append(mission)
        return mission

    def update_patrol_mission(
        self,
        mission_id: str,
        name: str | None = None,
        assigned_units: list[str] | None = None,
        assigned_area: list[Any] | None = None,
        active: bool | None = None,
    ) -> bool:
        mission = self._mission_by_id(mission_id)
        if not isinstance(mission, PatrolMission):
            return False
        if name:
            mission.name = name
        if assigned_units is not None:
            mission.assigned_unit_ids = [str(unit_id) for unit_id in assigned_units]
        if assigned_area is not None:
            area = self._coerce_reference_points(assigned_area)
            if len(area) >= 3:
                mission.assigned_area = area
        if active is not None:
            mission.active = active
        return True

    def create_strike_mission(
        self,
        name: str,
        assigned_units: list[str],
        assigned_targets: list[str],
    ) -> StrikeMission:
        mission = StrikeMission(
            mission_id=str(uuid4()),
            name=name,
            assigned_unit_ids=[str(unit_id) for unit_id in assigned_units],
            assigned_target_ids=[str(target_id) for target_id in assigned_targets],
            active=True,
        )
        self.scenario.missions.append(mission)
        return mission

    def update_strike_mission(
        self,
        mission_id: str,
        name: str | None = None,
        assigned_units: list[str] | None = None,
        assigned_targets: list[str] | None = None,
        active: bool | None = None,
    ) -> bool:
        mission = self._mission_by_id(mission_id)
        if not isinstance(mission, StrikeMission):
            return False
        if name:
            mission.name = name
        if assigned_units is not None:
            mission.assigned_unit_ids = [str(unit_id) for unit_id in assigned_units]
        if assigned_targets is not None:
            mission.assigned_target_ids = [str(target_id) for target_id in assigned_targets]
        if active is not None:
            mission.active = active
        return True

    def delete_mission(self, mission_id: str) -> bool:
        before = len(self.scenario.missions)
        self.scenario.missions = [
            mission for mission in self.scenario.missions if mission.mission_id != mission_id
        ]
        return len(self.scenario.missions) != before

    def clear_completed_strike_missions(self) -> None:
        active_missions = []
        for mission in self.scenario.missions:
            if not isinstance(mission, StrikeMission):
                active_missions.append(mission)
                continue
            targets = [self._unit_by_id(target_id) for target_id in mission.assigned_target_ids]
            attackers = [self._unit_by_id(unit_id) for unit_id in mission.assigned_unit_ids]
            alive_targets = [target for target in targets if target is not None and target.alive]
            alive_attackers = [attacker for attacker in attackers if attacker is not None and attacker.alive]
            attackers_expended = bool(alive_attackers) and all(
                self._best_available_weapon(attacker) is None for attacker in alive_attackers
            )
            if alive_targets and alive_attackers and not attackers_expended:
                active_missions.append(mission)
        self.scenario.missions = active_missions

    def get_alive_units(self) -> list[CombatUnit]:
        return [unit for unit in self.scenario.units if unit.alive]

    def get_events_since(self, last_index: int) -> list[CombatEvent]:
        return self.combat_log[last_index:]

    def known_contact_for(self, side: str, target_id: str) -> ContactTrack | None:
        return self.contact_tracks.get(side, {}).get(target_id)

    def target_position_for_decision(self, attacker: CombatUnit, target: CombatUnit) -> LonLat | None:
        if attacker.side == target.side:
            return target.position
        track = self.known_contact_for(attacker.side, target.unit_id)
        if track is not None:
            return track.last_known_position
        return target.position if is_detected(attacker, target, self.scenario.units) else None

    def can_launch_on_contact(
        self,
        attacker: CombatUnit,
        target: CombatUnit,
        track: ContactTrack | None,
    ) -> bool:
        if track is not None and track.track_type != "local":
            return False
        return is_detected(attacker, target, self.scenario.units)

    def _update_units_on_patrol_mission(self) -> None:
        for mission in self.scenario.missions:
            if not isinstance(mission, PatrolMission) or not mission.active or len(mission.assigned_area) < 3:
                continue
            for unit_id in mission.assigned_unit_ids:
                unit = self._unit_by_id(unit_id)
                if unit is None or not unit.alive or unit.unit_type != "aircraft":
                    continue
                if self._unit_has_active_strike_mission(unit.unit_id) or self._has_live_aircraft_target(unit):
                    continue
                if not unit.route.points:
                    self._set_dynamic_route(unit, [mission.generate_random_coordinates_within_patrol_area()])
                    continue
                target = unit.route.points[0]
                if not mission.check_if_coordinates_is_within_patrol_area(target.lat, target.lon):
                    self._set_dynamic_route(unit, [mission.generate_random_coordinates_within_patrol_area()])
                elif unit.motion != "dynamic":
                    unit.motion = "dynamic"
                    unit.route_id = ""

    def _update_units_on_strike_mission(self) -> None:
        for mission in self.scenario.missions:
            if not isinstance(mission, StrikeMission) or not mission.active:
                continue
            target = self._first_alive_target(mission.assigned_target_ids)
            if target is None:
                continue
            for unit_id in mission.assigned_unit_ids:
                attacker = self._unit_by_id(unit_id)
                if attacker is None or not attacker.alive or attacker.position is None:
                    continue
                weapon = self._best_available_weapon(attacker)
                if weapon is None:
                    continue
                target_position = self.target_position_for_decision(attacker, target)
                if target_position is None:
                    continue
                distance_nm = self._distance_nm(attacker.position, target_position)
                effective_detection_nm = effective_detection_range_nm(attacker, target, self.scenario.units)
                detection_radius_nm = effective_detection_nm if effective_detection_nm > 0 else weapon.range_nm
                strike_radius_nm = min(detection_radius_nm, weapon.range_nm)
                in_launch_envelope = (
                    distance_nm <= weapon.range_nm
                    and distance_nm <= detection_radius_nm
                    and self.can_launch_on_contact(attacker, target, self.known_contact_for(attacker.side, target.unit_id))
                )
                if in_launch_envelope:
                    if count_weapons_tracking(self.scenario, target.unit_id) < MAX_WEAPONS_TRACKING_TARGET:
                        self._launch_and_log(attacker, target, weapon)
                    attacker.target_id = target.unit_id
                    continue
                self._route_aircraft_to_strike_position(attacker, target, strike_radius_nm, target_position)

    def _aircraft_pursuit(self, aircraft: CombatUnit, target: CombatUnit) -> None:
        if self._unit_has_active_strike_mission(aircraft.unit_id):
            return
        if aircraft.position is None or target.position is None or self._best_available_weapon(aircraft) is None:
            return
        tail_bearing = (target.heading + 180.0) % 360.0
        tail_position = get_terminal_coordinates_from_distance_and_bearing(
            target.position.lat,
            target.position.lon,
            TAIL_CHASE_DISTANCE_NM,
            tail_bearing,
        )
        self._set_dynamic_route(aircraft, [tail_position])
        aircraft.target_id = target.unit_id

    def _route_aircraft_to_strike_position(
        self,
        aircraft: CombatUnit,
        target: CombatUnit,
        strike_radius_nm: float,
        target_position: LonLat | None = None,
    ) -> None:
        target_position = target_position or target.position
        if aircraft.position is None or target_position is None or strike_radius_nm <= 0:
            return
        bearing_target_to_aircraft = bearing_between(
            target_position.lat,
            target_position.lon,
            aircraft.position.lat,
            aircraft.position.lon,
        )
        strike_position = get_terminal_coordinates_from_distance_and_bearing(
            target_position.lat,
            target_position.lon,
            strike_radius_nm * STRIKE_POSITION_FACTOR,
            bearing_target_to_aircraft,
        )
        self._set_dynamic_route(aircraft, [strike_position])
        aircraft.target_id = target.unit_id
        aircraft.heading = bearing_between(
            aircraft.position.lat,
            aircraft.position.lon,
            target_position.lat,
            target_position.lon,
        )

    def _launch_and_log(self, shooter: CombatUnit, target: CombatUnit, weapon) -> None:
        launched = launch_weapon(self.scenario, shooter, weapon, target, 1)
        shooter.target_id = target.unit_id
        distance_nm = self._distance_nm(shooter.position, target.position) if shooter.position and target.position else 0.0
        effective_range_nm = effective_detection_range_nm(shooter, target, self.scenario.units)
        hit_probability = max(0.0, min(1.0, float(getattr(weapon, "lethality", 0.0))))
        for flying_weapon in launched:
            setattr(flying_weapon, "attacker_unit_id", shooter.unit_id)
            self._weapon_attackers[flying_weapon.weapon_id] = (shooter.unit_id, shooter.side)
            self._add_event(
                "launched",
                shooter.unit_id,
                target.unit_id,
                flying_weapon.weapon_class,
                (
                    f"{shooter.name} 发射 {flying_weapon.name} 攻击 {target.name}"
                    f"（距离 {distance_nm:.1f} nm，射程 {weapon.range_nm:.1f} nm，"
                    f"有效探测 {effective_range_nm:.1f} nm，命中率 {hit_probability:.0%}）"
                ),
                flying_weapon.position,
            )

    def _sync_unit_positions(self, units_positions: dict[str, LonLat]) -> None:
        for unit in self.scenario.units:
            if not unit.alive:
                continue
            position = units_positions.get(unit.unit_id)
            if position is None:
                continue
            previous = self._previous_positions.get(unit.unit_id)
            if previous is not None and (previous.lon != position.lon or previous.lat != position.lat):
                unit.heading = bearing_between(previous.lat, previous.lon, position.lat, position.lon)
            unit.position = position
            self._previous_positions[unit.unit_id] = position

    def _can_target(self, shooter: CombatUnit, target: CombatUnit) -> bool:
        if shooter.unit_id == target.unit_id or shooter.side == target.side:
            return False
        if target.unit_type == "airbase" and shooter.unit_type == "aircraft":
            return False
        if shooter.unit_type == "facility":
            return target.unit_type in {"aircraft", "ship", "facility", "airbase", "ground_vehicle"}
        if shooter.unit_type == "ship":
            return target.unit_type in {"aircraft", "ship", "facility", "airbase", "ground_vehicle"}
        if shooter.unit_type == "aircraft":
            return target.unit_type in {"aircraft", "ship", "facility", "ground_vehicle"}
        if shooter.unit_type == "ground_vehicle":
            if "sam" in str(getattr(shooter, "class_name", "")).lower():
                return target.unit_type in {"aircraft", "ship", "facility", "airbase", "ground_vehicle"}
            return target.unit_type in {"ship", "facility", "airbase", "ground_vehicle"}
        return bool(shooter.weapons)

    def _best_weapon_for(self, shooter: CombatUnit, shooter_pos: LonLat, target_pos: LonLat):
        candidates = [
            weapon
            for weapon in shooter.weapons
            if weapon.current_quantity > 0 and can_engage(weapon, shooter_pos, target_pos)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda weapon: weapon.range_nm)

    def _best_available_weapon(self, unit: CombatUnit):
        candidates = [
            weapon for weapon in unit.weapons if weapon.current_quantity > 0 and weapon.range_nm > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda weapon: weapon.range_nm)

    def _log_detection(
        self,
        shooter: CombatUnit,
        target: CombatUnit,
        position: LonLat,
        alive_units: list[CombatUnit],
    ) -> None:
        pair = (shooter.unit_id, target.unit_id)
        self._refresh_local_contact(shooter, target, position)
        self._share_contact_from(shooter, target, alive_units)
        if pair in self._detected_pairs:
            return
        self._detected_pairs.add(pair)
        pressure = jammer_pressure(shooter, target, alive_units)
        distance_nm = self._distance_nm(shooter.position, position) if shooter.position is not None else 0.0
        effective_range = effective_detection_range_nm(shooter, target, alive_units)
        base_range = float(getattr(shooter, "detection_range_nm", 0.0))
        rcs = float(getattr(target, "rcs", 1.0))
        message = (
            f"{shooter.name} 探测到 {target.name}"
            f"（距离 {distance_nm:.1f} nm，基础探测 {base_range:.1f} nm，"
            f"有效探测 {effective_range:.1f} nm，RCS {rcs:.2f}，干扰压力 {pressure:.2f}）"
        )
        if pressure > 0.0:
            message = (
                f"{shooter.name} 在电磁干扰下探测到 {target.name}"
                f"（距离 {distance_nm:.1f} nm，基础探测 {base_range:.1f} nm，"
                f"有效探测 {effective_range:.1f} nm，RCS {rcs:.2f}，干扰压力 {pressure:.2f}）"
            )
        self._add_event(
            "detected",
            shooter.unit_id,
            target.unit_id,
            "",
            message,
            position,
        )

    def _refresh_local_contact(self, observer: CombatUnit, target: CombatUnit, position: LonLat) -> None:
        side_tracks = self.contact_tracks.setdefault(observer.side, {})
        side_tracks[target.unit_id] = ContactTrack(
            target_id=target.unit_id,
            side=observer.side,
            last_known_position=position,
            last_detected_time=self.current_time,
            source_unit_id=observer.unit_id,
            confidence=1.0,
            track_type="local",
            shared=False,
        )

    def _share_contact_from(
        self,
        observer: CombatUnit,
        target: CombatUnit,
        alive_units: list[CombatUnit],
    ) -> None:
        target_pos = target.position
        if target_pos is None:
            return
        for receiver in alive_units:
            if receiver.unit_id == observer.unit_id or receiver.side != observer.side:
                continue
            link = communication_link(observer, receiver, alive_units)
            relay_unit: CombatUnit | None = None
            if link is None:
                relay_unit = self._relay_for_contact(observer, receiver, alive_units)
                if relay_unit is None:
                    continue
            side_tracks = self.contact_tracks.setdefault(observer.side, {})
            existing = side_tracks.get(target.unit_id)
            if existing is None or existing.track_type != "local":
                side_tracks[target.unit_id] = ContactTrack(
                    target_id=target.unit_id,
                    side=observer.side,
                    last_known_position=target_pos,
                    last_detected_time=self.current_time,
                    source_unit_id=observer.unit_id,
                    confidence=0.8,
                    track_type="shared",
                    shared=True,
                )
            else:
                existing.shared = True
            share_key = (observer.unit_id, receiver.unit_id, target.unit_id)
            if share_key in self._shared_contact_keys:
                continue
            self._shared_contact_keys.add(share_key)
            via_text = f"，经 {relay_unit.name} 中继" if relay_unit is not None else ""
            self._add_event(
                "shared_contact",
                observer.unit_id,
                target.unit_id,
                "",
                f"{observer.name} 向 {receiver.name} 共享了 {target.name} 的目标情报{via_text}",
                target_pos,
            )

    def _relay_for_contact(
        self,
        observer: CombatUnit,
        receiver: CombatUnit,
        alive_units: list[CombatUnit],
    ) -> CombatUnit | None:
        for relay in alive_units:
            if relay.side != observer.side or relay.unit_id in {observer.unit_id, receiver.unit_id}:
                continue
            if not bool(getattr(relay, "command_node", False)):
                continue
            if communication_link(observer, relay, alive_units) is None:
                continue
            if communication_link(relay, receiver, alive_units) is None:
                continue
            return relay
        return None

    def _expire_contacts(self) -> None:
        for side, tracks in list(self.contact_tracks.items()):
            expired_target_ids = [
                target_id for target_id, track in tracks.items() if track.is_expired(self.current_time)
            ]
            for target_id in expired_target_ids:
                del tracks[target_id]
            if not tracks:
                del self.contact_tracks[side]

    def shared_contact_count_for_side(self, side: str) -> int:
        return sum(1 for track in self.contact_tracks.get(side, {}).values() if track.shared)

    def _add_event(
        self,
        event_type: str,
        source_id: str,
        target_id: str,
        weapon_class: str,
        message: str,
        position: LonLat | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.combat_log.append(
            CombatEvent(
                time=self.current_time,
                event_type=event_type,
                source_id=source_id,
                target_id=target_id,
                weapon_class=weapon_class,
                message=message,
                position=position,
                extra=dict(extra or {}),
            )
        )

    def _weapon_event_extra(self, weapon) -> dict[str, Any]:
        attacker_unit_id = str(getattr(weapon, "attacker_unit_id", "")).strip()
        attacker_side = str(getattr(weapon, "side", ""))
        if attacker_unit_id:
            attacker = self._unit_by_id(attacker_unit_id)
            if attacker is not None:
                attacker_side = attacker.side
        mapped = self._weapon_attackers.get(weapon.weapon_id)
        if not attacker_unit_id and mapped is not None:
            attacker_unit_id, attacker_side = mapped
        elif not attacker_unit_id:
            same_side_units = [unit for unit in self.scenario.units if unit.side == attacker_side]
            targeting_units = [unit for unit in same_side_units if unit.target_id == weapon.target_id]
            if len(targeting_units) == 1:
                attacker_unit_id = targeting_units[0].unit_id
                attacker_side = targeting_units[0].side
            elif len(same_side_units) == 1:
                attacker_unit_id = same_side_units[0].unit_id
                attacker_side = same_side_units[0].side
        extra = {"attacker_side": attacker_side}
        if attacker_unit_id:
            extra["attacker_unit_id"] = attacker_unit_id
        return extra

    def _set_dynamic_route(self, unit: CombatUnit, points: list[LonLat]) -> None:
        unit.route = UnitRoute(points)
        unit.route_id = ""
        unit.motion = "dynamic"

    def _coerce_points(self, raw_points: list[Any]) -> list[LonLat]:
        if not raw_points:
            return []
        if self._looks_like_point(raw_points):
            return [self._coerce_point(raw_points)]
        return [self._coerce_point(point) for point in raw_points]

    def _coerce_reference_points(self, raw_points: list[Any]) -> list[ReferencePoint]:
        points = []
        for index, raw_point in enumerate(raw_points):
            if isinstance(raw_point, ReferencePoint):
                points.append(raw_point)
            else:
                points.append(make_reference_point(self._coerce_point(raw_point), f"Area Point {index + 1}"))
        return points

    def _coerce_point(self, raw_point: Any) -> LonLat:
        if isinstance(raw_point, ReferencePoint):
            return raw_point.position
        if isinstance(raw_point, LonLat):
            return raw_point
        if isinstance(raw_point, dict):
            if "position" in raw_point:
                return self._coerce_point(raw_point["position"])
            lon = raw_point.get("lon", raw_point.get("longitude", 0.0))
            lat = raw_point.get("lat", raw_point.get("latitude", 0.0))
            return LonLat(float(lon), float(lat))
        if isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
            return LonLat(float(raw_point[0]), float(raw_point[1]))
        raise ValueError(f"Unsupported coordinate value: {raw_point!r}")

    @staticmethod
    def _looks_like_point(value: Any) -> bool:
        if isinstance(value, (LonLat, ReferencePoint, dict)):
            return True
        return isinstance(value, (list, tuple)) and len(value) >= 2 and all(
            isinstance(item, (int, float)) for item in value[:2]
        )

    def _unit_by_id(self, unit_id: str) -> CombatUnit | None:
        for unit in self.scenario.units:
            if unit.unit_id == unit_id:
                return unit
        return None

    def _mission_by_id(self, mission_id: str):
        for mission in self.scenario.missions:
            if mission.mission_id == mission_id:
                return mission
        return None

    def _first_alive_target(self, target_ids: list[str]) -> CombatUnit | None:
        for target_id in target_ids:
            target = self._unit_by_id(target_id)
            if target is not None and target.alive:
                return target
        return None

    def _unit_has_active_strike_mission(self, unit_id: str) -> bool:
        return any(
            isinstance(mission, StrikeMission)
            and mission.active
            and unit_id in mission.assigned_unit_ids
            for mission in self.scenario.missions
        )

    def _has_live_aircraft_target(self, unit: CombatUnit) -> bool:
        target = self._unit_by_id(unit.target_id)
        return target is not None and target.alive and target.unit_type == "aircraft"

    @staticmethod
    def _distance_nm(point_a: LonLat, point_b: LonLat) -> float:
        return km_to_nm(haversine_distance_km(point_a.lat, point_a.lon, point_b.lat, point_b.lon))
