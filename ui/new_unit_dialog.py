from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from simulation.core.db import AirbaseDb, AllAircraftDb, FacilityDb, GroundVehicleDb, ShipDb, WeaponDb
from simulation.core.geo import LonLat


@dataclass(frozen=True)
class NewUnitWeaponRequest:
    weapon_class: str
    quantity: int


@dataclass(frozen=True)
class NewUnitRequest:
    side: str
    unit_type: str
    class_name: str
    unit_id: str
    name: str
    position: LonLat
    weapons: list[NewUnitWeaponRequest]


class NewUnitDialog(QDialog):
    """Dialog for creating a new scenario unit from database templates."""

    _TYPE_OPTIONS = [
        ("飞机", "aircraft", AllAircraftDb),
        ("舰艇", "ship", ShipDb),
        ("地面车辆", "ground_vehicle", GroundVehicleDb),
        ("设施", "facility", FacilityDb),
        ("机场", "airbase", AirbaseDb),
    ]

    def __init__(self, parent=None, center: LonLat | None = None, default_side: str = "blue") -> None:
        super().__init__(parent)
        self.setObjectName("NewUnitDialog")
        self.setWindowTitle("新增作战单位")
        self.resize(420, 360)
        self._center = center or LonLat(0.0, 0.0)
        self._last_unit_id_seed = ""
        self._last_name_seed = ""
        self._build_ui(default_side)
        self._apply_light_palette()
        self._refresh_class_combo()
        self._refresh_defaults()

    def request(self) -> NewUnitRequest:
        return NewUnitRequest(
            side=str(self.side_combo.currentData()),
            unit_type=str(self.type_combo.currentData()),
            class_name=str(self.class_combo.currentData() or ""),
            unit_id=self.unit_id_input.text().strip(),
            name=self.name_input.text().strip(),
            position=LonLat(self.lon_input.value(), self.lat_input.value()),
            weapons=self._weapon_requests(),
        )

    def _build_ui(self, default_side: str) -> None:
        self.setStyleSheet(
            """
            QDialog#NewUnitDialog {
                background: #ffffff;
                color: #111827;
            }
            QDialog#NewUnitDialog QLabel {
                color: #111827;
                font-size: 13px;
                font-weight: 600;
            }
            QDialog#NewUnitDialog QLabel#NewUnitFormLabel {
                color: #111827;
                font-size: 13px;
                font-weight: 700;
                padding-right: 6px;
            }
            QDialog#NewUnitDialog QLabel#NewUnitInlineLabel {
                color: #111827;
                font-size: 13px;
                font-weight: 700;
            }
            QDialog#NewUnitDialog QLabel#NewUnitPreviewLabel {
                color: #4b5563;
                font-size: 13px;
                font-weight: 500;
                line-height: 18px;
            }
            QDialog#NewUnitDialog QLineEdit,
            QDialog#NewUnitDialog QComboBox,
            QDialog#NewUnitDialog QSpinBox,
            QDialog#NewUnitDialog QDoubleSpinBox,
            QDialog#NewUnitDialog QTableWidget {
                background: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                min-height: 30px;
                padding: 4px 8px;
                font-size: 13px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QDialog#NewUnitDialog QTableWidget {
                border-radius: 6px;
                gridline-color: #e5e7eb;
            }
            QDialog#NewUnitDialog QHeaderView::section {
                background: #f9fafb;
                color: #111827;
                border: 1px solid #e5e7eb;
                padding: 4px;
                font-weight: 800;
            }
            QDialog#NewUnitDialog QLineEdit:focus,
            QDialog#NewUnitDialog QComboBox:focus,
            QDialog#NewUnitDialog QSpinBox:focus,
            QDialog#NewUnitDialog QDoubleSpinBox:focus {
                border: 2px solid #10b981;
                padding: 3px 7px;
            }
            QDialog#NewUnitDialog QPushButton {
                background: #f3f4f6;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                min-width: 72px;
                min-height: 30px;
                padding: 6px 12px;
                font-weight: 800;
            }
            QDialog#NewUnitDialog QPushButton:hover {
                background: #e5e7eb;
            }
            QDialog#NewUnitDialog QPushButton:default {
                background: #10b981;
                color: #ffffff;
                border-color: #10b981;
            }
            QDialog#NewUnitDialog QPushButton:default:hover {
                background: #059669;
                border-color: #059669;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.side_combo = QComboBox()
        self.side_combo.addItem("蓝方", "blue")
        self.side_combo.addItem("红方", "red")
        side_index = self.side_combo.findData(default_side)
        if side_index >= 0:
            self.side_combo.setCurrentIndex(side_index)
        self.side_combo.currentIndexChanged.connect(self._refresh_defaults)
        self._add_form_row(form, "阵营", self.side_combo)

        self.type_combo = QComboBox()
        for label, value, _entries in self._TYPE_OPTIONS:
            self.type_combo.addItem(label, value)
        self.type_combo.currentIndexChanged.connect(self._refresh_class_combo)
        self.type_combo.currentIndexChanged.connect(self._refresh_defaults)
        self._add_form_row(form, "类型", self.type_combo)

        self.class_combo = QComboBox()
        self.class_combo.currentIndexChanged.connect(self._refresh_defaults)
        self._add_form_row(form, "平台模板", self.class_combo)

        self.unit_id_input = QLineEdit()
        self._add_form_row(form, "单位 ID", self.unit_id_input)

        self.name_input = QLineEdit()
        self._add_form_row(form, "名称", self.name_input)

        coord_row = QHBoxLayout()
        self.lon_input = self._coord_input(self._center.lon, -180.0, 180.0)
        self.lat_input = self._coord_input(self._center.lat, -90.0, 90.0)
        coord_row.addWidget(self._inline_label("经度"))
        coord_row.addWidget(self.lon_input)
        coord_row.addWidget(self._inline_label("纬度"))
        coord_row.addWidget(self.lat_input)
        self._add_form_row(form, "初始坐标", coord_row)

        self.weapon_combo = QComboBox()
        self.weapon_combo.addItem("无武器", "")
        for entry in WeaponDb:
            class_name = str(entry.get("class_name", entry.get("className", ""))).strip()
            if class_name:
                self.weapon_combo.addItem(class_name, class_name)

        self.weapon_quantity_input = QSpinBox()
        self.weapon_quantity_input.setRange(0, 999)
        self.weapon_quantity_input.setValue(2)

        weapon_row = QHBoxLayout()
        weapon_row.addWidget(self.weapon_combo, 1)
        weapon_row.addWidget(self.weapon_quantity_input, 0)
        add_weapon_button = QPushButton("添加")
        add_weapon_button.clicked.connect(self._add_selected_weapon)
        weapon_row.addWidget(add_weapon_button, 0)
        self._add_form_row(form, "初始武器", weapon_row)

        layout.addLayout(form)

        self.weapon_table = QTableWidget(0, 2)
        self.weapon_table.setHorizontalHeaderLabels(["武器型号", "数量"])
        self.weapon_table.verticalHeader().setVisible(False)
        self.weapon_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.weapon_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.weapon_table.setMinimumHeight(92)
        self.weapon_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.weapon_table)

        remove_weapon_button = QPushButton("移除选中武器")
        remove_weapon_button.clicked.connect(self._remove_selected_weapon)
        layout.addWidget(remove_weapon_button, 0, Qt.AlignRight)

        self.preview_label = QLabel("")
        self.preview_label.setObjectName("NewUnitPreviewLabel")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_form_row(self, form: QFormLayout, label_text: str, field) -> None:
        label = QLabel(label_text)
        label.setObjectName("NewUnitFormLabel")
        form.addRow(label, field)

    def _inline_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("NewUnitInlineLabel")
        return label

    def _apply_light_palette(self) -> None:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#ffffff"))
        palette.setColor(QPalette.WindowText, QColor("#111827"))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.AlternateBase, QColor("#f9fafb"))
        palette.setColor(QPalette.Text, QColor("#111827"))
        palette.setColor(QPalette.Button, QColor("#f3f4f6"))
        palette.setColor(QPalette.ButtonText, QColor("#111827"))
        palette.setColor(QPalette.Highlight, QColor("#2563eb"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        for widget in self.findChildren(QWidget):
            widget.setPalette(palette)

    def _refresh_class_combo(self) -> None:
        unit_type = str(self.type_combo.currentData())
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        for label, value, entries in self._TYPE_OPTIONS:
            if value != unit_type:
                continue
            for entry in entries:
                class_name = str(entry.get("class_name", entry.get("className", entry.get("name", "")))).strip()
                if class_name:
                    self.class_combo.addItem(class_name, class_name)
            break
        self.class_combo.blockSignals(False)

    def _refresh_defaults(self) -> None:
        side = str(self.side_combo.currentData())
        unit_type = str(self.type_combo.currentData())
        class_name = str(self.class_combo.currentData() or unit_type)
        class_slug = _slug(class_name or unit_type)
        side_slug = "blue" if side == "blue" else "red"
        unit_id = f"{side_slug}-{_slug(unit_type)}-{class_slug}"
        name_seed = f"{'蓝方' if side == 'blue' else '红方'} {class_name}"
        if not self.unit_id_input.text().strip() or self.unit_id_input.text().strip() == self._last_unit_id_seed:
            self.unit_id_input.setText(unit_id[:48])
        if not self.name_input.text().strip() or self.name_input.text().strip() == self._last_name_seed:
            self.name_input.setText(name_seed)
        self._last_unit_id_seed = unit_id[:48]
        self._last_name_seed = name_seed
        self._select_default_weapon_for_type(unit_type)
        self.preview_label.setText(
            f"将创建 {class_name}，类型 {unit_type}，坐标 {self.lon_input.value():.4f}, {self.lat_input.value():.4f}。"
        )

    def _select_default_weapon_for_type(self, unit_type: str) -> None:
        if self.weapon_table.rowCount() > 0:
            return
        preferred_types = {
            "aircraft": {"aam", "air_to_air", "air-to-air"},
            "ship": {"asm", "anti_ship", "anti-ship", "sam"},
            "ground_vehicle": {"rocket", "ballistic", "surface_to_surface", "ssm"},
            "facility": {"sam", "surface_to_air", "surface-to-air"},
            "airbase": set(),
        }.get(unit_type, set())
        if not preferred_types:
            self.weapon_combo.setCurrentIndex(0)
            self.weapon_quantity_input.setValue(0)
            return
        for index in range(1, self.weapon_combo.count()):
            weapon_class = str(self.weapon_combo.itemData(index))
            raw_weapon = _weapon_entry(weapon_class)
            weapon_type = str(raw_weapon.get("type", "")).lower() if raw_weapon else ""
            if weapon_type in preferred_types:
                self.weapon_combo.setCurrentIndex(index)
                self.weapon_quantity_input.setValue(2 if unit_type == "aircraft" else 4)
                return
        self.weapon_combo.setCurrentIndex(0)

    def _add_selected_weapon(self) -> None:
        weapon_class = str(self.weapon_combo.currentData() or "")
        quantity = int(self.weapon_quantity_input.value())
        if not weapon_class or quantity <= 0:
            return
        for row in range(self.weapon_table.rowCount()):
            if self.weapon_table.item(row, 0).text() == weapon_class:
                existing = int(self.weapon_table.item(row, 1).text())
                self.weapon_table.item(row, 1).setText(str(existing + quantity))
                return
        row = self.weapon_table.rowCount()
        self.weapon_table.insertRow(row)
        self.weapon_table.setItem(row, 0, QTableWidgetItem(weapon_class))
        self.weapon_table.setItem(row, 1, QTableWidgetItem(str(quantity)))
        self.weapon_table.resizeColumnsToContents()

    def _remove_selected_weapon(self) -> None:
        rows = sorted({index.row() for index in self.weapon_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.weapon_table.removeRow(row)

    def _weapon_requests(self) -> list[NewUnitWeaponRequest]:
        weapons: list[NewUnitWeaponRequest] = []
        for row in range(self.weapon_table.rowCount()):
            weapon_item = self.weapon_table.item(row, 0)
            quantity_item = self.weapon_table.item(row, 1)
            if weapon_item is None or quantity_item is None:
                continue
            try:
                quantity = max(0, int(quantity_item.text()))
            except ValueError:
                quantity = 0
            if weapon_item.text() and quantity > 0:
                weapons.append(NewUnitWeaponRequest(weapon_item.text(), quantity))
        return weapons

    @staticmethod
    def _coord_input(value: float, minimum: float, maximum: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(6)
        box.setRange(minimum, maximum)
        box.setSingleStep(0.01)
        box.setValue(float(value))
        return box


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "unit"


def _weapon_entry(weapon_class: str) -> dict | None:
    for entry in WeaponDb:
        class_name = str(entry.get("class_name", entry.get("className", ""))).strip()
        if class_name == weapon_class:
            return entry
    return None
