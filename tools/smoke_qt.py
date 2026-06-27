from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPointF  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from simulation.core.geo import LonLat  # noqa: E402
from simulation.ui.main_window import MainWindow  # noqa: E402
from simulation.ui.new_unit_dialog import NewUnitDialog, NewUnitRequest, NewUnitWeaponRequest  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1280, 820)
    window.map_canvas.resize(900, 700)

    _check_control_overlay(window)
    _check_combat_log_overlay(window)
    _check_unit_popup(window)
    _check_new_unit_dialog(window)
    _check_new_unit_creation_flow(window)

    print("Qt smoke checks passed.")
    app.quit()
    return 0


def _check_control_overlay(window: MainWindow) -> None:
    assert window.control_overlay.parent() is window.map_canvas
    window._position_control_overlay_widgets()
    assert not window.control_overlay.isHidden()
    window.control_overlay.toggle_collapsed()
    window._position_control_overlay_widgets()
    assert window.control_overlay.width() <= 80
    window.control_overlay.toggle_collapsed()
    for page_id in ["display", "new_unit", "route", "missions", "combat_log"]:
        assert window.control_overlay.page(page_id) is not None
        window._show_control_page(page_id)
        assert not window.control_page_window.isHidden()
    window._begin_new_unit_position_pick()
    assert window.map_canvas._apply_pending_interaction(
        QPointF(window.map_canvas.width() / 2, window.map_canvas.height() / 2)
    )
    assert window._new_unit_position is not None
    assert window._new_unit_position == window.map_canvas.center
    window._begin_new_unit_position_pick()
    window._handle_coordinate_picked(120.25, 24.5)
    assert window._new_unit_position.lon == 120.25
    assert window._new_unit_position.lat == 24.5
    window._minimize_control_overlay()
    assert window.control_overlay.isHidden()
    assert window.control_page_window.isHidden()
    assert not window.control_overlay_marker.isHidden()
    window._restore_control_overlay()
    assert not window.control_overlay.isHidden()
    assert window.control_overlay_marker.isHidden()


def _check_combat_log_overlay(window: MainWindow) -> None:
    assert window.combat_log_overlay.parent() is window.map_canvas
    window._position_combat_log_widgets()
    assert not window.combat_log_overlay.isHidden()
    window._minimize_combat_log_overlay()
    assert window.combat_log_overlay.isHidden()
    assert not window.combat_log_marker.isHidden()
    window._restore_combat_log_overlay()
    assert not window.combat_log_overlay.isHidden()
    assert window.combat_log_marker.isHidden()


def _check_unit_popup(window: MainWindow) -> None:
    assert window.unit_info_popup.parent() is window.map_canvas
    unit_id = window.scenario.units[0].unit_id
    assert window.map_canvas.select_unit(unit_id)
    window._show_unit_popup(unit_id)
    assert not window.unit_info_popup.isHidden()
    expected_x = window.map_canvas.width() - window.unit_info_popup.width() - 8
    assert window.unit_info_popup.x() == expected_x
    window._hide_unit_popup()
    assert window.unit_info_popup.isHidden()


def _check_new_unit_dialog(window: MainWindow) -> None:
    dialog = NewUnitDialog(window, LonLat(120.0, 24.0), "blue")
    if dialog.weapon_combo.count() > 1:
        dialog.weapon_combo.setCurrentIndex(1)
        dialog.weapon_quantity_input.setValue(3)
        dialog._add_selected_weapon()
    request = dialog.request()
    assert request.side == "blue"
    assert request.unit_type
    assert request.class_name
    assert request.unit_id
    assert request.name
    assert request.position.lon == 120.0
    assert request.position.lat == 24.0
    assert len(request.weapons) >= 1
    assert request.weapons[0].quantity == 3


def _check_new_unit_creation_flow(window: MainWindow) -> None:
    request = NewUnitRequest(
        side="blue",
        unit_type="aircraft",
        class_name="F-35A Lightning II",
        unit_id="smoke-aircraft",
        name="Smoke Aircraft",
        position=LonLat(120.0, 24.0),
        weapons=[NewUnitWeaponRequest("AIM-120D AMRAAM", 2)],
    )
    unit = window._new_unit_from_request(request)
    assert unit.unit_id == "smoke-aircraft"
    assert unit.class_name == "F-35A Lightning II"
    assert len(unit.weapons) == 1
    assert unit.weapons[0].current_quantity == 2
    assert window.terrain_classifier.validate_deployment_for_unit(unit).ok

    invalid_ground_request = NewUnitRequest(
        side="blue",
        unit_type="ground_vehicle",
        class_name="HIMARS",
        unit_id="smoke-ground",
        name="Smoke Ground",
        position=LonLat(118.0, 21.0),
        weapons=[],
    )
    invalid_ground = window._new_unit_from_request(invalid_ground_request)
    assert not window.terrain_classifier.validate_deployment_for_unit(invalid_ground).ok


if __name__ == "__main__":
    raise SystemExit(main())
