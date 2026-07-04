# Project Optimization Plan

围绕当前纯 Qt 离线战术仿真原型做一轮工程化和体验优化：先修复影响演示观感的中文乱码和浮窗一致性，再逐步拆分 `main_window.py`、补强场景编辑与数据校验，最后提升探测、交战逻辑的可解释性。

## Scope
- In: 中文编码清理、地图浮窗统一管理、控制面板模块化、场景与单位编辑能力、武器与平台数据库校验、战斗日志增强、探测交战解释性、基础验证流程。
- Out: 不更换 Qt 技术栈、不引入 Web 前端、不重写仿真引擎、不追求一次性完成全部真实军事模型、不改变现有 JSON 场景格式的向后兼容。

## Action Items
- [x] Audit all visible Chinese text in `data/scenarios/`, `ui/`, `core/db/`, and `docs/`; restore corrupted strings to UTF-8 and add a quick script or checklist to catch future mojibake.
- [x] Add an overlay coordination layer for `UnitInfoPopup`, `CombatLogOverlay`, and `ControlOverlay` to standardize z-order, positioning, minimize/restore markers, close behavior, and resize handling.
- [x] Split the first control-page responsibility out of `ui/main_window.py` into `ui/control_pages.py`, and register map info, display settings, JSON scene loading, route editing, mission viewing, and combat log actions through the page registry.
- [x] Extend the control overlay page registration API so new pages can be added with a title, icon, builder, preferred size, default placement, and optional restore marker behavior.
- [x] Build a scenario editing pass: add/save units, edit position/speed/fuel/radar/comms/weapons, duplicate units, delete units, and save the current scenario back to JSON safely.
- [x] Add database validation for `core/db/_weapons.py`, `_ships.py`, `_aircraft_cn.py`, `_ground_vehicles.py`, and related loaders to flag missing fields, duplicate classes, invalid ranges, and unit mismatches.
- [x] Improve combat log usability: filters by side/event type, click-to-focus related unit or event position, unread count while minimized, and concise event categories.
- [x] Add explainable detection/engagement details in the UI and logs: detection range used, distance, RCS/jamming modifiers, weapon selected, launch condition, hit probability, and result reason.
- [x] Add focused smoke tests or scripts for scenario loading, database validation, combat stepping, overlay creation, and core UI construction using Qt offscreen mode.
- [x] Create a manual QA checklist for release/demo runs: load default scenario, switch perspectives, open/close overlays, play/pause/step, trigger combat, reload JSON, and verify no text overlap or stale panels.

## Completed In This Pass
- Added `save_scenario()` and JSON serializers in `core/scenario.py`, with atomic writes and support for both split-unit scenarios and single-file scenarios.
- Added scenario save roundtrip validation to `tools/validate_project.py`.
- Expanded `UnitInfoPopup` editing to cover radar, communications, EW/jamming, fuel, range, altitude, and editable weapon inventory.
- Added `新增单位`, `保存当前场景`, and `另存为 JSON` actions to the JSON scene control page.
- Added route, mission, and combat-log control pages to the map control overlay.
- Added `ui/control_pages.py` as the first page-registration split point for future feature modules.
- Added combat log side/type filters, unread marker counts, event categories, and click-to-focus behavior.
- Added explainable detection, launch, hit, and miss log messages with distances, ranges, jamming pressure, RCS, and hit probabilities.
- Extended Qt smoke checks to open the newly registered control pages.

## Completed In Next Pass
- Added `ui/new_unit_dialog.py`, a richer new-unit dialog for choosing side, unit type, database platform template, initial coordinate, initial weapon, and weapon quantity.
- Replaced the old one-click default unit creation with template-based unit creation from the dialog.
- Added combat-log export from the log control page. JSON export keeps structured event fields; text export writes readable filtered entries.
- Added persistent combat-log preferences using `QSettings`: side filter, event-type filter, minimized/closed state, and maximized state.
- Extended Qt smoke checks to instantiate the new-unit dialog and verify its request payload.

## Completed In Current Pass
- Extended `NewUnitDialog` from one initial weapon to a multi-weapon list: choose a weapon, set quantity, add it to the table, and remove selected entries before creating the unit.
- Added template-aware default weapon selection so aircraft, ships, facilities, and ground vehicles start with a more sensible weapon suggestion when possible.
- Added creation-time terrain validation before a new unit is appended to the scenario. Invalid ground/facility/airbase or ship placement is blocked with a warning.
- Added smoke checks for multi-weapon requests, `MainWindow._new_unit_from_request()`, weapon inventory creation, and terrain validation failure paths.
- Moved unit creation out of the `JSON 场景` page into a standalone `新增单位` first-level control-menu page.
- Added map-pick deployment placement for new units: the user can arm position picking from the `新增单位` page and set the default creation coordinate with a map click.
- Replaced the dark inherited deployment warning with a light warning dialog so invalid land/sea placement messages remain readable.
- Added replay recording, settlement, battle-report storage, and toolbar recording, settlement, and battle-report actions.
- Added a dedicated battle-report dialog with side overview, unit details, replay entry, and two cleanup levels for report-only vs. report-plus-replay deletion.
- Added a lightweight replay runtime and standalone replay viewer driven by snapshots plus event stream instead of the live simulation state.

## Verification
- `python tools\validate_project.py`
- `python tools\smoke_qt.py`
- `python -m compileall ui core controllers tools`

## Follow-Up Candidates
- Continue splitting `ui/main_window.py` by moving the actual page widget builders into dedicated page classes.
- Add richer default loadouts with multiple preset weapons per platform template.
- Add persistent positions for map overlays if future work makes them draggable.
