# Manual QA Checklist

Use this checklist before demos or larger UI changes.

## Startup
- [ ] Launch the app with the default scenario.
- [ ] Confirm the map loads without Python exceptions.
- [ ] Confirm unit names, route names, and common UI labels display readable Chinese text.
- [ ] Confirm the status bar shows coordinates, alive counts, and simulation time.

## Map Overlays
- [ ] Open the control menu, expand/collapse it, and open each page: `离线地图`, `显示控制`, `JSON 场景`, `新增单位`, `路线设置`, `任务查看`, `日志控制`.
- [ ] Minimize and restore the control menu.
- [ ] Open, minimize, restore, maximize/restore, and close the combat log overlay.
- [ ] Click a unit and confirm the unit info popup appears at the map's right edge.
- [ ] Close the unit info popup and confirm selection/range rings clear.
- [ ] Resize the window and confirm overlays stay inside the map.

## Simulation Controls
- [ ] Play, pause, reset view, and step once from the toolbar.
- [ ] Change playback speed and confirm time advances.
- [ ] Switch active side between BLUE and RED.
- [ ] Switch map perspective between god/blue/red and confirm visible units/logs update.

## Display Controls
- [ ] Toggle selected-unit radar range.
- [ ] Toggle radar animation.
- [ ] Toggle communications overlay.
- [ ] Click blank map space and confirm selected-unit-only overlays disappear.

## Data And JSON
- [ ] Open `JSON 场景`, choose a scenario JSON, and reload it.
- [ ] Add a new unit from the standalone `新增单位` menu page: click `在地图上选择位置`, left-click a map location, open the new-unit dialog, choose side/type/platform, add two initial weapons with different quantities, save the scenario, reload it, and confirm the unit and weapons remain.
- [ ] Try to create a ground/facility/airbase unit on sea or a ship on land, and confirm the dialog blocks creation with a deployment warning.
- [ ] Confirm the deployment warning uses a readable light background and dark text.
- [ ] Edit a unit's radar/comms/EW fields and weapon quantities, save the scenario, reload it, and confirm the changes remain.
- [ ] Confirm combat log, unit list, and overlays do not keep stale data after reload.
- [ ] Run `python tools\validate_project.py`.
- [ ] Run `python tools\smoke_qt.py`.

## Combat Flow
- [ ] Let the scenario run long enough to generate detection/launch/log events.
- [ ] Confirm combat log entries are visible and update in the map overlay.
- [ ] Filter combat log entries by side and event type.
- [ ] Minimize combat log, generate or wait for a new event, and confirm the marker shows unread count.
- [ ] Click a combat log entry and confirm the map focuses the related unit or event position.
- [ ] Export the filtered combat log as JSON and text, then confirm the files contain readable event content.
- [ ] Change combat log filters or minimize/maximize state, restart the app, and confirm preferences are restored.
- [ ] Confirm destroyed units remain visible in damaged styling.
- [ ] Confirm no floating panel text overlaps in a way that blocks core map use.
