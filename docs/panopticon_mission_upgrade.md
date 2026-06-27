# Panopticon 风格任务系统升级说明

本次升级按照 `implementation_plan.md`，把原来主要依赖固定航线的仿真方式，扩展为任务驱动的动态航路方式。核心行为是：任务逻辑实时改写 `CombatUnit.route.points`，运动控制器按 `dynamic` 模式消费这些航点。

## 修改的代码

### `core/mission.py`

新增任务数据模型：

- `ReferencePoint`：巡逻区参考点。
- `Mission`：任务基类。
- `PatrolMission`：巡逻任务，包含随机生成巡逻区内航点、判断点是否在巡逻区内。
- `StrikeMission`：打击任务，保存攻击单元和目标单元。

### `core/scenario.py`

扩展场景加载：

- `Scenario` 增加 `reference_points` 和 `missions`。
- `load_scenario()` 支持解析 JSON 根部的 `reference_points` / `referencePoints` 和 `missions`。
- 支持 `patrol` 与 `strike` 两类任务配置。

### `core/geo_utils.py`

新增任务需要的地理函数：

- `get_terminal_coordinates_from_distance_and_bearing()`：按起点、距离、方位角推算终点。
- `point_in_polygon()`：判断点是否在多边形内。
- `generate_random_coordinates_within_polygon()`：在巡逻区内生成随机航点。

### `controllers/motion.py`

新增 `dynamic` 运动模式：

- `unit.motion == "dynamic"` 时优先使用 `unit.route.points`，不再读取静态 `route_id`。
- 飞向 `unit.route.points[0]`。
- 距离航点小于 `0.5 km` 后 `pop(0)` 消费航点。
- 原有 `route_loop`、`route_once`、`route_pingpong` 保持兼容。

### `controllers/combat_controller.py`

新增任务管理 API：

- `add_reference_point(name, lat, lon)`
- `remove_reference_point(reference_id)`
- `move_aircraft(aircraft_id, new_coordinates)`
- `move_ship(ship_id, new_coordinates)`
- `create_patrol_mission(name, assigned_units, assigned_area)`
- `update_patrol_mission(...)`
- `create_strike_mission(name, assigned_units, assigned_targets)`
- `update_strike_mission(...)`
- `delete_mission(mission_id)`
- `clear_completed_strike_missions()`

新增任务 tick 行为：

- 巡逻任务：为空路线或航点离开巡逻区时，自动生成巡逻区内随机航点并设为 `dynamic`。
- 打击任务：攻击机不在武器/探测包线内时，自动计算目标外侧开火占位点并改写航路；进入包线后自动发射武器。
- 空战追击：飞机发现敌机但暂时打不到时，自动计算敌机尾后 `5 nm` 的尾随点并改写航路。

### `ui/map_canvas.py`

新增动态任务航路绘制层：

- 绘制 `motion == "dynamic"` 的单位当前位置到 `unit.route.points` 的虚线航路。
- 不改变原有 `routes.json` 固定航线绘制。

### `data/scenarios/taiwan_fujian_demo.json`

示例场景新增：

- `blue-air-01`：蓝方巡逻飞机。
- `blue-cap-north`：蓝方巡逻任务。
- `red-strike-blue-ship`：红方打击蓝方舰船任务。

## 行为说明

任务优先级高于 JSON 初始固定航线。单位一旦被任务接管，会被设置为 `motion = "dynamic"`，并且 `route_id` 会清空，避免静态路线覆盖任务航路。

动态航路会在仿真运行中被不断消费和重写。如果需要恢复场景初始状态，应重新加载场景 JSON。
