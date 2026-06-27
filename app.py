from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from simulation.styles.theme import build_application_stylesheet
from simulation.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Qt Frontend V6")
    app.setStyleSheet(build_application_stylesheet())

    font = QFont("Microsoft YaHei UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    window = MainWindow()
    window.resize(1280, 820)
    window.show()
    return app.exec_()

