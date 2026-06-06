"""qt_frontend_v6 的单位运动逻辑。

MapCanvas 负责画图，但不直接计算单位怎么动。
地图每一帧都会来这里询问“某个单位在当前仿真时间应该在哪个经纬度”。

routes.json 只保存路线控制点，不保存大量密集点。
这里根据控制点做插值，得到单位当前的位置。
"""

from __future__ import annotations

from qt_frontend_v6.core.geo import LonLat, interpolate_route
from qt_frontend_v6.core.layers import RouteLayerItem
from qt_frontend_v6.core.scenario import CombatUnit, UnitRoute


class MotionController:
    """单位运动控制器：根据路线和仿真时间计算单位位置。"""

    def __init__(self, routes: dict[str, RouteLayerItem]) -> None:
        self.routes = routes

    def set_routes(self, routes: dict[str, RouteLayerItem]) -> None:
        """更新路线表；当 routes.json 重新读取后会调用这个函数。"""
        self.routes = routes

    def route_for_unit(self, unit: CombatUnit) -> UnitRoute:
        """获取单位使用的路线；优先使用 routes.json 里的 route_id。"""
        route = self.routes.get(unit.route_id)
        if route and route.points:
            return UnitRoute(route.points)
        return unit.route

    def position_for(self, unit: CombatUnit, simulation_seconds: float) -> LonLat:
        """根据单位 motion 类型，计算单位在当前仿真时间的位置。"""
        motion = unit.motion or ("stationary" if unit.position is not None else "route_loop")
        if motion == "stationary":
            return self._stationary_position(unit)
        if motion == "route_once":
            return self._route_once_position(unit, simulation_seconds)
        if motion == "route_pingpong":
            return self._route_pingpong_position(unit, simulation_seconds)
        return self._route_loop_position(unit, simulation_seconds)

    def _stationary_position(self, unit: CombatUnit) -> LonLat:
        """静止单位的位置：优先用 position，没有 position 就用路线第一个点。"""
        if unit.position is not None:
            return unit.position
        route = self.route_for_unit(unit)
        return route.points[0] if route.points else LonLat(0.0, 0.0)

    def _route_loop_position(self, unit: CombatUnit, simulation_seconds: float) -> LonLat:
        """循环运动：走到路线末尾后回到起点继续走。"""
        route = self.route_for_unit(unit)
        return interpolate_route(route.points, self._route_progress(unit, simulation_seconds))

    def _route_once_position(self, unit: CombatUnit, simulation_seconds: float) -> LonLat:
        """单次运动：从起点走到终点，然后停在终点。"""
        route = self.route_for_unit(unit)
        progress = self._route_progress(unit, simulation_seconds)
        if progress >= 1.0 and route.points:
            return route.points[-1]
        return self._interpolate_clamped(route.points, progress)

    def _route_pingpong_position(self, unit: CombatUnit, simulation_seconds: float) -> LonLat:
        """往返运动：先从起点到终点，再沿原路线反向返回。"""
        route = self.route_for_unit(unit)
        raw_progress = self._route_progress(unit, simulation_seconds) % 2.0
        progress = raw_progress if raw_progress <= 1.0 else 2.0 - raw_progress
        return self._interpolate_clamped(route.points, progress)

    @staticmethod
    def _route_progress(unit: CombatUnit, simulation_seconds: float) -> float:
        """把仿真时间和单位速度换算成路线进度。"""
        # 当前 speed 还是场景里的倍率，不是真实节/米每秒。
        return simulation_seconds * max(0.0, unit.speed) / 80.0

    @staticmethod
    def _interpolate_clamped(points: list[LonLat], progress: float) -> LonLat:
        """在路线控制点之间插值，并把进度限制在 0 到 1 之间。"""
        if not points:
            return LonLat(0.0, 0.0)
        if len(points) == 1 or progress <= 0.0:
            return points[0]
        if progress >= 1.0:
            return points[-1]

        segment_count = len(points) - 1
        raw_index = progress * segment_count
        index = min(int(raw_index), segment_count - 1)
        local_t = raw_index - index
        start = points[index]
        end = points[index + 1]
        return LonLat(
            start.lon + (end.lon - start.lon) * local_t,
            start.lat + (end.lat - start.lat) * local_t,
        )
