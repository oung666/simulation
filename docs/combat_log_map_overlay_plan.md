# Plan

将当前左侧控制面板里的战斗日志迁移为地图内部浮动控件，固定显示在地图区域内，支持缩小、放大/还原、关闭；缩小后在地图左下角显示一个小信息标，点击后恢复日志面板。实现上复用现有 `_refresh_combat_log()` 的事件过滤和格式化逻辑，但把承载控件从控制 Dock 中拆出来，改成 `map_canvas` 的子控件。

## Scope
- In: 新增地图内战斗日志浮窗、缩小/放大/关闭按钮、左下角最小化标识、日志内容刷新、地图 resize 后重新定位、视角切换/战斗事件更新时同步刷新。
- Out: 不修改战斗事件生成逻辑、不修改 `CombatController` 日志数据结构、不改场景 JSON、不新增 Web 前端、不改变现有单位参数浮窗行为。

## Action items
[ ] Inspect current combat log flow in `ui/main_window.py`: `_build_combat_log_card()`, `self.combat_log_list`, `_refresh_combat_log()`, and `combatEventsChanged` connections.
[ ] Add a new reusable Qt widget, likely `ui/combat_log_overlay.py`, containing title, `QListWidget`, and three controls: minimize, maximize/restore, close.
[ ] Create a compact minimized marker widget as a `map_canvas` child, positioned at the map's bottom-left; show unread/count text such as `战斗日志` or latest event count.
[ ] Replace or disable the existing left Dock combat-log card so the log is no longer duplicated in the control panel.
[ ] Instantiate the overlay and minimized marker in `MainWindow` with `self.map_canvas` as parent, mirroring the current map-floating `UnitInfoPopup` pattern.
[ ] Refactor `_refresh_combat_log()` so it writes to the floating overlay list and updates the minimized marker when the overlay is minimized or closed.
[ ] Add positioning helpers in `MainWindow`: default log overlay size, bottom/left or preferred map position, maximized map-fill bounds, and bottom-left marker placement after map resize/viewport changes.
[ ] Implement minimize behavior: hide the full log overlay, show the small bottom-left marker, keep receiving log updates.
[ ] Implement maximize/restore behavior: toggle between compact floating size and larger map overlay size without leaving the map canvas.
[ ] Implement close behavior: hide both full overlay and minimized marker until a future explicit UI entry point is chosen, or until combat events reopen it if that behavior is desired.
[ ] Verify edge cases: map resize, playback updates, perspective changes, no combat events, many log entries, horizontal/vertical scrollbars, overlay covering unit parameter popup, and repeated minimize/maximize/close cycles.
[ ] Run `python -m compileall ui\main_window.py ui\combat_log_overlay.py ui\map_canvas.py` and manually launch the app to verify the log floats inside the map and the left-bottom marker restores it.

## Open questions
- 关闭战斗日志后，新的战斗事件是否自动重新打开左下角小标，还是保持完全关闭直到用户通过某个入口恢复？
- 放大状态是占据地图大部分区域，还是只变成一个更大的右/下侧浮窗？
- 战斗日志浮窗默认放在地图哪个位置：左下、右下，还是保持在当前截图类似的左侧区域？
