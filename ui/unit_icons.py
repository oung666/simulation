from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt5.QtCore import QByteArray, QPointF, QRectF
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtSvg import QSvgRenderer


_SVG_CACHE: dict[tuple[str, str], QSvgRenderer] = {}


def unit_icon_name(unit: Any) -> str | None:
    unit_type = _unit_value(unit, "unit_type")
    return {
        "aircraft": "flight_black_24dp.svg",
        "ship": "directions_boat_black_24dp.svg",
        "facility": "radar_black_24dp.svg",
        "airbase": "flight_takeoff_black_24dp.svg",
    }.get(unit_type)


def draw_svg_unit_icon(
    painter: QPainter,
    icon_name: str,
    screen: QPointF,
    color: QColor,
    heading: float = 0.0,
    size: float = 28.0,
) -> bool:
    renderer = _svg_renderer(icon_name, color)
    if renderer is None:
        return False

    painter.save()
    painter.translate(screen)
    painter.rotate(heading)
    renderer.render(painter, QRectF(-size / 2.0, -size / 2.0, size, size))
    painter.restore()
    return True


def _svg_renderer(icon_name: str, color: QColor) -> QSvgRenderer | None:
    color_name = color.name()
    key = (icon_name, color_name)
    if key in _SVG_CACHE:
        return _SVG_CACHE[key]

    icon_path = Path(__file__).resolve().parents[1] / "assets" / "svg" / icon_name
    if not icon_path.exists():
        return None
    svg_text = icon_path.read_text(encoding="utf-8").replace("#ffffff", color_name)
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    if not renderer.isValid():
        return None
    _SVG_CACHE[key] = renderer
    return renderer


def _unit_value(unit: Any, key: str) -> str:
    if isinstance(unit, dict):
        return str(unit.get(key, ""))
    return str(getattr(unit, key, ""))

