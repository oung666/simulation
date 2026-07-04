"""simulation 的纯 Qt 地图绘制核心。

这个文件负责“地图上画什么、怎么画、按什么顺序画”。
v6 不使用 WebEngine / HTML 前端，离线瓦片、红蓝航线、单位图标、范围圈、
海陆图层都在这里通过 QPainter 直接绘制。

主要输入数据：
- MapDocument：离线地图元信息、瓦片目录、地图边界、海陆多边形。
- Scenario：战斗单元、机场、雷达等场景数据。
- LayerDocument：从 data/layers/routes.json 读取的路线图层数据。
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget

from simulation.core.clock import SimulationClock
from simulation.core.geo import LonLat, ScreenPoint, lonlat_to_world, world_to_lonlat
from simulation.core.layers import LayerDocument, RouteLayerItem, route_lookup
from simulation.core.map_document import MapDocument, MapFeature
from simulation.core.mission import PatrolMission
from simulation.core.contact import ContactTrack
from simulation.core.perspective import (
    contact_track_for_view,
    is_god_view,
    known_enemy_tracks_for_view,
    normalize_perspective,
    perspective_label,
    perspective_side,
    unit_is_enemy,
    unit_is_operable,
    unit_is_real_visible,
    visible_units_for_view,
)
from simulation.core.scenario import CombatUnit, Scenario, UnitRoute
from simulation.controllers.combat_controller import CombatController, CombatEvent
from simulation.controllers.motion import MotionController
from simulation.controllers.tile_store import TileStore
from simulation.engine.communications import build_network_links
from simulation.replay.recorder import ReplayRecorder
from simulation.ui.map_layers import TacticalLayerSet
from simulation.ui.unit_icons import draw_svg_unit_icon, unit_icon_name


DEFAULT_ZOOM = 7.0


class MapCanvas(QWidget):
    """地图画布控件。

    这个类既负责绘制，也负责地图交互状态，例如中心点、缩放级别、鼠标拖动。
    单位运动计算不直接写在这里，而是交给 MotionController，避免绘制代码和仿真逻辑混在一起。
    """

    coordinateHovered = pyqtSignal(float, float)
    timeChanged = pyqtSignal(float)
    mapRightClicked = pyqtSignal(float, float)
    mapCoordinatePicked = pyqtSignal(float, float)
    unitLeftClicked = pyqtSignal(str)
    unitRightClicked = pyqtSignal(str)
    mapLeftClicked = pyqtSignal()
    viewportChanged = pyqtSignal()
    combatEventsChanged = pyqtSignal()
    unitUpdated = pyqtSignal(str)
    perspectiveChanged = pyqtSignal(str)

    def __init__(
        self,
        map_document: MapDocument,
        scenario: Scenario,
        layer_document: LayerDocument,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.map_document = map_document
        self.scenario = scenario
        self.layer_document = layer_document
        self.route_lookup = route_lookup(layer_document)
        self.motion_controller = MotionController(self.route_lookup)
        self.combat_controller = CombatController(scenario)
        self.tile_store = TileStore(map_document.tile_root)
        self.center = map_document.center
        self.zoom = DEFAULT_ZOOM
        self.clock = SimulationClock(
            start_time=scenario.start_time,
            duration=scenario.duration,
            time_compression=scenario.time_compression,
            current_time=scenario.start_time,
            paused=True,
        )
        self.show_radar_ranges = True
        self.show_radar_animation = True
        self.show_communications_overlay = True
        self.current_perspective = "god"
        self._last_combat_step_time = 0.0
        self._last_combat_event_index = 0
        self._impact_effects: list[tuple[LonLat, float, str, str, str]] = []
        self.route_drafts: dict[str, dict[str, object]] = {}
        self._last_mouse_pos: QPoint | None = None
        self._left_press_pos: QPoint | None = None
        self._left_dragged = False
        self._last_tile_paint_rect: QRectF | None = None
        self._selected_unit_id: str | None = None
        self._interaction_mode = "none"
        self._pending_unit_id: str | None = None
        self._replay_recorder: ReplayRecorder | None = None
        self.tactical_layers = TacticalLayerSet(self)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._smooth_time: float = 0.0  # sub-frame interpolated time for rendering
        self._constrain_center()

    def reset_view(self) -> None:
        """复位地图视角到 offline_map.json 里配置的中心点和默认缩放。"""
        self.zoom = DEFAULT_ZOOM
        self.set_center(self.map_document.center)

    def zoom_in(self) -> None:
        """放大地图一级，同时限制不超过地图允许的最大 zoom。"""
        self.zoom = min(self.map_document.max_zoom, self.zoom + 0.5)
        self._constrain_center()
        self.update()
        self.viewportChanged.emit()

    def zoom_out(self) -> None:
        """缩小地图一级，同时限制不低于地图允许的最小 zoom。"""
        self.zoom = max(self.map_document.min_zoom, self.zoom - 0.5)
        self._constrain_center()
        self.update()
        self.viewportChanged.emit()

    def set_center(self, center: LonLat) -> None:
        """Set map center, clamp to bounds, and notify listeners."""
        self.center = center
        self._constrain_center()
        self.update()
        self.viewportChanged.emit()

    def center_world_constraints(self) -> tuple[float, float, float, float]:
        """Return the min/max world coordinates the map center can occupy."""
        min_lon, min_lat, max_lon, max_lat = self.map_document.bounds
        north_west = lonlat_to_world(LonLat(min_lon, max_lat), self.zoom)
        south_east = lonlat_to_world(LonLat(max_lon, min_lat), self.zoom)

        half_width = max(1.0, self.width() / 2.0)
        half_height = max(1.0, self.height() / 2.0)
        min_x = north_west.x + half_width
        max_x = south_east.x - half_width
        min_y = north_west.y + half_height
        max_y = south_east.y - half_height
        return min_x, max_x, min_y, max_y

    def map_world_bounds(self) -> tuple[float, float, float, float]:
        """Return the map bounds in current-zoom world coordinates."""
        min_lon, min_lat, max_lon, max_lat = self.map_document.bounds
        north_west = lonlat_to_world(LonLat(min_lon, max_lat), self.zoom)
        south_east = lonlat_to_world(LonLat(max_lon, min_lat), self.zoom)
        return north_west.x, south_east.x, north_west.y, south_east.y

    def viewport_world_rect(self) -> tuple[float, float, float, float]:
        """Return the current viewport edges in world coordinates."""
        center_world = lonlat_to_world(self.center, self.zoom)
        half_width = max(1.0, self.width() / 2.0)
        half_height = max(1.0, self.height() / 2.0)
        return (
            center_world.x - half_width,
            center_world.x + half_width,
            center_world.y - half_height,
            center_world.y + half_height,
        )

    def set_scenario(self, scenario: Scenario) -> None:
        """替换当前场景数据，并把仿真时间重新归零。"""
        self.scenario = scenario
        self.combat_controller.set_scenario(scenario)
        self.motion_controller.reset()
        self.clock.reset()
        self._last_combat_step_time = 0.0
        self._last_combat_event_index = 0
        self._impact_effects.clear()
        self._selected_unit_id = None
        self.clear_interaction_mode()
        self._replay_recorder = None
        self.update()

    def set_replay_recorder(self, recorder: ReplayRecorder | None) -> None:
        self._replay_recorder = recorder

    def set_perspective(self, perspective: str) -> None:
        """Switch between god, blue, and red map perspectives."""
        next_perspective = normalize_perspective(perspective)
        if next_perspective == self.current_perspective:
            return
        self.current_perspective = next_perspective
        if not self._selected_item_is_visible():
            self._selected_unit_id = None
            self.clear_interaction_mode()
        self.update()
        self.perspectiveChanged.emit(next_perspective)
        self.viewportChanged.emit()

    def perspective_side(self) -> str | None:
        return perspective_side(self.current_perspective)

    def is_god_perspective(self) -> bool:
        return is_god_view(self.current_perspective)

    def perspective_label(self) -> str:
        return perspective_label(self.current_perspective)

    def visible_units(self) -> list[CombatUnit]:
        return visible_units_for_view(self.scenario.units, self.current_perspective)

    def visible_enemy_tracks(self) -> list[ContactTrack]:
        return known_enemy_tracks_for_view(
            self.scenario.units,
            self.combat_controller.contact_tracks,
            self.current_perspective,
        )

    def contact_track_for_unit(self, unit_id: str) -> ContactTrack | None:
        return contact_track_for_view(
            unit_id,
            self.scenario.units,
            self.combat_controller.contact_tracks,
            self.current_perspective,
        )

    def selected_contact_track(self) -> ContactTrack | None:
        if self._selected_unit_id is None:
            return None
        return self.contact_track_for_unit(self._selected_unit_id)

    def visible_unit_by_id(self, unit_id: str) -> CombatUnit | None:
        unit = self.unit_by_id(unit_id)
        if unit is None or not unit_is_real_visible(unit, self.current_perspective):
            return None
        return unit

    def operable_unit_by_id(self, unit_id: str) -> CombatUnit | None:
        unit = self.unit_by_id(unit_id)
        if unit is None or not unit_is_operable(unit, self.current_perspective):
            return None
        return unit

    def selected_item_is_contact(self) -> bool:
        return self.selected_contact_track() is not None

    def _selected_item_is_visible(self) -> bool:
        if self._selected_unit_id is None:
            return True
        unit = self.unit_by_id(self._selected_unit_id)
        if unit is not None and unit.alive and unit_is_real_visible(unit, self.current_perspective):
            return True
        return self.contact_track_for_unit(self._selected_unit_id) is not None

    def selected_unit_id(self) -> str | None:
        """Return the currently selected map unit id, if any."""
        return self._selected_unit_id

    def clear_selected_unit(self) -> None:
        """Clear the selected map unit and repaint the selection ring."""
        if self._selected_unit_id is None:
            return
        self._selected_unit_id = None
        self.update()

    def select_unit(self, unit_id: str) -> bool:
        """Select an alive visible unit or known contact and repaint the selection ring."""
        unit = self.unit_by_id(unit_id)
        track = self.contact_track_for_unit(unit_id)
        if (unit is None or not unit.alive or not unit_is_real_visible(unit, self.current_perspective)) and track is None:
            return False
        self.clear_interaction_mode()
        self._selected_unit_id = unit_id
        self.update()
        return True

    def begin_edit_location(self, unit_id: str) -> bool:
        """Arm the next left-click to move a unit directly to that location."""
        if self.operable_unit_by_id(unit_id) is None:
            return False
        self._interaction_mode = "edit_location"
        self._pending_unit_id = unit_id
        return True

    def begin_plot_course(self, unit_id: str) -> bool:
        """Arm the next left-click to set a dynamic route for a unit."""
        if self.operable_unit_by_id(unit_id) is None:
            return False
        self._interaction_mode = "plot_course"
        self._pending_unit_id = unit_id
        return True

    def clear_interaction_mode(self) -> None:
        """Cancel any pending one-click map interaction."""
        self._interaction_mode = "none"
        self._pending_unit_id = None

    def begin_pick_coordinate(self) -> None:
        """Arm the next left-click to capture a lon/lat coordinate."""
        self._interaction_mode = "pick_coordinate"
        self._pending_unit_id = None

    def unit_by_id(self, unit_id: str) -> CombatUnit | None:
        """Return a scenario unit by id."""
        return next((unit for unit in self.scenario.units if unit.unit_id == unit_id), None)

    def unit_screen_position(self, unit_id: str) -> QPointF | None:
        """Return the current screen position for a unit id."""
        position = self.unit_position(unit_id)
        return None if position is None else self._screen_from_lonlat(position)

    def unit_position(self, unit_id: str) -> LonLat | None:
        """Return the current lon/lat position for a unit id."""
        track = self.contact_track_for_unit(unit_id)
        if track is not None:
            return track.last_known_position
        unit = self.visible_unit_by_id(unit_id)
        if unit is None:
            return None
        return self._position_for_unit(unit)

    def set_layer_document(self, layer_document: LayerDocument) -> None:
        """替换路线图层数据，并同步给单位运动控制器。"""
        self.layer_document = layer_document
        self.route_lookup = route_lookup(layer_document)
        self.motion_controller.set_routes(self.route_lookup)
        self.update()

    def set_route_drafts(self, drafts: dict[str, dict[str, object]]) -> None:
        """更新右键临时路线草稿，用于还没保存到 routes.json 的路线预览。"""
        self.route_drafts = drafts
        self.update()

    @property
    def playing(self) -> bool:
        return self.clock.is_playing

    @playing.setter
    def playing(self, value: bool) -> None:
        if value:
            self.clock.play()
        else:
            self.clock.pause()

    def set_playing(self, playing: bool) -> None:
        if playing:
            self.clock.play()
        else:
            self.clock.pause()

    def set_speed_multiplier(self, value: float) -> None:
        self.clock.set_time_compression(max(1, int(value)))


    def set_radar_ranges_visible(self, visible: bool) -> None:
        """Show or hide radar/detection range circles."""
        self.show_radar_ranges = visible
        self.tactical_layers.set_visible("range_rings", visible)
        self.tactical_layers.set_visible("electromagnetic", visible)
        self.update()

    def set_radar_animation_visible(self, visible: bool) -> None:
        """Show or hide radar sweep animation."""
        self.show_radar_animation = visible
        self.tactical_layers.set_visible("radar_animation", visible)
        self.update()

    def set_communications_overlay_visible(self, visible: bool) -> None:
        """Show or hide communications/shared-awareness overlay."""
        self.show_communications_overlay = visible
        self.tactical_layers.set_visible("communications", visible)
        self.update()

    def set_tactical_layer_visible(self, layer_id: str, visible: bool) -> bool:
        """Toggle an individual tactical layer on or off."""
        changed = self.tactical_layers.set_visible(layer_id, visible)
        if changed:
            self.update()
        return changed

    def tactical_layer_states(self) -> list[tuple[str, bool, int]]:
        """Return ordered tactical layer visibility states."""
        return self.tactical_layers.states()

    def refresh_mission_routes(self) -> None:
        """Recompute mission-driven routes using current unit positions."""
        self.combat_controller.refresh_mission_routes(
            self._current_unit_positions(),
            self._last_combat_step_time,
        )
        self.motion_controller.reset()
        self.update()


    def _tick(self) -> None:
        steps = self.clock.tick()
        self._execute_simulation_steps(steps)
        if self.clock.is_finished:
            self.set_playing(False)

    def step_simulation(self, steps: int = 1) -> None:
        executed_steps = self.clock.step_once(steps)
        self._execute_simulation_steps(executed_steps)

    def _execute_simulation_steps(self, steps: int) -> None:
        for _ in range(max(0, int(steps))):
            self._last_combat_step_time += 1.0
            self._advance_units(1.0)
            self.combat_controller.step(self._current_unit_positions(), self._last_combat_step_time)
            replay_state = self.build_replay_state() if self._replay_recorder_active() else None
            self._capture_new_combat_effects(replay_state)
            self._capture_replay_periodic_snapshot(replay_state)
        self._smooth_time = self.clock.fractional_time if self.clock.is_playing else self.clock.current_time
        self._impact_effects = [
            effect for effect in self._impact_effects if self._smooth_time - effect[1] <= 1.2
        ]
        self.timeChanged.emit(self.clock.current_time)
        self.update()

    def _current_unit_positions(self) -> dict[str, LonLat]:
        """Return current positions for alive units."""
        return {
            unit.unit_id: self.motion_controller.position_for(unit)
            for unit in self.scenario.units
            if unit.alive
        }

    def _advance_units(self, dt_seconds: float) -> None:
        """Advance all alive units by physical speed for one simulation step."""
        for unit in self.scenario.units:
            if unit.alive:
                self.motion_controller.advance(unit, dt_seconds)

    def build_replay_state(self) -> dict[str, Any]:
        return {
            "units": [self._serialize_unit_state(unit) for unit in self.scenario.units],
            "flying_weapons": [
                self._serialize_flying_weapon_state(weapon)
                for weapon in self.scenario.flying_weapons
            ],
            "missions": [self._serialize_mission_state(mission) for mission in self.scenario.missions],
            "contacts": [
                self._serialize_contact_track_state(side, track)
                for side, tracks in self.combat_controller.contact_tracks.items()
                for track in tracks.values()
            ],
        }

    def _capture_new_combat_effects(self, replay_state: dict[str, Any] | None = None) -> None:
        """Convert new combat events into short-lived map effects."""
        events = self.combat_controller.get_events_since(self._last_combat_event_index)
        self._last_combat_event_index += len(events)
        changed = bool(events)
        self._record_replay_events(events, replay_state)
        for event in events:
            if event.position is not None and event.event_type in {"hit", "miss", "expired"}:
                self._impact_effects.append(
                    (event.position, event.time, event.event_type, event.source_id, event.target_id)
                )
        if changed:
            self.combatEventsChanged.emit()

    def _replay_recorder_active(self) -> bool:
        return self._replay_recorder is not None and self._replay_recorder.active

    def _capture_replay_periodic_snapshot(self, replay_state: dict[str, Any] | None) -> None:
        if replay_state is None or not self._replay_recorder_active():
            return
        self._replay_recorder.capture_periodic_snapshot(
            self._last_combat_step_time,
            replay_state,
        )

    def _record_replay_events(
        self,
        events: list[CombatEvent],
        replay_state: dict[str, Any] | None = None,
    ) -> None:
        if not events or not self._replay_recorder_active():
            return
        forced_snapshot_types = {"launched", "hit", "unit_destroyed"}
        for event in events:
            position = None
            if event.position is not None:
                position = {"lon": float(event.position.lon), "lat": float(event.position.lat)}
            self._replay_recorder.record_event(
                time=float(event.time),
                event_type=event.event_type,
                source_id=event.source_id,
                target_id=event.target_id,
                weapon_class=event.weapon_class,
                position=position,
                message=event.message,
                force_snapshot_state=(
                    replay_state if event.event_type in forced_snapshot_types else None
                ),
                extra=deepcopy(getattr(event, "extra", {})),
            )

    @staticmethod
    def _serialize_lonlat(point: LonLat | None) -> dict[str, float] | None:
        if point is None:
            return None
        return {"lon": float(point.lon), "lat": float(point.lat)}

    def _serialize_unit_state(self, unit: CombatUnit) -> dict[str, Any]:
        return {
            "unit_id": unit.unit_id,
            "name": unit.name,
            "side": unit.side,
            "unit_type": unit.unit_type,
            "class_name": unit.class_name,
            "alive": unit.alive,
            "position": self._serialize_lonlat(self._position_for_unit(unit)),
            "heading": float(unit.heading),
            "speed": float(unit.speed),
            "target_id": unit.target_id,
            "range_nm": float(unit.range_nm),
            "detection_range_nm": float(unit.detection_range_nm),
            "radar_on": bool(unit.radar_on),
            "jammer_power": float(unit.jammer_power),
            "jammer_range_nm": float(unit.jammer_range_nm),
            "comms_on": bool(unit.comms_on),
            "comms_range_nm": float(unit.comms_range_nm),
            "comms_power": float(unit.comms_power),
            "comms_resistance": float(unit.comms_resistance),
            "current_fuel": float(unit.current_fuel),
            "motion": unit.motion,
            "route_id": unit.route_id,
            "route": [self._serialize_lonlat(point) for point in unit.route.points],
            "weapons": [
                {
                    "weapon_class": weapon.weapon_class,
                    "name": weapon.name,
                    "current_quantity": int(weapon.current_quantity),
                    "max_quantity": int(weapon.max_quantity),
                }
                for weapon in unit.weapons
            ],
        }

    def _serialize_flying_weapon_state(self, weapon) -> dict[str, Any]:
        return {
            "weapon_id": weapon.weapon_id,
            "name": weapon.name,
            "side": weapon.side,
            "weapon_class": weapon.weapon_class,
            "position": self._serialize_lonlat(weapon.position),
            "heading": float(weapon.heading),
            "speed": float(weapon.speed),
            "target_id": weapon.target_id,
            "lethality": float(weapon.lethality),
            "fuel_remaining_s": float(weapon.fuel_remaining_s),
            "trail": [self._serialize_lonlat(point) for point in weapon.trail],
            "attacker_unit_id": str(getattr(weapon, "attacker_unit_id", "")),
        }

    def _serialize_mission_state(self, mission) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mission_id": mission.mission_id,
            "name": mission.name,
            "mission_type": mission.mission_type,
            "active": bool(mission.active),
            "assigned_unit_ids": list(mission.assigned_unit_ids),
        }
        if hasattr(mission, "assigned_target_ids"):
            payload["assigned_target_ids"] = list(getattr(mission, "assigned_target_ids", []))
        if isinstance(mission, PatrolMission):
            payload["assigned_area"] = [
                {
                    "reference_id": point.reference_id,
                    "name": point.name,
                    "position": self._serialize_lonlat(point.position),
                }
                for point in mission.assigned_area
            ]
        return payload

    def _serialize_contact_track_state(self, side: str, track: ContactTrack) -> dict[str, Any]:
        return {
            "side": side,
            "target_id": track.target_id,
            "last_known_position": self._serialize_lonlat(track.last_known_position),
            "last_detected_time": float(track.last_detected_time),
            "source_unit_id": track.source_unit_id,
            "confidence": float(track.confidence),
            "track_type": track.track_type,
            "shared": bool(track.shared),
        }

    def _screen_from_lonlat(self, point: LonLat) -> QPointF:
        """把经纬度坐标转换成当前窗口里的屏幕坐标。"""
        center_world = lonlat_to_world(self.center, self.zoom)
        world = lonlat_to_world(point, self.zoom)
        return QPointF(
            world.x - center_world.x + self.width() / 2.0,
            world.y - center_world.y + self.height() / 2.0,
        )

    def _lonlat_from_screen(self, point: QPointF) -> LonLat:
        """把鼠标/屏幕坐标反算成经纬度。"""
        center_world = lonlat_to_world(self.center, self.zoom)
        world = ScreenPoint(
            center_world.x + point.x() - self.width() / 2.0,
            center_world.y + point.y() - self.height() / 2.0,
        )
        return world_to_lonlat(world, self.zoom)

    def _recenter_for_zoom_anchor(self, anchor_screen: QPointF, anchor_lonlat: LonLat) -> None:
        """Keep the anchor screen point fixed while zoom changes."""
        anchor_world = lonlat_to_world(anchor_lonlat, self.zoom)
        self.center = world_to_lonlat(
            ScreenPoint(
                anchor_world.x - anchor_screen.x() + self.width() / 2.0,
                anchor_world.y - anchor_screen.y() + self.height() / 2.0,
            ),
            self.zoom,
        )

    def _constrain_center(self, preserve_anchor: tuple[QPointF, LonLat] | None = None) -> None:
        """限制地图中心点不要拖出 offline_map.json 配置的 bounds 范围。"""
        center_world = lonlat_to_world(self.center, self.zoom)
        min_x, max_x, min_y, max_y = self.center_world_constraints()

        if min_x > max_x:
            clamped_x = (min_x + max_x) / 2.0
        else:
            clamped_x = min(max(center_world.x, min_x), max_x)

        if min_y > max_y:
            clamped_y = (min_y + max_y) / 2.0
        else:
            clamped_y = min(max(center_world.y, min_y), max_y)

        self.center = world_to_lonlat(ScreenPoint(clamped_x, clamped_y), self.zoom)
        if preserve_anchor is not None:
            anchor_screen, anchor_lonlat = preserve_anchor
            self._recenter_for_zoom_anchor(anchor_screen, anchor_lonlat)

    @staticmethod
    def _event_position(event) -> QPointF:
        """兼容不同 PyQt 事件对象，统一拿到鼠标位置。"""
        if hasattr(event, "position"):
            return event.position()
        if hasattr(event, "localPos"):
            return event.localPos()
        return QPointF(event.pos())

    def paintEvent(self, event) -> None:  # noqa: N802
        # 图层绘制顺序很重要：
        # 1. 底图瓦片 / 备用矢量要素
        # 2. 海陆分类图层
        # 3. 战术图层：范围圈、路线、临时路线、武器、单位、命中效果
        # 4. 左上角文字状态
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#dcecf2"))
        self._last_tile_paint_rect = None
        tiles_drawn = self._draw_tiles(painter)
        if not tiles_drawn and not self.tile_store.has_any_tiles():
            self._draw_grid(painter)
            for feature in self.map_document.features:
                self._draw_feature(painter, feature)
        elif not tiles_drawn:
            self._draw_missing_tiles_notice(painter)
        self._draw_land_sea_mask_layer(painter)
        self.tactical_layers.draw(painter)

    def _draw_tiles(self, painter: QPainter) -> bool:
        """绘制离线瓦片；先用粗层铺底，再叠加细层，避免高层缺片时出现空白。"""
        candidate_zooms = self.tile_store.fallback_zooms_for(self.zoom)
        if not candidate_zooms:
            return False

        drawn_any = False
        for tile_zoom in reversed(candidate_zooms):
            drawn_any = self._draw_tiles_for_zoom(painter, tile_zoom) or drawn_any
        if drawn_any:
            self._last_tile_paint_rect = QRectF(self.rect())
            painter.fillRect(self.rect(), QColor(255, 255, 255, 12))
        return drawn_any

    def _draw_tiles_for_zoom(self, painter: QPainter, tile_zoom: int) -> bool:
        current_center = lonlat_to_world(self.center, self.zoom)
        scale = 2.0 ** (self.zoom - tile_zoom)
        current_world_size = 256.0 * (2.0**self.zoom)

        left_world = current_center.x - self.width() / 2.0
        right_world = current_center.x + self.width() / 2.0
        top_world = current_center.y - self.height() / 2.0
        bottom_world = current_center.y + self.height() / 2.0

        tile_size = 256.0 * scale
        min_x = int(max(0, left_world // tile_size - 1))
        max_x = int(min(2**tile_zoom - 1, right_world // tile_size + 1))
        min_y = int(max(0, top_world // tile_size - 1))
        max_y = int(min(2**tile_zoom - 1, bottom_world // tile_size + 1))

        drawn = False
        drawn_rect: QRectF | None = None
        for tile_x in range(min_x, max_x + 1):
            for tile_y in range(min_y, max_y + 1):
                pixmap = self.tile_store.get_tile(tile_zoom, tile_x, tile_y)
                if pixmap is None:
                    continue
                tile_left_world = tile_x / (2**tile_zoom) * current_world_size
                tile_top_world = tile_y / (2**tile_zoom) * current_world_size
                screen_x = tile_left_world - current_center.x + self.width() / 2.0
                screen_y = tile_top_world - current_center.y + self.height() / 2.0
                tile_rect = QRectF(screen_x, screen_y, int(tile_size) + 1, int(tile_size) + 1)
                painter.drawPixmap(int(screen_x), int(screen_y), int(tile_size) + 1, int(tile_size) + 1, pixmap)
                drawn_rect = tile_rect if drawn_rect is None else drawn_rect.united(tile_rect)
                drawn = True
        return drawn

    def _draw_missing_tiles_notice(self, painter: QPainter) -> None:
        """当前 zoom 没有对应离线瓦片时，绘制提示文字。"""
        painter.fillRect(self.rect(), QColor("#dcecf2"))
        painter.setPen(QColor("#374151"))
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        painter.drawText(24, 48, "当前缩放级别没有离线瓦片，请下载更高 zoom 或缩小地图。")

    def _draw_grid(self, painter: QPainter) -> None:
        """没有任何离线瓦片时，画经纬度网格作为兜底背景。"""
        pen = QPen(QColor(103, 132, 145, 70), 1)
        painter.setPen(pen)
        min_lon, min_lat, max_lon, max_lat = self.map_document.bounds
        for lon in range(int(min_lon), int(max_lon) + 1):
            top = self._screen_from_lonlat(LonLat(lon, max_lat))
            bottom = self._screen_from_lonlat(LonLat(lon, min_lat))
            painter.drawLine(top, bottom)
        for lat in range(int(min_lat), int(max_lat) + 1):
            left = self._screen_from_lonlat(LonLat(min_lon, lat))
            right = self._screen_from_lonlat(LonLat(max_lon, lat))
            painter.drawLine(left, right)

    def _draw_feature(self, painter: QPainter, feature: MapFeature) -> None:
        """绘制 offline_map.json 里的备用矢量要素，例如陆地面、海岸线、参考航道。"""
        if len(feature.coordinates) < 2:
            return
        style = feature.style
        if feature.kind == "polygon":
            polygon = QPolygonF([self._screen_from_lonlat(point) for point in feature.coordinates])
            fill = QColor("#edf2dc") if style == "land" else QColor("#cadfea")
            painter.setBrush(fill)
            painter.setPen(QPen(QColor("#809170"), 1.2))
            painter.drawPolygon(polygon)
            return

        color = {
            "coast": QColor("#546f69"),
            "shipping": QColor("#2f6f9f"),
            "road": QColor("#d58b3a"),
            "boundary": QColor("#7b8794"),
        }.get(style, QColor("#425466"))
        width = 2.2 if style in {"coast", "shipping"} else 1.4
        painter.setPen(QPen(color, width, Qt.DashLine if style == "shipping" else Qt.SolidLine))
        path = QPainterPath(self._screen_from_lonlat(feature.coordinates[0]))
        for point in feature.coordinates[1:]:
            path.lineTo(self._screen_from_lonlat(point))
        painter.drawPath(path)

        if feature.name and self.zoom >= 7.0:
            painter.setPen(QColor("#2f3a3f"))
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.drawText(self._screen_from_lonlat(feature.coordinates[len(feature.coordinates) // 2]), feature.name)

    def _draw_land_sea_mask_layer(self, painter: QPainter) -> None:
        """绘制海陆分类图层：陆地浅黄色填充，海陆边界黑色虚线。"""
        painter.save()
        #land_fill = QColor(244, 238, 205, 82)
        land_edge_halo = QPen(QColor(255, 255, 255, 210), 3.4, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin)
        land_edge = QPen(QColor(0, 0, 0, 230), 1.7, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin)

        land_paths: list[QPainterPath] = []
        boundary_paths: list[QPainterPath] = []
        for feature in self.map_document.features:
            if len(feature.coordinates) < 2:
                continue
            if feature.kind == "polygon" and feature.style == "land":
                # land 多边形负责“陆地区域”，这里只做半透明填充，避免盖住底图细节。
                #path = self._path_from_points(feature.coordinates, closed=True)
                #land_paths.append(path)
                if feature.name.lower() != "fujian coast":
                    # 岛屿可以直接用闭合多边形当边界。
                    # 大陆不能画闭合外框，否则会出现人工矩形边，所以大陆只画 coast 线。
                    boundary_paths.append(self._path_from_points(feature.coordinates, closed=True))
            elif feature.kind == "line" and feature.style == "coast":
                boundary_paths.append(self._path_from_points(feature.coordinates, closed=False))

        #painter.setPen(Qt.NoPen)
        #painter.setBrush(land_fill)
        #for path in land_paths:
            #painter.drawPath(path)

        for pen in (land_edge_halo, land_edge):
            if self._last_tile_paint_rect is not None:
                painter.setClipRect(self._last_tile_paint_rect)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for path in boundary_paths:
                painter.drawPath(path)
            painter.setClipping(False)

        if self.zoom >= 7.0:
            painter.setPen(QColor(0, 0, 0, 220))
            painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
            painter.drawText(16, 52, "黑色虚线：海陆边界")
        painter.restore()

    def _path_from_points(self, points: list[LonLat], closed: bool = False) -> QPainterPath:
        """把一组经纬度点转成 QPainter 可以绘制的路径。"""
        path = QPainterPath(self._screen_from_lonlat(points[0]))
        for point in points[1:]:
            path.lineTo(self._screen_from_lonlat(point))
        if closed:
            path.closeSubpath()
        return path

    def _route_for_unit(self, unit: CombatUnit) -> UnitRoute:
        """获取某个单位当前绑定的路线。"""
        return self.motion_controller.route_for_unit(unit)

    def _draw_route_layer(self, painter: QPainter) -> None:
        """绘制已经保存到 routes.json 的红蓝路线图层。"""
        side = self.perspective_side()
        for route in self.layer_document.routes:
            if not route.visible or len(route.points) < 2:
                continue
            if side is not None and route.side != side:
                continue
            color = QColor("#085cf6") if route.side == "blue" else QColor("#f70808")
            path = QPainterPath(self._screen_from_lonlat(route.points[0]))
            for point in route.points[1:]:
                path.lineTo(self._screen_from_lonlat(point))
            # A light halo keeps tactical routes readable over raster-map terrain shadows.
            painter.setPen(QPen(QColor(255, 255, 255, 190), 4.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            pen = QPen(QColor(color.red(), color.green(), color.blue(), 190), 1.8, Qt.SolidLine)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)
            self._draw_route_arrows(painter, route, color)
            if self.zoom >= 8.2:
                painter.setPen(color)
                painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
                painter.drawText(self._screen_from_lonlat(route.points[0]) + QPointF(8, -8), route.name)

    def _draw_patrol_mission_layer(self, painter: QPainter) -> None:
        """Draw patrol mission areas and their reference points."""
        for mission in self.scenario.missions:
            if not isinstance(mission, PatrolMission) or len(mission.assigned_area) < 3:
                continue
            if not self._mission_visible(mission):
                continue
            color = self._mission_color(mission)
            area_points = [point.position for point in mission.assigned_area]
            polygon = QPolygonF([self._screen_from_lonlat(point) for point in area_points])
            fill = QColor(color)
            fill.setAlpha(34 if mission.active else 18)
            edge = QColor(color)
            edge.setAlpha(210 if mission.active else 120)

            painter.setBrush(fill)
            painter.setPen(QPen(edge, 2.0, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolygon(polygon)

            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
            for index, point in enumerate(area_points, 1):
                screen = self._screen_from_lonlat(point)
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(edge, 1.6))
                painter.drawEllipse(screen, 4.5, 4.5)
                if self.zoom >= 7.0:
                    painter.setPen(edge)
                    painter.drawText(screen + QPointF(7, -7), f"P{index}")

            if self.zoom >= 6.6:
                screens = [self._screen_from_lonlat(point) for point in area_points]
                center = QPointF(
                    sum(point.x() for point in screens) / len(screens),
                    sum(point.y() for point in screens) / len(screens),
                )
                painter.setPen(edge)
                painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
                painter.drawText(center + QPointF(8, -8), mission.name)

    def _draw_dynamic_route_layer(self, painter: QPainter) -> None:
        """Draw task-generated routes stored directly on units."""
        for unit in self.visible_units():
            if not unit.alive or unit.motion != "dynamic" or not unit.route.points:
                continue
            color = QColor("#145cf2") if unit.side == "blue" else QColor("#dc2626")
            start = self._position_for_unit(unit)
            path = QPainterPath(self._screen_from_lonlat(start))
            for point in unit.route.points:
                path.lineTo(self._screen_from_lonlat(point))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 190), 4.0, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 210), 2.0, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            target = unit.route.points[0]
            target_screen = self._screen_from_lonlat(target)
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 230), 2.0))
            painter.drawEllipse(target_screen, 5.0, 5.0)
            if self.zoom >= 7.0:
                painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
                label = "Patrol" if self._unit_has_patrol_mission(unit.unit_id) else "Waypoint"
                painter.drawText(target_screen + QPointF(8, -8), label)

    def _mission_color(self, mission: PatrolMission) -> QColor:
        for unit_id in mission.assigned_unit_ids:
            unit = next((candidate for candidate in self.scenario.units if candidate.unit_id == unit_id), None)
            if unit is not None:
                return QColor("#145cf2") if unit.side == "blue" else QColor("#dc2626")
        return QColor("#0f766e")

    def _mission_visible(self, mission: PatrolMission) -> bool:
        if self.is_god_perspective():
            return True
        side = self.perspective_side()
        if side is None:
            return False
        return any(
            (unit := self.unit_by_id(unit_id)) is not None and unit.side == side
            for unit_id in mission.assigned_unit_ids
        )

    def _unit_has_patrol_mission(self, unit_id: str) -> bool:
        return any(
            isinstance(mission, PatrolMission)
            and mission.active
            and unit_id in mission.assigned_unit_ids
            for mission in self.scenario.missions
        )

    def _draw_route_arrows(self, painter: QPainter, route: RouteLayerItem, color: QColor) -> None:
        """在路线中段绘制方向箭头，表示单位沿路线运动的方向。"""
        arrow_color = QColor(color.red(), color.green(), color.blue(), 210)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(arrow_color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for start, end in zip(route.points, route.points[1:]):
            start_screen = self._screen_from_lonlat(start)
            end_screen = self._screen_from_lonlat(end)
            dx = end_screen.x() - start_screen.x()
            dy = end_screen.y() - start_screen.y()
            length = max((dx * dx + dy * dy) ** 0.5, 1.0)
            ux = dx / length
            uy = dy / length
            if length < 36:
                continue
            tip = QPointF((start_screen.x() + end_screen.x()) / 2.0, (start_screen.y() + end_screen.y()) / 2.0)
            arrow_len = 9.0
            arrow_width = 4.0
            left = QPointF(tip.x() - ux * arrow_len - uy * arrow_width, tip.y() - uy * arrow_len + ux * arrow_width)
            right = QPointF(tip.x() - ux * arrow_len + uy * arrow_width, tip.y() - uy * arrow_len - ux * arrow_width)
            painter.drawLine(left, tip)
            painter.drawLine(right, tip)

    def _draw_range_layer(self, painter: QPainter) -> None:
        """Draw the selected unit's radar/detection range ring."""
        if not self.show_radar_ranges:
            return
        selected_unit = self._selected_visible_unit()
        if selected_unit is not None:
            self._draw_detection_range_ring(painter, selected_unit, highlighted=True)

    def _draw_detection_range_ring(self, painter: QPainter, unit: CombatUnit, highlighted: bool) -> None:
        """Draw one unit's radar/detection range ring."""
        range_nm = unit.detection_range_nm or unit.range_nm
        if range_nm <= 0:
            return
        position = self._position_for_unit(unit)
        screen = self._screen_from_lonlat(position)
        edge = self._screen_from_lonlat(LonLat(position.lon + self._nm_to_lon_degrees(range_nm, position.lat), position.lat))
        radius = abs(edge.x() - screen.x())
        color = QColor("#145cf2") if unit.side == "blue" else QColor("#dc2626")
        fill = QColor(color)
        fill_alpha = 76 if highlighted else 50
        fill.setAlpha(0 if radius > max(self.width(), self.height()) * 0.42 else fill_alpha)
        painter.setBrush(fill)
        ring_color = QColor("#facc15") if highlighted else QColor(color.red(), color.green(), color.blue(), 100)
        ring_pen = QPen(ring_color, 3.4 if highlighted else 1.5, Qt.SolidLine)
        painter.setPen(ring_pen)
        painter.drawEllipse(screen, radius, radius)
        if highlighted:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 210), 1.2, Qt.DashLine))
            painter.drawEllipse(screen, radius + 4.0, radius + 4.0)

    def _draw_radar_animation_layer(self, painter: QPainter) -> None:
        """Draw optional radar sweep and pulse effects for the selected active radar unit."""
        if not self.show_radar_ranges or not self.show_radar_animation:
            return
        max_visible_radius = max(self.width(), self.height()) * 0.9
        unit = self._selected_visible_unit()
        if unit is None or not bool(getattr(unit, "radar_on", True)):
            return
        range_nm = unit.detection_range_nm or unit.range_nm
        if range_nm <= 0:
            return
        position = self._position_for_unit(unit)
        screen = self._screen_from_lonlat(position)
        edge = self._screen_from_lonlat(
            LonLat(position.lon + self._nm_to_lon_degrees(range_nm, position.lat), position.lat)
        )
        radius = abs(edge.x() - screen.x())
        if radius <= 4.0 or radius > max_visible_radius:
            return
        self._draw_radar_sweep(painter, unit, screen, radius, highlighted=True)
        self._draw_radar_pulse(painter, unit, screen, radius, highlighted=True)

    def _selected_visible_unit(self) -> CombatUnit | None:
        """Return the selected real unit when it can be rendered in the current perspective."""
        if self._selected_unit_id is None:
            return None
        unit = self.visible_unit_by_id(self._selected_unit_id)
        if unit is None or not unit.alive:
            return None
        return unit

    def _draw_radar_sweep(self, painter: QPainter, unit: CombatUnit, screen: QPointF, radius: float, highlighted: bool) -> None:
        unit_offset = sum(ord(character) for character in unit.unit_id) % 360
        sweep_angle = (self._smooth_time * 90.0 + unit_offset) % 360.0
        sweep_width = 34.0 if highlighted else 24.0
        color = QColor("#facc15" if highlighted else ("#38bdf8" if unit.side == "blue" else "#fb7185"))
        color.setAlpha(82 if highlighted else 36)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        rect = QRectF(screen.x() - radius, screen.y() - radius, radius * 2.0, radius * 2.0)
        painter.drawPie(rect, int(-sweep_angle * 16), int(-sweep_width * 16))

    def _draw_radar_pulse(self, painter: QPainter, unit: CombatUnit, screen: QPointF, radius: float, highlighted: bool) -> None:
        unit_offset = (sum(ord(character) for character in unit.unit_id) % 100) / 100.0
        pulse_phase = (self._smooth_time * (0.58 if highlighted else 0.35) + unit_offset) % 1.0
        pulse_radius = max(5.0, radius * pulse_phase)
        alpha = int((190 if highlighted else 45) * (1.0 - pulse_phase))
        if alpha <= 0:
            return
        color = QColor("#facc15" if highlighted else ("#38bdf8" if unit.side == "blue" else "#fb7185"))
        color.setAlpha(alpha)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color, 4.2 if highlighted else 1.4, Qt.SolidLine))
        painter.drawEllipse(screen, pulse_radius, pulse_radius)
        if highlighted:
            glow = QColor("#facc15")
            glow.setAlpha(max(20, alpha // 3))
            painter.setBrush(QColor(250, 204, 21, max(12, alpha // 8)))
            painter.setPen(QPen(glow, 8.0, Qt.SolidLine))
            painter.drawEllipse(screen, pulse_radius + 3.0, pulse_radius + 3.0)

    def _draw_electromagnetic_layer(self, painter: QPainter) -> None:
        """Draw jammer coverage ring for the selected unit when it is emitting electronic attack."""
        if not self.show_radar_ranges:
            return
        unit = self._selected_visible_unit()
        if unit is None:
            return
        jammer_range_nm = max(0.0, float(getattr(unit, "jammer_range_nm", 0.0)))
        jammer_power = max(0.0, float(getattr(unit, "jammer_power", 0.0)))
        if jammer_range_nm <= 0.0 or jammer_power <= 0.0:
            return
        position = self._position_for_unit(unit)
        screen = self._screen_from_lonlat(position)
        edge = self._screen_from_lonlat(
            LonLat(position.lon + self._nm_to_lon_degrees(jammer_range_nm, position.lat), position.lat)
        )
        radius = abs(edge.x() - screen.x())
        color = QColor("#f59e0b") if unit.side == "blue" else QColor("#d946ef")
        fill = QColor(color)
        fill.setAlpha(0 if radius > max(self.width(), self.height()) * 0.46 else 34)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 130), 1.6, Qt.DashLine))
        painter.drawEllipse(screen, radius, radius)

    def _draw_communications_overlay(self, painter: QPainter) -> None:
        """Draw selected-unit communication range, datalinks, and shared contacts."""
        if not self.show_communications_overlay or self._selected_unit_id is None:
            return
        selected = self.visible_unit_by_id(self._selected_unit_id)
        if selected is None or not selected.alive:
            return
        self._draw_selected_comms_range(painter, selected)
        self._draw_selected_datalinks(painter, selected)
        self._draw_shared_contact_markers(painter, selected.side)

    def _draw_selected_comms_range(self, painter: QPainter, unit: CombatUnit) -> None:
        comms_range_nm = max(0.0, float(getattr(unit, "comms_range_nm", 0.0)))
        if comms_range_nm <= 0.0 or not bool(getattr(unit, "comms_on", True)):
            return
        position = self._position_for_unit(unit)
        screen = self._screen_from_lonlat(position)
        edge = self._screen_from_lonlat(
            LonLat(position.lon + self._nm_to_lon_degrees(comms_range_nm, position.lat), position.lat)
        )
        radius = abs(edge.x() - screen.x())
        fill = QColor("#22d3ee")
        fill.setAlpha(0 if radius > max(self.width(), self.height()) * 0.48 else 22)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(34, 211, 238, 190), 2.2, Qt.DashLine))
        painter.drawEllipse(screen, radius, radius)

    def _draw_selected_datalinks(self, painter: QPainter, selected: CombatUnit) -> None:
        selected_screen = self._screen_from_lonlat(self._position_for_unit(selected))
        links = build_network_links(selected, [unit for unit in self.visible_units() if unit.alive])
        for link in links:
            receiver = self.unit_by_id(link.receiver_id)
            if receiver is None:
                continue
            receiver_screen = self._screen_from_lonlat(self._position_for_unit(receiver))
            color = QColor("#f97316") if link.degraded else QColor("#22d3ee")
            painter.setPen(QPen(color, 2.0, Qt.DashLine if link.degraded else Qt.SolidLine))
            painter.drawLine(selected_screen, receiver_screen)
            midpoint = QPointF(
                (selected_screen.x() + receiver_screen.x()) / 2.0,
                (selected_screen.y() + receiver_screen.y()) / 2.0,
            )
            painter.setPen(QColor("#0f172a"))
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
            painter.drawText(midpoint + QPointF(4, -4), f"{link.quality:.1f}")

    def _draw_shared_contact_markers(self, painter: QPainter, side: str) -> None:
        tracks = self.combat_controller.contact_tracks.get(side, {})
        if not tracks:
            return
        painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
        for track in tracks.values():
            if not track.shared:
                continue
            screen = self._screen_from_lonlat(track.last_known_position)
            confidence = track.decayed_confidence(self._last_combat_step_time)
            color = QColor("#22c55e") if confidence >= 0.7 else QColor("#f97316")
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 60))
            painter.setPen(QPen(color, 2.0, Qt.DashLine))
            painter.drawEllipse(screen, 16.0, 16.0)
            painter.setPen(color)
            painter.drawText(screen + QPointF(12, -14), f"SHARED {confidence:.1f}")

    @staticmethod
    def _nm_to_lon_degrees(radius_nm: float, lat: float) -> float:
        """把海里半径粗略换算成经度跨度，用于在屏幕上画范围圈。"""
        import math

        nm_per_degree = max(1.0, 60.0 * math.cos(math.radians(lat)))
        return radius_nm / nm_per_degree

    def _draw_route_drafts(self, painter: QPainter) -> None:
        """绘制右键设置路线时的临时起点、途经点、终点。"""
        visible_side = self.perspective_side()
        for side, draft in self.route_drafts.items():
            if visible_side is not None and side != visible_side:
                continue
            color = QColor("#145cf2") if side == "blue" else QColor("#dc2626")
            points: list[tuple[str, LonLat]] = []
            start = draft.get("start")
            end = draft.get("end")
            waypoints = draft.get("waypoints", [])
            if isinstance(start, LonLat):
                points.append(("起点", start))
            if isinstance(waypoints, list):
                for index, point in enumerate(waypoints, 1):
                    if isinstance(point, LonLat):
                        points.append((f"途经{index}", point))
            if isinstance(end, LonLat):
                points.append(("终点", end))
            if not points:
                continue

            painter.setPen(QPen(color, 2, Qt.SolidLine))
            if len(points) >= 2:
                path = QPainterPath(self._screen_from_lonlat(points[0][1]))
                for _, point in points[1:]:
                    path.lineTo(self._screen_from_lonlat(point))
                painter.drawPath(path)

            painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
            for label, point in points:
                screen = self._screen_from_lonlat(point)
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(color, 2))
                painter.drawRect(int(screen.x() - 6), int(screen.y() - 6), 12, 12)
                painter.setPen(color)
                painter.drawText(screen + QPointF(10, -8), f"{side.upper()} {label}")

    def _draw_unit_layer(self, painter: QPainter) -> None:
        """绘制战斗单元，包括运动中的舰艇/飞机和静态机场/雷达。"""
        for unit in self.visible_units():
            position = self._position_for_unit(unit)
            screen = self._screen_from_lonlat(position)
            color = QColor("#145cf2") if unit.side == "blue" else QColor("#dc2626")
            if not unit.alive:
                color = QColor("#6b7280")
            if unit.unit_id == self._selected_unit_id:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#facc15"), 3.0))
                painter.drawEllipse(screen, 22.0, 22.0)
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            self._draw_unit_symbol(painter, unit, screen, color)
            if not unit.alive:
                painter.setPen(QPen(QColor("#111827"), 2.2))
                painter.drawLine(screen + QPointF(-10, -10), screen + QPointF(10, 10))
                painter.drawLine(screen + QPointF(10, -10), screen + QPointF(-10, 10))
            if self.zoom >= 7.4:
                painter.setPen(QColor("#111827"))
                painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
                suffix = " 已毁伤" if not unit.alive else ""
                painter.drawText(screen + QPointF(10, -10), f"{unit.name}{suffix}")
        if not self.is_god_perspective():
            for track in self.visible_enemy_tracks():
                self._draw_contact_marker(painter, track)

    def _draw_contact_marker(self, painter: QPainter, track: ContactTrack) -> None:
        """Draw a side-view enemy contact without revealing truth-state details."""
        screen = self._screen_from_lonlat(track.last_known_position)
        confidence = track.decayed_confidence(self._last_combat_step_time)
        stale = track.is_stale(self._last_combat_step_time)
        color = QColor("#f97316" if stale else "#22c55e")
        fill = QColor(color.red(), color.green(), color.blue(), 60)
        painter.setBrush(fill)
        painter.setPen(QPen(color, 2.2, Qt.DashLine))
        diamond = QPolygonF(
            [
                screen + QPointF(0, -13),
                screen + QPointF(13, 0),
                screen + QPointF(0, 13),
                screen + QPointF(-13, 0),
            ]
        )
        if track.target_id == self._selected_unit_id:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#facc15"), 3.0))
            painter.drawEllipse(screen, 22.0, 22.0)
            painter.setBrush(fill)
            painter.setPen(QPen(color, 2.2, Qt.DashLine))
        painter.drawPolygon(diamond)
        if self.zoom >= 7.4:
            state = "STALE" if stale else ("SHARED" if track.shared else "LOCAL")
            painter.setPen(color)
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
            painter.drawText(screen + QPointF(12, -14), f"{state} {track.target_id} {confidence:.1f}")

    def _position_for_unit(self, unit: CombatUnit) -> LonLat:
        """Return a live unit's simulated position or a destroyed unit's last position."""
        if not unit.alive and unit.position is not None:
            return unit.position
        return self.motion_controller.position_for(unit)

    def _unit_at_screen(self, point: QPointF, radius_px: float = 20.0) -> CombatUnit | None:
        """Hit-test units by their current screen-space symbol centers."""
        best_unit: CombatUnit | None = None
        best_distance_sq = radius_px * radius_px
        for unit in reversed(self.visible_units()):
            if not unit.alive:
                continue
            screen = self._screen_from_lonlat(self._position_for_unit(unit))
            delta_x = screen.x() - point.x()
            delta_y = screen.y() - point.y()
            distance_sq = delta_x * delta_x + delta_y * delta_y
            if distance_sq <= best_distance_sq:
                best_unit = unit
                best_distance_sq = distance_sq
        return best_unit

    def _contact_at_screen(self, point: QPointF, radius_px: float = 20.0) -> ContactTrack | None:
        """Hit-test visible enemy contacts by their last-known positions."""
        best_track: ContactTrack | None = None
        best_distance_sq = radius_px * radius_px
        for track in reversed(self.visible_enemy_tracks()):
            screen = self._screen_from_lonlat(track.last_known_position)
            delta_x = screen.x() - point.x()
            delta_y = screen.y() - point.y()
            distance_sq = delta_x * delta_x + delta_y * delta_y
            if distance_sq <= best_distance_sq:
                best_track = track
                best_distance_sq = distance_sq
        return best_track

    def _draw_weapon_layer(self, painter: QPainter) -> None:
        """Draw launched weapons and short dashed trails."""
        side = self.perspective_side()
        for weapon in self.scenario.flying_weapons:
            if side is not None and weapon.side != side and self.contact_track_for_unit(weapon.target_id) is None:
                continue
            color = QColor("#145cf2") if weapon.side == "blue" else QColor("#dc2626")
            painter.save()
            if weapon.trail:
                trail_points = weapon.trail[-8:] + [weapon.position]
                path = QPainterPath(self._screen_from_lonlat(trail_points[0]))
                for point in trail_points[1:]:
                    path.lineTo(self._screen_from_lonlat(point))
                trail_pen = QPen(QColor(color.red(), color.green(), color.blue(), 155), 1.8, Qt.DashLine)
                trail_pen.setCapStyle(Qt.RoundCap)
                painter.setPen(trail_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)

            screen = self._screen_from_lonlat(weapon.position)
            heading = math.radians(weapon.heading)
            forward = QPointF(math.sin(heading), -math.cos(heading))
            right = QPointF(math.cos(heading), math.sin(heading))
            tip = screen + forward * 11.0
            left = screen - forward * 7.0 - right * 5.0
            right_point = screen - forward * 7.0 + right * 5.0
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#ffffff"), 1.4))
            painter.drawPolygon(QPolygonF([tip, left, right_point]))
            painter.restore()

    def _draw_impact_layer(self, painter: QPainter) -> None:
        """Draw short-lived hit or miss effects."""
        for point, created_at, kind, source_id, target_id in self._impact_effects:
            if not self._combat_event_visible(source_id, target_id):
                continue
            age = max(0.0, self._smooth_time - created_at)
            alpha = max(0, int(220 * (1.0 - age / 1.2)))
            radius = 10.0 + age * 18.0
            screen = self._screen_from_lonlat(point)
            color = QColor("#f97316" if kind == "hit" else "#facc15")
            color.setAlpha(alpha)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), max(0, alpha // 3)))
            painter.setPen(QPen(color, 2.2))
            painter.drawEllipse(screen, radius, radius)

    def _combat_event_visible(self, source_id: str, target_id: str) -> bool:
        side = self.perspective_side()
        if side is None:
            return True
        for unit_id in (source_id, target_id):
            unit = self.unit_by_id(unit_id)
            if unit is not None and unit.side == side:
                return True
            if self.contact_track_for_unit(unit_id) is not None:
                return True
        return False

    def _draw_unit_symbol(self, painter: QPainter, unit: CombatUnit, screen: QPointF, color: QColor) -> None:
        """根据单位类型绘制对应图标；优先使用 assets/svg 下的 SVG。"""
        heading = unit.heading if unit.unit_type == "aircraft" else 0.0

        icon_name = self._unit_icon_name(unit)
        if icon_name:
            self._draw_svg_unit_icon(painter, icon_name, screen, color, heading)
            return

        painter.save()
        painter.translate(screen)
        painter.rotate(heading)

        if unit.unit_type == "ship":
            points = QPolygonF(
                [
                    QPointF(0, -10),
                    QPointF(9, 4),
                    QPointF(4, 10),
                    QPointF(-4, 10),
                    QPointF(-9, 4),
                ]
            )
            painter.drawPolygon(points)
            painter.restore()
            return
        if unit.unit_type == "facility":
            painter.drawRect(-8, -8, 16, 16)
            painter.drawLine(QPointF(-11, 0), QPointF(11, 0))
            painter.drawLine(QPointF(0, -11), QPointF(0, 11))
            painter.restore()
            return
        if unit.unit_type == "airbase":
            painter.drawRect(-9, -6, 18, 12)
            painter.drawLine(QPointF(-12, 0), QPointF(12, 0))
            painter.restore()
            return
        if unit.unit_type == "ground_vehicle":
            body = QPolygonF(
                [
                    QPointF(-11, -6),
                    QPointF(8, -6),
                    QPointF(11, -2),
                    QPointF(11, 6),
                    QPointF(-11, 6),
                ]
            )
            painter.drawPolygon(body)
            painter.drawRect(-5, -11, 14, 5)
            painter.drawLine(QPointF(2, -11), QPointF(13, -16))
            painter.drawEllipse(QPointF(-6, 7), 2.5, 2.5)
            painter.drawEllipse(QPointF(6, 7), 2.5, 2.5)
            painter.restore()
            return
        points = QPolygonF(
            [
                QPointF(0, -12),
                QPointF(5, 6),
                QPointF(0, 3),
                QPointF(-5, 6),
            ]
        )
        painter.drawPolygon(points)
        painter.restore()

    def _unit_icon_name(self, unit: CombatUnit) -> str | None:
        return unit_icon_name(unit)

    def _draw_svg_unit_icon(self, painter: QPainter, icon_name: str, screen: QPointF, color: QColor, heading: float) -> None:
        """绘制 SVG 单位图标。"""
        draw_svg_unit_icon(painter, icon_name, screen, color, heading)

    def _draw_overlay(self, painter: QPainter) -> None:
        """绘制左上角地图状态文字，例如当前 zoom 和瓦片来源。"""
        painter.setPen(QColor("#1f2937"))
        painter.setFont(QFont("Microsoft YaHei UI", 10))
        best_zoom = self.tile_store.best_zoom_for(self.zoom)
        source = f"offline tiles z{best_zoom}" if best_zoom is not None else "fallback vector"
        painter.drawText(16, 28, f"{self.map_document.name}  zoom={self.zoom:.1f}  {source}  {self.perspective_label()}")

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """鼠标移动：更新经纬度显示；按住左键时拖动地图。"""
        lonlat = self._lonlat_from_screen(event.localPos())
        self.coordinateHovered.emit(lonlat.lon, lonlat.lat)
        if self._left_press_pos is not None and event.buttons() & Qt.LeftButton:
            delta = event.pos() - self._left_press_pos
            if delta.manhattanLength() > 4:
                self._left_dragged = True
        if self._last_mouse_pos is not None and event.buttons() & Qt.LeftButton:
            old_lonlat = self._lonlat_from_screen(QPointF(self._last_mouse_pos))
            new_lonlat = self._lonlat_from_screen(event.localPos())
            self.center = LonLat(
                self.center.lon + old_lonlat.lon - new_lonlat.lon,
                self.center.lat + old_lonlat.lat - new_lonlat.lat,
            )
            self._constrain_center()
            self.update()
            self.viewportChanged.emit()
        self._last_mouse_pos = event.pos()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """鼠标按下：右键查看单位信息，左键用于准备拖动地图。"""
        if event.button() == Qt.RightButton:
            unit = self._unit_at_screen(QPointF(event.pos()))
            if unit is not None and self.select_unit(unit.unit_id):
                self.unitRightClicked.emit(unit.unit_id)
            elif (track := self._contact_at_screen(QPointF(event.pos()))) is not None and self.select_unit(track.target_id):
                self.unitRightClicked.emit(track.target_id)
            else:
                lonlat = self._lonlat_from_screen(QPointF(event.pos()))
                self.mapRightClicked.emit(lonlat.lon, lonlat.lat)
            self._last_mouse_pos = event.pos()
            return
        if event.button() == Qt.LeftButton:
            self._left_press_pos = event.pos()
            self._left_dragged = False
        self._last_mouse_pos = event.pos()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """鼠标松开：结束地图拖动状态。"""
        if event.button() == Qt.LeftButton and self._left_press_pos is not None:
            delta = event.pos() - self._left_press_pos
            if not self._left_dragged and delta.manhattanLength() <= 4:
                if self._apply_pending_interaction(QPointF(event.pos())):
                    self._left_press_pos = None
                    self._left_dragged = False
                    self._last_mouse_pos = None
                    return
                unit = self._unit_at_screen(QPointF(event.pos()))
                if unit is None:
                    track = self._contact_at_screen(QPointF(event.pos()))
                    if track is None:
                        self._selected_unit_id = None
                        self.mapLeftClicked.emit()
                    else:
                        self._selected_unit_id = track.target_id
                        self.unitLeftClicked.emit(track.target_id)
                else:
                    self._selected_unit_id = unit.unit_id
                    self.unitLeftClicked.emit(unit.unit_id)
                self.update()
            self._left_press_pos = None
            self._left_dragged = False
        self._last_mouse_pos = None

    def _apply_pending_interaction(self, screen_point: QPointF) -> bool:
        mode = self._interaction_mode
        if mode == "none":
            return False

        lonlat = self._lonlat_from_screen(screen_point)
        if mode == "pick_coordinate":
            self.clear_interaction_mode()
            self._selected_unit_id = None
            self.mapCoordinatePicked.emit(lonlat.lon, lonlat.lat)
            self.update()
            return True

        if self._pending_unit_id is None:
            self.clear_interaction_mode()
            return False

        unit = self.operable_unit_by_id(self._pending_unit_id)
        unit_id = self._pending_unit_id
        self.clear_interaction_mode()
        if unit is None:
            return True
        if mode == "edit_location":
            unit.position = lonlat
            unit.route = UnitRoute([])
            unit.motion = "stationary"
            unit.route_id = ""
        elif mode == "plot_course":
            unit.route = UnitRoute([lonlat])
            unit.motion = "dynamic"
            unit.route_id = ""
            if unit.position is None:
                unit.position = lonlat
        else:
            return True
        self.motion_controller.reset()
        self._selected_unit_id = unit_id
        self.update()
        self.viewportChanged.emit()
        self.unitUpdated.emit(unit_id)
        return True

    def wheelEvent(self, event) -> None:  # noqa: N802
        """滚轮缩放地图，并尽量保持鼠标指向的经纬度不变。"""
        event_position = self._event_position(event)
        anchor_lonlat = self._lonlat_from_screen(event_position)
        delta = event.angleDelta().y()
        next_zoom = max(
            self.map_document.min_zoom,
            min(self.map_document.max_zoom, self.zoom + (0.35 if delta > 0 else -0.35)),
        )
        if next_zoom == self.zoom:
            return
        self.zoom = next_zoom
        self._recenter_for_zoom_anchor(event_position, anchor_lonlat)
        self._constrain_center((event_position, anchor_lonlat))
        self.update()
        self.viewportChanged.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """窗口大小变化后重新约束地图中心点，防止视角越界。"""
        self._constrain_center()
        self.viewportChanged.emit()
        super().resizeEvent(event)
