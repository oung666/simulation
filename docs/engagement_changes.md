# 交战引擎修改说明

## 项目差异与移植取舍

`panopticon` 的交战系统分布在 TypeScript 客户端和 Python Gym 后端中，核心规则包括探测、射程判定、发射武器、在飞武器追踪、燃料耗尽、概率命中和自动防御。它的单位模型更重，区分飞机、舰船、设施、机场、武器等独立类，并使用 Shapely/OpenLayers 几何对象做探测范围判断。

当前 `simulation` 项目是轻量 PyQt/QPainter 架构，所有战斗单位统一为 `CombatUnit` dataclass，运动由 `MotionController` 插值计算，地图直接用 `QPainter` 绘制。因此本次没有直接复制 panopticon 代码，而是保留规则流程，改成适配当前项目的 dataclass + 纯 Python 地理计算 + QPainter 渲染。

主要取舍：

- 用 Haversine 球面距离替代 panopticon 的 Shapely `Point.buffer().contains()`。
- 用 `WeaponTemplate` 表示单位库存武器，用 `FlyingWeapon` 表示已发射武器。
- 被命中的单位不从 `Scenario.units` 移除，而是标记 `alive=False` 并在地图上灰显。
- 自动交战暂按 `side != unit.side` 判断敌我，不引入 panopticon 的关系/条令系统。
- 交战逻辑按仿真每秒执行一次，地图仍按原 33ms timer 重绘。

## 新增代码

- `core/geo_utils.py`
  新增海里/公里换算、Haversine 距离、方位角、终点坐标、按速度推进一秒的位置计算。

- `core/weapon.py`
  新增 `WeaponTemplate` 和 `FlyingWeapon` 两个 dataclass，分别用于单位武器库存和场景中的在飞武器。

- `engine/__init__.py`
  新增交战引擎包入口。

- `engine/engagement.py`
  新增交战核心函数：探测判定、射程判定、目标追踪数量统计、发射武器、更新在飞武器、命中杀伤判定。

- `controllers/combat_controller.py`
  新增 `CombatController` 和 `CombatEvent`。控制器每个仿真秒同步单位位置、自动搜索敌方目标、发射武器、更新在飞武器，并记录战斗日志。

## 修改代码

- `core/scenario.py`
  扩展 `CombatUnit` 字段：`heading`、`detection_range_nm`、`weapons`、`target_id`、`alive`。扩展 `Scenario.flying_weapons`，并让 `load_scenario()` 解析新 JSON 字段，同时兼容旧场景。

- `ui/map_canvas.py`
  集成 `CombatController` 到 `_tick()`，每个仿真秒执行交战逻辑。新增在飞武器图层、虚线尾迹、命中/未命中短效动画，并让毁伤单位保留在地图上灰显。

- `ui/main_window.py`
  左侧 Dock 新增“战斗日志”列表；状态栏新增存活单位和在飞武器数量；战斗单元弹窗增加状态、探测范围和武器数量。

- `data/scenarios/taiwan_fujian_demo.json`
  为默认演示场景的单位补充 `detection_range_nm` 和 `weapons` 字段，使场景可触发自动探测和武器发射。

- `README.md`、`app.py`、`main.py` 及各模块导入
  当前目录名是 `simulation`，但旧代码仍按 `qt_frontend_v6` 导入，导致项目无法直接启动。本次统一改为 `simulation.*` 导入，并同步更新 README 启动命令。

## 验证结果

- `python -m py_compile core\geo_utils.py core\weapon.py engine\__init__.py engine\engagement.py controllers\combat_controller.py core\scenario.py ui\map_canvas.py ui\main_window.py main.py app.py`
  通过。

- 运行场景加载和 `CombatController` 烟测：
  默认场景可加载，交战控制器可生成探测、发射、命中/未命中日志，并能更新存活单位与在飞武器状态。

- 使用 `QT_QPA_PLATFORM=offscreen` 实例化 `MainWindow` 并推进 `_tick()`：
  主窗口、地图画布、战斗日志和状态统计可创建并运行，无运行时异常。
