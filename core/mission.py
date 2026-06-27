from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from simulation.core.geo import LonLat
from simulation.core.geo_utils import generate_random_coordinates_within_polygon, point_in_polygon


@dataclass
class ReferencePoint:
    reference_id: str
    name: str
    position: LonLat


@dataclass
class Mission:
    mission_id: str
    name: str
    assigned_unit_ids: list[str]
    active: bool = True
    mission_type: str = "mission"


@dataclass
class PatrolMission(Mission):
    assigned_area: list[ReferencePoint] = field(default_factory=list)
    mission_type: str = "patrol"

    def generate_random_coordinates_within_patrol_area(self) -> LonLat:
        return generate_random_coordinates_within_polygon([point.position for point in self.assigned_area])

    def check_if_coordinates_is_within_patrol_area(self, lat: float, lon: float) -> bool:
        return point_in_polygon(LonLat(lon, lat), [point.position for point in self.assigned_area])


@dataclass
class StrikeMission(Mission):
    assigned_target_ids: list[str] = field(default_factory=list)
    mission_type: str = "strike"


def make_reference_point(position: LonLat, name: str = "Reference Point", reference_id: str | None = None) -> ReferencePoint:
    return ReferencePoint(
        reference_id=reference_id or str(uuid4()),
        name=name,
        position=position,
    )
