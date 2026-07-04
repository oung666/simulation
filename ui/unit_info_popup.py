from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from simulation.core.contact import ContactTrack
from simulation.core.scenario import CombatUnit


class UnitInfoPopup(QFrame):
    """Embeddable tactical unit information panel."""

    actionRequested = pyqtSignal(str, str)
    unitEdited = pyqtSignal(str, dict)
    unitDeleted = pyqtSignal(str)
    closeRequested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("UnitInfoPopup")
        self.setFrameShape(QFrame.StyledPanel)
        self._unit_id: str | None = None
        self._header_name_label: QLabel | None = None
        self._header_meta_label: QLabel | None = None
        self._value_labels: dict[str, QLabel] = {}
        self._stack: QStackedWidget | None = None
        self._details_page: QWidget | None = None
        self._edit_page: QWidget | None = None
        self._weapons_page: QWidget | None = None
        self._edit_inputs: dict[str, QLineEdit | QDoubleSpinBox | QCheckBox] = {}
        self._weapons_table: QTableWidget | None = None
        self._editing_unit_id: str | None = None
        self._operation_buttons: list[QPushButton] = []
        self._build_ui()
        self.hide()

    def update_data(self, unit: CombatUnit, mission_name: str | None = None, position=None) -> None:
        self._set_operations_visible(True)
        same_editing_unit = (
            self._stack is not None
            and self._edit_page is not None
            and self._stack.currentWidget() == self._edit_page
            and self._editing_unit_id == unit.unit_id
        )
        self._unit_id = unit.unit_id
        if self._header_name_label is not None:
            self._header_name_label.setText(unit.name)
        if self._header_meta_label is not None:
            class_name = getattr(unit, "class_name", "") or unit.unit_type.upper()
            side_label = {"blue": "蓝方", "red": "红方"}.get(unit.side, unit.side.upper())
            self._header_meta_label.setText(f"{class_name} / {side_label}")
        position = position or unit.position or (unit.route.points[0] if unit.route.points else None)
        coordinate_text = "暂无" if position is None else f"{position.lon:.5f}, {position.lat:.5f}"
        values = {
            "coordinates": coordinate_text,
            "altitude": self._format_optional_number(getattr(unit, "altitude_ft", None), "英尺"),
            "heading": f"{unit.heading:.0f} 度",
            "speed": f"{unit.speed:g} 节",
            "fuel": self._format_fuel(unit),
            "fuel_consumption": f"{unit.fuel_rate:g} / 分钟" if unit.fuel_rate is not None else "暂无",
            "detection_range": f"{(unit.detection_range_nm or unit.range_nm):g} 海里",
            "radar_state": "开" if getattr(unit, "radar_on", True) else "关",
            "rcs": f"{float(getattr(unit, 'rcs', 1.0)):g}",
            "jammer_range": f"{float(getattr(unit, 'jammer_range_nm', 0.0)):g} 海里",
            "ew_resistance": f"{float(getattr(unit, 'ew_resistance', 0.0)):g}",
            "comms_state": "开" if getattr(unit, "comms_on", True) else "关",
            "datalink": "是" if getattr(unit, "datalink", True) else "否",
            "command_node": "是" if getattr(unit, "command_node", False) else "否",
            "comms_range": f"{float(getattr(unit, 'comms_range_nm', 0.0)):g} 海里",
            "comms_resistance": f"{float(getattr(unit, 'comms_resistance', 0.0)):g}",
            "mission": mission_name or "暂无",
        }
        for key, value in values.items():
            self._value_labels[key].setText(value)
        if not same_editing_unit:
            self._populate_edit_inputs(unit)
        self._populate_weapons(unit)

    def update_contact_data(self, track: ContactTrack, current_time: float) -> None:
        """Show a read-only side-view enemy contact without truth-state details."""
        self._set_operations_visible(False)
        self._unit_id = track.target_id
        if self._stack is not None and self._details_page is not None:
            self._stack.setCurrentWidget(self._details_page)
        if self._header_name_label is not None:
            self._header_name_label.setText(f"Contact {track.target_id}")
        if self._header_meta_label is not None:
            state = "STALE" if track.is_stale(current_time) else ("SHARED" if track.shared else "LOCAL")
            self._header_meta_label.setText(f"Enemy contact / {state}")
        confidence = track.decayed_confidence(current_time)
        state_text = "stale" if track.is_stale(current_time) else "current"
        values = {
            "coordinates": f"{track.last_known_position.lon:.5f}, {track.last_known_position.lat:.5f}",
            "altitude": "unknown",
            "heading": "unknown",
            "speed": "unknown",
            "fuel": "unknown",
            "fuel_consumption": "unknown",
            "detection_range": "unknown",
            "radar_state": "unknown",
            "rcs": "unknown",
            "jammer_range": "unknown",
            "ew_resistance": "unknown",
            "comms_state": "unknown",
            "datalink": "unknown",
            "command_node": "unknown",
            "comms_range": "unknown",
            "comms_resistance": "unknown",
            "mission": f"{state_text} / confidence {confidence:.2f} / source {track.source_unit_id}",
        }
        for key, value in values.items():
            self._value_labels[key].setText(value)
        if self._weapons_table is not None:
            self._weapons_table.setRowCount(0)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QFrame#UnitInfoPopup {
                background: rgba(10, 16, 30, 235);
                border: 1px solid rgba(125, 211, 252, 150);
                border-radius: 12px;
            }
            QLabel#PopupTitle {
                color: #f8fafc;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#PopupMeta {
                color: #38bdf8;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel.PopupCaption {
                color: #94a3b8;
                font-size: 14px;
            }
            QLabel.PopupValue {
                color: #e2e8f0;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton#PopupActionsButton {
                background: #f59e0b;
                color: #111827;
                border: none;
                border-radius: 7px;
                min-width: 78px;
                padding: 6px 10px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton.PopupHeaderButton {
                background: rgba(30, 41, 59, 220);
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 6px;
                min-width: 48px;
                padding: 5px 7px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton.PopupHeaderButton:hover {
                background: #1e40af;
                color: #ffffff;
            }
            QPushButton.PopupDangerButton:hover {
                background: #991b1b;
            }
            QPushButton.PopupPrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                padding: 6px 10px;
                font-weight: 700;
            }
            QPushButton#PopupCloseButton {
                background: rgba(15, 23, 42, 210);
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 6px;
                min-width: 28px;
                max-width: 28px;
                padding: 5px 0;
                font-size: 13px;
                font-weight: 800;
            }
            QPushButton#PopupCloseButton:hover {
                background: #991b1b;
                color: #ffffff;
            }
            QLineEdit, QDoubleSpinBox {
                background: #020617;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QTableWidget {
                background: #020617;
                color: #e2e8f0;
                border: 1px solid #334155;
                gridline-color: #334155;
            }
            QHeaderView::section {
                background: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                padding: 4px;
            }
            QMenu {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
            }
            QMenu::item:selected {
                background: #1e40af;
            }
            """
        )
        self.setFixedWidth(350)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        identity = QVBoxLayout()
        identity.setSpacing(2)
        self._header_name_label = QLabel("暂无")
        self._header_name_label.setObjectName("PopupTitle")
        self._header_name_label.setWordWrap(True)
        self._header_meta_label = QLabel("暂无 / 暂无")
        self._header_meta_label.setObjectName("PopupMeta")
        identity.addWidget(self._header_name_label)
        identity.addWidget(self._header_meta_label)
        header.addLayout(identity, 1)
        edit_button = QPushButton("编辑")
        edit_button.setProperty("class", "PopupHeaderButton")
        edit_button.clicked.connect(self.show_edit_page)
        delete_button = QPushButton("删除")
        delete_button.setProperty("class", "PopupHeaderButton PopupDangerButton")
        delete_button.clicked.connect(self._emit_delete)
        header.addWidget(edit_button)
        header.addWidget(delete_button)
        actions_button = QPushButton("操作")
        actions_button.setObjectName("PopupActionsButton")
        actions_button.setMinimumWidth(96)
        actions_button.setMenu(self._build_actions_menu(actions_button))
        header.addWidget(actions_button)
        close_button = QPushButton("X")
        close_button.setObjectName("PopupCloseButton")
        close_button.setToolTip("关闭参数表")
        close_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(close_button)
        self._operation_buttons.extend([edit_button, delete_button, actions_button])
        layout.addLayout(header)

        self._stack = QStackedWidget()
        self._details_page = QWidget()
        details_layout = QVBoxLayout(self._details_page)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(0)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        fields = [
            ("coordinates", "坐标"),
            ("altitude", "高度"),
            ("heading", "航向"),
            ("speed", "速度"),
            ("fuel", "燃油"),
            ("fuel_consumption", "油耗"),
            ("detection_range", "探测范围"),
            ("radar_state", "雷达"),
            ("rcs", "RCS"),
            ("jammer_range", "干扰范围"),
            ("ew_resistance", "抗干扰"),
            ("comms_state", "通信"),
            ("datalink", "数据链"),
            ("command_node", "指挥节点"),
            ("comms_range", "通信范围"),
            ("comms_resistance", "通信抗扰"),
            ("mission", "所属任务"),
        ]
        for row, (key, caption) in enumerate(fields):
            caption_label = QLabel(caption)
            caption_label.setProperty("class", "PopupCaption")
            value_label = QLabel("暂无")
            value_label.setProperty("class", "PopupValue")
            value_label.setWordWrap(True)
            self._value_labels[key] = value_label
            grid.addWidget(caption_label, row, 0)
            grid.addWidget(value_label, row, 1)
        details_layout.addLayout(grid, 0)
        details_layout.addStretch(1)
        self._edit_page = self._build_edit_page()
        self._weapons_page = self._build_weapons_page()
        self._stack.addWidget(self._details_page)
        self._stack.addWidget(self._edit_page)
        self._stack.addWidget(self._weapons_page)
        layout.addWidget(self._stack)

    def _build_actions_menu(self, parent_button: QPushButton) -> QMenu:
        menu = QMenu(parent_button)
        menu.setObjectName("UnitActionsMenu")
        menu.setStyleSheet(
            """
            QMenu#UnitActionsMenu {
                background: #0f172a;
                border: 1px solid #334155;
                padding: 6px;
            }
            QMenu#UnitActionsMenu::item {
                color: #f8fafc;
                background: transparent;
                padding: 8px 22px;
                min-width: 150px;
                border-radius: 6px;
            }
            QMenu#UnitActionsMenu::item:selected {
                background: #2563eb;
                color: #ffffff;
            }
            QMenu#UnitActionsMenu::item:disabled {
                color: #94a3b8;
            }
            QMenu::item {
                color: #f8fafc;
                background: transparent;
                padding: 8px 22px;
                min-width: 150px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: #2563eb;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #94a3b8;
            }
            """
        )
        actions = [
            ("plot_course", "规划航线"),
            ("auto_attack", "自动攻击"),
            ("manual_attack", "手动攻击"),
            ("return_to_base", "返回基地"),
            ("duplicate", "复制单位"),
            ("edit_location", "修改位置"),
        ]
        for action_key, label in actions:
            menu.addAction(label, lambda checked=False, key=action_key: self._emit_action(key))
        return menu

    def _emit_action(self, action_key: str) -> None:
        if self._unit_id is not None:
            if action_key == "manual_attack":
                self.show_weapons_page()
            self.actionRequested.emit(self._unit_id, action_key)

    def _emit_delete(self) -> None:
        if self._unit_id is not None:
            self.unitDeleted.emit(self._unit_id)

    def _build_edit_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        self._edit_inputs["name"] = QLineEdit()
        numeric_specs = [
            ("speed", "速度（节）", 0.0, 5000.0, 3),
            ("altitude_ft", "高度（英尺）", 0.0, 120000.0, 1),
            ("range_nm", "作战半径（海里）", 0.0, 100000.0, 3),
            ("current_fuel", "当前燃油", 0.0, 100000000.0, 3),
            ("max_fuel", "最大燃油", 0.0, 100000000.0, 3),
            ("fuel_rate", "油耗", 0.0, 1000000.0, 3),
            ("detection_range_nm", "探测范围（海里）", 0.0, 100000.0, 3),
            ("rcs", "RCS", 0.0, 100000.0, 3),
            ("jammer_power", "干扰功率", 0.0, 100.0, 3),
            ("jammer_range_nm", "干扰范围（海里）", 0.0, 100000.0, 3),
            ("ew_resistance", "抗干扰", 0.0, 100.0, 3),
            ("comms_range_nm", "通信范围（海里）", 0.0, 100000.0, 3),
            ("comms_power", "通信功率", 0.0, 100.0, 3),
            ("comms_resistance", "通信抗扰", 0.0, 100.0, 3),
        ]
        for key, _label, minimum, maximum, decimals in numeric_specs:
            box = QDoubleSpinBox()
            box.setDecimals(decimals)
            box.setRange(minimum, maximum)
            box.setSingleStep(1.0)
            self._edit_inputs[key] = box
        for key in ["radar_on", "comms_on", "datalink", "command_node"]:
            checkbox = QCheckBox("启用")
            self._edit_inputs[key] = checkbox
        rows = [
            ("name", "名称"),
            ("speed", "速度（节）"),
            ("altitude_ft", "高度（英尺）"),
            ("range_nm", "作战半径（海里）"),
            ("current_fuel", "燃油"),
            ("max_fuel", "最大燃油"),
            ("fuel_rate", "油耗"),
            ("detection_range_nm", "探测范围（海里）"),
            ("radar_on", "雷达"),
            ("rcs", "RCS"),
            ("jammer_power", "干扰功率"),
            ("jammer_range_nm", "干扰范围（海里）"),
            ("ew_resistance", "抗干扰"),
            ("comms_on", "通信"),
            ("datalink", "数据链"),
            ("command_node", "指挥节点"),
            ("comms_range_nm", "通信范围（海里）"),
            ("comms_power", "通信功率"),
            ("comms_resistance", "通信抗扰"),
        ]
        for row, (key, label_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setProperty("class", "PopupCaption")
            grid.addWidget(label, row, 0)
            grid.addWidget(self._edit_inputs[key], row, 1)
        layout.addLayout(grid)
        buttons = QHBoxLayout()
        save_button = QPushButton("保存")
        save_button.setProperty("class", "PopupPrimaryButton")
        save_button.clicked.connect(self._save_edit)
        cancel_button = QPushButton("取消")
        cancel_button.setProperty("class", "PopupHeaderButton")
        cancel_button.clicked.connect(self.show_details_page)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)
        return page

    def _build_weapons_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._weapons_table = QTableWidget(0, 7)
        self._weapons_table.setHorizontalHeaderLabels(["名称", "型号", "当前", "最大", "射程", "速度", "杀伤率"])
        self._weapons_table.verticalHeader().setVisible(False)
        self._weapons_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self._weapons_table.setSelectionMode(QTableWidget.NoSelection)
        layout.addWidget(self._weapons_table)
        buttons = QHBoxLayout()
        save_button = QPushButton("保存武器")
        save_button.setProperty("class", "PopupPrimaryButton")
        save_button.clicked.connect(self._save_weapons)
        back_button = QPushButton("返回")
        back_button.setProperty("class", "PopupHeaderButton")
        back_button.clicked.connect(self.show_details_page)
        buttons.addWidget(save_button)
        buttons.addWidget(back_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _populate_edit_inputs(self, unit: CombatUnit) -> None:
        name_input = self._edit_inputs.get("name")
        if isinstance(name_input, QLineEdit):
            name_input.setText(unit.name)
        numeric_values = {
            "speed": unit.speed,
            "altitude_ft": getattr(unit, "altitude_ft", 0.0),
            "range_nm": getattr(unit, "range_nm", 0.0),
            "current_fuel": getattr(unit, "current_fuel", 0.0),
            "max_fuel": getattr(unit, "max_fuel", 0.0),
            "fuel_rate": getattr(unit, "fuel_rate", 0.0),
            "detection_range_nm": unit.detection_range_nm or unit.range_nm,
            "rcs": getattr(unit, "rcs", 1.0),
            "jammer_power": getattr(unit, "jammer_power", 0.0),
            "jammer_range_nm": getattr(unit, "jammer_range_nm", 0.0),
            "ew_resistance": getattr(unit, "ew_resistance", 0.0),
            "comms_range_nm": getattr(unit, "comms_range_nm", 0.0),
            "comms_power": getattr(unit, "comms_power", 1.0),
            "comms_resistance": getattr(unit, "comms_resistance", 0.0),
        }
        for key, value in numeric_values.items():
            widget = self._edit_inputs.get(key)
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value or 0.0))
        boolean_values = {
            "radar_on": getattr(unit, "radar_on", True),
            "comms_on": getattr(unit, "comms_on", True),
            "datalink": getattr(unit, "datalink", True),
            "command_node": getattr(unit, "command_node", False),
        }
        for key, value in boolean_values.items():
            widget = self._edit_inputs.get(key)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))

    def _populate_weapons(self, unit: CombatUnit) -> None:
        if self._weapons_table is None:
            return
        self._weapons_table.setRowCount(len(unit.weapons))
        for row, weapon in enumerate(unit.weapons):
            values = [
                weapon.name,
                weapon.weapon_class,
                f"{weapon.current_quantity:g}",
                f"{weapon.max_quantity:g}",
                f"{weapon.range_nm:g}",
                f"{weapon.speed:g}",
                f"{weapon.lethality:g}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {0, 1}:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._weapons_table.setItem(row, column, item)
        self._weapons_table.resizeColumnsToContents()

    def _set_operations_visible(self, visible: bool) -> None:
        for button in self._operation_buttons:
            button.setVisible(visible)

    def show_details_page(self) -> None:
        if self._stack is not None and self._details_page is not None:
            self._stack.setCurrentWidget(self._details_page)
        self._editing_unit_id = None

    def show_edit_page(self) -> None:
        if self._stack is not None and self._edit_page is not None:
            self._editing_unit_id = self._unit_id
            self._stack.setCurrentWidget(self._edit_page)

    def show_weapons_page(self) -> None:
        if self._stack is not None and self._weapons_page is not None:
            self._stack.setCurrentWidget(self._weapons_page)
        self._editing_unit_id = None

    def _save_edit(self) -> None:
        if self._unit_id is None:
            return
        name_input = self._edit_inputs.get("name")
        values = {
            "name": name_input.text().strip() if isinstance(name_input, QLineEdit) else "",
        }
        numeric_keys = [
            "speed",
            "altitude_ft",
            "range_nm",
            "current_fuel",
            "max_fuel",
            "fuel_rate",
            "detection_range_nm",
            "rcs",
            "jammer_power",
            "jammer_range_nm",
            "ew_resistance",
            "comms_range_nm",
            "comms_power",
            "comms_resistance",
        ]
        for key in numeric_keys:
            widget = self._edit_inputs.get(key)
            if isinstance(widget, QDoubleSpinBox):
                values[key] = widget.value()
        for key in ["radar_on", "comms_on", "datalink", "command_node"]:
            widget = self._edit_inputs.get(key)
            if isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
        self.unitEdited.emit(self._unit_id, values)
        self.show_details_page()

    def _save_weapons(self) -> None:
        if self._unit_id is None or self._weapons_table is None:
            return
        weapons = []
        for row in range(self._weapons_table.rowCount()):
            weapons.append(
                {
                    "name": self._item_text(row, 0),
                    "weapon_class": self._item_text(row, 1),
                    "current_quantity": self._to_int(self._item_text(row, 2)),
                    "max_quantity": self._to_int(self._item_text(row, 3)),
                    "range_nm": self._to_float(self._item_text(row, 4)),
                    "speed": self._to_float(self._item_text(row, 5)),
                    "lethality": self._to_float(self._item_text(row, 6)),
                }
            )
        self.unitEdited.emit(self._unit_id, {"weapons": weapons})
        self.show_details_page()

    def _item_text(self, row: int, column: int) -> str:
        if self._weapons_table is None:
            return ""
        item = self._weapons_table.item(row, column)
        return "" if item is None else item.text().strip()

    @staticmethod
    def _to_float(value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return 0.0

    @staticmethod
    def _to_int(value: str) -> int:
        try:
            return max(0, int(float(value)))
        except ValueError:
            return 0

    @staticmethod
    def _format_optional_number(value: object, suffix: str) -> str:
        if value is None:
            return "N/A"
        try:
            return f"{float(value):g} {suffix}"
        except (TypeError, ValueError):
            return "N/A"

    @staticmethod
    def _format_fuel(unit: CombatUnit) -> str:
        current_fuel = getattr(unit, "current_fuel", None)
        max_fuel = getattr(unit, "max_fuel", None)
        if current_fuel is None:
            return "N/A"
        if max_fuel:
            return f"{current_fuel:g} / {max_fuel:g}"
        return f"{current_fuel:g}"
