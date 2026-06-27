from __future__ import annotations

from typing import Literal

from simulation.core.contact import ContactTrack
from simulation.core.scenario import CombatUnit


PerspectiveMode = Literal["god", "blue", "red"]

PERSPECTIVE_GOD: PerspectiveMode = "god"
PERSPECTIVE_BLUE: PerspectiveMode = "blue"
PERSPECTIVE_RED: PerspectiveMode = "red"
SIDE_PERSPECTIVES = {PERSPECTIVE_BLUE, PERSPECTIVE_RED}
ALL_PERSPECTIVES = {PERSPECTIVE_GOD, PERSPECTIVE_BLUE, PERSPECTIVE_RED}


def normalize_perspective(value: str | None) -> PerspectiveMode:
    normalized = (value or PERSPECTIVE_GOD).strip().lower()
    if normalized in {"blue", "blue_view"}:
        return PERSPECTIVE_BLUE
    if normalized in {"red", "red_view"}:
        return PERSPECTIVE_RED
    return PERSPECTIVE_GOD


def is_god_view(perspective: str | None) -> bool:
    return normalize_perspective(perspective) == PERSPECTIVE_GOD


def perspective_side(perspective: str | None) -> str | None:
    normalized = normalize_perspective(perspective)
    return normalized if normalized in SIDE_PERSPECTIVES else None


def perspective_label(perspective: str | None) -> str:
    return {
        PERSPECTIVE_GOD: "上帝视角",
        PERSPECTIVE_BLUE: "蓝方视角",
        PERSPECTIVE_RED: "红方视角",
    }[normalize_perspective(perspective)]


def unit_is_friendly(unit: CombatUnit, perspective: str | None) -> bool:
    side = perspective_side(perspective)
    return side is not None and unit.side == side


def unit_is_enemy(unit: CombatUnit, perspective: str | None) -> bool:
    side = perspective_side(perspective)
    return side is not None and unit.side != side


def unit_is_real_visible(unit: CombatUnit, perspective: str | None) -> bool:
    return is_god_view(perspective) or unit_is_friendly(unit, perspective)


def unit_is_operable(unit: CombatUnit, perspective: str | None) -> bool:
    return unit_is_real_visible(unit, perspective)


def visible_units_for_view(units: list[CombatUnit], perspective: str | None) -> list[CombatUnit]:
    if is_god_view(perspective):
        return list(units)
    side = perspective_side(perspective)
    if side is None:
        return []
    return [unit for unit in units if unit.side == side]


def known_enemy_tracks_for_view(
    units: list[CombatUnit],
    contact_tracks: dict[str, dict[str, ContactTrack]],
    perspective: str | None,
) -> list[ContactTrack]:
    side = perspective_side(perspective)
    if side is None:
        return []
    units_by_id = {unit.unit_id: unit for unit in units}
    tracks = []
    for track in contact_tracks.get(side, {}).values():
        target = units_by_id.get(track.target_id)
        if target is not None and target.side != side:
            tracks.append(track)
    return tracks


def contact_track_for_view(
    unit_id: str,
    units: list[CombatUnit],
    contact_tracks: dict[str, dict[str, ContactTrack]],
    perspective: str | None,
) -> ContactTrack | None:
    side = perspective_side(perspective)
    if side is None:
        return None
    target = next((unit for unit in units if unit.unit_id == unit_id), None)
    if target is None or target.side == side:
        return None
    return contact_tracks.get(side, {}).get(unit_id)
