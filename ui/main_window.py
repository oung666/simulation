from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from simulation.core.geo import LonLat
from simulation.core.geo import ScreenPoint, lonlat_to_world, world_to_lonlat
from simulation.core.layers import RouteLayerItem, load_layer_document, next_route_id, save_layer_document, upsert_route
from simulation.core.map_document import load_map_document
from simulation.core.mission import PatrolMission, StrikeMission
from simulation.core.paths import get_default_layers_path, get_default_scenario_path, get_map_asset_path, get_package_root
from simulation.core.scenario import CombatUnit, UnitRoute, load_scenario, save_scenario
from simulation.core.terrain import TerrainClassifier
from simulation.core.weapon import WeaponTemplate
from simulation.core.db import get_unit_attributes, get_weapon_attributes
from simulation.replay.recorder import ReplayRecorder
from simulation.replay.results import build_battle_report_summary
from simulation.replay.storage import ReplayStorage
from simulation.ui.battle_report_dialog import BattleReportDialog
from simulation.ui.combat_log_overlay import CombatLogMarker, CombatLogOverlay
from simulation.ui.control_overlay import ControlOverlay, ControlOverlayMarker, ControlPageWindow
from simulation.ui.control_pages import register_main_control_pages
from simulation.ui.map_canvas import MapCanvas
from simulation.ui.new_unit_dialog import NewUnitDialog
from simulation.ui.overlay_manager import OverlayManager
from simulation.ui.recording_switch import RecordingSwitchButton
from simulation.ui.replay_viewer_dialog import ReplayViewerDialog
from simulation.ui.unit_info_popup import UnitInfoPopup


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MainChrome")
        self.setWindowTitle("战术指挥平台 V6 - 纯 Qt 离线地图")
        self.settings = QSettings("SimulationSM", "TacticalSimulation")

        self.map_document = load_map_document(get_map_asset_path())
        self.scenario_path = get_default_scenario_path()
        self.layers_path = get_default_layers_path()
        self.scenario = load_scenario(self.scenario_path)
        self.layer_document = load_layer_document(self.layers_path)
        self.terrain_classifier = TerrainClassifier(self.map_document)
        self.map_canvas = MapCanvas(self.map_document, self.scenario, self.layer_document, self)
        self._viewport_sync_in_progress = False
        self.horizontal_map_scrollbar: QScrollBar | None = None
        self.vertical_map_scrollbar: QScrollBar | None = None
        self._build_map_workspace()
        self.route_drafts: dict[str, dict[str, object]] = {
            "blue": {"start": None, "waypoints": [], "end": None},
            "red": {"start": None, "waypoints": [], "end": None},
        }
        self._new_unit_position: LonLat | None = None
        self._new_unit_pick_armed = False
        self.active_side = "blue"
        self.side_action: QAction | None = None
        self.map_canvas.set_route_drafts(self.route_drafts)
        self.unit_info_popup = UnitInfoPopup(self.map_canvas)
        self.combat_log_overlay = CombatLogOverlay(self.map_canvas)
        self.combat_log_marker = CombatLogMarker(self.map_canvas)
        self._combat_log_maximized = False
        self._combat_log_closed = False
        self._combat_log_seen_event_count = 0
        self._combat_log_unread_count = 0
        self.control_overlay = ControlOverlay(self.map_canvas)
        self.control_overlay_marker = ControlOverlayMarker(self.map_canvas)
        self._control_overlay_closed = False
        self.control_page_window = ControlPageWindow(self.map_canvas)
        self._control_page_widgets: dict[str, QWidget] = {}
        self.overlay_manager = OverlayManager()
        self.overlay_manager.register("unit_info", self.unit_info_popup, self._position_unit_popup_at_map_right)
        self.overlay_manager.register("combat_log", self.combat_log_overlay, self._position_combat_log_widgets)
        self.overlay_manager.register("control_menu", self.control_overlay, self._position_control_overlay_widgets)

        self.coordinate_label = QLabel("经纬度: --, --")
        self.time_label = QLabel("仿真时间: 00:00")
        self.alive_label = QLabel("存活单位: --/--")
        self.statusBar().addWidget(self.coordinate_label)
        self.statusBar().addPermanentWidget(self.alive_label)
        self.statusBar().addPermanentWidget(self.time_label)
        replay_root = get_package_root() / "data"
        self._replay_storage = ReplayStorage(
            replay_root / "replays",
            replay_root / "battle_reports",
        )
        self._replay_recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
        self._battle_reports_cache = self._replay_storage.list_reports()
        self._recording_enabled = False
        self._active_replay_id: str | None = None
        self.record_action: QAction | None = None
        self.record_toggle_button: RecordingSwitchButton | None = None
        self.settlement_action: QAction | None = None
        self.battle_report_action: QAction | None = None
        self.map_canvas.set_replay_recorder(self._replay_recorder)

        self.map_canvas.coordinateHovered.connect(self._update_coordinates)
        self.map_canvas.timeChanged.connect(self._update_time)
        self.map_canvas.mapCoordinatePicked.connect(self._handle_coordinate_picked)
        self.map_canvas.unitLeftClicked.connect(self._handle_unit_left_click)
        self.map_canvas.unitRightClicked.connect(self._show_unit_popup)
        self.map_canvas.mapLeftClicked.connect(self._hide_unit_popup_keep_selection)
        self.map_canvas.viewportChanged.connect(self._refresh_visible_unit_popup)
        self.map_canvas.viewportChanged.connect(self._position_all_overlays)
        self.map_canvas.viewportChanged.connect(self._sync_map_scrollbars)
        self.map_canvas.combatEventsChanged.connect(self._refresh_combat_log)
        self.map_canvas.unitUpdated.connect(self._show_unit_popup)
        self.map_canvas.perspectiveChanged.connect(self._handle_map_perspective_changed)
        self.unit_info_popup.actionRequested.connect(self._handle_unit_popup_action)
        self.unit_info_popup.unitEdited.connect(self._handle_unit_popup_edit)
        self.unit_info_popup.unitDeleted.connect(self._handle_unit_popup_delete)
        self.unit_info_popup.closeRequested.connect(self._hide_unit_popup)
        self.combat_log_overlay.minimizeRequested.connect(self._minimize_combat_log_overlay)
        self.combat_log_overlay.maximizeRequested.connect(self._toggle_combat_log_overlay_size)
        self.combat_log_overlay.closeRequested.connect(self._close_combat_log_overlay)
        self.combat_log_overlay.filterChanged.connect(self._refresh_combat_log)
        self.combat_log_overlay.filterChanged.connect(self._save_user_preferences)
        self.combat_log_overlay.eventActivated.connect(self._focus_combat_log_event)
        self.combat_log_marker.clicked.connect(self._restore_combat_log_overlay)
        self.control_overlay.minimizeRequested.connect(self._minimize_control_overlay)
        self.control_overlay.closeRequested.connect(self._close_control_overlay)
        self.control_overlay.layoutChanged.connect(self._position_control_overlay_widgets)
        self.control_overlay.pageRequested.connect(self._show_control_page)
        self.control_overlay_marker.clicked.connect(self._restore_control_overlay)
        self.control_page_window.closeRequested.connect(self.control_page_window.hide)
        self._build_toolbar()
        self._build_control_overlay()
        self.control_overlay_marker.hide()
        self.overlay_manager.reposition("control_menu")
        self.combat_log_marker.hide()
        self._load_user_preferences()
        self._refresh_combat_log()
        self.overlay_manager.reposition("combat_log")
        self._sync_map_scrollbars()
        self._update_status_counts()

    def _build_map_workspace(self) -> None:
        workspace = QWidget(self)
        workspace.setObjectName("MapWorkspace")
        layout = QGridLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)

        self.horizontal_map_scrollbar = QScrollBar(Qt.Horizontal, workspace)
        self.horizontal_map_scrollbar.setObjectName("MapScrollBar")
        self.horizontal_map_scrollbar.valueChanged.connect(self._handle_horizontal_scrollbar_changed)

        self.vertical_map_scrollbar = QScrollBar(Qt.Vertical, workspace)
        self.vertical_map_scrollbar.setObjectName("MapScrollBar")
        self.vertical_map_scrollbar.valueChanged.connect(self._handle_vertical_scrollbar_changed)

        corner = QWidget(workspace)
        corner.setObjectName("MapScrollCorner")

        layout.addWidget(self.map_canvas, 0, 0)
        layout.addWidget(self.vertical_map_scrollbar, 0, 1)
        layout.addWidget(self.horizontal_map_scrollbar, 1, 0)
        layout.addWidget(corner, 1, 1)
        layout.setColumnStretch(0, 1)
        layout.setRowStretch(0, 1)
        self.setCentralWidget(workspace)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("主控")
        self.play_action = QAction("▶", self)
        self.play_action.triggered.connect(self._toggle_playing)
        step_action = QAction("⏭", self)
        step_action.setToolTip("单步推进 1 仿真秒")
        step_action.triggered.connect(self._step_forward)
        reset_action = QAction("复位", self)
        reset_action.triggered.connect(self.map_canvas.reset_view)
        debug_action = QAction("Debug", self)
        debug_action.triggered.connect(self._show_debug_log)
        message_action = QAction("消息平台", self)
        message_action.triggered.connect(self._show_message_platform)
        toolbar.addAction(self.play_action)
        toolbar.addAction(reset_action)
        toolbar.addAction(step_action)
        toolbar.addSeparator()
        speed_combo = QComboBox()
        speed_combo.setObjectName("ToolbarSpeedCombo")
        for label, value in [
            ("1x", 1),
            ("2x", 2),
            ("4x", 4),
            ("8x", 8),
            ("100x", 100),
        ]:
            speed_combo.addItem(label, value)
        speed_combo.currentIndexChanged.connect(
            lambda: self.map_canvas.set_speed_multiplier(float(speed_combo.currentData()))
        )
        speed_combo.setCurrentIndex(0)  # "1x"
        toolbar.addWidget(speed_combo)

        self.side_action = QAction("BLUE", self)
        self.side_action.triggered.connect(self._toggle_active_side)
        units_action = QAction("战斗单元", self)
        units_action.triggered.connect(self._show_units_dialog)
        self.record_action = QAction("录制", self)
        self.record_action.setCheckable(True)
        self.record_action.toggled.connect(self._set_recording_enabled)
        self.settlement_action = QAction("结算", self)
        self.settlement_action.triggered.connect(
            lambda: self._settle_current_simulation("manual_settlement")
        )
        self.battle_report_action = QAction("战绩", self)
        self.battle_report_action.triggered.connect(self._show_battle_report_dialog)
        toolbar.addAction(self.side_action)
        toolbar.addAction(units_action)
        toolbar.addSeparator()
        toolbar.addAction(message_action)
        toolbar.addAction(debug_action)
        self._style_toolbar_action(toolbar, self.play_action, "PlayToolButton")
        self._style_toolbar_action(toolbar, step_action, "ResetToolButton")
        self._style_toolbar_action(toolbar, reset_action, "ResetToolButton")
        self._style_toolbar_action(toolbar, units_action, "UnitsToolButton")
        self._style_toolbar_action(toolbar, message_action, "MessageToolButton")
        self._style_toolbar_action(toolbar, debug_action, "DebugToolButton")
        self.side_tool_button = toolbar.widgetForAction(self.side_action)
        self._build_replay_toolbar()
        self._sync_side_buttons()

    def _build_replay_toolbar(self) -> None:
        self.addToolBarBreak(Qt.TopToolBarArea)
        replay_toolbar = self.addToolBar("回放战绩")
        self.record_toggle_button = RecordingSwitchButton(replay_toolbar)
        self.record_toggle_button.toggled.connect(self._set_recording_enabled)
        replay_toolbar.addWidget(self.record_toggle_button)
        replay_toolbar.addAction(self.settlement_action)
        replay_toolbar.addAction(self.battle_report_action)
        self._style_toolbar_action(replay_toolbar, self.settlement_action, "ReplayToolButton")
        self._style_toolbar_action(replay_toolbar, self.battle_report_action, "ReplayToolButton")

    @staticmethod
    def _style_toolbar_action(toolbar, action: QAction, object_name: str) -> None:
        widget = toolbar.widgetForAction(action)
        if widget is not None:
            widget.setObjectName(object_name)

    def _build_control_overlay(self) -> None:
        register_main_control_pages(self, self.control_overlay)
        self.control_overlay.show_menu()
        self.control_overlay.show()
        self.overlay_manager.raise_overlay("control_menu")

    def _build_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("PanelCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("PanelTitle")
        layout.addWidget(title_label)
        return card, layout

    def _build_map_card(self) -> QFrame:
        card, layout = self._build_card("离线地图")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        entries = [
            ("中心", f"{self.map_document.center.lon:.4f}, {self.map_document.center.lat:.4f}"),
            ("范围", f"{self.map_document.bounds[0]:.1f}~{self.map_document.bounds[2]:.1f}E"),
            ("缩放", f"{self.map_document.min_zoom:g} - {self.map_document.max_zoom:g}"),
            ("瓦片", "已准备" if self.map_canvas.tile_store.has_any_tiles() else "未下载，使用矢量兜底"),
        ]
        for row, (caption, value) in enumerate(entries):
            caption_label = QLabel(caption)
            caption_label.setObjectName("CaptionLabel")
            value_label = QLabel(value)
            value_label.setObjectName("ValueLabel")
            value_label.setWordWrap(True)
            grid.addWidget(caption_label, row, 0)
            grid.addWidget(value_label, row, 1)
        layout.addLayout(grid)
        return card

    def _build_display_card(self) -> QFrame:
        card, layout = self._build_card("显示控制")

        self.perspective_combo = QComboBox()
        self.perspective_combo.addItem("上帝视角", "god")
        self.perspective_combo.addItem("蓝方视角", "blue")
        self.perspective_combo.addItem("红方视角", "red")
        self.perspective_combo.currentIndexChanged.connect(self._handle_perspective_selected)
        layout.addWidget(self.perspective_combo)

        self.radar_ranges_checkbox = QCheckBox("选中单位雷达范围圈")
        self.radar_ranges_checkbox.setChecked(self.map_canvas.show_radar_ranges)
        self.radar_ranges_checkbox.toggled.connect(self.map_canvas.set_radar_ranges_visible)
        layout.addWidget(self.radar_ranges_checkbox)

        self.radar_animation_checkbox = QCheckBox("显示雷达动态效果")
        self.radar_animation_checkbox.setChecked(self.map_canvas.show_radar_animation)
        self.radar_animation_checkbox.toggled.connect(self.map_canvas.set_radar_animation_visible)
        layout.addWidget(self.radar_animation_checkbox)

        self.communications_overlay_checkbox = QCheckBox("显示通信态势共享")
        self.communications_overlay_checkbox.setChecked(self.map_canvas.show_communications_overlay)
        self.communications_overlay_checkbox.toggled.connect(
            self.map_canvas.set_communications_overlay_visible
        )
        layout.addWidget(self.communications_overlay_checkbox)

        hint = QLabel("这里只恢复常用显示开关，图层细分仍在代码里统一管理。")
        hint.setObjectName("CaptionLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _build_units_table(self) -> QTableWidget:
        headers = [
            "序号",
            "状态",
            "阵营",
            "类型",
            "单位ID",
            "名称",
            "路线",
            "运动方式",
            "作战半径",
            "探测距离",
            "武器数量",
            "速度",
            "所属任务",
        ]
        self.units_table = QTableWidget(0, len(headers))
        self.units_table.setHorizontalHeaderLabels(headers)
        self.units_table.verticalHeader().setVisible(False)
        self.units_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.units_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.units_table.setAlternatingRowColors(True)
        self._refresh_units_table()
        return self.units_table

    def _build_mission_view(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        left_column = QVBoxLayout()
        left_column.setSpacing(8)
        mission_list_caption = QLabel("任务列表")
        mission_list_caption.setObjectName("CaptionLabel")
        left_column.addWidget(mission_list_caption)

        self.mission_list = QListWidget()
        self.mission_list.setObjectName("MissionList")
        self.mission_list.setMinimumWidth(280)
        self.mission_list.currentRowChanged.connect(self._handle_mission_selection_changed)
        left_column.addWidget(self.mission_list, 1)
        layout.addLayout(left_column, 2)

        right_column = QVBoxLayout()
        right_column.setSpacing(10)

        self.mission_summary_label = QLabel("请选择任务查看详情")
        self.mission_summary_label.setObjectName("ValueLabel")
        self.mission_summary_label.setWordWrap(True)
        right_column.addWidget(self.mission_summary_label)

        participants_caption = QLabel("参与单位")
        participants_caption.setObjectName("CaptionLabel")
        right_column.addWidget(participants_caption)

        self.mission_units_list = QListWidget()
        self.mission_units_list.setObjectName("MissionUnitsList")
        self.mission_units_list.setMinimumHeight(140)
        right_column.addWidget(self.mission_units_list, 1)

        self.mission_target_info_label = QLabel("")
        self.mission_target_info_label.setObjectName("ValueLabel")
        self.mission_target_info_label.setWordWrap(True)
        self.mission_target_info_label.setVisible(False)
        right_column.addWidget(self.mission_target_info_label)

        layout.addLayout(right_column, 3)
        self._refresh_mission_panel()
        return panel

    def _refresh_units_dialog(self) -> None:
        self._refresh_units_table()
        self._refresh_mission_panel()

    def _refresh_units_table(self) -> None:
        if not hasattr(self, "units_table"):
            return
        visible_units = self.map_canvas.visible_units()
        visible_tracks = [] if self.map_canvas.is_god_perspective() else self.map_canvas.visible_enemy_tracks()
        self.units_table.setRowCount(len(visible_units) + len(visible_tracks))
        for row, unit in enumerate(visible_units):
            values = [
                str(row + 1),
                "存活" if unit.alive else "毁伤",
                self._unit_side_label(unit.side),
                self._unit_type_label(unit),
                unit.unit_id,
                unit.name,
                self._route_label(unit),
                self._motion_label(unit.motion),
                f"{unit.range_nm:g} 海里",
                f"{unit.detection_range_nm:g} 海里",
                str(sum(weapon.current_quantity for weapon in unit.weapons)),
                f"{unit.speed:g} 节",
                self._mission_name_for_unit(unit.unit_id) or "暂无",
            ]
            for column, value in enumerate(values):
                self.units_table.setItem(row, column, QTableWidgetItem(value))
        base_row = len(visible_units)
        for offset, track in enumerate(visible_tracks):
            row = base_row + offset
            confidence = track.decayed_confidence(self.map_canvas._last_combat_step_time)
            values = [
                str(row + 1),
                "陈旧接触" if track.is_stale(self.map_canvas._last_combat_step_time) else "当前接触",
                "敌方",
                "接触",
                track.target_id,
                f"Contact {track.target_id}",
                "未知",
                "未知",
                "未知",
                f"confidence {confidence:.2f}",
                "未知",
                "未知",
                f"source {track.source_unit_id}",
            ]
            for column, value in enumerate(values):
                self.units_table.setItem(row, column, QTableWidgetItem(value))
        self.units_table.resizeColumnsToContents()

    def _clear_units_dialog_state(self) -> None:
        for attribute in [
            "units_table",
            "mission_list",
            "mission_summary_label",
            "mission_units_list",
            "mission_target_info_label",
        ]:
            if hasattr(self, attribute):
                delattr(self, attribute)

    def _build_json_card(self) -> QFrame:
        card, layout = self._build_card("JSON 场景")
        self.json_path_label = QLabel(str(self.scenario_path))
        self.json_path_label.setObjectName("ValueLabel")
        self.json_path_label.setWordWrap(True)
        layout.addWidget(self.json_path_label)

        row = QHBoxLayout()
        choose_button = QPushButton("选择 JSON")
        choose_button.setObjectName("GhostButton")
        choose_button.clicked.connect(self._choose_json)
        reload_button = QPushButton("重新读取")
        reload_button.setObjectName("WarmButton")
        reload_button.clicked.connect(self._reload_json)
        row.addWidget(choose_button)
        row.addWidget(reload_button)
        layout.addLayout(row)
        save_row = QHBoxLayout()
        save_button = QPushButton("保存当前场景")
        save_button.setObjectName("WarmButton")
        save_button.clicked.connect(self._save_json)
        save_as_button = QPushButton("另存为 JSON")
        save_as_button.setObjectName("GhostButton")
        save_as_button.clicked.connect(self._save_json_as)
        save_row.addWidget(save_button)
        save_row.addWidget(save_as_button)
        layout.addLayout(save_row)
        return card

    def _build_new_unit_card(self) -> QFrame:
        card, layout = self._build_card("新增单位")
        default_position = self._new_unit_position or self.map_canvas.center
        position_label = QLabel(
            f"当前创建位置: {default_position.lon:.5f}, {default_position.lat:.5f}"
        )
        position_label.setObjectName("ValueLabel")
        position_label.setWordWrap(True)
        layout.addWidget(position_label)

        side = self.map_canvas.perspective_side() or self.active_side
        side_label = QLabel(f"默认阵营: {self._unit_side_label(side)}")
        side_label.setObjectName("CaptionLabel")
        layout.addWidget(side_label)

        pick_row = QHBoxLayout()
        pick_button = QPushButton("在地图上选择位置")
        pick_button.setObjectName("GhostButton")
        pick_button.clicked.connect(self._begin_new_unit_position_pick)
        center_button = QPushButton("使用当前地图中心")
        center_button.setObjectName("GhostButton")
        center_button.clicked.connect(self._use_map_center_for_new_unit)
        pick_row.addWidget(pick_button)
        pick_row.addWidget(center_button)
        layout.addLayout(pick_row)

        add_unit_button = QPushButton("打开新增单位")
        add_unit_button.setObjectName("WarmButton")
        add_unit_button.clicked.connect(self._add_default_unit)
        layout.addWidget(add_unit_button)

        hint = QLabel("先在地图上点选位置，再打开新增单位。新增前会检查部署位置是否合法。")
        hint.setObjectName("CaptionLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _make_coord_input(self, value: float, minimum: float, maximum: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(6)
        box.setRange(minimum, maximum)
        box.setSingleStep(0.01)
        box.setValue(value)
        return box

    def _build_route_card(self) -> QFrame:
        card, layout = self._build_card("路线设置")
        self.route_side_combo = QComboBox()
        self.route_side_combo.addItems(["BLUE", "RED"])
        self.route_side_combo.currentTextChanged.connect(
            lambda text: self._set_active_side(text.lower())
        )
        layout.addWidget(self.route_side_combo)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.start_lon_input = self._make_coord_input(119.2, 117.0, 124.5)
        self.start_lat_input = self._make_coord_input(24.7, 20.0, 27.0)
        self.end_lon_input = self._make_coord_input(121.3, 117.0, 124.5)
        self.end_lat_input = self._make_coord_input(23.5, 20.0, 27.0)
        for row, (text, widget) in enumerate(
            [
                ("起点经度", self.start_lon_input),
                ("起点纬度", self.start_lat_input),
                ("终点经度", self.end_lon_input),
                ("终点纬度", self.end_lat_input),
            ]
        ):
            label = QLabel(text)
            label.setObjectName("CaptionLabel")
            grid.addWidget(label, row, 0)
            grid.addWidget(widget, row, 1)
        layout.addLayout(grid)

        apply_button = QPushButton("生成当前方路线")
        apply_button.setObjectName("WarmButton")
        apply_button.clicked.connect(self._apply_route)
        layout.addWidget(apply_button)
        hint = QLabel("也可以在地图上右键设置起点、途经点、终点。")
        hint.setObjectName("CaptionLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _build_simulation_card(self) -> QFrame:
        card, layout = self._build_card("播放控制")
        value = QLabel("播放、复位和倍率已移到顶部工具栏。")
        value.setObjectName("ValueLabel")
        value.setWordWrap(True)
        layout.addWidget(value)
        return card

    def _build_mission_control_card(self) -> QFrame:
        card, layout = self._build_card("任务查看")
        mission_list = QListWidget()
        mission_list.setObjectName("MissionControlList")
        visible_missions = [mission for mission in self.scenario.missions if self._mission_visible_for_current_view(mission)]
        if not visible_missions:
            mission_list.addItem("当前视角暂无可见任务")
        for mission in visible_missions:
            status = "激活" if mission.active else "停用"
            mission_type = self._mission_type_label(mission)
            item = QListWidgetItem(f"{mission_type}  [{status}]  {mission.name}")
            item.setData(Qt.UserRole, mission.mission_id)
            mission_list.addItem(item)
        mission_list.itemClicked.connect(lambda item: self._focus_mission(item.data(Qt.UserRole)))
        layout.addWidget(mission_list, 1)

        refresh_button = QPushButton("刷新任务")
        refresh_button.setObjectName("GhostButton")
        refresh_button.clicked.connect(lambda: self._rebuild_control_page("missions"))
        layout.addWidget(refresh_button)
        return card

    def _build_combat_log_control_card(self) -> QFrame:
        card, layout = self._build_card("日志控制")
        summary = QLabel(
            f"日志条数: {len(self.map_canvas.combat_controller.combat_log)}\n"
            f"未读事件: {self._combat_log_unread_count}"
        )
        summary.setObjectName("ValueLabel")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        row = QHBoxLayout()
        show_button = QPushButton("显示日志")
        show_button.setObjectName("WarmButton")
        show_button.clicked.connect(self._restore_combat_log_overlay)
        minimize_button = QPushButton("缩小日志")
        minimize_button.setObjectName("GhostButton")
        minimize_button.clicked.connect(self._minimize_combat_log_overlay)
        row.addWidget(show_button)
        row.addWidget(minimize_button)
        layout.addLayout(row)

        clear_button = QPushButton("清除未读")
        clear_button.setObjectName("GhostButton")
        clear_button.clicked.connect(self._mark_combat_log_seen)
        layout.addWidget(clear_button)

        export_button = QPushButton("导出日志")
        export_button.setObjectName("GhostButton")
        export_button.clicked.connect(self._export_combat_log)
        layout.addWidget(export_button)
        return card

    def _handle_perspective_selected(self) -> None:
        if not hasattr(self, "perspective_combo"):
            return
        perspective = self.perspective_combo.currentData()
        self.map_canvas.set_perspective(str(perspective))

    def _handle_map_perspective_changed(self, perspective: str) -> None:
        if hasattr(self, "perspective_combo"):
            index = self.perspective_combo.findData(perspective)
            if index >= 0 and self.perspective_combo.currentIndex() != index:
                self.perspective_combo.blockSignals(True)
                self.perspective_combo.setCurrentIndex(index)
                self.perspective_combo.blockSignals(False)
        self._refresh_visible_unit_popup()
        self._refresh_units_dialog()
        self._refresh_combat_log()
        self._update_status_counts()
        if (side := self.map_canvas.perspective_side()) is not None:
            self._set_active_side(side)
        self.statusBar().showMessage(f"已切换到 {self.map_canvas.perspective_label()}", 2000)

    def _refresh_mission_panel(self) -> None:
        if not hasattr(self, "mission_list"):
            return
        selected_mission_id = self._selected_mission_id()
        self.mission_list.blockSignals(True)
        self.mission_list.clear()
        selected_row = -1
        visible_missions = [mission for mission in self.scenario.missions if self._mission_visible_for_current_view(mission)]
        for index, mission in enumerate(visible_missions):
            status = "激活" if mission.active else "停用"
            mission_type = self._mission_type_label(mission)
            item = QListWidgetItem(f"{mission_type}  [{status}]  {mission.name}")
            item.setData(Qt.UserRole, mission.mission_id)
            self.mission_list.addItem(item)
            if mission.mission_id == selected_mission_id:
                selected_row = index
        self.mission_list.blockSignals(False)

        if self.mission_list.count() == 0:
            self._clear_mission_view()
            return

        if selected_row < 0:
            selected_row = 0
        self.mission_list.setCurrentRow(selected_row)
        self._handle_mission_selection_changed(selected_row)

    def _selected_mission_id(self) -> str | None:
        if not hasattr(self, "mission_list"):
            return None
        item = self.mission_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _selected_mission(self):
        mission_id = self._selected_mission_id()
        if mission_id is None:
            return None
        return next(
            (
                mission
                for mission in self.scenario.missions
                if mission.mission_id == mission_id and self._mission_visible_for_current_view(mission)
            ),
            None,
        )

    def _clear_mission_view(self) -> None:
        if not hasattr(self, "mission_summary_label"):
            return
        self.mission_summary_label.setText("请选择任务查看详情")
        self.mission_target_info_label.setText("")
        self.mission_target_info_label.setVisible(False)
        self._populate_mission_units_list(None)

    def _handle_mission_selection_changed(self, _: int) -> None:
        mission = self._selected_mission()
        if mission is None:
            self._clear_mission_view()
            return
        self._refresh_mission_details(mission)

    def _refresh_mission_details(self, mission) -> None:
        if mission is None:
            self._clear_mission_view()
            return
        mission_type = self._mission_type_label(mission)
        status = "激活" if mission.active else "停用"
        self.mission_summary_label.setText(
            f"{mission.name}\n类型：{mission_type}\n状态：{status}\n参与单位：{len(mission.assigned_unit_ids)}"
        )
        self._populate_mission_units_list(mission)
        target_info = self._mission_target_info_text(mission)
        self.mission_target_info_label.setText(target_info)
        self.mission_target_info_label.setVisible(bool(target_info))

    def _populate_mission_units_list(self, mission) -> None:
        self.mission_units_list.clear()
        if mission is None:
            return
        selected_ids = set(mission.assigned_unit_ids)
        for unit in self.map_canvas.visible_units():
            if unit.unit_id not in selected_ids:
                continue
            item = QListWidgetItem(self._format_unit_summary(unit))
            item.setData(Qt.UserRole, unit.unit_id)
            self.mission_units_list.addItem(item)

    def _mission_target_info_text(self, mission) -> str:
        if isinstance(mission, StrikeMission):
            targets = [unit for unit in self.scenario.units if unit.unit_id in mission.assigned_target_ids]
            if not targets:
                return "当前打击任务没有找到有效目标。"
            lines = ["目标信息："]
            for unit in targets:
                if self.map_canvas.is_god_perspective() or unit.side == self.map_canvas.perspective_side():
                    lines.append(self._format_unit_summary(unit))
                elif self.map_canvas.contact_track_for_unit(unit.unit_id) is not None:
                    lines.append(f"敌方接触 Contact {unit.unit_id}")
                else:
                    lines.append(f"未探测目标 {unit.unit_id}")
            return "\n".join(lines)
        return ""

    def _mission_visible_for_current_view(self, mission) -> bool:
        side = self.map_canvas.perspective_side()
        if side is None:
            return True
        return any(
            (unit := self.map_canvas.unit_by_id(unit_id)) is not None and unit.side == side
            for unit_id in getattr(mission, "assigned_unit_ids", [])
        )

    @staticmethod
    def _format_unit_summary(unit) -> str:
        status = "存活" if unit.alive else "毁伤"
        type_label = {
            "aircraft": "飞机",
            "ship": "舰艇",
            "facility": "设施",
            "airbase": "机场",
            "ground_vehicle": "地面车辆",
        }.get(unit.unit_type, unit.unit_type)
        side_label = MainWindow._unit_side_label(unit.side)
        return f"{side_label} {unit.name}（{type_label}，{status}）"

    @staticmethod
    def _unit_side_label(side: str) -> str:
        return {"blue": "蓝方", "red": "红方"}.get(side, side.upper())

    @staticmethod
    def _motion_label(motion: str) -> str:
        return {
            "route_loop": "循环航线",
            "route_once": "单程航线",
            "route_pingpong": "往返航线",
            "stationary": "静止",
            "dynamic": "动态航线",
        }.get((motion or "").lower(), motion or "未知")

    @staticmethod
    def _mission_type_label(mission) -> str:
        if isinstance(mission, PatrolMission):
            return "巡逻任务"
        if isinstance(mission, StrikeMission):
            return "打击任务"
        return "任务"

    @staticmethod
    def _unit_type_label(unit) -> str:
        class_name = getattr(unit, "class_name", "") or ""
        type_label = {
            "aircraft": "飞机",
            "ship": "舰艇",
            "facility": "设施",
            "airbase": "机场",
        }.get(unit.unit_type, unit.unit_type)
        if class_name:
            return f"{type_label} / {class_name}"
        return type_label

    @staticmethod
    def _route_label(unit) -> str:
        if unit.route_id:
            return unit.route_id
        if getattr(unit, "motion", "") == "dynamic":
            return "动态生成"
        return "内置航线"

    def _toggle_playing(self) -> None:
        if self.map_canvas.clock.is_finished:
            self.map_canvas.clock.reset()
            self.map_canvas._smooth_time = self.map_canvas.clock.current_time
        was_playing = self.map_canvas.playing
        self.map_canvas.set_playing(not was_playing)
        if was_playing:
            self.play_action.setText("▶")
            self.statusBar().showMessage("仿真已暂停", 1500)
        else:
            self.play_action.setText("⏸")
            self.statusBar().showMessage("仿真运行中", 1500)

    def _step_forward(self) -> None:
        """Advance exactly 1 simulation second (Panopticon-style step)."""
        if self.map_canvas.playing:
            self.map_canvas.set_playing(False)
            self.play_action.setText("▶")
        self.map_canvas.step_simulation(1)
        self.statusBar().showMessage("单步推进 1 秒", 1000)

    def _reset_replay_recorder(self) -> None:
        self._replay_recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
        self.map_canvas.set_replay_recorder(self._replay_recorder)
        self._active_replay_id = None

    def _set_recording_enabled(self, enabled: bool) -> None:
        self._recording_enabled = bool(enabled)
        if self.record_action is not None and self.record_action.isChecked() != self._recording_enabled:
            self.record_action.blockSignals(True)
            self.record_action.setChecked(self._recording_enabled)
            self.record_action.blockSignals(False)
        if self.record_toggle_button is not None and self.record_toggle_button.isChecked() != self._recording_enabled:
            self.record_toggle_button.blockSignals(True)
            self.record_toggle_button.setChecked(self._recording_enabled)
            self.record_toggle_button.setProperty("recording", self._recording_enabled)
            self.record_toggle_button.update()
            self.record_toggle_button.blockSignals(False)
        if self._recording_enabled:
            self._ensure_recording_session()
            self.statusBar().showMessage("已开启录制", 2000)
            return
        had_active_session = self._replay_recorder.active
        if had_active_session:
            if self._finalize_recorded_run("manual_settlement"):
                self.statusBar().showMessage("已关闭录制并自动结算", 2500)
                return
            self.statusBar().showMessage("已关闭录制，当前没有可结算会话", 2500)
            return
        self._reset_replay_recorder()
        self.statusBar().showMessage("已关闭录制", 1500)

    def _ensure_recording_session(self) -> None:
        if not self._recording_enabled or self._replay_recorder.active:
            return
        replay_id = datetime.now().strftime("replay-%Y%m%d-%H%M%S-%f")
        self._active_replay_id = replay_id
        self._replay_recorder.start(
            replay_id=replay_id,
            scenario_name=self.scenario.name,
            started_at=datetime.now().isoformat(timespec="seconds"),
            initial_state=self.map_canvas.build_replay_state(),
            initial_time=float(self.map_canvas.clock.current_time),
        )

    def _build_replay_final_state(self, state: dict) -> dict:
        alive_by_side: dict[str, int] = {}
        for unit in state.get("units", []):
            side = str(unit.get("side", "unknown"))
            alive_by_side.setdefault(side, 0)
            if bool(unit.get("alive", False)):
                alive_by_side[side] += 1
        return {"alive": alive_by_side}

    def _finalize_recorded_run(self, settlement_reason: str) -> bool:
        if not self._replay_recorder.active:
            return False
        finished_at = datetime.now().isoformat(timespec="seconds")
        final_snapshot_state = self.map_canvas.build_replay_state()
        replay = self._replay_recorder.finish(
            ended_at=finished_at,
            duration_seconds=float(self.map_canvas.clock.current_time),
            final_state=self._build_replay_final_state(final_snapshot_state),
            settlement_reason=settlement_reason,
            final_snapshot_state=final_snapshot_state,
        )
        replay_path = self._replay_storage.save_replay(replay)
        summary = build_battle_report_summary(
            scenario=self.scenario,
            replay_id=replay.replay_id,
            finished_at=finished_at,
            duration_seconds=float(replay.duration_seconds),
            settlement_reason=settlement_reason,
            events=replay.event_stream,
        )
        summary.replay_path = str(replay_path.relative_to(self._replay_storage.replay_dir.parent)).replace("\\", "/")
        self._replay_storage.save_report(summary)
        self._battle_reports_cache = self._replay_storage.list_reports()
        self._reset_replay_recorder()
        if self._recording_enabled and not self.map_canvas.clock.is_finished:
            self._ensure_recording_session()
        self.statusBar().showMessage(f"已生成战绩：{summary.result_label}", 2500)
        return True

    def _settle_current_simulation(self, settlement_reason: str = "manual_settlement") -> None:
        if not self._recording_enabled:
            self.statusBar().showMessage("请先开启录制，再进行结算", 2500)
            return
        self._ensure_recording_session()
        if not self._finalize_recorded_run(settlement_reason):
            self.statusBar().showMessage("当前没有可结算的录制会话", 2500)

    def _build_battle_report_dialog(self) -> BattleReportDialog:
        return BattleReportDialog(
            self._battle_reports_cache,
            self._open_replay_from_report,
            self._delete_battle_report,
            self,
        )

    def _show_battle_report_dialog(self) -> None:
        self._battle_reports_cache = self._replay_storage.list_reports()
        if not self._battle_reports_cache:
            self.statusBar().showMessage("暂无战绩记录", 2000)
            return
        dialog = self._build_battle_report_dialog()
        dialog.exec_()

    def _open_replay_from_report(self, report) -> None:
        if not report.has_replay:
            self.statusBar().showMessage("该战绩没有可用回放", 2000)
            return
        replay = self._replay_storage.load_replay(report.replay_id)
        dialog = ReplayViewerDialog(replay, self)
        dialog.exec_()

    def _delete_battle_report(self, report, delete_replay: bool) -> list:
        if delete_replay:
            self._replay_storage.delete_report_and_replay(report.report_id, report.replay_id)
        else:
            self._replay_storage.delete_report_only(report.report_id)
        self._battle_reports_cache = self._replay_storage.list_reports()
        self.statusBar().showMessage("已更新战绩记录", 2000)
        return self._battle_reports_cache

    def _set_active_side(self, side: str) -> None:
        if side not in {"blue", "red"}:
            return
        self.active_side = side
        if hasattr(self, "route_side_combo"):
            index = 0 if side == "blue" else 1
            if self.route_side_combo.currentIndex() != index:
                self.route_side_combo.setCurrentIndex(index)
        self._sync_side_buttons()
        self.statusBar().showMessage(f"当前路线设置阵营: {side.upper()}", 1500)

    def _toggle_active_side(self) -> None:
        self._set_active_side("red" if self.active_side == "blue" else "blue")

    def _sync_side_buttons(self) -> None:
        if self.side_action is not None:
            self.side_action.setText("BLUE" if self.active_side == "blue" else "RED")
        if hasattr(self, "side_tool_button") and self.side_tool_button is not None:
            self.side_tool_button.setObjectName(
                "BlueSideToolButton" if self.active_side == "blue" else "RedSideToolButton"
            )
            self.side_tool_button.style().unpolish(self.side_tool_button)
            self.side_tool_button.style().polish(self.side_tool_button)
        return

    def _choose_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择场景 JSON",
            str(self.scenario_path.parent),
            "JSON Files (*.json)",
        )
        if not path:
            return
        self.scenario_path = type(self.scenario_path)(path)
        self._reload_json()

    def _reload_json(self) -> None:
        self.scenario = load_scenario(self.scenario_path)
        self.map_canvas.set_scenario(self.scenario)
        self._recording_enabled = False
        if self.record_action is not None:
            self.record_action.blockSignals(True)
            self.record_action.setChecked(False)
            self.record_action.blockSignals(False)
        if self.record_toggle_button is not None:
            self.record_toggle_button.blockSignals(True)
            self.record_toggle_button.setChecked(False)
            self.record_toggle_button.setProperty("recording", False)
            self.record_toggle_button.update()
            self.record_toggle_button.blockSignals(False)
        self._reset_replay_recorder()
        self._control_page_widgets.clear()
        self.control_page_window.hide()
        self._hide_unit_popup()
        if hasattr(self, "json_path_label"):
            self.json_path_label.setText(str(self.scenario_path))
        self._refresh_combat_log()
        self._refresh_units_dialog()
        self._update_status_counts()
        self.statusBar().showMessage(f"已加载场景: {self.scenario.name}", 3000)

    def _save_json(self) -> None:
        save_scenario(self.scenario_path, self.scenario)
        if hasattr(self, "json_path_label"):
            self.json_path_label.setText(str(self.scenario_path))
        self.statusBar().showMessage(f"已保存场景: {self.scenario_path}", 4000)

    def _save_json_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "另存为场景 JSON",
            str(self.scenario_path),
            "JSON Files (*.json)",
        )
        if not path:
            return
        self.scenario_path = type(self.scenario_path)(path)
        save_scenario(self.scenario_path, self.scenario, split_units=False)
        if hasattr(self, "json_path_label"):
            self.json_path_label.setText(str(self.scenario_path))
        self.statusBar().showMessage(f"已另存场景: {self.scenario_path}", 4000)

    def _begin_new_unit_position_pick(self) -> None:
        self._new_unit_pick_armed = True
        self.map_canvas.begin_pick_coordinate()
        self.statusBar().showMessage("请在地图上左键点击新增单位部署位置", 5000)

    def _use_map_center_for_new_unit(self) -> None:
        self._new_unit_pick_armed = False
        self._new_unit_position = self.map_canvas.center
        self._rebuild_control_page("new_unit")
        self.statusBar().showMessage(
            f"新增单位位置已设为地图中心: {self._new_unit_position.lon:.5f}, {self._new_unit_position.lat:.5f}",
            3000,
        )

    def _add_default_unit(self) -> None:
        side = self.map_canvas.perspective_side() or self.active_side
        dialog = NewUnitDialog(self, self._new_unit_position or self.map_canvas.center, side)
        unit = None
        while dialog.exec_() == QDialog.Accepted:
            request = dialog.request()
            candidate = self._new_unit_from_request(request)
            terrain_check = self.terrain_classifier.validate_deployment_for_unit(candidate)
            if not terrain_check.ok:
                self._show_light_warning("部署位置不合法", terrain_check.message)
                continue
            unit = candidate
            break
        if unit is None:
            return
        self.scenario.units.append(unit)
        self.map_canvas.set_scenario(self.scenario)
        self.map_canvas.select_unit(unit.unit_id)
        self._refresh_units_dialog()
        self._update_status_counts()
        self._show_unit_popup(unit.unit_id)
        self.statusBar().showMessage("已新增单位，可在参数卡继续编辑后保存 JSON", 3500)

    def _new_unit_from_request(self, request) -> CombatUnit:
        defaults = get_unit_attributes(request.unit_type, request.class_name)
        max_fuel = float(defaults.get("max_fuel", 10000.0))
        return CombatUnit(
            unit_id=self._unique_unit_id(request.unit_id, request.side),
            name=request.name or request.unit_id,
            side=request.side,
            unit_type=request.unit_type,
            route=UnitRoute([]),
            route_id="",
            motion="stationary",
            position=request.position,
            speed=float(defaults.get("speed", 0.0)),
            range_nm=float(defaults.get("range_nm", defaults.get("range", 5.0))),
            altitude_ft=0.0,
            detection_range_nm=float(defaults.get("detection_range_nm", 50.0)),
            weapons=self._initial_weapons_for_new_unit(request.weapons),
            current_fuel=max_fuel,
            max_fuel=max_fuel,
            fuel_rate=float(defaults.get("fuel_rate", 1.0)),
            class_name=request.class_name,
            radar_on=bool(defaults.get("radar_on", True)),
            rcs=float(defaults.get("rcs", 1.0)),
            jammer_power=float(defaults.get("jammer_power", 0.0)),
            jammer_range_nm=float(defaults.get("jammer_range_nm", 0.0)),
            ew_resistance=float(defaults.get("ew_resistance", 0.0)),
            comms_on=bool(defaults.get("comms_on", True)),
            comms_range_nm=float(defaults.get("comms_range_nm", 0.0)),
            datalink=bool(defaults.get("datalink", True)),
            command_node=bool(defaults.get("command_node", False)),
            comms_power=float(defaults.get("comms_power", 1.0)),
            comms_resistance=float(defaults.get("comms_resistance", 0.0)),
            contact_share_delay_s=float(defaults.get("contact_share_delay_s", 0.0)),
        )

    def _unique_unit_id(self, requested_id: str, side: str) -> str:
        existing_ids = {unit.unit_id for unit in self.scenario.units}
        base_id = requested_id.strip() or f"{side}-unit"
        if base_id not in existing_ids:
            return base_id
        index = 1
        while True:
            candidate = f"{base_id}-{index:02d}"
            if candidate not in existing_ids:
                return candidate
            index += 1

    def _initial_weapons_for_new_unit(self, weapon_requests) -> list[WeaponTemplate]:
        weapons: list[WeaponTemplate] = []
        for weapon_request in weapon_requests:
            weapon_class = str(getattr(weapon_request, "weapon_class", ""))
            quantity = int(getattr(weapon_request, "quantity", 0))
            if not weapon_class or quantity <= 0:
                continue
            defaults = get_weapon_attributes(weapon_class)
            weapons.append(
                WeaponTemplate(
                    weapon_class=weapon_class,
                    name=str(defaults.get("name", weapon_class)),
                    speed=float(defaults.get("speed", 0.0)),
                    range_nm=float(defaults.get("range_nm", 0.0)),
                    lethality=float(defaults.get("lethality", 0.0)),
                    max_quantity=quantity,
                    current_quantity=quantity,
                )
            )
        return weapons

    def _show_light_warning(self, title: str, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(QMessageBox.Ok)
        box.setStyleSheet(
            """
            QMessageBox {
                background: #ffffff;
                color: #111827;
            }
            QMessageBox QLabel {
                color: #111827;
                font-size: 13px;
                font-weight: 600;
            }
            QMessageBox QPushButton {
                background: #10b981;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                min-width: 72px;
                min-height: 30px;
                padding: 6px 12px;
                font-weight: 800;
            }
            QMessageBox QPushButton:hover {
                background: #059669;
            }
            """
        )
        box.exec_()

    def _apply_route(self) -> None:
        side = self.route_side_combo.currentText().lower()
        points = [
            LonLat(self.start_lon_input.value(), self.start_lat_input.value()),
            LonLat(
                (self.start_lon_input.value() + self.end_lon_input.value()) / 2.0,
                (self.start_lat_input.value() + self.end_lat_input.value()) / 2.0,
            ),
            LonLat(self.end_lon_input.value(), self.end_lat_input.value()),
        ]
        self._apply_route_points(side, points, f"{side.upper()} 手动路线")

    def _apply_draft_route(self, side: str) -> None:
        draft = self.route_drafts[side]
        points: list[LonLat] = []
        start = draft.get("start")
        end = draft.get("end")
        waypoints = draft.get("waypoints", [])
        if isinstance(start, LonLat):
            points.append(start)
        if isinstance(waypoints, list):
            points.extend(point for point in waypoints if isinstance(point, LonLat))
        if isinstance(end, LonLat):
            points.append(end)
        if len(points) < 2:
            self.statusBar().showMessage("请先设置起点和终点", 3000)
            return
        self._apply_route_points(side, points, f"{side.upper()} 右键路线")
        self.map_canvas.set_route_drafts(self.route_drafts)
        self.statusBar().showMessage(f"已应用 {side.upper()} 右键路线", 3000)

    def _apply_route_points(self, side: str, points: list[LonLat], name: str) -> None:
        perspective_side = self.map_canvas.perspective_side()
        if perspective_side is not None and side != perspective_side:
            self.statusBar().showMessage("当前视角只能修改本方路线", 3000)
            return
        for unit in self.scenario.units:
            if unit.side != side:
                continue
            check = self.terrain_classifier.validate_route_for_unit(unit, points)
            if not check.ok:
                self.statusBar().showMessage(check.message, 5000)
                return
        route_id = next_route_id(self.layer_document, side)
        route = UnitRoute(points)
        upsert_route(
            self.layer_document,
            RouteLayerItem(
                route_id=route_id,
                name=name,
                side=side,
                points=points,
                visible=True,
            ),
        )
        save_layer_document(self.layer_document, self.layers_path)
        for unit in self.scenario.units:
            if unit.side == side:
                unit.route_id = route_id
                unit.route = route
        self.map_canvas.set_layer_document(self.layer_document)
        self.map_canvas.set_scenario(self.scenario)
        self._hide_unit_popup()
        self._refresh_units_dialog()
        self.statusBar().showMessage(f"已更新 {side.upper()} 路线图层: {name}", 3000)

    def _show_unit_popup(self, unit_id: str) -> None:
        track = self.map_canvas.contact_track_for_unit(unit_id)
        unit = self.map_canvas.visible_unit_by_id(unit_id)
        if track is None and (unit is None or not unit.alive):
            self._hide_unit_popup()
            return
        self._refresh_unit_popup(unit_id)
        self._position_unit_popup_at_map_right()
        self.unit_info_popup.show()
        self.overlay_manager.raise_overlay("unit_info")

    def _hide_unit_popup(self) -> None:
        self.unit_info_popup.hide()
        self.map_canvas.clear_selected_unit()

    def _hide_unit_popup_keep_selection(self) -> None:
        self.unit_info_popup.hide()

    def _handle_unit_left_click(self, unit_id: str) -> None:
        if self.map_canvas.selected_unit_id() != unit_id:
            self.map_canvas.select_unit(unit_id)
        self._show_unit_popup(unit_id)

    def _refresh_visible_unit_popup(self) -> None:
        if not self.unit_info_popup.isVisible():
            return
        unit_id = self.map_canvas.selected_unit_id()
        if unit_id is None:
            self._hide_unit_popup()
            return
        track = self.map_canvas.contact_track_for_unit(unit_id)
        unit = self.map_canvas.visible_unit_by_id(unit_id)
        if track is None and (unit is None or not unit.alive):
            self._hide_unit_popup()
            return
        self._refresh_unit_popup(unit_id)
        self._position_unit_popup_at_map_right()

    def _refresh_unit_popup(self, unit_id: str) -> None:
        track = self.map_canvas.contact_track_for_unit(unit_id)
        if track is not None:
            self.unit_info_popup.update_contact_data(track, self.map_canvas._last_combat_step_time)
            return
        unit = self.map_canvas.visible_unit_by_id(unit_id)
        if unit is None or not unit.alive:
            self._hide_unit_popup()
            return
        self.unit_info_popup.update_data(
            unit,
            self._mission_name_for_unit(unit_id),
            self.map_canvas.unit_position(unit_id),
        )

    def _position_unit_popup_at_map_right(self) -> None:
        self.unit_info_popup.adjustSize()
        margin = 8
        popup_width = self.unit_info_popup.width()
        popup_height = self.unit_info_popup.height()
        max_x = max(margin, self.map_canvas.width() - popup_width - margin)
        max_y = max(margin, self.map_canvas.height() - popup_height - margin)
        self.unit_info_popup.move(max_x, margin if margin <= max_y else max_y)

    def _position_all_overlays(self) -> None:
        self.overlay_manager.reposition_all()

    def _position_control_overlay_widgets(self) -> None:
        margin = 12
        canvas_width = max(1, self.map_canvas.width())
        canvas_height = max(1, self.map_canvas.height())
        preferred = self.control_overlay.preferred_size()
        width = min(preferred.width(), max(46, canvas_width - margin * 2))
        height = min(preferred.height(), max(44, canvas_height - margin * 2))
        self.control_overlay.setGeometry(margin, margin, width, height)

        if not self.control_page_window.isHidden():
            page_preferred = self.control_page_window.preferred_size()
            page_width = min(page_preferred.width(), max(220, canvas_width - margin * 2))
            page_height = min(page_preferred.height(), max(160, canvas_height - margin * 2))
            if self.control_page_window.placement() == "below":
                page_x = margin
                page_y = margin + height + 8
                if page_y + page_height + margin > canvas_height:
                    page_y = max(margin, canvas_height - page_height - margin)
            else:
                page_x = margin + width + 8
                if page_x + page_width + margin > canvas_width:
                    page_x = max(margin, canvas_width - page_width - margin)
                page_y = margin
            self.control_page_window.setGeometry(page_x, page_y, page_width, page_height)

        self.control_overlay_marker.adjustSize()
        marker_width = self.control_overlay_marker.width()
        marker_height = self.control_overlay_marker.height()
        marker_x = margin
        marker_y = margin
        if marker_width + margin * 2 > canvas_width:
            marker_x = max(0, canvas_width - marker_width - margin)
        if marker_height + margin * 2 > canvas_height:
            marker_y = max(0, canvas_height - marker_height - margin)
        self.control_overlay_marker.move(marker_x, marker_y)

    def _minimize_control_overlay(self) -> None:
        self._control_overlay_closed = False
        self.control_overlay.hide()
        self.control_page_window.hide()
        self.control_overlay_marker.show()
        self.control_overlay_marker.raise_()
        self._position_control_overlay_widgets()

    def _restore_control_overlay(self) -> None:
        self._control_overlay_closed = False
        self.control_overlay_marker.hide()
        self.control_overlay.show()
        self.overlay_manager.raise_overlay("control_menu")
        self._position_control_overlay_widgets()

    def _close_control_overlay(self) -> None:
        self._control_overlay_closed = True
        self.control_overlay.hide()
        self.control_overlay_marker.hide()
        self.control_page_window.hide()

    def _show_control_page(self, page_id: str) -> None:
        page = self.control_overlay.page(page_id)
        if page is None:
            return
        if page_id not in self._control_page_widgets:
            self._control_page_widgets[page_id] = page.builder()
        self.control_page_window.set_page(
            page.title,
            self._control_page_widgets[page_id],
            page.preferred_size,
            page.placement,
        )
        self.control_page_window.show()
        self.control_page_window.raise_()
        self._position_control_overlay_widgets()

    def _rebuild_control_page(self, page_id: str) -> None:
        page = self.control_overlay.page(page_id)
        if page is None:
            return
        self._control_page_widgets[page_id] = page.builder()
        self._show_control_page(page_id)

    def _focus_mission(self, mission_id: str | None) -> None:
        if not mission_id:
            return
        mission = next((candidate for candidate in self.scenario.missions if candidate.mission_id == mission_id), None)
        if mission is None:
            return
        focus_position = None
        if isinstance(mission, PatrolMission) and mission.assigned_area:
            focus_position = mission.assigned_area[0].position
        if focus_position is None and mission.assigned_unit_ids:
            focus_position = self.map_canvas.unit_position(mission.assigned_unit_ids[0])
        if focus_position is not None:
            self.map_canvas.set_center(focus_position)
            self.statusBar().showMessage(f"已定位任务: {mission.name}", 2000)

    def _position_combat_log_widgets(self) -> None:
        margin = 12
        canvas_width = max(1, self.map_canvas.width())
        canvas_height = max(1, self.map_canvas.height())

        if self._combat_log_maximized:
            width = max(260, canvas_width - margin * 2)
            height = max(180, canvas_height - margin * 2)
            self.combat_log_overlay.setGeometry(margin, margin, width, height)
        else:
            width = min(520, max(320, canvas_width - margin * 2))
            height = min(240, max(170, canvas_height - margin * 2))
            x = margin
            y = max(margin, canvas_height - height - margin)
            self.combat_log_overlay.setGeometry(x, y, width, height)

        self.combat_log_marker.adjustSize()
        marker_width = self.combat_log_marker.width()
        marker_height = self.combat_log_marker.height()
        marker_x = margin
        marker_y = max(margin, canvas_height - marker_height - margin)
        self.combat_log_marker.move(marker_x, marker_y)

    def _minimize_combat_log_overlay(self) -> None:
        self._combat_log_closed = False
        self.combat_log_overlay.hide()
        self.combat_log_marker.show()
        self.combat_log_marker.raise_()
        self._position_combat_log_widgets()
        self._save_user_preferences()

    def _restore_combat_log_overlay(self) -> None:
        self._combat_log_closed = False
        self._combat_log_unread_count = 0
        self._combat_log_seen_event_count = len(self.map_canvas.combat_controller.combat_log)
        self.combat_log_marker.set_count(0)
        self.combat_log_marker.hide()
        self.combat_log_overlay.show()
        self.overlay_manager.raise_overlay("combat_log")
        self._position_combat_log_widgets()
        self._save_user_preferences()

    def _toggle_combat_log_overlay_size(self) -> None:
        self._combat_log_closed = False
        self._combat_log_maximized = not self._combat_log_maximized
        self.combat_log_overlay.set_maximized_state(self._combat_log_maximized)
        self.combat_log_marker.hide()
        self.combat_log_overlay.show()
        self.overlay_manager.raise_overlay("combat_log")
        self._position_combat_log_widgets()
        self._save_user_preferences()

    def _close_combat_log_overlay(self) -> None:
        self._combat_log_closed = True
        self.combat_log_overlay.hide()
        self.combat_log_marker.hide()
        self._save_user_preferences()

    def _mission_name_for_unit(self, unit_id: str) -> str | None:
        for mission in self.scenario.missions:
            if unit_id in mission.assigned_unit_ids:
                return mission.name
        return None

    def _handle_unit_popup_action(self, unit_id: str, action_key: str) -> None:
        unit = self.map_canvas.operable_unit_by_id(unit_id)
        if unit is None:
            self.statusBar().showMessage("当前视角下敌方接触只允许查看", 2000)
            return
        if action_key == "plot_course":
            if self.map_canvas.begin_plot_course(unit_id):
                self.statusBar().showMessage(f"Next left-click sets course for {unit.name}", 5000)
            return
        if action_key == "manual_attack":
            self.unit_info_popup.show_weapons_page()
            weapon_count = sum(weapon.current_quantity for weapon in unit.weapons)
            self.statusBar().showMessage(f"{unit.name} manual attack weapons: {weapon_count}", 3000)
            return
        if action_key == "auto_attack":
            self.statusBar().showMessage("Enemy target selection is not connected yet", 3000)
            return
        if action_key == "return_to_base":
            self.statusBar().showMessage("Return To Base is not connected yet", 3000)
            return
        if action_key == "duplicate":
            copied_unit, placement_warning = self._duplicate_unit(unit)
            self.map_canvas.motion_controller.reset()
            self.map_canvas.select_unit(copied_unit.unit_id)
            self._update_status_counts()
            self._show_unit_popup(copied_unit.unit_id)
            message = f"Duplicated {unit.name} as {copied_unit.name}"
            if placement_warning:
                message = f"{message}; {placement_warning}"
            self.statusBar().showMessage(message, 4000)
            return
        if action_key == "edit_location":
            if self.map_canvas.begin_edit_location(unit_id):
                self.statusBar().showMessage(f"Next left-click moves {unit.name}", 5000)
            return
        self.statusBar().showMessage(f"{action_key} requested for {unit.name}", 3000)

    def _handle_unit_popup_edit(self, unit_id: str, values: dict) -> None:
        unit = self.map_canvas.operable_unit_by_id(unit_id)
        if unit is None:
            self.statusBar().showMessage("当前视角下敌方接触只允许查看", 2000)
            return
        name = str(values.get("name", "")).strip()
        if name:
            unit.name = name
        for field, attr in [
            ("speed", "speed"),
            ("altitude_ft", "altitude_ft"),
            ("range_nm", "range_nm"),
            ("current_fuel", "current_fuel"),
            ("max_fuel", "max_fuel"),
            ("fuel_rate", "fuel_rate"),
            ("detection_range_nm", "detection_range_nm"),
            ("rcs", "rcs"),
            ("jammer_power", "jammer_power"),
            ("jammer_range_nm", "jammer_range_nm"),
            ("ew_resistance", "ew_resistance"),
            ("comms_range_nm", "comms_range_nm"),
            ("comms_power", "comms_power"),
            ("comms_resistance", "comms_resistance"),
        ]:
            if field in values:
                setattr(unit, attr, float(values[field]))
        for field, attr in [
            ("radar_on", "radar_on"),
            ("comms_on", "comms_on"),
            ("datalink", "datalink"),
            ("command_node", "command_node"),
        ]:
            if field in values:
                setattr(unit, attr, bool(values[field]))
        if "weapons" in values and isinstance(values["weapons"], list):
            unit.weapons = [
                WeaponTemplate(
                    weapon_class=str(raw_weapon.get("weapon_class", "")),
                    name=str(raw_weapon.get("name", raw_weapon.get("weapon_class", "Weapon"))),
                    speed=max(0.0, float(raw_weapon.get("speed", 0.0))),
                    range_nm=max(0.0, float(raw_weapon.get("range_nm", 0.0))),
                    lethality=max(0.0, min(1.0, float(raw_weapon.get("lethality", 0.0)))),
                    max_quantity=max(0, int(raw_weapon.get("max_quantity", 0))),
                    current_quantity=max(0, int(raw_weapon.get("current_quantity", 0))),
                )
                for raw_weapon in values["weapons"]
            ]
            for weapon in unit.weapons:
                weapon.current_quantity = min(weapon.current_quantity, weapon.max_quantity)
        self.map_canvas.update()
        self._refresh_unit_popup(unit_id)
        self._refresh_units_dialog()
        self._update_status_counts()
        self.statusBar().showMessage(f"Updated {unit.name}", 2500)

    def _handle_unit_popup_delete(self, unit_id: str) -> None:
        unit = self.map_canvas.operable_unit_by_id(unit_id)
        if unit is None:
            self._hide_unit_popup()
            return
        unit_name = unit.name
        self.scenario.units = [candidate for candidate in self.scenario.units if candidate.unit_id != unit_id]
        self.map_canvas.scenario = self.scenario
        self.map_canvas.combat_controller.scenario = self.scenario
        self.scenario.flying_weapons = [
            weapon for weapon in self.scenario.flying_weapons if weapon.target_id != unit_id
        ]
        for candidate in self.scenario.units:
            if candidate.target_id == unit_id:
                candidate.target_id = ""
        for mission in self.scenario.missions:
            mission.assigned_unit_ids = [
                assigned_id for assigned_id in mission.assigned_unit_ids if assigned_id != unit_id
            ]
            if hasattr(mission, "assigned_target_ids"):
                mission.assigned_target_ids = [
                    target_id for target_id in mission.assigned_target_ids if target_id != unit_id
                ]
        self.map_canvas.motion_controller.reset()
        self.map_canvas.clear_interaction_mode()
        self._hide_unit_popup()
        self.map_canvas.update()
        self._refresh_combat_log()
        self._refresh_units_dialog()
        self._update_status_counts()
        self.statusBar().showMessage(f"Deleted {unit_name}", 3000)

    def _duplicate_unit(self, unit):
        copied_unit = deepcopy(unit)
        existing_ids = {candidate.unit_id for candidate in self.scenario.units}
        existing_names = {candidate.name for candidate in self.scenario.units}
        base_id = f"{unit.unit_id}_copy"
        base_name = f"{unit.name} Copy"
        index = 1
        new_id = base_id
        new_name = base_name
        while new_id in existing_ids or new_name in existing_names:
            index += 1
            new_id = f"{base_id}_{index}"
            new_name = f"{base_name} {index}"
        copied_unit.unit_id = new_id
        copied_unit.name = new_name
        position = self.map_canvas.unit_position(unit.unit_id) or unit.position
        placement_warning = ""
        if position is not None:
            copied_unit.position, placement_warning = self._duplicate_position(copied_unit, position)
            copied_unit.route = UnitRoute([])
            copied_unit.motion = "stationary"
            copied_unit.route_id = ""
        copied_unit.target_id = ""
        self.scenario.units.append(copied_unit)
        return copied_unit, placement_warning

    def _duplicate_position(self, copied_unit, source_position: LonLat) -> tuple[LonLat, str]:
        min_lon, min_lat, max_lon, max_lat = self.map_document.bounds
        offsets = [
            (0.03, 0.03),
            (-0.03, 0.03),
            (0.03, -0.03),
            (-0.03, -0.03),
            (0.05, 0.0),
            (-0.05, 0.0),
            (0.0, 0.05),
            (0.0, -0.05),
        ]
        for lon_offset, lat_offset in offsets:
            candidate = LonLat(
                max(min_lon, min(max_lon, source_position.lon + lon_offset)),
                max(min_lat, min(max_lat, source_position.lat + lat_offset)),
            )
            copied_unit.position = candidate
            if self.terrain_classifier.validate_deployment_for_unit(copied_unit).ok:
                return candidate, ""
        fallback = LonLat(
            max(min_lon, min(max_lon, source_position.lon)),
            max(min_lat, min(max_lat, source_position.lat)),
        )
        copied_unit.position = fallback
        check = self.terrain_classifier.validate_deployment_for_unit(copied_unit)
        if check.ok:
            return fallback, "used original position after terrain checks"
        return fallback, f"used clamped original position; {check.message}"

    def _begin_coordinate_pick(self) -> None:
        self._new_unit_pick_armed = False
        self.map_canvas.begin_pick_coordinate()
        self.statusBar().showMessage("下一次左键点击地图将复制经纬度", 4000)

    def _handle_coordinate_picked(self, lon: float, lat: float) -> None:
        text = f"{lon:.6f}, {lat:.6f}"
        if self._new_unit_pick_armed:
            self._new_unit_pick_armed = False
            self._new_unit_position = LonLat(lon, lat)
            self.coordinate_label.setText(f"经纬度: {text}")
            self._rebuild_control_page("new_unit")
            self.statusBar().showMessage(f"已选择新增单位位置: {text}", 4000)
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.coordinate_label.setText(f"经纬度: {text}")
        self.statusBar().showMessage(f"已复制坐标: {text}", 4000)

    def _sync_map_scrollbars(self) -> None:
        if (
            self._viewport_sync_in_progress
            or self.horizontal_map_scrollbar is None
            or self.vertical_map_scrollbar is None
        ):
            return
        self._viewport_sync_in_progress = True
        try:
            map_left, map_right, map_top, map_bottom = self.map_canvas.map_world_bounds()
            view_left, view_right, view_top, view_bottom = self.map_canvas.viewport_world_rect()

            self._set_scrollbar_state(
                self.horizontal_map_scrollbar,
                content_min=map_left,
                content_max=map_right,
                viewport_min=view_left,
                viewport_max=view_right,
            )
            self._set_scrollbar_state(
                self.vertical_map_scrollbar,
                content_min=map_top,
                content_max=map_bottom,
                viewport_min=view_top,
                viewport_max=view_bottom,
            )
        finally:
            self._viewport_sync_in_progress = False

    @staticmethod
    def _set_scrollbar_state(
        scrollbar: QScrollBar,
        content_min: float,
        content_max: float,
        viewport_min: float,
        viewport_max: float,
    ) -> None:
        content_span = content_max - content_min
        viewport_span = viewport_max - viewport_min
        movable_span = content_span - viewport_span
        if content_span <= 1.0 or movable_span <= 1.0:
            scrollbar.setEnabled(False)
            scrollbar.setRange(0, 0)
            scrollbar.setPageStep(1)
            scrollbar.setSingleStep(1)
            scrollbar.setValue(0)
            return

        scale = 1000.0
        page_step = max(1, int(round(viewport_span * scale)))
        total_range = max(page_step, int(round(content_span * scale)))
        slider_value = max(
            0,
            min(
                total_range - page_step,
                int(round((viewport_min - content_min) * scale)),
            ),
        )
        scrollbar.setEnabled(True)
        scrollbar.setRange(0, total_range - page_step)
        scrollbar.setPageStep(page_step)
        scrollbar.setSingleStep(max(1, int(round(viewport_span * scale * 0.12))))
        scrollbar.setValue(slider_value)

    def _handle_horizontal_scrollbar_changed(self, value: int) -> None:
        if self._viewport_sync_in_progress:
            return
        self._set_center_from_scrollbars(horizontal_value=value)

    def _handle_vertical_scrollbar_changed(self, value: int) -> None:
        if self._viewport_sync_in_progress:
            return
        self._set_center_from_scrollbars(vertical_value=value)

    def _set_center_from_scrollbars(
        self,
        horizontal_value: int | None = None,
        vertical_value: int | None = None,
    ) -> None:
        if self.horizontal_map_scrollbar is None or self.vertical_map_scrollbar is None:
            return
        scale = 1000.0
        map_left, _, map_top, _ = self.map_canvas.map_world_bounds()
        view_left, view_right, view_top, view_bottom = self.map_canvas.viewport_world_rect()
        viewport_width = view_right - view_left
        viewport_height = view_bottom - view_top
        left_world = map_left + (
            float(horizontal_value if horizontal_value is not None else self.horizontal_map_scrollbar.value()) / scale
        )
        top_world = map_top + (
            float(vertical_value if vertical_value is not None else self.vertical_map_scrollbar.value()) / scale
        )
        world_x = left_world + viewport_width / 2.0
        world_y = top_world + viewport_height / 2.0
        self.map_canvas.set_center(world_to_lonlat(ScreenPoint(world_x, world_y), self.map_canvas.zoom))

    def _show_message_platform(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("消息指挥平台")
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        side = self.map_canvas.perspective_side()
        if side is None:
            unit_summary = f"单位数量: {len(self.scenario.units)}\n存活单位: {len(self.map_canvas.combat_controller.get_alive_units())}"
            weapon_summary = f"在飞武器: {len(self.scenario.flying_weapons)}"
        else:
            friendly_units = [unit for unit in self.scenario.units if unit.side == side]
            alive = len([unit for unit in friendly_units if unit.alive])
            contacts = len(self.map_canvas.visible_enemy_tracks())
            unit_summary = f"{side.upper()} 单位: {alive}/{len(friendly_units)}\n已知敌方接触: {contacts}"
            weapon_summary = f"可见在飞武器: {self._visible_flying_weapon_count()}"
        text.setPlainText(
            "消息指挥平台\n"
            f"当前视角: {self.map_canvas.perspective_label()}\n"
            f"当前场景: {self.scenario.name}\n"
            f"{unit_summary}\n"
            f"{weapon_summary}\n"
            "地图模式: 纯 Qt 离线地图\n"
            "前端环境: 未使用\n"
        )
        layout.addWidget(text)
        dialog.exec_()

    def _show_units_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("战斗单元")
        dialog.resize(1120, 680)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget(dialog)
        tabs.addTab(self._build_units_table(), "战斗单元")
        tabs.addTab(self._build_mission_view(), "任务查看")
        layout.addWidget(tabs)
        self._refresh_units_dialog()
        try:
            dialog.exec_()
        finally:
            self._clear_units_dialog_state()

    def _show_debug_log(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Debug 日志")
        dialog.resize(680, 480)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "Qt Frontend V6 Debug\n"
            f"map: {self.map_document.name}\n"
            f"bounds: {self.map_document.bounds}\n"
            f"center: {self.map_canvas.center.lon:.6f}, {self.map_canvas.center.lat:.6f}\n"
            f"zoom: {self.map_canvas.zoom:.2f}\n"
            f"tile_root: {self.map_document.tile_root}\n"
            f"tiles_ready: {self.map_canvas.tile_store.has_any_tiles()}\n"
            f"scenario: {self.scenario_path}\n"
            f"layers: {self.layers_path}\n"
            f"route_count: {len(self.layer_document.routes)}\n"
            f"terrain_checks: {self._terrain_debug_summary()}\n"
        )
        layout.addWidget(text)
        dialog.exec_()

    def _terrain_debug_summary(self) -> str:
        messages: list[str] = []
        for unit in self.scenario.units:
            check = self.terrain_classifier.validate_deployment_for_unit(unit)
            if not check.ok:
                messages.append(check.message)
        return "OK" if not messages else " | ".join(messages)

    def _update_coordinates(self, lon: float, lat: float) -> None:
        self.coordinate_label.setText(f"经纬度: {lon:.6f}, {lat:.6f}")

    def _update_time(self, seconds: float) -> None:
        self.time_label.setText(f"仿真时间: {self.map_canvas.clock.format_time()}")
        self.play_action.setText("⏸" if self.map_canvas.playing else "▶")
        if self.map_canvas.clock.is_finished:
            if self._recording_enabled and self._replay_recorder.active:
                self._finalize_recorded_run("simulation_finished")
            self.statusBar().showMessage("仿真已结束", 1500)
        self._refresh_units_dialog()
        self._update_status_counts()
        self._refresh_visible_unit_popup()

    def _update_status_counts(self) -> None:
        side = self.map_canvas.perspective_side()
        if side is None:
            alive = len([unit for unit in self.scenario.units if unit.alive])
            total = len(self.scenario.units)
            flying = len(self.scenario.flying_weapons)
            self.alive_label.setText(f"存活单位: {alive}/{total}  在飞武器: {flying}")
            return
        friendly_units = [unit for unit in self.scenario.units if unit.side == side]
        alive = len([unit for unit in friendly_units if unit.alive])
        contacts = len(self.map_canvas.visible_enemy_tracks())
        flying = self._visible_flying_weapon_count()
        self.alive_label.setText(f"{side.upper()} 存活: {alive}/{len(friendly_units)}  接触: {contacts}  可见在飞: {flying}")

    def _refresh_combat_log(self) -> None:
        event_count = len(self.map_canvas.combat_controller.combat_log)
        new_count = max(0, event_count - self._combat_log_seen_event_count)
        if new_count:
            if self.combat_log_overlay.isHidden():
                self._combat_log_unread_count += new_count
            else:
                self._combat_log_unread_count = 0
            self._combat_log_seen_event_count = event_count
        entries = self._combat_log_entries()
        self.combat_log_overlay.set_entries(entries)
        self.combat_log_marker.set_count(self._combat_log_unread_count)
        if not self._combat_log_closed and self.combat_log_marker.isHidden():
            self.combat_log_overlay.show()
            self.overlay_manager.raise_overlay("combat_log")
            self._combat_log_unread_count = 0
            self.combat_log_marker.set_count(0)
        self._position_combat_log_widgets()
        self._update_status_counts()

    def _combat_log_entries(self) -> list[tuple[int, str]]:
        indexed_events = [
            (index, event)
            for index, event in enumerate(self.map_canvas.combat_controller.combat_log)
            if self._event_visible_for_current_view(event) and self._event_matches_log_filters(event)
        ][-80:]
        entries: list[tuple[int, str]] = []
        for index, event in reversed(indexed_events):
            minute = int(event.time) // 60
            second = int(event.time) % 60
            category = self._event_type_label(event.event_type)
            entries.append((index, f"{minute:02d}:{second:02d}  [{category}]  {event.message}"))
        return entries

    def _load_user_preferences(self) -> None:
        side_filter = str(self.settings.value("combat_log/side_filter", "all"))
        type_filter = str(self.settings.value("combat_log/type_filter", "all"))
        self.combat_log_overlay.set_filters(side_filter, type_filter)
        self._combat_log_maximized = _settings_bool(self.settings.value("combat_log/maximized", False))
        self._combat_log_closed = _settings_bool(self.settings.value("combat_log/closed", False))
        self.combat_log_overlay.set_maximized_state(self._combat_log_maximized)
        if _settings_bool(self.settings.value("combat_log/minimized", False)):
            self.combat_log_overlay.hide()
            self.combat_log_marker.show()
        elif self._combat_log_closed:
            self.combat_log_overlay.hide()
            self.combat_log_marker.hide()

    def _save_user_preferences(self) -> None:
        self.settings.setValue("combat_log/side_filter", self.combat_log_overlay.side_filter())
        self.settings.setValue("combat_log/type_filter", self.combat_log_overlay.type_filter())
        self.settings.setValue("combat_log/maximized", self._combat_log_maximized)
        self.settings.setValue("combat_log/minimized", self.combat_log_overlay.isHidden() and not self._combat_log_closed)
        self.settings.setValue("combat_log/closed", self._combat_log_closed)

    def _export_combat_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出战斗日志",
            str(self.scenario_path.with_name("combat_log.json")),
            "JSON Files (*.json);;Text Files (*.txt)",
        )
        if not path:
            return
        export_path = type(self.scenario_path)(path)
        indexed_events = [
            (index, event)
            for index, event in enumerate(self.map_canvas.combat_controller.combat_log)
            if self._event_visible_for_current_view(event) and self._event_matches_log_filters(event)
        ]
        if export_path.suffix.lower() == ".txt":
            lines = []
            for _index, event in indexed_events:
                minute = int(event.time) // 60
                second = int(event.time) % 60
                lines.append(f"{minute:02d}:{second:02d} [{self._event_type_label(event.event_type)}] {event.message}")
            export_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        else:
            payload = {
                "scenario": self.scenario.name,
                "perspective": self.map_canvas.perspective_label(),
                "side_filter": self.combat_log_overlay.side_filter(),
                "type_filter": self.combat_log_overlay.type_filter(),
                "events": [self._combat_event_to_dict(index, event) for index, event in indexed_events],
            }
            export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.statusBar().showMessage(f"已导出战斗日志: {export_path}", 3500)

    def _combat_event_to_dict(self, index: int, event) -> dict:
        position = event.position
        return {
            "index": index,
            "time": event.time,
            "event_type": event.event_type,
            "category": self._event_type_label(event.event_type),
            "source_id": event.source_id,
            "target_id": event.target_id,
            "weapon_class": event.weapon_class,
            "message": event.message,
            "position": None if position is None else {"lon": position.lon, "lat": position.lat},
            "extra": deepcopy(getattr(event, "extra", {})),
        }

    def _mark_combat_log_seen(self) -> None:
        self._combat_log_seen_event_count = len(self.map_canvas.combat_controller.combat_log)
        self._combat_log_unread_count = 0
        self.combat_log_marker.set_count(0)
        self.statusBar().showMessage("已清除战斗日志未读计数", 1500)

    def _focus_combat_log_event(self, event_index: int) -> None:
        combat_log = self.map_canvas.combat_controller.combat_log
        if event_index < 0 or event_index >= len(combat_log):
            return
        event = combat_log[event_index]
        focus_position = event.position
        if focus_position is None and event.target_id:
            focus_position = self.map_canvas.unit_position(event.target_id)
        if focus_position is None and event.source_id:
            focus_position = self.map_canvas.unit_position(event.source_id)
        if focus_position is None:
            self.statusBar().showMessage("该日志事件没有可定位坐标", 2000)
            return
        self.map_canvas.set_center(focus_position)
        for unit_id in [event.target_id, event.source_id]:
            if unit_id and self.map_canvas.select_unit(unit_id):
                self._show_unit_popup(unit_id)
                break
        self.statusBar().showMessage(f"已定位日志事件: {self._event_type_label(event.event_type)}", 2000)

    def _event_matches_log_filters(self, event) -> bool:
        side_filter = self.combat_log_overlay.side_filter()
        type_filter = self.combat_log_overlay.type_filter()
        if type_filter != "all" and event.event_type != type_filter:
            return False
        if side_filter == "all":
            return True
        for unit_id in (event.source_id, event.target_id):
            unit = self.map_canvas.unit_by_id(unit_id)
            if unit is not None and unit.side == side_filter:
                return True
        return False

    @staticmethod
    def _event_type_label(event_type: str) -> str:
        return {
            "detected": "探测",
            "shared_contact": "共享",
            "launched": "发射",
            "hit": "命中",
            "unit_destroyed": "击毁",
            "miss": "未命中",
            "expired": "失效",
            "lost_target": "丢失目标",
        }.get(event_type, event_type or "事件")

    def _visible_flying_weapon_count(self) -> int:
        side = self.map_canvas.perspective_side()
        if side is None:
            return len(self.scenario.flying_weapons)
        return sum(
            1
            for weapon in self.scenario.flying_weapons
            if weapon.side == side or self.map_canvas.contact_track_for_unit(weapon.target_id) is not None
        )

    def _event_visible_for_current_view(self, event) -> bool:
        side = self.map_canvas.perspective_side()
        if side is None:
            return True
        for unit_id in (event.source_id, event.target_id):
            unit = self.map_canvas.unit_by_id(unit_id)
            if unit is not None and unit.side == side:
                return True
            if self.map_canvas.contact_track_for_unit(unit_id) is not None:
                return True
        return False


def _settings_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
