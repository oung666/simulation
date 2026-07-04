from __future__ import annotations


def build_application_stylesheet() -> str:
    return """
    QMainWindow#MainChrome {
        background: #ededed;
    }

    QMainWindow::separator {
        background: #d9d9d9;
        border: none;
        width: 8px;
        height: 8px;
    }

    QMainWindow::separator:hover {
        background: #cfcfcf;
    }

    QWidget {
        background: transparent;
        color: #1f1f1f;
        font-family: "Microsoft YaHei UI", "Segoe UI";
        font-size: 13px;
    }

    QWidget#DockSurface,
    QWidget#MapWorkspace {
        background: #ededed;
    }

    QToolBar {
        background: #f7f7f7;
        border: none;
        border-bottom: 1px solid #dddddd;
        spacing: 8px;
        padding: 8px 12px;
    }

    QToolBar::separator {
        background: #dddddd;
        width: 1px;
        margin: 6px 8px;
    }

    QToolButton,
    QPushButton {
        background: #07c160;
        border: none;
        border-radius: 10px;
        color: #ffffff;
        font-size: 13px;
        font-weight: 700;
        min-height: 18px;
        padding: 8px 14px;
    }

    QToolBar QToolButton {
        background: #ffffff;
        border: 1px solid #dcdcdc;
        color: #2f2f2f;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 800;
        min-width: 88px;
        padding: 8px 14px;
    }

    QToolButton:hover,
    QPushButton:hover {
        background: #06ad56;
    }

    QToolBar QToolButton:hover {
        background: #f4f4f4;
        border: 1px solid #dcdcdc;
        color: #2f2f2f;
    }

    QToolBar QComboBox#ToolbarSpeedCombo {
        background: #ffffff;
        border: 1px solid #dcdcdc;
        border-radius: 12px;
        color: #2f2f2f;
        font-size: 12px;
        font-weight: 800;
        min-width: 92px;
        padding: 7px 12px;
    }

    QToolButton#BlueSideToolButton {
        background: #2b6ef2;
        border: 1px solid #d7e5ff;
        color: #ffffff;
    }

    QToolButton#RedSideToolButton {
        background: #e04444;
        border: 1px solid #ffd6d6;
        color: #ffffff;
    }

    QToolButton#UnitsToolButton {
        background: #e8f1ff;
        border: 1px solid #bdd6ff;
        color: #1f56b3;
    }

    QToolButton#ReplayToolButton,
    QToolButton#ReplayRecordToolButton {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #9a3412;
    }

    QToolButton#ReplayRecordToolButton:checked {
        background: #dc2626;
        border: 1px solid #b91c1c;
        color: #ffffff;
    }

    QToolButton#MessageToolButton {
        background: #e8f8ee;
        border: 1px solid #b8e7c7;
        color: #087f45;
    }

    QToolButton#DebugToolButton {
        background: #fff4df;
        border: 1px solid #f4d19c;
        color: #8a5200;
    }

    QToolButton#ResetToolButton {
        background: #f3f4f6;
        border: 1px solid #d1d5db;
        color: #374151;
    }

    QToolButton#PlayToolButton {
        background: #07c160;
        border: 1px solid #07c160;
        color: #ffffff;
    }

    QStatusBar {
        background: #f7f7f7;
        border-top: 1px solid #dddddd;
        color: #666666;
        min-height: 30px;
    }

    QDockWidget {
        font-size: 13px;
        border: none;
    }

    QDockWidget::title {
        background: #f7f7f7;
        color: #2b2b2b;
        font-size: 14px;
        font-weight: 800;
        padding: 8px 12px;
        border-bottom: 1px solid #dddddd;
        text-align: left;
    }

    QDockWidget > QWidget {
        background: transparent;
    }

    QLabel#CaptionLabel {
        color: #777777;
        font-size: 12px;
        font-weight: 700;
    }

    QLabel#ValueLabel {
        color: #2f2f2f;
        font-size: 13px;
    }

    QLabel#InfoChip {
        background: #ffffff;
        border: 1px solid #dcdcdc;
        border-radius: 11px;
        color: #2f2f2f;
        font-size: 12px;
        font-weight: 800;
        padding: 6px 10px;
    }

    QFrame#PanelCard {
        background: #ffffff;
        border: 1px solid #e1e1e1;
        border-radius: 14px;
    }

    QLabel#PanelTitle {
        color: #222222;
        font-size: 15px;
        font-weight: 900;
    }

    QPushButton#GhostButton {
        background: #ffffff;
        border: 1px solid #dcdcdc;
        color: #2f2f2f;
    }

    QPushButton#GhostButton:hover {
        background: #f5f5f5;
    }

    QPushButton#WarmButton {
        background: #07c160;
        border: none;
        color: #ffffff;
    }

    QPushButton#BlueSideButton,
    QPushButton#RedSideButton {
        border: 1px solid transparent;
        border-radius: 12px;
        color: #ffffff;
        font-size: 12px;
        font-weight: 800;
        min-width: 84px;
        padding: 9px 16px;
    }

    QPushButton#BlueSideButton {
        background: #5b92ff;
    }

    QPushButton#RedSideButton {
        background: #ff6b6b;
    }

    QComboBox,
    QDoubleSpinBox,
    QLineEdit {
        background: #ffffff;
        border: 1px solid #dcdcdc;
        border-radius: 10px;
        color: #222222;
        padding: 8px 10px;
        min-height: 18px;
    }

    QComboBox:focus,
    QDoubleSpinBox:focus,
    QLineEdit:focus {
        border: 1px solid #07c160;
    }

    QComboBox::drop-down {
        border: none;
        width: 22px;
    }

    QListWidget {
        background: #ffffff;
        border: 1px solid #e1e1e1;
        border-radius: 12px;
        color: #2f2f2f;
        padding: 6px;
    }

    QTableWidget {
        background: #ffffff;
        alternate-background-color: #f6fbff;
        border: 1px solid #e1e1e1;
        border-radius: 12px;
        color: #1f1f1f;
        gridline-color: #e5e7eb;
        selection-background-color: #dbeafe;
        selection-color: #1f1f1f;
    }

    QHeaderView::section {
        background: #f3f4f6;
        border: none;
        border-bottom: 1px solid #dcdcdc;
        color: #374151;
        font-weight: 800;
        padding: 8px;
    }

    QPlainTextEdit {
        background: #ffffff;
        border: 1px solid #e1e1e1;
        border-radius: 12px;
        color: #303030;
        font-family: "Cascadia Mono", "Consolas";
        font-size: 12px;
        padding: 10px;
    }

    QMenu {
        background: #ffffff;
        border: 1px solid #dcdcdc;
        border-radius: 8px;
        color: #1f1f1f;
        font-size: 13px;
        padding: 6px;
    }

    QMenu::item {
        background: transparent;
        border-radius: 6px;
        color: #1f1f1f;
        min-width: 180px;
        padding: 8px 22px;
    }

    QMenu::item:selected {
        background: #07c160;
        color: #ffffff;
    }

    QMenu::separator {
        background: #e5e5e5;
        height: 1px;
        margin: 6px 8px;
    }

    QScrollArea {
        border: none;
        background: transparent;
    }

    QScrollBar:vertical {
        background: #f1f1f1;
        width: 10px;
        margin: 8px 2px 8px 2px;
        border-radius: 5px;
    }

    QScrollBar::handle:vertical {
        background: #cccccc;
        min-height: 28px;
        border-radius: 5px;
    }

    QScrollBar::handle:vertical:hover {
        background: #b7b7b7;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        background: transparent;
        height: 0px;
    }

    QScrollBar#MapScrollBar:vertical {
        background: #dde8ee;
        width: 14px;
        margin: 0px;
        border-left: 1px solid #c8d4dc;
    }

    QScrollBar#MapScrollBar:horizontal {
        background: #dde8ee;
        height: 14px;
        margin: 0px;
        border-top: 1px solid #c8d4dc;
    }

    QScrollBar#MapScrollBar::handle:vertical,
    QScrollBar#MapScrollBar::handle:horizontal {
        background: #9cb3bf;
        border-radius: 6px;
        min-height: 28px;
        min-width: 28px;
        margin: 1px;
    }

    QScrollBar#MapScrollBar::handle:vertical:hover,
    QScrollBar#MapScrollBar::handle:horizontal:hover {
        background: #839eab;
    }

    QScrollBar#MapScrollBar::add-line:vertical,
    QScrollBar#MapScrollBar::sub-line:vertical,
    QScrollBar#MapScrollBar::add-page:vertical,
    QScrollBar#MapScrollBar::sub-page:vertical,
    QScrollBar#MapScrollBar::add-line:horizontal,
    QScrollBar#MapScrollBar::sub-line:horizontal,
    QScrollBar#MapScrollBar::add-page:horizontal,
    QScrollBar#MapScrollBar::sub-page:horizontal {
        background: transparent;
        width: 0px;
        height: 0px;
    }

    QWidget#MapScrollCorner {
        background: #dde8ee;
        border-left: 1px solid #c8d4dc;
        border-top: 1px solid #c8d4dc;
    }
    """
