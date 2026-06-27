from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import QSize

if TYPE_CHECKING:
    from simulation.ui.control_overlay import ControlOverlay
    from simulation.ui.main_window import MainWindow


def register_main_control_pages(window: MainWindow, overlay: ControlOverlay) -> None:
    """Register first-level map control pages in one extensible place."""
    pages = [
        ("map", "离线地图", window._build_map_card, 10, "⌖", QSize(360, 260), "right"),
        ("display", "显示控制", window._build_display_card, 20, "▣", QSize(360, 300), "right"),
        ("json", "JSON 场景", window._build_json_card, 30, "JS", QSize(420, 260), "right"),
        ("new_unit", "新增单位", window._build_new_unit_card, 40, "+", QSize(380, 260), "right"),
        ("route", "路线设置", window._build_route_card, 50, "⇄", QSize(380, 360), "right"),
        ("missions", "任务查看", window._build_mission_control_card, 60, "◎", QSize(520, 430), "right"),
        ("combat_log", "日志控制", window._build_combat_log_control_card, 70, "LOG", QSize(360, 280), "below"),
    ]
    for page_id, title, builder, order, icon, preferred_size, placement in pages:
        overlay.register_page(page_id, title, builder, order, icon, preferred_size, placement)
