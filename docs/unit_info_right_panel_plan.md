# Plan

将作战单元参数卡从地图画布上的浮动弹窗，迁移到 Qt 主窗口最右侧的固定信息面板，目标是点击单位后仍能查看、编辑和执行操作，但不再遮挡地图内容。实现上优先复用现有 `UnitInfoPopup` 的数据刷新、编辑、武器页和操作信号，再把承载方式从地图子控件改为右侧 `QDockWidget` 或固定右侧面板。

## Scope
- In: 调整单位参数显示位置、复用现有参数卡交互、同步左键/右键点击行为、保留编辑/删除/操作菜单、处理空白地图点击时的隐藏或清空状态。
- Out: 不修改场景 JSON 数据结构、不改雷达/通信/干扰圈绘制规则、不重做单位参数字段内容、不引入 Web 前端或新 UI 框架。

## Action items
[ ] Inspect `ui/main_window.py` around `self.unit_info_popup = UnitInfoPopup(self.map_canvas)` and `_show_unit_popup/_hide_unit_popup/_position_unit_popup` to identify all map-floating assumptions.
[ ] Refactor `UnitInfoPopup` so it can be hosted inside a right-side Qt container, removing fixed map-relative movement as the normal display path while keeping its existing signals.
[ ] Add a right-side `QDockWidget` in `MainWindow`, for example `QDockWidget("作战单元参数", self)`, and place `UnitInfoPopup` inside it with `Qt.RightDockWidgetArea`.
[ ] Replace `_position_unit_popup` usage with right-panel refresh/show logic, so left-click or right-click on a unit updates the panel instead of moving a popup over the map.
[ ] Decide map blank-click behavior: hide the right panel, or keep the panel visible while clearing map selection; implement the chosen behavior consistently in `_hide_unit_popup` and `_hide_unit_popup_keep_selection`.
[ ] Preserve contact-track display for side perspectives by keeping `_refresh_unit_popup` paths for both real units and known enemy contacts.
[ ] Verify unit operations still work from the right panel: edit fields, save, delete, duplicate, plot course, manual attack page, and return to details page.
[ ] Run `python -m compileall ui\main_window.py ui\unit_info_popup.py ui\map_canvas.py` and manually launch the app to confirm the panel stays at the far right and does not cover the map.
[ ] Check edge cases: resizing the main window, switching perspectives, selected unit destroyed/deleted, selected contact going stale, and repeated left/right clicks on different units.

## Open questions
- 空白处点击地图时，右侧参数面板是直接隐藏，还是保留最后一次选中单位的信息但清除地图高亮？
- 右侧参数面板是否允许用户拖出为浮动 Dock，还是固定锁定在最右侧？
- 当前 `UnitInfoPopup` 文案存在乱码，是否顺手纳入这次右侧面板迁移一起修正？
