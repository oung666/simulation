from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt5.QtGui import QPainter

if TYPE_CHECKING:
    from simulation.ui.map_canvas import MapCanvas


@dataclass
class MapLayer:
    """Base class for map overlay layers."""

    layer_id: str
    visible: bool = True
    feature_count: int = 0

    def refresh(self, canvas: MapCanvas) -> None:
        """Refresh cached metadata before a paint pass."""

    def draw(self, painter: QPainter, canvas: MapCanvas) -> None:
        raise NotImplementedError


@dataclass
class CallbackMapLayer(MapLayer):
    """Layer backed by existing MapCanvas draw functions during the refactor."""

    draw_method_name: str = ""
    refresh_method_name: str | None = None

    def refresh(self, canvas: MapCanvas) -> None:
        if self.refresh_method_name:
            getattr(canvas, self.refresh_method_name)()

    def draw(self, painter: QPainter, canvas: MapCanvas) -> None:
        if not self.visible:
            return
        getattr(canvas, self.draw_method_name)(painter)


@dataclass
class RangeLayer(CallbackMapLayer):
    layer_id: str = "range_rings"
    draw_method_name: str = "_draw_range_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        unit = canvas.visible_unit_by_id(canvas.selected_unit_id()) if canvas.selected_unit_id() else None
        self.feature_count = (
            1 if unit is not None and unit.alive and (unit.detection_range_nm or unit.range_nm) > 0 else 0
        )


@dataclass
class RadarAnimationLayer(CallbackMapLayer):
    layer_id: str = "radar_animation"
    draw_method_name: str = "_draw_radar_animation_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        unit = canvas.visible_unit_by_id(canvas.selected_unit_id()) if canvas.selected_unit_id() else None
        self.feature_count = (
            1 if unit is not None and unit.alive and bool(getattr(unit, "radar_on", True)) else 0
        )


@dataclass
class ElectromagneticLayer(CallbackMapLayer):
    layer_id: str = "electromagnetic"
    draw_method_name: str = "_draw_electromagnetic_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        unit = canvas.visible_unit_by_id(canvas.selected_unit_id()) if canvas.selected_unit_id() else None
        self.feature_count = (
            1
            if unit is not None
            and unit.alive
            and float(getattr(unit, "jammer_range_nm", 0.0)) > 0.0
            and float(getattr(unit, "jammer_power", 0.0)) > 0.0
            else 0
        )


@dataclass
class CommunicationsLayer(CallbackMapLayer):
    layer_id: str = "communications"
    draw_method_name: str = "_draw_communications_overlay"

    def refresh(self, canvas: MapCanvas) -> None:
        self.feature_count = 0 if canvas.selected_unit_id() is None else 1


@dataclass
class MissionAreaLayer(CallbackMapLayer):
    layer_id: str = "mission_areas"
    draw_method_name: str = "_draw_patrol_mission_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        self.feature_count = sum(
            1
            for mission in canvas.scenario.missions
            if getattr(mission, "mission_type", "") == "patrol"
            and len(getattr(mission, "assigned_area", [])) >= 3
            and canvas._mission_visible(mission)
        )


@dataclass
class RouteLayer(CallbackMapLayer):
    layer_id: str = "routes"
    draw_method_name: str = "_draw_route_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        side = canvas.perspective_side()
        self.feature_count = sum(
            1
            for route in canvas.layer_document.routes
            if route.visible and len(route.points) >= 2 and (side is None or route.side == side)
        )


@dataclass
class DynamicRouteLayer(CallbackMapLayer):
    layer_id: str = "dynamic_routes"
    draw_method_name: str = "_draw_dynamic_route_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        self.feature_count = sum(
            1
            for unit in canvas.visible_units()
            if unit.alive and unit.motion == "dynamic" and bool(unit.route.points)
        )


@dataclass
class DraftRouteLayer(CallbackMapLayer):
    layer_id: str = "route_drafts"
    draw_method_name: str = "_draw_route_drafts"

    def refresh(self, canvas: MapCanvas) -> None:
        self.feature_count = sum(
            1 for draft in canvas.route_drafts.values() if any(draft.get(key) for key in ("start", "waypoints", "end"))
        )


@dataclass
class WeaponLayer(CallbackMapLayer):
    layer_id: str = "weapons"
    draw_method_name: str = "_draw_weapon_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        side = canvas.perspective_side()
        if side is None:
            self.feature_count = len(canvas.scenario.flying_weapons)
        else:
            self.feature_count = sum(
                1
                for weapon in canvas.scenario.flying_weapons
                if weapon.side == side or canvas.contact_track_for_unit(weapon.target_id) is not None
            )


@dataclass
class UnitLayer(CallbackMapLayer):
    layer_id: str = "units"
    draw_method_name: str = "_draw_unit_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        self.feature_count = len(canvas.visible_units()) + len(canvas.visible_enemy_tracks())


@dataclass
class ImpactLayer(CallbackMapLayer):
    layer_id: str = "impact_effects"
    draw_method_name: str = "_draw_impact_layer"

    def refresh(self, canvas: MapCanvas) -> None:
        self.feature_count = len(canvas._impact_effects)


@dataclass
class OverlayLabelLayer(CallbackMapLayer):
    layer_id: str = "overlay_labels"
    draw_method_name: str = "_draw_overlay"
    feature_count: int = 1


@dataclass
class TacticalLayerSet:
    """Ordered collection of tactical layers rendered over the basemap."""

    canvas: MapCanvas
    _layers: list[MapLayer] = field(init=False)

    def __post_init__(self) -> None:
        self._layers = [
            RangeLayer(),
            RadarAnimationLayer(),
            ElectromagneticLayer(),
            CommunicationsLayer(),
            MissionAreaLayer(),
            RouteLayer(),
            DynamicRouteLayer(),
            DraftRouteLayer(),
            WeaponLayer(),
            UnitLayer(),
            ImpactLayer(),
            OverlayLabelLayer(),
        ]

    def refresh(self) -> None:
        for layer in self._layers:
            layer.refresh(self.canvas)

    def draw(self, painter: QPainter) -> None:
        self.refresh()
        for layer in self._layers:
            layer.draw(painter, self.canvas)

    def set_visible(self, layer_id: str, visible: bool) -> bool:
        layer = self.layer(layer_id)
        if layer is None:
            return False
        layer.visible = visible
        return True

    def layer(self, layer_id: str) -> MapLayer | None:
        return next((layer for layer in self._layers if layer.layer_id == layer_id), None)

    def states(self) -> list[tuple[str, bool, int]]:
        self.refresh()
        return [(layer.layer_id, layer.visible, layer.feature_count) for layer in self._layers]
