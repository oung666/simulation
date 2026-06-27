# Plan

将当前 Qt 左侧 `仿真控制` Dock 改造为地图内部浮动控件：初始状态只显示一级菜单按钮，包括 `离线地图`、`显示控制`、`JSON 场景`，点击按钮后在同一个浮动面板内切换到对应二级内容页。实现上复用现有 `_build_map_card()`、`_build_display_card()`、`_build_json_card()` 的内容构建逻辑，并新增一个可注册页面的菜单框架，方便后续继续加入路线设置、任务控制、态势图层等功能。

## Scope
- In: 地图内浮动控制面板、一级菜单按钮、二级内容页切换、返回菜单、关闭/缩小入口、现有三块内容迁移、后续页面注册接口、地图 resize 后重定位。
- Out: 不改场景 JSON、不改仿真计算逻辑、不改地图绘制逻辑、不重做顶部工具栏播放/复位/倍率按钮、不迁移已经独立成地图浮窗的单位参数和战斗日志。

## Action items
[ ] Inspect `ui/main_window.py` 中 `_build_control_dock()`、`_build_map_card()`、`_build_display_card()`、`_build_json_card()`、`_build_simulation_card()` 的依赖关系，确认哪些控件字段仍需要被 `MainWindow` 后续方法访问。
[ ] Add a reusable floating menu widget, likely `ui/control_overlay.py`, hosted with `self.map_canvas` as parent and styled consistently with existing map overlays.
[ ] Define a page registration API such as `register_page(page_id, title, builder, order, icon_text=None)` so future features can add menu entries without rewriting the overlay shell.
[ ] Implement the first-level menu view with three default entries: `离线地图`、`显示控制`、`JSON 场景`; each entry opens its registered second-level page.
[ ] Implement the second-level page container with a header, back button, optional close/minimize button, and scrollable content area for longer future pages.
[ ] Reuse existing card/content builders by adapting them to return page content widgets or by extracting card body builders from `_build_map_card()`、`_build_display_card()`、`_build_json_card()`.
[ ] Remove or hide the old left `QDockWidget("仿真控制")` path after the overlay version is connected, avoiding duplicated controls.
[ ] Add positioning helpers in `MainWindow` to place the control overlay inside the map, preferably top-left with margins, and keep it within bounds on resize/viewport changes.
[ ] Preserve signal wiring for current controls: perspective combo, radar range toggle, radar animation toggle, communication overlay toggle, choose JSON, and reload JSON.
[ ] Add a small minimized marker if the overlay is minimized, similar to the combat-log marker, so users can restore the control menu from the map.
[ ] Verify edge cases: changing perspective from the overlay, reloading JSON while a page is open, resizing the window, hiding/restoring the menu, opening future pages, and interactions with unit info/combat log floating panels.
[ ] Run `python -m compileall ui\main_window.py ui\control_overlay.py ui\map_canvas.py` and manually launch the app to confirm the left Dock is gone and the map overlay menu works.

## Open questions
- 一级菜单浮窗默认放在地图左上角，还是沿用原左侧栏位置贴地图左边居中？
- 二级内容页打开后是否自动覆盖一级菜单，还是菜单栏常驻在左侧、内容显示在右侧？
- 缩小后的恢复标识希望显示为 `控制`、`菜单`，还是 `仿真控制`？
