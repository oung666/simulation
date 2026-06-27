"""simulation 的单位运动逻辑。

MapCanvas 负责画图，但不直接计算单位怎么动。
这里采用 Panopticon 风格的物理速度模型：单位 speed 统一表示节
（knots，海里/小时），每个仿真秒沿航线推进 speed / 3600 海里。
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation.core.geo import LonLat
from simulation.core.geo_utils import bearing_between, haversine_distance_km, km_to_nm, next_position
from simulation.core.layers import RouteLayerItem
from simulation.core.scenario import CombatUnit, UnitRoute


@dataclass
class UnitMotionState:
    current_position: LonLat
    current_waypoint_index: int
    direction: int
    initialized: bool = False


class MotionController:
    """单位运动控制器：按物理速度沿航线逐秒推进单位位置。"""

    def __init__(self, routes: dict[str, RouteLayerItem]) -> None:
        self.routes = routes
        self._states: dict[str, UnitMotionState] = {}

    def set_routes(self, routes: dict[str, RouteLayerItem]) -> None:
        """更新路线表；当 routes.json 重新读取后会调用这个函数。"""
        self.routes = routes
        self.reset()

    def reset(self) -> None:
        """清空运动状态，下次读取单位位置时按当前场景重新初始化。"""
        self._states.clear()

    def route_for_unit(self, unit: CombatUnit) -> UnitRoute:
        """获取单位使用的路线；优先使用 routes.json 里的 route_id。"""
        if (unit.motion or "").lower() == "dynamic":
            return unit.route
        route = self.routes.get(unit.route_id)
        if route and route.points:
            return UnitRoute(route.points)
        return unit.route

    def position_for(self, unit: CombatUnit, simulation_seconds: float | None = None) -> LonLat:
        """返回单位当前物理位置；simulation_seconds 参数保留为兼容旧调用。"""
        return self._state_for(unit).current_position

    def advance(self, unit: CombatUnit, dt_seconds: float = 1.0) -> LonLat:
        """将单位按物理速度推进 dt_seconds 秒，返回新位置。"""
        state = self._state_for(unit)
        motion = unit.motion or ("stationary" if unit.position is not None else "route_loop")
        if motion == "stationary" or unit.speed <= 0.0:
            unit.position = state.current_position
            return state.current_position

        if motion == "dynamic":
            return self._advance_dynamic(unit, state, dt_seconds)

        route = self.route_for_unit(unit)
        if len(route.points) < 2:
            unit.position = state.current_position
            return state.current_position

        remaining = max(0.0, dt_seconds)
        while remaining > 0.0:
            target = route.points[state.current_waypoint_index]
            distance_nm = km_to_nm(
                haversine_distance_km(
                    state.current_position.lat,
                    state.current_position.lon,
                    target.lat,
                    target.lon,
                )
            )
            if distance_nm <= 0.0001:
                if not self._advance_waypoint(state, route, motion):
                    break
                continue

            step_seconds = min(remaining, 1.0)
            step_nm = unit.speed * step_seconds / 3600.0
            if step_nm >= distance_nm:
                state.current_position = target
                remaining -= distance_nm / max(unit.speed / 3600.0, 1e-9)
                if not self._advance_waypoint(state, route, motion):
                    break
                continue

            next_lat, next_lon = next_position(
                state.current_position.lat,
                state.current_position.lon,
                target.lat,
                target.lon,
                unit.speed * step_seconds,
            )
            state.current_position = LonLat(next_lon, next_lat)
            remaining -= step_seconds

        target = route.points[state.current_waypoint_index]
        unit.heading = bearing_between(
            state.current_position.lat,
            state.current_position.lon,
            target.lat,
            target.lon,
        )
        unit.position = state.current_position
        return state.current_position

    def _state_for(self, unit: CombatUnit) -> UnitMotionState:
        state = self._states.get(unit.unit_id)
        if state is not None:
            return state

        route = self.route_for_unit(unit)
        start = unit.position or (route.points[0] if route.points else LonLat(0.0, 0.0))
        motion = unit.motion or ("stationary" if unit.position is not None else "route_loop")
        target_index = 0
        if motion != "stationary" and len(route.points) > 1:
            target_index = 1
        state = UnitMotionState(
            current_position=start,
            current_waypoint_index=target_index,
            direction=1,
            initialized=True,
        )
        self._states[unit.unit_id] = state
        unit.position = start
        return state

    def _advance_dynamic(self, unit: CombatUnit, state: UnitMotionState, dt_seconds: float) -> LonLat:
        route = unit.route
        remaining = max(0.0, dt_seconds)
        while remaining > 0.0 and route.points:
            target = route.points[0]
            distance_km = haversine_distance_km(
                state.current_position.lat,
                state.current_position.lon,
                target.lat,
                target.lon,
            )
            if distance_km < 0.5:
                state.current_position = target
                route.points.pop(0)
                continue

            step_seconds = min(remaining, 1.0)
            distance_nm = km_to_nm(distance_km)
            step_nm = unit.speed * step_seconds / 3600.0
            if step_nm >= distance_nm:
                state.current_position = target
                route.points.pop(0)
                remaining -= distance_nm / max(unit.speed / 3600.0, 1e-9)
                continue

            unit.heading = bearing_between(
                state.current_position.lat,
                state.current_position.lon,
                target.lat,
                target.lon,
            )
            next_lat, next_lon = next_position(
                state.current_position.lat,
                state.current_position.lon,
                target.lat,
                target.lon,
                unit.speed * step_seconds,
            )
            state.current_position = LonLat(next_lon, next_lat)
            remaining -= step_seconds

        unit.position = state.current_position
        return state.current_position

    def _advance_waypoint(self, state: UnitMotionState, route: UnitRoute, motion: str) -> bool:
        last_index = len(route.points) - 1
        if motion == "route_once":
            if state.current_waypoint_index >= last_index:
                state.current_waypoint_index = last_index
                return False
            state.current_waypoint_index += 1
            return True

        if motion == "route_pingpong":
            if state.current_waypoint_index >= last_index:
                state.direction = -1
                state.current_waypoint_index = max(0, last_index - 1)
                return state.current_waypoint_index != last_index
            if state.current_waypoint_index <= 0:
                state.direction = 1
                state.current_waypoint_index = 1 if last_index >= 1 else 0
                return state.current_waypoint_index != 0
            state.current_waypoint_index += state.direction
            return True

        state.current_waypoint_index = (state.current_waypoint_index + 1) % len(route.points)
        return True
