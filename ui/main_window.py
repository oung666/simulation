from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QComboBox,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qt_frontend_v6.core.geo import LonLat
from qt_frontend_v6.core.layers import RouteLayerItem, load_layer_document, next_route_id, save_layer_document, upsert_route
from qt_frontend_v6.core.map_document import load_map_document
from qt_frontend_v6.core.paths import get_default_layers_path, get_default_scenario_path, get_map_asset_path
from qt_frontend_v6.core.scenario import UnitRoute, load_scenario
from qt_frontend_v6.core.terrain import TerrainClassifier
from qt_frontend_v6.ui.map_canvas import MapCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MainChrome")
        self.setWindowTitle("战术指挥平台 V6 - 纯 Qt 离线地图")

        self.map_document = load_map_document(get_map_asset_path())
        self.scenario_path = get_default_scenario_path()
        self.layers_path = get_default_layers_path()
        self.scenario = load_scenario(self.scenario_path)
        self.layer_document = load_layer_document(self.layers_path)
        self.terrain_classifier = TerrainClassifier(self.map_document)
        self.map_canvas = MapCanvas(self.map_document, self.scenario, self.layer_document, self)
        self.setCentralWidget(self.map_canvas)
        self.route_drafts: dict[str, dict[str, object]] = {
            "blue": {"start": None, "waypoints": [], "end": None},
            "red": {"start": None, "waypoints": [], "end": None},
        }
        self.active_side = "blue"
        self.side_action: QAction | None = None
        self.map_canvas.set_route_drafts(self.route_drafts)

        self.coordinate_label = QLabel("经纬度: --, --")
        self.time_label = QLabel("仿真时间: 00:00")
        self.statusBar().addWidget(self.coordinate_label)
        self.statusBar().addPermanentWidget(self.time_label)

        self.map_canvas.coordinateHovered.connect(self._update_coordinates)
        self.map_canvas.timeChanged.connect(self._update_time)
        self.map_canvas.mapRightClicked.connect(self._show_route_context_menu)
        self._build_toolbar()
        self._build_control_dock()

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("主控")
        play_action = QAction("▶ / ||", self)
        play_action.triggered.connect(self._toggle_playing)
        reset_action = QAction("复位", self)
        reset_action.triggered.connect(self.map_canvas.reset_view)
        message_action = QAction("消息平台", self)
        message_action.triggered.connect(self._show_message_platform)
        debug_action = QAction("Debug", self)
        debug_action.triggered.connect(self._show_debug_log)
        toolbar.addAction(play_action)
        toolbar.addAction(reset_action)
        toolbar.addSeparator()
        speed_combo = QComboBox()
        speed_combo.setObjectName("ToolbarSpeedCombo")
        for label, value in [
            ("1.5x", 1.5),
            ("2x", 2.0),
            ("3x", 3.0),
            ("4x", 4.0),
            ("10x", 10.0),
            ("50x", 50.0),
            ("100x", 100.0),
        ]:
            speed_combo.addItem(label, value)
        speed_combo.currentIndexChanged.connect(
            lambda: self.map_canvas.set_speed_multiplier(float(speed_combo.currentData()))
        )
        self.map_canvas.set_speed_multiplier(1.5)
        toolbar.addWidget(speed_combo)

        self.side_action = QAction("BLUE", self)
        self.side_action.triggered.connect(self._toggle_active_side)
        units_action = QAction("战斗单元", self)
        units_action.triggered.connect(self._show_units_dialog)
        toolbar.addAction(self.side_action)
        toolbar.addAction(units_action)
        toolbar.addSeparator()
        toolbar.addAction(message_action)
        toolbar.addAction(debug_action)
        self._style_toolbar_action(toolbar, play_action, "PlayToolButton")
        self._style_toolbar_action(toolbar, reset_action, "ResetToolButton")
        self._style_toolbar_action(toolbar, units_action, "UnitsToolButton")
        self._style_toolbar_action(toolbar, message_action, "MessageToolButton")
        self._style_toolbar_action(toolbar, debug_action, "DebugToolButton")
        self.side_tool_button = toolbar.widgetForAction(self.side_action)
        self._sync_side_buttons()

    @staticmethod
    def _style_toolbar_action(toolbar, action: QAction, object_name: str) -> None:
        widget = toolbar.widgetForAction(action)
        if widget is not None:
            widget.setObjectName(object_name)

    def _build_control_dock(self) -> None:
        dock = QDockWidget("仿真控制", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setMinimumWidth(360)
        dock.setMaximumWidth(520)

        scroll = QScrollArea(dock)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        panel = QWidget(scroll)
        panel.setObjectName("DockSurface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(self._build_map_card())
        layout.addWidget(self._build_layer_card())
        layout.addWidget(self._build_json_card())
        layout.addWidget(self._build_route_card())
        layout.addWidget(self._build_simulation_card())
        layout.addStretch(1)

        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

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

    def _build_layer_card(self) -> QFrame:
        card, layout = self._build_card("图层管理")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        entries = [
            ("底图层", "离线瓦片 / 经纬度映射"),
            ("路线层", f"{len(self.layer_document.routes)} 条路线，来自 routes.json"),
            ("单位层", "飞机 / 舰船 / 设施 / 机场"),
            ("范围层", "按单位 range_nm 自动生成"),
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

        self.layers_path_label = QLabel(str(self.layers_path))
        self.layers_path_label.setObjectName("ValueLabel")
        self.layers_path_label.setWordWrap(True)
        layout.addWidget(self.layers_path_label)
        return card

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

    def _toggle_playing(self) -> None:
        self.map_canvas.set_playing(not self.map_canvas.playing)

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
        self.json_path_label.setText(str(self.scenario_path))
        self.statusBar().showMessage(f"已加载场景: {self.scenario.name}", 3000)

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
        self.statusBar().showMessage(f"已更新 {side.upper()} 路线图层: {name}", 3000)

    def _show_route_context_menu(self, lon: float, lat: float) -> None:
        side = self.active_side
        point = LonLat(lon, lat)
        menu = QMenu(self)
        menu.addAction(f"{side.upper()} 设为起点", lambda: self._set_draft_point(side, "start", point))
        menu.addAction(f"{side.upper()} 添加途经点", lambda: self._add_draft_waypoint(side, point))
        menu.addAction(f"{side.upper()} 设为终点", lambda: self._set_draft_point(side, "end", point))
        menu.addSeparator()
        menu.addAction(f"应用 {side.upper()} 路线", lambda: self._apply_draft_route(side))
        menu.addAction(f"清空 {side.upper()} 草稿", lambda: self._clear_draft_route(side))
        menu.exec_(self.cursor().pos())

    def _set_draft_point(self, side: str, key: str, point: LonLat) -> None:
        self.route_drafts[side][key] = point
        self.map_canvas.set_route_drafts(self.route_drafts)
        self.statusBar().showMessage(f"已设置 {side.upper()} {key}: {point.lon:.5f}, {point.lat:.5f}", 3000)

    def _add_draft_waypoint(self, side: str, point: LonLat) -> None:
        waypoints = self.route_drafts[side].setdefault("waypoints", [])
        if isinstance(waypoints, list):
            waypoints.append(point)
        self.map_canvas.set_route_drafts(self.route_drafts)
        self.statusBar().showMessage(f"已添加 {side.upper()} 途经点", 3000)

    def _clear_draft_route(self, side: str) -> None:
        self.route_drafts[side] = {"start": None, "waypoints": [], "end": None}
        self.map_canvas.set_route_drafts(self.route_drafts)
        self.statusBar().showMessage(f"已清空 {side.upper()} 路线草稿", 3000)

    def _show_message_platform(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("消息指挥平台")
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "消息指挥平台\n"
            f"当前场景: {self.scenario.name}\n"
            f"单位数量: {len(self.scenario.units)}\n"
            "地图模式: 纯 Qt 离线地图\n"
            "前端环境: 未使用\n"
        )
        layout.addWidget(text)
        dialog.exec_()

    def _show_units_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("战斗单元")
        dialog.resize(860, 460)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(self.scenario.units), 9)
        table.setHorizontalHeaderLabels(["序号", "阵营", "类型", "单位ID", "名称", "路线", "运动", "范围", "速度"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        for row, unit in enumerate(self.scenario.units):
            values = [
                str(row + 1),
                unit.side.upper(),
                unit.unit_type,
                unit.unit_id,
                unit.name,
                unit.route_id or "内置 route",
                unit.motion,
                f"{unit.range_nm:g} nm",
                f"{unit.speed:g}",
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        dialog.exec_()

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
        total = int(seconds)
        minutes = total // 60
        remain = total % 60
        self.time_label.setText(f"仿真时间: {minutes:02d}:{remain:02d}")
