from __future__ import annotations

import math
from typing import Any

from PyQt5.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSlider, QVBoxLayout, QWidget

from simulation.controllers.tile_store import TileStore
from simulation.core.geo import LonLat, ScreenPoint, lonlat_to_world, world_to_lonlat
from simulation.core.map_document import MapDocument, MapFeature, load_map_document
from simulation.core.paths import get_map_asset_path
from simulation.replay.runtime import ReplayRuntime
from simulation.ui.unit_icons import draw_svg_unit_icon, unit_icon_name


DEFAULT_REPLAY_ZOOM = 7.0
REPLAY_STATUS_OVERLAY_HEIGHT = 56

EVENT_TYPE_LABELS = {
    "detected": "探测",
    "shared_contact": "共享",
    "launched": "发射",
    "hit": "命中",
    "unit_destroyed": "击毁",
    "miss": "未命中",
    "expired": "失效",
    "lost_target": "丢失目标",
}


class ReplayMapCanvas(QWidget):
    """Replay-only canvas that uses the same offline map source as the main page."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ReplayMapCanvas")
        self.setMinimumSize(980, 620)
        self.map_document: MapDocument = load_map_document(get_map_asset_path())
        self.tile_store = TileStore(self.map_document.tile_root)
        self.center = self.map_document.center
        self.zoom = DEFAULT_REPLAY_ZOOM
        self._state: dict[str, Any] = {"units": [], "flying_weapons": [], "contacts": []}
        self._current_time = 0.0
        self._last_tile_paint_rect: QRectF | None = None
        self._auto_fit_enabled = True
        self.show_radar_ranges = True
        self.show_communications_overlay = True
        self.selected_unit_id: str | None = None

    def state(self) -> dict[str, Any]:
        return self._state

    def set_state(self, state: dict[str, Any]) -> None:
        self._state = dict(state)
        self._current_time = float(state.get("current_time", 0.0))
        self._ensure_selected_unit()
        if self._auto_fit_enabled:
            self._fit_to_state()
        self.update()

    def set_radar_ranges_visible(self, visible: bool) -> None:
        self.show_radar_ranges = bool(visible)
        self.update()

    def set_communications_overlay_visible(self, visible: bool) -> None:
        self.show_communications_overlay = bool(visible)
        self.update()

    def _ensure_selected_unit(self) -> None:
        units = self._state.get("units", [])
        if any(unit.get("unit_id") == self.selected_unit_id for unit in units):
            return
        selected = next((unit for unit in units if unit.get("alive", False)), units[0] if units else None)
        self.selected_unit_id = None if selected is None else str(selected.get("unit_id", ""))

    def paintEvent(self, event) -> None:  # noqa: N802
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
        self._draw_land_sea_boundary(painter)
        self._draw_contacts(painter)
        self._draw_display_control_layers(painter)
        self._draw_weapons(painter)
        self._draw_units(painter)
        self._draw_status_text(painter)

    def _fit_to_state(self) -> None:
        points = self._state_points()
        if not points:
            self.center = self.map_document.center
            self.zoom = DEFAULT_REPLAY_ZOOM
            return
        min_lon = min(point.lon for point in points)
        max_lon = max(point.lon for point in points)
        min_lat = min(point.lat for point in points)
        max_lat = max(point.lat for point in points)
        self.center = LonLat((min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0)
        lon_span = max(0.15, max_lon - min_lon)
        lat_span = max(0.15, max_lat - min_lat)
        span = max(lon_span, lat_span)
        self.zoom = 8.2 if span < 0.5 else 7.6 if span < 1.0 else DEFAULT_REPLAY_ZOOM

    def _state_points(self) -> list[LonLat]:
        points: list[LonLat] = []
        for unit in self._state.get("units", []):
            if point := self._point_from_dict(unit.get("position")):
                points.append(point)
        for weapon in self._state.get("flying_weapons", []):
            if point := self._point_from_dict(weapon.get("position")):
                points.append(point)
            for trail_point in weapon.get("trail", []):
                if point := self._point_from_dict(trail_point):
                    points.append(point)
        for contact in self._state.get("contacts", []):
            if point := self._point_from_dict(contact.get("last_known_position")):
                points.append(point)
        return points

    @staticmethod
    def _point_from_dict(raw: object) -> LonLat | None:
        if not isinstance(raw, dict):
            return None
        try:
            return LonLat(float(raw["lon"]), float(raw["lat"]))
        except (KeyError, TypeError, ValueError):
            return None

    def _screen_from_lonlat(self, point: LonLat) -> QPointF:
        center_world = lonlat_to_world(self.center, self.zoom)
        world = lonlat_to_world(point, self.zoom)
        return QPointF(
            world.x - center_world.x + self.width() / 2.0,
            world.y - center_world.y + self.height() / 2.0,
        )

    def _lonlat_from_screen(self, point: QPointF) -> LonLat:
        center_world = lonlat_to_world(self.center, self.zoom)
        world = ScreenPoint(
            center_world.x + point.x() - self.width() / 2.0,
            center_world.y + point.y() - self.height() / 2.0,
        )
        return world_to_lonlat(world, self.zoom)

    def apply_zoom_delta(self, steps: int, anchor: QPointF | None = None) -> None:
        if steps == 0:
            return
        self._auto_fit_enabled = False
        anchor = anchor or QPointF(self.width() / 2.0, self.height() / 2.0)
        anchor_lonlat = self._lonlat_from_screen(anchor)
        self.zoom = max(5.0, min(11.0, self.zoom + steps * 0.35))
        anchor_world = lonlat_to_world(anchor_lonlat, self.zoom)
        center_world = ScreenPoint(
            anchor_world.x - anchor.x() + self.width() / 2.0,
            anchor_world.y - anchor.y() + self.height() / 2.0,
        )
        self.center = world_to_lonlat(center_world, self.zoom)
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self.apply_zoom_delta(1 if delta > 0 else -1, event.pos())
        event.accept()

    def _draw_tiles(self, painter: QPainter) -> bool:
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
        for tile_x in range(min_x, max_x + 1):
            for tile_y in range(min_y, max_y + 1):
                pixmap = self.tile_store.get_tile(tile_zoom, tile_x, tile_y)
                if pixmap is None:
                    continue
                tile_left_world = tile_x / (2**tile_zoom) * current_world_size
                tile_top_world = tile_y / (2**tile_zoom) * current_world_size
                screen_x = tile_left_world - current_center.x + self.width() / 2.0
                screen_y = tile_top_world - current_center.y + self.height() / 2.0
                painter.drawPixmap(int(screen_x), int(screen_y), int(tile_size) + 1, int(tile_size) + 1, pixmap)
                drawn = True
        return drawn

    def _draw_missing_tiles_notice(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor("#dcecf2"))
        painter.setPen(QColor("#374151"))
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        painter.drawText(24, 48, "当前缩放级别没有离线瓦片，正在显示备用地图。")

    def _draw_grid(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(103, 132, 145, 70), 1))
        min_lon, min_lat, max_lon, max_lat = self.map_document.bounds
        for lon in range(int(min_lon), int(max_lon) + 1):
            painter.drawLine(
                self._screen_from_lonlat(LonLat(lon, max_lat)),
                self._screen_from_lonlat(LonLat(lon, min_lat)),
            )
        for lat in range(int(min_lat), int(max_lat) + 1):
            painter.drawLine(
                self._screen_from_lonlat(LonLat(min_lon, lat)),
                self._screen_from_lonlat(LonLat(max_lon, lat)),
            )

    def _draw_feature(self, painter: QPainter, feature: MapFeature) -> None:
        if len(feature.coordinates) < 2:
            return
        if feature.kind == "polygon":
            fill = QColor("#edf2dc") if feature.style == "land" else QColor("#cadfea")
            painter.setBrush(fill)
            painter.setPen(QPen(QColor("#809170"), 1.2))
            painter.drawPolygon(QPolygonF([self._screen_from_lonlat(point) for point in feature.coordinates]))
            return
        color = {
            "coast": QColor("#546f69"),
            "shipping": QColor("#2f6f9f"),
            "road": QColor("#d58b3a"),
            "boundary": QColor("#7b8794"),
        }.get(feature.style, QColor("#425466"))
        painter.setPen(QPen(color, 2.2 if feature.style in {"coast", "shipping"} else 1.4))
        path = QPainterPath(self._screen_from_lonlat(feature.coordinates[0]))
        for point in feature.coordinates[1:]:
            path.lineTo(self._screen_from_lonlat(point))
        painter.drawPath(path)

    def _draw_land_sea_boundary(self, painter: QPainter) -> None:
        paths: list[QPainterPath] = []
        for feature in self.map_document.features:
            if len(feature.coordinates) < 2:
                continue
            if feature.kind == "line" and feature.style == "coast":
                paths.append(self._path_from_points(feature.coordinates, closed=False))
            elif feature.kind == "polygon" and feature.style == "land" and feature.name.lower() != "fujian coast":
                paths.append(self._path_from_points(feature.coordinates, closed=True))
        painter.save()
        for pen in (
            QPen(QColor(255, 255, 255, 210), 3.4, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin),
            QPen(QColor(0, 0, 0, 230), 1.7, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin),
        ):
            if self._last_tile_paint_rect is not None:
                painter.setClipRect(self._last_tile_paint_rect)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for path in paths:
                painter.drawPath(path)
            painter.setClipping(False)
        painter.restore()

    def _path_from_points(self, points: list[LonLat], closed: bool) -> QPainterPath:
        path = QPainterPath(self._screen_from_lonlat(points[0]))
        for point in points[1:]:
            path.lineTo(self._screen_from_lonlat(point))
        if closed:
            path.closeSubpath()
        return path

    def _draw_units(self, painter: QPainter) -> None:
        for unit in self._state.get("units", []):
            point = self._point_from_dict(unit.get("position"))
            if point is None:
                continue
            screen = self._screen_from_lonlat(point)
            side = str(unit.get("side", ""))
            alive = bool(unit.get("alive", False))
            color = QColor("#145cf2") if side == "blue" else QColor("#dc2626")
            if not alive:
                color = QColor("#6b7280")
            if unit.get("unit_id") == self.selected_unit_id:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#facc15"), 3.0))
                painter.drawEllipse(screen, 22.0, 22.0)
            icon_name = self._unit_icon_name(unit)
            heading = float(unit.get("heading", 0.0) or 0.0) if str(unit.get("unit_type", "")).lower() == "aircraft" else 0.0
            if icon_name:
                draw_svg_unit_icon(painter, icon_name, screen, color, heading)
            else:
                painter.setBrush(color)
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.drawEllipse(screen, 8.0, 8.0)
            if not alive:
                painter.setPen(QPen(QColor("#111827"), 2.2))
                painter.drawLine(screen + QPointF(-10, -10), screen + QPointF(10, 10))
                painter.drawLine(screen + QPointF(10, -10), screen + QPointF(-10, 10))
            painter.setPen(QColor("#111827"))
            painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
            suffix = " 已毁伤" if not alive else ""
            painter.drawText(screen + QPointF(10, -10), f"{unit.get('name') or unit.get('unit_id', '')}{suffix}")

    def _unit_icon_name(self, unit: dict[str, Any]) -> str | None:
        return unit_icon_name(unit)

    def _draw_display_control_layers(self, painter: QPainter) -> None:
        selected = self._selected_unit()
        if selected is None:
            return
        if self.show_radar_ranges:
            self._draw_detection_range_ring(painter, selected, highlighted=True)
        if self.show_communications_overlay:
            self._draw_communications_overlay(painter, selected)

    def _selected_unit(self) -> dict[str, Any] | None:
        return next(
            (unit for unit in self._state.get("units", []) if unit.get("unit_id") == self.selected_unit_id),
            None,
        )

    def _draw_detection_range_ring(self, painter: QPainter, unit: dict[str, Any], highlighted: bool = False) -> None:
        point = self._point_from_dict(unit.get("position"))
        if point is None:
            return
        range_nm = self._float_unit_value(unit, "detection_range_nm") or self._float_unit_value(unit, "range_nm")
        if range_nm <= 0:
            return
        center = self._screen_from_lonlat(point)
        edge = self._screen_from_lonlat(LonLat(point.lon + self._nm_to_lon_degrees(range_nm, point.lat), point.lat))
        radius = max(8.0, abs(edge.x() - center.x()))
        color = QColor("#145cf2") if unit.get("side") == "blue" else QColor("#dc2626")
        fill = QColor(color)
        fill_alpha = 76 if highlighted else 50
        large_radius_alpha = 28 if highlighted else 12
        fill.setAlpha(large_radius_alpha if radius > max(self.width(), self.height()) * 0.42 else fill_alpha)
        painter.save()
        painter.setBrush(fill)
        ring_color = QColor("#facc15") if highlighted else QColor(color.red(), color.green(), color.blue(), 100)
        painter.setPen(QPen(ring_color, 3.4 if highlighted else 1.5, Qt.SolidLine))
        painter.drawEllipse(center, radius, radius)
        painter.restore()

    def _draw_communications_overlay(self, painter: QPainter, selected: dict[str, Any]) -> None:
        if not bool(selected.get("comms_on", True)):
            return
        selected_point = self._point_from_dict(selected.get("position"))
        if selected_point is None:
            return
        comms_range_nm = self._float_unit_value(selected, "comms_range_nm")
        if comms_range_nm <= 0:
            return
        center = self._screen_from_lonlat(selected_point)
        edge = self._screen_from_lonlat(
            LonLat(selected_point.lon + self._nm_to_lon_degrees(comms_range_nm, selected_point.lat), selected_point.lat)
        )
        radius = max(8.0, abs(edge.x() - center.x()))
        painter.save()
        fill = QColor("#22d3ee")
        fill.setAlpha(10 if radius > max(self.width(), self.height()) * 0.48 else 22)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(34, 211, 238, 190), 2.2, Qt.DashLine))
        painter.drawEllipse(center, radius, radius)
        for unit in self._state.get("units", []):
            if unit.get("unit_id") == selected.get("unit_id") or unit.get("side") != selected.get("side"):
                continue
            if not bool(unit.get("alive", False)) or not bool(unit.get("comms_on", True)):
                continue
            target_point = self._point_from_dict(unit.get("position"))
            if target_point is None or self._distance_nm(selected_point, target_point) > comms_range_nm:
                continue
            painter.setPen(QPen(QColor("#22d3ee"), 2.0, Qt.SolidLine))
            painter.drawLine(center, self._screen_from_lonlat(target_point))
        painter.restore()

    @staticmethod
    def _float_unit_value(unit: dict[str, Any], key: str) -> float:
        try:
            return max(0.0, float(unit.get(key, 0.0) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _nm_to_lon_degrees(radius_nm: float, lat: float) -> float:
        nm_per_degree = max(1.0, 60.0 * abs(math.cos(math.radians(lat))))
        return radius_nm / nm_per_degree

    @staticmethod
    def _distance_nm(a: LonLat, b: LonLat) -> float:
        lat_nm = (a.lat - b.lat) * 60.0
        avg_lat = (a.lat + b.lat) / 2.0
        lon_nm = (a.lon - b.lon) * 60.0 * abs(math.cos(math.radians(avg_lat)))
        return (lat_nm * lat_nm + lon_nm * lon_nm) ** 0.5

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        click = QPointF(event.pos())
        best_unit_id: str | None = None
        best_distance_sq = 24.0 * 24.0
        for unit in self._state.get("units", []):
            point = self._point_from_dict(unit.get("position"))
            if point is None:
                continue
            screen = self._screen_from_lonlat(point)
            dx = screen.x() - click.x()
            dy = screen.y() - click.y()
            distance_sq = dx * dx + dy * dy
            if distance_sq <= best_distance_sq:
                best_distance_sq = distance_sq
                best_unit_id = str(unit.get("unit_id", ""))
        if best_unit_id:
            self.selected_unit_id = best_unit_id
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def _draw_weapons(self, painter: QPainter) -> None:
        for weapon in self._state.get("flying_weapons", []):
            point = self._point_from_dict(weapon.get("position"))
            if point is None:
                continue
            color = QColor("#145cf2") if weapon.get("side") == "blue" else QColor("#dc2626")
            screen = self._screen_from_lonlat(point)
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#ffffff"), 1.4))
            painter.drawPolygon(QPolygonF([screen + QPointF(0, -11), screen + QPointF(7, 7), screen + QPointF(-7, 7)]))

    def _draw_contacts(self, painter: QPainter) -> None:
        for contact in self._state.get("contacts", []):
            point = self._point_from_dict(contact.get("last_known_position"))
            if point is None:
                continue
            screen = self._screen_from_lonlat(point)
            painter.setPen(QPen(QColor("#facc15"), 1.8, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(
                QPolygonF([screen + QPointF(0, -10), screen + QPointF(10, 0), screen + QPointF(0, 10), screen + QPointF(-10, 0)])
            )
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
            painter.drawText(screen + QPointF(12, -8), f"接触 {contact.get('target_id', '')}")

    def _draw_status_text(self, painter: QPainter) -> None:
        units = self._state.get("units", [])
        alive_blue = sum(1 for unit in units if unit.get("side") == "blue" and unit.get("alive"))
        alive_red = sum(1 for unit in units if unit.get("side") == "red" and unit.get("alive"))
        weapons = len(self._state.get("flying_weapons", []))
        painter.fillRect(QRectF(14, 12, 380, 32), QColor(255, 255, 255, 215))
        painter.setPen(QColor("#111827"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        painter.drawText(24, 34, f"地图回放 T+{self._current_time:.1f}s  蓝方 {alive_blue}  红方 {alive_red}  在飞武器 {weapons}")


class ReplayViewerDialog(QDialog):
    SLIDER_SCALE = 10

    def __init__(self, replay, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ReplayViewerDialog")
        self.setWindowTitle("地图回放")
        self.resize(1280, 780)
        self.replay = replay
        self.runtime = ReplayRuntime(replay)
        self.current_time = 0.0
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(100)
        self.time_label = QLabel("时间: 00:00.0 / 00:00.0", self)
        self.timeline = QSlider(Qt.Horizontal, self)
        self.previous_step_button = QPushButton("上一步", self)
        self.play_button = QPushButton("▶", self)
        self.next_step_button = QPushButton("下一步", self)
        self.speed_combo = QComboBox(self)
        self.speed_combo.addItem("1x", 1.0)
        self.speed_combo.addItem("2x", 2.0)
        self.speed_combo.addItem("4x", 4.0)
        self.speed_combo.addItem("8x", 8.0)
        self.speed_combo.addItem("100x", 100.0)
        self.map_canvas = ReplayMapCanvas(self)
        self.key_event_button = QPushButton("关键事件", self.map_canvas)
        self.key_event_button.setObjectName("ReplayKeyEventButton")
        self.key_event_panel = QFrame(self.map_canvas)
        self.key_event_panel.setObjectName("ReplayKeyEventPanel")
        self.key_event_panel.setAttribute(Qt.WA_StyledBackground, True)
        self.key_event_title_label = QLabel("关键事件", self.key_event_panel)
        self.key_event_close_button = QPushButton("X", self.key_event_panel)
        self.key_event_close_button.setObjectName("ReplayKeyEventCloseButton")
        self.key_event_list = QListWidget(self.key_event_panel)
        self.key_event_list.setObjectName("ReplayKeyEventList")
        self.display_control_panel = QFrame(self.map_canvas)
        self.display_control_panel.setObjectName("ReplayDisplayControlPanel")
        self.display_control_panel.setAttribute(Qt.WA_StyledBackground, True)
        self.display_control_label = QLabel("显示控制", self.display_control_panel)
        self.radar_ranges_checkbox = QCheckBox("选中单位雷达范围圈", self.display_control_panel)
        self.radar_ranges_checkbox.setChecked(True)
        self.communications_overlay_checkbox = QCheckBox("显示通信态势共享", self.display_control_panel)
        self.communications_overlay_checkbox.setChecked(True)
        self._build_ui()
        self._bind_events()
        self._load_key_events()
        self.timeline.setRange(0, max(0, int(round(replay.duration_seconds * self.SLIDER_SCALE))))
        self._update_state(0.0)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog#ReplayViewerDialog {
                background: #ededed;
                color: #1f1f1f;
            }
            QLabel {
                color: #1f1f1f;
                font-weight: 800;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #dcdcdc;
                border-radius: 12px;
                color: #2f2f2f;
                font-weight: 900;
                min-width: 84px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background: #f4f4f4;
            }
            QPushButton#ReplayPlayButton {
                background: #07c160;
                border: 1px solid #07c160;
                color: #ffffff;
                min-width: 56px;
            }
            QPushButton#ReplayKeyEventButton {
                background: rgba(255, 255, 255, 238);
                border: 1px solid rgba(156, 163, 175, 190);
                border-radius: 12px;
                color: #111827;
                font-weight: 900;
                min-width: 96px;
                padding: 8px 14px;
            }
            QPushButton#ReplayKeyEventCloseButton {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                color: #111827;
                font-weight: 900;
                min-width: 30px;
                max-width: 30px;
                padding: 4px 0px;
            }
            QComboBox {
                background: #ffffff;
                border: 1px solid #dcdcdc;
                border-radius: 12px;
                color: #2f2f2f;
                font-weight: 800;
                min-width: 76px;
                padding: 7px 12px;
            }
            QFrame#ReplayKeyEventPanel {
                background: rgba(255, 255, 255, 238);
                border: 1px solid rgba(156, 163, 175, 190);
                border-radius: 14px;
            }
            QFrame#ReplayKeyEventPanel QLabel {
                color: #111827;
                font-size: 13px;
                font-weight: 900;
            }
            QListWidget#ReplayKeyEventList {
                background: transparent;
                border: 0px;
                color: #111827;
                font-weight: 800;
                outline: 0;
            }
            QListWidget#ReplayKeyEventList::item {
                border-radius: 8px;
                padding: 7px 8px;
            }
            QListWidget#ReplayKeyEventList::item:selected {
                background: rgba(7, 193, 96, 45);
                color: #064e3b;
            }
            QFrame#ReplayDisplayControlPanel {
                background: rgba(255, 255, 255, 235);
                border: 1px solid rgba(156, 163, 175, 190);
                border-radius: 14px;
            }
            QFrame#ReplayDisplayControlPanel QLabel {
                color: #111827;
                font-size: 13px;
                font-weight: 900;
            }
            QFrame#ReplayDisplayControlPanel QCheckBox {
                color: #111827;
                font-weight: 800;
                spacing: 5px;
            }
            QCheckBox {
                color: #1f1f1f;
                font-weight: 800;
                spacing: 4px;
            }
            QSlider::groove:horizontal {
                background: #d7dde7;
                border-radius: 4px;
                height: 8px;
            }
            QSlider::handle:horizontal {
                background: #07c160;
                border-radius: 8px;
                margin: -5px 0px;
                width: 16px;
            }
            """
        )
        self.play_button.setObjectName("ReplayPlayButton")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        controls = QHBoxLayout()
        controls.addWidget(self.time_label)
        controls.addWidget(self.timeline, 1)
        controls.addWidget(self.previous_step_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_step_button)
        controls.addWidget(self.speed_combo)
        layout.addLayout(controls)
        layout.addWidget(self.map_canvas, 1)
        key_header_layout = QHBoxLayout()
        key_header_layout.setContentsMargins(0, 0, 0, 0)
        key_header_layout.addWidget(self.key_event_title_label)
        key_header_layout.addStretch(1)
        key_header_layout.addWidget(self.key_event_close_button)
        key_panel_layout = QVBoxLayout(self.key_event_panel)
        key_panel_layout.setContentsMargins(12, 10, 12, 12)
        key_panel_layout.setSpacing(8)
        key_panel_layout.addLayout(key_header_layout)
        key_panel_layout.addWidget(self.key_event_list)
        self.key_event_panel.resize(260, 210)
        panel_layout = QVBoxLayout(self.display_control_panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(6)
        panel_layout.addWidget(self.display_control_label)
        panel_layout.addWidget(self.radar_ranges_checkbox)
        panel_layout.addWidget(self.communications_overlay_checkbox)
        self.display_control_panel.adjustSize()
        self.map_canvas.installEventFilter(self)
        self._position_key_event_widgets()
        self._position_display_control_panel()

    def _bind_events(self) -> None:
        self.timeline.valueChanged.connect(lambda value: self._update_state(value / self.SLIDER_SCALE))
        self.play_button.clicked.connect(self._toggle_playback)
        self.previous_step_button.clicked.connect(lambda: self._step(-1.0))
        self.next_step_button.clicked.connect(lambda: self._step(1.0))
        self.key_event_button.clicked.connect(self._show_key_event_panel)
        self.key_event_close_button.clicked.connect(self.key_event_panel.hide)
        self.key_event_list.currentItemChanged.connect(lambda current, previous: self._jump_to_key_event_item(current))
        self.radar_ranges_checkbox.toggled.connect(self.map_canvas.set_radar_ranges_visible)
        self.communications_overlay_checkbox.toggled.connect(self.map_canvas.set_communications_overlay_visible)
        self._play_timer.timeout.connect(self._advance_playback)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.map_canvas and event.type() in {QEvent.Resize, QEvent.Show}:
            self._position_key_event_widgets()
            self._position_display_control_panel()
        return super().eventFilter(watched, event)

    def _position_key_event_widgets(self) -> None:
        self.key_event_button.adjustSize()
        self.key_event_button.move(16, REPLAY_STATUS_OVERLAY_HEIGHT)
        self.key_event_panel.move(16, self.key_event_button.y() + self.key_event_button.height() + 10)
        self.key_event_button.raise_()
        self.key_event_panel.raise_()

    def _position_display_control_panel(self) -> None:
        self.display_control_panel.adjustSize()
        x = max(16, self.map_canvas.width() - self.display_control_panel.width() - 18)
        self.display_control_panel.move(x, 18)
        self.display_control_panel.raise_()

    def _show_key_event_panel(self) -> None:
        self.key_event_panel.show()
        self.key_event_panel.raise_()

    def _load_key_events(self) -> None:
        self.key_event_list.blockSignals(True)
        self.key_event_list.clear()
        for event in self.replay.event_stream:
            label = event_type_label(event.event_type)
            item = QListWidgetItem(f"{event.time:06.1f}s | {label}")
            item.setData(Qt.UserRole, float(event.time))
            self.key_event_list.addItem(item)
        self.key_event_list.blockSignals(False)

    def _toggle_playback(self) -> None:
        if self._play_timer.isActive():
            self._pause_playback()
            return
        self._start_playback()

    def _start_playback(self) -> None:
        if self.current_time >= float(self.replay.duration_seconds):
            self._update_state(0.0)
        self.play_button.setText("⏸")
        self._play_timer.start()

    def _pause_playback(self) -> None:
        self._play_timer.stop()
        self.play_button.setText("▶")

    def _step(self, seconds: float) -> None:
        self._pause_playback()
        self._update_state(self.current_time + seconds)

    def _jump_to_key_event_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        target_time = item.data(Qt.UserRole)
        if target_time is None:
            return
        self._pause_playback()
        self._update_state(float(target_time))

    def _advance_playback(self) -> None:
        speed = float(self.speed_combo.currentData() or 1.0)
        next_time = self.current_time + self._play_timer.interval() / 1000.0 * speed
        if next_time >= float(self.replay.duration_seconds):
            next_time = float(self.replay.duration_seconds)
            self._pause_playback()
        self._update_state(next_time)

    def _update_state(self, target_time: float) -> None:
        duration = float(self.replay.duration_seconds)
        self.current_time = max(0.0, min(duration, float(target_time)))
        state = self.runtime.seek(self.current_time)
        self.time_label.setText(f"时间: {format_replay_time(self.current_time)} / {format_replay_time(duration)}")
        slider_value = int(round(self.current_time * self.SLIDER_SCALE))
        if self.timeline.value() != slider_value:
            self.timeline.blockSignals(True)
            self.timeline.setValue(slider_value)
            self.timeline.blockSignals(False)
        self.map_canvas.set_state(state)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._play_timer.stop()
        super().closeEvent(event)


def format_replay_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minute = int(seconds) // 60
    second = seconds - minute * 60
    return f"{minute:02d}:{second:04.1f}"


def event_type_label(event_type: str) -> str:
    return EVENT_TYPE_LABELS.get(event_type, event_type or "事件")
