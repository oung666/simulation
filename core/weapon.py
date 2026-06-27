from __future__ import annotations

from dataclasses import dataclass, field

from simulation.core.geo import LonLat


@dataclass
class WeaponTemplate:
    """Weapon inventory entry carried by a combat unit."""

    weapon_class: str
    name: str
    speed: float
    range_nm: float
    lethality: float
    max_quantity: int
    current_quantity: int


@dataclass
class FlyingWeapon:
    """A launched weapon that is independently tracked in the scenario."""

    weapon_id: str
    name: str
    side: str
    weapon_class: str
    position: LonLat
    heading: float
    speed: float
    target_id: str
    lethality: float
    fuel_remaining_s: float
    trail: list[LonLat] = field(default_factory=list)

