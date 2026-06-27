from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt5.QtCore import QSize, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class ControlOverlayPage:
    page_id: str
    title: str
    builder: Callable[[], QWidget]
    order: int
    icon_text: str | None = None
    preferred_size: QSize | None = None
    placement: str = "right"


class ControlOverlay(QFrame):
    """Compact map-hosted first-level control menu."""

    minimizeRequested = pyqtSignal()
    closeRequested = pyqtSignal()
    layoutChanged = pyqtSignal()
    pageRequested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ControlOverlay")
        self._pages: dict[str, ControlOverlayPage] = {}
        self._menu_buttons: dict[str, QPushButton] = {}
        self._collapsed = False
        self._menu_layout: QVBoxLayout | None = None
        self._collapse_button: QPushButton | None = None
        self._build_ui()

    def register_page(
        self,
        page_id: str,
        title: str,
        builder: Callable[[], QWidget],
        order: int,
        icon_text: str | None = None,
        preferred_size: QSize | None = None,
        placement: str = "right",
    ) -> None:
        self._pages[page_id] = ControlOverlayPage(
            page_id=page_id,
            title=title,
            builder=builder,
            order=order,
            icon_text=icon_text,
            preferred_size=preferred_size,
            placement=placement,
        )
        self._rebuild_menu()
        self.layoutChanged.emit()

    def page(self, page_id: str) -> ControlOverlayPage | None:
        return self._pages.get(page_id)

    def preferred_size(self) -> QSize:
        return QSize((46 if self._collapsed else 150) + 24, max(44, 44 * max(1, len(self._pages))))

    def show_menu(self) -> None:
        self._sync_menu_button_text()
        self.layoutChanged.emit()

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapse_button is not None:
            self._collapse_button.setText(">" if self._collapsed else "<")
        self._sync_menu_button_text()
        self.layoutChanged.emit()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlOverlay {
                background: rgba(255, 255, 255, 245);
                border: 1px solid rgba(209, 213, 219, 230);
                border-radius: 0px;
            }
            QPushButton#ControlOverlayCollapseButton {
                background: #047857;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                min-width: 24px;
                max-width: 24px;
                min-height: 44px;
                padding: 0px;
                font-size: 20px;
                font-weight: 900;
            }
            QPushButton#ControlOverlayCollapseButton:hover {
                background: #059669;
            }
            QPushButton.ControlMenuButton {
                background: transparent;
                color: #111827;
                border: none;
                border-radius: 0px;
                min-height: 44px;
                padding: 0px 10px;
                font-size: 15px;
                font-weight: 700;
                text-align: left;
            }
            QPushButton.ControlMenuButton:hover {
                background: #eff6ff;
                color: #1d4ed8;
            }
            """
        )
        shell = QHBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        menu_buttons = QWidget(self)
        self._menu_layout = QVBoxLayout(menu_buttons)
        self._menu_layout.setContentsMargins(0, 0, 0, 0)
        self._menu_layout.setSpacing(0)
        shell.addWidget(menu_buttons, 1)

        self._collapse_button = QPushButton("<")
        self._collapse_button.setObjectName("ControlOverlayCollapseButton")
        self._collapse_button.setToolTip("展开/收起菜单")
        self._collapse_button.clicked.connect(self.toggle_collapsed)
        shell.addWidget(self._collapse_button, 0)

    def _rebuild_menu(self) -> None:
        if self._menu_layout is None:
            return
        self._menu_buttons.clear()
        while self._menu_layout.count():
            item = self._menu_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for page in sorted(self._pages.values(), key=lambda candidate: candidate.order):
            button = QPushButton(self._menu_label(page))
            button.setProperty("class", "ControlMenuButton")
            button.clicked.connect(lambda checked=False, page_id=page.page_id: self.pageRequested.emit(page_id))
            self._menu_layout.addWidget(button)
            self._menu_buttons[page.page_id] = button

    def _sync_menu_button_text(self) -> None:
        for page_id, button in self._menu_buttons.items():
            page = self._pages.get(page_id)
            if page is not None:
                button.setText(self._menu_label(page))

    def _menu_label(self, page: ControlOverlayPage) -> str:
        icon = page.icon_text or "*"
        return icon if self._collapsed else f"{icon}  {page.title}"


class ControlPageWindow(QFrame):
    """Separate map-hosted popup window for second-level control content."""

    closeRequested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ControlPageWindow")
        self._title_label: QLabel | None = None
        self._scroll: QScrollArea | None = None
        self._content_widget: QWidget | None = None
        self._preferred_size = QSize(380, 430)
        self._placement = "right"
        self._build_ui()
        self.hide()

    def preferred_size(self) -> QSize:
        return self._preferred_size

    def placement(self) -> str:
        return self._placement

    def set_page(
        self,
        title: str,
        widget: QWidget,
        preferred_size: QSize | None = None,
        placement: str = "right",
    ) -> None:
        self._preferred_size = preferred_size or QSize(380, 430)
        self._placement = placement
        if self._title_label is not None:
            self._title_label.setText(title)
        if self._scroll is None:
            return
        if self._content_widget is not None:
            self._scroll.takeWidget()
        self._content_widget = widget
        self._scroll.setWidget(widget)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlPageWindow {
                background: rgba(255, 255, 255, 248);
                border: 1px solid rgba(209, 213, 219, 230);
                border-radius: 10px;
            }
            QLabel#ControlPageTitle {
                color: #111827;
                font-size: 15px;
                font-weight: 900;
            }
            QPushButton.ControlPageToolButton {
                background: #f3f4f6;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                min-width: 42px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 800;
            }
            QPushButton.ControlPageToolButton:hover {
                background: #e5e7eb;
            }
            QPushButton#ControlPageCloseButton:hover {
                background: #991b1b;
                border-color: #991b1b;
                color: #ffffff;
            }
            QScrollArea#ControlPageScroll {
                background: transparent;
                border: none;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._title_label = QLabel("控制")
        self._title_label.setObjectName("ControlPageTitle")
        header.addWidget(self._title_label, 1)
        close_button = QPushButton("X")
        close_button.setObjectName("ControlPageCloseButton")
        close_button.setProperty("class", "ControlPageToolButton")
        close_button.clicked.connect(self.closeRequested.emit)
        header.addWidget(close_button)
        layout.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("ControlPageScroll")
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll, 1)


class ControlOverlayMarker(QPushButton):
    """Small map marker used to restore the minimized control menu."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ControlOverlayMarker")
        self.setText("仿真控制")
        self.setStyleSheet(
            """
            QPushButton#ControlOverlayMarker {
                background: rgba(255, 255, 255, 245);
                color: #111827;
                border: 1px solid rgba(209, 213, 219, 230);
                border-radius: 8px;
                min-height: 30px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 900;
            }
            QPushButton#ControlOverlayMarker:hover {
                background: #eff6ff;
                color: #1d4ed8;
            }
            """
        )
