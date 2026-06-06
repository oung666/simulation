"""qt_frontend_v6 的纯 Qt 地图绘制核心。

这个文件负责“地图上画什么、怎么画、按什么顺序画”。
v6 不使用 WebEngine / HTML 前端，离线瓦片、红蓝航线、单位图标、范围圈、
海陆图层都在这里通过 QPainter 直接绘制。

主要输入数据：
- MapDocument：离线地图元信息、瓦片目录、地图边界、海陆多边形。
- Scenario：战斗单元、机场、雷达等场景数据。
- LayerDocument：从 data/layers/routes.json 读取的路线图层数据。
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QByteArray, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QWidget

from qt_frontend_v6.core.geo import LonLat, ScreenPoint, lonlat_to_world, world_to_lonlat
from qt_frontend_v6.core.layers import LayerDocument, RouteLayerItem, route_lookup
from qt_frontend_v6.core.map_document import MapDocument, MapFeature
from qt_frontend_v6.core.scenario import CombatUnit, Scenario, UnitRoute
from qt_frontend_v6.controllers.motion import MotionController
from qt_frontend_v6.controllers.tile_store import TileStore


DEFAULT_ZOOM = 7.0


class MapCanvas(QWidget):
    """地图画布控件。

    这个类既负责绘制，也负责地图交互状态，例如中心点、缩放级别、鼠标拖动。
    单位运动计算不直接写在这里，而是交给 MotionController，避免绘制代码和仿真逻辑混在一起。
    """

    coordinateHovered = pyqtSignal(float, float)
    timeChanged = pyqtSignal(float)
    mapRightClicked = pyqtSignal(float, float)

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
        self.tile_store = TileStore(map_document.tile_root)
        self.center = map_document.center
        self.zoom = DEFAULT_ZOOM
        self.playing = True
        self.speed_multiplier = 1.0
        self.simulation_seconds = 0.0
        self.route_drafts: dict[str, dict[str, object]] = {}
        self._svg_cache: dict[tuple[str, str], QSvgRenderer] = {}
        self._last_mouse_pos: QPoint | None = None
        self._last_tile_paint_rect: QRectF | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._constrain_center()

    def reset_view(self) -> None:
        """复位地图视角到 offline_map.json 里配置的中心点和默认缩放。"""
        self.center = self.map_document.center
        self.zoom = DEFAULT_ZOOM
        self._constrain_center()
        self.update()

    def zoom_in(self) -> None:
        """放大地图一级，同时限制不超过地图允许的最大 zoom。"""
        self.zoom = min(self.map_document.max_zoom, self.zoom + 0.5)
        self._constrain_center()
        self.update()

    def zoom_out(self) -> None:
        """缩小地图一级，同时限制不低于地图允许的最小 zoom。"""
        self.zoom = max(self.map_document.min_zoom, self.zoom - 0.5)
        self._constrain_center()
        self.update()

    def set_scenario(self, scenario: Scenario) -> None:
        """替换当前场景数据，并把仿真时间重新归零。"""
        self.scenario = scenario
        self.simulation_seconds = 0.0
        self.update()

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

    def set_playing(self, playing: bool) -> None:
        """设置仿真是否播放；暂停后单位位置不再随时间更新。"""
        self.playing = playing

    def set_speed_multiplier(self, value: float) -> None:
        """设置仿真倍率，例如 1.5x、2x、10x。"""
        self.speed_multiplier = max(0.1, value)

    def _tick(self) -> None:
        """定时器回调：推进仿真时间，并触发地图重绘。"""
        if self.playing:
            self.simulation_seconds += 0.033 * self.speed_multiplier
            self.timeChanged.emit(self.simulation_seconds)
            self.update()

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

    def _constrain_center(self) -> None:
        """限制地图中心点不要拖出 offline_map.json 配置的 bounds 范围。"""
        min_lon, min_lat, max_lon, max_lat = self.map_document.bounds
        north_west = lonlat_to_world(LonLat(min_lon, max_lat), self.zoom)
        south_east = lonlat_to_world(LonLat(max_lon, min_lat), self.zoom)
        center_world = lonlat_to_world(self.center, self.zoom)

        half_width = max(1.0, self.width() / 2.0)
        half_height = max(1.0, self.height() / 2.0)
        min_x = north_west.x + half_width
        max_x = south_east.x - half_width
        min_y = north_west.y + half_height
        max_y = south_east.y - half_height

        if min_x > max_x:
            clamped_x = (north_west.x + south_east.x) / 2.0
        else:
            clamped_x = min(max(center_world.x, min_x), max_x)

        if min_y > max_y:
            clamped_y = (north_west.y + south_east.y) / 2.0
        else:
            clamped_y = min(max(center_world.y, min_y), max_y)

        self.center = world_to_lonlat(ScreenPoint(clamped_x, clamped_y), self.zoom)

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
        # 3. 战术图层：范围圈、路线、临时路线、单位
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
        self._draw_range_layer(painter)
        self._draw_route_layer(painter)
        self._draw_route_drafts(painter)
        self._draw_unit_layer(painter)
        self._draw_overlay(painter)

    def _draw_tiles(self, painter: QPainter) -> bool:
        """绘制离线瓦片；返回 True 表示当前视角至少画出了一张瓦片。"""
        tile_zoom = self.tile_store.best_zoom_for(self.zoom)
        if tile_zoom is None:
            return False
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
        if drawn:
            self._last_tile_paint_rect = drawn_rect.intersected(QRectF(self.rect())) if drawn_rect else None
            painter.fillRect(self.rect(), QColor(255, 255, 255, 12))
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
        for route in self.layer_document.routes:
            if not route.visible or len(route.points) < 2:
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
        """绘制单位探测/影响范围圈，半径来自场景 JSON 的 range_nm。"""
        for unit in self.scenario.units:
            if unit.range_nm <= 0:
                continue
            position = self.motion_controller.position_for(unit, self.simulation_seconds)
            screen = self._screen_from_lonlat(position)
            edge = self._screen_from_lonlat(LonLat(position.lon + self._nm_to_lon_degrees(unit.range_nm, position.lat), position.lat))
            radius = abs(edge.x() - screen.x())
            color = QColor("#145cf2") if unit.side == "blue" else QColor("#dc2626")
            fill = QColor(color)
            fill.setAlpha(0 if radius > max(self.width(), self.height()) * 0.42 else 50)
            painter.setBrush(fill)
            ring_pen = QPen(color, 1.5, Qt.SolidLine)
            ring_pen.setColor(QColor(color.red(), color.green(), color.blue(), 100))
            painter.setPen(ring_pen)
            painter.drawEllipse(screen, radius, radius)

    @staticmethod
    def _nm_to_lon_degrees(radius_nm: float, lat: float) -> float:
        """把海里半径粗略换算成经度跨度，用于在屏幕上画范围圈。"""
        import math

        nm_per_degree = max(1.0, 60.0 * math.cos(math.radians(lat)))
        return radius_nm / nm_per_degree

    def _draw_route_drafts(self, painter: QPainter) -> None:
        """绘制右键设置路线时的临时起点、途经点、终点。"""
        for side, draft in self.route_drafts.items():
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
        for unit in self.scenario.units:
            route = self._route_for_unit(unit)
            position = self.motion_controller.position_for(unit, self.simulation_seconds)
            screen = self._screen_from_lonlat(position)
            color = QColor("#145cf2") if unit.side == "blue" else QColor("#dc2626")
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            self._draw_unit_symbol(painter, unit, screen, color)
            if self.zoom >= 7.4:
                painter.setPen(QColor("#111827"))
                painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
                painter.drawText(screen + QPointF(10, -10), unit.name)

    def _draw_unit_symbol(self, painter: QPainter, unit: CombatUnit, screen: QPointF, color: QColor) -> None:
        """根据单位类型绘制对应图标；优先使用 assets/svg 下的 SVG。"""
        icon_name = {
            "aircraft": "flight_black_24dp.svg",
            "ship": "directions_boat_black_24dp.svg",
            "facility": "radar_black_24dp.svg",
            "airbase": "flight_takeoff_black_24dp.svg",
        }.get(unit.unit_type)
        if icon_name:
            self._draw_svg_unit_icon(painter, icon_name, screen, color)
            return

        if unit.unit_type == "ship":
            points = QPolygonF(
                [
                    QPointF(screen.x(), screen.y() - 10),
                    QPointF(screen.x() + 9, screen.y() + 4),
                    QPointF(screen.x() + 4, screen.y() + 10),
                    QPointF(screen.x() - 4, screen.y() + 10),
                    QPointF(screen.x() - 9, screen.y() + 4),
                ]
            )
            painter.drawPolygon(points)
            return
        if unit.unit_type == "facility":
            painter.drawRect(int(screen.x() - 8), int(screen.y() - 8), 16, 16)
            painter.drawLine(screen + QPointF(-11, 0), screen + QPointF(11, 0))
            painter.drawLine(screen + QPointF(0, -11), screen + QPointF(0, 11))
            return
        if unit.unit_type == "airbase":
            painter.drawRect(int(screen.x() - 9), int(screen.y() - 6), 18, 12)
            painter.drawLine(screen + QPointF(-12, 0), screen + QPointF(12, 0))
            return
        points = QPolygonF(
            [
                QPointF(screen.x(), screen.y() - 12),
                QPointF(screen.x() + 5, screen.y() + 6),
                QPointF(screen.x(), screen.y() + 3),
                QPointF(screen.x() - 5, screen.y() + 6),
            ]
        )
        painter.drawPolygon(points)

    def _draw_svg_unit_icon(self, painter: QPainter, icon_name: str, screen: QPointF, color: QColor) -> None:
        """绘制 SVG 单位图标，并加白色光圈，避免图标淹没在底图里。"""
        renderer = self._svg_renderer(icon_name, color)
        if renderer is None:
            return

        size = 28.0
        halo_size = size + 8.0
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 230), 2.2))
        painter.setBrush(QColor(255, 255, 255, 190))
        painter.drawEllipse(screen, halo_size / 2.0, halo_size / 2.0)
        renderer.render(
            painter,
            QRectF(screen.x() - size / 2.0, screen.y() - size / 2.0, size, size),
        )
        painter.restore()

    def _svg_renderer(self, icon_name: str, color: QColor) -> QSvgRenderer | None:
        """读取 SVG 文件，把白色替换成红/蓝阵营色，并缓存渲染器。"""
        color_name = color.name()
        key = (icon_name, color_name)
        if key in self._svg_cache:
            return self._svg_cache[key]

        icon_path = Path(__file__).resolve().parents[1] / "assets" / "svg" / icon_name
        if not icon_path.exists():
            return None
        svg_text = icon_path.read_text(encoding="utf-8").replace("#ffffff", color_name)
        renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        if not renderer.isValid():
            return None
        self._svg_cache[key] = renderer
        return renderer

    def _draw_overlay(self, painter: QPainter) -> None:
        """绘制左上角地图状态文字，例如当前 zoom 和瓦片来源。"""
        painter.setPen(QColor("#1f2937"))
        painter.setFont(QFont("Microsoft YaHei UI", 10))
        best_zoom = self.tile_store.best_zoom_for(self.zoom)
        source = f"offline tiles z{best_zoom}" if best_zoom is not None else "fallback vector"
        painter.drawText(16, 28, f"{self.map_document.name}  zoom={self.zoom:.1f}  {source}")

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """鼠标移动：更新经纬度显示；按住左键时拖动地图。"""
        lonlat = self._lonlat_from_screen(event.localPos())
        self.coordinateHovered.emit(lonlat.lon, lonlat.lat)
        if self._last_mouse_pos is not None and event.buttons() & Qt.LeftButton:
            old_lonlat = self._lonlat_from_screen(QPointF(self._last_mouse_pos))
            new_lonlat = self._lonlat_from_screen(event.localPos())
            self.center = LonLat(
                self.center.lon + old_lonlat.lon - new_lonlat.lon,
                self.center.lat + old_lonlat.lat - new_lonlat.lat,
            )
            self._constrain_center()
            self.update()
        self._last_mouse_pos = event.pos()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """鼠标按下：右键用于设置路线点，左键用于准备拖动地图。"""
        if event.button() == Qt.RightButton:
            lonlat = self._lonlat_from_screen(QPointF(event.pos()))
            self.mapRightClicked.emit(lonlat.lon, lonlat.lat)
            return
        self._last_mouse_pos = event.pos()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """鼠标松开：结束地图拖动状态。"""
        self._last_mouse_pos = None

    def wheelEvent(self, event) -> None:  # noqa: N802
        """滚轮缩放地图，并尽量保持鼠标指向的经纬度不变。"""
        event_position = self._event_position(event)
        before = self._lonlat_from_screen(event_position)
        delta = event.angleDelta().y()
        self.zoom = max(self.map_document.min_zoom, min(self.map_document.max_zoom, self.zoom + (0.35 if delta > 0 else -0.35)))
        after = self._lonlat_from_screen(event_position)
        self.center = LonLat(
            self.center.lon + before.lon - after.lon,
            self.center.lat + before.lat - after.lat,
        )
        self._constrain_center()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """窗口大小变化后重新约束地图中心点，防止视角越界。"""
        self._constrain_center()
        super().resizeEvent(event)
