from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QPen  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QToolBar  # noqa: E402

from simulation.core.geo import LonLat  # noqa: E402
from simulation.replay.models import ReplayEvent, ReplayRecord, ReplaySnapshot  # noqa: E402
from simulation.replay.storage import ReplayStorage  # noqa: E402
from simulation.styles.theme import build_application_stylesheet  # noqa: E402
from simulation.ui.main_window import MainWindow  # noqa: E402
from simulation.ui.new_unit_dialog import NewUnitDialog, NewUnitRequest, NewUnitWeaponRequest  # noqa: E402
from simulation.ui.replay_viewer_dialog import ReplayViewerDialog  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(build_application_stylesheet())
    window = MainWindow()
    window.resize(1280, 820)
    window.map_canvas.resize(900, 700)

    _check_control_overlay(window)
    _check_combat_log_overlay(window)
    _check_unit_popup(window)
    _check_new_unit_dialog(window)
    _check_new_unit_creation_flow(window)
    _check_himars_svg_icon(window)
    _check_selected_ring_uses_yellow_only()
    _check_replay_toolbar_actions_remain_clickable(window)
    _check_recording_switch_button(window)
    _check_replay_viewer_playback_controls()
    _check_manual_settlement_generates_battle_report(window)

    print("Qt smoke checks passed.")
    app.quit()
    return 0


def _check_control_overlay(window: MainWindow) -> None:
    assert window.control_overlay.parent() is window.map_canvas
    window._restore_control_overlay()
    window._position_control_overlay_widgets()
    assert not window.control_overlay.isHidden()
    window.control_overlay.toggle_collapsed()
    window._position_control_overlay_widgets()
    assert window.control_overlay.width() <= 80
    window.control_overlay.toggle_collapsed()
    for page_id in ["display", "new_unit", "route", "missions", "combat_log"]:
        assert window.control_overlay.page(page_id) is not None
        window._show_control_page(page_id)
        assert not window.control_page_window.isHidden()
    window._begin_new_unit_position_pick()
    assert window.map_canvas._apply_pending_interaction(
        QPointF(window.map_canvas.width() / 2, window.map_canvas.height() / 2)
    )
    assert window._new_unit_position is not None
    assert window._new_unit_position == window.map_canvas.center
    window._begin_new_unit_position_pick()
    window._handle_coordinate_picked(120.25, 24.5)
    assert window._new_unit_position.lon == 120.25
    assert window._new_unit_position.lat == 24.5
    window._minimize_control_overlay()
    assert window.control_overlay.isHidden()
    assert window.control_page_window.isHidden()
    assert not window.control_overlay_marker.isHidden()
    window._restore_control_overlay()
    assert not window.control_overlay.isHidden()
    assert window.control_overlay_marker.isHidden()


def _check_combat_log_overlay(window: MainWindow) -> None:
    assert window.combat_log_overlay.parent() is window.map_canvas
    window._restore_combat_log_overlay()
    window._position_combat_log_widgets()
    assert not window.combat_log_overlay.isHidden()
    window._minimize_combat_log_overlay()
    assert window.combat_log_overlay.isHidden()
    assert not window.combat_log_marker.isHidden()
    window._restore_combat_log_overlay()
    assert not window.combat_log_overlay.isHidden()
    assert window.combat_log_marker.isHidden()


def _check_unit_popup(window: MainWindow) -> None:
    assert window.unit_info_popup.parent() is window.map_canvas
    unit_id = window.scenario.units[0].unit_id
    assert window.map_canvas.select_unit(unit_id)
    window._show_unit_popup(unit_id)
    assert not window.unit_info_popup.isHidden()
    expected_x = window.map_canvas.width() - window.unit_info_popup.width() - 8
    assert window.unit_info_popup.x() == expected_x
    window._hide_unit_popup()
    assert window.unit_info_popup.isHidden()


def _check_new_unit_dialog(window: MainWindow) -> None:
    dialog = NewUnitDialog(window, LonLat(120.0, 24.0), "blue")
    if dialog.weapon_combo.count() > 1:
        dialog.weapon_combo.setCurrentIndex(1)
        dialog.weapon_quantity_input.setValue(3)
        dialog._add_selected_weapon()
    request = dialog.request()
    assert request.side == "blue"
    assert request.unit_type
    assert request.class_name
    assert request.unit_id
    assert request.name
    assert request.position.lon == 120.0
    assert request.position.lat == 24.0
    assert len(request.weapons) >= 1
    assert request.weapons[0].quantity == 3


def _check_new_unit_creation_flow(window: MainWindow) -> None:
    request = NewUnitRequest(
        side="blue",
        unit_type="aircraft",
        class_name="F-35A Lightning II",
        unit_id="smoke-aircraft",
        name="Smoke Aircraft",
        position=LonLat(120.0, 24.0),
        weapons=[NewUnitWeaponRequest("AIM-120D AMRAAM", 2)],
    )
    unit = window._new_unit_from_request(request)
    assert unit.unit_id == "smoke-aircraft"
    assert unit.class_name == "F-35A Lightning II"
    assert len(unit.weapons) == 1
    assert unit.weapons[0].current_quantity == 2
    assert window.terrain_classifier.validate_deployment_for_unit(unit).ok

    invalid_ground_request = NewUnitRequest(
        side="blue",
        unit_type="ground_vehicle",
        class_name="HIMARS",
        unit_id="smoke-ground",
        name="Smoke Ground",
        position=LonLat(118.0, 21.0),
        weapons=[],
    )
    invalid_ground = window._new_unit_from_request(invalid_ground_request)
    assert not window.terrain_classifier.validate_deployment_for_unit(invalid_ground).ok


def _check_himars_svg_icon(window: MainWindow) -> None:
    request = NewUnitRequest(
        side="blue",
        unit_type="ground_vehicle",
        class_name="HIMARS",
        unit_id="smoke-himars",
        name="Smoke HIMARS",
        position=LonLat(120.0, 24.0),
        weapons=[],
    )
    unit = window._new_unit_from_request(request)
    assert window.map_canvas._unit_icon_name(unit) is None


def _check_replay_toolbar_actions_remain_clickable(window: MainWindow) -> None:
    window.resize(900, 820)
    window.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    toolbars = window.findChildren(QToolBar)
    assert window.record_toggle_button is not None
    assert window.record_toggle_button.isVisible()
    assert window.record_toggle_button.isEnabled()
    for action in [window.settlement_action, window.battle_report_action]:
        button = next((toolbar.widgetForAction(action) for toolbar in toolbars if toolbar.widgetForAction(action)), None)
        assert button is not None
        assert button.isVisible()
        assert button.isEnabled()


def _check_selected_ring_uses_yellow_only() -> None:
    for relative_path in [
        "simulation/ui/map_canvas.py",
        "simulation/ui/replay_viewer_dialog.py",
    ]:
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "drawEllipse(screen, 27.0, 27.0)" not in source


def _check_recording_switch_button(window: MainWindow) -> None:
    with tempfile.TemporaryDirectory(prefix="simulation-record-switch-") as temp_dir:
        temp_root = Path(temp_dir)
        window._replay_storage = ReplayStorage(
            temp_root / "replays",
            temp_root / "battle_reports",
        )
        window._battle_reports_cache = []
        switch = window.record_toggle_button
        assert switch is not None
        assert switch.text() == ""
        assert switch.toolTip() == "录制开关"
        assert switch.focusPolicy() == Qt.NoFocus
        assert switch.width() >= 120
        assert switch.track_color_name() == "#ffffff"
        assert switch.property("recording") is False
        window._step_forward()
        recording_started_at = float(window.map_canvas.clock.current_time)
        QTest.mouseClick(switch, Qt.LeftButton, pos=switch.rect().center())
        assert window._recording_enabled is True
        assert window.record_action.isChecked()
        assert switch.property("recording") is True
        window._step_forward()
        QTest.mouseClick(switch, Qt.LeftButton, pos=switch.rect().center())
        assert window._recording_enabled is False
        assert not window.record_action.isChecked()
        assert switch.property("recording") is False
        assert len(window._battle_reports_cache) >= 1
        assert len(window._replay_storage.list_reports()) >= 1
        expected_duration = float(window.map_canvas.clock.current_time) - recording_started_at
        assert window._battle_reports_cache[0].duration_seconds == expected_duration


def _check_replay_viewer_playback_controls() -> None:
    replay = ReplayRecord(
        replay_id="smoke-replay",
        scenario_name="Smoke Replay",
        started_at="2026-06-30T10:00:00",
        ended_at="2026-06-30T10:00:10",
        settlement_reason="manual_settlement",
        duration_seconds=10.0,
        tick_interval_seconds=1.0,
        snapshot_interval_seconds=2.5,
        participants=["blue", "red"],
        initial_state={"units": []},
        snapshots=[
            ReplaySnapshot(
                time=0.0,
                clock_state={"current_time": 0.0},
                unit_states=[
                    {
                        "unit_id": "blue-1",
                        "name": "蓝方一号",
                        "side": "blue",
                        "unit_type": "ship",
                        "class_name": "Destroyer",
                        "alive": True,
                        "position": {"lon": 120.0, "lat": 24.0},
                        "target_id": "red-1",
                        "detection_range_nm": 70.0,
                        "range_nm": 3.5,
                        "comms_on": True,
                        "comms_range_nm": 220.0,
                    },
                    {
                        "unit_id": "red-1",
                        "name": "红方一号",
                        "side": "red",
                        "unit_type": "aircraft",
                        "class_name": "Aircraft",
                        "alive": True,
                        "position": {"lon": 120.3, "lat": 24.25},
                        "target_id": "",
                        "detection_range_nm": 95.0,
                        "range_nm": 5.5,
                        "comms_on": True,
                        "comms_range_nm": 120.0,
                    },
                    {
                        "unit_id": "red-2",
                        "name": "红方二号",
                        "side": "red",
                        "unit_type": "ship",
                        "class_name": "Destroyer",
                        "alive": True,
                        "position": {"lon": 120.32, "lat": 24.27},
                        "target_id": "",
                        "detection_range_nm": 65.0,
                        "range_nm": 4.5,
                        "comms_on": True,
                        "comms_range_nm": 120.0,
                    },
                ],
                flying_weapon_states=[],
                mission_states=[],
                contact_track_states=[],
            ),
            ReplaySnapshot(
                time=10.0,
                clock_state={"current_time": 10.0},
                unit_states=[
                    {
                        "unit_id": "blue-1",
                        "name": "蓝方一号",
                        "side": "blue",
                        "unit_type": "ship",
                        "class_name": "Destroyer",
                        "alive": True,
                        "position": {"lon": 120.1, "lat": 24.05},
                        "target_id": "red-1",
                        "detection_range_nm": 70.0,
                        "range_nm": 3.5,
                        "comms_on": True,
                        "comms_range_nm": 220.0,
                    },
                    {
                        "unit_id": "red-1",
                        "name": "红方一号",
                        "side": "red",
                        "unit_type": "aircraft",
                        "class_name": "Aircraft",
                        "alive": False,
                        "position": {"lon": 120.35, "lat": 24.22},
                        "target_id": "",
                        "detection_range_nm": 95.0,
                        "range_nm": 5.5,
                        "comms_on": True,
                        "comms_range_nm": 120.0,
                    },
                ],
                flying_weapon_states=[],
                mission_states=[],
                contact_track_states=[],
            ),
        ],
        event_stream=[
            ReplayEvent(
                time=2.0,
                event_type="shared_contact",
                source_id="blue-1",
                target_id="red-1",
                weapon_class="",
                position={"lon": 120.2, "lat": 24.1},
                message="蓝方共享目标",
                extra={},
            ),
            ReplayEvent(
                time=8.0,
                event_type="unit_destroyed",
                source_id="blue-1",
                target_id="red-1",
                weapon_class="",
                position={"lon": 120.35, "lat": 24.22},
                message="红方一号被摧毁",
                extra={},
            ),
        ],
        highlights=[],
        final_state={"alive": {"blue": 1, "red": 0}},
    )
    dialog = ReplayViewerDialog(replay)
    dialog.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    assert dialog.windowTitle() == "地图回放"
    assert not hasattr(dialog, "unit_table")
    assert dialog.map_canvas.objectName() == "ReplayMapCanvas"
    assert dialog.map_canvas.state()["units"]
    assert dialog.display_control_panel.parent() is dialog.map_canvas
    assert dialog.display_control_panel.isVisible()
    assert dialog.display_control_label.text() == "显示控制"
    assert dialog.radar_ranges_checkbox.text() == "选中单位雷达范围圈"
    assert dialog.communications_overlay_checkbox.text() == "显示通信态势共享"
    assert dialog.radar_ranges_checkbox.isChecked()
    assert dialog.communications_overlay_checkbox.isChecked()
    assert dialog.map_canvas.selected_unit_id == "blue-1"
    radar_units = []
    original_draw_detection_range_ring = dialog.map_canvas._draw_detection_range_ring
    dialog.map_canvas._draw_detection_range_ring = lambda painter, unit, highlighted=False: radar_units.append(unit["unit_id"])
    dialog.map_canvas.show_communications_overlay = False
    dialog.map_canvas._draw_display_control_layers(None)
    dialog.map_canvas.show_communications_overlay = True
    dialog.map_canvas._draw_detection_range_ring = original_draw_detection_range_ring
    assert radar_units == ["blue-1"]
    red_click = dialog.map_canvas._screen_from_lonlat(LonLat(120.3, 24.25)).toPoint()
    QTest.mouseClick(dialog.map_canvas, Qt.LeftButton, pos=red_click)
    assert dialog.map_canvas.selected_unit_id == "red-1"
    radar_units = []
    selected_comms = []
    original_draw_detection_range_ring = dialog.map_canvas._draw_detection_range_ring
    original_draw_communications_overlay = dialog.map_canvas._draw_communications_overlay
    dialog.map_canvas._draw_detection_range_ring = lambda painter, unit, highlighted=False: radar_units.append(unit["unit_id"])
    dialog.map_canvas._draw_communications_overlay = lambda painter, selected: selected_comms.append(selected["unit_id"])
    dialog.map_canvas._draw_display_control_layers(None)
    dialog.map_canvas._draw_detection_range_ring = original_draw_detection_range_ring
    dialog.map_canvas._draw_communications_overlay = original_draw_communications_overlay
    assert radar_units == ["red-1"]
    assert selected_comms == ["red-1"]
    _check_replay_selected_unit_overlay_style(dialog)
    dialog.radar_ranges_checkbox.setChecked(False)
    assert dialog.map_canvas.show_radar_ranges is False
    dialog.radar_ranges_checkbox.setChecked(True)
    assert dialog.map_canvas.show_radar_ranges is True
    dialog.communications_overlay_checkbox.setChecked(False)
    assert dialog.map_canvas.show_communications_overlay is False
    dialog.communications_overlay_checkbox.setChecked(True)
    assert dialog.map_canvas.show_communications_overlay is True
    assert dialog.map_canvas._unit_icon_name(dialog.map_canvas.state()["units"][0]) == "directions_boat_black_24dp.svg"
    assert dialog.map_canvas._unit_icon_name(dialog.map_canvas.state()["units"][1]) == "flight_black_24dp.svg"
    assert dialog.play_button.text() == "▶"
    assert not hasattr(dialog, "pause_button")
    assert dialog.previous_step_button.text() == "上一步"
    assert dialog.next_step_button.text() == "下一步"
    assert [dialog.speed_combo.itemText(index) for index in range(dialog.speed_combo.count())] == ["1x", "2x", "4x", "8x", "100x"]
    assert not hasattr(dialog, "event_combo")
    assert dialog.key_event_button.parent() is dialog.map_canvas
    assert dialog.key_event_panel.parent() is dialog.map_canvas
    assert dialog.key_event_button.isVisible()
    assert dialog.key_event_panel.isVisible()
    assert dialog.key_event_button.y() >= 56
    assert dialog.key_event_panel.y() > dialog.key_event_button.geometry().bottom()
    assert dialog.key_event_title_label.text() == "关键事件"
    assert dialog.key_event_close_button.text() == "X"
    assert dialog.key_event_list.count() == 2
    start_time = dialog.current_time
    QTest.mouseClick(dialog.play_button, Qt.LeftButton)
    QTest.qWait(180)
    assert dialog.current_time > start_time
    assert dialog.play_button.text() == "⏸"
    QTest.mouseClick(dialog.play_button, Qt.LeftButton)
    paused_time = dialog.current_time
    QTest.qWait(80)
    assert dialog.current_time == paused_time
    assert dialog.play_button.text() == "▶"
    QTest.mouseClick(dialog.key_event_close_button, Qt.LeftButton)
    assert not dialog.key_event_panel.isVisible()
    QTest.mouseClick(dialog.key_event_button, Qt.LeftButton)
    assert dialog.key_event_panel.isVisible()
    dialog.key_event_list.setCurrentRow(0)
    assert dialog.current_time == 2.0
    old_zoom = dialog.map_canvas.zoom
    dialog.map_canvas.apply_zoom_delta(1)
    assert dialog.map_canvas.zoom > old_zoom
    dialog.close()


class _PainterProbe:
    def __init__(self) -> None:
        self.brushes = []
        self.pens = []
        self.ellipses = 0
        self.lines = 0

    def save(self) -> None:
        pass

    def restore(self) -> None:
        pass

    def setBrush(self, brush) -> None:  # noqa: N802
        self.brushes.append(brush)

    def setPen(self, pen) -> None:  # noqa: N802
        self.pens.append(pen)

    def drawEllipse(self, *args) -> None:  # noqa: N802
        self.ellipses += 1

    def drawLine(self, *args) -> None:  # noqa: N802
        self.lines += 1


def _brush_color_alpha(brush) -> int | None:
    if isinstance(brush, QColor):
        return brush.alpha()
    color = getattr(brush, "color", lambda: QColor())()
    return color.alpha() if isinstance(color, QColor) and color.isValid() else None


def _check_replay_selected_unit_overlay_style(dialog: ReplayViewerDialog) -> None:
    canvas = dialog.map_canvas
    canvas.resize(980, 620)
    selected = canvas._selected_unit()
    assert selected is not None

    radar_probe = _PainterProbe()
    canvas._draw_detection_range_ring(radar_probe, selected, highlighted=True)
    assert radar_probe.ellipses == 1
    radar_pen = next(pen for pen in radar_probe.pens if isinstance(pen, QPen))
    assert radar_pen.color().name() == "#facc15"
    assert radar_pen.style() == Qt.SolidLine
    assert radar_pen.widthF() >= 3.4
    assert any(alpha == 76 for alpha in (_brush_color_alpha(brush) for brush in radar_probe.brushes))
    wide_radar_probe = _PainterProbe()
    wide_selected = dict(selected, detection_range_nm=1000.0)
    canvas._draw_detection_range_ring(wide_radar_probe, wide_selected, highlighted=True)
    wide_radar_alphas = [
        alpha for alpha in (_brush_color_alpha(brush) for brush in wide_radar_probe.brushes) if alpha is not None
    ]
    assert wide_radar_alphas and max(wide_radar_alphas) > 0

    comms_probe = _PainterProbe()
    canvas._draw_communications_overlay(comms_probe, selected)
    assert comms_probe.ellipses == 1
    assert comms_probe.lines >= 1
    comms_pen = next(pen for pen in comms_probe.pens if isinstance(pen, QPen) and pen.color().name() == "#22d3ee")
    assert comms_pen.style() == Qt.DashLine
    assert comms_pen.widthF() >= 2.2
    assert any(alpha == 22 for alpha in (_brush_color_alpha(brush) for brush in comms_probe.brushes))
    wide_comms_probe = _PainterProbe()
    wide_comms_selected = dict(selected, comms_range_nm=1000.0)
    canvas._draw_communications_overlay(wide_comms_probe, wide_comms_selected)
    wide_comms_alphas = [
        alpha for alpha in (_brush_color_alpha(brush) for brush in wide_comms_probe.brushes) if alpha is not None
    ]
    assert wide_comms_alphas and max(wide_comms_alphas) > 0


def _check_manual_settlement_generates_battle_report(window: MainWindow) -> None:
    with tempfile.TemporaryDirectory(prefix="simulation-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        window._replay_storage = ReplayStorage(
            temp_root / "replays",
            temp_root / "battle_reports",
        )
        window._battle_reports_cache = []
        window._set_recording_enabled(True)
        assert window._recording_enabled is True
        window._step_forward()
        window._settle_current_simulation("manual_settlement")
        assert len(window._battle_reports_cache) >= 1
        assert len(window._replay_storage.list_reports()) >= 1
        dialog = window._build_battle_report_dialog()
        assert dialog.windowTitle() == "战绩"


if __name__ == "__main__":
    raise SystemExit(main())
