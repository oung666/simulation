# Perspective Rules Decisions

## Purpose

This document records the default behavior decisions for the planned god/blue/red perspective switch. The goal is to keep side perspectives close to realistic situational awareness while preserving god view as the referee/debug view.

## Decisions

### 1. Enemy Contacts Are Read-Only In Side Views

In blue or red perspective, known enemy contacts should be view-only.

- Friendly units can be inspected and operated normally.
- Enemy contacts can be selected to view last-known information.
- Enemy contacts cannot be edited, duplicated, moved, or deleted.
- Full enemy-unit editing remains available only in god view.

Reason: a side perspective sees an intelligence contact, not the true underlying unit object. Allowing edits or duplication would mix intelligence state with truth state and could leak hidden enemy information.

### 2. Shared Contacts Cannot Directly Trigger Weapon Launch

Shared contacts can support situational awareness and maneuvering, but cannot directly authorize a weapon launch in the first implementation.

- A unit may route toward or intercept a shared contact's last-known position.
- A unit must locally detect the target before launching.
- Existing `is_detected()` logic remains the launch gate.
- Future phases may add optional rules for high-confidence shared-contact launches or specific weapon types.

Reason: this avoids making an entire side instantly omniscient once one sensor detects a target. It also keeps initial engagement behavior conservative and easy to validate.

### 3. Enemy Damage State Requires Confirmation

In side perspectives, enemy units destroyed in the truth state should not immediately reveal their real damage state unless that side has confirmation.

- Friendly unit status can show true alive/damaged state.
- Enemy contacts should show contact state such as current, stale, lost, or status unknown.
- Enemy contacts should not automatically show `destroyed` just because the truth-state unit has `alive=False`.
- A kill or damage state should become visible only when confirmed by that side's own observation or a credible own-side combat event.

Reason: side views should model what the side knows, not what the simulation engine knows. If a target is destroyed but the side has not observed or confirmed it, the contact should remain unknown or eventually expire.

## Implementation Defaults

- God view keeps full truth-state visibility and full editing permissions.
- Blue/red views show all friendly units plus enemy contacts from that side's `ContactTrack` picture.
- Enemy contact popups show last-known position, confidence, source, shared/local state, and freshness.
- Enemy contact popups hide true route, fuel, full weapons inventory, exact live/dead state, and edit actions.
- Strike missions may navigate toward a shared contact but must reacquire locally before firing.

## Implementation Plan

当前仿真有真实全局态 `Scenario.units`，也已有每方 `contact_tracks`，但地图、单位弹窗、战斗单元表、任务攻击逻辑仍大量直接读取真实态。需要新增“视角/态势过滤层”：上帝视角保留裁判全知，蓝方/红方视角只显示和决策本方部署、本方传感器探测与通信共享得到的目标。

### Scope

- In: 增加上帝/蓝方/红方视角设置；按视角过滤地图图层、点击选择、弹窗、单位表、状态栏、日志；让任务/交战决策优先消费本方 `ContactTrack` 而不是敌方真实坐标。
- Out: 复杂情报融合、假目标、地形遮蔽、频段级电磁模型、持久化用户偏好。

### Action Items

- [ ] Add a small perspective model, e.g. `core/perspective.py`, defining `god`, `blue`, `red` and helpers such as `is_god_view`, `friendly_side`, `visible_units_for_view`, `visible_track_for_unit`.
- [ ] Add `MapCanvas.current_perspective` plus `set_perspective(mode)` in `ui/map_canvas.py`; default to `god` to preserve current behavior, and clear invalid selected enemy units when switching to a side view.
- [ ] Add a view selector in `ui/main_window.py` display controls or toolbar: `上帝视角 / 蓝方视角 / 红方视角`; connect it to `MapCanvas.set_perspective` and refresh popup, units dialog, status counts, and combat log.
- [ ] Refactor map drawing in `ui/map_canvas.py` so each tactical layer uses the perspective filter: friendly units use true positions; enemy units only render as contact markers from `combat_controller.contact_tracks[side]`; enemy range rings, jammer rings, comms links, dynamic routes, mission areas, and labels are hidden unless visible through the selected side's known picture.
- [ ] Refactor hit-testing and popup behavior in `ui/map_canvas.py` and `ui/unit_info_popup.py`: side views can select friendly real units and enemy contacts, but enemy contacts should show last-known position, confidence, source, stale/shared state, not true weapons, route, fuel, or exact live status.
- [ ] Update `controllers/combat_controller.py` decision logic: keep truth-state sensor resolution for `_update_local_detections`, but make strike routing and launch decisions use side contact tracks; especially `_update_units_on_strike_mission` should route to `ContactTrack.last_known_position` and hold/search if no valid track exists, instead of always using `target.position`.
- [ ] Add engagement helper methods in `CombatController`, e.g. `known_contact_for(side, target_id)`, `target_position_for_decision(attacker, target)`, and `can_launch_on_contact(attacker, target, track)`, so shared/local contact policy is explicit and testable.
- [ ] Filter non-map UI in `ui/main_window.py`: units table shows all units only in god; blue/red views show all friendlies plus known enemy contacts; status counts and message platform should either be perspective counts or clearly marked as debug-only in god view.
- [ ] Handle edge cases: stale contacts should remain as last-known markers until expiry; destroyed enemy units should not reveal death immediately unless observed; flying weapons should show own side weapons and only observed hostile weapons/impacts in side view; switching back to god restores full inspection/editing.
- [ ] Validate with smoke tests/manual checks: run `python -m py_compile app.py main.py core/*.py controllers/*.py engine/*.py ui/*.py`; create a scenario where blue sees red only after detection; verify blue/red/god switching changes map icons, ranges, unit table, popups, strike routing, and combat log without breaking existing god-view behavior.

### Product Rule Defaults

- 蓝/红视角下，敌方已知接触只允许查看，不允许编辑、复制、移动或删除。
- 共享接触可以用于态势显示和机动引导，但不能直接触发武器发射；发射前必须由本机本地探测确认。
- 已毁伤敌方单位在未被本方观察确认前，继续显示为“状态未知”或按接触新鲜度显示为 current/stale/lost。
