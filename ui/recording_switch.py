from __future__ import annotations

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QPushButton


class RecordingSwitchButton(QPushButton):
    """Recording toggle with a left/right sliding puck."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setText("")
        self.setToolTip("录制开关")
        self.setAccessibleName("录制开关")
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(self.sizeHint())
        self.setProperty("recording", False)
        self.toggled.connect(self._sync_recording_property)

    def sizeHint(self) -> QSize:
        return QSize(128, 40)

    def _sync_recording_property(self, checked: bool) -> None:
        self.setProperty("recording", bool(checked))
        self.update()

    def track_color_name(self) -> str:
        return "#ffffff"

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = QRectF(3, 3, self.width() - 6, self.height() - 6)
        radius = track.height() / 2
        painter.setPen(QPen(QColor("#d1d5db"), 1.5))
        painter.setBrush(QColor(self.track_color_name()))
        painter.drawRoundedRect(track, radius, radius)

        margin = 7
        knob_size = self.height() - margin * 2
        knob_x = margin if not self.isChecked() else self.width() - knob_size - margin
        knob = QRectF(knob_x, margin, knob_size, knob_size)
        knob_color = QColor("#07c160") if self.isChecked() else QColor("#ffffff")
        shadow = QRectF(knob)
        shadow.translate(0, 1.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(17, 24, 39, 45))
        painter.drawRoundedRect(shadow, knob_size / 2, knob_size / 2)
        painter.setPen(QPen(QColor("#059669" if self.isChecked() else "#9ca3af"), 1.2))
        painter.setBrush(knob_color)
        painter.drawRoundedRect(knob, knob_size / 2, knob_size / 2)
