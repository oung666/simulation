"""simulation 的海陆判定和部署规则检查。

地图绘制只负责“看起来在哪里”，这个文件负责“规则上能不能在那里”。
比如：舰艇不能在陆地上，也不能太贴近陆地；雷达、机场这类地面单位必须在陆地上。

当前做法是轻量级方案：从 offline_map.json 读取 land 多边形，
用点在多边形内判断陆地/海洋，用点到多边形边界的距离判断舰艇是否太靠岸。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from simulation.core.geo import LonLat
from simulation.core.map_document import MapDocument
from simulation.core.scenario import CombatUnit


SHIP_LAND_BUFFER_DEGREES = 0.20


@dataclass(frozen=True)
class TerrainCheck:
    ok: bool
    message: str = ""


class TerrainClassifier:
    """海陆分类器：根据地图里的 land 多边形判断一个点属于陆地还是海洋。"""

    def __init__(self, map_document: MapDocument) -> None:
        self.land_polygons = self._polygons_by_style(map_document, "land")

    def terrain_at(self, point: LonLat) -> str:
        """判断一个经纬度点属于陆地还是海洋，返回 "land" 或 "sea"。"""
        if self._in_any_polygon(point, self.land_polygons):
            return "land"
        return "sea"

    def is_land(self, point: LonLat) -> bool:
        """判断某个点是否在陆地上。"""
        return self.terrain_at(point) == "land"

    def is_near_land(self, point: LonLat, buffer_degrees: float = SHIP_LAND_BUFFER_DEGREES) -> bool:
        """判断某个点是否在陆地上或距离陆地太近，主要给舰艇避陆使用。"""
        if self.is_land(point):
            return True
        return self._distance_to_land_degrees(point) < buffer_degrees

    def validate_route_for_unit(self, unit: CombatUnit, points: list[LonLat]) -> TerrainCheck:
        """检查某个单位的路线是否合法。

        目前重点检查舰艇：不仅检查控制点，还会沿每一段路线采样。
        这样可以避免“两个端点在海上，但中间直线穿过陆地”的问题。
        """
        if unit.unit_type == "ship":
            for index, point in enumerate(self._route_sample_points(points), 1):
                if self.is_land(point):
                    return TerrainCheck(False, f"{unit.name} 是舰艇，航线采样点 {index} 在陆地上。")
                if self.is_near_land(point):
                    return TerrainCheck(False, f"{unit.name} 是舰艇，航线采样点 {index} 过于贴近陆地。")
        if unit.unit_type == "ground_vehicle":
            for index, point in enumerate(self._route_sample_points(points), 1):
                if not self.is_land(point):
                    return TerrainCheck(False, f"{unit.name} 是地面车辆，路线采样点 {index} 不在陆地上。")
        return TerrainCheck(True)

    def validate_deployment_for_unit(self, unit: CombatUnit) -> TerrainCheck:
        """检查静态部署是否合法，例如机场/雷达必须部署在陆地上。"""
        if unit.position is None:
            return TerrainCheck(True)
        terrain = self.terrain_at(unit.position)
        if unit.unit_type in {"facility", "airbase", "ground_vehicle"} and terrain != "land":
            return TerrainCheck(False, f"{unit.name} 是地面部署单位，当前位置不在陆地上。")
        if unit.unit_type == "ship" and terrain == "land":
            return TerrainCheck(False, f"{unit.name} 是舰艇，当前位置不能在陆地上。")
        return TerrainCheck(True)

    def _distance_to_land_degrees(self, point: LonLat) -> float:
        """计算某个点到最近陆地边界的大致距离，单位是经纬度度数。"""
        if not self.land_polygons:
            return math.inf
        min_distance = math.inf
        for polygon in self.land_polygons:
            for start, end in zip(polygon, polygon[1:] + polygon[:1]):
                min_distance = min(min_distance, self._distance_to_segment(point, start, end))
        return min_distance

    @staticmethod
    def _route_sample_points(points: list[LonLat]) -> list[LonLat]:
        """沿路线每一段生成采样点，用于发现路线中间是否穿陆或贴陆。"""
        if len(points) < 2:
            return points
        samples: list[LonLat] = []
        for start, end in zip(points, points[1:]):
            for step in range(21):
                t = step / 20.0
                samples.append(
                    LonLat(
                        start.lon + (end.lon - start.lon) * t,
                        start.lat + (end.lat - start.lat) * t,
                    )
                )
        return samples

    @staticmethod
    def _distance_to_segment(point: LonLat, start: LonLat, end: LonLat) -> float:
        """计算一个点到一条线段的最短距离。"""
        px, py = point.lon, point.lat
        ax, ay = start.lon, start.lat
        bx, by = end.lon, end.lat
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        closest_x = ax + t * dx
        closest_y = ay + t * dy
        return math.hypot(px - closest_x, py - closest_y)

    @staticmethod
    def _polygons_by_style(map_document: MapDocument, style: str) -> list[list[LonLat]]:
        """从地图文档里取出指定 style 的多边形，例如所有 land 多边形。"""
        return [
            feature.coordinates
            for feature in map_document.features
            if feature.kind == "polygon" and feature.style == style and len(feature.coordinates) >= 3
        ]

    @classmethod
    def _in_any_polygon(cls, point: LonLat, polygons: list[list[LonLat]]) -> bool:
        """判断某个点是否落在任意一个多边形内部。"""
        return any(cls._point_in_polygon(point, polygon) for polygon in polygons)

    @staticmethod
    def _point_in_polygon(point: LonLat, polygon: list[LonLat]) -> bool:
        """射线法判断点是否在一个多边形内部。"""
        inside = False
        j = len(polygon) - 1
        for i, current in enumerate(polygon):
            previous = polygon[j]
            intersects = (current.lat > point.lat) != (previous.lat > point.lat)
            if intersects:
                lon_at_lat = (previous.lon - current.lon) * (point.lat - current.lat) / (
                    previous.lat - current.lat
                ) + current.lon
                if point.lon < lon_at_lat:
                    inside = not inside
            j = i
        return inside
