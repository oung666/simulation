from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout


class CombatLogOverlay(QFrame):
    """Floating combat-log panel hosted inside the map canvas."""

    minimizeRequested = pyqtSignal()
    maximizeRequested = pyqtSignal()
    closeRequested = pyqtSignal()
    filterChanged = pyqtSignal()
    eventActivated = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CombatLogOverlay")
        self._maximized = False
        self._title_label: QLabel | None = None
        self._maximize_button: QPushButton | None = None
        self._side_filter: QComboBox | None = None
        self._type_filter: QComboBox | None = None
        self.log_list = QListWidget(self)
        self._build_ui()

    def set_entries(self, entries: list[tuple[int, str]]) -> None:
        self.log_list.clear()
        if not entries:
            self.log_list.addItem("暂无交战事件")
            return
        for event_index, text in entries:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, event_index)
            self.log_list.addItem(item)

    def side_filter(self) -> str:
        return "all" if self._side_filter is None else str(self._side_filter.currentData())

    def type_filter(self) -> str:
        return "all" if self._type_filter is None else str(self._type_filter.currentData())

    def set_filters(self, side: str = "all", event_type: str = "all") -> None:
        self._set_combo_data(self._side_filter, side)
        self._set_combo_data(self._type_filter, event_type)

    def set_maximized_state(self, maximized: bool) -> None:
        self._maximized = maximized
        if self._maximize_button is not None:
            self._maximize_button.setText("还原" if maximized else "放大")

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QFrame#CombatLogOverlay {
                background: rgba(255, 255, 255, 245);
                border: 1px solid rgba(210, 218, 226, 230);
                border-radius: 10px;
            }
            QLabel#CombatLogTitle {
                color: #111827;
                font-size: 15px;
                font-weight: 900;
            }
            QListWidget#CombatLogOverlayList {
                background: #ffffff;
                border: 1px solid #d9dee5;
                border-radius: 8px;
                color: #111827;
                font-size: 13px;
                padding: 4px;
            }
            QPushButton.CombatLogToolButton {
                background: #f3f4f6;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                min-width: 42px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 800;
            }
            QPushButton.CombatLogToolButton:hover {
                background: #e5e7eb;
            }
            QPushButton#CombatLogCloseButton:hover {
                background: #991b1b;
                border-color: #991b1b;
                color: #ffffff;
            }
            QComboBox.CombatLogFilter {
                background: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 12px;
                min-height: 24px;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._title_label = QLabel("战斗日志")
        self._title_label.setObjectName("CombatLogTitle")
        header.addWidget(self._title_label, 1)

        minimize_button = QPushButton("缩小")
        minimize_button.setProperty("class", "CombatLogToolButton")
        minimize_button.clicked.connect(self.minimizeRequested.emit)
        header.addWidget(minimize_button)

        self._maximize_button = QPushButton("放大")
        self._maximize_button.setProperty("class", "CombatLogToolButton")
        self._maximize_button.clicked.connect(self.maximizeRequested.emit)
        header.addWidget(self._maximize_button)

        close_button = QPushButton("X")
        close_button.setObjectName("CombatLogCloseButton")
        close_button.setProperty("class", "CombatLogToolButton")
        close_button.setToolTip("关闭战斗日志")
        close_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(close_button)

        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.setSpacing(6)
        self._side_filter = QComboBox()
        self._side_filter.setProperty("class", "CombatLogFilter")
        self._side_filter.addItem("全部阵营", "all")
        self._side_filter.addItem("蓝方相关", "blue")
        self._side_filter.addItem("红方相关", "red")
        self._side_filter.currentIndexChanged.connect(self.filterChanged.emit)
        filters.addWidget(self._side_filter)

        self._type_filter = QComboBox()
        self._type_filter.setProperty("class", "CombatLogFilter")
        for label, value in [
            ("全部类型", "all"),
            ("探测", "detected"),
            ("共享", "shared_contact"),
            ("发射", "launched"),
            ("命中", "hit"),
            ("未命中", "miss"),
            ("失效", "expired"),
            ("丢失目标", "lost_target"),
        ]:
            self._type_filter.addItem(label, value)
        self._type_filter.currentIndexChanged.connect(self.filterChanged.emit)
        filters.addWidget(self._type_filter)
        layout.addLayout(filters)

        self.log_list.setObjectName("CombatLogOverlayList")
        self.log_list.itemClicked.connect(self._emit_event_activated)
        self.log_list.itemActivated.connect(self._emit_event_activated)
        layout.addWidget(self.log_list, 1)

    def _emit_event_activated(self, item: QListWidgetItem) -> None:
        event_index = item.data(Qt.UserRole)
        if isinstance(event_index, int):
            self.eventActivated.emit(event_index)

    def _set_combo_data(self, combo: QComboBox | None, value: str) -> None:
        if combo is None:
            return
        index = combo.findData(value)
        if index < 0:
            index = 0
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)


class CombatLogMarker(QPushButton):
    """Small bottom-left marker used to restore a minimized combat log."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CombatLogMarker")
        self.setText("战斗日志")
        self.setStyleSheet(
            """
            QPushButton#CombatLogMarker {
                background: rgba(17, 24, 39, 225);
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 210);
                border-radius: 8px;
                min-height: 30px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 900;
            }
            QPushButton#CombatLogMarker:hover {
                background: rgba(37, 99, 235, 235);
                border-color: rgba(191, 219, 254, 230);
            }
            """
        )

    def set_count(self, count: int) -> None:
        self.setText(f"战斗日志 {count}" if count > 0 else "战斗日志")
