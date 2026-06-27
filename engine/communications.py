from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from simulation.core.geo import LonLat
from simulation.core.geo_utils import haversine_distance_km, km_to_nm
from simulation.core.scenario import CombatUnit
from simulation.engine.engagement import clamp, jamming_pressure_against


@dataclass(frozen=True)
class CommunicationLink:
    sender_id: str
    receiver_id: str
    quality: float
    degraded: bool
    distance_nm: float
    effective_range_nm: float


def unit_position(unit: CombatUnit) -> LonLat | None:
    if unit.position is not None:
        return unit.position
    route_points = unit.route.points if unit.route else []
    return route_points[0] if route_points else None


def distance_nm(point_a: LonLat, point_b: LonLat) -> float:
    return km_to_nm(haversine_distance_km(point_a.lat, point_a.lon, point_b.lat, point_b.lon))


def comms_jammer_pressure(
    sender: CombatUnit,
    receiver: CombatUnit,
    units: Iterable[CombatUnit] | None,
) -> float:
    sender_pos = unit_position(sender)
    receiver_pos = unit_position(receiver)
    return jamming_pressure_against(sender.side, [sender_pos, receiver_pos], units)


def effective_comms_range_nm(
    sender: CombatUnit,
    receiver: CombatUnit,
    units: Iterable[CombatUnit] | None = None,
) -> float:
    base_range = min(
        max(0.0, float(getattr(sender, "comms_range_nm", 0.0))),
        max(0.0, float(getattr(receiver, "comms_range_nm", 0.0))),
    )
    if base_range <= 0.0:
        return 0.0
    pressure = comms_jammer_pressure(sender, receiver, units)
    resistance = min(
        max(0.0, float(getattr(sender, "comms_resistance", 0.0))),
        max(0.0, float(getattr(receiver, "comms_resistance", 0.0))),
    )
    jammer_factor = clamp(1.0 - pressure + resistance, 0.2, 1.0)
    return base_range * jammer_factor


def can_share_contact(
    sender: CombatUnit,
    receiver: CombatUnit,
    units: Iterable[CombatUnit] | None = None,
) -> bool:
    return communication_link(sender, receiver, units) is not None


def communication_link(
    sender: CombatUnit,
    receiver: CombatUnit,
    units: Iterable[CombatUnit] | None = None,
) -> CommunicationLink | None:
    if sender.unit_id == receiver.unit_id or sender.side != receiver.side:
        return None
    if not sender.alive or not receiver.alive:
        return None
    if not bool(getattr(sender, "comms_on", True)) or not bool(getattr(receiver, "comms_on", True)):
        return None
    if not bool(getattr(sender, "datalink", True)) or not bool(getattr(receiver, "datalink", True)):
        return None
    sender_pos = unit_position(sender)
    receiver_pos = unit_position(receiver)
    if sender_pos is None or receiver_pos is None:
        return None
    effective_range = effective_comms_range_nm(sender, receiver, units)
    if effective_range <= 0.0:
        return None
    distance = distance_nm(sender_pos, receiver_pos)
    if distance > effective_range:
        return None
    quality = clamp(1.0 - distance / max(1.0, effective_range), 0.2, 1.0)
    pressure = comms_jammer_pressure(sender, receiver, units)
    return CommunicationLink(
        sender_id=sender.unit_id,
        receiver_id=receiver.unit_id,
        quality=quality,
        degraded=pressure > 0.0,
        distance_nm=distance,
        effective_range_nm=effective_range,
    )


def build_network_links(
    selected: CombatUnit,
    units: Iterable[CombatUnit],
) -> list[CommunicationLink]:
    return [
        link
        for unit in units
        if (link := communication_link(selected, unit, units)) is not None
    ]
